---
source_file: "new_orders_service.py"
type: "code"
community: "Yeni Sipariş Hazırlama & Toplama"
location: "L53"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Yeni_Sipari_Hazrlama__Toplama
---

# _prep_model()

## Connections
- [[Hazırlamatoplama kuyruğu = Hazırlanıyor (stoğu teyit edilmiş) siparişler.]] - `rationale_for` [EXTRACTED]
- [[OrderHazirlaniyor]] - `indirect_call` [INFERRED]
- [[_build_shelf_groups()]] - `calls` [EXTRACTED]
- [[new_orders_service.py]] - `contains` [EXTRACTED]
- [[scan_barcode_to_order()]] - `calls` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Yeni_Sipari_Hazrlama__Toplama