---
source_file: "order_service.py"
type: "code"
community: "Trendyol Sipariş Çekme & Komisyon"
location: "L345"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Trendyol_Sipari_ekme__Komisyon
---

# _process_sync_orders_bulk()

## Connections
- [[OrderCancelled]] - `indirect_call` [INFERRED]
- [[OrderCreated]] - `indirect_call` [INFERRED]
- [[OrderHazirlaniyor]] - `indirect_call` [INFERRED]
- [[OrderPicking]] - `indirect_call` [INFERRED]
- [[_minimal_update_if_needed()]] - `calls` [EXTRACTED]
- [[apply_lifecycle_effect()]] - `calls` [EXTRACTED]
- [[combine_line_items()]] - `calls` [EXTRACTED]
- [[log_event()]] - `calls` [EXTRACTED]
- [[log_many()]] - `calls` [EXTRACTED]
- [[log_user_action()_1]] - `calls` [EXTRACTED]
- [[normalize_barcode()]] - `calls` [EXTRACTED]
- [[order_service.py]] - `contains` [EXTRACTED]
- [[process_all_orders()]] - `calls` [EXTRACTED]
- [[recover_missing_raf()]] - `calls` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Trendyol_Sipari_ekme__Komisyon