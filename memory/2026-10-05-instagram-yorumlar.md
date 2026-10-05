# Instagram gönderi yorumları → /soru-cevap (2026-10-05, yerelde, commit/deploy yok)

Komutan kararı: yoruma cevap TEK düğmeyle İKİ mesaj olarak gider — asıl cevap yorum sahibine özelden (DM),
yorumun altına da herkese açık "özelden yanıtladık" notu.

- `models.py` `InstagramComment` (tablo `instagram_comments`, additive; app init'te açılır). status new|answered|ignored.
- `trendyol_qna/instagram_dm.py`: `sync_comments` (son 20 gönderi; yorum bildirimi Meta incelemesi istediği için
  2 dk'da bir çekme; ilk görüşte 3 günden eski yorum alınmaz; kendi yorumlarımız atlanır; altında bizim yanıtımız
  olan yorum 'answered'), `answer_comment` (ÖNCE `POST me/messages {recipient:{comment_id}}`, SONRA
  `POST <comment_id>/replies`; DM gitmezse not yazılmaz; not yazılamazsa cevap sayılır + uyarı; giden DM konuşma
  geçmişine de yazılır), `ignore_comment`, `new_comment_count`.
- Sınırlar: özel yanıt yorumdan sonra 7 gün içinde, yorum başına tek mesaj; DM 1000, not 300 karakter.
- `qna_routes.py`: dördüncü kaynak `instagram_yorum`; `/soru-cevap/api/instagram-yorum/{cevapla,yoksay,taslak,taslak-durum}`.
- `qna_ai.py`: `generate_instagram_comment_draft` — YALNIZ düğmeyle (otomatik değil; emoji yorumlarına boşuna
  taslak üretilmesin diye benim kararım). Bağlam: yorum + gönderi açıklaması.
- `templates/soru_cevap.html`: `instagramYorumCardHtml` ("Yorum" etiketli kart, not kutusu, Yoksay, "İkisini gönder").
- `app.py`: `pull_instagram_comments` işi (120 sn) — yalnız `INSTAGRAM_COMMENTS=1` ise çalışır.
- Bildirim (mail/WhatsApp) YOK; yalnız bekleyen sayacı artar (benim varsayımım, komutan yanıtlamadı).
- Tüm yorumlar düşer, gereksizler "Yoksay" ile kapatılır (benim varsayımım).
- Canlı salt-okunur sınama (mevcut anahtarla): `me/media` ve `<media>/comments` 200; yorumda üst düzey `username`
  alanı GELMİYOR, `from.username` geliyor (kod ikisini de okur); `replies{...}` iç içe alanı kabul ediliyor.
  Yeni anahtar gerekmedi. YAZMA çağrıları (özel yanıt + yorum yanıtı) canlıda DENENMEDİ.
- Reklam yorumları ve yanıtın yanıtı kapsam dışı.
- Testler: `tests/test_instagram_dm.py` toplam 29 (yalıtılmış sqlite).
- Deploy: commit + sunucu .env'e `INSTAGRAM_COMMENTS=1` + restart.
