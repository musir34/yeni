---
type: community
cohesion: 0.06
members: 66
---

# Sipariş Denetim Kaydı (Audit Log)

**Cohesion:** 0.06 - loosely connected
**Members:** 66 nodes

## Members
- [[.__repr__()_3]] - code - models.py
- [[Any_2]] - code
- [[Birden çok event'i tek transaction'da yazar.      Her dict, ``log_event`` argüma]] - rationale - order_audit.py
- [[Değişikliğin hangi bağlamdan geldiğini tespit et (teşhis için).      Arka plan j]] - rationale - order_audit.py
- [[Operatörün manuel notu ekler (post-mortem için).]] - rationale - order_audit_routes.py
- [[OrderArchived]] - code - models.py
- [[OrderAuditLog]] - code - models.py
- [[OrderReadyToShip]] - code - models.py
- [[SaSession]] - code
- [[Sipariş + stok hareketleri için audit log helper.  Tek noktadan ``log_event(...)]] - rationale - order_audit.py
- [[Sipariş iz sürme paneli.]] - rationale - order_audit_routes.py
- [[Tablo yoksa oluştur (Alembic migration çalışmadıysa yedek).]] - rationale - order_audit.py
- [[Tek event yazar. Asıl akışı kırmaz.      snapshot=True olursa (barcode verildiys]] - rationale - order_audit.py
- [[Toplu pick endpoint + confirm_packing senaryoları — izole sqlite.]] - rationale - tests/test_bulk_pick.py
- [[Verilen barkod için (central_qty, raf_total) anlık değer.]] - rationale - order_audit.py
- [[_audit_events()]] - code - order_audit_routes.py
- [[_bind()]] - code - order_audit.py
- [[_current_user_id()]] - code - order_audit.py
- [[_extract_barcodes()]] - code - order_audit_routes.py
- [[_find_order_records()]] - code - order_audit_routes.py
- [[_flush_audit_after_commit()]] - code - order_audit.py
- [[_install_udf()]] - code - tests/test_bulk_pick.py
- [[_load_user()]] - code - tests/test_bulk_pick.py
- [[_mk_hazirlaniyor()]] - code - tests/test_bulk_pick.py
- [[_origin_source()]] - code - order_audit.py
- [[_parse_details()_1]] - code - order_audit_routes.py
- [[_request_origin()]] - code - order_audit.py
- [[_safe_get()]] - code - order_audit_routes.py
- [[_seed_shelf()]] - code - tests/test_bulk_pick.py
- [[_serialize_order_row()]] - code - order_audit_routes.py
- [[_shelf_qty()]] - code - tests/test_bulk_pick.py
- [[_snapshot()]] - code - order_audit.py
- [[_stock_source_breakdown()]] - code - order_audit_routes.py
- [[_track_central_change()]] - code - order_audit.py
- [[_track_raf_change()_1]] - code - order_audit.py
- [[_user_logs()]] - code - order_audit_routes.py
- [[add_note()]] - code - order_audit_routes.py
- [[app context içinde bir kez çağrılır — event listener'ları kayda geçer.]] - rationale - order_audit.py
- [[atanan_raf=NULL olan Created siparişleri için raf ataması + retro event yazar.]] - rationale - order_audit_routes.py
- [[backfill()]] - code - order_audit_routes.py
- [[client()_1]] - code - tests/test_bulk_pick.py
- [[e()_2]] - code - scripts/trace_batch.py
- [[ensure_table_exists()]] - code - order_audit.py
- [[install_listeners()]] - code - order_audit.py
- [[log_event()]] - code - order_audit.py
- [[log_many()]] - code - order_audit.py
- [[lookup()]] - code - order_audit_routes.py
- [[order_audit.py]] - code - order_audit.py
- [[order_audit_routes.py]] - code - order_audit_routes.py
- [[origin dict'inden audit `source` etiketi türet.]] - rationale - order_audit.py
- [[page()]] - code - order_audit_routes.py
- [[stock_source_data()]] - code - order_audit_routes.py
- [[stock_source_page()]] - code - order_audit_routes.py
- [[test_bulk_pick.py]] - code - tests/test_bulk_pick.py
- [[test_confirm_packing_blocks_unpicked_sequential_off()]] - code - tests/test_bulk_pick.py
- [[test_confirm_packing_packs_picked_without_decrement()]] - code - tests/test_bulk_pick.py
- [[test_confirm_packing_picked_then_sequential_on_no_double()]] - code - tests/test_bulk_pick.py
- [[test_confirm_packing_sequential_lowercase_shelf_decrements()]] - code - tests/test_bulk_pick.py
- [[test_confirm_packing_sequential_zebra_shelf_decrements()]] - code - tests/test_bulk_pick.py
- [[test_pick_endpoint_decrements_and_stamps()]] - code - tests/test_bulk_pick.py
- [[test_pick_endpoint_unknown_order_404()]] - code - tests/test_bulk_pick.py
- [[test_pick_endpoint_wrong_shelf_rejected()]] - code - tests/test_bulk_pick.py
- [[test_pick_endpoint_zebra_shelf_decrements()]] - code - tests/test_bulk_pick.py
- [[test_reserved_excludes_picked_hazirlaniyor()]] - code - tests/test_bulk_pick.py
- [[trace_batch.py]] - code - scripts/trace_batch.py
- [[İstek bağlamı varsa kullanıcı id'sini döner.]] - rationale - order_audit.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Sipari_Denetim_Kayd_Audit_Log
SORT file.name ASC
```

## Connections to other communities
- 19 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 12 edges to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 10 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 6 edges to [[_COMMUNITY_Stok Hareket Defteri (Ledger)]]
- 5 edges to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 5 edges to [[_COMMUNITY_Community 38]]
- 5 edges to [[_COMMUNITY_Community 50]]
- 5 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 4 edges to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 2 edges to [[_COMMUNITY_Agent API & Sipariş Sorguları]]
- 2 edges to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 2 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 2 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 2 edges to [[_COMMUNITY_Merkezi Stok Senkronizasyonu]]
- 1 edge to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 1 edge to [[_COMMUNITY_Community 98]]
- 1 edge to [[_COMMUNITY_Community 54]]
- 1 edge to [[_COMMUNITY_Community 49]]
- 1 edge to [[_COMMUNITY_Yeni Sipariş Hazırlama & Toplama]]
- 1 edge to [[_COMMUNITY_Community 64]]

## Top bridge nodes
- [[order_audit_routes.py]] - degree 40, connects to 10 communities
- [[test_bulk_pick.py]] - degree 36, connects to 10 communities
- [[OrderAuditLog]] - degree 20, connects to 8 communities
- [[order_audit.py]] - degree 18, connects to 4 communities
- [[log_event()]] - degree 15, connects to 3 communities