---
type: community
cohesion: 0.10
members: 35
---

# Değişim / İade Talepleri

**Cohesion:** 0.10 - loosely connected
**Members:** 35 nodes

## Members
- [[- 'add' Seçilen rafa ürün ekler, CentralStock'u artırır.     - 'renew' Seçilen]] - rationale - stock_management.py
- [[Barkod Alias (Takma Ad) Yönetim Yardımcıları ═══════════════════════════════════]] - rationale - barcode_alias_helper.py
- [[RafUrun]] - code - models.py
- [[Rafa ürün ekle. Body {barkod ABC123, adet 1}]] - rationale - agent_api.py
- [[Raflardan stok tahsis eder ve CentralStock'u günceller.     Race condition önlem]] - rationale - stock_management.py
- [[Sipariş detayları JSON'unu parse edip her ürün için raf stoğunu düşer.     Platf]] - rationale - stock_management.py
- [[Stoğu rafa geri yükler. Sipariş silmeiptal durumlarında kullanılır.     shelf_c]] - rationale - stock_management.py
- [[Verilen barkodla ÖNEK-ÇAKIŞMASI olan ürünleri döndürür.      Tehlikeli ilişki b]] - rationale - barcode_alias_helper.py
- [[Verilen barkodu ana barkoda çevirir.     Eğer alias ise - ana barkod döner]] - rationale - barcode_alias_helper.py
- [[Verilen barkodun bir alias olup olmadığını kontrol eder.          Args]] - rationale - barcode_alias_helper.py
- [[``atanan_raf=NULL`` olan Created siparişleri için raf atar + event yazar.      A]] - rationale - raf_recovery.py
- [[add_product_to_shelf()]] - code - agent_api.py
- [[allocate_from_shelf_and_decrement()]] - code - stock_management.py
- [[allocate_stock_for_order_details()]] - code - stock_management.py
- [[atanan_raf=NULL olan Created siparişleri için raf ataması yapan helper.  Üç yerd]] - rationale - raf_recovery.py
- [[barcode_alias_helper.py]] - code - barcode_alias_helper.py
- [[check_central_zero_alias.py]] - code - scripts/check_central_zero_alias.py
- [[delete_phantom_shelf_rows.py]] - code - scripts/delete_phantom_shelf_rows.py
- [[emit()]] - code - scripts/check_central_zero_alias.py
- [[find_barcode_siblings()]] - code - barcode_alias_helper.py
- [[get_product_details()_3]] - code - stock_management.py
- [[handle_stock_update_from_frontend()]] - code - stock_management.py
- [[is_alias()]] - code - barcode_alias_helper.py
- [[log_failed_items()]] - code - stock_management.py
- [[main()_5]] - code - scripts/check_central_zero_alias.py
- [[move_product_between_shelves()]] - code - agent_api.py
- [[normalize_barcode()]] - code - barcode_alias_helper.py
- [[raf_recovery.py]] - code - raf_recovery.py
- [[recover_missing_raf()]] - code - raf_recovery.py
- [[restore_stock_for_order_details()]] - code - stock_management.py
- [[restore_stock_to_shelf()]] - code - stock_management.py
- [[stock_addition_page()]] - code - stock_management.py
- [[stock_management.py]] - code - stock_management.py
- [[stok_ekle_api()]] - code - raf_sistemi.py
- [[Ürünü bir raftan diğerine taşı. Body {barkod ABC123, hedef_raf B-02-1]] - rationale - agent_api.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Deiim_/_ade_Talepleri
SORT file.name ASC
```

## Connections to other communities
- 17 edges to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 13 edges to [[_COMMUNITY_Community 48]]
- 10 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 10 edges to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 9 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 9 edges to [[_COMMUNITY_Hepsiburada Servisi]]
- 8 edges to [[_COMMUNITY_Community 61]]
- 8 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 8 edges to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 7 edges to [[_COMMUNITY_Yeni Sipariş Hazırlama & Toplama]]
- 7 edges to [[_COMMUNITY_Community 66]]
- 6 edges to [[_COMMUNITY_Community 53]]
- 6 edges to [[_COMMUNITY_Community 76]]
- 6 edges to [[_COMMUNITY_Canlı Panel (SSE)]]
- 5 edges to [[_COMMUNITY_Community 78]]
- 5 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 4 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 4 edges to [[_COMMUNITY_Community 67]]
- 4 edges to [[_COMMUNITY_Community 69]]
- 3 edges to [[_COMMUNITY_Community 42]]
- 2 edges to [[_COMMUNITY_Stok Senkron API]]
- 2 edges to [[_COMMUNITY_Merkezi Stok Senkronizasyonu]]
- 2 edges to [[_COMMUNITY_Kimlik Doğrulama & Kullanıcı Yönetimi]]
- 2 edges to [[_COMMUNITY_Ana Kasa Defteri]]
- 2 edges to [[_COMMUNITY_Community 52]]
- 1 edge to [[_COMMUNITY_Community 104]]
- 1 edge to [[_COMMUNITY_Shopify Admin Servisi]]
- 1 edge to [[_COMMUNITY_Hepsiburada Route Katmanı]]
- 1 edge to [[_COMMUNITY_Community 105]]
- 1 edge to [[_COMMUNITY_Community 86]]
- 1 edge to [[_COMMUNITY_Community 93]]
- 1 edge to [[_COMMUNITY_Community 106]]
- 1 edge to [[_COMMUNITY_Shopify Route Katmanı]]
- 1 edge to [[_COMMUNITY_Community 71]]
- 1 edge to [[_COMMUNITY_Community 57]]
- 1 edge to [[_COMMUNITY_Community 111]]

## Top bridge nodes
- [[RafUrun]] - degree 55, connects to 25 communities
- [[normalize_barcode()]] - degree 58, connects to 16 communities
- [[barcode_alias_helper.py]] - degree 30, connects to 14 communities
- [[stock_management.py]] - degree 30, connects to 13 communities
- [[check_central_zero_alias.py]] - degree 9, connects to 5 communities