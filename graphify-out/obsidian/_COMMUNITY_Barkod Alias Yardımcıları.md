---
type: community
cohesion: 0.09
members: 30
---

# Barkod Alias Yardımcıları

**Cohesion:** 0.09 - loosely connected
**Members:** 30 nodes

## Members
- [[.__repr__()]] - code - models.py
- [[BarcodeAlias]] - code - models.py
- [[Barkod Alias (Takma Ad) Yönetim Yardımcıları ═══════════════════════════════════]] - rationale - barcode_alias_helper.py
- [[Barkod Alias Yönetim Blueprint ═══════════════════════════════════  Bu modül bar]] - rationale - barcode_alias_routes.py
- [[Barkod alias (takma ad) sistemi.     Birden fazla barkod aynı ürünü gösterebilir]] - rationale - models.py
- [[Barkod alias listesi ve yönetim sayfası]] - rationale - barcode_alias_routes.py
- [[Barkodu normalize eder (API)]] - rationale - barcode_alias_routes.py
- [[Bir barkod alias'ı siler.          Args         alias_barcode Silinecek alias]] - rationale - barcode_alias_helper.py
- [[Bir barkod hakkında bilgi döner (API)]] - rationale - barcode_alias_routes.py
- [[Bir barkod hakkında detaylı bilgi döner.          Args         barcode Sorgula]] - rationale - barcode_alias_helper.py
- [[Tüm alias'ları listeler veya belirli bir ana barkoda ait alias'ları getirir.]] - rationale - barcode_alias_helper.py
- [[Verilen barkodun bir alias olup olmadığını kontrol eder.          Args]] - rationale - barcode_alias_helper.py
- [[Yeni alias ekle ve stokları birleştir]] - rationale - barcode_alias_routes.py
- [[Yeni bir barkod alias ekler ve isteğe bağlı olarak stokları birleştirir.]] - rationale - barcode_alias_helper.py
- [[_barcode_snapshot()]] - code - order_audit_routes.py
- [[add_alias()]] - code - barcode_alias_helper.py
- [[add_alias_route()]] - code - barcode_alias_routes.py
- [[api_check_barcode()]] - code - barcode_alias_routes.py
- [[api_normalize()]] - code - barcode_alias_routes.py
- [[barcode_alias_helper.py]] - code - barcode_alias_helper.py
- [[barcode_alias_routes.py]] - code - barcode_alias_routes.py
- [[delete_alias_route()]] - code - barcode_alias_routes.py
- [[diag_real_mismatch.py]] - code - scripts/diag_real_mismatch.py
- [[e()_1]] - code - scripts/diag_real_mismatch.py
- [[get_alias_info()]] - code - barcode_alias_helper.py
- [[get_all_aliases()]] - code - barcode_alias_helper.py
- [[index()_2]] - code - barcode_alias_routes.py
- [[is_alias()]] - code - barcode_alias_helper.py
- [[main()_17]] - code - scripts/diag_real_mismatch.py
- [[remove_alias()]] - code - barcode_alias_helper.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Barkod_Alias_Yardmclar
SORT file.name ASC
```

## Connections to other communities
- 13 edges to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 12 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 5 edges to [[_COMMUNITY_Community 38]]
- 4 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 4 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 3 edges to [[_COMMUNITY_Yeni Sipariş Hazırlama & Toplama]]
- 2 edges to [[_COMMUNITY_Agent API & Sipariş Sorguları]]
- 2 edges to [[_COMMUNITY_Community 62]]
- 2 edges to [[_COMMUNITY_Idefix Entegrasyonu]]
- 1 edge to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 1 edge to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 1 edge to [[_COMMUNITY_E-posta Bildirimleri]]
- 1 edge to [[_COMMUNITY_Raf Sistemi & Etiket]]
- 1 edge to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 1 edge to [[_COMMUNITY_Community 35]]
- 1 edge to [[_COMMUNITY_Community 54]]
- 1 edge to [[_COMMUNITY_Stok Hareket Defteri (Ledger)]]
- 1 edge to [[_COMMUNITY_Community 65]]

## Top bridge nodes
- [[barcode_alias_helper.py]] - degree 30, connects to 10 communities
- [[BarcodeAlias]] - degree 17, connects to 8 communities
- [[diag_real_mismatch.py]] - degree 12, connects to 5 communities
- [[_barcode_snapshot()]] - degree 7, connects to 4 communities
- [[barcode_alias_routes.py]] - degree 17, connects to 3 communities