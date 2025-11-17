# Yeni Sipariş - Raf Entegrasyonu

## 🎯 Özellik

Yeni sipariş oluştururken ürünler artık **raflardan otomatik olarak tahsis edilir** ve hangi raftan alındığı bilgisi siparişe kaydedilir.

## 📋 Yapılan Değişiklikler

### 1. Database Değişiklikleri

#### SiparisUrun Modeli
**Dosya:** `models.py`

```python
class SiparisUrun(db.Model):
    # ... mevcut alanlar ...
    raf_kodu = db.Column(db.String)  # YENİ: Hangi raftan alındığı
```

**Migration Gerekli:**
```bash
# Veritabanı migration'ı çalıştırın
flask db migrate -m "SiparisUrun tablosuna raf_kodu alanı eklendi"
flask db upgrade
```

Veya manuel SQL:
```sql
ALTER TABLE siparis_urunler ADD COLUMN raf_kodu VARCHAR;
```

### 2. Backend Değişiklikleri

#### siparisler.py

**Yeni Import:**
```python
from models import db, Product, YeniSiparis, SiparisUrun, RafUrun, CentralStock
```

**Yeni Fonksiyon:** `allocate_from_shelf_and_decrement(barcode, qty)`

Bu fonksiyon:
1. İlgili barkod için rafları stok miktarına göre (çoktan aza) sıralar
2. İhtiyaç duyulan miktarı raflardan tahsis eder
3. Raf stoklarını düşürür
4. CentralStock'tan da aynı miktarı düşürür
5. Hangi raflardan kaç adet alındığını döner

**Sipariş Kaydetme Güncellemesi:**

```python
# Her ürün için raf tahsisi
barkod = u_data.get('barkod', '')
alloc = allocate_from_shelf_and_decrement(barkod, qty=urun_adet)
raf_kodu = ", ".join([rk for rk in alloc["shelf_codes"] if rk]) if alloc["shelf_codes"] else None

# SiparisUrun kaydederken raf_kodu da eklenir
db.session.add(SiparisUrun(
    # ... diğer alanlar ...
    raf_kodu = raf_kodu  # Hangi raftan alındığı
))
```

### 3. Frontend Değişiklikleri

#### siparis_detay_partial.html

**Yeni Sütun Eklendi:**

Sipariş detayında ürünlerin hangi raftan alındığı gösterilir:

```html
<th>Raf</th>
...
<td>
  {% if urun.raf_kodu %}
    <span class="badge bg-info">{{ urun.raf_kodu }}</span>
  {% else %}
    <span class="text-muted">-</span>
  {% endif %}
</td>
```

## 🔄 Çalışma Mantığı

### Raf Tahsis Algoritması

1. **Stok Kontrolü**: Barkod için tüm raflarda stok aranır
2. **Sıralama**: Raflar stok miktarına göre çoktan aza sıralanır
3. **Tahsis**: İhtiyaç duyulan miktar raflardan sırayla alınır
4. **Kayıt**: Her ürün için hangi raftan kaç adet alındığı kaydedilir

**Örnek:**
```
Sipariş: 5 adet ayakkabı (Barkod: ABC123)

Raflar:
- A-1-1: 3 adet
- B-2-3: 4 adet
- C-1-2: 1 adet

Tahsis:
1. B-2-3'ten 4 adet alınır (kalan: 0)
2. A-1-1'den 1 adet alınır (kalan: 2)

Sonuç:
- raf_kodu: "B-2-3, B-2-3, B-2-3, B-2-3, A-1-1"
  (Görünüm için: "B-2-3, A-1-1")
```

### Stok Düşürme

**Otomatik olarak:**
1. **RafUrun**: Her raftan alınan miktar düşülür
2. **CentralStock**: Toplam tahsis edilen miktar düşülür

## 📊 Veri Akışı

```
Yeni Sipariş Oluştur
    ↓
Her Ürün İçin:
    ↓
allocate_from_shelf_and_decrement()
    ↓
    ├─→ Rafları Sorgula (adet > 0)
    ├─→ Stok Çoktan Aza Sırala
    ├─→ Gerekli Miktarı Tahsis Et
    ├─→ RafUrun Stoklarını Düş
    ├─→ CentralStock'u Düş
    └─→ Raf Kodlarını Döndür
    ↓
SiparisUrun Kaydı Oluştur
    ├─→ Ürün Bilgileri
    ├─→ raf_kodu (virgülle ayrılmış)
    └─→ Kaydet
    ↓
Sipariş Tamamlandı
```

## 🎨 Görünüm

### Sipariş Detayında

| # | Görsel | Barkod | Model Kod | Renk/Beden | **Raf** | Adet | Birim | Toplam |
|---|--------|--------|-----------|------------|---------|------|-------|--------|
| 1 | 🖼️ | ABC123 | MOD001 | Siyah/42 | `B-2-3, A-1-1` | 5 | 100₺ | 500₺ |
| 2 | 🖼️ | DEF456 | MOD002 | Mavi/40 | `C-1-2` | 2 | 150₺ | 300₺ |

Raf sütunu **mavi badge** olarak gösterilir.

## ⚠️ Önemli Notlar

### Stok Yetersizliği

- Eğer raflarda yeterli stok yoksa, mevcut olan kadar tahsis edilir
- Eksik kalan miktar için sipariş yine de oluşturulur
- `allocate_from_shelf_and_decrement()` her zaman tahsis edilen gerçek miktarı döner

### Birden Fazla Raftan Tahsis

- Bir ürün birden fazla raftan toplanabilir
- Her raf kodu virgülle ayrılarak kaydedilir
- Örnek: `"A-1-1, B-2-3, C-4-5"`

### Migration Öncesi Mevcut Veriler

- Eski siparişlerin `raf_kodu` alanı `NULL` olacaktır
- Frontend'de `NULL` değer `-` olarak gösterilir

## 🔧 Kurulum

### 1. Veritabanı Güncellemesi

```bash
cd /Users/abdurrahmankuli/Documents/Webs/yeni

# Flask-Migrate kullanıyorsanız:
flask db migrate -m "SiparisUrun tablosuna raf_kodu eklendi"
flask db upgrade

# veya doğrudan SQL:
# psql veya mysql client ile bağlanıp:
ALTER TABLE siparis_urunler ADD COLUMN raf_kodu VARCHAR;
```

### 2. Kod Güncellemeleri

Dosyalar zaten güncellendi:
- ✅ `models.py` - `SiparisUrun.raf_kodu` eklendi
- ✅ `siparisler.py` - Raf tahsis fonksiyonu ve sipariş kaydetme güncellendi
- ✅ `templates/siparis_detay_partial.html` - Raf sütunu eklendi

### 3. Test

1. Yeni bir sipariş oluşturun
2. Sipariş detayına bakın
3. Raf sütununda raf kodlarını görmelisiniz
4. Raf stoklarını kontrol edin (düşmüş olmalı)
5. CentralStock'u kontrol edin (düşmüş olmalı)

## 🐛 Sorun Giderme

### "RafUrun bulunamadı" Hatası

**Neden:** Import eksik
**Çözüm:** `siparisler.py` başındaki import'ları kontrol edin:
```python
from models import db, Product, YeniSiparis, SiparisUrun, RafUrun, CentralStock
```

### Raf Kodu Gösterilmiyor

**Neden:** Migration yapılmamış olabilir
**Çözüm:** 
```bash
flask db upgrade
# veya manuel SQL çalıştırın
```

### Stok Düşmüyor

**Neden:** `db.session.flush()` veya `db.session.commit()` çağrılmıyor olabilir
**Çözüm:** `allocate_from_shelf_and_decrement()` fonksiyonunda flush çağrılarını kontrol edin

## 📈 Gelecek İyileştirmeler

- [ ] Stok yetersizliği uyarısı (sipariş oluşturulmadan önce)
- [ ] Raf öncelik sistemi (bazı rafların önce boşaltılması)
- [ ] Sipariş iptalinde raf stoklarını geri ekleme
- [ ] Raf bazlı sipariş raporları
- [ ] Toplu sipariş için raf optimizasyonu
- [ ] Raf değiştirme/transfer fonksiyonu

---

Tarih: 17 Kasım 2025
Geliştirme: Raf Entegrasyonu v1.0
