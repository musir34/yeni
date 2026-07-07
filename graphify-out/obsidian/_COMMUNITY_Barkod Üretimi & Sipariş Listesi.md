---
type: community
cohesion: 0.06
members: 56
---

# Barkod Üretimi & Sipariş Listesi

**Cohesion:** 0.06 - loosely connected
**Members:** 56 nodes

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
- [[Sipariş satırındaki ürün barkodlarını çıkar (details JSON → fallback product_bar]] - rationale - scripts/audit_today_picking.py
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
- [[_parse_barcodes()]] - code - scripts/audit_today_picking.py
- [[_sort_clause()]] - code - order_list_service.py
- [[api_toggle_order_pull()]] - code - order_list_service.py
- [[audit_today_picking.py]] - code - scripts/audit_today_picking.py
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
- [[main()_2]] - code - scripts/audit_today_picking.py
- [[normalize_barcode()_1]] - code - scripts/audit_today_picking.py
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
TABLE source_file, type FROM #community/Barkod_retimi__Sipari_Listesi
SORT file.name ASC
```

## Connections to other communities
- 12 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 9 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 3 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 3 edges to [[_COMMUNITY_Anasayfa Özet & Sayımlar]]
- 2 edges to [[_COMMUNITY_Yeni Sipariş Hazırlama & Toplama]]
- 2 edges to [[_COMMUNITY_Community 50]]
- 2 edges to [[_COMMUNITY_Community 75]]
- 2 edges to [[_COMMUNITY_Manuel Sipariş Oluşturma]]
- 1 edge to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 1 edge to [[_COMMUNITY_Ürün Çekme & Görsel İndirme]]
- 1 edge to [[_COMMUNITY_Community 38]]
- 1 edge to [[_COMMUNITY_Stok Hareket Defteri (Ledger)]]
- 1 edge to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 1 edge to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 1 edge to [[_COMMUNITY_Community 64]]

## Top bridge nodes
- [[order_list_service.py]] - degree 45, connects to 8 communities
- [[audit_today_picking.py]] - degree 11, connects to 7 communities
- [[get_filtered_orders()]] - degree 24, connects to 2 communities
- [[process_order_details()]] - degree 12, connects to 1 community
- [[generate_barcode_data_uri()]] - degree 7, connects to 1 community