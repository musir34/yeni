---
source_file: "siparis_hazirla.py"
type: "code"
community: "Barkod Üretimi & Sipariş Listesi"
location: "L14"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Barkod_retimi__Sipari_Listesi
---

# _prep_model()

## Connections
- [[Hazırlama kuyruğu = Hazırlanıyor (stoğu teyit edilmiş) siparişler.]] - `rationale_for` [EXTRACTED]
- [[OrderHazirlaniyor]] - `indirect_call` [INFERRED]
- [[get_home()]] - `calls` [EXTRACTED]
- [[get_queue_orders()]] - `calls` [EXTRACTED]
- [[siparis_hazirla.py]] - `contains` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Barkod_retimi__Sipari_Listesi