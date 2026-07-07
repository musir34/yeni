---
type: community
cohesion: 0.06
members: 51
---

# Veri Modelleri (SQLAlchemy)

**Cohesion:** 0.06 - loosely connected
**Members:** 51 nodes

## Members
- [[.to_dict()_2]] - code - models.py
- [[21 stale Shopify mapping'inin gerçek durumunu Shopify GraphQL ile kontrol eder.]] - rationale - scripts/diagnose_stale_shopify_mappings.py
- [[73073434828 barkodu için panel stoğu, raf, mapping ve Shopify envanterini karşıl]] - rationale - scripts/check_stock_sync_73073434828.py
- [[730734501 için neden sync düzeltmiyor — tam tanı.]] - rationale - scripts/diagnose_730734501.py
- [[Aynı barkodda birden çok mapping varsa, Shopify'da bulunmayan inventory item'lar]] - rationale - scripts/clean_all_stale_duplicates.py
- [[Commit sonrası etkilenen barkodların CentralStock'unu güncelle.      NOT after_]] - rationale - models.py
- [[Expense]] - code - models.py
- [[ForecastDirty]] - code - models.py
- [[Hatice Göker siparişindeki ürünlerin raf konumlarını kontrol eder.]] - rationale - scripts/check_hatice_raf.py
- [[MasterTask]] - code - models.py
- [[OrderItem]] - code - models.py
- [[Panel ≠ Shopify son gönderilen olan mapping'leri tespit edip zorla gönderir.]] - rationale - scripts/fix_mismatches.py
- [[Product]] - code - models.py
- [[RafUrun insertupdatedelete olduğunda barkodu session.info'ya ekle]] - rationale - models.py
- [[Shipment]] - code - models.py
- [[Shopify Admin API konfigürasyonu. Yeni API client_id + client_secret ile OAuth]] - rationale - shopify_site/shopify_config.py
- [[Shopify Admin GraphQL servis katmanı.]] - rationale - shopify_site/shopify_service.py
- [[Shopify barkod eşleştirme tablosu - Panel barkodu - Shopify variant eşleşmesi]] - rationale - models.py
- [[Shopify'da artık bulunmayan inventory item'lara ait stale mapping'leri temizle.]] - rationale - scripts/clean_stale_mappings.py
- [[Shopify'da artık var olmayan ShopifyMapping kayıtlarını siler.  Önce diagnose_st]] - rationale - scripts/cleanup_dead_shopify_mappings.py
- [[ShopifyMapping]] - code - models.py
- [[Task]] - code - models.py
- [[TaskTemplate]] - code - models.py
- [[_sync_central_after_commit()]] - code - models.py
- [[_track_raf_change()]] - code - models.py
- [[check_hatice_raf.py]] - code - scripts/check_hatice_raf.py
- [[check_stock_sync_73073434828.py]] - code - scripts/check_stock_sync_73073434828.py
- [[clean_all_stale_duplicates.py]] - code - scripts/clean_all_stale_duplicates.py
- [[clean_stale_mappings.py]] - code - scripts/clean_stale_mappings.py
- [[cleanup_dead_shopify_mappings.py]] - code - scripts/cleanup_dead_shopify_mappings.py
- [[diagnose_730734501.py]] - code - scripts/diagnose_730734501.py
- [[diagnose_stale_shopify_mappings.py]] - code - scripts/diagnose_stale_shopify_mappings.py
- [[fix_mismatches.py]] - code - scripts/fix_mismatches.py
- [[main()_7]] - code - scripts/check_hatice_raf.py
- [[main()_10]] - code - scripts/check_stock_sync_73073434828.py
- [[main()_12]] - code - scripts/clean_all_stale_duplicates.py
- [[main()_13]] - code - scripts/clean_stale_mappings.py
- [[main()_14]] - code - scripts/cleanup_dead_shopify_mappings.py
- [[main()_18]] - code - scripts/diagnose_730734501.py
- [[main()_19]] - code - scripts/diagnose_stale_shopify_mappings.py
- [[main()_21]] - code - scripts/fix_mismatches.py
- [[main()_28]] - code - scripts/today_picking_pdf.py
- [[models.py]] - code - models.py
- [[resolve_panel_barcode()]] - code - scripts/check_hatice_raf.py
- [[shelf_for()]] - code - scripts/check_hatice_raf.py
- [[shopify_config.py]] - code - shopify_site/shopify_config.py
- [[shopify_service.py]] - code - shopify_site/shopify_service.py
- [[shopify_stock_service.py]] - code - shopify_site/shopify_stock_service.py
- [[stock_report()]] - code - stock_report.py
- [[stock_report.py]] - code - stock_report.py
- [[today_picking_pdf.py]] - code - scripts/today_picking_pdf.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Veri_Modelleri_SQLAlchemy
SORT file.name ASC
```

## Connections to other communities
- 17 edges to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 15 edges to [[_COMMUNITY_Community 38]]
- 12 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 12 edges to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 12 edges to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 10 edges to [[_COMMUNITY_Üretim Önerisi & Satış Tahmini]]
- 10 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 10 edges to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 6 edges to [[_COMMUNITY_Maliyet Fişi & Tedarikçi]]
- 6 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 5 edges to [[_COMMUNITY_Ürün Çekme & Görsel İndirme]]
- 5 edges to [[_COMMUNITY_Kasa & Gelir-Gider]]
- 5 edges to [[_COMMUNITY_Ana Kasa Defteri]]
- 5 edges to [[_COMMUNITY_Manuel Sipariş Oluşturma]]
- 5 edges to [[_COMMUNITY_Community 62]]
- 5 edges to [[_COMMUNITY_Stok Senkron API]]
- 5 edges to [[_COMMUNITY_Community 68]]
- 5 edges to [[_COMMUNITY_Shopify Admin Servisi]]
- 4 edges to [[_COMMUNITY_Anasayfa Özet & Sayımlar]]
- 4 edges to [[_COMMUNITY_Community 75]]
- 4 edges to [[_COMMUNITY_Stok Hareket Defteri (Ledger)]]
- 4 edges to [[_COMMUNITY_Community 65]]
- 4 edges to [[_COMMUNITY_Community 35]]
- 3 edges to [[_COMMUNITY_Canlı Panel (SSE)]]
- 3 edges to [[_COMMUNITY_Community 49]]
- 3 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 3 edges to [[_COMMUNITY_Community 44]]
- 3 edges to [[_COMMUNITY_Community 59]]
- 3 edges to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 3 edges to [[_COMMUNITY_Community 77]]
- 3 edges to [[_COMMUNITY_Community 55]]
- 3 edges to [[_COMMUNITY_Shopify Route Katmanı]]
- 2 edges to [[_COMMUNITY_Agent API & Sipariş Sorguları]]
- 2 edges to [[_COMMUNITY_Community 80]]
- 2 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 2 edges to [[_COMMUNITY_Community 61]]
- 2 edges to [[_COMMUNITY_Kimlik Doğrulama & Kullanıcı Yönetimi]]
- 2 edges to [[_COMMUNITY_Community 93]]
- 2 edges to [[_COMMUNITY_Community 42]]
- 2 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 2 edges to [[_COMMUNITY_Yeni Sipariş Hazırlama & Toplama]]
- 2 edges to [[_COMMUNITY_Community 64]]
- 2 edges to [[_COMMUNITY_Community 74]]
- 2 edges to [[_COMMUNITY_Raf Sistemi & Etiket]]
- 2 edges to [[_COMMUNITY_Community 85]]
- 2 edges to [[_COMMUNITY_Community 98]]
- 2 edges to [[_COMMUNITY_Community 54]]
- 2 edges to [[_COMMUNITY_Community 37]]
- 1 edge to [[_COMMUNITY_Community 47]]
- 1 edge to [[_COMMUNITY_Community 60]]
- 1 edge to [[_COMMUNITY_Idefix Entegrasyonu]]
- 1 edge to [[_COMMUNITY_Community 50]]
- 1 edge to [[_COMMUNITY_Community 106]]
- 1 edge to [[_COMMUNITY_Community 76]]
- 1 edge to [[_COMMUNITY_Merkezi Stok Senkronizasyonu]]

## Top bridge nodes
- [[models.py]] - degree 139, connects to 46 communities
- [[Product]] - degree 62, connects to 35 communities
- [[ShopifyMapping]] - degree 31, connects to 10 communities
- [[shopify_service.py]] - degree 13, connects to 7 communities
- [[shopify_config.py]] - degree 10, connects to 7 communities