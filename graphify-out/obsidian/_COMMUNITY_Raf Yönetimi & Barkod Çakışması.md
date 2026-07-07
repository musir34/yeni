---
type: community
cohesion: 0.07
members: 54
---

# Raf Yönetimi & Barkod Çakışması

**Cohesion:** 0.07 - loosely connected
**Members:** 54 nodes

## Members
- [[- 'add' Seçilen rafa ürün ekler, CentralStock'u artırır.     - 'renew' Seçilen]] - rationale - stock_management.py
- [[AJAX isteğinde JSON, normal istekte redirect döner.]] - rationale - update_service.py
- [[Manuel raf-okutmalı toplama — ortak düşüm yardımcısı.  İki ekran (toplu `pick`]] - rationale - picking_service.py
- [[MovementResult]] - code - stock_ledger.py
- [[Raf ürün adedini güncelle. Body {adet 5}]] - rationale - agent_api.py
- [[RafUrun]] - code - models.py
- [[Rafa ürün ekle. Body {barkod ABC123, adet 1}]] - rationale - agent_api.py
- [[Raflardan stok tahsis eder ve CentralStock'u günceller.     Race condition önlem]] - rationale - stock_management.py
- [[Raftan ürün sil (tamamen kaldır).]] - rationale - agent_api.py
- [[Sipariş detayları JSON'unu parse edip her ürün için raf stoğunu düşer.     Platf]] - rationale - stock_management.py
- [[Sipariş detayları JSON'unu parse edip her ürün için stoğu rafa geri yükler.]] - rationale - stock_management.py
- [[Stok Hareket Defteri (Ledger) — merkezi stok mutasyon katmanı.  AMAÇ ---- Sipari]] - rationale - stock_ledger.py
- [[Stoğu rafa geri yükler. Sipariş silmeiptal durumlarında kullanılır.     shelf_c]] - rationale - stock_management.py
- [[Tek bir barkod için CentralStock'u raflardaki toplamla senkronize eder.      Arg]] - rationale - stock_management.py
- [[Tek bir stok hareketini deftere yazar (ve gerekiyorsa rafı mutasyona uğratır).]] - rationale - stock_ledger.py
- [[Trendyol API'den siparişleri asenkron olarak çeker.]] - rationale - update_service.py
- [[Verilen barkodla ÖNEK-ÇAKIŞMASI olan ürünleri döndürür.      Tehlikeli ilişki b]] - rationale - barcode_alias_helper.py
- [[Verilen barkodu ana barkoda çevirir.     Eğer alias ise - ana barkod döner]] - rationale - barcode_alias_helper.py
- [[Verilen idempotency anahtarıyla bir hareket zaten yazılmış mı.]] - rationale - stock_ledger.py
- [[_norm_bc()]] - code - update_service.py
- [[_norm_raf()_1]] - code - update_service.py
- [[_respond()]] - code - update_service.py
- [[``atanan_raf=NULL`` olan Created siparişleri için raf atar + event yazar.      A]] - rationale - raf_recovery.py
- [[add_product_to_shelf()]] - code - agent_api.py
- [[allocate_from_shelf_and_decrement()]] - code - stock_management.py
- [[allocate_stock_for_order_details()]] - code - stock_management.py
- [[atanan_raf=NULL olan Created siparişleri için raf ataması yapan helper.  Üç yerd]] - rationale - raf_recovery.py
- [[confirm_packing()]] - code - update_service.py
- [[delete_phantom_shelf_rows.py]] - code - scripts/delete_phantom_shelf_rows.py
- [[fetch_orders_from_api()]] - code - update_service.py
- [[find_barcode_siblings()]] - code - barcode_alias_helper.py
- [[get_product_details()_3]] - code - stock_management.py
- [[handle_stock_update_from_frontend()]] - code - stock_management.py
- [[has_movement()]] - code - stock_ledger.py
- [[log_failed_items()]] - code - stock_management.py
- [[move_product_between_shelves()]] - code - agent_api.py
- [[normalize_barcode()]] - code - barcode_alias_helper.py
- [[picking_service.py]] - code - picking_service.py
- [[raf_recovery.py]] - code - raf_recovery.py
- [[raf_stok_guncelle()]] - code - raf_sistemi.py
- [[raf_urun_sil()]] - code - raf_sistemi.py
- [[record_movement()]] - code - stock_ledger.py
- [[recover_missing_raf()]] - code - raf_recovery.py
- [[remove_product_from_shelf()]] - code - agent_api.py
- [[restore_stock_for_order_details()]] - code - stock_management.py
- [[restore_stock_to_shelf()]] - code - stock_management.py
- [[stock_addition_page()]] - code - stock_management.py
- [[stock_ledger.py]] - code - stock_ledger.py
- [[stock_management.py]] - code - stock_management.py
- [[stok_ekle_api()]] - code - raf_sistemi.py
- [[sync_central_stock()]] - code - stock_management.py
- [[update_service.py]] - code - update_service.py
- [[update_shelf_product_qty()]] - code - agent_api.py
- [[Ürünü bir raftan diğerine taşı. Body {barkod ABC123, hedef_raf B-02-1]] - rationale - agent_api.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Raf_Ynetimi__Barkod_akmas
SORT file.name ASC
```

## Connections to other communities
- 17 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 16 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 13 edges to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 12 edges to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 12 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 11 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 11 edges to [[_COMMUNITY_Raf Sistemi & Etiket]]
- 10 edges to [[_COMMUNITY_Agent API & Sipariş Sorguları]]
- 10 edges to [[_COMMUNITY_Stok Hareket Defteri (Ledger)]]
- 9 edges to [[_COMMUNITY_Manuel Sipariş Oluşturma]]
- 9 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 8 edges to [[_COMMUNITY_Community 38]]
- 7 edges to [[_COMMUNITY_Community 54]]
- 6 edges to [[_COMMUNITY_Community 50]]
- 5 edges to [[_COMMUNITY_Yeni Sipariş Hazırlama & Toplama]]
- 4 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 4 edges to [[_COMMUNITY_Community 62]]
- 4 edges to [[_COMMUNITY_Community 65]]
- 2 edges to [[_COMMUNITY_Merkezi Stok Senkronizasyonu]]
- 2 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 2 edges to [[_COMMUNITY_Community 64]]
- 1 edge to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 1 edge to [[_COMMUNITY_Shopify Admin Servisi]]
- 1 edge to [[_COMMUNITY_Ürün Çekme & Görsel İndirme]]
- 1 edge to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 1 edge to [[_COMMUNITY_Community 85]]
- 1 edge to [[_COMMUNITY_Community 98]]
- 1 edge to [[_COMMUNITY_Stok Senkron API]]
- 1 edge to [[_COMMUNITY_Community 55]]
- 1 edge to [[_COMMUNITY_Community 102]]
- 1 edge to [[_COMMUNITY_Community 77]]

## Top bridge nodes
- [[RafUrun]] - degree 55, connects to 21 communities
- [[normalize_barcode()]] - degree 58, connects to 14 communities
- [[update_service.py]] - degree 32, connects to 12 communities
- [[stock_management.py]] - degree 30, connects to 10 communities
- [[sync_central_stock()]] - degree 22, connects to 5 communities