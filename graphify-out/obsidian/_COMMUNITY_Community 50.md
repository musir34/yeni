---
type: community
cohesion: 0.20
members: 18
---

# Community 50

**Cohesion:** 0.20 - loosely connected
**Members:** 18 nodes

## Members
- [[OrderShipped]] - code - models.py
- [[_load_csv()]] - code - scripts/backfill_opening_balance.py
- [[_maybe_write()]] - code - scripts/verify_no_phantom_ledger.py
- [[_parse_details()_3]] - code - scripts/measure_phantom_stock.py
- [[_parse_details()_4]] - code - scripts/reconcile_phantom_ledger.py
- [[_parse_details()_5]] - code - scripts/verify_no_phantom_ledger.py
- [[backfill_opening_balance.py]] - code - scripts/backfill_opening_balance.py
- [[barkod,adet biçimindeki CSV'yi {barcode qty} olarak yükler.]] - rationale - scripts/backfill_opening_balance.py
- [[csv_rows()]] - code - scripts/backfill_opening_balance.py
- [[main()_4]] - code - scripts/backfill_opening_balance.py
- [[main()_23]] - code - scripts/measure_phantom_stock.py
- [[main()_24]] - code - scripts/reconcile_phantom_ledger.py
- [[main()_31]] - code - scripts/verify_no_phantom_ledger.py
- [[measure_phantom_stock.py]] - code - scripts/measure_phantom_stock.py
- [[reconcile_phantom_ledger.py]] - code - scripts/reconcile_phantom_ledger.py
- [[run_opening()]] - code - scripts/backfill_opening_balance.py
- [[run_reconcile()]] - code - scripts/backfill_opening_balance.py
- [[verify_no_phantom_ledger.py]] - code - scripts/verify_no_phantom_ledger.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_50
SORT file.name ASC
```

## Connections to other communities
- 19 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 7 edges to [[_COMMUNITY_Canlı Panel (SSE)]]
- 6 edges to [[_COMMUNITY_Community 38]]
- 6 edges to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 5 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 4 edges to [[_COMMUNITY_Stok Hareket Defteri (Ledger)]]
- 3 edges to [[_COMMUNITY_Anasayfa Özet & Sayımlar]]
- 2 edges to [[_COMMUNITY_Akıllı Motor (İndirim & Fiyat)]]
- 2 edges to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 2 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 2 edges to [[_COMMUNITY_Ana Kasa Defteri]]
- 2 edges to [[_COMMUNITY_Üretim Önerisi & Satış Tahmini]]
- 1 edge to [[_COMMUNITY_Agent API & Sipariş Sorguları]]
- 1 edge to [[_COMMUNITY_Community 80]]
- 1 edge to [[_COMMUNITY_Değişim  İade Talepleri]]
- 1 edge to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 1 edge to [[_COMMUNITY_Community 98]]
- 1 edge to [[_COMMUNITY_Community 62]]

## Top bridge nodes
- [[OrderShipped]] - degree 48, connects to 15 communities
- [[backfill_opening_balance.py]] - degree 12, connects to 4 communities
- [[verify_no_phantom_ledger.py]] - degree 8, connects to 4 communities
- [[reconcile_phantom_ledger.py]] - degree 7, connects to 4 communities
- [[main()_31]] - degree 7, connects to 3 communities