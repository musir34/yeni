# Veritabanı Tabloları (gerçek şema)

## ⭐ SİPARİŞLER İÇİN TEK KAYNAK: `ai_orders_all` VIEW'İ
Siparişlerle ilgili HER soruda (sayım, dağılım, ciro, saat, pazaryeri...) **yalnızca
`ai_orders_all` view'ini kullan.** Bu view 8 statü tablosunu (yeni→arşiv) birleştirir ve
tarihleri **Türkiye saatine (Europe/Istanbul) çevrilmiş hazır kolonlarla** verir.

🚫 Tek tek statü tablolarına (orders_created, orders_shipped...) ELLE bakma, UNION yazma,
ham `created_at`/`order_date` ile TR dönüşümü yapma — hepsi bu view'de HAZIR.

### View'in hazır kolonları
> ⚠️ Bu view'de her şey ZATEN Türkiye saatinde. Bağlantı oturumu da Europe/Istanbul.
> Dolayısıyla `current_date` = TR bugün, `now()` = TR şimdi. **HİÇBİR `AT TIME ZONE` dönüşümü
> YAPMA** — çift çevirirsen saat 3 saat kayar. Sadece kolonları olduğu gibi kullan.

- `statu` — durum (Yeni / Hazırlanıyor / Toplanıyor / Kargoya Hazır / Kargolandı / Teslim Edildi / İptal / Arşiv)
- **`tarih_tr` (date) — sipariş tarihi (TR). TÜM tarih filtreleri için TEK kolon: `tarih_tr = current_date`.**
- `saat_tr` (timestamptz) — sipariş anı; TR saatinde gösterilir. Saat için `to_char(saat_tr,'HH24:MI')`.
- `teslim_tarihi_tr` (timestamptz) — tahmini teslim; geciken için `teslim_tarihi_tr < now()`.
- `source` — pazaryeri (TRENDYOL, SHOPIFY_SYNC... NULL olabilir). Shopify: `source ILIKE '%SHOPIFY%'`.
- Ayrıca: `order_number, status, amount, quantity, discount, commission, customer_name,
  customer_surname, product_name, product_barcode, product_code, product_size, cargo_tracking_number`.
- Her satır bir sipariştir (order_number benzersiz). Ham UTC kolonu YOKTUR.

### Hazır sorgular (kopyala-kullan) — dönüşüm YOK, sade
- **"Bugün kaç sipariş geldi?"** `SELECT count(*) FROM ai_orders_all WHERE tarih_tr = current_date;`
- **"Shopify'dan bugün kaç sipariş?"** → `... WHERE tarih_tr=current_date AND source ILIKE '%SHOPIFY%';`
- **"Pazaryeri dağılımı bugün":** `SELECT source, count(*) FROM ai_orders_all WHERE tarih_tr=current_date GROUP BY source ORDER BY 2 DESC;`
- **"Saatlik dağılım / saat kaçtan beri":** `SELECT to_char(saat_tr,'HH24') saat, count(*) FROM ai_orders_all WHERE tarih_tr=current_date GROUP BY 1 ORDER BY 1;`
  (ilk/son saat için: `min(saat_tr), max(saat_tr)`)
- **"Bugünkü ciro":** `SELECT sum(amount) FROM ai_orders_all WHERE tarih_tr=current_date;`
- **"Statü dağılımı":** `SELECT statu, count(*) FROM ai_orders_all WHERE tarih_tr=current_date GROUP BY statu;`
- **"Kaç sipariş gecikti?"** `... WHERE teslim_tarihi_tr < now() AND statu NOT IN ('Kargolandı','Teslim Edildi','İptal','Arşiv');`
- **"Dün":** `tarih_tr = current_date - 1` · **"Bu ay":** `tarih_tr >= date_trunc('month',current_date)` · **"Son 7 gün":** `tarih_tr >= current_date - 6`

## Diğer tablolar (view kapsamı dışı)
- Sipariş ürün kalemleri: `order_items`
- Ürün/model, stok, ledger, kasa/kâr tabloları — şemadan keşfet:
  - Tablolar: `SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1;`
  - Kolonlar: `SELECT column_name, data_type FROM information_schema.columns WHERE table_name='<tablo>';`
