---
type: community
cohesion: 0.33
members: 6
---

# Community 99

**Cohesion:** 0.33 - loosely connected
**Members:** 6 nodes

## Members
- [[.fetch_and_cache_all_listings()]] - code - hepsiburada/hepsiburada_service.py
- [[.get_listings()]] - code - hepsiburada/hepsiburada_service.py
- [[.test_connection()]] - code - hepsiburada/hepsiburada_service.py
- [[API bağlantı testi - Listing çekerek bağlantıyı doğrula]] - rationale - hepsiburada/hepsiburada_service.py
- [[Listing bilgilerini çek.         Tüm listingleri veya belirli SKU'ya göre filtre]] - rationale - hepsiburada/hepsiburada_service.py
- [[Tüm listingleri API'den çekip cache'le]] - rationale - hepsiburada/hepsiburada_service.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_99
SORT file.name ASC
```

## Connections to other communities
- 4 edges to [[_COMMUNITY_Anasayfa Özet & Sayımlar]]

## Top bridge nodes
- [[.get_listings()]] - degree 5, connects to 1 community
- [[.fetch_and_cache_all_listings()]] - degree 3, connects to 1 community
- [[.test_connection()]] - degree 3, connects to 1 community