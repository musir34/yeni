---
type: community
cohesion: 0.05
members: 65
---

# Üretim Önerisi & Satış Tahmini

**Cohesion:** 0.05 - loosely connected
**Members:** 65 nodes

## Members
- [[DailySales]] - code - models.py
- [[DailySalesStatus]] - code - models.py
- [[ForecastCache]] - code - models.py
- [[Geçmiş 'days' gününü baştan hesaplar ve o aralığı daily_sales'ta yeniler.     Pr]] - rationale - uretim_oneri.py
- [[Haftalık üretim önerisi (BAŞTAN YAZILDI)      Özellikler       - Model → Renk s]] - rationale - uretim_oneri.py
- [[UretimOneriDefaults]] - code - models.py
- [[UretimOneriWatch]] - code - models.py
- [[UretimPlan]] - code - models.py
- [[UretimSecimPreset]] - code - models.py
- [[_bind_columns_once()]] - code - uretim_oneri.py
- [[_col()_1]] - code - uretim_oneri.py
- [[_daily_series_from_cache()]] - code - uretim_oneri.py
- [[_expand_barcodes_for_models()]] - code - uretim_oneri.py
- [[_expand_barcodes_for_selection()]] - code - uretim_oneri.py
- [[_fetch_product_info_for_barcodes()_1]] - code - uretim_oneri.py
- [[_fetch_sales_totals_from_cache()]] - code - uretim_oneri.py
- [[_fetch_stock_for_barcodes()_1]] - code - uretim_oneri.py
- [[_get_or_create_defaults()]] - code - uretim_oneri.py
- [[_iter_items_once()_2]] - code - uretim_oneri.py
- [[_json_parse()_2]] - code - uretim_oneri.py
- [[_moving_average()]] - code - uretim_oneri.py
- [[_parse_first_image()_1]] - code - uretim_oneri.py
- [[_pick()]] - code - uretim_oneri.py
- [[_reserved_from_active_plans()]] - code - uretim_oneri.py
- [[_run_fcache_loop()]] - code - app.py
- [[_to_list()]] - code - uretim_oneri.py
- [[_to_number()_2]] - code - uretim_oneri.py
- [[ai_forecast_sales()]] - code - uretim_oneri.py
- [[build_cache_for_barcode()]] - code - uretim_oneri.py
- [[bulk_add_models()]] - code - uretim_oneri.py
- [[bulk_delete_plans()]] - code - uretim_oneri.py
- [[create_plan()]] - code - uretim_oneri.py
- [[create_preset()]] - code - uretim_oneri.py
- [[daily_sales_rebuild()]] - code - uretim_oneri.py
- [[daily_sales_status()]] - code - uretim_oneri.py
- [[date]] - code
- [[datetime_3]] - code
- [[delete_plan()]] - code - uretim_oneri.py
- [[delete_plan_via_post()]] - code - uretim_oneri.py
- [[delete_preset()]] - code - uretim_oneri.py
- [[event_type 'create'  'cancel'  'return'     ts event timestamp (EuropeIstan]] - rationale - uretim_oneri.py
- [[forecast_worker_loop()]] - code - uretim_oneri.py
- [[get_defaults()]] - code - uretim_oneri.py
- [[get_model_colors()]] - code - uretim_oneri.py
- [[get_plan()]] - code - uretim_oneri.py
- [[get_preset()]] - code - uretim_oneri.py
- [[get_selected_models()]] - code - uretim_oneri.py
- [[list_plans()]] - code - uretim_oneri.py
- [[list_presets()]] - code - uretim_oneri.py
- [[mark_forecast_dirty()]] - code - uretim_oneri.py
- [[pop_dirty_batch()]] - code - uretim_oneri.py
- [[print_plan()]] - code - uretim_oneri.py
- [[prophet_forecast()]] - code - uretim_oneri.py
- [[rebuild_daily_sales()]] - code - uretim_oneri.py
- [[save_defaults()]] - code - uretim_oneri.py
- [[selection {modelM123,colorsSiyah,Kırmızı}, ...     renk listesi]] - rationale - uretim_oneri.py
- [[toggle_selected_model()]] - code - uretim_oneri.py
- [[toggle_watch()]] - code - uretim_oneri.py
- [[update_daily_from_event()]] - code - uretim_oneri.py
- [[update_plan_status()]] - code - uretim_oneri.py
- [[upsert_daily_sales()]] - code - uretim_oneri.py
- [[uretim_oneri.py]] - code - uretim_oneri.py
- [[uretim_oneri_haftalik_api()]] - code - uretim_oneri.py
- [[uretim_oneri_haftalik_page()]] - code - uretim_oneri.py
- [[uretim_oneri_page()]] - code - uretim_oneri.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/retim_nerisi__Sat_Tahmini
SORT file.name ASC
```

## Connections to other communities
- 10 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 6 edges to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 6 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 2 edges to [[_COMMUNITY_Canlı Panel (SSE)]]
- 2 edges to [[_COMMUNITY_Community 38]]
- 2 edges to [[_COMMUNITY_Community 50]]
- 1 edge to [[_COMMUNITY_Manuel Sipariş Oluşturma]]

## Top bridge nodes
- [[uretim_oneri.py]] - degree 66, connects to 5 communities
- [[rebuild_daily_sales()]] - degree 12, connects to 3 communities
- [[_bind_columns_once()]] - degree 12, connects to 2 communities
- [[date]] - degree 9, connects to 1 community
- [[forecast_worker_loop()]] - degree 5, connects to 1 community