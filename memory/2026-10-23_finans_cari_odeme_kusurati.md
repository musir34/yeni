# 2026-10-23 — Finans cari: ödeme küsuratı (yuvarlama) — "2997'ye 3000 verdim, 3 ₺ alacak kalmasın"

- Sorun: tedarikçi borcu 2997 ₺, 3000 ₺ ödenince cari -3 ("3,00 ₺ alacağımız") görünüyordu (Mahmut Zikzak örneği).
- Çözüm (`finans_cari_service.py`): yeni cari hareket türü `yuvarlama` (yön +1, kasasız; para gerçekten çıktı,
  kasa raporu zaten doğru). `odeme_yap` içinde: tür `odeme`, önceki bakiye > 0 (gerçek borç vardı) ve kalan alacak
  ≤ `YUVARLAMA_SINIRI` (10 ₺) ise otomatik yuvarlama satırı yazılır, bakiye 0. Üstü bilinçli ön ödeme sayılır.
  Yalnız TL, tedarikçi/müşteri/diğer (şahsi ve çalışan hariç). Borçsuz hesaba küçük ön ödeme yuvarlanmaz.
- İptal bağı: yuvarlama satırının `odeme_anahtari = 'yuvarlama:<ödeme hareket id>'` (UUID değil, çalışan
  idempotency anahtarlarıyla çakışmaz). `finans_service.cari_hareket_geri_al` ödeme iptalinde (hem cari sayfası
  hem kasa defteri yolu) bağlı yuvarlamayı da geri alır; yoksa borç 2997 yerine 3000 şişerdi.
- Eski kayıtlar için: cari detayında alacak 0–10 ₺ arasıysa "Küsuratı Kapat (x ₺)" düğmesi →
  `POST /finans/cari/<id>/yuvarlama` (`yuvarlama_kapat`). Mahmut Zikzak bu düğmeyle kapatılacak (Komutan).
- Şema değişikliği YOK. Testler: `tests/test_finans_cari_yuvarlama.py` (10 test, HTTP render dahil).
- Eşik 10 ₺ varsayım; değiştirmek için `YUVARLAMA_SINIRI`. Tahsilat (müşteri bize fazla öderse) kapsam dışı bırakıldı.
- Deploy bekliyor.
