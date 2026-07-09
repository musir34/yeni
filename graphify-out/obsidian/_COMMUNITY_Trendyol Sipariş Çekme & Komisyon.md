---
type: community
cohesion: 0.12
members: 29
---

# Trendyol Sipariş Çekme & Komisyon

**Cohesion:** 0.12 - loosely connected
**Members:** 29 nodes

## Members
- [[Aktif tablolarda (YeniHazırlanıyorİşleme Alındı) takılı kalan ESKİ Trendyol]] - rationale - order_service.py
- [[Belirli statüdeki TÜM siparişleri Trendyol API'den sayfalama ile çeker.]] - rationale - fix_commissions.py
- [[Komisyonu eksik siparişleri Trendyol API'den tekrar çekip güncelleyen script. Tü]] - rationale - fix_commissions.py
- [[OrderHazirlaniyor]] - code - models.py
- [[Phantom picking temizligi Terfi sirasinda (sync guard eklenmeden onceki pencere]] - rationale - scripts/cleanup_phantom_picking.py
- [[Tek bir siparişi orderNumber ile çeker. Bu sorgu Trendyol'un varsayılan     ~2 h]] - rationale - order_service.py
- [[_fetch_order_by_number()]] - code - order_service.py
- [[_minimal_update_if_needed()]] - code - order_service.py
- [[_process_sync_orders_bulk()]] - code - order_service.py
- [[add_orders_hazirlaniyor_table.py]] - code - migrations/versions/add_orders_hazirlaniyor_table.py
- [[cleanup_phantom_picking.py]] - code - scripts/cleanup_phantom_picking.py
- [[clear_atanan_raf.py]] - code - scripts/clear_atanan_raf.py
- [[combine_line_items()]] - code - order_service.py
- [[create_order_details()]] - code - order_service.py
- [[downgrade()_1]] - code - migrations/versions/add_orders_hazirlaniyor_table.py
- [[fetch_all_orders_by_status()]] - code - fix_commissions.py
- [[fetch_orders_page()]] - code - order_service.py
- [[fetch_trendyol_orders_async()]] - code - order_service.py
- [[fetch_trendyol_orders_route()]] - code - order_service.py
- [[fix_commissions.py]] - code - fix_commissions.py
- [[main()]] - code - fix_commissions.py
- [[main()_15]] - code - scripts/clear_atanan_raf.py
- [[order_service.py]] - code - order_service.py
- [[process_all_orders()]] - code - order_service.py
- [[process_bg_orders_bulk()]] - code - order_service.py
- [[reconcile_active_orders_async()]] - code - order_service.py
- [[safe_float()]] - code - order_service.py
- [[safe_int()]] - code - order_service.py
- [[upgrade()_1]] - code - migrations/versions/add_orders_hazirlaniyor_table.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Trendyol_Sipari_ekme__Komisyon
SORT file.name ASC
```

## Connections to other communities
- 24 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 11 edges to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 8 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 8 edges to [[_COMMUNITY_Üretim Önerisi & Satış Tahmini]]
- 6 edges to [[_COMMUNITY_Stok Senkron API]]
- 6 edges to [[_COMMUNITY_Kasa & Gelir-Gider]]
- 5 edges to [[_COMMUNITY_Canlı Panel (SSE)]]
- 5 edges to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 4 edges to [[_COMMUNITY_Community 66]]
- 4 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 3 edges to [[_COMMUNITY_Community 67]]
- 3 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 3 edges to [[_COMMUNITY_Community 48]]
- 2 edges to [[_COMMUNITY_Community 41]]
- 2 edges to [[_COMMUNITY_Yeni Sipariş Hazırlama & Toplama]]
- 2 edges to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 2 edges to [[_COMMUNITY_Community 52]]
- 2 edges to [[_COMMUNITY_Community 42]]
- 1 edge to [[_COMMUNITY_Kimlik Doğrulama & Kullanıcı Yönetimi]]
- 1 edge to [[_COMMUNITY_Community 106]]
- 1 edge to [[_COMMUNITY_Community 69]]
- 1 edge to [[_COMMUNITY_Merkezi Stok Senkronizasyonu]]
- 1 edge to [[_COMMUNITY_Maliyet Fişi & Tedarikçi]]
- 1 edge to [[_COMMUNITY_Community 71]]

## Top bridge nodes
- [[OrderHazirlaniyor]] - degree 50, connects to 17 communities
- [[order_service.py]] - degree 46, connects to 12 communities
- [[_process_sync_orders_bulk()]] - degree 14, connects to 5 communities
- [[process_bg_orders_bulk()]] - degree 15, connects to 4 communities
- [[cleanup_phantom_picking.py]] - degree 5, connects to 3 communities