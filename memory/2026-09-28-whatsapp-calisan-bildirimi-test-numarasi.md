# 2026-09-28 — WhatsApp çalışan bildirimi (Meta test numarası, ikinci hat)

## Ne değişti
- `whatsapp_notify.py` (yeni): `notify_staff(event_type, summary)` + `notify_staff_async`.
  Önce serbest metin dener, 131047 (24 saat penceresi kapalı) gelirse onaylı şablona düşer.
  Bir alıcıda hata diğerlerini durdurmaz; loga numaranın yalnız son 4 hanesi yazılır.
- `trendyol_qna/shopify_qna.py` `_notify_new_question`: mail bloğundan sonra ayrı try ile
  "Shopify sorusu" bildirimi.
- `trendyol_qna/qna_service.py` `_notify_new_questions`: "Trendyol sorusu" bildirimi;
  aynı turda birden çok soru düşerse tek mesaj ("+N soru daha").
- `tests/test_whatsapp_notify.py` (yeni): 7 test, ağa çıkmaz.

## Neden
- Kaynak talimat: `~/Documents/Shopify/gullupanel-whatsapp-bildirim-talimati.md`.
- Talimat anahtar adları (`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, ...) mevcut
  `whatsapp_service.py` ile aynıydı. Aynı adlar kullanılsa üretim bildirimleri test
  numarasına kayar, şirket hattı Coexistence ile bağlanınca env-token + DB-numara
  uyuşmazlığı çıkardı. Komutan kararıyla ayrı modül + ayrı `WHATSAPP_STAFF_*` anahtarları.
- `whatsapp_service.py` ve üretim olayları akışına dokunulmadı.

## Deploy
- Migration yok. `.env`: `WHATSAPP_STAFF_TOKEN`, `WHATSAPP_STAFF_PHONE_NUMBER_ID`,
  `WHATSAPP_STAFF_NUMBERS` (905..., virgüllü). Opsiyonel: `_TEMPLATE_NAME` (gullu_bildirim),
  `_TEMPLATE_LANG` (en; 132001 gelirse en_US), `_API_VERSION` (v25.0).
- Anahtarlar girilmeden modül sessizce devre dışıdır.
- `git pull && systemctl restart gullupanel.service`

## Açık kalanlar
- Webhook kurulmadı (komutan kararı).
- Yeni sipariş, üretim siparişi, gecikme, unutulmuş soru bildirimleri bağlanmadı;
  ayrıntısı sonra konuşulacak.
- Gerçek gönderim denenmedi (Meta tarafı: alıcı listesi, kalıcı anahtar, şablon onayı bekliyor).

## Güncelleme (aynı gün)
- Talimat dosyası güncellendi: şablon `gullu_bildirim` (test hesabında Active, dil `en`), API v25.0,
  alıcılar 905522000953 (mağaza hattı) + 905368520104 (Ahmet). Modül varsayılanları buna çekildi.
- Lokal `.env`'e WHATSAPP_STAFF_* satırları eklendi, TOKEN boş — komutan dolduracak. Sunucu `.env`'i ayrıca doldurulmalı.
- Kurulum testi: `python scripts/test_whatsapp_notify.py` (listedeki herkese deneme bildirimi atar).
- Talimattaki WHATSAPP_TOKEN adı KULLANILMAZ; bu modülün anahtarı WHATSAPP_STAFF_TOKEN.
- 2026-09-28: Lokal uçtan uca deneme BAŞARILI — scripts/test_whatsapp_notify.py iki alıcıya da OK döndü (API mesajı kabul etti). Kalan: commit/push + sunucu .env + restart.
- 2026-09-28: Komutan commit 951eb81 ("wp mesaj") ile push etti ve yayına aldı. .env Git dışında (doğrulandı). Sunucu .env satırları ve canlı uçtan uca test komutan teyidi bekliyor.
