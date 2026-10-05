---
name: project-instagram-dm-soru-cevap
description: Instagram DM'leri /soru-cevap ekranına üçüncü kaynak — 2026-10-05 araştırma + kod yazıldı (yerelde, 20 test geçti); Meta kurulumu ve canlı deneme bekliyor
metadata:
  type: project
---

Komutan 2026-10-05'te Instagram'dan gelen soruları Trendyol/site soruları gibi panelden cevaplamak istedi; başlangıç kapsamı YALNIZ DM (yorumlar sonra). Araştırma yapıldı, kod yazılmadı.

**Meta tarafı (resmî belge, 2026-10-05):**
- Yol: "Instagram API with Instagram Login" — host `graph.instagram.com`, Facebook sayfası GEREKMEZ. İzinler: `instagram_business_basic` + `instagram_business_manage_messages`. Hesap profesyonel (işletme) olmalı.
- Kendi hesabımız için Standard Access yeterli → App Review yok. Advanced Access yalnız başkasının hesabına hizmette.
- Gelen mesaj webhook ile: alan `messages`; doğrulama GET `hub.challenge`/`hub.verify_token`; imza `X-Hub-Signature-256` (app secret HMAC-SHA256); uygulama **Live** olmalı; hesapta `POST /me/subscribed_apps?subscribed_fields=messages` + Instagram uygulamasında "Bağlı araçlar → Mesajlara erişime izin ver" açık olmalı (kapalıysa hata vermeden hiç gelmez).
- Cevap: `POST graph.instagram.com/<IG_ID>/messages` `{recipient:{id:IGSID}, message:{text}}`. 24 saat penceresi (müşterinin son mesajından); dışında hata 10/2534022. `HUMAN_AGENT` etiketi 7 güne uzatır ama AYRI App Review + işletme doğrulaması ister.
- Yedek/başlangıç doldurma: Conversations API `/me/conversations` (konuşma başına yalnız son 20 mesajın detayı; 30+ gün hareketsiz istek klasörü gelmez). Token 60 gün, süresi dolmadan yenilenmeli.
- Kendi gönderdiğimiz cevap `is_echo:true` ile webhook'a geri düşer → süzülmeli. Müşteri kimliği IGSID; kullanıcı adından bulunamaz.
- DOĞRULANMADI: Standard Access'te rolü olmayan gerçek müşterinin mesajı webhook'a düşüyor mu (resmî belge "kendi hesabın için yeter" diyor, üçüncü taraf yazılar çelişkili). İlk iş canlı deneme; düşmezse Conversations API yoklaması.

**Bizim taraf:** /soru-cevap zaten iki kaynaklı (TrendyolQuestion + ShopifyQuestion, `qna_routes.py` Python'da birleştirir, `source` alanı). Instagram üçüncü kaynak; fark: soru tek mesaj değil KONUŞMA. `/api/` öneki oturumdan muaf (webhook oraya). Meta uygulaması mevcut (FB_APP_ID whatsapp_baglanti.py'de; WhatsApp incelemesi sürüyor) — aynı uygulamaya Instagram ürünü eklemek incelemeyi etkiler mi bilinmiyor, ayrı uygulama daha güvenli olabilir.

**How to apply:** İşe başlarken önce Meta panelinde kurulum + canlı webhook denemesi, sonra kod. Tablo additive (`ensure_table_exists` deseni). İlgili: [[project-trendyol-qna]], [[project-shopify-soru-widget]], [[project-whatsapp-bildirim]]

**2026-10-05 kod yazıldı (yerelde, commit/deploy yok):** `trendyol_qna/instagram_dm.py` (webhook `/api/instagram/webhook`, kayıt, cevap, yoklama, anahtar yenileme), `InstagramConversation`+`InstagramMessage` tabloları (app init'te açılır), qna_routes'ta üçüncü kaynak, `instagramCardHtml`, AI taslak, işler. .env: INSTAGRAM_APP_SECRET / INSTAGRAM_VERIFY_TOKEN / INSTAGRAM_ACCESS_TOKEN (+ops. ACCOUNT_ID, API_VERSION, POLL=1). Ayarlar yokken pasif. Sıradaki adım komutanla Meta paneli kurulumu + canlı deneme; yoklama varsayılan kapalı (webhook/yoklama mesaj kimliği aynı mı doğrulanmadı). Ayrıntı: repo `memory/2026-10-05-instagram-dm-kod.md`.

**2026-10-05 Meta paneli (Chrome'dan yapıldı):** Komutan kararıyla ayrı uygulama AÇILMADI; mevcut "Gullu Panel" uygulamasına (ID 1365245268503883, Live) "Manage messaging & content on Instagram" kullanım durumu eklendi. Instagram alt uygulaması: "Gullu Panel-IG", Instagram app ID 1423914405922063. `instagram_business_basic` + `instagram_business_manage_messages` "Ready for testing" (standart erişim). ⚠️ Webhook imzası FB uygulama sırrıyla DEĞİL, bu sayfadaki ayrı **Instagram app secret** ile atılır → `INSTAGRAM_APP_SECRET` odur (FB_APP_SECRET değil). Panel "canlı veri için App Review gerekir" notu gösteriyor → rolsüz müşteri mesajı sorusu hâlâ açık. KALAN: (1) kod commit+deploy, (2) sunucu .env'e 3 anahtar, (3) "Add account" ile Instagram girişi + anahtar üretimi (komutan yapar), (4) webhook adresi `https://<panel alanı>/api/instagram/webhook` + doğrulama anahtarı, `messages` alanına abonelik, (5) Instagram uygulamasında mesaj erişim izni, (6) canlı deneme. Ayar sayfası: Kullanım durumları → Instagram → Customize → "API setup with Instagram login".
