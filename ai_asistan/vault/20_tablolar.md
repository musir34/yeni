# Veritabanı Tabloları (gerçek şema)

> Kesin kolon adlarını gerekirse information_schema ile doğrula ama aşağıdakiler günceldir.

## Siparişler — statüye göre AYRI tablolara bölünür
Sipariş "durumuna" göre farklı tablolarda tutulur (hepsi aynı OrderBase kolonlarını paylaşır):
- `orders_created` — yeni sipariş
- `orders_hazirlaniyor` — hazırlanıyor
- `orders_picking` — toplanıyor
- `orders_ready_to_ship` — kargoya hazır
- `orders_shipped` — kargolandı
- `orders_delivered` — teslim edildi
- `orders_cancelled` — iptal
- `orders_archived` — arşiv

### Ortak (OrderBase) önemli kolonlar
- `created_at` (DateTime, **UTC**) — siparişin oluşturulma anı → "bugünkü sipariş" bununla.
- `source` (String) — **PAZARYERİ/KAYNAK**. Örn: `TRENDYOL`, `SHOPIFY_SYNC` vb.
  Kesin değerleri gör: `SELECT DISTINCT source FROM orders_created;`
- `estimated_delivery_end` (DateTime) — tahmini teslim tarihi (geciken hesabı için).

## Sık sorulan kalıplar
> ⚠️ "Bugün" = TÜRKİYE saati. created_at UTC'dir → MUTLAKA çevir (bkz. 00_asistan_kimligi).
> Tüm statü tablolarını UNION ALL ile birleştir (sipariş bugün gelip Shipped'e geçmiş olabilir).

- **"Bugün kaç sipariş geldi?"**
  ```sql
  SELECT count(*) FROM (
    SELECT source, created_at FROM orders_created
    UNION ALL SELECT source, created_at FROM orders_hazirlaniyor
    UNION ALL SELECT source, created_at FROM orders_picking
    UNION ALL SELECT source, created_at FROM orders_ready_to_ship
    UNION ALL SELECT source, created_at FROM orders_shipped
    UNION ALL SELECT source, created_at FROM orders_delivered
    UNION ALL SELECT source, created_at FROM orders_cancelled
  ) t
  WHERE (created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Istanbul')::date
        = (now() AT TIME ZONE 'Europe/Istanbul')::date;
  ```
- **"Shopify'dan kaç sipariş?"** → aynı sorguya `AND source ILIKE '%SHOPIFY%'` ekle.
  Not: `source` NULL da olabilir; "Shopify değilse" derken NULL'ı ayrı değerlendir.
  (Shopify siparişleri de gulludb'ye senkron edilir — dış API/MCP KULLANMA.)
- **"Saat kaçtan beri / saatlik dağılım?"** → TR saatine çevirip grupla:
  ```sql
  SELECT to_char(created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Istanbul','HH24') AS saat,
         count(*)
  FROM ( ... yukarıdaki UNION ALL ... ) t
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
