# 2026-09-28 — WhatsApp Duyuru sayfası (/whatsapp-duyuru)

## Ne değişti
- `whatsapp_duyuru.py` (yeni blueprint) + `templates/whatsapp_duyuru.html`: başlık + metin +
  alıcı seçimi → `POST /whatsapp-duyuru/api/gonder` → alıcı bazında sonuç (sade metin / şablon).
- `whatsapp_notify.py` (additive): `notify_staff(..., only_last4=None)` alıcı süzgeci,
  `staff_last4()`, sonuçta `via` alanı (text/template). Mevcut çağrılar değişmedi.
- `routes/__init__.py`: blueprint kaydı. `templates/_ust_menu.html`: Kullanıcı menüsüne
  admin'e özel "WhatsApp Duyuru" linki (eski `menu.html`'e eklenmedi).
- Testler: `tests/test_whatsapp_duyuru.py` + notify testlerine 2 ek (toplam 19).

## Neden / kararlar
- Komutan çalışanlara elle duyuru atmak istedi; terminal komutu yerine panel ekranı.
- Yetki: admin + 2FA + fetch başlığı (whatsapp_baglanti kalkanının aynısı).
- Metin 200 karakterle sınırlı: 24 saat penceresi kapalıyken mesaj `gullu_bildirim`
  şablonuyla gider, parametre 200'de kesilir ve tek satıra iner. Yazılan = giden olsun diye.
- Sayfaya ve yanıta numaranın yalnız son 4 hanesi iner; alıcı listesi .env'den.
- Gönderim geçmişi tablosu YOK (migration yok); yalnız kullanıcı hareket loguna yazılır.
- Gönderim senkron (sonuç ekranda görünsün diye); en kötü durumda alıcı başına ~20 sn.

## Deploy
- Migration yok, yeni .env anahtarı yok. `git pull && systemctl restart gullupanel.service`.
- Tarayıcıda görsel test yapılmadı (lokalde DB yok); rota + şablon derlemesi + uç nokta testleri geçti.

## Düzeltme (aynı gün) — "gönderildi" diyor ama mesaj gelmiyor
- Belirti: duyuru sayfası iki alıcı için "gönderildi (sade metin)" gösterdi, telefona mesaj düşmedi.
- Neden: talimattaki "önce serbest metin, 131047 gelirse şablon" tasarımı çalışmıyor. Meta, 24 saat
  penceresi kapalıyken de serbest metin isteğini 200 + mesaj kimliğiyle kabul ediyor; hata sonradan
  yalnız webhook'a düşüyor. Eşzamanlı yanıtta 131047 gelmediği için şablona geçiş hiç tetiklenmedi.
- Çözüm: `whatsapp_notify._send_one` artık HER ZAMAN şablonla gönderir; serbest metin yolu kaldırıldı.
- Ders: Cloud API'de 200 = "kabul edildi", "teslim edildi" değil. Teslim bilgisi yalnız webhook ile alınır.
  Önceki "OK" test sonuçları da teslimi kanıtlamıyordu.
- Teyit: şablonla gönderilen deneme telefonlara ULAŞTI (komutan teyidi). Teşhis doğrulandı; yalnız-şablon düzeltmesi komutan tarafından push + deploy ediliyor.
