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
- **"Bugün kaç sipariş geldi?"** → tüm statü tablolarında `created_at::date = CURRENT_DATE` say.
  Aktif siparişler statülere dağıldığı için gerekiyorsa UNION ALL ile birleştir:
  ```sql
  SELECT count(*) FROM (
    SELECT id, source, created_at FROM orders_created
    UNION ALL SELECT id, source, created_at FROM orders_hazirlaniyor
    UNION ALL SELECT id, source, created_at FROM orders_picking
    UNION ALL SELECT id, source, created_at FROM orders_shipped
    UNION ALL SELECT id, source, created_at FROM orders_delivered
  ) t WHERE created_at::date = CURRENT_DATE;
  ```
- **"Shopify'dan kaç sipariş?"** → aynı sorguya `AND source ILIKE '%SHOPIFY%'` ekle.
  (Shopify siparişleri de gulludb'ye senkron edilir — dış API/MCP KULLANMA.)
- **"Kaç sipariş gecikti?"** → `estimated_delivery_end < now()` ve henüz kargolanmamış
  (orders_shipped/delivered dışındaki statülerde).

## Diğer tablolar
- Sipariş satırları/kalemleri: `order_items`
- Ürün/model, stok, ledger, kasa/kâr tabloları ayrıca mevcut — şemadan keşfet.

## Şema keşfi
- Tablolar: `SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1;`
- Kolonlar: `SELECT column_name, data_type FROM information_schema.columns WHERE table_name='orders_created';`
