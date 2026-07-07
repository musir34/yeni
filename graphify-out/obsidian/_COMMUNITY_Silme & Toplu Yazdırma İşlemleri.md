---
type: community
cohesion: 0.12
members: 24
---

# Silme & Toplu Yazdırma İşlemleri

**Cohesion:** 0.12 - loosely connected
**Members:** 24 nodes

## Members
- [[Ana Kasa işlem kaydını sil ve bakiyeyi yeniden hesapla]] - rationale - kasa.py
- [[Arşivdeki siparişi kalıcı olarak silmek.]] - rationale - archive.py
- [[Birden fazla modele aynı tedarikçiyi ata.]] - rationale - siparis_fisi.py
- [[Geliştirilmiş kullanıcı işlem loglama fonksiyonu          Args         action]] - rationale - user_logs.py
- [[JavaScript'ten gelen kullanıcı hareketlerini toplu olarak kaydetmek için API end]] - rationale - user_logs.py
- [[UserLog]] - code - models.py
- [[ana_kasa_islem_sil()]] - code - kasa.py
- [[api_tedarikci_sil()]] - code - siparis_fisi.py
- [[delete_siparis_fisi()]] - code - siparis_fisi.py
- [[extract_page_from_referrer()]] - code - user_logs.py
- [[get_browser_info()]] - code - user_logs.py
- [[get_platform_info()]] - code - user_logs.py
- [[history()]] - code - stock_sync/routes.py
- [[log_user_action()_1]] - code - user_logs.py
- [[log_user_activity_api()]] - code - user_logs.py
- [[remove_archived_order()]] - code - archive.py
- [[siparis_fisi_yazdir()]] - code - siparis_fisi.py
- [[teslimat_kaydi_ekle()]] - code - siparis_fisi.py
- [[toplu_tedarikci_ata()]] - code - siparis_fisi.py
- [[toplu_yazdir()]] - code - siparis_fisi.py
- [[translate_action_type()]] - code - user_logs.py
- [[translate_page_name()]] - code - user_logs.py
- [[update_tedarikci()]] - code - siparis_fisi.py
- [[user_logs.py]] - code - user_logs.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Silme__Toplu_Yazdrma_lemleri
SORT file.name ASC
```

## Connections to other communities
- 13 edges to [[_COMMUNITY_Stok Senkron API]]
- 12 edges to [[_COMMUNITY_Maliyet Fişi & Tedarikçi]]
- 11 edges to [[_COMMUNITY_Kasa & Gelir-Gider]]
- 9 edges to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 9 edges to [[_COMMUNITY_Shopify Route Katmanı]]
- 8 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 7 edges to [[_COMMUNITY_Manuel Sipariş Oluşturma]]
- 5 edges to [[_COMMUNITY_Raf Sistemi & Etiket]]
- 4 edges to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 4 edges to [[_COMMUNITY_Ürün Çekme & Görsel İndirme]]
- 4 edges to [[_COMMUNITY_Ana Kasa Defteri]]
- 4 edges to [[_COMMUNITY_Kimlik Doğrulama & Kullanıcı Yönetimi]]
- 3 edges to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 3 edges to [[_COMMUNITY_Community 80]]
- 3 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 3 edges to [[_COMMUNITY_Community 59]]
- 2 edges to [[_COMMUNITY_Community 91]]
- 2 edges to [[_COMMUNITY_Community 44]]
- 2 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 2 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 2 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 2 edges to [[_COMMUNITY_Community 100]]
- 2 edges to [[_COMMUNITY_Community 75]]
- 1 edge to [[_COMMUNITY_Agent API & Sipariş Sorguları]]
- 1 edge to [[_COMMUNITY_Community 60]]
- 1 edge to [[_COMMUNITY_Community 106]]
- 1 edge to [[_COMMUNITY_Community 125]]
- 1 edge to [[_COMMUNITY_Community 41]]
- 1 edge to [[_COMMUNITY_Community 124]]
- 1 edge to [[_COMMUNITY_Community 82]]
- 1 edge to [[_COMMUNITY_Community 64]]
- 1 edge to [[_COMMUNITY_Community 93]]
- 1 edge to [[_COMMUNITY_Community 103]]
- 1 edge to [[_COMMUNITY_Community 102]]

## Top bridge nodes
- [[log_user_action()_1]] - degree 109, connects to 28 communities
- [[user_logs.py]] - degree 29, connects to 18 communities
- [[UserLog]] - degree 8, connects to 4 communities
- [[remove_archived_order()]] - degree 3, connects to 1 community
- [[ana_kasa_islem_sil()]] - degree 3, connects to 1 community