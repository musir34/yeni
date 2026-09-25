# 2026-09-25 — Şahsi cari: dükkânın kasasından alınan borç

İstek: "Dükkânın parasından aldığım borcu unutmamak için finansta tutmak istiyorum, cariye böyle bir detay ekle."
Netleştirme cevapları: (1) para kasadan gerçekten düşsün; (2) bu hareketler yalnız kendi/şahsi hesapta olsun.

## Ne değişti
- finans_cari_service.py: yeni cari türü `sahsi` ("Şahsi (kasadan borç)") + iki hareket türü
  `borc_alma` (-1) ve `borc_odeme` (+1). `_sahsi_kontrol`: şahsi hesapta yalnız bu ikisi, diğer
  hesaplarda bu ikisi yasak. `mal_girisi` şahsi hesapta kapalı. `odeme_yap`/`tahsilat_al`'a
  `tur` parametresi eklendi (kasa tarafı aynen `cari_odeme` / `cari_tahsilat`, rapor kolonları değişmedi).
  `cari_guncelle`: hareketi olan hesap şahsiye çevrilemez (tersi de). `cari_ozet`'e `sahsi` anahtarı
  (TL şahsi negatif bakiyeler ayrı toplanır, alacağa karışmaz).
- finans_cari.py: `/finans/cari/<id>/borc-alma` (Elde/Banka'dan düşer) ve `/finans/cari/<id>/borc-odeme`
  (Beyazıt'a girer) route'ları; flash mesajları "toplam/kalan borcunuz" diliyle.
- Şablonlar: cari detayda şahsi hesapta "Kasadan Borç Aldım" / "Borcumu Ödedim" butonları + iki modal
  (USD hesapta kur alanı ve canlı TL önizlemesi dahil), defterde kolon başlıkları "Ödediğim/Aldığım"
  ve renkler ters çevrildi, bakiye "kasaya borcunuz"; cari listesi ve panelde "Kasadan aldığım borç" satırı.
- Kullanım: Cari Hesaplar'dan tür "Şahsi (kasadan borç)" ile bir hesap aç (örn. kendi adın), sonra
  her para aldığında "Kasadan Borç Aldım"; geri koyduğunda "Borcumu Ödedim". İptal iki tarafı geri alır.

## Doğrulama
- `py -W ignore -m unittest discover -s tests -p "test_finans_*.py"` → 45 test OK
  (yeni tests/test_finans_cari_sahsi.py, 8 test: kasa çıkışı+alacak, geri ödeme, iptal, şahside normal
  hareketlerin kapalılığı, diğer hesapta borç almanın kapalılığı, tür dönüşümü kilidi, özet ayrımı,
  bakiyeli hesabın kapatılamaması).
- Jinja parse + py_compile + `git diff --check` geçti. Canlı/deploy YAPILMADI.

## Yayına alma
DB değişikliği YOK (cari/hareket `tur` kolonları serbest metin, CHECK yok) →
`git pull && systemctl restart gullupanel.service` yeterli.
