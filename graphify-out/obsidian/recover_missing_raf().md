---
source_file: "raf_recovery.py"
type: "code"
community: "Raf Yönetimi & Barkod Çakışması"
location: "L22"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Raf_Ynetimi__Barkod_akmas
---

# recover_missing_raf()

## Connections
- [[OrderCreated]] - `indirect_call` [INFERRED]
- [[RafUrun]] - `indirect_call` [INFERRED]
- [[_process_sync_orders_bulk()]] - `calls` [EXTRACTED]
- [[``atanan_raf=NULL`` olan Created siparişleri için raf atar + event yazar.      A]] - `rationale_for` [EXTRACTED]
- [[backfill()]] - `calls` [EXTRACTED]
- [[log_many()]] - `calls` [EXTRACTED]
- [[normalize_barcode()]] - `calls` [EXTRACTED]
- [[order_audit_routes.py]] - `imports` [EXTRACTED]
- [[order_service.py]] - `imports` [EXTRACTED]
- [[raf_recovery.py]] - `contains` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Raf_Ynetimi__Barkod_akmas