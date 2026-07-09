---
source_file: "models.py"
type: "code"
community: "E-posta Bildirimleri"
location: "L662"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/E-posta_Bildirimleri
---

# OrderCreated

## Connections
- [[OrderBase]] - `inherits` [EXTRACTED]
- [[StockSyncService]] - `uses` [INFERRED]
- [[_collect_month_orders_unified()]] - `indirect_call` [INFERRED]
- [[_collect_orders_between_strict()]] - `indirect_call` [INFERRED]
- [[_collect_orders_today()]] - `indirect_call` [INFERRED]
- [[_collect_orders_today_strict()]] - `indirect_call` [INFERRED]
- [[_collect_today_order_ids_by_created()]] - `indirect_call` [INFERRED]
- [[_count_orders_between_distinct()]] - `indirect_call` [INFERRED]
- [[_count_orders_today_distinct()]] - `indirect_call` [INFERRED]
- [[_ctx_and_clean()]] - `indirect_call` [INFERRED]
- [[_ctx_clean()]] - `indirect_call` [INFERRED]
- [[_get_order_created_ts()]] - `indirect_call` [INFERRED]
- [[_monthly_aov_like_panel()]] - `indirect_call` [INFERRED]
- [[_order_numbers_created_between()]] - `indirect_call` [INFERRED]
- [[_process_sync_orders_bulk()]] - `indirect_call` [INFERRED]
- [[_status_counts_now()]] - `indirect_call` [INFERRED]
- [[agent_api.py]] - `imports` [EXTRACTED]
- [[all_orders_service.py]] - `imports` [EXTRACTED]
- [[archive.py]] - `imports` [EXTRACTED]
- [[archive_an_order()]] - `indirect_call` [INFERRED]
- [[audit_today_prepared.py]] - `imports` [EXTRACTED]
- [[canli_panel.py]] - `imports` [EXTRACTED]
- [[clear_atanan_raf.py]] - `imports` [EXTRACTED]
- [[commission_update_routes.py]] - `imports` [EXTRACTED]
- [[degisim.py]] - `imports` [EXTRACTED]
- [[find_order_across_tables()]] - `indirect_call` [INFERRED]
- [[find_order_across_tables()_1]] - `indirect_call` [INFERRED]
- [[get_filtered_orders()]] - `indirect_call` [INFERRED]
- [[home.py]] - `imports` [EXTRACTED]
- [[index()_5]] - `indirect_call` [INFERRED]
- [[list_orders()]] - `indirect_call` [INFERRED]
- [[main()_15]] - `indirect_call` [INFERRED]
- [[models.py]] - `contains` [EXTRACTED]
- [[order_audit_routes.py]] - `imports` [EXTRACTED]
- [[order_list_service.py]] - `imports` [EXTRACTED]
- [[order_service.py]] - `imports` [EXTRACTED]
- [[overdue_orders.py]] - `imports` [EXTRACTED]
- [[process_bg_orders_bulk()]] - `indirect_call` [INFERRED]
- [[profit.py]] - `imports` [EXTRACTED]
- [[profit_report()]] - `indirect_call` [INFERRED]
- [[promotion_service.py]] - `imports` [EXTRACTED]
- [[raf_recovery.py]] - `imports` [EXTRACTED]
- [[rebuild_daily_sales()]] - `indirect_call` [INFERRED]
- [[reconcile_active_orders_async()]] - `indirect_call` [INFERRED]
- [[recover_from_archive()]] - `indirect_call` [INFERRED]
- [[recover_missing_raf()]] - `indirect_call` [INFERRED]
- [[reset_db()]] - `indirect_call` [INFERRED]
- [[search_order_by_number()]] - `indirect_call` [INFERRED]
- [[service.py]] - `imports` [EXTRACTED]
- [[siparis_hazirla.py]] - `imports` [EXTRACTED]
- [[stock_alert_service.py]] - `imports` [EXTRACTED]
- [[test_bg_handler_created_to_delivered_decrements()]] - `calls` [EXTRACTED]
- [[test_bulk_pick.py]] - `imports` [EXTRACTED]
- [[test_get_home_atanan_raf_bosaldi()]] - `calls` [EXTRACTED]
- [[test_get_home_stok_yok()]] - `calls` [EXTRACTED]
- [[test_get_home_with_atanan_raf()]] - `calls` [EXTRACTED]
- [[test_savepoint_preserves_outer_transaction_on_idem_race()]] - `calls` [EXTRACTED]
- [[test_stock_ledger.py]] - `imports` [EXTRACTED]
- [[test_stok_fixleri.py]] - `imports` [EXTRACTED]
- [[trace_orders_phantom.py]] - `imports` [EXTRACTED]
- [[update_service.py]] - `imports` [EXTRACTED]
- [[uretim_oneri.py]] - `imports` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/E-posta_Bildirimleri