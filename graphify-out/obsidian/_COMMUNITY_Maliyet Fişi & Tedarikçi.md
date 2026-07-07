---
type: community
cohesion: 0.05
members: 57
---

# Maliyet Fişi & Tedarikçi

**Cohesion:** 0.05 - loosely connected
**Members:** 57 nodes

## Members
- [[Bir modelin tüm maliyet değerlerini getir (kalem + direkt).]] - rationale - siparis_fisi.py
- [[Canlı panelden seçilen kartların satış adetlerine göre     otomatik tedarik sipa]] - rationale - siparis_fisi.py
- [[Kategoriye yeni maliyet kalemi ekle. model_id verilirse modele özel olur.]] - rationale - siparis_fisi.py
- [[Maliyet ana başlıkları Kesim Giderleri, Kalfa Giderleri, vb.]] - rationale - models.py
- [[Maliyet kalemi sil. Şablon kalemler sadece şablon yönetiminden, modele özel kale]] - rationale - siparis_fisi.py
- [[Maliyet kalemleri Astar, Çelik Taban, vb. Alt başlık ile gruplandırılır.     mo]] - rationale - models.py
- [[Maliyet kategorisi sil (alt kalemler cascade silinir).]] - rationale - siparis_fisi.py
- [[Maliyet tablolarını oluştur (yoksa), eksik kolonları ekle.]] - rationale - siparis_fisi.py
- [[Maliyet şablonunu döndür. model_id= verilirse modele özel kalemler de dahil.]] - rationale - siparis_fisi.py
- [[MaliyetKalem]] - code - models.py
- [[MaliyetKategori]] - code - models.py
- [[Maliyeti girilmiş modellerin listesi.]] - rationale - siparis_fisi.py
- [[Model kodlarına karşılık gelen güncel USD birim maliyetini döndürür.     Öncelik]] - rationale - siparis_fisi.py
- [[Modelleri tedarikçi bilgisiyle birlikte listele. Opsiyonel search= ve tedarikc]] - rationale - siparis_fisi.py
- [[SiparisFisi]] - code - models.py
- [[Tedarikci]] - code - models.py
- [[Tedarikci tablosundan tüm tedarikçileri listele.]] - rationale - siparis_fisi.py
- [[Tek bir modelin canlı USD birim maliyetini döndür.]] - rationale - siparis_fisi.py
- [[Varsayılan maliyet kalemlerini oluşturur (sadece tablo boşsa).]] - rationale - siparis_fisi.py
- [[Yeni maliyet kategorisi (başlık) ekle.]] - rationale - siparis_fisi.py
- [[_ensure_maliyet_tables()]] - code - siparis_fisi.py
- [[_parse_or_float_zero()]] - code - siparis_fisi.py
- [[_parse_or_zero()]] - code - siparis_fisi.py
- [[_usd_maliyet_map()]] - code - siparis_fisi.py
- [[api_maliyet_kalem_ekle()]] - code - siparis_fisi.py
- [[api_maliyet_kalem_sil()]] - code - siparis_fisi.py
- [[api_maliyet_kategori_ekle()]] - code - siparis_fisi.py
- [[api_maliyet_kategori_sil()]] - code - siparis_fisi.py
- [[api_maliyet_model_get()]] - code - siparis_fisi.py
- [[api_maliyet_model_listesi()]] - code - siparis_fisi.py
- [[api_maliyet_sablon()]] - code - siparis_fisi.py
- [[api_model_maliyet_tek()]] - code - siparis_fisi.py
- [[api_tedarikci_ekle()]] - code - siparis_fisi.py
- [[api_tedarikci_modeller()]] - code - siparis_fisi.py
- [[api_tedarikcilar()]] - code - siparis_fisi.py
- [[bos_yazdir()]] - code - siparis_fisi.py
- [[generate_and_save_qr_code()]] - code - siparis_fisi.py
- [[get_product_details()_2]] - code - siparis_fisi.py
- [[get_siparis_fisi()]] - code - siparis_fisi.py
- [[get_siparis_fisi_list()]] - code - siparis_fisi.py
- [[group_products_by_model_and_color()_1]] - code - siparis_fisi.py
- [[json_loads_filter()]] - code - siparis_fisi.py
- [[maliyet_fisi_bos()]] - code - siparis_fisi.py
- [[maliyet_fisi_yazdir()]] - code - siparis_fisi.py
- [[mark_as_printed()]] - code - siparis_fisi.py
- [[seed_maliyet_sablonu()]] - code - siparis_fisi.py
- [[siparis_fisi.py]] - code - siparis_fisi.py
- [[siparis_fisi_barkod_yazdir()]] - code - siparis_fisi.py
- [[siparis_fisi_detay()]] - code - siparis_fisi.py
- [[siparis_fisi_listesi()]] - code - siparis_fisi.py
- [[siparis_fisi_olustur()]] - code - siparis_fisi.py
- [[siparis_fisi_sayfasi()]] - code - siparis_fisi.py
- [[siparis_fisi_urunler()]] - code - siparis_fisi.py
- [[sort_variants_by_size()_1]] - code - siparis_fisi.py
- [[tedarik_olustur_from_panel()]] - code - siparis_fisi.py
- [[tedarikci_sayfasi()]] - code - siparis_fisi.py
- [[update_siparis_fisi()]] - code - siparis_fisi.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Maliyet_Fii__Tedariki
SORT file.name ASC
```

## Connections to other communities
- 12 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 6 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 3 edges to [[_COMMUNITY_Community 93]]
- 2 edges to [[_COMMUNITY_Agent API & Sipariş Sorguları]]
- 1 edge to [[_COMMUNITY_Community 64]]

## Top bridge nodes
- [[siparis_fisi.py]] - degree 55, connects to 4 communities
- [[_usd_maliyet_map()]] - degree 7, connects to 1 community
- [[MaliyetKalem]] - degree 5, connects to 1 community
- [[MaliyetKategori]] - degree 5, connects to 1 community
- [[siparis_fisi_olustur()]] - degree 5, connects to 1 community