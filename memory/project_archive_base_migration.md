# archive.html base.html'e taşındı (12. taşıma)

- `templates/archive.html` (eski 1169 satır standalone) → `{% extends "base.html" %}` + 4 blok
  (title, extra_css, content, scripts).
- Silinenler: DOCTYPE/html/head/body, inline dark-mode script, BS 5.3.0 CSS+bundle,
  font-awesome linki, dark-mode.css linki, kendi jQuery 3.6.0'ı, çift notification_popup.
  (base 5.3.3 CSS+bundle + jQuery 3.7.1 + font/ikon + notification_popup sağlıyor.)
- Container kararı: kendi `<div class="container mt-5">` sarmalayıcısı KALDIRILDI (base'inkiyle
  BİREBİR aynıydı). Nested container / nötrleme rule'una gerek olmadı; sayfaya özgü
  `.container{max-width:1200px}` base'in container'ını hedefliyor.
- :root yoktu → budama yok. #B76E79/#A05F6A yoktu → 0 hex→var dönüşümü.
  Tüm sayfaya özgü CSS extra_css'te aynen korundu (byte-identical gullu-common dupe yok).
- jQuery 3.6→3.7: kullanılan API'ler ($.post/.fail/.find/.addClass/.removeClass/.text/
  .fadeOut/$(this).remove) 3.7'de değişmedi → uyumlu. bootstrap.Modal/getInstance yok;
  yalnız native show.bs.modal + data-bs öznitelikleri (5.3.3 uyumlu).
- gullu-common `* {margin:0;padding:0}` reset artık uygulanıyor (11 önceki taşımayla
  tutarlı); archive utility-margin bazlı olduğu için düşük risk.
- Doğrulama: venv Jinja2 get_template COMPILE OK; 4 blok dengeli; blok dışı içerik yok;
  çift jquery/bootstrap/notification_popup/app-shell = 0; url_for + modal id↔JS eşleşmesi tam.
- Commit YAPILMADI (istek gereği).
