---
name: project-uretim-degisim
description: Değişimden üretim — üretim modundaki modelin rafı boşsa değişim hata vermez, kalem DG-<degisim_no> üretim kaydına yazılır, mail+WhatsApp gider (2026-10-09, yerelde, deploy bekliyor)
metadata:
  type: project
---

2026-10-09 komutan emri: değişimde ürün üretilecekse üretim akışı + WhatsApp bildirimi.

- Önce: üretim modundaki modelde raf boşsa değişim "Stok yetersiz" ile hiç oluşturulamıyordu; iki modül birbirini tanımıyordu.
- degisim_kaydet: barkod üretim modunda VE rafta toplam adet < istenen → kalem `uretim: true`, raftan tahsis YOK (kısmi tahsis yok, Trendyol raf önceliğiyle aynı kural). Rafta yetiyorsa eski akış. Üretim modu dışı barkodda eski sert hata aynen.
- Kayıt commit'inden sonra `isle_yeni_siparisler` çağrılır, numara `DG-<degisim_no>` (SH- deseni) → kayıt + mail + WhatsApp (konu "Üretim DEĞİŞİMİ") + personel bildirimi aynı akıştan. Karma değişim tek kayıt.
- uretim_modu: DEGISIM_ONEK, degisim_kaydi/degisim_detay/degisim_kargo/degisim_kargolandi; _siparis_tam_detay DG- dalı; raftan_kalemler DG- için boş (raf kalemi kayıtta zaten düşüldü, ikinci okutma/düşüm yok); eksik_raf_okutmalar kargolanmış değişimde serbest; iptal bildirimi gövdesi `_iptal_bildirimi_gonder`'e çıkarıldı; `isle_degisim_silindi`: değişim silinince üretilmemişse uretim_iptal mail+WhatsApp, üretim kaydı + doğrulamaları silinir.
- uretim_routes: kargoda/teslim değişimin kendi durumundan (Kargoya Verildi/Teslim Edildi); liste ve kargo-kodu DG- içerik/etiket Degisim kaydından (etiket orijinal siparis_no ile basılır).
- Etiket kilidi: /order-label yeni `uretim_ref` alanı (DG-...) ile sorulur; hazırlayan damgası da aynı kimliğe (yoksa orijinal siparişin kendi üretim kaydına yanlış damga düşerdi). Değişim sayfası etiket formu + üretim ekranı kargo formu uretim_ref gönderir; değişim kartında "Üretimde" rozeti.
- Şema değişikliği YOK. Testler: tests/test_uretim_degisim.py (7, izole sqlite, --noconftest).
- Bilinen sınır: değişim durum düğmeleri (Kargola) doğrulama kilidine bağlı değil; kilit yalnız etiket basımında.

İlgili: [[project-uretim-modu]], [[project-uretim-shopify-bosluklari]], [[project-ledger-manual-exchange]]
