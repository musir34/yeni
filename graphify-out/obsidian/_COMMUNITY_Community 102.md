---
type: community
cohesion: 0.50
members: 4
---

# Community 102

**Cohesion:** 0.50 - moderately connected
**Members:** 4 nodes

## Members
- [[Mevcut OrderCreated kayıtları için raf stoğunu tahsis eder (tek seferlik migrasy]] - rationale - stock_sync/routes.py
- [[Mevcut OrderCreated kayıtları için raf stoğunu tahsis eder (tek seferlik migrasy_1]] - rationale - stock_sync/service.py
- [[api_migrate_reserved_stock()]] - code - stock_sync/routes.py
- [[migrate_existing_reserved_stock()]] - code - stock_sync/service.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_102
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_Stok Senkron API]]
- 1 edge to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 1 edge to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 1 edge to [[_COMMUNITY_Community 65]]
- 1 edge to [[_COMMUNITY_Community 36]]

## Top bridge nodes
- [[migrate_existing_reserved_stock()]] - degree 6, connects to 4 communities
- [[api_migrate_reserved_stock()]] - degree 4, connects to 2 communities