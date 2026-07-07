---
source_file: "uretim_oneri.py"
type: "code"
community: "Üretim Önerisi & Satış Tahmini"
location: "L229"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/retim_nerisi__Sat_Tahmini
---

# rebuild_daily_sales()

## Connections
- [[DailySales]] - `calls` [EXTRACTED]
- [[DailySalesStatus]] - `calls` [EXTRACTED]
- [[Geçmiş 'days' gününü baştan hesaplar ve o aralığı daily_sales'ta yeniler.     Pr]] - `rationale_for` [EXTRACTED]
- [[OrderCreated]] - `indirect_call` [INFERRED]
- [[OrderDelivered]] - `indirect_call` [INFERRED]
- [[OrderPicking]] - `indirect_call` [INFERRED]
- [[OrderShipped]] - `indirect_call` [INFERRED]
- [[_nightly_rebuild()]] - `calls` [EXTRACTED]
- [[app.py]] - `imports` [EXTRACTED]
- [[daily_sales_rebuild()]] - `calls` [EXTRACTED]
- [[date]] - `calls` [EXTRACTED]
- [[uretim_oneri.py]] - `contains` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/retim_nerisi__Sat_Tahmini