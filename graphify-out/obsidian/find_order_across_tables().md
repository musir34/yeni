---
source_file: "archive.py"
type: "code"
community: "E-posta Bildirimleri"
location: "L57"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/E-posta_Bildirimleri
---

# find_order_across_tables()

## Connections
- [[OrderCancelled]] - `indirect_call` [INFERRED]
- [[OrderCreated]] - `indirect_call` [INFERRED]
- [[OrderDelivered]] - `indirect_call` [INFERRED]
- [[OrderHazirlaniyor]] - `indirect_call` [INFERRED]
- [[OrderPicking]] - `indirect_call` [INFERRED]
- [[OrderShipped]] - `indirect_call` [INFERRED]
- [[Siparişi tablolarda arar Created, Picking, Shipped, Delivered, Cancelled     Bu]] - `rationale_for` [EXTRACTED]
- [[archive.py]] - `contains` [EXTRACTED]
- [[archive_an_order()]] - `calls` [EXTRACTED]
- [[change_order_status()]] - `calls` [EXTRACTED]
- [[confirm_packing()]] - `calls` [EXTRACTED]
- [[order_cancellation()]] - `calls` [EXTRACTED]
- [[update_service.py]] - `imports` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/E-posta_Bildirimleri