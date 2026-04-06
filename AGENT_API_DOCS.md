# OpenClaw Agent API Dokümantasyonu

**Base URL:** `/agent/api/v1/`
**Kimlik Doğrulama:** Her istekte `X-Agent-Key` header'ı gereklidir.
**Format:** Tüm response'lar JSON formatındadır.

---

## Kimlik Doğrulama (Authentication)

Her istekte aşağıdaki header gönderilmelidir:

```
X-Agent-Key: <AGENT_API_KEY>
```

`AGENT_API_KEY` değeri `.env` dosyasında tanımlıdır. Geçersiz veya eksik key durumunda `401 Unauthorized` döner.

**Örnek:**
```bash
curl -H "X-Agent-Key: gullu-openclaw-agent-2026-secret" \
     https://panel.gullushoes.com/agent/api/v1/dashboard
```

---

## Ortak Response Formatı

```json
{
  "success": true,
  "total": 100,
  "page": 1,
  "per_page": 50,
  "total_pages": 2,
  "data": [...]
}
```

Hata durumunda:
```json
{
  "success": false,
  "error": "Hata açıklaması"
}
```

---

## 1. Dashboard

### `GET /dashboard`
Genel panel özeti — agent'ın hızlıca durum öğrenmesi için.

**Response:**
```json
{
  "success": true,
  "timestamp": "2026-04-04T15:30:00",
  "orders": {
    "Oluşturuldu": 25,
    "Hazırlanıyor": 10,
    "Kargoda": 50,
    "Teslim Edildi": 200,
    "İptal": 5
  },
  "today_new_orders": 12,
  "total_stock": 5420,
  "total_products": 340,
  "active_exchanges": 3,
  "pending_returns": 7,
  "ana_kasa_bakiye": 125000.50
}
```

---

## 2. Global Arama

### `GET /search?q={arama_terimi}`
Tüm sistemde arama yapar (ürün, sipariş, değişim, iade).

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `q` | string | Evet | Arama terimi (min 2 karakter) |
| `limit` | int | Hayır | Her kategori için max sonuç (default: 5, max: 20) |

**Response:**
```json
{
  "success": true,
  "query": "GLL001",
  "total_results": 8,
  "results": {
    "products": [...],
    "orders": [...],
    "exchanges": [...],
    "returns": [...]
  }
}
```

---

## 3. Siparişler (Orders)

### `GET /orders`
Siparişleri listele.

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `status` | string | Hayır | `Oluşturuldu` \| `Hazırlanıyor` \| `Kargoda` \| `Teslim Edildi` \| `İptal` |
| `search` | string | Hayır | Sipariş no, müşteri adı, barkod ile arama |
| `start_date` | string | Hayır | Başlangıç tarihi (YYYY-MM-DD) |
| `end_date` | string | Hayır | Bitiş tarihi (YYYY-MM-DD) |
| `sort` | string | Hayır | `date_asc` \| `date_desc` (default: date_desc) |
| `page` | int | Hayır | Sayfa numarası (default: 1) |
| `per_page` | int | Hayır | Sayfa başına kayıt (default: 50, max: 200) |

**Response:**
```json
{
  "success": true,
  "total": 150,
  "page": 1,
  "per_page": 50,
  "total_pages": 3,
  "orders": [
    {
      "id": 1,
      "order_number": "1234567890",
      "order_date": "2026-04-04T10:00:00",
      "status": "Oluşturuldu",
      "raw_status": "Created",
      "customer_name": "Ali",
      "customer_surname": "Yılmaz",
      "merchant_sku": "0172-38 Siyah",
      "product_barcode": "ABC123",
      "product_name": "Güllü Model 0172",
      "amount": 599.90,
      "commission": 89.99,
      "cargo_tracking_number": "TRK123456",
      "source": "trendyol",
      "details": [...]
    }
  ]
}
```

### `GET /orders/{order_number}`
Tek sipariş detayı (tüm tablolarda arar).

### `GET /orders/stats`
Sipariş istatistikleri — duruma göre sayılar.

**Response:**
```json
{
  "success": true,
  "stats": {
    "Oluşturuldu": 25,
    "Hazırlanıyor": 10,
    "Kargoda": 50,
    "Teslim Edildi": 200,
    "İptal": 5,
    "Toplam": 290
  }
}
```

---

## 4. Ürünler (Products)

### `GET /products`
Ürünleri listele.

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `search` | string | Hayır | Barkod, başlık, model kodu ile arama |
| `model` | string | Hayır | Model kodu (product_main_id) filtresi |
| `color` | string | Hayır | Renk filtresi |
| `size` | string | Hayır | Beden filtresi |
| `brand` | string | Hayır | Marka filtresi |
| `in_stock` | bool | Hayır | `true` = sadece stokta olanlar |
| `archived` | bool | Hayır | `true` = arşivlenmiş ürünler (default: false) |
| `sort` | string | Hayır | `title` \| `price_asc` \| `price_desc` \| `barcode` |
| `page` | int | Hayır | Sayfa numarası (default: 1) |
| `per_page` | int | Hayır | Sayfa başına kayıt (default: 50, max: 200) |

**Response:**
```json
{
  "success": true,
  "total": 340,
  "products": [
    {
      "barcode": "ABC123",
      "title": "Güllü Model 0172 Siyah 38",
      "product_main_id": "0172",
      "size": "38",
      "color": "Siyah",
      "brand": "Güllü Shoes",
      "sale_price": 599.90,
      "list_price": 699.90,
      "cost_usd": 12.50,
      "cost_try": 425.00,
      "quantity": 0,
      "on_sale": true,
      "archived": false
    }
  ]
}
```

### `GET /products/{barcode}`
Tek ürün detayı + stok ve alias bilgisi.

**Response:**
```json
{
  "success": true,
  "product": {
    "barcode": "ABC123",
    "title": "...",
    "stock": {
      "total": 15,
      "shelves": [
        {"raf_kodu": "A-01-3", "adet": 10},
        {"raf_kodu": "B-02-1", "adet": 5}
      ]
    },
    "aliases": ["DEF456", "GHI789"]
  }
}
```

### `GET /products/models`
Benzersiz model kodlarını listele.

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `search` | string | Hayır | Model kodu araması |

**Response:**
```json
{
  "success": true,
  "total": 45,
  "models": [
    {
      "product_main_id": "0172",
      "variant_count": 12,
      "min_price": 499.90,
      "max_price": 699.90
    }
  ]
}
```

---

## 5. Stok (Stock)

### `GET /stock`
Stok listesi.

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `search` | string | Hayır | Barkod ile arama |
| `min_qty` | int | Hayır | Minimum stok miktarı |
| `max_qty` | int | Hayır | Maximum stok miktarı |
| `zero_stock` | bool | Hayır | `true` = sadece sıfır stoklular |
| `page` | int | Hayır | Sayfa (default: 1) |
| `per_page` | int | Hayır | Sayfa başına (default: 100, max: 500) |

**Response:**
```json
{
  "success": true,
  "total": 340,
  "items": [
    {
      "barcode": "ABC123",
      "qty": 15,
      "updated_at": "2026-04-04T10:00:00",
      "product_title": "Güllü Model 0172 Siyah 38",
      "product_main_id": "0172",
      "color": "Siyah",
      "size": "38"
    }
  ]
}
```

### `GET /stock/{barcode}`
Tek barkod stok detayı (merkez + raf bazlı dağılım).

**Response:**
```json
{
  "success": true,
  "barcode": "ABC123",
  "total_qty": 15,
  "shelves": [
    {"raf_kodu": "A-01-3", "adet": 10},
    {"raf_kodu": "B-02-1", "adet": 5}
  ],
  "product_title": "...",
  "product_main_id": "0172"
}
```

### `GET /stock/summary`
Genel stok özeti.

**Response:**
```json
{
  "success": true,
  "total_products": 340,
  "total_stock": 5420,
  "in_stock_count": 280,
  "zero_stock_count": 60,
  "top_models": [
    {"model": "0172", "total_stock": 250},
    {"model": "0088", "total_stock": 180}
  ]
}
```

### `POST /stock/sync/{barcode}`
Tek barkod için CentralStock'u raflarla senkronize et.

**Response:**
```json
{
  "success": true,
  "barcode": "ABC123",
  "new_qty": 15
}
```

---

## 6. Değişim (Exchanges)

### `GET /exchanges`
Değişim taleplerini listele.

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `status` | string | Hayır | Durum filtresi (Oluşturuldu, Kargoda, Tamamlandı, İptal) |
| `search` | string | Hayır | Sipariş no, ad/soyad, değişim no ile arama |
| `start_date` | string | Hayır | Başlangıç (YYYY-MM-DD) |
| `end_date` | string | Hayır | Bitiş (YYYY-MM-DD) |
| `page` | int | Hayır | Sayfa (default: 1) |
| `per_page` | int | Hayır | Sayfa başına (default: 50) |

**Response:**
```json
{
  "success": true,
  "total": 25,
  "exchanges": [
    {
      "id": 1,
      "degisim_no": "uuid-here",
      "siparis_no": "1234567890",
      "ad": "Ali",
      "soyad": "Yılmaz",
      "adres": "...",
      "telefon_no": "05xx...",
      "degisim_tarihi": "2026-04-04T10:00:00",
      "degisim_durumu": "Oluşturuldu",
      "kargo_kodu": "5551234567",
      "degisim_nedeni": "Beden uymuyor",
      "musteri_kargo_takip": null,
      "urunler": [
        {
          "barkod": "ABC123",
          "model_kodu": "0172",
          "renk": "Siyah",
          "beden": "38",
          "adet": 1,
          "raf_kodu": "A-01-3",
          "tahsis_edilen": 1
        }
      ]
    }
  ]
}
```

### `GET /exchanges/{degisim_no}`
Tek değişim detayı.

### `POST /exchanges`
Yeni değişim talebi oluştur. Stok otomatik olarak raflardan tahsis edilir.

**Request Body:**
```json
{
  "siparis_no": "1234567890",
  "ad": "Ali",
  "soyad": "Yılmaz",
  "adres": "Ankara, Çankaya ...",
  "telefon_no": "05551234567",
  "degisim_nedeni": "Beden uymuyor",
  "urunler": [
    {
      "barkod": "ABC123",
      "model_kodu": "0172",
      "renk": "Siyah",
      "beden": "38",
      "adet": 1
    }
  ]
}
```

**Zorunlu Alanlar:** `siparis_no`, `ad`, `soyad`, `adres`, `urunler`

**Response (201):**
```json
{
  "success": true,
  "message": "Değişim talebi oluşturuldu.",
  "degisim_no": "generated-uuid",
  "kargo_kodu": "5551234567",
  "toplam_tahsis": 1,
  "exchange": {...}
}
```

### `PUT /exchanges/{degisim_no}/status`
Değişim durumunu güncelle.

**Request Body:**
```json
{
  "status": "Kargoda",
  "musteri_kargo_takip": "TRACK123456"
}
```

> Not: Kargo takip numarası olmadan durum güncellenemez.

### `DELETE /exchanges/{degisim_no}`
Değişim kaydını sil.

### `GET /exchanges/stats`
Değişim istatistikleri — duruma göre sayılar.

---

## 7. İadeler (Returns)

### `GET /returns`
İade taleplerini listele.

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `status` | string | Hayır | İade durumu filtresi |
| `search` | string | Hayır | Sipariş no, müşteri adı ile arama |
| `page` | int | Hayır | Sayfa (default: 1) |
| `per_page` | int | Hayır | Sayfa başına (default: 50) |

**Response:**
```json
{
  "success": true,
  "total": 15,
  "returns": [
    {
      "id": "uuid",
      "order_number": "1234567890",
      "return_request_number": "RN123",
      "status": "Created",
      "return_date": "2026-04-04T10:00:00",
      "customer_first_name": "Ali",
      "customer_last_name": "Yılmaz",
      "cargo_tracking_number": "TRK123",
      "return_reason": "Beden uymuyor",
      "refund_amount": 599.90,
      "products": [
        {
          "barcode": "ABC123",
          "product_name": "Güllü 0172 Siyah 38",
          "size": "38",
          "color": "Siyah",
          "quantity": 1,
          "reason": "Beden küçük",
          "return_to_stock": false
        }
      ]
    }
  ]
}
```

### `GET /returns/{return_id}`
Tek iade detayı (ürünleriyle birlikte).

---

## 8. Manuel Siparişler

### `GET /manual-orders`
Manuel oluşturulan siparişleri listele.

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `search` | string | Hayır | Sipariş no, müşteri adı |
| `status` | string | Hayır | Durum filtresi |
| `page` | int | Hayır | Sayfa (default: 1) |
| `per_page` | int | Hayır | Sayfa başına (default: 50) |

### `POST /manual-orders`
Manuel sipariş oluştur. Stok otomatik olarak raflardan tahsis edilir.

**Request Body:**
```json
{
  "musteri_adi": "Ali",
  "musteri_soyadi": "Yılmaz",
  "musteri_adres": "Ankara, Çankaya ...",
  "musteri_telefon": "05551234567",
  "notlar": "Hızlı kargo",
  "kapida_odeme": true,
  "kapida_odeme_tutari": 599.90,
  "urunler": [
    {
      "barkod": "ABC123",
      "adet": 1,
      "birim_fiyat": 599.90
    }
  ]
}
```

**Zorunlu Alanlar:** `musteri_adi`, `musteri_soyadi`, `musteri_adres`, `urunler`

> `birim_fiyat` 0 veya belirtilmezse ürünün `sale_price` değeri kullanılır.

**Response (201):**
```json
{
  "success": true,
  "message": "Sipariş oluşturuldu.",
  "siparis_no": "MAN-20260404153000-A1B2C3",
  "toplam_tutar": 599.90
}
```

---

## 9. Finans (Kasa)

### `GET /finance/summary`
Finansal özet.

**Response:**
```json
{
  "success": true,
  "ana_kasa_bakiye": 125000.50,
  "toplam_gelir": 500000.00,
  "toplam_gider": 375000.00,
  "odenmemis_kayit": 5,
  "kismi_odenmis_kayit": 2,
  "tamamlanmis_kayit": 150
}
```

### `GET /finance/transactions`
Kasa kayıtlarını listele.

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `tip` | string | Hayır | `gelir` \| `gider` |
| `kategori` | string | Hayır | Kategori filtresi |
| `durum` | string | Hayır | `odenmedi` \| `kismi_odendi` \| `tamamlandi` |
| `start_date` | string | Hayır | Başlangıç (YYYY-MM-DD) |
| `end_date` | string | Hayır | Bitiş (YYYY-MM-DD) |
| `page` | int | Hayır | Sayfa (default: 1) |
| `per_page` | int | Hayır | Sayfa başına (default: 50) |

**Response:**
```json
{
  "success": true,
  "transactions": [
    {
      "id": 1,
      "tip": "gelir",
      "aciklama": "Trendyol sipariş geliri",
      "tutar": 5000.00,
      "kategori": "Satış",
      "tarih": "2026-04-04T10:00:00",
      "durum": "tamamlandı",
      "odenen_tutar": 5000.00,
      "kalan_tutar": 0.00,
      "ana_kasadan": false
    }
  ]
}
```

### `GET /finance/categories`
Kasada kullanılabilecek kategori listesini döner. Gelir/gider eklerken `kategori` alanına bu listeden bir değer gönder.

**Response:**
```json
{
  "success": true,
  "categories": [
    { "id": 1, "kategori_adi": "Kargo", "renk": "#007bff" },
    { "id": 2, "kategori_adi": "Kira", "renk": "#dc3545" },
    { "id": 3, "kategori_adi": "Satış", "renk": "#28a745" }
  ]
}
```

### `POST /finance/transactions`
Normal kasaya gelir veya gider kaydı ekle (ana kasa etkilenmez).

> **Agent için önemli notlar:**
> - Kullanıcı "şuna 500 lira gider ekle" derse → `tip: "gider"` kullan.
> - Kullanıcı "gelir yaz" derse → `tip: "gelir"` kullan.
> - `aciklama` alanına kullanıcının verdiği açıklamayı yaz. Kullanıcı açıklama vermediyse kısa ve anlaşılır bir açıklama üret (örn: "Kargo gideri", "Ürün satış geliri").
> - `tarih` verilmezse bugünün tarihi kullanılır. Kullanıcı "dünkü" derse dünün tarihini hesapla ve YYYY-MM-DD formatında gönder.
> - `kategori` için önce `GET /finance/categories` ile mevcut kategorileri çek, kullanıcının söylediğiyle en yakın eşleşeni kullan. Eşleşen yoksa boş bırak.
> - `durum`: Kullanıcı "ödendi" / "ödedim" derse → `tamamlandi`. "Henüz ödenmedi" / "borç" derse → `odenmedi`. Default: `odenmedi`.

**Body (JSON):**

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `tip` | string | Evet | `gelir` \| `gider` |
| `aciklama` | string | Evet | Ne için olduğunu açıkla |
| `tutar` | number | Evet | TL cinsinden tutar (0'dan büyük, kuruş için ondalık kullan: `1500.50`) |
| `kategori` | string | Hayır | Kategori adı (`GET /finance/categories`'den al) |
| `durum` | string | Hayır | `odenmedi` \| `kismi_odendi` \| `tamamlandi` (default: `odenmedi`) |
| `tarih` | string | Hayır | `YYYY-MM-DD` formatında (default: bugün) |
| `kullanici_id` | int | Hayır | Kullanıcı ID (default: 1) |

**Örnek — Gider ekleme:**
```json
{
  "tip": "gider",
  "aciklama": "Nisan ayı kargo ödemesi - Yurtiçi Kargo",
  "tutar": 1500.00,
  "kategori": "Kargo",
  "durum": "tamamlandi",
  "tarih": "2026-04-06"
}
```

**Örnek — Gelir ekleme:**
```json
{
  "tip": "gelir",
  "aciklama": "Mağaza içi nakit satış",
  "tutar": 3200.00,
  "kategori": "Satış",
  "durum": "tamamlandi"
}
```

**Response (201):**
```json
{
  "success": true,
  "message": "Gider kaydı eklendi",
  "transaction": {
    "id": 42,
    "tip": "gider",
    "aciklama": "Nisan ayı kargo ödemesi - Yurtiçi Kargo",
    "tutar": 1500.00,
    "kategori": "Kargo",
    "tarih": "2026-04-06T00:00:00",
    "durum": "tamamlandı"
  }
}
```

---

## 10. Raflar (Shelves / Depo)

### `GET /shelves`
Rafları listele.

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `search` | string | Hayır | Raf kodu ile arama |
| `page` | int | Hayır | Sayfa (default: 1) |
| `per_page` | int | Hayır | Sayfa başına (default: 100) |

**Response:**
```json
{
  "success": true,
  "shelves": [
    {
      "kod": "A-01-3",
      "ana": "A",
      "ikincil": "01",
      "kat": "3",
      "urun_cesidi": 5,
      "toplam_adet": 45
    }
  ]
}
```

### `GET /shelves/{shelf_code}/products`
Belirli raftaki ürünleri listele.

**Response:**
```json
{
  "success": true,
  "shelf": {
    "kod": "A-01-3",
    "ana": "A",
    "ikincil": "01",
    "kat": "3"
  },
  "products": [
    {
      "barcode": "ABC123",
      "adet": 10,
      "product_title": "Güllü 0172 Siyah 38",
      "product_main_id": "0172",
      "color": "Siyah",
      "size": "38"
    }
  ],
  "total_products": 5
}
```

---

## 11. Barkod Alias

### `GET /barcode-alias/check/{barcode}`
Barkodun alias olup olmadığını kontrol et.

**Alias ise Response:**
```json
{
  "success": true,
  "is_alias": true,
  "alias_barcode": "DEF456",
  "main_barcode": "ABC123"
}
```

**Ana barkod ise Response:**
```json
{
  "success": true,
  "is_alias": false,
  "main_barcode": "ABC123",
  "aliases": ["DEF456", "GHI789"]
}
```

---

## HTTP Durum Kodları

| Kod | Açıklama |
|-----|----------|
| `200` | Başarılı |
| `201` | Kayıt oluşturuldu |
| `400` | Hatalı istek (eksik parametre vb.) |
| `401` | Yetkisiz (geçersiz API key) |
| `404` | Kayıt bulunamadı |
| `500` | Sunucu hatası |

---

## Rate Limiting

Şu anda rate limiting uygulanmamaktadır. Gelecekte eklenebilir.

---

## Agent İçin Önerilen Akış

1. **Başlangıç:** `GET /dashboard` ile genel durumu öğren
2. **Arama:** `GET /search?q=...` ile global arama yap
3. **Detay:** İlgili endpoint'ten detay çek (`/orders/{no}`, `/products/{barcode}`, vs.)
4. **İşlem:** Gerekirse değişim oluştur (`POST /exchanges`), sipariş oluştur (`POST /manual-orders`)
5. **Güncelleme:** Durum güncelle (`PUT /exchanges/{no}/status`)

---

## Endpoint Özet Tablosu

| # | Method | Endpoint | Açıklama |
|---|--------|----------|----------|
| 1 | GET | `/dashboard` | Genel panel özeti |
| 2 | GET | `/search` | Global arama |
| 3 | GET | `/orders` | Sipariş listesi |
| 4 | GET | `/orders/{order_number}` | Sipariş detayı |
| 5 | GET | `/orders/stats` | Sipariş istatistikleri |
| 6 | GET | `/products` | Ürün listesi |
| 7 | GET | `/products/{barcode}` | Ürün detayı + stok |
| 8 | GET | `/products/models` | Model listesi |
| 9 | GET | `/stock` | Stok listesi |
| 10 | GET | `/stock/{barcode}` | Barkod stok detayı |
| 11 | GET | `/stock/summary` | Stok özeti |
| 12 | POST | `/stock/sync/{barcode}` | Stok senkronizasyonu |
| 13 | GET | `/exchanges` | Değişim listesi |
| 14 | GET | `/exchanges/{degisim_no}` | Değişim detayı |
| 15 | POST | `/exchanges` | Değişim oluştur |
| 16 | PUT | `/exchanges/{degisim_no}/status` | Değişim durumu güncelle |
| 17 | DELETE | `/exchanges/{degisim_no}` | Değişim sil |
| 18 | GET | `/exchanges/stats` | Değişim istatistikleri |
| 19 | GET | `/returns` | İade listesi |
| 20 | GET | `/returns/{return_id}` | İade detayı |
| 21 | GET | `/manual-orders` | Manuel sipariş listesi |
| 22 | POST | `/manual-orders` | Manuel sipariş oluştur |
| 23 | GET | `/finance/summary` | Finansal özet |
| 24 | GET | `/finance/transactions` | Kasa kayıtları |
| 25 | GET | `/finance/categories` | Kasa kategorileri |
| 26 | POST | `/finance/transactions` | Gelir/gider kaydı ekle |
| 27 | GET | `/shelves` | Raf listesi |
| 28 | GET | `/shelves/{code}/products` | Raftaki ürünler |
| 29 | GET | `/barcode-alias/check/{barcode}` | Barkod alias kontrolü |
