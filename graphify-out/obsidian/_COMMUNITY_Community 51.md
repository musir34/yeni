---
type: community
cohesion: 0.16
members: 18
---

# Community 51

**Cohesion:** 0.16 - loosely connected
**Members:** 18 nodes

## Members
- [[Base Layout Template]] - document - templates/order_list.html
- [[Central Stok Listesi (Central Stock)]] - document - templates/stock_sync/central_stock.html
- [[Kullanıcı İşlem Kayıtları (User Logs)]] - document - templates/user_logs.html
- [[Paketleme Ekranı (Packing Screen)]] - document - templates/siparis_hazirla.html
- [[Sipariş Detay Partial (Order Detail Fragment)]] - document - templates/siparis_detay_partial.html
- [[Sipariş Takip (Order List)]] - document - templates/order_list.html
- [[Sipariş Veri Güncelleme (Update Commission)]] - document - templates/update_commission.html
- [[Sipariş İz Sürme (Order Audit)]] - document - templates/order_audit.html
- [[Stock Change Source Tags (JOBSYSTEMUSERAGENT_APIREQ)]] - rationale - templates/stock_source.html
- [[Stok Kaynak Analizi (Stock Source Analysis)]] - document - templates/stock_source.html
- [[Stok Senkronizasyon Dashboard]] - document - templates/stock_sync/dashboard.html
- [[Yeni Değişim Talebi (New Exchange Request)]] - document - templates/yeni_degisim_talebi.html
- [[Yeni Sipariş (New Order)]] - document - templates/yeni_siparis.html
- [[gullu-common.css shared tokens]] - rationale - templates/order_audit.html
- [[home.home endpoint]] - concept - templates/stock_sync/central_stock.html
- [[stock_sync.central_stock endpoint]] - concept - templates/stock_sync/dashboard.html
- [[stock_sync.dashboard endpoint]] - concept - templates/stock_sync/central_stock.html
- [[İstanbul Timezone Jinja Filter (ist)]] - rationale - templates/siparis_detay_partial.html

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_51
SORT file.name ASC
```
