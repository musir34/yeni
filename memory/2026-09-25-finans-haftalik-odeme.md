# 2026-09-25 — Haftalık ve değişken tutarlı düzenli ödemeler

Kullanıcı her hafta ayrı ödeme yaptığını, bazı tutarların sabit bazılarının değişken olduğunu belirtti.

- Düzenli ödeme ekleme/düzenlemede aylık/haftalık sıklık, ilk haftalık ödeme tarihi ve sabit/değişken tutar seçimi eklendi. Sabit tutar ödeme esnasında da değiştirilebilir; değişken tutar her ödemede girilir.
- İlk tarihten itibaren 7 günde bir vade oluşturulur; ay/yıl geçişi, ayda 4/5 ödeme ve artık yıl desteklenir. Aylık sayfada her hafta ayrı bekliyor/ödendi satırıdır.
- Panel, ödeme penceresi, kayıt defteri dönem etiketleri ve bekleyen toplamları güncellendi. Tutarı bilinmeyen ödemeler ayrıca sayılır; gerçek ödeme tutarları işlem tarihine göre raporlanmaya devam eder.
- Mevcut aylık planlar varsayılan olarak aylık kalır. Aylıktan haftalığa geçiş, ödenmiş son aylık dönemden sonraki ayda başlayabilir; önceki aylık kayıtlar korunur. Haftalık ödeme yapıldıktan sonra takvim başlangıcı/sıklığı değiştirilemez; yeni takvim için eski planın bitiş ayı belirlenip ayrı plan açılmalıdır. Tutar seçimi düzenlenebilir.
- Model: finans_ana_gider_kalem.siklik / ilk_odeme_tarihi / tutar_degisken. finans_islem.donem VARCHAR(10): aylık YYYY-MM, haftalık YYYY-MM-DD. Mevcut kalem/dönem kısmi unique index aynı haftaya çift ödemeyi engeller. Ödeme ve düzeltmede plan kilidi kullanılır.
- scripts/update_finans_haftalik.py mevcut veriyi koruyan, tekrar çalıştırılabilir güncellemedir. İlk kurulum scripti de bunu içerir.

## Doğrulama
- İzole SQLite üzerinde 12 unittest geçti: sabit/değişken tutar, haftalar, ay/yıl/artık yıl sınırı, eski aylık kayıtların korunması, mükerrer koruma (DB index dahil), iptal/yeniden ödeme, düzeltme, yetersiz bakiye, rapor dönemi ve kapatılmış planın ödeme geçmişi.
- Komut: `.venv/bin/python -m unittest discover -s tests -p test_finans_haftalik.py`
- Chromium üzerinde gerçek şablonların izole verilerle render edilen halleri kontrol edildi: yeni plan, düzenleme, sabit/değişken alanları, haftanın modal'a aktarılması, boş tutar doğrulaması, panel ve mobil sayfa genişliği. Konsol hatası yok.
- Jinja/Python sözdizimi ve git diff --check geçti.
- PostgreSQL güncellemesi / canlı veri üzerinde çalıştırma / deploy yapılmadı.

## Yayına alma
Kod güncellendikten sonra uygulama yeniden başlatılmadan önce sunucunun Python ortamıyla:
`DISABLE_JOBS=1 python scripts/update_finans_haftalik.py`
Ardından mevcut servis yeniden başlatma akışı uygulanır. Sadece restart yeterli değildir; önce şema güncellemesi gerekir.
