---
type: community
cohesion: 0.05
members: 37
---

# Stok Senkron API

**Cohesion:** 0.05 - loosely connected
**Members:** 37 nodes

## Members
- [[Aktif session'ları döndür]] - rationale - stock_sync/routes.py
- [[Aktif session'ı iptal et]] - rationale - stock_sync/routes.py
- [[Arka planda sync başlat (non-blocking)]] - rationale - stock_sync/routes.py
- [[Belirli barkodları sync et]] - rationale - stock_sync/routes.py
- [[Bir barkodun her platformdaki son sync durumunu döndür.      TrendyolAmazonIde]] - rationale - stock_sync/routes.py
- [[Central Stock listesi sayfası]] - rationale - stock_sync/routes.py
- [[Central Stock listesini Excel olarak indir]] - rationale - stock_sync/routes.py
- [[CentralStock tablosunu raflardaki toplamlarla senkronize et]] - rationale - stock_sync/routes.py
- [[Otomatik senkronizasyon durumunu döndür]] - rationale - stock_sync/routes.py
- [[Platform config'ini döndür]] - rationale - stock_sync/routes.py
- [[Platform durumlarını döndür]] - rationale - stock_sync/routes.py
- [[Session detay sayfası]] - rationale - stock_sync/routes.py
- [[Session detaylarını JSON olarak döndür]] - rationale - stock_sync/routes.py
- [[Stok senkronizasyon dashboard'u]] - rationale - stock_sync/routes.py
- [[Stok tutarlılık kontrolü — CentralStock vs RafUrun karşılaştırması.      Body {]] - rationale - stock_sync/routes.py
- [[Sync geçmişini JSON olarak döndür]] - rationale - stock_sync/routes.py
- [[Tek platforma sync başlat.      Uzun sürebilen platformlar (shopify) gunicorn wo]] - rationale - stock_sync/routes.py
- [[api_active_sessions()]] - code - stock_sync/routes.py
- [[api_auto_sync_status()]] - code - stock_sync/routes.py
- [[api_barcode_history()]] - code - stock_sync/routes.py
- [[api_cancel_session()]] - code - stock_sync/routes.py
- [[api_errors()]] - code - stock_sync/routes.py
- [[api_get_config()]] - code - stock_sync/routes.py
- [[api_history()]] - code - stock_sync/routes.py
- [[api_integrity_check()]] - code - stock_sync/routes.py
- [[api_session_detail()]] - code - stock_sync/routes.py
- [[api_stats()]] - code - stock_sync/routes.py
- [[api_status()]] - code - stock_sync/routes.py
- [[api_sync_background()]] - code - stock_sync/routes.py
- [[api_sync_barcodes()]] - code - stock_sync/routes.py
- [[api_sync_central_stock()]] - code - stock_sync/routes.py
- [[api_sync_platform()]] - code - stock_sync/routes.py
- [[central_stock()]] - code - stock_sync/routes.py
- [[central_stock_export()]] - code - stock_sync/routes.py
- [[dashboard()_1]] - code - stock_sync/routes.py
- [[routes.py]] - code - stock_sync/routes.py
- [[session_detail()]] - code - stock_sync/routes.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Stok_Senkron_API
SORT file.name ASC
```

## Connections to other communities
- 13 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 5 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 4 edges to [[_COMMUNITY_Community 75]]
- 2 edges to [[_COMMUNITY_Community 65]]
- 2 edges to [[_COMMUNITY_Agent API & Sipariş Sorguları]]
- 2 edges to [[_COMMUNITY_Community 102]]
- 2 edges to [[_COMMUNITY_Community 103]]
- 2 edges to [[_COMMUNITY_Community 36]]
- 1 edge to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 1 edge to [[_COMMUNITY_Community 38]]
- 1 edge to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 1 edge to [[_COMMUNITY_Community 76]]
- 1 edge to [[_COMMUNITY_Community 64]]
- 1 edge to [[_COMMUNITY_Manuel Sipariş Oluşturma]]

## Top bridge nodes
- [[routes.py]] - degree 42, connects to 13 communities
- [[api_integrity_check()]] - degree 4, connects to 2 communities
- [[api_sync_platform()]] - degree 4, connects to 2 communities
- [[central_stock()]] - degree 4, connects to 2 communities
- [[central_stock_export()]] - degree 4, connects to 2 communities