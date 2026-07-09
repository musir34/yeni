---
source_file: "stock_management.py"
type: "code"
community: "Değişim / İade Talepleri"
location: "L276"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Deiim_/_ade_Talepleri
---

# restore_stock_to_shelf()

## Connections
- [[RafUrun]] - `calls` [EXTRACTED]
- [[Stoğu rafa geri yükler. Sipariş silmeiptal durumlarında kullanılır.     shelf_c]] - `rationale_for` [EXTRACTED]
- [[normalize_barcode()]] - `calls` [EXTRACTED]
- [[record_movement()]] - `calls` [EXTRACTED]
- [[restore_stock_for_order_details()]] - `calls` [EXTRACTED]
- [[siparis_sil()]] - `calls` [EXTRACTED]
- [[siparis_toplu_sil()]] - `calls` [EXTRACTED]
- [[siparisler.py]] - `imports` [EXTRACTED]
- [[stock_ledger.py]] - `imports` [EXTRACTED]
- [[stock_management.py]] - `contains` [EXTRACTED]
- [[sync_central_stock()]] - `calls` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Deiim_/_ade_Talepleri