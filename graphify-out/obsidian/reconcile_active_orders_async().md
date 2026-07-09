---
source_file: "order_service.py"
type: "code"
community: "Trendyol Sipariş Çekme & Komisyon"
location: "L228"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Trendyol_Sipari_ekme__Komisyon
---

# reconcile_active_orders_async()

## Connections
- [[Aktif tablolarda (YeniHazırlanıyorİşleme Alındı) takılı kalan ESKİ Trendyol]] - `rationale_for` [EXTRACTED]
- [[OrderCreated]] - `indirect_call` [INFERRED]
- [[OrderHazirlaniyor]] - `indirect_call` [INFERRED]
- [[OrderPicking]] - `indirect_call` [INFERRED]
- [[_fetch_order_by_number()]] - `calls` [EXTRACTED]
- [[app.py]] - `imports` [EXTRACTED]
- [[order_service.py]] - `contains` [EXTRACTED]
- [[process_all_orders()]] - `calls` [EXTRACTED]
- [[reconcile_orders_job()]] - `calls` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Trendyol_Sipari_ekme__Komisyon