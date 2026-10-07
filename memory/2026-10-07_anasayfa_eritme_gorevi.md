# 2026-10-07 — Anasayfa "Görev: Bu Modeller Eritilecek" kartı

**Neden:** Komutan üretim modu dışındaki modellerin stoğunu sıfıra indirmek istiyor; hangi
modellerin kapsamda olduğunu ve kalan stoğu anasayfadan takip edecek.

**Ne yapıldı:**
- `eritme_gorevi.py` (yeni): iki sabit model listesi + `eritme_ozeti()`.
  - Çok Satan (9): 9, 099, 0109, 0172, 0106, 0419, 017, 018, 020
  - Ağır Giden (99): üretim modu dışı kalan modeller; Alissa (TED-003) modelleri
    (0128, 014, 160, 2031, 4380, 4480, 658, 778, 856) bilinçli olarak YOK.
  - Stok her açılışta central_stock'tan canlı; hata → sıfır, anasayfa düşmez.
- `home.py`: import + `render_template(..., eritme=eritme_ozeti())` (2 dokunuş).
- `templates/home.html`: Hızlı İşlemler altına kart; grup başına toplam stok + model sayısı,
  Bootstrap collapse ile model rozetleri (kod + stok, sıfır stoklu üstü çizili), gece modu CSS'i.
- Migration yok, DB'ye yazma yok. Model listesini değiştirmek = eritme_gorevi.py sabitleri.

**Doğrulama:** Jinja parse OK; canlı DB'de salt-okunur çalıştırıldı (07.10: çok satan 3.813,
ağır giden 4.060 çift). Tarayıcı görüntüsü alınmadı.

**Deploy:** `git pull && systemctl restart gullupanel.service`
