---
type: community
cohesion: 0.15
members: 15
---

# Community 60

**Cohesion:** 0.15 - loosely connected
**Members:** 15 nodes

## Members
- [[1) Trendyol 'archived=true' barkodlarını çek → DB’den sil     2) Trendyol 'appro]] - rationale - get_products.py
- [[Sadece onaylı ve arşivde olmayan ürünleri Trendyol'dan çeker.]] - rationale - get_products.py
- [[Trendyol ürün senkronu (tam)      1) approved=true & archived=false ürünleri çe]] - rationale - get_products.py
- [[Trendyol'da ARŞİVDE olan ürünlerin barkod listesini döner.]] - rationale - get_products.py
- [[delete_archived_in_db()]] - code - get_products.py
- [[delete_missing_products_in_db()]] - code - get_products.py
- [[extract_active_barcodes()]] - code - get_products.py
- [[fetch_all_products_async ile gelen (approved=true, archived=false) ürünlerin bar]] - rationale - get_products.py
- [[fetch_all_products_async()]] - code - get_products.py
- [[fetch_archived_barcodes_async()]] - code - get_products.py
- [[fetch_products_page()]] - code - get_products.py
- [[fetch_products_route()]] - code - get_products.py
- [[save_products_to_db_async()]] - code - get_products.py
- [[sync_trendyol_deletions()]] - code - get_products.py
- [[update_products_route()]] - code - get_products.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_60
SORT file.name ASC
```

## Connections to other communities
- 11 edges to [[_COMMUNITY_Ürün Çekme & Görsel İndirme]]
- 1 edge to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 1 edge to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]

## Top bridge nodes
- [[save_products_to_db_async()]] - degree 5, connects to 2 communities
- [[fetch_products_route()]] - degree 4, connects to 2 communities
- [[sync_trendyol_deletions()]] - degree 7, connects to 1 community
- [[fetch_all_products_async()]] - degree 5, connects to 1 community
- [[update_products_route()]] - degree 5, connects to 1 community