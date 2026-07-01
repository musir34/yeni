# Veritabanı Tabloları (gerçek şema)

## ⭐ SİPARİŞLER İÇİN TEK KAYNAK: `ai_orders_all` VIEW'İ
Siparişlerle ilgili HER soruda (sayım, dağılım, ciro, saat, pazaryeri...) **yalnızca
`ai_orders_all` view'ini kullan.** Bu view 8 statü tablosunu (yeni→arşiv) birleştirir ve
tarihleri **Türkiye saatine (Europe/Istanbul) çevrilmiş hazır kolonlarla** verir.

🚫 Tek tek statü tablolarına (orders_created, orders_shipped...) ELLE bakma, UNION yazma,
ham `created_at`/`order_date` ile TR dönüşümü yapma — hepsi bu view'de HAZIR.

### View'in hazır kolonları
- `statu` — sipariş durumu (Yeni / Hazırlanıyor / Toplanıyor / Kargoya Hazır / Kargolandı /
  Teslim Edildi / İptal / Arşiv)
- `siparis_tarihi_tr` (date) — **müşterinin sipariş verdiği tarih (TR)**. "Bugün gelen sipariş"
  bu demektir. → **VARSAYILAN "bugün" kolonu budur.**
- `siparis_tr` (timestamp) — müşteri sipariş anı, TR saati (saat gösterimi için).
- `giris_tarihi_tr` (date) — siparişin bizim sisteme senkron olduğu tarih (TR). Sadece kullanıcı
  "sisteme ne zaman düştü / ne zaman senkron oldu" derse kullan.
- `giris_tr` (timestamp) — sisteme giriş anı, TR saati.
- `source` — pazaryeri (TRENDYOL, SHOPIFY_SYNC... NULL olabilir). Shopify: `source ILIKE '%SHOPIFY%'`.
- Ayrıca: `order_number, status, amount, quantity, discount, commission, customer_name,
  customer_surname, product_name, product_barcode, product_code, product_size,
  cargo_tracking_number, estimated_delivery_end, created_at, order_date`.
- Her satır bir sipariştir (order_number benzersiz).

### Hazır sorgular (kopyala-kullan)
- **"Bugün kaç sipariş geldi?"** (varsayılan = müşteri sipariş tarihi):
  ```sql
  SELECT count(*) FROM ai_orders_all
  WHERE siparis_tarihi_tr = (now() AT TIME ZONE 'Europe/Istanbul')::date;
  ```
- **"Shopify'dan bugün kaç sipariş?"** → yukarıya `AND source ILIKE '%SHOPIFY%'` ekle.
- **"Pazaryeri dağılımı bugün":**
  ```sql
  SELECT source, count(*) FROM ai_orders_all
  WHERE siparis_tarihi_tr=(now() AT TIME ZONE 'Europe/Istanbul')::date GROUP BY source ORDER BY 2 DESC;
  ```
- **"Saatlik dağılım / saat kaçtan beri":**
  ```sql
  SELECT to_char(siparis_tr,'HH24') AS saat, count(*) FROM ai_orders_all
  WHERE siparis_tarihi_tr=(now() AT TIME ZONE 'Europe/Istanbul')::date GROUP BY 1 ORDER BY 1;
  ```
- **"Bugünkü ciro":** `SELECT sum(amount) FROM ai_orders_all WHERE siparis_tarihi_tr=(now() AT TIME ZONE 'Europe/Istanbul')::date;`
- **"Statü dağılımı":** `SELECT statu, count(*) FROM ai_orders_all WHERE siparis_tarihi_tr=... GROUP BY statu;`
- **"Kaç sipariş gecikti?"** → `estimated_delivery_end < now()` ve statu NOT IN ('Kargolandı','Teslim Edildi','İptal','Arşiv').
- **"Dün / bu ay / son 7 gün"** → `siparis_tarihi_tr` üzerinde tarih aralığı filtrele.

> Saat gösterirken `siparis_tr`/`giris_tr` zaten TR'dir, ekstra çevirme.

## Diğer tablolar (view kapsamı dışı)
- Sipariş ürün kalemleri: `order_items`
- Ürün/model, stok, ledger, kasa/kâr tabloları — şemadan keşfet:
  - Tablolar: `SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1;`
  - Kolonlar: `SELECT column_name, data_type FROM information_schema.columns WHERE table_name='<tablo>';`
