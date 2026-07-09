---
type: community
cohesion: 0.12
members: 16
---

# Community 58

**Cohesion:** 0.12 - loosely connected
**Members:** 16 nodes

## Members
- [[Kategoriye yeni maliyet kalemi ekle. model_id verilirse modele özel olur.]] - rationale - siparis_fisi.py
- [[Maliyet ana başlıkları Kesim Giderleri, Kalfa Giderleri, vb.]] - rationale - models.py
- [[Maliyet kalemleri Astar, Çelik Taban, vb. Alt başlık ile gruplandırılır.     mo]] - rationale - models.py
- [[Maliyet tablolarını oluştur (yoksa), eksik kolonları ekle.]] - rationale - siparis_fisi.py
- [[Maliyet şablonunu döndür. model_id= verilirse modele özel kalemler de dahil.]] - rationale - siparis_fisi.py
- [[MaliyetKalem]] - code - models.py
- [[MaliyetKategori]] - code - models.py
- [[Maliyeti girilmiş modellerin listesi.]] - rationale - siparis_fisi.py
- [[Varsayılan maliyet kalemlerini oluşturur (sadece tablo boşsa).]] - rationale - siparis_fisi.py
- [[Yeni maliyet kategorisi (başlık) ekle.]] - rationale - siparis_fisi.py
- [[_ensure_maliyet_tables()]] - code - siparis_fisi.py
- [[api_maliyet_kalem_ekle()]] - code - siparis_fisi.py
- [[api_maliyet_kategori_ekle()]] - code - siparis_fisi.py
- [[api_maliyet_model_listesi()]] - code - siparis_fisi.py
- [[api_maliyet_sablon()]] - code - siparis_fisi.py
- [[seed_maliyet_sablonu()]] - code - siparis_fisi.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_58
SORT file.name ASC
```

## Connections to other communities
- 8 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 2 edges to [[_COMMUNITY_Community 66]]

## Top bridge nodes
- [[MaliyetKalem]] - degree 5, connects to 2 communities
- [[MaliyetKategori]] - degree 5, connects to 2 communities
- [[seed_maliyet_sablonu()]] - degree 6, connects to 1 community
- [[_ensure_maliyet_tables()]] - degree 4, connects to 1 community
- [[api_maliyet_kalem_ekle()]] - degree 3, connects to 1 community