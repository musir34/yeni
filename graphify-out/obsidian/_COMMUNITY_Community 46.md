---
type: community
cohesion: 0.15
members: 20
---

# Community 46

**Cohesion:** 0.15 - loosely connected
**Members:** 20 nodes

## Members
- [[10 sn'lik hafif tur sadece cevap bekleyen soruların son sayfasına bakar.     Ye]] - rationale - trendyol_qna/qna_service.py
- [[API item'ını tabloya işle. (satır, yeni_mi) döner. Commit çağıranın işi.]] - rationale - trendyol_qna/qna_service.py
- [[Bir sayfalık item'ı işleyip COMMIT eder; yeni soru ID'lerini döner.     Başka bi]] - rationale - trendyol_qna/qna_service.py
- [[Tablo yoksa oluştur (migration çalışmadıysa yedek).]] - rationale - trendyol_qna/qna_service.py
- [[Tek sayfa soru çek; hata durumunda None (job'lar sessizce loglayıp geçer).]] - rationale - trendyol_qna/qna_service.py
- [[Trendyol Müşteri Soruları (Q&A) servisi.  API dokümanı httpsdevelopers.trend]] - rationale - trendyol_qna/qna_service.py
- [[Trendyol epoch-millis → aware UTC datetime.]] - rationale - trendyol_qna/qna_service.py
- [[Verilen pencerede tüm statüleri senkronla (upsert). Yeni soru ID'lerini döner.]] - rationale - trendyol_qna/qna_service.py
- [[Yeni sorular için 'yeni_soru' olayına abone kullanıcılara mail at.]] - rationale - trendyol_qna/qna_service.py
- [[_fetch_page()]] - code - trendyol_qna/qna_service.py
- [[_headers()]] - code - trendyol_qna/qna_service.py
- [[_ms_to_dt()]] - code - trendyol_qna/qna_service.py
- [[_notify_new_questions()]] - code - trendyol_qna/qna_service.py
- [[_upsert_batch()]] - code - trendyol_qna/qna_service.py
- [[_upsert_question()]] - code - trendyol_qna/qna_service.py
- [[datetime_2]] - code
- [[ensure_table_exists()_1]] - code - trendyol_qna/qna_service.py
- [[qna_service.py]] - code - trendyol_qna/qna_service.py
- [[quick_poll()]] - code - trendyol_qna/qna_service.py
- [[sync_questions()]] - code - trendyol_qna/qna_service.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_46
SORT file.name ASC
```

## Connections to other communities
- 8 edges to [[_COMMUNITY_Community 45]]
- 6 edges to [[_COMMUNITY_Stok Senkron API]]
- 3 edges to [[_COMMUNITY_Community 96]]
- 2 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 1 edge to [[_COMMUNITY_Community 66]]
- 1 edge to [[_COMMUNITY_Community 76]]
- 1 edge to [[_COMMUNITY_Community 61]]
- 1 edge to [[_COMMUNITY_Maliyet Fişi & Tedarikçi]]
- 1 edge to [[_COMMUNITY_Community 62]]

## Top bridge nodes
- [[qna_service.py]] - degree 23, connects to 9 communities
- [[quick_poll()]] - degree 9, connects to 2 communities
- [[sync_questions()]] - degree 8, connects to 2 communities
- [[_upsert_question()]] - degree 5, connects to 1 community
- [[_notify_new_questions()]] - degree 4, connects to 1 community