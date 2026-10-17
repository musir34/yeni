# 2026-10-17 — Alissa ↔ Finans cari köprüsü + ödeme hesabı seçimi (Nakit / Banka / Beyazıt)

## Emir
1. /alissa "Ödenecek bakiye" Finans > Cari'de **Muhammet Alissa** carisine her hafta kendiliğinden düşsün;
   ödeme ister /alissa'dan ister /finans/cari'den yapılsın kasadan düşsün.
2. Bazı ödemeler Beyazıt'tan doğrudan çıkıyor: her ödemede tutardan sonra hesap sorulsun, **nakit otomatik
   seçili olmasın**, sıra üstten alta Nakit (Elde) → Banka → Beyazıt.

## Ne değişti
- `alissa/cari.py` (yeni): cariyi açar/bulur (`alissa_ayar.cari_id`; ada göre de tanır), `esitle()` haftalık
  netleri (`hesap.hafta_netleri`) cariye yazar — **hafta başına tek açık satır**; hafta neti değişince eski satır
  iptal + tamamı yeniden (tur `alissa_hakedis` / eksi hafta `alissa_duzeltme`). İzleme tablosu
  `alissa_cari_hafta` (hafta_basi PK, tutar, hareket_id). Bu satırlar Finans'tan elle iptal edilemez
  (`finans_cari_service.ALISSA_TURLERI`, ✕ gizli).
- Ödemeler artık `finans_cari_service.odeme_yap` ile (kasa `cari_odeme` + cari `odeme`, tek transaction);
  /alissa "Ödemeler" listesi ve "ödenen" cari defterinden okunur (`cari.odenen/odemeler`). `AlissaOdeme`
  tablosu yalnız geçmiş; ilk bağlantıda iptal olmayan eski kayıtlar **kasasız** `odeme` satırı olarak devredilir
  (`cari_devir=1`, bir kez).
- `esitle()` çağrı yerleri: /alissa GET (oturum kullanıcısı), arka plan senkron sonu (`senkron._calistir`,
  kullanıcı = cariyi açan), `alissa.kur --senkron`.
- Finans: `GIDER_HESAPLARI`'na `beyazit` eklendi (hiyerarşik "Beyazıt'tan gider çıkmaz" kuralı KALKTI),
  `ODEME_HESAP_SIRASI` + `fs.odeme_hesaplari()` + context `fn_odeme_hesaplari`. Tüm ödeme formları
  (cari ödeme / borç alma / çalışan borç+geri ödeme, günlük harcama, düzenli ödeme "Öde", çalışan maaş,
  defter düzelt) dikey radyo/seçim, varsayılan seçili yok, Beyazıt dahil. "Öde" düğmelerinde `or 'elde'`
  fallback kaldırıldı (planın varsayılan hesabı varsa yine işaretlenir).
- Flash + "Emin misiniz?" kutusu `_finans_flash.html` ortak parçasına alındı (nav ve /alissa kullanır) →
  /alissa ödemesinde yetersiz bakiye de onayla eksiye düşebilir.

## Deploy
```
git pull
DISABLE_JOBS=1 venv/bin/python -m alissa.kur      # alissa_cari_hafta tablosu (additive)
systemctl restart gullupanel.service
```
İlk /alissa açılışı cariyi açar, haftaları yazar, eski ödemeleri devreder. Finans > Cari'de kontrol edilmeli:
cari bakiyesi = /alissa "Ödenecek bakiye".

## Test
`python -m unittest alissa.tests.test_cari alissa.tests.test_alissa` (26 OK) ·
`python -m unittest discover -s tests -p "test_finans_*.py"` (121 OK; Windows'ta `PYTHONUTF8=1`).

## Ek — Kredi kartı ekstresi: kategorisiz gider (aynı gün)
Komutan: "kategori seçmeyince hata veriyor; otomatik Diğer/Bilinmeyen olsun." `finans_kart.satirlari_kaydet`
artık hata fırlatmaz: `_varsayilan_kategori_id()` "Diğer / Bilinmeyen" günlük harcama kategorisini bulur
(ad duyarsız), yoksa aynı transaction'da açar, pasifse açar; satıcı hafızası bu kategoriyi öğrenir (önizlemede
görünür, sonradan değiştirilebilir). Şablonda boş seçenek "— kategori (boş: Diğer / Bilinmeyen) —". Şema yok.
Test: test_finans_kart.test_gider_kategorisiz_diger_bilinmeyene_yazilir.
