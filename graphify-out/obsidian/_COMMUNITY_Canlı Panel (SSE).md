---
type: community
cohesion: 0.10
members: 53
---

# Canlı Panel (SSE)

**Cohesion:** 0.10 - loosely connected
**Members:** 53 nodes

## Members
- [[(model, renk) çiftleri için Product tablosundan TÜM barkodbeden satırlarını çek]] - rationale - canli_panel.py
- [[0000–2359 TR → Created + Picking + Shipped + Archive     - Dahil edilecek sipa]] - rationale - canli_panel.py
- [[Aynı listeyi iki kez saymayı engelle (tek anahtar).]] - rationale - canli_panel.py
- [[CreatedPickingShippedDeliveredArchive tablolarında     EuropeIstanbul aralı]] - rationale - canli_panel.py
- [[Mevcut pinfo'daki (model,renk) çiftleri için satışı olmayan barkodları da ekle.]] - rationale - canli_panel.py
- [[None'None''null'boş → default; '₺1.234,56 TL' → 1234.56; '1,234.56' → 1234.56]] - rationale - canli_panel.py
- [[OrderId yoksa, içerik imzası (barcodesizeqty) ile stabil kimlik üret.]] - rationale - canli_panel.py
- [[Sadece seçilen aralıkta OLUŞTURULAN siparişlere ait iadeleri toplar.     Döner]] - rationale - canli_panel.py
- [[Seçilen aralıktaki benzersiz sipariş sayısını döndürür.     source_filter all]] - rationale - canli_panel.py
- [[Siparişleri tarih aralığında topla.          Args         start_ist Başlangıç]] - rationale - canli_panel.py
- [[Verilen order_number kümesi için iade satırlarını barkod bazında toplar.     Dön]] - rationale - canli_panel.py
- [[Yerel dosya sisteminde model_renk.jpgpng ara.]] - rationale - canli_panel.py
- [[_build_cards_between()]] - code - canli_panel.py
- [[_build_cards_from_orders()]] - code - canli_panel.py
- [[_col()]] - code - canli_panel.py
- [[_collect_orders_between_strict()]] - code - canli_panel.py
- [[_collect_orders_today()]] - code - canli_panel.py
- [[_collect_orders_today_strict()]] - code - canli_panel.py
- [[_collect_returns_by_order_created_between()]] - code - canli_panel.py
- [[_collect_returns_for_order_numbers()]] - code - canli_panel.py
- [[_collect_today_order_ids_by_created()]] - code - canli_panel.py
- [[_content_signature()]] - code - canli_panel.py
- [[_count_orders_between_distinct()]] - code - canli_panel.py
- [[_count_orders_today_distinct()]] - code - canli_panel.py
- [[_dt_ms()]] - code - canli_panel.py
- [[_exc()]] - code - canli_panel.py
- [[_expand_with_all_sizes()]] - code - canli_panel.py
- [[_extract_order_id_from_row_or_payload()]] - code - canli_panel.py
- [[_fetch_pinfo_for_model_color_pairs()]] - code - canli_panel.py
- [[_fetch_product_info_for_barcodes()]] - code - canli_panel.py
- [[_fetch_stock_for_barcodes()]] - code - canli_panel.py
- [[_info()]] - code - canli_panel.py
- [[_iter_items_once()]] - code - canli_panel.py
- [[_json_parse()]] - code - canli_panel.py
- [[_local_image_fallback()]] - code - canli_panel.py
- [[_log()]] - code - canli_panel.py
- [[_order_numbers_created_between()]] - code - canli_panel.py
- [[_parse_first_image()]] - code - canli_panel.py
- [[_parse_yyyy_mm_dd()]] - code - canli_panel.py
- [[_pick_first()]] - code - canli_panel.py
- [[_t0()]] - code - canli_panel.py
- [[_to_ist_aware()]] - code - canli_panel.py
- [[_to_number()]] - code - canli_panel.py
- [[_tr_range_from_params()]] - code - canli_panel.py
- [[_want_group_by_barcode()]] - code - canli_panel.py
- [[akis_sse()]] - code - canli_panel.py
- [[canli_panel.py]] - code - canli_panel.py
- [[canli_panel_sayfa()]] - code - canli_panel.py
- [[datetime]] - code
- [[dt - EuropeIstanbul (tz-aware). Naive ise ASSUME_DB_UTC'ye göre tz eklenir.]] - rationale - canli_panel.py
- [[now_tr_str()]] - code - canli_panel.py
- [[ozet_json()]] - code - canli_panel.py
- [[tr_today_bounds_sql()]] - code - canli_panel.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Canl_Panel_SSE
SORT file.name ASC
```

## Connections to other communities
- 38 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 7 edges to [[_COMMUNITY_Community 50]]
- 4 edges to [[_COMMUNITY_Community 44]]
- 3 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 2 edges to [[_COMMUNITY_Community 82]]
- 2 edges to [[_COMMUNITY_Üretim Önerisi & Satış Tahmini]]
- 1 edge to [[_COMMUNITY_Kimlik Doğrulama & Kullanıcı Yönetimi]]
- 1 edge to [[_COMMUNITY_Community 38]]
- 1 edge to [[_COMMUNITY_Community 64]]

## Top bridge nodes
- [[canli_panel.py]] - degree 56, connects to 8 communities
- [[_collect_orders_between_strict()]] - degree 19, connects to 2 communities
- [[_collect_orders_today()]] - degree 17, connects to 2 communities
- [[_collect_orders_today_strict()]] - degree 13, connects to 2 communities
- [[_count_orders_today_distinct()]] - degree 13, connects to 2 communities