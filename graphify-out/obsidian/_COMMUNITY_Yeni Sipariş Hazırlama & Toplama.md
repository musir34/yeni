---
type: community
cohesion: 0.10
members: 28
---

# Yeni Sipariş Hazırlama & Toplama

**Cohesion:** 0.10 - loosely connected
**Members:** 28 nodes

## Members
- [[Birden fazla barkod alıp, her biri için QR kod üretip A4 sayfasında     maksimum]] - rationale - qr_utils.py
- [[Hazırlamatoplama kuyruğu = Hazırlanıyor (stoğu teyit edilmiş) siparişler.]] - rationale - new_orders_service.py
- [[Hazırlanıyor (OrderHazirlaniyor — stoğu teyit edilmiş) TÜM tek ürünlü siparişler]] - rationale - new_orders_service.py
- [[Kalan saniyeyi 'X gün Y saat Z dakika' metnine çevirir.]] - rationale - new_orders_service.py
- [[Naive ise IST varsay, aware ise IST'ye çevir.]] - rationale - new_orders_service.py
- [[Okutulan ürün barkoduna ait, 'Hazırlanıyor' (OrderHazirlaniyor — stoğu teyit edi]] - rationale - new_orders_service.py
- [[Toplu ekranda raf+ürün okutarak o raftan fiziksel düşüm yapar (tek-ürünlü).]] - rationale - new_orders_service.py
- [[Türkçe karakterleri ASCII karşılıklarına çevirir.     ç→c, ğ→g, ı→i, ö→o, ş→s, ü]] - rationale - barcode_alias_helper.py
- [[Yeni siparişler için A4 etiket baskı sayfası.     Her etiket sipariş no barkodu]] - rationale - new_orders_service.py
- [[Yeni statüsündeki tek ürünlü siparişleri raf bazında gruplar ve ekranda gösterir]] - rationale - new_orders_service.py
- [[Yeni statüsündeki tek ürünlü siparişleri xlsx olarak indirir.     Sütunlar Mode]] - rationale - new_orders_service.py
- [[_build_shelf_groups()]] - code - new_orders_service.py
- [[_format_remaining()]] - code - new_orders_service.py
- [[_parse_details()]] - code - new_orders_service.py
- [[_prep_model()]] - code - new_orders_service.py
- [[_remaining_seconds()]] - code - new_orders_service.py
- [[_to_ist()]] - code - new_orders_service.py
- [[agreed_delivery_date'e kalan saniye. Tarih yoksa None (sıralamada en sona).]] - rationale - new_orders_service.py
- [[details alanını güvenli şekilde liste olarak döndürür.]] - rationale - new_orders_service.py
- [[generate_qr_labels_pdf()]] - code - qr_utils.py
- [[new_orders_service.py]] - code - new_orders_service.py
- [[pick_order()]] - code - new_orders_service.py
- [[prepare_new_orders()]] - code - new_orders_service.py
- [[prepare_new_orders_excel()]] - code - new_orders_service.py
- [[prepare_new_orders_labels_print()]] - code - new_orders_service.py
- [[qr_utils.py]] - code - qr_utils.py
- [[scan_barcode_to_order()]] - code - new_orders_service.py
- [[strip_turkish()]] - code - barcode_alias_helper.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Yeni_Sipari_Hazrlama__Toplama
SORT file.name ASC
```

## Connections to other communities
- 5 edges to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 3 edges to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 3 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 3 edges to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 2 edges to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 2 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 2 edges to [[_COMMUNITY_Community 54]]
- 1 edge to [[_COMMUNITY_Community 64]]
- 1 edge to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]

## Top bridge nodes
- [[new_orders_service.py]] - degree 27, connects to 9 communities
- [[strip_turkish()]] - degree 5, connects to 2 communities
- [[_build_shelf_groups()]] - degree 8, connects to 1 community
- [[scan_barcode_to_order()]] - degree 8, connects to 1 community
- [[_prep_model()]] - degree 5, connects to 1 community