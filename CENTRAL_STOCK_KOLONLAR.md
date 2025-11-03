# 📊 CentralStock Tablosu - Kolon Açıklamaları

## 🔍 Tablo Yapısı

```sql
CREATE TABLE central_stock (
    barcode VARCHAR PRIMARY KEY,     -- Ürün barkodu
    qty INTEGER NOT NULL,            -- Stok adedi
    updated_at TIMESTAMP,            -- ⏰ Stoğun fiziksel değişim tarihi
    last_push_date TIMESTAMPTZ       -- 📤 Trendyol'a gönderim tarihi
);
```

---

## 📋 Kolon Detayları

### 1️⃣ `barcode` (Primary Key)
**Ne İşe Yarar:** Ürün barkodu (benzersiz)
**Örnek:** `8699001234567`

---

### 2️⃣ `qty` (Quantity - Miktar)
**Ne İşe Yarar:** Merkez depodaki toplam stok adedi
**Örnek:** `21` (21 adet var)

**Ne Zaman Değişir:**
- ✅ Rafa yeni ürün eklendiğinde → ARTAR
- ✅ Sipariş hazırlandığında → AZALIR
- ✅ Raftan ürün silindiğinde → AZALIR
- ✅ Değişim/iade ürünü çıktığında → AZALIR

---

### 3️⃣ `updated_at` - ⏰ FİZİKSEL STOK DEĞİŞİM TARİHİ
**Ne İşe Yarar:** Stoğun **fiziksel olarak** depoda en son ne zaman değiştiğini gösterir

**Ne Zaman Güncellenir:**
```python
# 1. Rafa ürün eklendiğinde (stock_management.py)
cs.qty = (cs.qty or 0) + count
cs.updated_at = datetime.utcnow()  # ✅ Güncellenir

# 2. Sipariş hazırlandığında (update_service.py)
cs.qty = max(0, eski_cs - adet)
cs.updated_at = datetime.utcnow()  # ✅ Güncellenir

# 3. Raftan ürün silindiğinde (raf_sistemi.py)
cs.qty = max(0, cs.qty - urun.adet)
cs.updated_at = datetime.utcnow()  # ✅ Güncellenir
```

**Örnek Senaryo:**
```
Tarih: 2025-10-30 13:13:18
İşlem: Rafa 5 adet eklendi
Sonuç: qty: 16→21, updated_at: 2025-10-30 13:13:18 ✅

Tarih: 2025-10-31 09:15:10  
İşlem: Sipariş hazırlandı (2 adet çıktı)
Sonuç: qty: 21→19, updated_at: 2025-10-31 09:15:10 ✅
```

**❓ Kullanım Alanları:**
- Hangi ürünlerin stoku uzun süredir değişmedi?
- En son hangi ürünler hareket etti?
- Stok hareketlerini takip et
- Ölü stok analizi (uzun süredir değişmeyen)

---

### 4️⃣ `last_push_date` - 📤 TRENDYOL'A GÖNDERİM TARİHİ
**Ne İşe Yarar:** Bu ürünün stok bilgisinin **Trendyol'a** en son ne zaman gönderildiğini gösterir

**Ne Zaman Güncellenir:**
```python
# Sadece push_central_stock_to_trendyol() çalıştığında
# Her 10 dakikada bir otomatik

push_time = datetime.now(ZoneInfo("Europe/Istanbul"))
barcode_obj.last_push_date = push_time  # ✅ Güncellenir
```

**Örnek Senaryo:**
```
2025-11-03 22:15:00 - İlk gönderim
→ 3,071 ürün Trendyol'a gönderildi
→ Tüm barkodların last_push_date = 2025-11-03 22:15:00

2025-11-03 22:25:00 - İkinci gönderim (10 dk sonra)
→ 3,071 ürün tekrar gönderildi
→ Tüm barkodların last_push_date = 2025-11-03 22:25:00
```

**❓ Kullanım Alanları:**
- Scheduler çalışıyor mu kontrol et
- Hangi ürünler uzun süredir Trendyol'a gönderilmedi?
- API hatası durumunda hangi ürünler güncellenmedi?
- Senkronizasyon doğrulama

---

## 🔄 FARKLAR - `updated_at` vs `last_push_date`

| Özellik | `updated_at` | `last_push_date` |
|---------|--------------|------------------|
| **Ne gösterir?** | Fiziksel stok değişimi | Trendyol'a gönderim |
| **Ne zaman değişir?** | qty değiştiğinde | Her 10 dk (push job) |
| **Tetikleyici** | Manuel işlemler | Otomatik scheduler |
| **Değişim sıklığı** | Sporadik (ihtiyaca göre) | Düzenli (10 dk) |
| **NULL olabilir mi?** | Hayır (default: now()) | Evet (ilk gönderime kadar) |

---

## 📊 GERÇEK HAYAT ÖRNEĞİ

### Senaryo 1: Normal Akış
```
2025-10-30 13:13:18 → Rafa 5 adet eklendi
├─ qty: 16 → 21
├─ updated_at: 2025-10-30 13:13:18 ✅
└─ last_push_date: NULL (henüz gönderilmedi)

2025-11-03 22:15:00 → İlk Trendyol gönderimi
├─ qty: 21 (değişmedi)
├─ updated_at: 2025-10-30 13:13:18 (değişmedi)
└─ last_push_date: 2025-11-03 22:15:00 ✅

2025-11-03 22:25:00 → İkinci Trendyol gönderimi
├─ qty: 21 (değişmedi)
├─ updated_at: 2025-10-30 13:13:18 (değişmedi)
└─ last_push_date: 2025-11-03 22:25:00 ✅
```

**Sonuç:** 
- `updated_at`: Stok son 4 gündür değişmemiş (ölü stok?)
- `last_push_date`: Trendyol güncel (10 dk önce gönderildi)

---

### Senaryo 2: Stok Hareketi
```
2025-11-03 22:15:00 → Trendyol gönderimi
├─ qty: 21
├─ updated_at: 2025-10-30 13:13:18
└─ last_push_date: 2025-11-03 22:15:00

2025-11-03 22:18:00 → Sipariş hazırlandı (3 adet çıktı)
├─ qty: 21 → 18 ✅
├─ updated_at: 2025-11-03 22:18:00 ✅
└─ last_push_date: 2025-11-03 22:15:00 (değişmedi)

2025-11-03 22:25:00 → Trendyol gönderimi (güncel stok)
├─ qty: 18 (değişmedi)
├─ updated_at: 2025-11-03 22:18:00 (değişmedi)
└─ last_push_date: 2025-11-03 22:25:00 ✅
```

**Sonuç:** 
- `updated_at`: 7 dk önce stok değişti
- `last_push_date`: Yeni stok Trendyol'a bildirildi

---

## 🔍 KULLANIM ÖRNEKLERİ

### 1. Ölü Stok Tespiti (30+ gün hareketsiz)
```sql
SELECT barcode, qty, updated_at
FROM central_stock
WHERE updated_at < NOW() - INTERVAL '30 days'
  AND qty > 0
ORDER BY updated_at ASC;
```

### 2. Scheduler Çalışıyor mu?
```sql
-- Son gönderim 15 dk'dan eski ise scheduler durmuş!
SELECT MAX(last_push_date) as son_gonderim,
       NOW() - MAX(last_push_date) as gecen_sure
FROM central_stock
WHERE last_push_date IS NOT NULL;
```

### 3. Senkronizasyon Kontrolü
```sql
-- Stoku değişen ama Trendyol'a henüz gönderilmemiş
SELECT barcode, qty, updated_at, last_push_date
FROM central_stock
WHERE updated_at > last_push_date 
   OR last_push_date IS NULL
ORDER BY updated_at DESC;
```

### 4. Bugün Hareket Eden Ürünler
```sql
SELECT barcode, qty, updated_at
FROM central_stock
WHERE updated_at >= CURRENT_DATE
ORDER BY updated_at DESC;
```

### 5. Gönderim Başarı Oranı
```sql
SELECT 
    COUNT(*) as toplam,
    COUNT(last_push_date) as gonderilmis,
    ROUND(COUNT(last_push_date)::numeric / COUNT(*) * 100, 2) as yuzde
FROM central_stock;
```

---

## 🎯 ÖZET

### `updated_at` = "DEPO HAREKETİ"
- ✅ Fiziksel stok değişimi
- ✅ Manuel işlemler
- ✅ Gerçek zamanlı güncelleme
- ❌ Trendyol'la ilgisi yok

### `last_push_date` = "TRENDYOL SENKRONİZASYONU"
- ✅ API gönderim zamanı
- ✅ Otomatik zamanlayıcı
- ✅ 10 dakikada bir
- ❌ Fiziksel stokla doğrudan bağlantısı yok

---

## 💡 NEDEN İKİSİ DE VAR?

1. **Takip:** Hangi ürünler hareket ediyor? (updated_at)
2. **Doğrulama:** Trendyol güncel mi? (last_push_date)
3. **Hata Tespiti:** Senkronizasyon sorunu var mı?
4. **Analiz:** Ölü stok, hızlı satan ürünler
5. **Monitoring:** Scheduler çalışıyor mu?

**Her iki kolon da farklı amaçlara hizmet eder!** 🎉
