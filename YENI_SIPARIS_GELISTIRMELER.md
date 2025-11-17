# Yeni Sipariş Sayfası Geliştirmeleri

## 📋 Yapılan Geliştirmeler

### 1. ✅ Durum Güncelleme (Direkt Listeden)
- Her sipariş satırında durum dropdown'u eklendi
- Dropdown'dan seçim yapıldığında otomatik olarak sipariş durumu güncellenir
- Durum seçenekleri:
  - Yeni Sipariş
  - Hazırlanıyor
  - Kargoya Hazır
  - Kargoda
  - Teslim Edildi
  - İptal Edildi
- Başarılı güncelleme sonrası toast bildirim gösterilir

**Endpoint:** `POST /siparis-durum-guncelle/<siparis_no>`
```json
{
  "durum": "Kargoda"
}
```

---

### 2. 🚚 Kargo Etiketi Yazdırma (Direkt Listeden)
- Her sipariş satırında kargo etiketi butonu eklendi
- Butona tıklandığında yeni pencerede yazdırılabilir kargo etiketi açılır
- Kargo etiketinde şunlar bulunur:
  - Sipariş No (büyük font, barkod stili)
  - Sipariş tarihi ve durumu
  - Alıcı bilgileri (Ad, Soyad, Telefon, Adres)
  - Ürün listesi (Model, Ürün Adı, Renk/Beden, Adet)
  - Toplam tutar
  - Sipariş notları (varsa)
  - Yazdırma tarihi

**Endpoint:** `GET /siparis-kargo-etiketi/<siparis_no>`

**Template:** `templates/kargo_etiketi.html`
- Yazdırma dostu tasarım (100mm x 150mm)
- Otomatik yazdırma özelliği (opsiyonel)

---

### 3. 🗑️ Toplu/Tekli Sipariş Silme

#### Tekli Silme
- Her sipariş satırında silme butonu
- Tıklandığında onay penceresi
- Silinen sipariş satırı anında tablodan kaldırılır (sayfa yenilenmez)

**Endpoint:** `DELETE /siparis-sil/<siparis_no>`

#### Toplu Silme
- Sipariş listesi başında toplu işlem araçları eklendi
- Her sipariş satırında checkbox
- "Tümünü Seç" butonu
- "Seçimi Kaldır" butonu
- "Seçili Siparişleri Sil" butonu (seçili sayı gösterir)
- Siparişler seçildiğinde butonlar otomatik görünür/gizlenir

**Endpoint:** `POST /siparis-toplu-sil`
```json
{
  "siparis_nolar": ["SP20251117...", "SP20251117..."]
}
```

---

## 🎨 Kullanıcı Arayüzü İyileştirmeleri

### Tablo Güncellemeleri
- Checkbox sütunu eklendi
- Durum badge'i yerine dropdown select eklendi
- İşlemler sütunu buton grubu olarak düzenlendi
- Her satıra `data-siparis-no` özniteliği eklendi (kolay erişim için)

### Butonlar
- **Detay** (Mavi) - Sipariş detaylarını modal'da gösterir
- **Kargo Etiketi** (Mor) - Kargo etiketini yeni pencerede açar
- **Müşteri Bilgileri** (Yeşil) - Müşteri bilgilerini yazdırır
- **Sil** (Kırmızı) - Siparişi siler

### Toast Bildirimleri
- Durum güncellemeleri için başarılı/hata bildirimleri
- Otomatik 3 saniye sonra kapanır
- Sağ üst köşede gösterilir

---

## 🔧 Teknik Detaylar

### Backend (siparisler.py)
Yeni route'lar eklendi:
1. `/siparis-durum-guncelle/<siparis_no>` - POST
2. `/siparis-kargo-etiketi/<siparis_no>` - GET
3. `/siparis-toplu-sil` - POST

### Frontend (yeni_siparis.html)
Yeni JavaScript fonksiyonları:
1. `updateOrderStatus(siparisNo, yeniDurum)` - Durum güncelle
2. `printShippingLabel(siparisNo)` - Kargo etiketi yazdır
3. `deleteSingleOrder(siparisNo)` - Tekli silme
4. `deleteSelectedOrders()` - Toplu silme
5. `toggleSelectAll()` - Tümünü seç/kaldır
6. `updateSelectedCount()` - Seçili sipariş sayısını güncelle
7. `showToast(message, type)` - Toast bildirimi göster

### Yeni Template
- `templates/kargo_etiketi.html` - Yazdırılabilir kargo etiketi

---

## 📝 Kullanım Örnekleri

### Durum Güncelleme
1. Sipariş listesinde ilgili siparişi bulun
2. "Durum" sütunundaki dropdown'dan yeni durumu seçin
3. Otomatik olarak kaydedilir ve toast bildirim gösterilir

### Kargo Etiketi Yazdırma
1. İşlemler sütununda kamyon ikonu olan butona tıklayın
2. Yeni pencerede kargo etiketi açılır
3. "Yazdır" butonuna tıklayın veya Ctrl+P ile yazdırın

### Toplu Sipariş Silme
1. Silmek istediğiniz siparişlerin checkbox'larını işaretleyin
2. "Seçili Siparişleri Sil" butonuna tıklayın
3. Onay penceresinde "Tamam"a tıklayın
4. Siparişler silinir ve sayfa yenilenir

### Tekli Sipariş Silme
1. İşlemler sütununda çöp kutusu ikonuna tıklayın
2. Onay penceresinde "Tamam"a tıklayın
3. Sipariş anında tablodan kaldırılır

---

## ⚠️ Önemli Notlar

1. **Silme İşlemleri Geri Alınamaz:** Hem tekli hem toplu silme işlemleri kalıcıdır
2. **Durum Güncellemeleri:** Dropdown'dan seçim yapılır yapılmaz kaydedilir
3. **Kargo Etiketi:** A4 kağıda veya termal yazıcıya uygun tasarlanmıştır
4. **Toast Bildirimleri:** Bootstrap alert componentini kullanır
5. **Checkbox Seçimi:** Sayfa yenilendiğinde sıfırlanır

---

## 🔄 Gelecek Geliştirme Önerileri

- [ ] Toplu durum güncelleme (seçili siparişlerin durumunu tek seferde değiştirme)
- [ ] Kargo etiketlerini PDF olarak indirme
- [ ] Sipariş filtreleme/arama geliştirmesi
- [ ] Durum değişikliği geçmişi
- [ ] Kargo takip numarası ekleme
- [ ] Toplu kargo etiketi yazdırma (seçili siparişler için)
- [ ] Excel/CSV export özelliği
- [ ] Sipariş notlarını hızlı düzenleme

---

## 📚 İlgili Dosyalar

### Backend
- `siparisler.py` - Ana sipariş route'ları

### Frontend
- `templates/yeni_siparis.html` - Sipariş listesi ve form
- `templates/kargo_etiketi.html` - Kargo etiketi şablonu
- `templates/siparis_detay_partial.html` - Sipariş detay modal'ı (mevcut)

### Veritabanı
- `models.py` -> `YeniSiparis` modeli
- `models.py` -> `SiparisUrun` modeli

---

Tarih: 17 Kasım 2025
Geliştirici: AI Assistant
