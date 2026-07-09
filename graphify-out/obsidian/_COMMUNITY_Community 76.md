---
type: community
cohesion: 0.23
members: 12
---

# Community 76

**Cohesion:** 0.23 - loosely connected
**Members:** 12 nodes

## Members
- [[CentralStock]] - code - models.py
- [[Genel Shopify stok sync sağlığını kontrol eder.]] - rationale - scripts/check_sync_health.py
- [[Mevcut bir alias'ın stokunu ana barkoda birleştir.     Alias kaydını silmez, sad]] - rationale - barcode_alias_helper.py
- [[Trendyol'dan tüm ürün barkodlarını çeker (orijinal haliyle)]] - rationale - scripts/sync_original_barcodes.py
- [[Veritabanındaki barkodları Trendyol'dan gelen orijinal hallerine güncelle]] - rationale - scripts/sync_original_barcodes.py
- [[check_sync_health.py]] - code - scripts/check_sync_health.py
- [[fetch_all_trendyol_barcodes()]] - code - scripts/sync_original_barcodes.py
- [[main()_11]] - code - scripts/check_sync_health.py
- [[main()_25]] - code - scripts/sync_original_barcodes.py
- [[merge_existing_alias_stocks()]] - code - barcode_alias_helper.py
- [[sync_original_barcodes.py]] - code - scripts/sync_original_barcodes.py
- [[update_database_barcodes()]] - code - scripts/sync_original_barcodes.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_76
SORT file.name ASC
```

## Connections to other communities
- 8 edges to [[_COMMUNITY_Ana Kasa Defteri]]
- 6 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 6 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 5 edges to [[_COMMUNITY_Community 61]]
- 4 edges to [[_COMMUNITY_Hepsiburada Servisi]]
- 4 edges to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 3 edges to [[_COMMUNITY_Hepsiburada Route Katmanı]]
- 3 edges to [[_COMMUNITY_Community 66]]
- 3 edges to [[_COMMUNITY_Community 78]]
- 3 edges to [[_COMMUNITY_Canlı Panel (SSE)]]
- 3 edges to [[_COMMUNITY_Community 70]]
- 2 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 2 edges to [[_COMMUNITY_Stok Senkron API]]
- 2 edges to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 2 edges to [[_COMMUNITY_Community 86]]
- 2 edges to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 2 edges to [[_COMMUNITY_Community 67]]
- 2 edges to [[_COMMUNITY_Agent API & Sipariş Sorguları]]
- 1 edge to [[_COMMUNITY_Community 53]]
- 1 edge to [[_COMMUNITY_Üretim Önerisi & Satış Tahmini]]
- 1 edge to [[_COMMUNITY_Kimlik Doğrulama & Kullanıcı Yönetimi]]
- 1 edge to [[_COMMUNITY_Kasa & Gelir-Gider]]
- 1 edge to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 1 edge to [[_COMMUNITY_Community 105]]
- 1 edge to [[_COMMUNITY_Community 93]]
- 1 edge to [[_COMMUNITY_Community 106]]
- 1 edge to [[_COMMUNITY_Community 35]]
- 1 edge to [[_COMMUNITY_Shopify Route Katmanı]]
- 1 edge to [[_COMMUNITY_Community 69]]
- 1 edge to [[_COMMUNITY_Merkezi Stok Senkronizasyonu]]
- 1 edge to [[_COMMUNITY_Community 52]]
- 1 edge to [[_COMMUNITY_Community 46]]
- 1 edge to [[_COMMUNITY_Community 62]]
- 1 edge to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]

## Top bridge nodes
- [[CentralStock]] - degree 76, connects to 34 communities
- [[check_sync_health.py]] - degree 6, connects to 3 communities
- [[sync_original_barcodes.py]] - degree 6, connects to 2 communities
- [[merge_existing_alias_stocks()]] - degree 3, connects to 1 community
- [[main()_11]] - degree 3, connects to 1 community