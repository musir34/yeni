---
type: community
cohesion: 0.09
members: 39
---

# Kimlik Doğrulama & Kullanıcı Yönetimi

**Cohesion:** 0.09 - loosely connected
**Members:** 39 nodes

## Members
- [[.__repr__()_7]] - code - models.py
- [[Barkoda göre güvenli görsel yolu üretir; barkod geçersizse default döner.]] - rationale - degisim.py
- [[Barkodu doğrular; geçersizse None döner. Path traversal koruması.]] - rationale - degisim.py
- [[Benzersiz bir kargo kodu üretir. 10 denemede bulamazsa UUID suffix ekler.]] - rationale - degisim.py
- [[Degisim]] - code - models.py
- [[RafUrun.urun_barkodu üzerinden raflardan 'qty' adet tahsis eder.     Hiçbir comm]] - rationale - degisim.py
- [[Shopify sipariş numarasıyla müşteri bilgilerini ve ürünleri çeker.]] - rationale - degisim.py
- [[Silineniptal edilen değişim kaydının stoğunu raflara geri yazar.     shelf_code]] - rationale - degisim.py
- [[Trendyol API'den sipariş numarasıyla müşteri telefonunu çeker.]] - rationale - degisim.py
- [[Yeni değişim talebi oluştur.      JSON body     {       siparis_no 123456,]] - rationale - agent_api.py
- [[_aggregate_shelf_restore()]] - code - degisim.py
- [[_auto_deliver_old_shipped()]] - code - degisim.py
- [[_fetch_shopify_order_info()]] - code - degisim.py
- [[_fetch_trendyol_phone()]] - code - degisim.py
- [[_get_attr()]] - code - degisim.py
- [[_parse_no_list()]] - code - degisim.py
- [[_resolve_col()]] - code - degisim.py
- [[_safe_barcode()]] - code - degisim.py
- [[_safe_image_url()]] - code - degisim.py
- [[_safe_json_loads()]] - code - degisim.py
- [[_safe_log()]] - code - degisim.py
- [[`degisim_tarihi` 7+ gün öncesi olan 'Kargoya Verildi' kayıtları 'Teslim Edildi']] - rationale - degisim.py
- [[allocate_from_shelves()]] - code - degisim.py
- [[bulk_delete()]] - code - degisim.py
- [[bulk_update_status()]] - code - degisim.py
- [[create_exchange()]] - code - agent_api.py
- [[degisim.py]] - code - degisim.py
- [[degisim_kaydet()]] - code - degisim.py
- [[degisim_talep()]] - code - degisim.py
- [[delete_exchange()_1]] - code - degisim.py
- [[generate_kargo_kodu()]] - code - degisim.py
- [[get_order_details()]] - code - degisim.py
- [[get_product_details()]] - code - degisim.py
- [[raw hem str hem dictlist olabilir; güvenli şekilde deserialize eder.]] - rationale - degisim.py
- [[request.form.getlist veya virgülle ayrılmış string'i temizle.]] - rationale - degisim.py
- [[restore_to_shelves()]] - code - degisim.py
- [[update_status()]] - code - degisim.py
- [[urunler_json'dan (raf_kodu, barcode) → adet toplamı çıkarır.]] - rationale - degisim.py
- [[yeni_degisim_talebi()]] - code - degisim.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Kimlik_Dorulama__Kullanc_Ynetimi
SORT file.name ASC
```

## Connections to other communities
- 8 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 4 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 2 edges to [[_COMMUNITY_Community 66]]
- 2 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 2 edges to [[_COMMUNITY_Community 42]]
- 2 edges to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 1 edge to [[_COMMUNITY_Community 76]]
- 1 edge to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 1 edge to [[_COMMUNITY_Community 61]]
- 1 edge to [[_COMMUNITY_Maliyet Fişi & Tedarikçi]]
- 1 edge to [[_COMMUNITY_Community 57]]
- 1 edge to [[_COMMUNITY_Community 71]]
- 1 edge to [[_COMMUNITY_Kasa & Gelir-Gider]]

## Top bridge nodes
- [[degisim.py]] - degree 39, connects to 10 communities
- [[Degisim]] - degree 9, connects to 4 communities
- [[_safe_log()]] - degree 8, connects to 1 community
- [[get_order_details()]] - degree 6, connects to 1 community
- [[create_exchange()]] - degree 5, connects to 1 community