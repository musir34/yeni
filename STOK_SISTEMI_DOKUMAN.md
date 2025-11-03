# 📦 CentralStock ve Trendyol Senkronizasyon Sistemi

## 🎯 Sistem Mantığı

### 1️⃣ **Yeni Sipariş Geldiğinde (OrderCreated - "Yeni")**
```
Trendyol'dan sipariş → OrderCreated tablosuna kaydedilir
❗ CentralStock'tan DÜŞÜLMEZ (sadece REZERVE sayılır)
```

**Neden düşülmez?**
- Sipariş henüz hazırlanmadı
- İptal edilebilir
- Müşteri ödemesi henüz netleşmemiş olabilir
- Stok fiziksel olarak depoda hala mevcut

---

### 2️⃣ **Sipariş Hazırlandığında (OrderPicking - "İşleme Alındı")**
```
Sipariş Hazırla → "Onayla" butonu → update_service.py/confirm_packing
├─> Raflardan stok düşülür (RafUrun.adet ↓)
└─> CentralStock'tan düşülür (CentralStock.qty ↓)
```

**Dosya:** `update_service.py` (satır 197-210)
```python
# 6c) CentralStock: quantity kadar düş
cs = CentralStock.query.get(bc)
if not cs:
    cs = CentralStock(barcode=bc, qty=0)
    db.session.add(cs)

eski_cs = cs.qty or 0
cs.qty = max(0, eski_cs - adet)
cs.updated_at = datetime.utcnow()  # 🔧 Manuel güncelleme
```

---

### 3️⃣ **Trendyol'a Stok Gönderimi (Her 10 Dakikada)**

#### 📊 Gönderilen Miktar Hesaplama:
```python
Available Stock = CentralStock.qty - (OrderCreated rezerv toplamı)
```

**Örnek:**
- Barkod: 8699001234567
- CentralStock.qty: 50 adet
- OrderCreated'daki rezerv: 8 adet (3 bekleyen sipariş)
- **Trendyol'a gönderilen: 42 adet** ✅

#### 🔄 Otomatik Zamanlama:
**Dosya:** `app.py` (satır ~463-470)
```python
_add_job_safe(
    push_stock_job,
    trigger='interval',
    id="push_stock",
    minutes=10,  # 🔧 10 dakikada bir
    next_run_time=now + timedelta(minutes=3)  # İlk çalışma 3 dk sonra
)
```

#### 📝 Log Kaydı:
Her gönderim **`stock_push_log`** tablosuna yazılır:
```sql
CREATE TABLE stock_push_log (
    id SERIAL PRIMARY KEY,
    push_time TIMESTAMPTZ NOT NULL,
    total_items INTEGER NOT NULL,        -- Kaç ürün gönderildi
    total_quantity INTEGER NOT NULL,     -- Toplam adet
    reserved_quantity INTEGER NOT NULL,  -- Rezerve miktar
    batch_count INTEGER NOT NULL,        -- Kaç batch gönderildi
    success BOOLEAN NOT NULL,            -- Başarılı mı?
    error_message TEXT,                  -- Hata varsa
    duration_seconds FLOAT               -- İşlem süresi
);
```

---

## 🔧 Kurulum ve Çalıştırma

### 1. Migration Uygula
```powershell
cd C:\Users\MUS1R\Documents\yeni
flask db upgrade
```

### 2. Sunucuyu Başlat
```powershell
$env:ENABLE_JOBS="1"
flask run
```

### 3. Log'ları Kontrol Et
```python
# Python konsolunda veya route'ta:
from models import StockPushLog

# Son 10 gönderimi göster
logs = StockPushLog.query.order_by(StockPushLog.push_time.desc()).limit(10).all()
for log in logs:
    print(f"{log.push_time}: {log.total_items} ürün, başarılı={log.success}")
```

---

## 📊 Veri Akışı Diyagramı

```
┌─────────────────────┐
│  Trendyol API       │
│  (Yeni Sipariş)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  OrderCreated       │  ← Rezerve sayılır
│  (details JSON)     │    (stok düşmez)
└─────────────────────┘
           │
           │ (Sipariş Hazırla)
           ▼
┌─────────────────────┐
│  confirm_packing()  │
└──────────┬──────────┘
           │
           ├─> RafUrun.adet ↓
           └─> CentralStock.qty ↓
                     │
                     ▼
           ┌─────────────────────┐
           │  OrderPicking       │
           │  (Hazırlandı)       │
           └─────────────────────┘

┌─────────────────────────────────────┐
│  Zamanlanmış Görev (Her 10 dk)     │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  push_central_stock_to_trendyol()  │
│                                     │
│  1. CentralStock.qty oku           │
│  2. OrderCreated rezerv hesapla    │
│  3. Available = qty - rezerv       │
│  4. Trendyol API'ye gönder         │
│  5. StockPushLog'a kaydet          │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────┐
│  Trendyol API       │
│  (Stok Güncelleme)  │
└─────────────────────┘
```

---

## ✅ Avantajlar

1. **Çift Rezervasyon Önlenir:** Sipariş geldiğinde rezerve sayılır, başka müşteri satın alamaz
2. **Gerçek Zamanlı Stok:** 10 dakikada bir Trendyol'da doğru stok görünür
3. **Audit Trail:** Her gönderim `stock_push_log` tablosunda kayıtlı
4. **Hata Yönetimi:** API hatası olursa log'da görülür, tekrar denenebilir
5. **Performans:** 100'lük batch'ler halinde gönderim

---

## 🐛 Sorun Giderme

### Problem: Stok Trendyol'a gitmiyor
```python
# Log kontrol et
from models import StockPushLog
last = StockPushLog.query.order_by(StockPushLog.push_time.desc()).first()
print(f"Son gönderim: {last.push_time}")
print(f"Başarılı: {last.success}")
if not last.success:
    print(f"Hata: {last.error_message}")
```

### Problem: Scheduler çalışmıyor
```powershell
# Loglara bak
# Şu satırı görmeli: "Scheduler started (ENABLE_JOBS=on, leader ok)."
```

### Problem: Rezerv yanlış hesaplanıyor
```python
# OrderCreated kontrolü
from models import OrderCreated
orders = OrderCreated.query.all()
print(f"Toplam bekleyen sipariş: {len(orders)}")
```

---

## 📞 İlgili Dosyalar

| Dosya | Satır | Açıklama |
|-------|-------|----------|
| `app.py` | 287-426 | `push_central_stock_to_trendyol()` fonksiyonu |
| `app.py` | 463-470 | Zamanlama ayarları (10 dakika) |
| `models.py` | 148-160 | `StockPushLog` model tanımı |
| `update_service.py` | 197-210 | CentralStock düşürme (Picking'e geçiş) |
| `stock_management.py` | 312-314 | CentralStock artırma (Rafa ekleme) |

---

## 🎉 Sonuç

Artık sisteminiz:
- ✅ Yeni siparişleri rezerve sayıyor (düşmüyor)
- ✅ Hazırlanan siparişlerde stok düşüyor
- ✅ Her 10 dakikada Trendyol'a güncel stok gönderiyor
- ✅ Tüm gönderimler veritabanına loglanıyor

**Güvenli ve izlenebilir stok yönetimi! 🚀**
