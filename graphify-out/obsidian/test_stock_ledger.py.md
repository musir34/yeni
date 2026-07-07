---
source_file: "tests/test_stock_ledger.py"
type: "code"
community: "Stok Hareket Defteri (Ledger)"
location: "L1"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Stok_Hareket_Defteri_Ledger
---

# test_stock_ledger.py

## Connections
- [[BarcodeAlias]] - `imports` [EXTRACTED]
- [[CentralStock]] - `imports` [EXTRACTED]
- [[OrderAuditLog]] - `imports` [EXTRACTED]
- [[OrderCancelled]] - `imports` [EXTRACTED]
- [[OrderCreated]] - `imports` [EXTRACTED]
- [[OrderDelivered]] - `imports` [EXTRACTED]
- [[OrderHazirlaniyor]] - `imports` [EXTRACTED]
- [[OrderPicking]] - `imports` [EXTRACTED]
- [[OrderShipped]] - `imports` [EXTRACTED]
- [[Product]] - `imports` [EXTRACTED]
- [[Raf]] - `imports` [EXTRACTED]
- [[RafUrun]] - `imports` [EXTRACTED]
- [[StockMovement]] - `imports` [EXTRACTED]
- [[Stok Hareket Defteri (ledger) testleri — TDD.  İzole, dosya-tabanlı sqlite üzeri]] - `rationale_for` [EXTRACTED]
- [[_ctx_and_clean()]] - `contains` [EXTRACTED]
- [[_install_sqlite_translate()]] - `contains` [EXTRACTED]
- [[_ledger_movements()]] - `imports` [EXTRACTED]
- [[_movements()]] - `contains` [EXTRACTED]
- [[_seed_shelf()_2]] - `contains` [EXTRACTED]
- [[_shelf_qty()_2]] - `contains` [EXTRACTED]
- [[enforce_shelfless_central_zero()]] - `imports` [EXTRACTED]
- [[models.py]] - `imports_from` [EXTRACTED]
- [[process_bg_orders_bulk()]] - `imports` [EXTRACTED]
- [[stock_ledger.py]] - `imports` [EXTRACTED]
- [[test_apply_created_to_delivered_decrements_stock()]] - `contains` [EXTRACTED]
- [[test_apply_hazirlaniyor_to_shipped_decrements()]] - `contains` [EXTRACTED]
- [[test_audit_page_lookup_includes_ledger_movements()]] - `contains` [EXTRACTED]
- [[test_bg_handler_created_to_delivered_decrements()]] - `contains` [EXTRACTED]
- [[test_bg_handler_packed_picking_to_shipped_no_double()]] - `contains` [EXTRACTED]
- [[test_bg_handler_unpacked_picking_to_shipped_decrements()]] - `contains` [EXTRACTED]
- [[test_created_to_cancelled_no_effect()]] - `contains` [EXTRACTED]
- [[test_enforce_shelfless_central_zero()]] - `contains` [EXTRACTED]
- [[test_idempotency_no_double_apply()]] - `contains` [EXTRACTED]
- [[test_partial_allocation_records_actual_delta()]] - `contains` [EXTRACTED]
- [[test_picking_to_cancelled_restores()]] - `contains` [EXTRACTED]
- [[test_picking_to_shipped_safety_net_idempotent()]] - `contains` [EXTRACTED]
- [[test_picking_to_shipped_unpacked_safety_net_decrements()]] - `contains` [EXTRACTED]
- [[test_picking_to_shipped_with_prior_packout_no_double_decrement()]] - `contains` [EXTRACTED]
- [[test_record_movement_no_mutate_just_logs()]] - `contains` [EXTRACTED]
- [[test_savepoint_preserves_outer_transaction_on_idem_race()]] - `contains` [EXTRACTED]
- [[test_trace_barcode_shows_movements()]] - `contains` [EXTRACTED]
- [[test_trace_order_includes_ledger_and_location()]] - `contains` [EXTRACTED]
- [[trace_barcode()]] - `imports` [EXTRACTED]
- [[trace_order()]] - `imports` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Stok_Hareket_Defteri_Ledger