---
type: community
cohesion: 0.11
members: 23
---

# Silme & Toplu Yazdırma İşlemleri

**Cohesion:** 0.11 - loosely connected
**Members:** 23 nodes

## Members
- [[AJAX isteğinde JSON, normal istekte redirect döner.]] - rationale - update_service.py
- [[Hatice Göker siparişindeki ürünlerin raf konumlarını kontrol eder.]] - rationale - scripts/check_hatice_raf.py
- [[Shopify Admin API konfigürasyonu. Yeni API client_id + client_secret ile OAuth]] - rationale - shopify_site/shopify_config.py
- [[Shopify Admin GraphQL servis katmanı.]] - rationale - shopify_site/shopify_service.py
- [[Shopify sipariş verisini siparis_hazirla ekranının beklediği formata dönüştürür.]] - rationale - siparis_hazirla.py
- [[Shopify variant barkodu veya SKU'dan panel barkodunu bul.     ShopifyMapping tab]] - rationale - siparis_hazirla.py
- [[Tek bir lineId ve quantity için (daha eski örnek). Yukarıda 'update_order_status]] - rationale - update_service.py
- [[Trendyol API'den siparişleri asenkron olarak çeker.]] - rationale - update_service.py
- [[_norm_bc()]] - code - update_service.py
- [[_norm_raf()_1]] - code - update_service.py
- [[_resolve_shopify_barcode()]] - code - siparis_hazirla.py
- [[_respond()]] - code - update_service.py
- [[_shopify_order_to_hazirla_format()]] - code - siparis_hazirla.py
- [[check_hatice_raf.py]] - code - scripts/check_hatice_raf.py
- [[confirm_packing()]] - code - update_service.py
- [[fetch_orders_from_api()]] - code - update_service.py
- [[main()_7]] - code - scripts/check_hatice_raf.py
- [[resolve_panel_barcode()]] - code - scripts/check_hatice_raf.py
- [[shelf_for()]] - code - scripts/check_hatice_raf.py
- [[shopify_config.py]] - code - shopify_site/shopify_config.py
- [[shopify_service.py]] - code - shopify_site/shopify_service.py
- [[update_package_to_picking()]] - code - update_service.py
- [[update_service.py]] - code - update_service.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Silme__Toplu_Yazdrma_lemleri
SORT file.name ASC
```

## Connections to other communities
- 10 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 6 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 6 edges to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 3 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 3 edges to [[_COMMUNITY_Community 61]]
- 3 edges to [[_COMMUNITY_Ana Kasa Defteri]]
- 3 edges to [[_COMMUNITY_Shopify Admin Servisi]]
- 3 edges to [[_COMMUNITY_Community 39]]
- 2 edges to [[_COMMUNITY_Community 41]]
- 2 edges to [[_COMMUNITY_Kasa & Gelir-Gider]]
- 2 edges to [[_COMMUNITY_Community 69]]
- 2 edges to [[_COMMUNITY_Community 66]]
- 2 edges to [[_COMMUNITY_Idefix Entegrasyonu]]
- 2 edges to [[_COMMUNITY_Community 48]]
- 2 edges to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 2 edges to [[_COMMUNITY_Community 42]]
- 1 edge to [[_COMMUNITY_Stok Senkron API]]
- 1 edge to [[_COMMUNITY_Üretim Önerisi & Satış Tahmini]]
- 1 edge to [[_COMMUNITY_Community 76]]
- 1 edge to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 1 edge to [[_COMMUNITY_Community 71]]
- 1 edge to [[_COMMUNITY_Community 74]]
- 1 edge to [[_COMMUNITY_Community 52]]
- 1 edge to [[_COMMUNITY_Maliyet Fişi & Tedarikçi]]
- 1 edge to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 1 edge to [[_COMMUNITY_Community 57]]

## Top bridge nodes
- [[update_service.py]] - degree 32, connects to 18 communities
- [[shopify_service.py]] - degree 13, connects to 9 communities
- [[shopify_config.py]] - degree 10, connects to 7 communities
- [[check_hatice_raf.py]] - degree 13, connects to 6 communities
- [[confirm_packing()]] - degree 10, connects to 4 communities