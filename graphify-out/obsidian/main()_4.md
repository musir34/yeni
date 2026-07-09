---
source_file: "scripts/backfill_opening_balance.py"
type: "code"
community: "Community 86"
location: "L132"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Community_86
---

# main()

## Connections
- [[OrderDelivered]] - `indirect_call` [INFERRED]
- [[OrderShipped]] - `indirect_call` [INFERRED]
- [[_load_csv()]] - `calls` [EXTRACTED]
- [[_parse_details()_3]] - `calls` [EXTRACTED]
- [[backfill_opening_balance.py]] - `contains` [EXTRACTED]
- [[run_opening()]] - `calls` [EXTRACTED]
- [[run_reconcile()]] - `calls` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Community_86