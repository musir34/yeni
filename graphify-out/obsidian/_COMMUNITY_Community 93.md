---
type: community
cohesion: 0.33
members: 6
---

# Community 93

**Cohesion:** 0.33 - loosely connected
**Members:** 6 nodes

## Members
- [[Bir modelin maliyet değerlerini toplu kaydet (kalem + direkt).]] - rationale - siparis_fisi.py
- [[Model bazlı direkt toplam maliyet (kalem kalem girmek istemeyenler için).]] - rationale - models.py
- [[Model bazlı gerçek maliyet değerleri.]] - rationale - models.py
- [[ModelDirekMaliyet]] - code - models.py
- [[ModelMaliyet]] - code - models.py
- [[api_maliyet_model_kaydet()]] - code - siparis_fisi.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_93
SORT file.name ASC
```

## Connections to other communities
- 3 edges to [[_COMMUNITY_Maliyet Fişi & Tedarikçi]]
- 2 edges to [[_COMMUNITY_Agent API & Sipariş Sorguları]]
- 2 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 2 edges to [[_COMMUNITY_Ana Kasa Defteri]]
- 1 edge to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]

## Top bridge nodes
- [[ModelDirekMaliyet]] - degree 6, connects to 4 communities
- [[ModelMaliyet]] - degree 6, connects to 4 communities
- [[api_maliyet_model_kaydet()]] - degree 5, connects to 2 communities