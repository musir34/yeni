---
type: community
cohesion: 0.07
members: 49
---

# Stok Fix Testleri & Yardımcılar

**Cohesion:** 0.07 - loosely connected
**Members:** 49 nodes

## Members
- [[.__repr__()_3]] - code - models.py
- [[Any_2]] - code
- [[Birden çok event'i tek transaction'da yazar.      Her dict, ``log_event`` argüma]] - rationale - order_audit.py
- [[Değişikliğin hangi bağlamdan geldiğini tespit et (teşhis için).      Arka plan j]] - rationale - order_audit.py
- [[Operatörün manuel notu ekler (post-mortem için).]] - rationale - order_audit_routes.py
- [[OrderArchived]] - code - models.py
- [[OrderAuditLog]] - code - models.py
- [[OrderReadyToShip]] - code - models.py
- [[SaSession]] - code
- [[Sipariş + stok hareketleri için audit log helper.  Tek noktadan ``log_event(...)]] - rationale - order_audit.py
- [[Sipariş iz sürme paneli.]] - rationale - order_audit_routes.py
- [[Tablo yoksa oluştur (Alembic migration çalışmadıysa yedek).]] - rationale - order_audit.py
- [[Tek event yazar. Asıl akışı kırmaz.      snapshot=True olursa (barcode verildiys]] - rationale - order_audit.py
- [[UserLog]] - code - models.py
- [[Verilen barkod için (central_qty, raf_total) anlık değer.]] - rationale - order_audit.py
- [[_audit_events()]] - code - order_audit_routes.py
- [[_bind()]] - code - order_audit.py
- [[_current_user_id()]] - code - order_audit.py
- [[_extract_barcodes()]] - code - order_audit_routes.py
- [[_find_order_records()]] - code - order_audit_routes.py
- [[_flush_audit_after_commit()]] - code - order_audit.py
- [[_origin_source()]] - code - order_audit.py
- [[_parse_details()_1]] - code - order_audit_routes.py
- [[_request_origin()]] - code - order_audit.py
- [[_safe_get()]] - code - order_audit_routes.py
- [[_serialize_order_row()]] - code - order_audit_routes.py
- [[_snapshot()]] - code - order_audit.py
- [[_stock_source_breakdown()]] - code - order_audit_routes.py
- [[_track_central_change()]] - code - order_audit.py
- [[_track_raf_change()_1]] - code - order_audit.py
- [[_user_logs()]] - code - order_audit_routes.py
- [[add_note()]] - code - order_audit_routes.py
- [[app context içinde bir kez çağrılır — event listener'ları kayda geçer.]] - rationale - order_audit.py
- [[atanan_raf=NULL olan Created siparişleri için raf ataması + retro event yazar.]] - rationale - order_audit_routes.py
- [[backfill()]] - code - order_audit_routes.py
- [[e()_2]] - code - scripts/trace_batch.py
- [[ensure_table_exists()]] - code - order_audit.py
- [[install_listeners()]] - code - order_audit.py
- [[log_event()]] - code - order_audit.py
- [[log_many()]] - code - order_audit.py
- [[lookup()]] - code - order_audit_routes.py
- [[order_audit.py]] - code - order_audit.py
- [[order_audit_routes.py]] - code - order_audit_routes.py
- [[origin dict'inden audit `source` etiketi türet.]] - rationale - order_audit.py
- [[page()]] - code - order_audit_routes.py
- [[stock_source_data()]] - code - order_audit_routes.py
- [[stock_source_page()]] - code - order_audit_routes.py
- [[trace_batch.py]] - code - scripts/trace_batch.py
- [[İstek bağlamı varsa kullanıcı id'sini döner.]] - rationale - order_audit.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Stok_Fix_Testleri__Yardmclar
SORT file.name ASC
```

## Connections to other communities
- 10 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 8 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 7 edges to [[_COMMUNITY_Community 66]]
- 5 edges to [[_COMMUNITY_Canlı Panel (SSE)]]
- 5 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 4 edges to [[_COMMUNITY_Stok Senkron API]]
- 4 edges to [[_COMMUNITY_Community 76]]
- 4 edges to [[_COMMUNITY_Community 61]]
- 3 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 2 edges to [[_COMMUNITY_Community 86]]
- 2 edges to [[_COMMUNITY_Üretim Önerisi & Satış Tahmini]]
- 2 edges to [[_COMMUNITY_Community 57]]
- 2 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 1 edge to [[_COMMUNITY_Community 41]]
- 1 edge to [[_COMMUNITY_Akıllı Motor (İndirim & Fiyat)]]
- 1 edge to [[_COMMUNITY_Community 104]]
- 1 edge to [[_COMMUNITY_Community 105]]
- 1 edge to [[_COMMUNITY_Community 106]]
- 1 edge to [[_COMMUNITY_Community 52]]
- 1 edge to [[_COMMUNITY_Community 67]]
- 1 edge to [[_COMMUNITY_Maliyet Fişi & Tedarikçi]]
- 1 edge to [[_COMMUNITY_Community 42]]
- 1 edge to [[_COMMUNITY_Ana Kasa Defteri]]
- 1 edge to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 1 edge to [[_COMMUNITY_Community 71]]

## Top bridge nodes
- [[order_audit_routes.py]] - degree 40, connects to 11 communities
- [[OrderAuditLog]] - degree 20, connects to 8 communities
- [[UserLog]] - degree 8, connects to 5 communities
- [[order_audit.py]] - degree 18, connects to 4 communities
- [[log_event()]] - degree 15, connects to 3 communities