# 2026-10-12 — Finans iptal/sil düğmeleri hiç çalışmıyordu (tojson + çift tırnak)

Kullanıcı: Düzenli Ödemeler'de Halı Saha ödemesinin "✕ İptal" düğmesine basıyor, hiçbir şey olmuyor.

## Kök neden
`onclick="fnIptal({{ id }}, {{ aciklama | tojson }})"` — Flask `tojson` çift tırnaklı JSON üretir
(`"Halı Saha …"`), çift tırnaklı özniteliği erkenden kapatır → tarayıcı `fnIptal(5, ` görür → SyntaxError,
tıklama sessizce boşa gider. Açıklaması boş olmayan her kayıtta bozuk (yani pratikte hep).

## Düzeltme
- Öznitelik tek tırnağa alındı: `onclick='fnIptal(…, {{ x | tojson }})'` (Flask tojson tek tırnağı ''ye çevirir → güvenli).
- Aynı kusurlu 7 yer: finans_ana_gider (İptal), finans_panel, finans_defter, finans_kucuk_gider, finans_gelir
  (fnIptal) ve finans_tanimlar (fnKatSil, fnGaSil — kategori/gider adı silme de çalışmıyordu).
- tests/test_finans_iptal_dugmesi.py: finans şablonlarında `onclick="…| tojson` kalıbı kalmasın + tek tırnaklı
  özniteliğin tek parça kaldığı render kanıtı.
- Test ortamı: 0174448 (menü katalogdan) sonrası `sayfa_erisebilir` Jinja global'i yalıtılmış testlerde yoktu → 7 HTTP
  render testi önceden de kırıktı; test_finans_calisan / test_finans_kart'a sahte global eklendi (uygulama kodu değil).
- Finans testleri 109 OK. Şema yok. Canlı/deploy YOK.

## Yayına alma
`git pull && systemctl restart gullupanel.service`
