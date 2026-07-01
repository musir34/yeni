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
- **`tarih_tr` (date) — sipariş tarihi, TR. TÜM "bugün/dün/tarih" filtreleri İÇİN TEK VE
  ZORUNLU KOLON BUDUR.** Başka tarih kolonu (created_at, order_date) ile filtre YAPMA.
- `saat_tr` (timestamp) — sipariş anı, TR saati. Saat/saatlik dağılım için bunu kullan.
- `teslim_tarihi_tr` (timestamp) — tahmini teslim tarihi, TR (geciken hesabı için).
- `source` — pazaryeri (TRENDYOL, SHOPIFY_SYNC... NULL olabilir). Shopify: `source ILIKE '%SHOPIFY%'`.
- Ayrıca: `order_number, status, amount, quantity, discount, commission, customer_name,
  customer_surname, product_name, product_barcode, product_code, product_size,
  cargo_tracking_number`. Her satır bir sipariştir (order_number benzersiz).
- NOT: view'de ham UTC tarih kolonu YOKTUR; tüm zaman kolonları zaten TR'dir.

### Hazır sorgular (kopyala-kullan) — tarih filtresi HER ZAMAN `tarih_tr`
Kısaltma: `BUGUN = (now() AT TIME ZONE 'Europe/Istanbul')::date`
- **"Bugün kaç sipariş geldi?"**
  `SELECT count(*) FROM ai_orders_all WHERE tarih_tr = (now() AT TIME ZONE 'Europe/Istanbul')::date;`
- **"Shopify'dan bugün kaç sipariş?"** → yukarıya `AND source ILIKE '%SHOPIFY%'` ekle.
- **"Pazaryeri dağılımı bugün":**
  `SELECT source, count(*) FROM ai_orders_all WHERE tarih_tr=(now() AT TIME ZONE 'Europe/Istanbul')::date GROUP BY source ORDER BY 2 DESC;`
- **"Saatlik dağılım / saat kaçtan beri":**
  `SELECT to_char(saat_tr,'HH24') AS saat, count(*) FROM ai_orders_all WHERE tarih_tr=(now() AT TIME ZONE 'Europe/Istanbul')::date GROUP BY 1 ORDER BY 1;`
- **"Bugünkü ciro":** `SELECT sum(amount) FROM ai_orders_all WHERE tarih_tr=(now() AT TIME ZONE 'Europe/Istanbul')::date;`
- **"Statü dağılımı":** `SELECT statu, count(*) FROM ai_orders_all WHERE tarih_tr=(now() AT TIME ZONE 'Europe/Istanbul')::date GROUP BY statu;`
- **"Kaç sipariş gecikti?"** → `teslim_tarihi_tr < (now() AT TIME ZONE 'Europe/Istanbul')` ve statu NOT IN ('Kargolandı','Teslim Edildi','İptal','Arşiv').
- **"Dün / bu ay / son 7 gün"** → `tarih_tr` üzerinde aralık filtrele (ör. `tarih_tr >= date_trunc('month', BUGUN)`).

> `saat_tr` zaten TR'dir, ekstra çevirme. Tarih için ASLA created_at/order_date kullanma, sadece `tarih_tr`.

## Diğer tablolar (view kapsamı dışı)
- Sipariş ürün kalemleri: `order_items`
- Ürün/model, stok, ledger, kasa/kâr tabloları — şemadan keşfet:
  - Tablolar: `SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1;`
  - Kolonlar: `SELECT column_name, data_type FROM information_schema.columns WHERE table_name='<tablo>';`
