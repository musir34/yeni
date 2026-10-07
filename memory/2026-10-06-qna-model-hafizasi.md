# Soru-cevap yapay zekâsına model koduna özel hafıza + art arda soru kuralı (2026-10-06, yerelde, commit/deploy yok)

Komutan isteği: "Bir modele bir müşteriye '2 hafta sonra gelecek' dediysem sonraki soruda AI bunu kendiliğinden
bilsin; ne zaman kime ne demişim. Müşteriye de özel zekâsı olsun." + şikâyet: "Müşteri 5 dakikada 3 soru soruyor,
üçüne de Merhaba yazıyor."

Kararlar: model notu için AYRI yer açılmadı, Takip Notları paneli kullanılır (benim önerim, komutan itiraz etmedi);
müşteriye elle not YOK, müşteri hafızası otomatik.

- `qna_service.model_hafizasi(model, haric_id, haric_musteri)`: aynı model koduna verilmiş son 8 cevap, soru
  tablosundan (ortak vault defteri eskidikçe kırpıldığı için oradan değil). Sorunun kendisi ve aynı müşterinin
  soruları hariç.
- `qna_service.model_notu(model, renk)`: Takip Notları'ndaki model notu + rengin notu (renk bilinmiyorsa hepsi etiketli).
- `qna_ai._draft_prompt` artık şunları da verir: "Bugünün tarihi", MAĞAZA NOTU (her şeyden önce gelir),
  "BU MODELE daha önce verdiğimiz cevaplar" — her biri `22.09.2026 (14 gün önce) — Ayşe Y. sordu: … / Biz: …`
  biçiminde + talimat: süreli ifadeyi o cevabın tarihine göre bugüne çevir, süresi dolmuş sözü tekrarlama,
  canlı stok esas, başka müşterinin adını cevapta kullanma.
- Art arda soru (`ART_ARDA_SORU` = 60 dk): müşterinin bu sorudan en çok 60 dk önce başka sorusu varsa isteme
  "selamlamayla BAŞLAMA, az önceki cevabı tekrar etme" eklenir; konuşmanın ilk sorusu yine selamlanır.
  Müşteri geçmişi satırları da tarihli; henüz gönderilmemiş hazır taslak "hazırlanan taslak" diye bağlama girer.
- Kapsam: yalnız Trendyol soruları. Site (Shopify) ve Instagram taslakları değişmedi.
- Şema değişikliği yok. 49 test (yalıtılmış). Gerçek yapay zekâ çıktısıyla DENENMEDİ: istemin doğru kurulduğu
  doğrulandı, modelin talimata uyup uymadığı canlıda görülecek.

## 2026-10-07: üretim modundaki model soru kartında işaretli (yerelde)
- Komutan: "müşteri ne zaman elimde olur diye soruyor; hangi model üretimde ezbere bilmiyorum."
- Kaynak: `uretim_modu.get_uretim_models()` (mevcut üretim modu ayarı). `qna_routes.uretim_modelleri()` liste
  başına bir kez okur; Trendyol (`product_main_id`) ve site (`product_sku`) kart sözlüğüne `uretim_modu` eklendi.
- Kart: model kodunun yanında mor "⚙ Üretimde" rozeti (`.qna-uretim`, ipucu: stok 0 olsa da sipariş alınır).
- AI taslağı: `_draft_prompt(..., uretim_modu=)` → "ÜRETİM MODU … 'stok yok' deme; süreyi yalnız mağaza notu /
  genel talimat yazıyorsa belirt" (`URETIM_MODU_NOTU`). Üretim süresi kodda yok; komutan genel talimata ya da
  Takip Notları'na yazarsa taslak onu kullanır. Instagram kartlarında işaret yok (model kodu bilinmiyor).
- 51 test. Canlıda denenmedi.
