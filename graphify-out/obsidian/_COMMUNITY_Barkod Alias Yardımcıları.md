---
type: community
cohesion: 0.08
members: 30
---

# Barkod Alias Yardımcıları

**Cohesion:** 0.08 - loosely connected
**Members:** 30 nodes

## Members
- [[Barkod girildiğinde ürünün hangi raflarda olduğunu döndürür.     Sadece adet  0]] - rationale - raf_sistemi.py
- [[Birden fazla barkod için CentralStock'u senkronize eder.]] - rationale - stock_management.py
- [[Raf kodunun sistemde olup olmadığını kontrol eder.     🔧 = ve  karakterleri]] - rationale - raf_sistemi.py
- [[Rafları 3 katmanlı bir yapıda döndürür. Frontend'in artık path'lere ihtiyacı olm]] - rationale - raf_sistemi.py
- [[Seçili rafları toplu olarak siler.      - Ana raf kodu verilirse (örn 'Z') o an]] - rationale - raf_sistemi.py
- [[Tek barkod için CentralStock'u raflarla senkronize et.]] - rationale - agent_api.py
- [[Tek bir barkod için CentralStock'u raflardaki toplamla senkronize eder.      Arg]] - rationale - stock_management.py
- [[Verilen raf koduna göre anlık olarak QR kod resmi oluşturur ve döndürür.]] - rationale - raf_sistemi.py
- [[api_get_raf_stoklari()]] - code - raf_sistemi.py
- [[barkod_ara()]] - code - raf_sistemi.py
- [[check_raf_var_mi()]] - code - raf_sistemi.py
- [[generate_barcode_etiket()]] - code - raf_sistemi.py
- [[generate_qr_etiket()]] - code - raf_sistemi.py
- [[qrcode_with_text()]] - code - raf_sistemi.py
- [[raf_form_sayfasi()]] - code - raf_sistemi.py
- [[raf_gruplu_liste()]] - code - raf_sistemi.py
- [[raf_kademeli_liste()]] - code - raf_sistemi.py
- [[raf_listesi_api()]] - code - raf_sistemi.py
- [[raf_olustur_api()]] - code - raf_sistemi.py
- [[raf_sil()]] - code - raf_sistemi.py
- [[raf_sistemi.py]] - code - raf_sistemi.py
- [[raf_stok_guncelle()]] - code - raf_sistemi.py
- [[raf_stok_listesi()]] - code - raf_sistemi.py
- [[raf_urun_sil()]] - code - raf_sistemi.py
- [[raf_yonetimi()]] - code - raf_sistemi.py
- [[stok_form()]] - code - raf_sistemi.py
- [[sync_central_stock()]] - code - stock_management.py
- [[sync_multiple_barcodes()]] - code - stock_management.py
- [[sync_stock()]] - code - agent_api.py
- [[toplu_raf_sil()]] - code - raf_sistemi.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Barkod_Alias_Yardmclar
SORT file.name ASC
```

## Connections to other communities
- 17 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 6 edges to [[_COMMUNITY_Community 42]]
- 5 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 2 edges to [[_COMMUNITY_Community 76]]
- 2 edges to [[_COMMUNITY_Barkod Üretimi & Sipariş Listesi]]
- 2 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 1 edge to [[_COMMUNITY_Community 66]]
- 1 edge to [[_COMMUNITY_Community 61]]
- 1 edge to [[_COMMUNITY_Community 48]]
- 1 edge to [[_COMMUNITY_Community 67]]
- 1 edge to [[_COMMUNITY_Community 57]]
- 1 edge to [[_COMMUNITY_Community 71]]
- 1 edge to [[_COMMUNITY_Hepsiburada Servisi]]

## Top bridge nodes
- [[raf_sistemi.py]] - degree 32, connects to 8 communities
- [[sync_central_stock()]] - degree 22, connects to 7 communities
- [[sync_multiple_barcodes()]] - degree 8, connects to 2 communities
- [[raf_olustur_api()]] - degree 4, connects to 2 communities
- [[raf_stok_guncelle()]] - degree 4, connects to 2 communities