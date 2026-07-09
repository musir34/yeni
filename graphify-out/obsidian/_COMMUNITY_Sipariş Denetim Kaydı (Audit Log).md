---
type: community
cohesion: 0.04
members: 60
---

# Sipariş Denetim Kaydı (Audit Log)

**Cohesion:** 0.04 - loosely connected
**Members:** 60 nodes

## Members
- [[Barkod alias kontrolü — asıl barkodu döner.]] - rationale - agent_api.py
- [[Belirli raftaki ürünleri listele.]] - rationale - agent_api.py
- [[Benzersiz model kodlarını listele (product_main_id).]] - rationale - agent_api.py
- [[CentralStock ile RafUrun toplamlarını karşılaştırır, tutarsızlıkları tespit eder]] - rationale - stock_management.py
- [[Değişim durumunu güncelle.      JSON body     {       status Kargoda,]] - rationale - agent_api.py
- [[Değişim istatistikleri.]] - rationale - agent_api.py
- [[Değişim objesini dict'e çevir.]] - rationale - agent_api.py
- [[Değişim taleplerini listele.      Query params       - status Oluşturuldu  Ka]] - rationale - agent_api.py
- [[Finansal özet — ana kasa bakiyesi ve kasa istatistikleri.]] - rationale - agent_api.py
- [[Genel panel özeti — agent'ın hızlıca durum öğrenmesi için.]] - rationale - agent_api.py
- [[Global arama — ürün, sipariş, değişim, iade hepsinde arar.      Query params]] - rationale - agent_api.py
- [[Kasa kategorilerini listele.]] - rationale - agent_api.py
- [[Kasa kayıtlarını listele.      Query params       - tip gelir  gider       -]] - rationale - agent_api.py
- [[Manuel siparişleri listele.      Query params       - search sipariş no, müşte]] - rationale - agent_api.py
- [[Raf ürün adedini güncelle. Body {adet 5}]] - rationale - agent_api.py
- [[Rafları listele.      Query params       - search raf kodu ile arama       - p]] - rationale - agent_api.py
- [[Raftan ürün sil (tamamen kaldır).]] - rationale - agent_api.py
- [[Sipariş istatistikleri — durumlara göre sayılar.]] - rationale - agent_api.py
- [[Sipariş numarasını tüm tablolarda ara.]] - rationale - agent_api.py
- [[Sipariş objesini dict'e çevir.]] - rationale - agent_api.py
- [[Tek barkod stok detayı (merkez + raf bazlı dağılım).]] - rationale - agent_api.py
- [[Tek sipariş detayını getir (tüm tablolarda arar).]] - rationale - agent_api.py
- [[Tek ürün detayı + stok bilgisi.]] - rationale - agent_api.py
- [[Tüm CentralStock → Product.quantity toplu senkronizasyon.]] - rationale - agent_api.py
- [[X-Agent-Key header kontrolü.]] - rationale - agent_api.py
- [[_degisim_to_dict()]] - code - agent_api.py
- [[_find_order_across_tables()]] - code - agent_api.py
- [[_order_to_dict()]] - code - agent_api.py
- [[_product_to_dict()]] - code - agent_api.py
- [[agent_api.py]] - code - agent_api.py
- [[check_barcode_alias()]] - code - agent_api.py
- [[dashboard()]] - code - agent_api.py
- [[delete_exchange()]] - code - agent_api.py
- [[exchange_stats()]] - code - agent_api.py
- [[finance_summary()]] - code - agent_api.py
- [[get_exchange()]] - code - agent_api.py
- [[get_order()]] - code - agent_api.py
- [[get_product()]] - code - agent_api.py
- [[get_return()]] - code - agent_api.py
- [[get_stock()]] - code - agent_api.py
- [[global_search()]] - code - agent_api.py
- [[list_exchanges()]] - code - agent_api.py
- [[list_finance_categories()]] - code - agent_api.py
- [[list_manual_orders()]] - code - agent_api.py
- [[list_models()]] - code - agent_api.py
- [[list_products()]] - code - agent_api.py
- [[list_returns()]] - code - agent_api.py
- [[list_shelves()]] - code - agent_api.py
- [[list_transactions()]] - code - agent_api.py
- [[order_stats()]] - code - agent_api.py
- [[remove_product_from_shelf()]] - code - agent_api.py
- [[require_agent_key()]] - code - agent_api.py
- [[shelf_products()]] - code - agent_api.py
- [[sync_all_stock()]] - code - agent_api.py
- [[update_exchange_status()]] - code - agent_api.py
- [[update_shelf_product_qty()]] - code - agent_api.py
- [[verify_stock_integrity()]] - code - stock_management.py
- [[Ürün objesini dict'e çevir.]] - rationale - agent_api.py
- [[Ürünleri listele.      Query params       - search barkod, başlık, model kodu]] - rationale - agent_api.py
- [[İade taleplerini listele.      Query params       - status filtre       - sear]] - rationale - agent_api.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Sipari_Denetim_Kayd_Audit_Log
SORT file.name ASC
```

## Connections to other communities
- 9 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 7 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 7 edges to [[_COMMUNITY_Community 55]]
- 5 edges to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 4 edges to [[_COMMUNITY_Kimlik Doğrulama & Kullanıcı Yönetimi]]
- 4 edges to [[_COMMUNITY_Hepsiburada Servisi]]
- 3 edges to [[_COMMUNITY_Ürün Çekme & Görsel İndirme]]
- 3 edges to [[_COMMUNITY_Community 54]]
- 3 edges to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 3 edges to [[_COMMUNITY_Maliyet Fişi & Tedarikçi]]
- 2 edges to [[_COMMUNITY_Community 61]]
- 2 edges to [[_COMMUNITY_Community 66]]
- 2 edges to [[_COMMUNITY_Community 76]]
- 2 edges to [[_COMMUNITY_Community 100]]
- 2 edges to [[_COMMUNITY_Shopify Route Katmanı]]
- 1 edge to [[_COMMUNITY_Community 104]]
- 1 edge to [[_COMMUNITY_Community 42]]
- 1 edge to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 1 edge to [[_COMMUNITY_Community 90]]
- 1 edge to [[_COMMUNITY_Community 57]]
- 1 edge to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 1 edge to [[_COMMUNITY_Community 71]]

## Top bridge nodes
- [[agent_api.py]] - degree 86, connects to 21 communities
- [[verify_stock_integrity()]] - degree 7, connects to 3 communities
- [[remove_product_from_shelf()]] - degree 4, connects to 2 communities
- [[update_shelf_product_qty()]] - degree 4, connects to 2 communities
- [[_degisim_to_dict()]] - degree 7, connects to 1 community