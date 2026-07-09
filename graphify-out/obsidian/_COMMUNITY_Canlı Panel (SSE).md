---
type: community
cohesion: 0.11
members: 46
---

# Canlı Panel (SSE)

**Cohesion:** 0.11 - loosely connected
**Members:** 46 nodes

## Members
- [[.__repr__()_2]] - code - models.py
- [[Değerin sipariş mi barkod mu olduğunu kabaca tahmin et.]] - rationale - scripts/trace_order.py
- [[Raf bilgisi OLMAYAN barkodların CentralStock.qty'sini 0'a çeker (invariant).]] - rationale - stock_management.py
- [[StockMovement]] - code - models.py
- [[StockMovement (stok hareket defteri) kayıtları — sipariş no veya barkod.      Ta]] - rationale - order_audit_routes.py
- [[StockMovement tablosu yoksa (deploy öncesi) sessizce boş döner.]] - rationale - scripts/trace_order.py
- [[Stok Hareket Defteri (ledger) testleri — TDD.  İzole, dosya-tabanlı sqlite üzeri]] - rationale - tests/test_stock_ledger.py
- [[_audit_detail()]] - code - scripts/trace_order.py
- [[_audit_events()_1]] - code - scripts/trace_order.py
- [[_auto_detect()]] - code - scripts/trace_order.py
- [[_fmt_ts()]] - code - scripts/trace_order.py
- [[_install_sqlite_translate()]] - code - tests/test_stock_ledger.py
- [[_ledger_movements()]] - code - order_audit_routes.py
- [[_movement_events()]] - code - scripts/trace_order.py
- [[_movements()]] - code - tests/test_stock_ledger.py
- [[_print_timeline()]] - code - scripts/trace_order.py
- [[_safe_movements_query()]] - code - scripts/trace_order.py
- [[_seed_shelf()_2]] - code - tests/test_stock_ledger.py
- [[_shelf_qty()_2]] - code - tests/test_stock_ledger.py
- [[create_stock_movement_table.py]] - code - scripts/create_stock_movement_table.py
- [[enforce_shelfless_central_zero()]] - code - stock_management.py
- [[main()_16]] - code - scripts/create_stock_movement_table.py
- [[main()_29]] - code - scripts/trace_order.py
- [[normalize_barcode() PostgreSQL translate() kullanıyor — SQLite UDF ekle.]] - rationale - tests/test_stock_ledger.py
- [[test_apply_created_to_delivered_decrements_stock()]] - code - tests/test_stock_ledger.py
- [[test_apply_hazirlaniyor_to_shipped_decrements()]] - code - tests/test_stock_ledger.py
- [[test_audit_page_lookup_includes_ledger_movements()]] - code - tests/test_stock_ledger.py
- [[test_bg_handler_created_to_delivered_decrements()]] - code - tests/test_stock_ledger.py
- [[test_bg_handler_packed_picking_to_shipped_no_double()]] - code - tests/test_stock_ledger.py
- [[test_bg_handler_unpacked_picking_to_shipped_decrements()]] - code - tests/test_stock_ledger.py
- [[test_created_to_cancelled_no_effect()]] - code - tests/test_stock_ledger.py
- [[test_enforce_shelfless_central_zero()]] - code - tests/test_stock_ledger.py
- [[test_idempotency_no_double_apply()]] - code - tests/test_stock_ledger.py
- [[test_partial_allocation_records_actual_delta()]] - code - tests/test_stock_ledger.py
- [[test_picking_to_cancelled_restores()]] - code - tests/test_stock_ledger.py
- [[test_picking_to_shipped_safety_net_idempotent()]] - code - tests/test_stock_ledger.py
- [[test_picking_to_shipped_unpacked_safety_net_decrements()]] - code - tests/test_stock_ledger.py
- [[test_picking_to_shipped_with_prior_packout_no_double_decrement()]] - code - tests/test_stock_ledger.py
- [[test_record_movement_no_mutate_just_logs()]] - code - tests/test_stock_ledger.py
- [[test_savepoint_preserves_outer_transaction_on_idem_race()]] - code - tests/test_stock_ledger.py
- [[test_stock_ledger.py]] - code - tests/test_stock_ledger.py
- [[test_trace_barcode_shows_movements()]] - code - tests/test_stock_ledger.py
- [[test_trace_order_includes_ledger_and_location()]] - code - tests/test_stock_ledger.py
- [[trace_barcode()]] - code - scripts/trace_order.py
- [[trace_order()]] - code - scripts/trace_order.py
- [[trace_order.py]] - code - scripts/trace_order.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Canl_Panel_SSE
SORT file.name ASC
```

## Connections to other communities
- 16 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 6 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 5 edges to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 5 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 4 edges to [[_COMMUNITY_Community 48]]
- 3 edges to [[_COMMUNITY_Community 76]]
- 2 edges to [[_COMMUNITY_Community 66]]
- 2 edges to [[_COMMUNITY_Community 61]]
- 2 edges to [[_COMMUNITY_Community 67]]
- 2 edges to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 1 edge to [[_COMMUNITY_Community 104]]
- 1 edge to [[_COMMUNITY_Community 105]]
- 1 edge to [[_COMMUNITY_Community 106]]
- 1 edge to [[_COMMUNITY_Community 52]]
- 1 edge to [[_COMMUNITY_Üretim Önerisi & Satış Tahmini]]
- 1 edge to [[_COMMUNITY_Community 69]]
- 1 edge to [[_COMMUNITY_Merkezi Stok Senkronizasyonu]]

## Top bridge nodes
- [[test_stock_ledger.py]] - degree 44, connects to 10 communities
- [[StockMovement]] - degree 26, connects to 9 communities
- [[trace_order.py]] - degree 16, connects to 4 communities
- [[enforce_shelfless_central_zero()]] - degree 6, connects to 3 communities
- [[_seed_shelf()_2]] - degree 21, connects to 2 communities