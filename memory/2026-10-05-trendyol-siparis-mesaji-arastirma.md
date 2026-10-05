---
name: project-trendyol-qna
description: "Trendyol Soru-Cevap entegrasyonu — webhook YOK (sadece sipariş paketleri), 10 sn polling + AI taslak (headless Claude) + /soru-cevap paneli + anasayfa pulse butonu; deploy bekliyor"
metadata: 
  node_type: memory
  type: project
  originSessionId: e43dbab6-f5e3-4b0a-9eab-6d412a862b12
---

Trendyol müşteri soruları (Q&A) entegrasyonu kuruldu (2026-07-02). Sunucu deploy'u bekliyor.

**Önemli kısıt:** Trendyol webhook'ları SADECE sipariş paketleri için; Q&A webhook'u yok → polling zorunlu. Q&A çekme limiti 1000 istek/dk, bizim 10 sn polling = 6/dk (sorun yok). Cevap: 10-2000 karakter, sadece WAITING_FOR_ANSWER cevaplanabilir, yasaklı kelime filtresi var.

**Mimari:**
- `trendyol_qna/` paketi: qna_service.py (polling/upsert/cevaplama, apigw qna endpoint'leri), qna_ai.py (headless claude taslak — [[project-ai-asistan]] altyapısını, cwd=ai_asistan/.mcp.json'ı yeniden kullanır), qna_routes.py (/soru-cevap sayfa+API), CEVAP_KURALLARI.md (AI cevap kuralları — Haziran Excel analizinden damıtıldı).
- `TrendyolQuestion` modeli (models.py sonu) + migrations/create_trendyol_questions.sql (idempotent) + startup ensure_table_exists.
- app.py job'ları: `pull_qna` 10 sn (quick_poll: WAITING ilk 20, yeni → mail 'yeni_soru' + AI taslak thread), `qna_reconcile` 3 saat (14 gün tüm statüler).
- Anasayfa SORU-CEVAP butonu (btn-pulse-active + "n Soru Var!" + 30 sn JS poll), menu.html linki.
- JSON API'ler bilinçli olarak `/soru-cevap/api/*` altında — `/api/*` öneki check_authentication'dan MUAF olduğu için kullanılmadı.

**Haziran 2026 Excel analizi (karar gerekçesi):** 464 soru, medyan cevap 34 dk, %40 şablon kopyala-yapıştır, stok soruları canlı stoğa bakılmadan cevaplanıyordu ("35 yok" denip seçeneklerde 35 varken). Kategoriler: kargo 132, stok 76, kalıp 53, özellik 48. AI taslak canlı stoğu (product_main_id → Product+CentralStock) prompta gömer.

**Kural:** Cevap ASLA otomatik gönderilmez — panelde insan onayı şart.

**Review sertleştirmeleri (aynı gün):** upsert'ler sayfa-başı commit + IntegrityError-retry'lı `_upsert_batch` (job'lar arası PK yarışı batch'i yakmaz) + süreç içi `_sync_lock`; `/api/taslak` asenkron tetikleme + `/api/taslak-durum` polling (web worker 2 dk bloklanmaz); pending-dedup (5 dk stale penceresi); blueprint'te `X-Requested-With: fetch` CSRF guard'ı (POST'lar); panelden cevaplanan soruyu reconcile 15 dk boyunca WAITING'e geri düşürmez.

**Bilgi bankası (2026-07-02, gün 2):** `trendyol_qna/vault/` Obsidian-uyumlu; AI taslak üretirken CEVAP_KURALLARI + vault/*.md okur (30k char cap, taşarsa sondan alır). `scripts/import_qna_excel.py` geçmiş "UrunSorulariniz" Excel'lerini `vault/gecmis-excel-ozeti.md`'ye damıtır (Haziran: 464 Q&A işlendi — DHL kargo kodu, ölçüm tablosu şablonu dahil). Panelden gönderilen her onaylı cevap `vault/onaylanan-cevaplar.md`'ye otomatik not düşülür (1200 satır cap). Vault git'e GİRMEZ (.gitignore — müşteri verisi); sunucuya scp ile taşınır. E2E test: gerçek şikâyet sorusuna AI özür+değişim taslağı üretti (local claude ile doğrulandı).

**2026-10-05 araştırma — sipariş mesajları API'si YOK:** Komutan Trendyol sipariş mesajlarını (müşterinin siparişle ilgili yazdıkları) panele almak istedi. developers.trendyol.com tam dizini (llms.txt) + changelog tarandı: "Müşteri Soruları Entegrasyonu" yalnız 3 servis (filtrele / detay / cevapla) ve cevap alanları yalnız ÜRÜNE bağlı (productMainId, productName…); sipariş no / soru tipi alanı yok. Sipariş mesajı, sohbet ya da "sipariş sorusu" servisi yok; Eylül 2026'ya kadarki changelog'da bu yönde güncelleme yok. Webhook yalnız sipariş paketi olayları. Resmî yol yok; panel kazıma önerilmedi. Trendyol yeni servis açarsa changelog'dan görülür.
