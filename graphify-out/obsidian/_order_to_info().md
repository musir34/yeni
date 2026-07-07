---
source_file: "stock_alert_service.py"
type: "code"
community: "E-posta Bildirimleri"
location: "L23"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/E-posta_Bildirimleri
---

# _order_to_info()

## Connections
- [[OrderCreated → mail için sipariş bilgisi (sipariş no, müşteri, ürünler).]] - `rationale_for` [EXTRACTED]
- [[alert_uncovered_orders()]] - `calls` [EXTRACTED]
- [[send_periodic_reminder()]] - `calls` [EXTRACTED]
- [[stock_alert_service.py]] - `contains` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/E-posta_Bildirimleri