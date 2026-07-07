---
type: community
cohesion: 0.13
members: 22
---

# Community 37

**Cohesion:** 0.13 - loosely connected
**Members:** 22 nodes

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
- [[Yeni sorular için taslakları arka plan thread'inde sırayla üret.]] - rationale - trendyol_qna/qna_ai.py
- [[_fetch_page()]] - code - trendyol_qna/qna_service.py
- [[_headers()]] - code - trendyol_qna/qna_service.py
- [[_ms_to_dt()]] - code - trendyol_qna/qna_service.py
- [[_notify_new_questions()]] - code - trendyol_qna/qna_service.py
- [[_upsert_batch()]] - code - trendyol_qna/qna_service.py
- [[_upsert_question()]] - code - trendyol_qna/qna_service.py
- [[datetime_2]] - code
- [[ensure_table_exists()_1]] - code - trendyol_qna/qna_service.py
- [[generate_drafts_async()]] - code - trendyol_qna/qna_ai.py
- [[qna_service.py]] - code - trendyol_qna/qna_service.py
- [[quick_poll()]] - code - trendyol_qna/qna_service.py
- [[sync_questions()]] - code - trendyol_qna/qna_service.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_37
SORT file.name ASC
```

## Connections to other communities
- 10 edges to [[_COMMUNITY_Community 42]]
- 6 edges to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 2 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 2 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 2 edges to [[_COMMUNITY_Community 58]]
- 1 edge to [[_COMMUNITY_Community 38]]
- 1 edge to [[_COMMUNITY_Community 77]]
- 1 edge to [[_COMMUNITY_Community 104]]

## Top bridge nodes
- [[qna_service.py]] - degree 23, connects to 8 communities
- [[quick_poll()]] - degree 9, connects to 2 communities
- [[sync_questions()]] - degree 8, connects to 2 communities
- [[generate_drafts_async()]] - degree 6, connects to 2 communities
- [[_upsert_question()]] - degree 5, connects to 1 community