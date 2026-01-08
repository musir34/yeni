# WooCommerce Sipariş Yönetim Sistemi

WooCommerce sitenizdeki siparişleri Flask uygulamanızdan görüntülemek ve yönetmek için geliştirilmiş modül.

## ✨ Yeni Özellikler

- ✅ **Otomatik Veritabanı Kaydı:** Siparişler otomatik olarak yerel veritabanına kaydedilir
- ✅ **Ödeme Yöntemi Gösterimi:** Her siparişin ödeme yöntemi görüntülenir
- ✅ **WooCommerce Orijinal Statüler:** Statü isimleri WooCommerce'deki orijinal halleriyle eşleştirildi
- ✅ **"Kargoya Verildi" Statüsü:** "shipped" durumu "Kargoya Verildi" olarak gösterilir
- ✅ **Hızlı Sipariş Bilgi Girişi:** Bilgisi eksik siparişler için "Bilgi Gir" butonu
- ✅ **Teslimat Etiketi Yazdırma:** 100x100mm profesyonel teslimat etiketi
- ✅ **Kapıda Ödeme Vurgusu:** KOD siparişleri için özel kırmızı vurgulu etiket
- ✅ **Senkronizasyon:** Toplu sipariş senkronizasyonu ile geçmiş siparişleri çekme

## 📁 Dosya Yapısı

```
woocommerce_site/
├── __init__.py          # Modül başlatıcı
├── models.py            # WooOrder veritabanı modeli
├── woo_config.py        # WooCommerce API yapılandırması
├── woo_service.py       # Sipariş işlemleri servisi
└── woo_routes.py        # Flask route'ları

templates/woocommerce_site/
├── orders.html          # Sipariş listesi sayfası
├── order_detail.html    # Sipariş detay sayfası
└── config_error.html    # Yapılandırma hatası sayfası
```

## 🚀 Kurulum

### 1. Gerekli Paketleri Yükleyin

```bash
pip install requests python-dotenv
```

### 2. WooCommerce API Ayarlarını Yapın

`.env` dosyanıza aşağıdaki değişkenleri ekleyin:

```env
WOO_STORE_URL=https://siteniz.com
WOO_CONSUMER_KEY=ck_xxxxxxxxxxxxxxxxxxxxx
WOO_CONSUMER_SECRET=cs_xxxxxxxxxxxxxxxxxxxxx
```

### 3. WooCommerce'den API Anahtarları Alın

1. WooCommerce yönetim panelinize giriş yapın
2. **WooCommerce → Ayarlar → Gelişmiş → REST API** bölümüne gidin
3. **"Anahtar Ekle"** butonuna tıklayın
4. Açıklama girin (örn: "Flask Uygulama")
5. Kullanıcı seçin ve **"Okuma/Yazma"** yetkisi verin
6. **Consumer Key** ve **Consumer Secret** değerlerini kopyalayın
7. Bu değerleri `.env` dosyanıza ekleyin

### 4. Blueprint'i Ana Uygulamaya Ekleyin

`app.py` dosyanıza şunu ekleyin:

```python
from site import woo_bp

# Blueprint'i kaydet
app.register_blueprint(woo_bp)
```

## 📖 Kullanım

### Sayfalar

#### Sipariş Listesi
- **URL:** `/site/orders`
- **Özellikler:**
  - Tüm siparişleri listeler
  - Duruma göre filtreleme
  - Sipariş numarası, müşteri adı veya email ile arama
  - Sayfalama desteği
  - Otomatik veritabanına kayıt
  - Ödeme yöntemi gösterimi
  - Senkronizasyon butonu (son 30 günü çeker)

#### Sipariş Detayı
- **URL:** `/site/orders/<order_id>`
- **Özellikler:**
  - Sipariş detaylarını görüntüleme
  - Ürün listesi ve fiyat özeti
  - Müşteri ve adres bilgileri
  - Ödeme yöntemi bilgisi
  - Sipariş durumu güncelleme
  - Not ekleme ve görüntüleme
  - Otomatik veritabanına kayıt

#### Senkronizasyon
- **URL:** `/site/sync-orders?days=30`
- **Özellikler:**
  - Son X günün siparişlerini toplu çeker
  - Veritabanına kaydeder
  - İstatistik gösterir

#### Teslimat Etiketi
- **URL:** `/site/orders/<order_id>/shipping-label`
- **Özellikler:**
  - 100x100mm profesyonel etiket tasarımı
  - Kapıda ödeme siparişleri için kırmızı vurgulu özel tasarım
  - Tutar bilgisi bariz şekilde gösterilir (KOD için)
  - Müşteri adı, telefon, adres bilgileri
  - Yazdırma butonu (Ctrl+P)
  - Otomatik sayfa boyutu ayarı

### API Endpoint'leri

#### Siparişleri JSON Olarak Al
```
GET /site/api/orders?status=processing&page=1
```

**Yanıt:**
```json
{
  "success": true,
  "orders": [...],
  "page": 1
}
```

#### Tek Sipariş Detayı (JSON)
```
GET /site/api/orders/<order_id>
```

#### Sipariş Durumu Güncelle
```
POST /site/orders/<order_id>/update-status
Content-Type: application/json

{
  "status": "completed"
}
```

#### Sipariş Notu Ekle
```
POST /site/orders/<order_id>/add-note
Content-Type: application/json

{
  "note": "Sipariş kargoya verildi",
  "customer_note": false
}
```

## 🎯 Özellikler

### Sipariş Yönetimi
- ✅ Tüm siparişleri listeleme
- ✅ Duruma göre filtreleme (bekliyor, işleniyor, tamamlandı, vb.)
- ✅ Sipariş arama
- ✅ Tarih aralığına göre filtreleme
- ✅ Sipariş detaylarını görüntüleme

### Sipariş İşlemleri
- ✅ Sipariş durumu güncelleme
- ✅ Sipariş notları ekleme
- ✅ Sipariş notlarını görüntüleme
- ✅ Müşteri bilgilerini görüntüleme
- ✅ Fatura ve teslimat adresi

### Sipariş Durumları
- `pending` - Ödeme Bekliyor
- `processing` - İşleme Alındı
- `on-hold` - Beklemede
- `completed` - Tamamlandı
- `cancelled` - İptal Edildi
- `refunded` - İade Edildi
- `failed` - Başarısız
- `shipped` - Kargoya Verildi ⭐
- `trash` - Çöp Kutusu

## 🛠️ Servis Fonksiyonları

### WooCommerceService Sınıfı

```python
from site.woo_service import WooCommerceService

service = WooCommerceService()

# Siparişleri getir
orders = service.get_orders(status='processing', page=1)

# Tek sipariş getir
order = service.get_order(order_id=123)

# Durum güncelle
service.update_order_status(order_id=123, status='completed')

# Not ekle
service.add_order_note(order_id=123, note='Kargoya verildi', customer_note=True)

# Arama yap
results = service.search_orders('john@example.com')

# Tarih aralığı
orders = service.get_orders_by_date_range('2024-01-01', '2024-01-31')
```

## 🎨 Arayüz

- Modern ve responsive tasarım (Bootstrap 5)
- Koyu/açık renk şeması
- Sipariş kartları ile görsel liste
- Detaylı sipariş görünümü
- AJAX ile anlık güncellemeler

## 🔒 Güvenlik

- API anahtarları `.env` dosyasında saklanır
- Yapılandırma kontrolü middleware ile yapılır
- HTTPS kullanımı önerilir
- API istekleri timeout ile sınırlandırılmıştır

## 📝 Notlar

- WooCommerce REST API v3 kullanılmaktadır
- Varsayılan sayfa başına 50 sipariş gösterilir
- API timeout süresi 30 saniyedir
- Tüm tarihler ISO 8601 formatındadır

## 🐛 Sorun Giderme

### API Bağlantı Hatası
- WooCommerce site URL'inin doğru olduğundan emin olun
- API anahtarlarının geçerli olduğunu kontrol edin
- SSL sertifikasının geçerli olduğunu doğrulayın

### Sipariş Görünmüyor
- WooCommerce REST API'nin aktif olduğunu kontrol edin
- Kullanıcının yeterli yetkilere sahip olduğunu doğrulayın
- Filtrelerinizi kontrol edin

### Durum Güncellenmiyor
- API anahtarının "Okuma/Yazma" yetkisine sahip olduğunu kontrol edin
- Sipariş ID'sinin doğru olduğunu doğrulayın

## 📞 Destek

Sorun yaşarsanız:
1. `.env` dosyasındaki ayarları kontrol edin
2. WooCommerce API ayarlarını doğrulayın
3. Tarayıcı konsolunda hata mesajlarını kontrol edin
4. Flask log dosyalarını inceleyin

## 🔄 Güncellemeler

Modülü güncellemek için:
1. Yeni kod dosyalarını indirin
2. Mevcut ayarlarınızı koruyun
3. Yeni özellikleri test edin

---

**Not:** Bu modül bağımsız çalışır ve mevcut uygulamanızı etkilemez. İstediğiniz zaman aktif veya pasif hale getirebilirsiniz.
