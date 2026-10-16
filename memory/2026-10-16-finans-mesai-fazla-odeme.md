# 2026-10-16 — Düzenli Ödemeler: çalışan mesaisi + fazla ödeme toleransı

İstek: Mesai yapan çalışanlara Düzenli Ödemeler'de "Ödeme ekle"nin yanından saat + tutar girip hesabına
eklemek; mesai 1080 ₺ tutarken 1100 ₺ verilince hata alınmamalı.

## Karar / varsayımlar
- Mesai ayrı satır değil, **haftanın hak edişine eklenir**: cari defterine `tur='mesai'` (+1) hareketi
  (açıklama "Mesai 3 saat — <hafta etiketi> · not"), `FinansCalisanHakedis.tutar += tutar`. Kasaya dokunmaz.
  Saat yalnız açıklamada saklanır (şema değişikliği yok, migration yok).
- Fazla nakit ödeme (`odeme > kalan`) artık hata değil: fark `hakedis` hareketi olarak
  "… fazla ödeme (+X ₺ hak edişe eklendi)" açıklamasıyla yazılır, çalışan borçlu/alacaklı kalmaz, hafta kapanır.
  Şahsi "Hesabıma yaz" (mahsup) sınırı aynen korunur.
- Değişken tutarlı ve hak edişi girilmemiş hafta: "Önce bu dönemin hak edişini girin" hatası.
  Sabit planda henüz hak ediş satırı yoksa önce varsayılan tutar yazılır, sonra mesai eklenir.
- Mesai iptali cari defterinden ✕ ile (`_mesai_iptal`): hak ediş düşer; ödenenin altına inemez.
  Çift tıklama koruması `odeme_anahtari` sütunu ile (mesai hareketinde de benzersiz anahtar).

## Dosyalar
- finans_calisan_service.py: `_hak_yaz(aciklama=)`, `hakedis_ve_odeme` fazla ödeme, `_saat`, `mesai_ekle`,
  `durum_satiri['mesailer']`.
- finans_cari_service.py: HAREKET_TURLERI/ETIKET'e `mesai`, `_mesai_iptal`, `hareket_iptal` dalı.
- finans_calisan.py: `POST /finans/calisan/mesai`; ödeme flash'ında "Fazla verilen X ₺ hak edişe eklendi".
- templates: `_finans_mesai_modal.html` (yeni, `_finans_calisan_modal.html` sonunda include),
  `_finans_calisan_buton.html` "⏱ Mesai" düğmesi, `finans_ana_gider.html` hak ediş hücresinde mesai mini satırı,
  `finans_cari_detay.html` mesai satırında ✕.

## Doğrulama
- tests/test_finans_mesai.py (9 test) + test_finans_calisan.py fazla-ödeme testi yeni davranışa güncellendi.
- `PYTHONUTF8=1 DISABLE_JOBS=1 python -W ignore -m unittest discover -s tests -p "test_finans_*.py"` → 121 OK
  (yerel Python 3.11'e tzdata/qrcode/pyotp/flask-login/pandas kuruldu). Tarayıcıda görülmedi, canlı/deploy YOK.

## Yayın
`git pull && systemctl restart gullupanel.service` (şema değişikliği yok).
