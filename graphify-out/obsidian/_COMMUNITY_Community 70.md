---
type: community
cohesion: 0.23
members: 14
---

# Community 70

**Cohesion:** 0.23 - loosely connected
**Members:** 14 nodes

## Members
- [[Any_12]] - code
- [[Donmuş veya tutarsız mapping'leri tespit et, eşik aşılırsa mail gönder.]] - rationale - stock_sync/health_monitor.py
- [[Health monitor'ı lokal test et — kimse abone değilse mail atmaz, sadece loglar.]] - rationale - scripts/test_health_monitor.py
- [[Panel stoğu 0 ama Shopify'a son 'var' olarak gönderilmiş ürünleri tespit et.]] - rationale - stock_sync/health_monitor.py
- [[Shopify stok senkronizasyon sağlık izleme.  İki ayrı kontrol   1. check_sync_st]] - rationale - stock_sync/health_monitor.py
- [[Stoksistem uyarıları için jenerik HTML email oluşturur.      summary_rows (et]] - rationale - mail_service.py
- [[Tüm kontrolleri sıra ile çalıştır. Scheduler bunu çağırır.]] - rationale - stock_sync/health_monitor.py
- [[build_alert_email_html()]] - code - mail_service.py
- [[check_oversell_risk()]] - code - stock_sync/health_monitor.py
- [[check_sync_staleness()]] - code - stock_sync/health_monitor.py
- [[health_monitor.py]] - code - stock_sync/health_monitor.py
- [[main()_26]] - code - scripts/test_health_monitor.py
- [[run_all_checks()]] - code - stock_sync/health_monitor.py
- [[test_health_monitor.py]] - code - scripts/test_health_monitor.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_70
SORT file.name ASC
```

## Connections to other communities
- 5 edges to [[_COMMUNITY_Ana Kasa Defteri]]
- 4 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 3 edges to [[_COMMUNITY_Stok Senkron API]]
- 3 edges to [[_COMMUNITY_Community 76]]

## Top bridge nodes
- [[health_monitor.py]] - degree 10, connects to 3 communities
- [[check_sync_staleness()]] - degree 9, connects to 3 communities
- [[check_oversell_risk()]] - degree 8, connects to 3 communities
- [[run_all_checks()]] - degree 9, connects to 1 community
- [[build_alert_email_html()]] - degree 5, connects to 1 community