# 2026-09-25 — Finans sayı alanlarında canlı binlik ayırıcı

İstek: "Finansta sayı girdiğim tüm alanlarda yazarken otomatik nokta koysun (100000 → 100.000),
sıfırları karıştırmayayım. Her finans sayfasındaki giriş yerinde olsun."

## Ne değişti
- Yeni `static/js/finans_sayi.js`: `input[inputmode="decimal"]` alanlarını yazarken biçimler.
  Olay delegasyonu (document 'input') → sonradan eklenen kalem satırları/modallar da kapsanır;
  `shown.bs.modal` ile JS'in doldurduğu modal tutarları da biçimlenir; sayfa açılışında mevcut
  değerler biçimlenir. İmleç, yazılan rakamın üzerinde kalır. `window.fnSayi = {bicimle, num, uygula, hepsi}`.
- Kural: binlik noktasını JS koyar, ondalık **virgül**; kullanıcının yazdığı nokta yok sayılır
  ("1.500" yazımı da 1500 verir, "12.5" ise 125 olur — ekranda görülür, virgülle düzeltilir).
- `templates/_finans_nav.html`: script tek yerden (`defer`) yükleniyor; nav zaten 10 finans şablonunun
  hepsinde include edildiği için tüm finans sayfaları kapsanır.
- `templates/finans_kucuk_gider.html`: hazır harcama seçilince tutarı dolduran satırdan sonra
  `fnSayi.uygula(tutar)` (modal olmadığı için shown olayı kapsamıyordu).
- `templates/finans_cari_detay.html`: kalem toplamı/kur önizlemesi için yerel `num()` artık `fnSayi.num`
  (eski num "1.250"yi 1,25 okuyordu).
- `finans_cari_service.parse_kur`: virgülsüz "1.250" artık binlik yazım kabul edilir (parse_tutar ile aynı kural).
  `parse_tutar` zaten bu biçimi okuyordu — diğer tüm finans tutarları ondan geçtiği için sunucu tarafı değişmedi.

## Kapsam kontrolü
Tüm `templates/finans_*.html` + `_finans_*.html` inputları tarandı: sayı alanlarının **tamamı**
`inputmode="decimal"` taşıyor (tutar, kalem adet/fiyat, kur, varsayılan tutar, hak ediş, düzeltme tutarı,
tanımlar gider adı tutarı) → tek seçici hepsini kapsıyor.

## Doğrulama
- Node ile bicimle/num/imleç birim testleri (scratchpad, 22 senaryo) geçti; `node --check` temiz.
- `py -W ignore -m unittest discover -s tests -p "test_finans_*.py"` → 45 test OK (parse_kur binlik testi eklendi).
- `parse_tutar`/`parse_kur` elle sınandı: 100.000 / 1.234.567 / 1.234,56 / 0,50 / 41,25 doğru.
- Jinja parse geçti. Tarayıcıda gerçek sayfada denenmedi; deploy YAPILMADI.

## Yayına alma
DB değişikliği yok: `git pull && systemctl restart gullupanel.service` (yeni static dosya için
tarayıcıda sert yenileme gerekebilir).
