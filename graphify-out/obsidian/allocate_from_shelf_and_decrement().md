---
source_file: "stock_management.py"
type: "code"
community: "Raf Yönetimi & Barkod Çakışması"
location: "L228"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Raf_Ynetimi__Barkod_akmas
---

# allocate_from_shelf_and_decrement()

## Connections
- [[Raflardan stok tahsis eder ve CentralStock'u günceller.     Race condition önlem]] - `rationale_for` [EXTRACTED]
- [[allocate_stock_for_order_details()]] - `calls` [EXTRACTED]
- [[normalize_barcode()]] - `calls` [EXTRACTED]
- [[record_movement()]] - `calls` [EXTRACTED]
- [[siparisler.py]] - `imports` [EXTRACTED]
- [[stock_ledger.py]] - `imports` [EXTRACTED]
- [[stock_management.py]] - `contains` [EXTRACTED]
- [[sync_central_stock()]] - `calls` [EXTRACTED]
- [[yeni_siparis()]] - `calls` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Raf_Ynetimi__Barkod_akmas