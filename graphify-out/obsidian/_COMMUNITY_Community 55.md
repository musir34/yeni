---
type: community
cohesion: 0.16
members: 16
---

# Community 55

**Cohesion:** 0.16 - loosely connected
**Members:** 16 nodes

## Members
- [[with_try=0 ile TL dönüşümü kapatılabilir (varsayılan açık).]] - rationale - agent_api.py
- [[Birden çok model kodunun maliyetini tek istekte döndürür.      POST agentapiv]] - rationale - agent_api.py
- [[Güncel USDTL kurunu JSON olarak döndür.]] - rationale - profit.py
- [[Güncel USDTL kurunu çek. Önce Harem Altın, sonra fallback.]] - rationale - profit.py
- [[Maliyeti girilmiş tüm modelleri sayfalı döndürür (ilk senkronimport için).]] - rationale - agent_api.py
- [[Tek bir model kodunun güncel maliyetini döndürür.      GET agentapiv1model-c]] - rationale - agent_api.py
- [[Verilen model kodları için {model_id {cost_usd, cost_try, has_cost}} döndür.]] - rationale - agent_api.py
- [[_fetch_usd_try()]] - code - profit.py
- [[_maliyet_payload()]] - code - agent_api.py
- [[_maliyet_rate()]] - code - agent_api.py
- [[_want_try()]] - code - agent_api.py
- [[api_exchange_rate()]] - code - profit.py
- [[model_cost_batch()]] - code - agent_api.py
- [[model_cost_list()]] - code - agent_api.py
- [[model_cost_single()]] - code - agent_api.py
- [[İstenmişse güncel USDTL kurunu getir (10 dk cache'li).]] - rationale - agent_api.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_55
SORT file.name ASC
```

## Connections to other communities
- 7 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 2 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 1 edge to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]

## Top bridge nodes
- [[_maliyet_payload()]] - degree 6, connects to 2 communities
- [[_fetch_usd_try()]] - degree 5, connects to 2 communities
- [[_maliyet_rate()]] - degree 6, connects to 1 community
- [[model_cost_batch()]] - degree 5, connects to 1 community
- [[model_cost_list()]] - degree 5, connects to 1 community