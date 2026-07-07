---
type: community
cohesion: 0.20
members: 11
---

# Community 75

**Cohesion:** 0.20 - loosely connected
**Members:** 11 nodes

## Members
- [[.to_dict()_1]] - code - models.py
- [[Otomatik senkronizasyonu açkapat]] - rationale - stock_sync/routes.py
- [[Platform config'ini güncelle]] - rationale - stock_sync/routes.py
- [[Platform yapılandırmaları]] - rationale - models.py
- [[PlatformConfig]] - code - models.py
- [[Senkronizasyon detayı - Her ürün için kayıt]] - rationale - models.py
- [[SyncDetail]] - code - models.py
- [[__init__.py_6]] - code - stock_sync/__init__.py
- [[api_toggle_auto_sync()]] - code - stock_sync/routes.py
- [[api_update_config()]] - code - stock_sync/routes.py
- [[models.py_1]] - code - stock_sync/models.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_75
SORT file.name ASC
```

## Connections to other communities
- 4 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 4 edges to [[_COMMUNITY_Stok Senkron API]]
- 3 edges to [[_COMMUNITY_Community 65]]
- 3 edges to [[_COMMUNITY_Merkezi Stok Senkronizasyonu]]
- 3 edges to [[_COMMUNITY_Community 76]]
- 2 edges to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 2 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 1 edge to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 1 edge to [[_COMMUNITY_Community 36]]
- 1 edge to [[_COMMUNITY_Community 85]]

## Top bridge nodes
- [[PlatformConfig]] - degree 13, connects to 7 communities
- [[SyncDetail]] - degree 9, connects to 5 communities
- [[__init__.py_6]] - degree 6, connects to 4 communities
- [[models.py_1]] - degree 5, connects to 3 communities
- [[api_toggle_auto_sync()]] - degree 4, connects to 2 communities