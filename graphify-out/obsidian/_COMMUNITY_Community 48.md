---
type: community
cohesion: 0.15
members: 19
---

# Community 48

**Cohesion:** 0.15 - loosely connected
**Members:** 19 nodes

## Members
- [[Bir statü geçişinin stok etkisini ``LIFECYCLE_EFFECTS`` haritasından uygular.]] - rationale - stock_ledger.py
- [[Bu sipariş için ledger'da fiziksel çıkış (pack_outship_out, delta0) var mı.]] - rationale - stock_ledger.py
- [[Manuel raf-okutmalı toplama — ortak düşüm yardımcısı.  İki ekran (toplu `pick`]] - rationale - picking_service.py
- [[MovementResult]] - code - stock_ledger.py
- [[Raf kodu normalize — Zebratelefon klavyesi '-' yerine '=''' gönderebilir.]] - rationale - picking_service.py
- [[Statü etiketini kanonik forma getirir.      Çağrı yerleri statüyü farklı biçimle]] - rationale - stock_ledger.py
- [[Stok Hareket Defteri (Ledger) — merkezi stok mutasyon katmanı.  AMAÇ ---- Sipari]] - rationale - stock_ledger.py
- [[Tek bir stok hareketini deftere yazar (ve gerekiyorsa rafı mutasyona uğratır).]] - rationale - stock_ledger.py
- [[Verilen idempotency anahtarıyla bir hareket zaten yazılmış mı.]] - rationale - stock_ledger.py
- [[_canon_status()]] - code - stock_ledger.py
- [[_norm_raf()]] - code - picking_service.py
- [[_order_has_prior_outflow()]] - code - stock_ledger.py
- [[_parse_details()_6]] - code - stock_ledger.py
- [[apply_lifecycle_effect()]] - code - stock_ledger.py
- [[details JSON'unu (str veya list) normalize edip {barcode, quantity} listesi döne]] - rationale - stock_ledger.py
- [[has_movement()]] - code - stock_ledger.py
- [[picking_service.py]] - code - picking_service.py
- [[record_movement()]] - code - stock_ledger.py
- [[stock_ledger.py]] - code - stock_ledger.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_48
SORT file.name ASC
```

## Connections to other communities
- 13 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 4 edges to [[_COMMUNITY_Canlı Panel (SSE)]]
- 3 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 3 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 3 edges to [[_COMMUNITY_Community 67]]
- 3 edges to [[_COMMUNITY_Community 86]]
- 2 edges to [[_COMMUNITY_Community 66]]
- 2 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 1 edge to [[_COMMUNITY_Community 41]]
- 1 edge to [[_COMMUNITY_Barkod Alias Yardımcıları]]

## Top bridge nodes
- [[record_movement()]] - degree 18, connects to 6 communities
- [[apply_lifecycle_effect()]] - degree 13, connects to 4 communities
- [[picking_service.py]] - degree 11, connects to 4 communities
- [[stock_ledger.py]] - degree 17, connects to 3 communities
- [[MovementResult]] - degree 4, connects to 1 community