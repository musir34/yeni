# ✅ CentralStock & Trendyol Senkronizasyon Sistemi - KURULUM TAMAMLANDI

## 📊 Mevcut Durum

✅ **StockPushLog** tablosu oluşturuldu (0 kayıt - henüz ilk gönderim yapılmadı)
✅ **CentralStock** aktif: 3,071 ürün
✅ **OrderCreated** bekleyen: 53 sipariş (rezerve edilmiş)

---

## 🎯 Sistem Özeti

### 1️⃣ **Yeni Sipariş (OrderCreated)** 
```
Trendyol → OrderCreated tablosu
❌ CentralStock'tan DÜŞÜLMEZ
✅ Sadece REZERVE sayılır
```

### 2️⃣ **Sipariş Hazırlandığında (OrderPicking)**
```
Sipariş Hazırla → Onayla
├─> RafUrun.adet ↓
└─> CentralStock.qty ↓
    └─> updated_at güncellenir
```

### 3️⃣ **Trendyol'a Stok Gönderimi**
```
⏰ Her 10 dakikada bir otomatik

Hesaplama:
Available = CentralStock.qty - (OrderCreated rezerv)

Örnek:
- CentralStock: 3,071 ürün
- Rezerv (53 sipariş): ~150-200 adet (tahmini)
- Trendyol'a gönderilen: 2,900 adet müsait stok
```

---

## 🚀 Çalıştırma

### Scheduler'ı Aktif Et
```powershell
cd C:\Users\MUS1R\Documents\yeni
$env:ENABLE_JOBS="1"
flask run
```

### İlk Gönderimi Manuel Tetikle (Opsiyonel)
```python
# Python konsolunda:
from app import app, push_central_stock_to_trendyol
with app.app_context():
    push_central_stock_to_trendyol()
```

---

## 📝 Log Görüntüleme

### Son 10 Gönderimi Göster
```python
from app import app
from models import StockPushLog

with app.app_context():
    logs = StockPushLog.query.order_by(
        StockPushLog.push_time.desc()
    ).limit(10).all()
    
    for log in logs:
        status = "✅" if log.success else "❌"
        print(f"{status} {log.push_time}: {log.total_items} ürün, "
              f"{log.total_quantity} adet, rezerv: {log.reserved_quantity}")
```

### Bugünkü Gönderimler
```sql
SELECT 
    push_time,
    total_items,
    total_quantity,
    reserved_quantity,
    success,
    duration_seconds
FROM stock_push_log
WHERE push_time >= CURRENT_DATE
ORDER BY push_time DESC;
```

---

## 📅 Zamanlama Detayları

| Görev | Frekans | İlk Çalışma | Açıklama |
|-------|---------|-------------|----------|
| `pull_orders_job` | Her 4 dk | Hemen | Trendyol'dan sipariş çeker |
| `push_stock_job` | **Her 10 dk** | 3 dk sonra | Stok Trendyol'a gönderir |
| `pull_returns_daily` | Günlük | 23:50 | İade siparişlerini çeker |

---

## 🔍 Monitoring

### Sistem Durumu Kontrolü
```python
from app import app, db
from models import StockPushLog, CentralStock, OrderCreated
from datetime import datetime, timedelta

with app.app_context():
    # Son 1 saatteki gönderimler
    one_hour_ago = datetime.now() - timedelta(hours=1)
    recent = StockPushLog.query.filter(
        StockPushLog.push_time >= one_hour_ago
    ).count()
    
    print(f"📊 Son 1 saatte {recent} gönderim yapıldı")
    print(f"📦 Toplam CentralStock: {CentralStock.query.count()} ürün")
    print(f"🛒 Bekleyen sipariş: {OrderCreated.query.count()}")
    
    # Son gönderim başarılı mı?
    last = StockPushLog.query.order_by(
        StockPushLog.push_time.desc()
    ).first()
    
    if last:
        status = "✅ Başarılı" if last.success else "❌ Hatalı"
        print(f"🕐 Son gönderim: {last.push_time} - {status}")
        if not last.success:
            print(f"   Hata: {last.error_message}")
```

---

## 🐛 Sorun Giderme

### Problem: Scheduler çalışmıyor
```powershell
# Terminalde şu satırı görmeli:
# "Scheduler started (ENABLE_JOBS=on, leader ok)."

# Eğer görmüyorsan:
$env:ENABLE_JOBS="1"
flask run
```

### Problem: Stok gitmiyor
```python
# Log kontrol:
from app import app
from models import StockPushLog

with app.app_context():
    last = StockPushLog.query.order_by(
        StockPushLog.push_time.desc()
    ).first()
    
    if last and not last.success:
        print(f"Hata: {last.error_message}")
```

### Problem: Yanlış stok görünüyor
```python
# Rezerv kontrolü:
from app import app
from models import OrderCreated
import json

with app.app_context():
    reserved = {}
    for order in OrderCreated.query.all():
        try:
            details = json.loads(order.details) if isinstance(order.details, str) else order.details
            for item in (details if isinstance(details, list) else [details]):
                barcode = item.get('barcode')
                qty = int(item.get('quantity', 0))
                if barcode and qty > 0:
                    reserved[barcode] = reserved.get(barcode, 0) + qty
        except:
            pass
    
    print(f"Toplam rezerve adet: {sum(reserved.values())}")
    print(f"Toplam farklı barkod: {len(reserved)}")
```

---

## 📈 Beklenen Sonuçlar

### İlk 24 Saatte:
- ✅ 144 adet stok gönderimi (10 dk × 6/saat × 24 saat)
- ✅ Trendyol'da güncel stok görünümü
- ✅ `stock_push_log` tablosunda 144 kayıt

### İlk Hafta:
- ✅ ~1,000 stok gönderimi
- ✅ Hata oranı <%1
- ✅ Ortalama işlem süresi <5 saniye

---

## 🎉 Başarı Kriterleri

✅ Scheduler düzgün çalışıyor
✅ Her 10 dakikada otomatik gönderim yapılıyor
✅ Log tablosu dolmaya başladı
✅ Trendyol'da stok güncel
✅ OrderCreated siparişler rezerve sayılıyor
✅ OrderPicking'e geçenlerde stok düşüyor

---

## 📞 Önemli Dosyalar

| Dosya | İşlev |
|-------|-------|
| `app.py` | Zamanlama ve stok gönderim fonksiyonu |
| `models.py` | StockPushLog model tanımı |
| `update_service.py` | Sipariş hazırlandığında stok düşürme |
| `STOK_SISTEMI_DOKUMAN.md` | Detaylı dokümantasyon |

---

## 🚦 Sistem Durumu: HAZIR ✅

**İlk çalıştırma için:**
```powershell
cd C:\Users\MUS1R\Documents\yeni
$env:ENABLE_JOBS="1"
flask run
```

**3 dakika sonra ilk stok gönderimi başlayacak!** 🚀
