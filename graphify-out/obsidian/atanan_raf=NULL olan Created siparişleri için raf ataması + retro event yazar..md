---
source_file: "order_audit_routes.py"
type: "rationale"
community: "Sipariş Denetim Kaydı (Audit Log)"
location: "L478"
tags:
  - graphify/rationale
  - graphify/EXTRACTED
  - community/Sipari_Denetim_Kayd_Audit_Log
---

# atanan_raf=NULL olan Created siparişleri için raf ataması + retro event yazar.

## Connections
- [[backfill()]] - `rationale_for` [EXTRACTED]

#graphify/rationale #graphify/EXTRACTED #community/Sipari_Denetim_Kayd_Audit_Log