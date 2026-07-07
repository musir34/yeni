---
type: community
cohesion: 0.11
members: 29
---

# Trendyol Sipariş Çekme & Komisyon

**Cohesion:** 0.11 - loosely connected
**Members:** 29 nodes

## Members
- [[Belirli statüdeki TÜM siparişleri Trendyol API'den sayfalama ile çeker.]] - rationale - fix_commissions.py
- [[Bir statü geçişinin stok etkisini ``LIFECYCLE_EFFECTS`` haritasından uygular.]] - rationale - stock_ledger.py
- [[Bu sipariş için ledger'da fiziksel çıkış (pack_outship_out, delta0) var mı.]] - rationale - stock_ledger.py
- [[Komisyonu eksik siparişleri Trendyol API'den tekrar çekip güncelleyen script. Tü]] - rationale - fix_commissions.py
- [[Statü etiketini kanonik forma getirir.      Çağrı yerleri statüyü farklı biçimle]] - rationale - stock_ledger.py
- [[Tek bir lineId ve quantity için (daha eski örnek). Yukarıda 'update_order_status]] - rationale - update_service.py
- [[Tek bir siparişi orderNumber ile çeker. Bu sorgu Trendyol'un varsayılan     ~2 h]] - rationale - order_service.py
- [[_canon_status()]] - code - stock_ledger.py
- [[_fetch_order_by_number()]] - code - order_service.py
- [[_minimal_update_if_needed()]] - code - order_service.py
- [[_order_has_prior_outflow()]] - code - stock_ledger.py
- [[_parse_details()_6]] - code - stock_ledger.py
- [[_process_sync_orders_bulk()]] - code - order_service.py
- [[apply_lifecycle_effect()]] - code - stock_ledger.py
- [[combine_line_items()]] - code - order_service.py
- [[create_order_details()]] - code - order_service.py
- [[details JSON'unu (str veya list) normalize edip {barcode, quantity} listesi döne]] - rationale - stock_ledger.py
- [[fetch_all_orders_by_status()]] - code - fix_commissions.py
- [[fetch_orders_page()]] - code - order_service.py
- [[fetch_trendyol_orders_async()]] - code - order_service.py
- [[fetch_trendyol_orders_route()]] - code - order_service.py
- [[fix_commissions.py]] - code - fix_commissions.py
- [[main()]] - code - fix_commissions.py
- [[order_service.py]] - code - order_service.py
- [[process_all_orders()]] - code - order_service.py
- [[process_bg_orders_bulk()]] - code - order_service.py
- [[safe_float()]] - code - order_service.py
- [[safe_int()]] - code - order_service.py
- [[update_package_to_picking()]] - code - update_service.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Trendyol_Sipari_ekme__Komisyon
SORT file.name ASC
```

## Connections to other communities
- 19 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 16 edges to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 9 edges to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 5 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 4 edges to [[_COMMUNITY_Stok Hareket Defteri (Ledger)]]
- 3 edges to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 2 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 2 edges to [[_COMMUNITY_Community 50]]
- 2 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 2 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 1 edge to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 1 edge to [[_COMMUNITY_Community 77]]
- 1 edge to [[_COMMUNITY_Community 64]]

## Top bridge nodes
- [[order_service.py]] - degree 46, connects to 11 communities
- [[process_bg_orders_bulk()]] - degree 15, connects to 4 communities
- [[_process_sync_orders_bulk()]] - degree 14, connects to 4 communities
- [[apply_lifecycle_effect()]] - degree 13, connects to 2 communities
- [[fix_commissions.py]] - degree 7, connects to 2 communities