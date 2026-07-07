---
type: community
cohesion: 0.11
members: 45
---

# Sipariş Yaşam Döngüsü & Arşiv

**Cohesion:** 0.11 - loosely connected
**Members:** 45 nodes

## Members
- [[.__repr__()_6]] - code - models.py
- [[Aktif tablolarda (YeniHazırlanıyorİşleme Alındı) takılı kalan ESKİ Trendyol]] - rationale - order_service.py
- [[Archive]] - code - models.py
- [[Arşivdeki siparişi 'Picking' statüsüne geçirmek için     1) Trendyol API'ye -]] - rationale - archive.py
- [[Arşivdeki siparişi orders_created tablosuna geri taşır.]] - rationale - archive.py
- [[Bir siparişin statüsünü güncelle.     Eğer çok tablolu modelde sipariş CreatedP]] - rationale - archive.py
- [[Detaylı ve güzel HTML email oluşturur.]] - rationale - mail_service.py
- [[Her testte temiz tablolarla app context.]] - rationale - tests/test_stock_ledger.py
- [[OrderBase]] - code - models.py
- [[OrderCancelled]] - code - models.py
- [[OrderCreated]] - code - models.py
- [[OrderDelivered]] - code - models.py
- [[OrderHazirlaniyor]] - code - models.py
- [[OrderPicking]] - code - models.py
- [[Phantom picking temizligi Terfi sirasinda (sync guard eklenmeden onceki pencere]] - rationale - scripts/cleanup_phantom_picking.py
- [[Sipariş details alanını ürün listesine çevirir.]] - rationale - mail_service.py
- [[Siparişi bul (ya arşivde ya da 5 tablodan birinde) - statüsünü İptal Edildi y]] - rationale - archive.py
- [[Siparişi tablolarda arar Created, Picking, Shipped, Delivered, Cancelled     Bu]] - rationale - archive.py
- [[Siparişleri listele.      Query params       - status Oluşturuldu  Hazırlanıy]] - rationale - agent_api.py
- [[Tüm statü tablolarını ortak kolonlarda UNION ALL yaparak tek sorgu döndürüyor.]] - rationale - all_orders_service.py
- [[_ctx_and_clean()]] - code - tests/test_stock_ledger.py
- [[_ctx_clean()]] - code - tests/test_bulk_pick.py
- [[_get_order_created_ts()]] - code - canli_panel.py
- [[_locate()]] - code - scripts/audit_today_prepared.py
- [[_parse_products()]] - code - mail_service.py
- [[all_orders_service.py]] - code - all_orders_service.py
- [[all_orders_union()]] - code - all_orders_service.py
- [[archive.py]] - code - archive.py
- [[archive_an_order()]] - code - archive.py
- [[audit_today_prepared.py]] - code - scripts/audit_today_prepared.py
- [[build_email_html()]] - code - mail_service.py
- [[change_order_status()]] - code - archive.py
- [[cleanup_phantom_picking.py]] - code - scripts/cleanup_phantom_picking.py
- [[clear_atanan_raf.py]] - code - scripts/clear_atanan_raf.py
- [[execute_order_processing()]] - code - archive.py
- [[find_order_across_tables()]] - code - archive.py
- [[find_order_across_tables()_1]] - code - degisim.py
- [[list_orders()]] - code - agent_api.py
- [[main()_3]] - code - scripts/audit_today_prepared.py
- [[main()_15]] - code - scripts/clear_atanan_raf.py
- [[order_cancellation()]] - code - archive.py
- [[reconcile_active_orders_async()]] - code - order_service.py
- [[recover_from_archive()]] - code - archive.py
- [[search_order_by_number()]] - code - order_list_service.py
- [[Çok tablolu modelde, siparişi bul - arşive ekle - o tablodan sil.     Shopify]] - rationale - archive.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Sipari_Yaam_Dngs__Ariv
SORT file.name ASC
```

## Connections to other communities
- 38 edges to [[_COMMUNITY_Canlı Panel (SSE)]]
- 21 edges to [[_COMMUNITY_Anasayfa Özet & Sayımlar]]
- 19 edges to [[_COMMUNITY_Community 50]]
- 19 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 19 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 14 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 14 edges to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 14 edges to [[_COMMUNITY_Stok Hareket Defteri (Ledger)]]
- 12 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 12 edges to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 11 edges to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 8 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 8 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 7 edges to [[_COMMUNITY_Ana Kasa Defteri]]
- 6 edges to [[_COMMUNITY_Agent API & Sipariş Sorguları]]
- 6 edges to [[_COMMUNITY_Üretim Önerisi & Satış Tahmini]]
- 5 edges to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 5 edges to [[_COMMUNITY_Community 79]]
- 5 edges to [[_COMMUNITY_Community 98]]
- 4 edges to [[_COMMUNITY_Community 80]]
- 3 edges to [[_COMMUNITY_Community 64]]
- 3 edges to [[_COMMUNITY_Community 38]]
- 3 edges to [[_COMMUNITY_Yeni Sipariş Hazırlama & Toplama]]
- 2 edges to [[_COMMUNITY_Akıllı Motor (İndirim & Fiyat)]]
- 2 edges to [[_COMMUNITY_Community 59]]
- 2 edges to [[_COMMUNITY_Community 65]]
- 2 edges to [[_COMMUNITY_Merkezi Stok Senkronizasyonu]]
- 2 edges to [[_COMMUNITY_Community 54]]
- 1 edge to [[_COMMUNITY_Community 77]]
- 1 edge to [[_COMMUNITY_Community 108]]

## Top bridge nodes
- [[OrderCreated]] - degree 62, connects to 18 communities
- [[OrderHazirlaniyor]] - degree 50, connects to 18 communities
- [[OrderPicking]] - degree 52, connects to 15 communities
- [[OrderDelivered]] - degree 48, connects to 15 communities
- [[archive.py]] - degree 37, connects to 13 communities