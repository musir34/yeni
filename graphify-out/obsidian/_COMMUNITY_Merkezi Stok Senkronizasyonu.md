---
type: community
cohesion: 0.09
members: 27
---

# Merkezi Stok Senkronizasyonu

**Cohesion:** 0.09 - loosely connected
**Members:** 27 nodes

## Members
- [[.__init__()_10]] - code - stock_sync/service.py
- [[._get_all_stocks()]] - code - stock_sync/service.py
- [[._get_stocks_by_barcodes()]] - code - stock_sync/service.py
- [[._init_adapters()]] - code - stock_sync/service.py
- [[.cancel_session()]] - code - stock_sync/service.py
- [[.cleanup_stale_sessions()]] - code - stock_sync/service.py
- [[.get_active_sessions()]] - code - stock_sync/service.py
- [[.get_platform_status()]] - code - stock_sync/service.py
- [[.get_reserved_barcodes()]] - code - stock_sync/service.py
- [[.get_reserved_count()]] - code - stock_sync/service.py
- [[.get_session_details()]] - code - stock_sync/service.py
- [[.get_session_history()]] - code - stock_sync/service.py
- [[.run_sync_in_background()]] - code - stock_sync/service.py
- [[Aktif session'ı iptal et_1]] - rationale - stock_sync/service.py
- [[Aktif sync session'larını döndür]] - rationale - stock_sync/service.py
- [[Belirli barkodlar için stokları çek.         Bekleyen siparişlerdeki (OrderCreat]] - rationale - stock_sync/service.py
- [[CentralStock'tan tüm stokları çek.         Bekleyen siparişlerdeki (OrderCreated]] - rationale - stock_sync/service.py
- [[Merkezi Stok Senkronizasyon Servisi          Kullanım         service = StockSy]] - rationale - stock_sync/service.py
- [[Platform adaptörlerini başlat]] - rationale - stock_sync/service.py
- [[Session detaylarını döndür (rezerv bilgisiyle birlikte)]] - rationale - stock_sync/service.py
- [[StockSyncService]] - code - stock_sync/service.py
- [[Sync geçmişini döndür]] - rationale - stock_sync/service.py
- [[Sync'i arka planda çalıştır (blocking olmayan).          Returns             Se]] - rationale - stock_sync/service.py
- [[Toplam rezerv edilen ürün sayısı]] - rationale - stock_sync/service.py
- [[Tüm platformların durumunu döndür]] - rationale - stock_sync/service.py
- [[Yarıda kalmış session'ları temizle.         - 'running' durumunda olup belirli s]] - rationale - stock_sync/service.py
- [[orders_hazirlaniyor tablosundaki siparişlerin details JSON'undan rezerv barkodla]] - rationale - stock_sync/service.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Merkezi_Stok_Senkronizasyonu
SORT file.name ASC
```

## Connections to other communities
- 11 edges to [[_COMMUNITY_Community 36]]
- 3 edges to [[_COMMUNITY_Community 77]]
- 3 edges to [[_COMMUNITY_Community 69]]
- 2 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 2 edges to [[_COMMUNITY_Community 84]]
- 2 edges to [[_COMMUNITY_Ana Kasa Defteri]]
- 2 edges to [[_COMMUNITY_Community 52]]
- 1 edge to [[_COMMUNITY_Community 76]]
- 1 edge to [[_COMMUNITY_E-posta Bildirimleri]]
- 1 edge to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 1 edge to [[_COMMUNITY_Community 61]]
- 1 edge to [[_COMMUNITY_Canlı Panel (SSE)]]

## Top bridge nodes
- [[StockSyncService]] - degree 34, connects to 10 communities
- [[._get_all_stocks()]] - degree 7, connects to 4 communities
- [[._get_stocks_by_barcodes()]] - degree 6, connects to 3 communities
- [[.get_reserved_barcodes()]] - degree 8, connects to 2 communities
- [[.cancel_session()]] - degree 3, connects to 1 community