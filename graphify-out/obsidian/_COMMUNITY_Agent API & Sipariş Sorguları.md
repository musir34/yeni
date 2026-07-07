---
type: community
cohesion: 0.04
members: 70
---

# Agent API & Sipariş Sorguları

**Cohesion:** 0.04 - loosely connected
**Members:** 70 nodes

## Members
- [[with_try=0 ile TL dönüşümü kapatılabilir (varsayılan açık).]] - rationale - agent_api.py
- [[Barkod alias kontrolü — asıl barkodu döner.]] - rationale - agent_api.py
- [[Belirli raftaki ürünleri listele.]] - rationale - agent_api.py
- [[Benzersiz model kodlarını listele (product_main_id).]] - rationale - agent_api.py
- [[Birden çok model kodunun maliyetini tek istekte döndürür.      POST agentapiv]] - rationale - agent_api.py
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
- [[Maliyeti girilmiş tüm modelleri sayfalı döndürür (ilk senkronimport için).]] - rationale - agent_api.py
- [[Manuel siparişleri listele.      Query params       - search sipariş no, müşte]] - rationale - agent_api.py
- [[Rafları listele.      Query params       - search raf kodu ile arama       - p]] - rationale - agent_api.py
- [[Sipariş istatistikleri — durumlara göre sayılar.]] - rationale - agent_api.py
- [[Sipariş numarasını tüm tablolarda ara.]] - rationale - agent_api.py
- [[Sipariş objesini dict'e çevir.]] - rationale - agent_api.py
- [[Tek barkod için CentralStock'u raflarla senkronize et.]] - rationale - agent_api.py
- [[Tek barkod stok detayı (merkez + raf bazlı dağılım).]] - rationale - agent_api.py
- [[Tek bir model kodunun güncel maliyetini döndürür.      GET agentapiv1model-c]] - rationale - agent_api.py
- [[Tek sipariş detayını getir (tüm tablolarda arar).]] - rationale - agent_api.py
- [[Tek ürün detayı + stok bilgisi.]] - rationale - agent_api.py
- [[Tüm CentralStock → Product.quantity toplu senkronizasyon.]] - rationale - agent_api.py
- [[Verilen model kodları için {model_id {cost_usd, cost_try, has_cost}} döndür.]] - rationale - agent_api.py
- [[X-Agent-Key header kontrolü.]] - rationale - agent_api.py
- [[_degisim_to_dict()]] - code - agent_api.py
- [[_find_order_across_tables()]] - code - agent_api.py
- [[_maliyet_payload()]] - code - agent_api.py
- [[_maliyet_rate()]] - code - agent_api.py
- [[_order_to_dict()]] - code - agent_api.py
- [[_product_to_dict()]] - code - agent_api.py
- [[_want_try()]] - code - agent_api.py
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
- [[model_cost_batch()]] - code - agent_api.py
- [[model_cost_list()]] - code - agent_api.py
- [[model_cost_single()]] - code - agent_api.py
- [[order_stats()]] - code - agent_api.py
- [[require_agent_key()]] - code - agent_api.py
- [[shelf_products()]] - code - agent_api.py
- [[sync_all_stock()]] - code - agent_api.py
- [[sync_stock()]] - code - agent_api.py
- [[update_exchange_status()]] - code - agent_api.py
- [[verify_stock_integrity()]] - code - stock_management.py
- [[Ürün objesini dict'e çevir.]] - rationale - agent_api.py
- [[Ürünleri listele.      Query params       - search barkod, başlık, model kodu]] - rationale - agent_api.py
- [[İade taleplerini listele.      Query params       - status filtre       - sear]] - rationale - agent_api.py
- [[İstenmişse güncel USDTL kurunu getir (10 dk cache'li).]] - rationale - agent_api.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Agent_API__Sipari_Sorgular
SORT file.name ASC
```

## Connections to other communities
- 10 edges to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 6 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 5 edges to [[_COMMUNITY_Kasa & Gelir-Gider]]
- 5 edges to [[_COMMUNITY_Ana Kasa Defteri]]
- 4 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 4 edges to [[_COMMUNITY_Community 38]]
- 3 edges to [[_COMMUNITY_Manuel Sipariş Oluşturma]]
- 2 edges to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 2 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 2 edges to [[_COMMUNITY_Community 93]]
- 2 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 2 edges to [[_COMMUNITY_Community 59]]
- 2 edges to [[_COMMUNITY_Community 44]]
- 2 edges to [[_COMMUNITY_Maliyet Fişi & Tedarikçi]]
- 2 edges to [[_COMMUNITY_Stok Senkron API]]
- 1 edge to [[_COMMUNITY_Community 50]]
- 1 edge to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 1 edge to [[_COMMUNITY_Community 49]]
- 1 edge to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 1 edge to [[_COMMUNITY_Raf Sistemi & Etiket]]
- 1 edge to [[_COMMUNITY_Community 64]]

## Top bridge nodes
- [[agent_api.py]] - degree 86, connects to 20 communities
- [[verify_stock_integrity()]] - degree 7, connects to 3 communities
- [[_degisim_to_dict()]] - degree 7, connects to 1 community
- [[_maliyet_payload()]] - degree 6, connects to 1 community
- [[_maliyet_rate()]] - degree 6, connects to 1 community