---
type: community
cohesion: 0.09
members: 25
---

# Raf Sistemi & Etiket

**Cohesion:** 0.09 - loosely connected
**Members:** 25 nodes

## Members
- [[Barkod girildiğinde ürünün hangi raflarda olduğunu döndürür.     Sadece adet  0]] - rationale - raf_sistemi.py
- [[Birden fazla barkod için CentralStock'u senkronize eder.]] - rationale - stock_management.py
- [[Raf kodunun sistemde olup olmadığını kontrol eder.     🔧 = ve  karakterleri]] - rationale - raf_sistemi.py
- [[Rafları 3 katmanlı bir yapıda döndürür. Frontend'in artık path'lere ihtiyacı olm]] - rationale - raf_sistemi.py
- [[Seçili rafları toplu olarak siler.      - Ana raf kodu verilirse (örn 'Z') o an]] - rationale - raf_sistemi.py
- [[Verilen raf koduna göre anlık olarak Barkod resmi oluşturur ve döndürür.]] - rationale - raf_sistemi.py
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
- [[raf_stok_listesi()]] - code - raf_sistemi.py
- [[raf_yonetimi()]] - code - raf_sistemi.py
- [[stok_form()]] - code - raf_sistemi.py
- [[sync_multiple_barcodes()]] - code - stock_management.py
- [[toplu_raf_sil()]] - code - raf_sistemi.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Raf_Sistemi__Etiket
SORT file.name ASC
```

## Connections to other communities
- 11 edges to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 5 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 2 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 2 edges to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 1 edge to [[_COMMUNITY_Agent API & Sipariş Sorguları]]
- 1 edge to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 1 edge to [[_COMMUNITY_Community 38]]
- 1 edge to [[_COMMUNITY_Community 64]]

## Top bridge nodes
- [[raf_sistemi.py]] - degree 32, connects to 7 communities
- [[sync_multiple_barcodes()]] - degree 8, connects to 2 communities
- [[raf_olustur_api()]] - degree 4, connects to 2 communities
- [[toplu_raf_sil()]] - degree 4, connects to 1 community
- [[barkod_ara()]] - degree 3, connects to 1 community