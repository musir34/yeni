---
type: community
cohesion: 0.05
members: 44
---

# Idefix Entegrasyonu

**Cohesion:** 0.05 - loosely connected
**Members:** 44 nodes

## Members
- [[TODO Sipariş durumu güncelleme endpoint'i eklenecek]] - rationale - idefix/idefix_service.py
- [[TODO Sipariş entegrasyonu eklenecek]] - rationale - idefix/idefix_service.py
- [[.__init__()_2]] - code - idefix/idefix_service.py
- [[._get_headers()]] - code - idefix/idefix_service.py
- [[._get_vendor_token()]] - code - idefix/idefix_service.py
- [[.get_all_products()]] - code - idefix/idefix_service.py
- [[.get_orders()]] - code - idefix/idefix_service.py
- [[.get_product_by_barcode()]] - code - idefix/idefix_service.py
- [[.get_products()]] - code - idefix/idefix_service.py
- [[.update_order_status()]] - code - idefix/idefix_service.py
- [[API Key ve Secret'tan vendor token oluşturur (base64 encode)]] - rationale - idefix/idefix_service.py
- [[API istekleri için gerekli header'ları döndürür]] - rationale - idefix/idefix_service.py
- [[Any_1]] - code
- [[Bir ürünün platformlarını getirir]] - rationale - idefix/idefix_routes.py
- [[Bizim ürünlerimizi arama için listeler]] - rationale - idefix/idefix_routes.py
- [[Idefix API entegrasyonu için servis sınıfı]] - rationale - idefix/idefix_service.py
- [[Idefix Satıcı Paneli Route'ları]] - rationale - idefix/idefix_routes.py
- [[Idefix Satıcı Paneli Servisi Satıcı Güllü shoes Satıcı ID 10594]] - rationale - idefix/idefix_service.py
- [[Idefix siparişler sayfası]] - rationale - idefix/idefix_routes.py
- [[Idefix ürün eşleştirme sayfası]] - rationale - idefix/idefix_routes.py
- [[Idefix ürünler sayfası]] - rationale - idefix/idefix_routes.py
- [[Idefix ürünlerini çek ve mevcut ürünlerle eşleştir     Barkod eşleşen ürünlere ']] - rationale - idefix/idefix_routes.py
- [[IdefixService]] - code - idefix/idefix_service.py
- [[Manuel ürün eşleştirme     Idefix barkodunu mevcut bir ürün barkoduna eşleştirir]] - rationale - idefix/idefix_routes.py
- [[Satıcının ürünlerini listeler                  Args             page Sayfa num]] - rationale - idefix/idefix_service.py
- [[Sipariş durumunu günceller]] - rationale - idefix/idefix_service.py
- [[Siparişleri JSON olarak döndürür]] - rationale - idefix/idefix_routes.py
- [[Trendyol'daki fiyatları Idefix'e senkronize et     Eşleşen ürünlerin sale_price]] - rationale - idefix/idefix_routes.py
- [[Tüm ürünleri sayfalama ile çeker                  Args             max_pages M]] - rationale - idefix/idefix_service.py
- [[api_get_platforms()]] - code - idefix/idefix_routes.py
- [[api_match_product()_1]] - code - idefix/idefix_routes.py
- [[api_orders()_2]] - code - idefix/idefix_routes.py
- [[api_our_products()]] - code - idefix/idefix_routes.py
- [[api_products()_1]] - code - idefix/idefix_routes.py
- [[api_search_products()]] - code - idefix/idefix_routes.py
- [[api_sync_prices()]] - code - idefix/idefix_routes.py
- [[api_sync_products()]] - code - idefix/idefix_routes.py
- [[eslestirme()]] - code - idefix/idefix_routes.py
- [[idefix_routes.py]] - code - idefix/idefix_routes.py
- [[idefix_service.py]] - code - idefix/idefix_service.py
- [[index()_6]] - code - idefix/idefix_routes.py
- [[siparisler()]] - code - idefix/idefix_routes.py
- [[urunler()]] - code - idefix/idefix_routes.py
- [[Ürünleri JSON olarak döndürür - eşleşme bilgisiyle birlikte]] - rationale - idefix/idefix_routes.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Idefix_Entegrasyonu
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_Community 65]]
- 2 edges to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 1 edge to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 1 edge to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]

## Top bridge nodes
- [[idefix_routes.py]] - degree 18, connects to 4 communities
- [[idefix_service.py]] - degree 6, connects to 1 community
- [[api_match_product()_1]] - degree 3, connects to 1 community