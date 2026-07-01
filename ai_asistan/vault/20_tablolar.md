# Veritabanı Tabloları (gerçek şema)

> Kesin kolon adlarını gerekirse information_schema ile doğrula ama aşağıdakiler günceldir.

## Siparişler — statüye göre 8 AYRI tabloya bölünür (KRİTİK)
Sipariş "durumuna" göre farklı tablolarda tutulur (hepsi aynı OrderBase kolonlarını paylaşır).
Bir sipariş yaşam döngüsünde tablodan tabloya taşınır. `orders` tablosu BOŞTUR, kullanma.

### 📅 HANGİ TARİH? (created_at vs order_date) — KARIŞTIRMA
- `created_at` = siparişin **bizim sistemimize düştüğü/geldiği** an. **"Bugün kaç sipariş geldi",
  "bugünkü siparişler", "saat kaçta geldi" → HER ZAMAN `created_at` kullan.**
- `order_date` = pazaryerinin (Trendyol vb.) orijinal sipariş tarihi; günler önce olabilir.
  Sadece kullanıcı açıkça "müşteri ne zaman sipariş verdi / pazaryeri sipariş tarihi" derse kullan.
- İkisi çok farklı sonuç verir (örn. bugün created_at=100, order_date=29). Varsayılan: **created_at**.

### Sipariş kimliği
- Her satır bir sipariştir; gerekirse `COUNT(DISTINCT order_number)` de aynı sonucu verir.

🚫 **ASLA tek bir statü tablosuna bakıp "toplam sipariş" sayma!** Örn. sadece `orders_shipped`'e
bakmak yanlış sayı verir (bugün 100 yerine 27 gibi). Sipariş SAYISI/analizi gereken HER soruda
AŞAĞIDAKİ 8-TABLO BİRLEŞİMİNİ (`tum_siparisler` CTE, **created_at ile**) kullan — istisnasız:

```sql
WITH tum_siparisler AS (
  SELECT 'Yeni'         AS statu, source, created_at, amount, order_number, estimated_delivery_end FROM orders_created
  UNION ALL SELECT 'Hazırlanıyor',  source, created_at, amount, order_number, estimated_delivery_end FROM orders_hazirlaniyor
  UNION ALL SELECT 'Toplanıyor',    source, created_at, amount, order_number, estimated_delivery_end FROM orders_picking
  UNION ALL SELECT 'Kargoya Hazır', source, created_at, amount, order_number, estimated_delivery_end FROM orders_ready_to_ship
  UNION ALL SELECT 'Kargolandı',    source, created_at, amount, order_number, estimated_delivery_end FROM orders_shipped
  UNION ALL SELECT 'Teslim Edildi', source, created_at, amount, order_number, estimated_delivery_end FROM orders_delivered
  UNION ALL SELECT 'İptal',         source, created_at, amount, order_number, estimated_delivery_end FROM orders_cancelled
  UNION ALL SELECT 'Arşiv',         source, created_at, amount, order_number, estimated_delivery_end FROM orders_archived
)
SELECT count(*) FROM tum_siparisler
WHERE (created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Istanbul')::date
      = (now() AT TIME ZONE 'Europe/Istanbul')::date;
```
Diğer sütun gerekiyorsa CTE'ye ekle (ortak OrderBase kolonları: customer_name, product_name,
product_barcode, quantity, discount, commission, status, order_date, cargo_tracking_number...).

### Ortak (OrderBase) önemli kolonlar
- `created_at` (DateTime, **UTC**) — siparişin oluşturulma anı → "bugünkü sipariş" bununla.
- `source` (String) — **PAZARYERİ/KAYNAK**. Örn: `TRENDYOL`, `SHOPIFY_SYNC` vb.
  Kesin değerleri gör: `SELECT DISTINCT source FROM orders_created;`
- `estimated_delivery_end` (DateTime) — tahmini teslim tarihi (geciken hesabı için).

## Sık sorulan kalıplar
> ⚠️ "Bugün" = TÜRKİYE saati. created_at UTC'dir → MUTLAKA çevir (bkz. 00_asistan_kimligi).
> Tüm statü tablolarını UNION ALL ile birleştir (sipariş bugün gelip Shipped'e geçmiş olabilir).

- **"Bugün kaç sipariş geldi?"** → yukarıdaki `tum_siparisler` CTE'sini kullan (8 tablo!),
  TR saatiyle bugüne filtrele. Tek tabloya ASLA bakma.
- **"Shopify'dan kaç sipariş?"** → aynı CTE + `WHERE ... AND source ILIKE '%SHOPIFY%'`.
  Not: `source` NULL da olabilir; "Shopify değilse" derken NULL'ı ayrı değerlendir.
  (Shopify siparişleri de gulludb'ye senkron edilir — dış API/MCP KULLANMA.)
- **"Saat kaçtan beri / saatlik dağılım?"** → `tum_siparisler` CTE'sinden, TR saatine çevirip grupla:
  ```sql
  WITH tum_siparisler AS ( ... 8 tablo UNION ALL ... )
  SELECT to_char(created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Istanbul','HH24') AS saat,
         count(*)
  FROM tum_siparisler
  WHERE (created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Istanbul')::date
        = (now() AT TIME ZONE 'Europe/Istanbul')::date
  GROUP BY 1 ORDER BY 1;
  ```
- **"Kaç sipariş gecikti?"** → `estimated_delivery_end < now()` ve henüz kargolanmamış
  (orders_shipped/delivered dışındaki statülerde).

## Diğer tablolar
- Sipariş satırları/kalemleri: `order_items`
- Ürün/model, stok, ledger, kasa/kâr tabloları ayrıca mevcut — şemadan keşfet.

## Şema keşfi
- Tablolar: `SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1;`
- Kolonlar: `SELECT column_name, data_type FROM information_schema.columns WHERE table_name='orders_created';`
