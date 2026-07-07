---
source_file: "models.py"
type: "code"
community: "Sipariş Denetim Kaydı (Audit Log)"
location: "L234"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Sipari_Denetim_Kayd_Audit_Log
---

# OrderAuditLog

## Connections
- [[.__repr__()_3]] - `method` [EXTRACTED]
- [[_audit_events()]] - `indirect_call` [INFERRED]
- [[_ctx_and_clean()]] - `indirect_call` [INFERRED]
- [[_stock_source_breakdown()]] - `indirect_call` [INFERRED]
- [[audit_source_breakdown.py]] - `imports` [EXTRACTED]
- [[audit_today_picking.py]] - `imports` [EXTRACTED]
- [[audit_today_prepared.py]] - `imports` [EXTRACTED]
- [[backfill_opening_balance.py]] - `imports` [EXTRACTED]
- [[log_event()]] - `calls` [EXTRACTED]
- [[log_many()]] - `calls` [EXTRACTED]
- [[measure_phantom_stock.py]] - `imports` [EXTRACTED]
- [[models.py]] - `contains` [EXTRACTED]
- [[order_audit.py]] - `imports` [EXTRACTED]
- [[order_audit_routes.py]] - `imports` [EXTRACTED]
- [[test_bulk_pick.py]] - `imports` [EXTRACTED]
- [[test_picking_service.py]] - `imports` [EXTRACTED]
- [[test_stock_ledger.py]] - `imports` [EXTRACTED]
- [[trace_order.py]] - `imports` [EXTRACTED]
- [[trace_orders_phantom.py]] - `imports` [EXTRACTED]
- [[verify_no_phantom_ledger.py]] - `imports` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Sipari_Denetim_Kayd_Audit_Log