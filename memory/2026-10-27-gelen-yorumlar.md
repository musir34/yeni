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
