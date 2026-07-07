---
type: community
cohesion: 0.50
members: 4
---

# Community 101

**Cohesion:** 0.50 - moderately connected
**Members:** 4 nodes

## Members
- [[Dashboard istatistikleri.]] - rationale - shopify_site/shopify_routes.py
- [[Shopify stok senkronizasyon sayfası.]] - rationale - shopify_site/shopify_routes.py
- [[get_stats()]] - code - shopify_site/shopify_routes.py
- [[stock_sync_dashboard()]] - code - shopify_site/shopify_routes.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_101
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_Shopify Route Katmanı]]
- 1 edge to [[_COMMUNITY_Anasayfa Özet & Sayımlar]]

## Top bridge nodes
- [[stock_sync_dashboard()]] - degree 4, connects to 2 communities
- [[get_stats()]] - degree 3, connects to 1 community