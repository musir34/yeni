---
type: community
cohesion: 0.07
members: 50
---

# Raf Yönetimi & Barkod Çakışması

**Cohesion:** 0.07 - loosely connected
**Members:** 50 nodes

## Members
- [[Barkodun altına yazıyı ekler (Pillow 10+ uyumlu).]] - rationale - barcode_utils.py
- [[Benzersiz order_number sayfalaması için aggregate sıralama üretir.]] - rationale - order_list_service.py
- [[Beş tabloda ortak kolonları seçip UNION ALL ile birleştirir.]] - rationale - order_list_service.py
- [[Dosyaya KAYDETMEDEN barkodu base64 (data URI) olarak döndürür.     show_text=Fal]] - rationale - barcode_utils.py
- [[Geciken siparişleri normal listeden ayırmak için order_number kümesi.]] - rationale - order_list_service.py
- [[Geri uyumlu fonksiyon barkodu DOSYAYA kaydeder, STATIC'e göre RELATIF path döne]] - rationale - barcode_utils.py
- [[Her sipariş için 'details' alanını işleyerek ve Product tablosundan sorgu yapara]] - rationale - order_list_service.py
- [[Kargo barkodu için QR kod oluşturur ve statik klasöre kaydeder.]] - rationale - order_list_service.py
- [[Kartlarda hızlı öncelik sinyali için süre durumunu ekle.]] - rationale - order_list_service.py
- [[Query param'dan güvenli sıralama anahtarı döndürür (whitelist).]] - rationale - order_list_service.py
- [[Sayfa başına sipariş adedini güvenli seçeneklerle sınırla.]] - rationale - order_list_service.py
- [[Sıralama anahtarına göre SQLAlchemy order_by ifadesi üretir.      deadline_ seç]] - rationale - order_list_service.py
- [[YeniHazırlanıyorİşleme statülerindeki teslim süresi geçmiş (geciken) siparişle]] - rationale - order_list_service.py
- [[_append_details()]] - code - order_list_service.py
- [[_decorate_order_priority()]] - code - order_list_service.py
- [[_draw_text_below()]] - code - barcode_utils.py
- [[_get_order_pull_enabled()]] - code - order_list_service.py
- [[_get_overdue_orders()]] - code - order_list_service.py
- [[_get_per_page()]] - code - order_list_service.py
- [[_get_sort_key()]] - code - order_list_service.py
- [[_group_sort_clause()]] - code - order_list_service.py
- [[_merge_order_rows()]] - code - order_list_service.py
- [[_normalize_details()]] - code - order_list_service.py
- [[_overdue_order_numbers()]] - code - order_list_service.py
- [[_page_bounds()_1]] - code - order_list_service.py
- [[_sort_clause()]] - code - order_list_service.py
- [[barcode_utils.py]] - code - barcode_utils.py
- [[generate_barcode()]] - code - barcode_utils.py
- [[generate_barcode_data_uri()]] - code - barcode_utils.py
- [[generate_qr_code()_1]] - code - order_list_service.py
- [[get_cancelled_orders()]] - code - order_service.py
- [[get_delivered_orders()]] - code - order_service.py
- [[get_filtered_orders()]] - code - order_list_service.py
- [[get_new_orders()]] - code - order_service.py
- [[get_order_list()]] - code - order_list_service.py
- [[get_picking_orders()]] - code - order_service.py
- [[get_product_image()_1]] - code - order_list_service.py
- [[get_shipped_orders()]] - code - order_service.py
- [[get_union_all_orders()]] - code - order_list_service.py
- [[order_label()]] - code - order_list_service.py
- [[order_list_all()]] - code - order_list_service.py
- [[order_list_cancelled()]] - code - order_list_service.py
- [[order_list_delivered()]] - code - order_list_service.py
- [[order_list_hazirlaniyor()]] - code - order_list_service.py
- [[order_list_new()]] - code - order_list_service.py
- [[order_list_processed()]] - code - order_list_service.py
- [[order_list_service.py]] - code - order_list_service.py
- [[order_list_shipped()]] - code - order_list_service.py
- [[process_order_details()]] - code - order_list_service.py
- [[Ürün barkoduna göre resim dosyası yolunu döndürür.]] - rationale - order_list_service.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Raf_Ynetimi__Barkod_akmas
SORT file.name ASC
```

## Connections to other communities
- 11 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 11 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 3 edges to [[_COMMUNITY_Kasa & Gelir-Gider]]
- 2 edges to [[_COMMUNITY_Yeni Sipariş Hazırlama & Toplama]]
- 2 edges to [[_COMMUNITY_Community 77]]
- 2 edges to [[_COMMUNITY_Hepsiburada Servisi]]
- 1 edge to [[_COMMUNITY_Community 105]]
- 1 edge to [[_COMMUNITY_Hepsiburada Route Katmanı]]
- 1 edge to [[_COMMUNITY_Community 66]]
- 1 edge to [[_COMMUNITY_Community 61]]
- 1 edge to [[_COMMUNITY_Community 71]]

## Top bridge nodes
- [[order_list_service.py]] - degree 45, connects to 8 communities
- [[get_filtered_orders()]] - degree 24, connects to 2 communities
- [[barcode_utils.py]] - degree 6, connects to 2 communities
- [[process_order_details()]] - degree 12, connects to 1 community
- [[generate_barcode_data_uri()]] - degree 7, connects to 1 community