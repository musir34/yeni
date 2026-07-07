---
type: community
cohesion: 0.13
members: 24
---

# Community 35

**Cohesion:** 0.13 - loosely connected
**Members:** 24 nodes

## Members
- [[.__init__()_6]] - code - shopify_site/shopify_stock_service.py
- [[._enable_tracking_for_mappings()]] - code - shopify_site/shopify_stock_service.py
- [[._graphql()_1]] - code - shopify_site/shopify_stock_service.py
- [[._send_stock_batch()]] - code - shopify_site/shopify_stock_service.py
- [[.fetch_all_variants()]] - code - shopify_site/shopify_stock_service.py
- [[.get_location_id()]] - code - shopify_site/shopify_stock_service.py
- [[.get_mappings()]] - code - shopify_site/shopify_stock_service.py
- [[.get_stats()]] - code - shopify_site/shopify_stock_service.py
- [[.get_unmatched_items()]] - code - shopify_site/shopify_stock_service.py
- [[.is_configured()_5]] - code - shopify_site/shopify_stock_service.py
- [[.match_barcodes()]] - code - shopify_site/shopify_stock_service.py
- [[.push_stock()]] - code - shopify_site/shopify_stock_service.py
- [[Any_5]] - code
- [[CentralStock'taki stokları Shopify'a gönder.         barcodes Belirli barkodlar]] - rationale - shopify_site/shopify_stock_service.py
- [[Dashboard istatistikleri._1]] - rationale - shopify_site/shopify_stock_service.py
- [[Envanter takibi (tracked) kapalı olan ürünlerde tracking'i toplu olarak açar.]] - rationale - shopify_site/shopify_stock_service.py
- [[Kayıtlı eşleştirmeleri listele.]] - rationale - shopify_site/shopify_stock_service.py
- [[Shopify stok eşleştirme ve senkronizasyon servisi.]] - rationale - shopify_site/shopify_stock_service.py
- [[Shopify variant barkodlarını panel barkodlarıyla eşleştir ve DB'ye kaydet.]] - rationale - shopify_site/shopify_stock_service.py
- [[Shopify'dan tüm product variant'ları çeker.         Her variant id, sku, barcod]] - rationale - shopify_site/shopify_stock_service.py
- [[ShopifyStockService]] - code - shopify_site/shopify_stock_service.py
- [[Son eşleştirmede eşleşmeyen tüm ürünleri döndür.]] - rationale - shopify_site/shopify_stock_service.py
- [[Tek bir batch stok güncellemesi gönder (max 100 item tek API çağrısı).]] - rationale - shopify_site/shopify_stock_service.py
- [[İlk aktif fulfillment lokasyonunun GID'sini döndür.]] - rationale - shopify_site/shopify_stock_service.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_35
SORT file.name ASC
```

## Connections to other communities
- 4 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 2 edges to [[_COMMUNITY_Community 55]]
- 1 edge to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 1 edge to [[_COMMUNITY_Community 38]]
- 1 edge to [[_COMMUNITY_E-posta Bildirimleri]]

## Top bridge nodes
- [[ShopifyStockService]] - degree 19, connects to 4 communities
- [[.push_stock()]] - degree 7, connects to 1 community
- [[.match_barcodes()]] - degree 5, connects to 1 community
- [[.__init__()_6]] - degree 2, connects to 1 community