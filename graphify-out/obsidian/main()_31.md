---
source_file: "scripts/verify_no_phantom_ledger.py"
type: "code"
community: "E-posta Bildirimleri"
location: "L52"
tags:
  - graphify/code
  - graphify/INFERRED
  - community/E-posta_Bildirimleri
---

# main()

## Connections
- [[CentralStock]] - `indirect_call` [INFERRED]
- [[OrderDelivered]] - `indirect_call` [INFERRED]
- [[OrderShipped]] - `indirect_call` [INFERRED]
- [[_maybe_write()]] - `calls` [EXTRACTED]
- [[_parse_details()_5]] - `calls` [EXTRACTED]
- [[emit()]] - `calls` [INFERRED]
- [[verify_no_phantom_ledger.py]] - `contains` [EXTRACTED]

#graphify/code #graphify/INFERRED #community/E-posta_Bildirimleri