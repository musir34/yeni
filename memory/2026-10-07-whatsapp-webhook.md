# 2026-10-07 — WhatsApp webhook (Coexistence şartı)

**Neden:** Şirket hattını (+90 552 200 09 53) Coexistence ile bağlama akışında
"mevcut WhatsApp Business uygulaması numaranı bağla" seçeneği hiç çıkmıyordu;
akış numarayı yeni kayıt gibi işleyip "numara zaten WhatsApp'ta kayıtlı" diyordu.
Meta belgesi: bu seçenek, uygulama `history`, `smb_app_state_sync`,
`smb_message_echoes` webhook alanlarına abone olmadan görünmez. Abonelik için
Meta'nın çağıracağı public bir adres gerekir; panelde WhatsApp webhook'u yoktu
(Instagram'ınki vardı: trendyol_qna/instagram_dm.py).

**Ne değişti:**
- `whatsapp_webhook.py` (yeni): `GET/POST /api/whatsapp/webhook`. GET →
  `WHATSAPP_VERIFY_TOKEN` ile hub.challenge; POST → `FB_APP_SECRET` ile
  X-Hub-Signature-256 imzası, olaylar yalnız loglanır (senkron işlenmez).
  `/api/` öneki check_authentication'dan muaf (instagram ile aynı desen).
- `routes/__init__.py`: blueprint kaydı.
- `tests/test_whatsapp_webhook.py`: izole Flask testi (7 senaryo, --noconftest).

**Deploy (kullanıcı):** `.env` → `WHATSAPP_VERIFY_TOKEN=<rastgele>` ekle;
`git pull && systemctl restart gullupanel.service`. Sonra Meta panelinde
WhatsApp > Configuration > Webhooks: callback `https://gullupanel.com/api/whatsapp/webhook`,
verify token aynı değer; alanlar: messages, history, smb_app_state_sync,
smb_message_echoes. Ardından /whatsapp-baglanti'dan ES akışını tekrar dene.

**Ayrıca:** Meta, Embedded Signup v2'yi 15 Eki 2026'da kapatıyor; v4 yapılandırması
(Facebook Login for Business > Configurations > Embedded Signup) ayrıca açılmalı.
Bugün Chrome'da görüldü: uygulama "Verified Tech Provider"; App Review 4 Eki onaylı.
