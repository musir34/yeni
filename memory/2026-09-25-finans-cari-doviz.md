# 2026-09-25 — Cari hesaplarda para birimi (TL / Dolar)

Kullanıcı: "cari açtığımda TL mi dolar mı sorsun, bazı yerlerde dolarla çalışıyoruz."
Netleştirme cevapları: (1) USD caride ödeme = USD tutar + o günkü kur, kasadan USD×kur TL düşer;
(2) para birimi cari açılışında bir kez seçilir, sabittir.

## Ne değişti
- models.py: `finans_cari.para_birimi` VARCHAR(3) NOT NULL DEFAULT 'TRY'; `finans_cari_hareket.kur` NUMERIC(12,4) NULL.
- finans_cari_service.py: PARA_BIRIMLERI/PARA_SEMBOL/PARA_ETIKET, `parse_kur` (4 hane), `sembol(cari)`;
  cari_ekle/guncelle `para_birimi` (çalışan → yalnız TRY; hareketi olan hesabın birimi değişmez);
  odeme_yap/tahsilat_al `kur` parametresi: USD caride zorunlu, kasaya (tutar×kur).quantize(0.01) TL,
  kasa açıklamasına "(40.00 $ × 34.5000)" eki, kur harekette saklanır; TL caride kur yok sayılır.
  cari_ozet artık borc/alacak + borc_usd/alacak_usd (ayrı toplanır, birbirine çevrilmez).
- finans_cari.py: form'dan para_birimi/kur; flash+log mesajları cari sembolüyle, USD'de TL karşılığı+kur eki.
- Şablonlar: cari listesi (açılışta "Hangi parayla çalışıyorsunuz?" seçimi, $ rozeti, dolar toplamları),
  cari detay (bakiye sembolü, kalem "Birim $", ödeme/tahsilat modallarında kur alanı + canlı TL önizleme,
  defterde kasa TL karşılığı+kur, hesap bilgisi modalında birim seçimi — çalışan/hareketli hesapta disabled),
  panel (dolar borç/alacak satırı).
- İptal: mevcut islem_iptal/cari_hareket_geri_al kasa tarafını islem.tutar (TL), cari tarafını h.tutar (USD)
  ile geri alır; ek kod gerekmedi (test kanıtı: test_usd_collection_and_cancel_restore_both_sides).
- Çalışan cari/hakediş akışı dokunulmadı (finans_calisan_service cari'yi model default'uyla TRY açar).

## Doğrulama
- `.venv/bin/python -m unittest discover -s tests -p 'test_finans_*.py'` → 37 test OK
  (yeni: tests/test_finans_cari_doviz.py, 9 test: varsayılan TRY, EUR/çalışan-USD red, USD ödeme→TL kasa,
  kursuz USD ödeme red + hiçbir şey yazılmaz, TL caride kur yok sayılır, USD tahsilat+iptal iki taraf,
  hareket sonrası birim kilidi, özet ayrımı, parse_kur).
- Jinja parse + py_compile + git diff --check geçti. Canlı/deploy YAPILMADI.

## Yayına alma (sırayla)
1. `git pull`
2. `cd ~/gullupanel/yeni && DISABLE_JOBS=1 ../venv/bin/python scripts/update_finans_cari_doviz.py`  (additive, tekrar çalıştırılabilir)
3. `systemctl restart gullupanel.service`
Sadece restart yeterli değil; önce şema güncellemesi gerekir (cari sayfaları yeni kolonu okur).
