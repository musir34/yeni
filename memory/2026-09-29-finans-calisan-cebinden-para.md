# 2026-09-29 — Çalışanın cebinden verdiği para (çalışan carisinde "para al" + "geri öde")

Kullanıcı: Hatice Yüksel Ertaş gibi maaşlı çalışanlar, kendisi yokken dükkân için cebinden para veriyor;
sonra geri ödüyor. Çalışan carisinde bunu kaydedecek buton yoktu (ödeme/tahsilat çalışanda kapalıydı).
Netleştirme cevabı: "Para kasaya girsin" (yalnız borç yazılsın seçeneği reddedildi).

## Ne değişti
- finans_cari_service.py: iki yeni hareket türü, YALNIZ çalışan hesabında:
  - `calisan_borc` (+1): seçilen Elde/Banka hesabına `cari_tahsilat` girişi + çalışana borcumuz ↑
    (`tahsilat_al(..., tur='calisan_borc', hesap_kodu=...)`; Beyazıt'a giremez).
  - `calisan_borc_odeme` (-1): Elde/Banka'dan `cari_odeme` + borç ↓ (`odeme_yap(..., tur='calisan_borc_odeme')`).
    Üst sınır `calisan_borc_kalan(cari_id)`: alınandan fazlası ödenemez → maaş hak edişine dokunamaz.
  - Eski sabit `cari.tur == 'calisan'` yasakları `_calisan_kontrol` ile değişti; normal ödeme/tahsilat/şahsi
    türleri çalışanda hâlâ kapalı, yeni türler diğer hesaplarda kapalı.
- finans_cari.py: `/cari/<id>/calisan-borc`, `/cari/<id>/calisan-borc-odeme`; detay route'u `calisan_borc_kalan` geçirir.
- templates/finans_cari_detay.html: çalışan hesabında "Cebinden Para Verdi" + (borç varsa) "Geri Öde" butonları,
  iki modal, başlıkta "bakiyenin X ₺'si cebinden verdiği para" satırı.
- DB/şema değişikliği YOK (tur VARCHAR(20), yeni değerler sığıyor). Migration gerekmez.

## Bilinçli sınırlar
- Parayla yapılan harcama otomatik yazılmaz; Günlük Harcamalar'dan ayrıca girilir (kullanıcı kararı).
- Raporda alınan para "Cari Tahsilat", geri ödeme "Cari Ödeme" sütununda görünür (gelir değildir, netleşir).
- Kısmen geri ödenmiş bir "cebinden verdi" kaydı iptal edilirse kalan 0'a sabitlenir (negatif gösterilmez);
  bakiye aritmetiği tutarlı kalır.

## Doğrulama
- Önce test yazıldı (7/8 kırmızı), sonra kod: tests/test_finans_calisan_borc.py 8 test.
- `.venv/bin/python -m unittest discover -s tests -p 'test_finans_*.py'` → 53 test OK.
- py_compile, Jinja parse, git diff --check geçti. Tarayıcıda görsel kontrol ve canlı/deploy YAPILMADI.

## Yayına alma
`git pull && systemctl restart gullupanel.service` (şema adımı yok).
