// Mini kargo rozeti (istemci tarafı). Firma tespiti SUNUCUDA yapılır
// (kargo_degistir.kargo_firma_tespit: takip no ön eki 733→TEX, 728→DHL, yoksa kargo adı);
// burada yalnız {kod, kisa, ad, bg, fg} sözlüğü işaretlemeye çevrilir.
// Jinja karşılığı: {{ kargo_rozet(takip_no, kargo_adi) }} — aynı sınıf ve nitelikler.
(function () {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  window.kargoRozetHtml = function (firma, buyuk) {
    if (!firma || !firma.kisa) return '';
    return `<span class="kargo-rozet${buyuk ? ' kargo-rozet--lg' : ''}" data-kargo-kod="${esc(firma.kod)}" title="${esc(firma.ad)}" style="background:${esc(firma.bg)};color:${esc(firma.fg)}">${esc(firma.kisa)}</span>`;
  };
})();
