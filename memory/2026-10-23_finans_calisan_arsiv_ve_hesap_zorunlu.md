# 2026-10-23 — Finans: çalışan ödemesinde hesap zorunlu + işten ayrılan çalışanı arşivle

## Sorun 1: Ödeme hesabı seçilmeden "Kaydet" pencereyi kapatıyordu
- Yer: `templates/_finans_calisan_modal.html` (Düzenli Ödemeler › çalışan "Ödeme ekle" penceresi).
- "Şimdi verdiğin para" dolu, "Ödeme hesabı" boşken form sunucuya gidiyor; sunucu
  `_gider_hesabi_kontrol` ile reddediyor (`finans_calisan_service.hakedis_ve_odeme`), sayfa
  yenileniyor, pencere kapanıyor → kullanıcı kaydedildi sanıyor. Hesap alanı bilerek `required`
  değil çünkü yalnız hak ediş girişi (para vermeden) de bu formdan yapılıyor.
- Çözüm: istemci tarafı kural — tutar doluysa hesap seçilmeden submit engellenir
  (`preventDefault`), select `is-invalid` kırmızı uyarı metniyle işaretlenir, pencere açık kalır.
  Sunucu kuralı aynen duruyor (çift kalkan). `_finans_ode_modal.html` (diğer giderler) zaten
  `required` radyo ile korunuyordu, dokunulmadı.

## Sorun 2: İşten ayrılan çalışan için tek düğme
- Eski yol iki adımdı: Kalem Tanımları › Pasif + Cari Hesaplar › Kapat (bakiye 0 şartı).
- Yeni: `finans_calisan_service.calisan_arsivle(kalem_id, arsiv=True|False)` tek transaction:
  bugüne kadarki hak edişleri yazar (`plan_hakedislerini_isle`), bekleyen hak ediş ya da bakiye ≠ 0
  varsa FinansHata (önce ödenmeli), sonra plan `aktif=False` + cari `aktif=False`. Geri Al ikisini açar.
  `arsivde(kalem)` = plan pasif + cari kapalı (yalnız Pasif yapılmış eski kayıt arşiv sayılmaz).
- Rota: `POST /finans/calisan/<kalem_id>/arsiv` (`arsiv=1|0`, admin) — `finans_calisan.py`.
- UI (`finans_ana_gider.html`): çalışan satırında "🗄 Arşivle" (confirm ile); arşivdekiler ana tablodan
  çıkar, altta kapalı "🗄 Arşiv — işten ayrılan çalışanlar (n)" kartında "↩ Geri Al" ile listelenir.
  Cari kapalı olduğu için `maas_carileri()` listesine (yeni plan açılır menüsü) de düşmez.
- Şema değişikliği YOK (mevcut `aktif` bayrakları). Geçmiş hak ediş/ödeme kayıtlarına dokunulmaz.
- Test: `tests/test_finans_calisan_arsiv.py` (sqlite, izole). Çalıştırma Windows'ta:
  `DISABLE_JOBS=1 PYTHONUTF8=1 PYTHONPATH=. python -m unittest discover -s tests -p "test_finans_*.py"`
  (PYTHONUTF8 olmadan test_finans_iptal_dugmesi şablonları cp1252 ile okuyup patlıyor — eski sorun).
- Deploy bekliyor: `git pull && systemctl restart gullupanel.service`.
