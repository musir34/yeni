---
type: community
cohesion: 0.11
members: 21
---

# Community 38

**Cohesion:** 0.11 - loosely connected
**Members:** 21 nodes

## Members
- [[.__init__()_7]] - code - siparisler.py
- [[CentralStock]] - code - models.py
- [[FakeDB]] - code - siparisler.py
- [[Genel Shopify stok sync sağlığını kontrol eder.]] - rationale - scripts/check_sync_health.py
- [[Mevcut bir alias'ın stokunu ana barkoda birleştir.     Alias kaydını silmez, sad]] - rationale - barcode_alias_helper.py
- [[Stok listesi.      Query params       - search barkod ile arama       - min_qt]] - rationale - agent_api.py
- [[Trendyol'dan tüm ürün barkodlarını çeker (orijinal haliyle)]] - rationale - scripts/sync_original_barcodes.py
- [[Tüm CentralStock kayıtlarını raflardaki toplamla senkronize et - SQL ile hızlı]] - rationale - scripts/fix_central_stock_sync.py
- [[Veritabanındaki barkodları Trendyol'dan gelen orijinal hallerine güncelle]] - rationale - scripts/sync_original_barcodes.py
- [[_ctx_clean()_1]] - code - tests/test_picking_service.py
- [[check_sync_health.py]] - code - scripts/check_sync_health.py
- [[fetch_all_trendyol_barcodes()]] - code - scripts/sync_original_barcodes.py
- [[fix_central_stock_sync.py]] - code - scripts/fix_central_stock_sync.py
- [[list_stock()]] - code - agent_api.py
- [[main()_11]] - code - scripts/check_sync_health.py
- [[main()_25]] - code - scripts/sync_original_barcodes.py
- [[merge_existing_alias_stocks()]] - code - barcode_alias_helper.py
- [[stock_summary()]] - code - agent_api.py
- [[sync_all_central_stock()]] - code - scripts/fix_central_stock_sync.py
- [[sync_original_barcodes.py]] - code - scripts/sync_original_barcodes.py
- [[update_database_barcodes()]] - code - scripts/sync_original_barcodes.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_38
SORT file.name ASC
```

## Connections to other communities
- 15 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 8 edges to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 6 edges to [[_COMMUNITY_Manuel Sipariş Oluşturma]]
- 6 edges to [[_COMMUNITY_Community 50]]
- 5 edges to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 5 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 4 edges to [[_COMMUNITY_Agent API & Sipariş Sorguları]]
- 4 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 4 edges to [[_COMMUNITY_Community 62]]
- 4 edges to [[_COMMUNITY_Stok Hareket Defteri (Ledger)]]
- 3 edges to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 3 edges to [[_COMMUNITY_Ürün Çekme & Görsel İndirme]]
- 3 edges to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 3 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 2 edges to [[_COMMUNITY_Community 54]]
- 2 edges to [[_COMMUNITY_Üretim Önerisi & Satış Tahmini]]
- 1 edge to [[_COMMUNITY_Canlı Panel (SSE)]]
- 1 edge to [[_COMMUNITY_Değişim  İade Talepleri]]
- 1 edge to [[_COMMUNITY_Anasayfa Özet & Sayımlar]]
- 1 edge to [[_COMMUNITY_Raf Sistemi & Etiket]]
- 1 edge to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 1 edge to [[_COMMUNITY_Community 85]]
- 1 edge to [[_COMMUNITY_Community 98]]
- 1 edge to [[_COMMUNITY_Community 35]]
- 1 edge to [[_COMMUNITY_Stok Senkron API]]
- 1 edge to [[_COMMUNITY_Community 65]]
- 1 edge to [[_COMMUNITY_Merkezi Stok Senkronizasyonu]]
- 1 edge to [[_COMMUNITY_Community 37]]
- 1 edge to [[_COMMUNITY_Community 58]]

## Top bridge nodes
- [[CentralStock]] - degree 76, connects to 29 communities
- [[_ctx_clean()_1]] - degree 6, connects to 5 communities
- [[FakeDB]] - degree 7, connects to 3 communities
- [[fix_central_stock_sync.py]] - degree 5, connects to 3 communities
- [[check_sync_health.py]] - degree 6, connects to 2 communities