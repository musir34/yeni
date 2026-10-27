# 2026-10-27 — Gelen Yorumlar sayfası (Güllü Yorum gönderim takibi, salt okunur)

**Kaynak brif:** `Documents/Shopify/Uygulamalar/Gullu-Yorum/PANEL-GELEN-YORUMLAR-BRIFI.md`
**İstek:** Ana sayfa "Paneller → Shopify (Site)" altına **Gelen Yorumlar** düğmesi: kaç müşteriye
yorum e-postası gitti, kaçı bağlantıyı açtı (sipariş numarasıyla), kaçı yorum yazdı.

## Ne eklendi
- `gelen_yorumlar_service.py` — Flask'sız saf okuma: Güllü Yorum SQLite'ını `file:...?mode=ro`
  ile açar (WAL yüzünden `immutable` yok), brif §4 özet + liste SQL'i, durum (yorum / baktı /
  açmadı), e-posta maskeleme (`ay***@gmail.com`), ISO-UTC → tz-aware datetime (`| ist` ile İstanbul).
  Dosya yoksa/açılamazsa `GelenYorumHata`. Yol: `GULLU_YORUM_DB` env (varsayılan
  `/home/musir/shopify-uygulamalari/gullu-yorum/data/gullu_yorum.sqlite3`).
- `gelen_yorumlar.py` — `gelen_yorumlar_bp`, `/gelen-yorumlar` (`?filtre=yorum` → yalnız yorum
  yapanlar); hata durumunda sayfa "Güllü Yorum verisine ulaşılamadı" uyarısıyla açılır, panel çalışır.
- `templates/gelen_yorumlar.html` — kargo_mutabakat deseni: Anasayfa düğmeli başlık, 4 kutu
  (Gönderilen · Bakan % · Yorum yapan % · İade bekleyen adet+TL), tablo + Hepsi/Yalnız yorum yapanlar.
- `sayfa_yetki.py` — `gelen_yorumlar` (grup Paneller, SADECE_ADMIN; sahip yetki ekranından açabilir).
- `templates/_ust_menu.html` — Shopify (Site) bölümüne kalem; `routes/__init__.py` kayıt.
- `tests/test_gelen_yorumlar.py` — geçici SQLite ile özet/liste/filtre/hata/salt-okunurluk (5 test).

## Yapılmayanlar (brif §6)
- requests/submissions'a yazma yok; iade işareti hâlâ `mark-refunded` CLI ile.
- Tam e-posta, CSV, Shopify API (yorum metni) yok → ikinci faz.

## Deploy / doğrulama (brif §7)
- `git pull && systemctl restart gullupanel.service` (şema değişikliği yok, pip yok).
- Sunucuda: `sqlite3 "file:/home/musir/shopify-uygulamalari/gullu-yorum/data/gullu_yorum.sqlite3?mode=ro" "SELECT COUNT(*) FROM requests WHERE delivered=1"` → 34 beklenir, sayfadaki Gönderilen ile eşleşmeli.
- `systemctl --user status gullu-yorum-web` değişmemeli; `data/` içinde yeni dosya oluşmamalı.
- Dosya geçici adlandırılınca sayfa hata vermeden "ulaşılamadı" göstermeli.

## 15:20 brif eki — Yorumlar sekmesi (reviews_cache)
- Güllü Yorum yeni `reviews_cache` tablosu açtı (Shopify yorumunun yerel kopyası: yıldız, başlık, metin,
  ürün+varyant, görünen ad, durum, mağaza yanıtı, foto sayısı; compile ile tazelenir).
- Servise `oku_yorumlar()` eklendi: yorum listesi (yeniden eskiye, requests ile teşvik/iade bağı) +
  onaylı yıldız dağılımı (`YildizDagilimi`: adetler, toplam, ortalama, yüzde). Tablo yoksa boş döner
  (eski sürüm), gönderim sekmesi etkilenmez.
- Sayfa iki sekme: **Gönderimler** (eski tablo + filtre) · **Yorumlar** (yıldız dağılımı kartı + yorum
  kartları: ★★★★☆ + sayı, durum rozeti Yayında/Onay bekliyor/Reddedildi, foto rozeti, iade rozeti,
  mağaza yanıtı). `?sekme=yorumlar` ile açılışta o sekme.
- Müşteri metni (`body`, `title`, `reply`) otomatik kaçırma ile basılır, `|safe` yok; testte `<b>` → `&lt;b&gt;` doğrulandı.
- Testler: 7 (reviews_cache'li fixture + tablo-yok senaryosu). Brif §7 güncel beklenti: gonderilen 34, bakan 3, yorum_yapan 2, reviews_cache 3 satır (biri #1488 test).

## "İade Edildi" düğmesi — brif §6'ya KOMUTAN KARARIYLA tek istisna (2026-10-27)
- Komutan: "iadeyi sağladığımızda bir butonla iade edildi gibi bir seçenek olsa". Brif bunu "panelden
  işaretleme istenirse ayrı karar" diye bırakmıştı; karar verildi.
- Güllü Yorum `db.mark_refunded` tek UPDATE: `requests.refunded_at = UTC-ISO WHERE order_name=? AND
  incentive_amount>0 AND refunded_at IS NULL`. Panel `gelen_yorumlar_service.iade_isaretle` birebir aynı
  sorguyu ayrı `mode=rw` bağlantıyla (dosya yoksa oluşturmaz) çalıştırır; başka hiçbir yazma yok, okumalar ro.
- Rota: POST `/gelen-yorumlar/iade-edildi` (admin, confirm, flash, log_user_action UPDATE). Düğme hem
  gönderim tablosunda hem yorum kartında, yalnız "iade bekliyor" rozeti olan satırda; işaretlenince
  "İade yapıldı" rozetine döner. Zaten işaretli/teşviksiz → uyarı, değişiklik yok.
- Güllü Yorum'un `refund-list` / `mark-refunded` komutları aynı alanı okuduğundan iki taraf tutarlı kalır.
