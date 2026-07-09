---
type: community
cohesion: 0.08
members: 50
---

# Barkod Üretimi & Sipariş Listesi

**Cohesion:** 0.08 - loosely connected
**Members:** 50 nodes

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
TABLE source_file, type FROM #community/Barkod_retimi__Sipari_Listesi
SORT file.name ASC
```

## Connections to other communities
- 10 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 8 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 6 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 5 edges to [[_COMMUNITY_Kasa & Gelir-Gider]]
- 3 edges to [[_COMMUNITY_Community 66]]
- 3 edges to [[_COMMUNITY_Community 67]]
- 3 edges to [[_COMMUNITY_Community 61]]
- 3 edges to [[_COMMUNITY_Yeni Sipariş Hazırlama & Toplama]]
- 2 edges to [[_COMMUNITY_Stok Senkron API]]
- 2 edges to [[_COMMUNITY_Community 76]]
- 2 edges to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 2 edges to [[_COMMUNITY_Community 52]]
- 2 edges to [[_COMMUNITY_Canlı Panel (SSE)]]
- 2 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 2 edges to [[_COMMUNITY_Üretim Önerisi & Satış Tahmini]]
- 2 edges to [[_COMMUNITY_Kimlik Doğrulama & Kullanıcı Yönetimi]]
- 2 edges to [[_COMMUNITY_Ana Kasa Defteri]]
- 2 edges to [[_COMMUNITY_Community 39]]
- 2 edges to [[_COMMUNITY_Hepsiburada Servisi]]
- 1 edge to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 1 edge to [[_COMMUNITY_Community 69]]
- 1 edge to [[_COMMUNITY_Community 71]]

## Top bridge nodes
- [[siparis_hazirla.py]] - degree 32, connects to 11 communities
- [[test_stok_fixleri.py]] - degree 22, connects to 8 communities
- [[Raf]] - degree 19, connects to 7 communities
- [[reset_db()]] - degree 10, connects to 4 communities
- [[get_istanbul_time()]] - degree 14, connects to 3 communities