---
type: community
cohesion: 0.11
members: 44
---

# E-posta Bildirimleri

**Cohesion:** 0.11 - loosely connected
**Members:** 44 nodes

## Members
- [[Eksik maliyet formundan gelen değerleri Product tablosuna yazar     ve aynı tari]] - rationale - profit.py
- [[Her testte temiz tablolarla app context.]] - rationale - tests/test_stock_ledger.py
- [[Ondalıklı sayıları '1.234,56' biçiminde döndürür.     Decimal veya sayısal tür b]] - rationale - profit.py
- [[OrderBase]] - code - models.py
- [[OrderCancelled]] - code - models.py
- [[OrderCreated]] - code - models.py
- [[OrderDelivered]] - code - models.py
- [[OrderPicking]] - code - models.py
- [[OrderShipped]] - code - models.py
- [[Siparişi bul (ya arşivde ya da 5 tablodan birinde) - statüsünü İptal Edildi y]] - rationale - archive.py
- [[Siparişi tablolarda arar Created, Picking, Shipped, Delivered, Cancelled     Bu]] - rationale - archive.py
- [[Siparişleri listele.      Query params       - status Oluşturuldu  Hazırlanıy]] - rationale - agent_api.py
- [[Tüm statü tablolarını ortak kolonlarda UNION ALL yaparak tek sorgu döndürüyor.]] - rationale - all_orders_service.py
- [[UI'dan gelen 123,45 gibi değerleri güvenli şekilde Decimal'e çevirir.     None]] - rationale - profit.py
- [[_ctx_and_clean()]] - code - tests/test_stock_ledger.py
- [[_ctx_clean()]] - code - tests/test_bulk_pick.py
- [[_get_order_created_ts()]] - code - canli_panel.py
- [[_locate()]] - code - scripts/audit_today_prepared.py
- [[_maybe_write()]] - code - scripts/verify_no_phantom_ledger.py
- [[_parse_details()_4]] - code - scripts/reconcile_phantom_ledger.py
- [[_parse_details()_5]] - code - scripts/verify_no_phantom_ledger.py
- [[all_orders_service.py]] - code - all_orders_service.py
- [[all_orders_union()]] - code - all_orders_service.py
- [[archive_an_order()]] - code - archive.py
- [[audit_today_prepared.py]] - code - scripts/audit_today_prepared.py
- [[commission_update_routes.py]] - code - commission_update_routes.py
- [[d()]] - code - profit.py
- [[download_excel()]] - code - commission_update_routes.py
- [[find_order_across_tables()]] - code - archive.py
- [[find_order_across_tables()_1]] - code - degisim.py
- [[format_number()]] - code - profit.py
- [[list_orders()]] - code - agent_api.py
- [[main()_3]] - code - scripts/audit_today_prepared.py
- [[main()_24]] - code - scripts/reconcile_phantom_ledger.py
- [[main()_31]] - code - scripts/verify_no_phantom_ledger.py
- [[order_cancellation()]] - code - archive.py
- [[profit.py]] - code - profit.py
- [[profit_report()]] - code - profit.py
- [[reconcile_phantom_ledger.py]] - code - scripts/reconcile_phantom_ledger.py
- [[save_missing_costs()]] - code - profit.py
- [[search_order_by_number()]] - code - order_list_service.py
- [[update_commission_page()]] - code - commission_update_routes.py
- [[verify_no_phantom_ledger.py]] - code - scripts/verify_no_phantom_ledger.py
- [[Çok tablolu modelde, siparişi bul - arşive ekle - o tablodan sil.     Shopify]] - rationale - archive.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/E-posta_Bildirimleri
SORT file.name ASC
```

## Connections to other communities
- 35 edges to [[_COMMUNITY_Üretim Önerisi & Satış Tahmini]]
- 24 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 18 edges to [[_COMMUNITY_Kasa & Gelir-Gider]]
- 16 edges to [[_COMMUNITY_Canlı Panel (SSE)]]
- 14 edges to [[_COMMUNITY_Community 41]]
- 11 edges to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 10 edges to [[_COMMUNITY_Community 66]]
- 10 edges to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 8 edges to [[_COMMUNITY_Kimlik Doğrulama & Kullanıcı Yönetimi]]
- 8 edges to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 8 edges to [[_COMMUNITY_Agent API & Sipariş Sorguları]]
- 8 edges to [[_COMMUNITY_Community 86]]
- 7 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 6 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 6 edges to [[_COMMUNITY_Community 76]]
- 6 edges to [[_COMMUNITY_Community 52]]
- 5 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 5 edges to [[_COMMUNITY_Community 106]]
- 4 edges to [[_COMMUNITY_Stok Hareket Defteri (Ledger)]]
- 4 edges to [[_COMMUNITY_Community 71]]
- 4 edges to [[_COMMUNITY_Community 54]]
- 3 edges to [[_COMMUNITY_Community 48]]
- 3 edges to [[_COMMUNITY_Community 42]]
- 3 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 3 edges to [[_COMMUNITY_Community 97]]
- 3 edges to [[_COMMUNITY_Maliyet Fişi & Tedarikçi]]
- 2 edges to [[_COMMUNITY_Community 61]]
- 2 edges to [[_COMMUNITY_Community 100]]
- 2 edges to [[_COMMUNITY_Community 55]]
- 1 edge to [[_COMMUNITY_Stok Senkron API]]
- 1 edge to [[_COMMUNITY_Community 129]]
- 1 edge to [[_COMMUNITY_Community 57]]
- 1 edge to [[_COMMUNITY_Community 69]]
- 1 edge to [[_COMMUNITY_Merkezi Stok Senkronizasyonu]]
- 1 edge to [[_COMMUNITY_Community 105]]
- 1 edge to [[_COMMUNITY_Hava Durumu Animasyonu (Canvas)]]

## Top bridge nodes
- [[OrderCreated]] - degree 62, connects to 19 communities
- [[OrderPicking]] - degree 52, connects to 16 communities
- [[OrderDelivered]] - degree 48, connects to 15 communities
- [[OrderShipped]] - degree 48, connects to 15 communities
- [[OrderCancelled]] - degree 24, connects to 10 communities