---
type: community
cohesion: 0.08
members: 54
---

# Stok Fix Testleri & Yardımcılar

**Cohesion:** 0.08 - loosely connected
**Members:** 54 nodes

## Members
- [['İşleme Alındı' statüsündeki değişimler için mesaj + max saat.     Dönüş (messa]] - rationale - siparis_hazirla.py
- [[Bir ürün için raf listesi ve öneriuyarı bayrakları üretir.      atanan_raf Sip]] - rationale - siparis_hazirla.py
- [[Hava durumu bilgisini formatlanmış string olarak döner]] - rationale - weather_service.py
- [[Hava durumu koduna göre emoji döner     Open-Meteo WMO Weather Codes     https]] - rationale - weather_service.py
- [[Hazırlama kuyruğu = Hazırlanıyor (stoğu teyit edilmiş) siparişler.]] - rationale - siparis_hazirla.py
- [[Kapıda ödeme siparişi mi kontrol et.]] - rationale - siparis_hazirla.py
- [[Naive ise IST varsay, aware ise IST'ye çevir._1]] - rationale - siparis_hazirla.py
- [[Open-Meteo API'den hava durumu verisini çeker     TAMAMEN ÜCRETSİZ - API KEY GER]] - rationale - weather_service.py
- [[Raf]] - code - models.py
- [[Shopify sipariş verisini siparis_hazirla ekranının beklediği formata dönüştürür.]] - rationale - siparis_hazirla.py
- [[Shopify variant barkodu veya SKU'dan panel barkodunu bul.     ShopifyMapping tab]] - rationale - siparis_hazirla.py
- [[Shopify'dan beklemedeki siparişleri çek.     - Ödemesi onaylanmış (PAID) sipariş]] - rationale - siparis_hazirla.py
- [[Stok düzeltmelerinin uçtan uca test scripti.  Test edilen değişiklikler   1) or]] - rationale - scripts/test_stok_fixleri.py
- [[Sıradaki siparişlerin özet bilgilerini döndürür.     Aktif sipariş hariç, en faz]] - rationale - siparis_hazirla.py
- [[Türkiye saati ile tarih formatı]] - rationale - app.py
- [[WMO Weather Code'u Türkçe açıklamaya çevirir     Open-Meteo WMO kodları]] - rationale - weather_service.py
- [[_build_raf_payload()]] - code - siparis_hazirla.py
- [[_fetch_shopify_beklemede_orders()]] - code - siparis_hazirla.py
- [[_install_sqlite_udfs()]] - code - scripts/test_stok_fixleri.py
- [[_is_cod_order()]] - code - siparis_hazirla.py
- [[_prep_model()_1]] - code - siparis_hazirla.py
- [[_resolve_shopify_barcode()]] - code - siparis_hazirla.py
- [[_shopify_order_to_hazirla_format()]] - code - siparis_hazirla.py
- [[calculate_remaining_time()]] - code - siparis_hazirla.py
- [[default_order_data()]] - code - siparis_hazirla.py
- [[expect()]] - code - scripts/test_stok_fixleri.py
- [[fetch_weather_data()]] - code - weather_service.py
- [[format_datetime_filter()]] - code - app.py
- [[format_weather_info()]] - code - weather_service.py
- [[get_archive_warnings()]] - code - siparis_hazirla.py
- [[get_exchange_warnings()]] - code - siparis_hazirla.py
- [[get_home()]] - code - siparis_hazirla.py
- [[get_istanbul_time()]] - code - weather_service.py
- [[get_product_image()_2]] - code - siparis_hazirla.py
- [[get_queue_orders()]] - code - siparis_hazirla.py
- [[get_weather_description_tr()]] - code - weather_service.py
- [[get_weather_icon_emoji()]] - code - weather_service.py
- [[get_weather_info()]] - code - weather_service.py
- [[index()_7]] - code - siparis_hazirla.py
- [[main()_27]] - code - scripts/test_stok_fixleri.py
- [[order_number verilirse o siparişi yükler (manuel mod).     Verilmezse en eski 'C]] - rationale - siparis_hazirla.py
- [[reset_db()]] - code - scripts/test_stok_fixleri.py
- [[siparis_hazirla.py]] - code - siparis_hazirla.py
- [[test_build_raf_payload()]] - code - scripts/test_stok_fixleri.py
- [[test_code_changes_present()]] - code - scripts/test_stok_fixleri.py
- [[test_get_home_atanan_raf_bosaldi()]] - code - scripts/test_stok_fixleri.py
- [[test_get_home_stok_yok()]] - code - scripts/test_stok_fixleri.py
- [[test_get_home_with_atanan_raf()]] - code - scripts/test_stok_fixleri.py
- [[test_stok_fixleri.py]] - code - scripts/test_stok_fixleri.py
- [[test_template_render()]] - code - scripts/test_stok_fixleri.py
- [[to_ist()]] - code - siparis_hazirla.py
- [[weather_service.py]] - code - weather_service.py
- [[Önbellekli hava durumu bilgisini döner     5 dakikada bir güncellenir]] - rationale - weather_service.py
- [[İstanbul saatini döner]] - rationale - weather_service.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Stok_Fix_Testleri__Yardmclar
SORT file.name ASC
```

## Connections to other communities
- 14 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 12 edges to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 10 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 6 edges to [[_COMMUNITY_Anasayfa Özet & Sayımlar]]
- 3 edges to [[_COMMUNITY_Community 38]]
- 3 edges to [[_COMMUNITY_Yeni Sipariş Hazırlama & Toplama]]
- 2 edges to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 2 edges to [[_COMMUNITY_Raf Sistemi & Etiket]]
- 2 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 2 edges to [[_COMMUNITY_Community 54]]
- 2 edges to [[_COMMUNITY_Stok Hareket Defteri (Ledger)]]
- 2 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 2 edges to [[_COMMUNITY_Manuel Sipariş Oluşturma]]
- 1 edge to [[_COMMUNITY_Agent API & Sipariş Sorguları]]
- 1 edge to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 1 edge to [[_COMMUNITY_Community 65]]
- 1 edge to [[_COMMUNITY_Community 64]]
- 1 edge to [[_COMMUNITY_Community 55]]

## Top bridge nodes
- [[Raf]] - degree 19, connects to 8 communities
- [[siparis_hazirla.py]] - degree 32, connects to 7 communities
- [[test_stok_fixleri.py]] - degree 22, connects to 5 communities
- [[reset_db()]] - degree 10, connects to 4 communities
- [[get_istanbul_time()]] - degree 14, connects to 3 communities