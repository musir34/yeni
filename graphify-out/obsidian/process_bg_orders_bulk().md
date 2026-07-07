---
source_file: "order_service.py"
type: "code"
community: "Trendyol Sipariş Çekme & Komisyon"
location: "L727"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Trendyol_Sipari_ekme__Komisyon
---

# process_bg_orders_bulk()

## Connections
- [[OrderCreated]] - `indirect_call` [INFERRED]
- [[OrderDelivered]] - `indirect_call` [INFERRED]
- [[OrderHazirlaniyor]] - `indirect_call` [INFERRED]
- [[OrderPicking]] - `indirect_call` [INFERRED]
- [[OrderShipped]] - `indirect_call` [INFERRED]
- [[_minimal_update_if_needed()]] - `calls` [EXTRACTED]
- [[apply_lifecycle_effect()]] - `calls` [EXTRACTED]
- [[combine_line_items()]] - `calls` [EXTRACTED]
- [[log_event()]] - `calls` [EXTRACTED]
- [[order_service.py]] - `contains` [EXTRACTED]
- [[process_all_orders()]] - `indirect_call` [INFERRED]
- [[test_bg_handler_created_to_delivered_decrements()]] - `calls` [EXTRACTED]
- [[test_bg_handler_packed_picking_to_shipped_no_double()]] - `calls` [EXTRACTED]
- [[test_bg_handler_unpacked_picking_to_shipped_decrements()]] - `calls` [EXTRACTED]
- [[test_stock_ledger.py]] - `imports` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Trendyol_Sipari_ekme__Komisyon