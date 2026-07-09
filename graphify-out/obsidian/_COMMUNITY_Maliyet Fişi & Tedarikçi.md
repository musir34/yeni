---
type: community
cohesion: 0.06
members: 51
---

# Maliyet Fişi & Tedarikçi

**Cohesion:** 0.06 - loosely connected
**Members:** 51 nodes

## Members
- [[.__repr__()_8]] - code - models.py
- [[Belirli bir sayfadaki iade taleplerini çeker]] - rationale - claims_service.py
- [[Her çağrıda aynı `db.session`’ı verip otomatik kapatır.]] - rationale - iade_islemleri.py
- [[Order]] - code - models.py
- [[Otomatik retry’lı requests oturumu.]] - rationale - iade_islemleri.py
- [[Return]] - code - models.py
- [[ReturnOrder]] - code - models.py
- [[ReturnOrder & ReturnProduct toplu kaydetmeupsert.]] - rationale - iade_islemleri.py
- [[ReturnProduct]] - code - models.py
- [[Trendyol API'den tüm iade taleplerini asenkron olarak çeker]] - rationale - claims_service.py
- [[Trendyol API'den tüm ürünleri asenkron olarak çeker]] - rationale - product_service.py
- [[Trendyol'dan çekilen iade taleplerini veritabanına kaydeder]] - rationale - claims_service.py
- [[Tüm iade taleplerini listeler]] - rationale - claims_service.py
- [[_get_return_order_or_404()]] - code - iade_islemleri.py
- [[approve_claim()]] - code - claims_service.py
- [[claims_list()]] - code - claims_service.py
- [[claims_service.py]] - code - claims_service.py
- [[datetime_1]] - code
- [[fetch_and_save_daily_returns()]] - code - iade_islemleri.py
- [[fetch_and_save_returns()]] - code - app.py
- [[fetch_claims_page()]] - code - claims_service.py
- [[fetch_data_from_api()]] - code - iade_islemleri.py
- [[fetch_products_page()_1]] - code - product_service.py
- [[fetch_trendyol_claims_async()]] - code - claims_service.py
- [[fetch_trendyol_claims_route()]] - code - claims_service.py
- [[fetch_trendyol_products_async()]] - code - product_service.py
- [[fetch_trendyol_products_route()]] - code - product_service.py
- [[get_brands()]] - code - product_service.py
- [[get_category_attributes()]] - code - product_service.py
- [[get_product_categories()]] - code - product_service.py
- [[get_requests_session()]] - code - iade_islemleri.py
- [[iade_guncelle()]] - code - iade_islemleri.py
- [[iade_islemleri.py]] - code - iade_islemleri.py
- [[iade_listesi()]] - code - iade_islemleri.py
- [[iade_onayla()]] - code - iade_islemleri.py
- [[iade_verileri()]] - code - iade_islemleri.py
- [[is_valid_uuid()]] - code - iade_islemleri.py
- [[log_user_action()]] - code - iade_islemleri.py
- [[process_all_claims()]] - code - claims_service.py
- [[process_all_products()]] - code - product_service.py
- [[product_service.py]] - code - product_service.py
- [[reject_claim()]] - code - claims_service.py
- [[safe_strip()]] - code - iade_islemleri.py
- [[save_to_database()]] - code - iade_islemleri.py
- [[schedule_daily_return_fetch()]] - code - iade_islemleri.py
- [[trendyol_api.py]] - code - trendyol_api.py
- [[update_price_stock()]] - code - product_service.py
- [[with_db_session()]] - code - iade_islemleri.py
- [[İade bilgilerini tutan tablo]] - rationale - models.py
- [[İade talebini onaylar]] - rationale - claims_service.py
- [[İade talebini reddeder]] - rationale - claims_service.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Maliyet_Fii__Tedariki
SORT file.name ASC
```

## Connections to other communities
- 7 edges to [[_COMMUNITY_Community 66]]
- 5 edges to [[_COMMUNITY_Stok Senkron API]]
- 4 edges to [[_COMMUNITY_Üretim Önerisi & Satış Tahmini]]
- 3 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 3 edges to [[_COMMUNITY_Community 71]]
- 3 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 2 edges to [[_COMMUNITY_Community 61]]
- 1 edge to [[_COMMUNITY_Community 41]]
- 1 edge to [[_COMMUNITY_Kimlik Doğrulama & Kullanıcı Yönetimi]]
- 1 edge to [[_COMMUNITY_Hepsiburada Route Katmanı]]
- 1 edge to [[_COMMUNITY_Kasa & Gelir-Gider]]
- 1 edge to [[_COMMUNITY_Community 57]]
- 1 edge to [[_COMMUNITY_Community 42]]
- 1 edge to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 1 edge to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 1 edge to [[_COMMUNITY_Community 46]]
- 1 edge to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]

## Top bridge nodes
- [[trendyol_api.py]] - degree 10, connects to 7 communities
- [[iade_islemleri.py]] - degree 22, connects to 4 communities
- [[ReturnProduct]] - degree 10, connects to 4 communities
- [[ReturnOrder]] - degree 9, connects to 4 communities
- [[product_service.py]] - degree 12, connects to 3 communities