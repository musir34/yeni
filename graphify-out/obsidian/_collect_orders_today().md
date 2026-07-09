---
source_file: "canli_panel.py"
type: "code"
community: "Üretim Önerisi & Satış Tahmini"
location: "L647"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/retim_nerisi__Sat_Tahmini
---

# _collect_orders_today()

## Connections
- [[0000–2359 TR → Created + Picking + Shipped + Archive     - Dahil edilecek sipa]] - `rationale_for` [EXTRACTED]
- [[Archive]] - `indirect_call` [INFERRED]
- [[OrderCreated]] - `indirect_call` [INFERRED]
- [[OrderDelivered]] - `indirect_call` [INFERRED]
- [[OrderHazirlaniyor]] - `indirect_call` [INFERRED]
- [[OrderPicking]] - `indirect_call` [INFERRED]
- [[OrderShipped]] - `indirect_call` [INFERRED]
- [[_col()]] - `calls` [EXTRACTED]
- [[_collect_today_order_ids_by_created()]] - `calls` [EXTRACTED]
- [[_content_signature()]] - `calls` [EXTRACTED]
- [[_extract_order_id_from_row_or_payload()]] - `calls` [EXTRACTED]
- [[_iter_items_once()]] - `calls` [EXTRACTED]
- [[_log()]] - `calls` [EXTRACTED]
- [[_pick_first()]] - `calls` [EXTRACTED]
- [[_to_number()]] - `calls` [EXTRACTED]
- [[canli_panel.py]] - `contains` [EXTRACTED]
- [[tr_today_bounds_sql()]] - `calls` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/retim_nerisi__Sat_Tahmini