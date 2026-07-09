---
type: community
cohesion: 0.10
members: 27
---

# Ana Kasa Defteri

**Cohesion:** 0.10 - loosely connected
**Members:** 27 nodes

## Members
- [[.to_dict()_2]] - code - models.py
- [[21 stale Shopify mapping'inin gerçek durumunu Shopify GraphQL ile kontrol eder.]] - rationale - scripts/diagnose_stale_shopify_mappings.py
- [[73073434828 barkodu için panel stoğu, raf, mapping ve Shopify envanterini karşıl]] - rationale - scripts/check_stock_sync_73073434828.py
- [[730734501 için neden sync düzeltmiyor — tam tanı.]] - rationale - scripts/diagnose_730734501.py
- [[Aynı barkodda birden çok mapping varsa, Shopify'da bulunmayan inventory item'lar]] - rationale - scripts/clean_all_stale_duplicates.py
- [[Panel ≠ Shopify son gönderilen olan mapping'leri tespit edip zorla gönderir.]] - rationale - scripts/fix_mismatches.py
- [[Shopify barkod eşleştirme tablosu - Panel barkodu - Shopify variant eşleşmesi]] - rationale - models.py
- [[Shopify'da artık bulunmayan inventory item'lara ait stale mapping'leri temizle.]] - rationale - scripts/clean_stale_mappings.py
- [[Shopify'da artık var olmayan ShopifyMapping kayıtlarını siler.  Önce diagnose_st]] - rationale - scripts/cleanup_dead_shopify_mappings.py
- [[ShopifyMapping]] - code - models.py
- [[Tüm platformlara gönderilen stoktan düşülecek güvenlik tamponu.      Env değişke]] - rationale - stock_sync/service.py
- [[check_stock_sync_73073434828.py]] - code - scripts/check_stock_sync_73073434828.py
- [[clean_all_stale_duplicates.py]] - code - scripts/clean_all_stale_duplicates.py
- [[clean_stale_mappings.py]] - code - scripts/clean_stale_mappings.py
- [[cleanup_dead_shopify_mappings.py]] - code - scripts/cleanup_dead_shopify_mappings.py
- [[diagnose_730734501.py]] - code - scripts/diagnose_730734501.py
- [[diagnose_stale_shopify_mappings.py]] - code - scripts/diagnose_stale_shopify_mappings.py
- [[fix_mismatches.py]] - code - scripts/fix_mismatches.py
- [[get_safety_stock_buffer()]] - code - stock_sync/service.py
- [[main()_10]] - code - scripts/check_stock_sync_73073434828.py
- [[main()_12]] - code - scripts/clean_all_stale_duplicates.py
- [[main()_13]] - code - scripts/clean_stale_mappings.py
- [[main()_14]] - code - scripts/cleanup_dead_shopify_mappings.py
- [[main()_18]] - code - scripts/diagnose_730734501.py
- [[main()_19]] - code - scripts/diagnose_stale_shopify_mappings.py
- [[main()_21]] - code - scripts/fix_mismatches.py
- [[shopify_stock_service.py]] - code - shopify_site/shopify_stock_service.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Ana_Kasa_Defteri
SORT file.name ASC
```

## Connections to other communities
- 8 edges to [[_COMMUNITY_Community 66]]
- 8 edges to [[_COMMUNITY_Community 76]]
- 7 edges to [[_COMMUNITY_Stok Senkron API]]
- 5 edges to [[_COMMUNITY_Community 61]]
- 5 edges to [[_COMMUNITY_Community 70]]
- 4 edges to [[_COMMUNITY_Community 35]]
- 3 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 2 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 2 edges to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 2 edges to [[_COMMUNITY_Community 74]]
- 2 edges to [[_COMMUNITY_Community 69]]
- 2 edges to [[_COMMUNITY_Merkezi Stok Senkronizasyonu]]
- 1 edge to [[_COMMUNITY_Hepsiburada Route Katmanı]]
- 1 edge to [[_COMMUNITY_Community 104]]
- 1 edge to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 1 edge to [[_COMMUNITY_Shopify Admin Servisi]]
- 1 edge to [[_COMMUNITY_Shopify Route Katmanı]]
- 1 edge to [[_COMMUNITY_Community 39]]
- 1 edge to [[_COMMUNITY_Idefix Entegrasyonu]]

## Top bridge nodes
- [[ShopifyMapping]] - degree 31, connects to 12 communities
- [[shopify_stock_service.py]] - degree 16, connects to 7 communities
- [[check_stock_sync_73073434828.py]] - degree 10, connects to 6 communities
- [[diagnose_730734501.py]] - degree 9, connects to 5 communities
- [[get_safety_stock_buffer()]] - degree 8, connects to 4 communities