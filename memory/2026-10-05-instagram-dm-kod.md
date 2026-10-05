# Instagram DM → /soru-cevap (kod yazıldı, 2026-10-05)

Komutan emri: Instagram DM'leri Trendyol/site soruları gibi panelden cevaplansın. Kod yazıldı; Instagram
tarafı (Meta uygulaması, anahtarlar, webhook) henüz KURULMADI — ayarlar yokken sistem sessizce pasif kalır.

## Dosyalar
- `models.py`: `InstagramConversation` (kart = müşteri, igsid tekil, status new|answered, last_customer_at →
  24 saat penceresi, AI taslak alanları) + `InstagramMessage` (mid tekil, direction in|out). Additive;
  tablolar app init'te `instagram_dm.ensure_table_exists` ile açılır (migration yok).
- `trendyol_qna/instagram_dm.py` (yeni): public `GET/POST /api/instagram/webhook` (GET doğrulama anahtarı,
  POST `X-Hub-Signature-256`; sır yoksa POST reddedilir), `kaydet_mesaj` (mid ile tekilleştirme, durum
  yalnız EN YENİ mesaja göre değişir), `answer_conversation` (24 saat + 1000 karakter kontrolü, sonra
  `POST <hesap|me>/messages`), `sync_conversations` (yoklama yedeği), `refresh_token_if_needed`
  (60 günlük anahtar; yenisi PlatformConfig `instagram_dm` torbasında, .env tohum).
- `trendyol_qna/qna_ai.py`: `generate_instagram_draft(_s_async)` — bağlam son 12 mesaj.
- `trendyol_qna/qna_routes.py`: listeye üçüncü kaynak; `/soru-cevap/api/instagram/{cevapla,taslak,taslak-durum}`;
  Senkronla düğmesi Instagram'ı da çeker. `qna_service.waiting_count` Instagram'ı da sayar.
- `templates/soru_cevap.html`: `instagramCardHtml` (konuşma balonları, kalan süre rozeti, süresi dolunca kilit).
- `app.py`: `pull_instagram_dm` (60 sn, yalnız INSTAGRAM_POLL=1) + `instagram_token` (günlük) işleri.
- `tests/test_instagram_dm.py`: 20 test (izole sqlite; `DISABLE_JOBS=1 ... pytest --noconftest`).

## .env anahtarları
INSTAGRAM_APP_SECRET, INSTAGRAM_VERIFY_TOKEN, INSTAGRAM_ACCESS_TOKEN; opsiyonel INSTAGRAM_ACCOUNT_ID,
INSTAGRAM_API_VERSION, INSTAGRAM_POLL=1.

## Davranış kararları (benim varsayımlarım)
- Instagram uygulamasından elle yazılan cevap echo ile gelir → kart kendiliğinden "Cevaplandı" olur.
- Aynı müşteri art arda yazarsa 10 dk içinde tek bildirim (mail + WhatsApp `musteri_sorusu`).
- Yoklama varsayılan KAPALI: webhook ile yoklamanın mesaj kimliklerinin aynı olduğu canlıda doğrulanmadı;
  farklıysa çift kayıt olur. Canlı denemede bakılacak.
- Süresi dolan bekleyen konuşma "Bekleyen"de kalır (kilitli kart); otomatik düşürme yok.

## Doğrulanmayanlar (canlı kurulumda bakılacak)
- Rolsüz gerçek müşterinin mesajı standart erişimde webhook'a düşüyor mu.
- Webhook gövde biçimi (messaging / changes — ikisi de işleniyor), conversations API alan adları,
  sürümsüz çağrının kabulü, `Authorization: Bearer` başlığı.
