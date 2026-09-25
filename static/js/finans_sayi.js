/* Finans — sayı giriş alanlarında canlı binlik ayırıcı: 100000 yazarken 100.000 görünür.
 *
 * Kapsam: finans sayfalarındaki her input[inputmode="decimal"] (tutar, fiyat, adet, kur);
 * sonradan eklenen satırlar/modallar da olay delegasyonuyla kapsanır.
 * Kural: binlik noktasını bu dosya koyar, ondalık için virgül kullanılır; kullanıcının
 * yazdığı nokta yok sayılır ("1.500" yazımı da doğru sonucu verir).
 * Sunucu tarafı (finans_service.parse_tutar / finans_cari_service.parse_kur) bu biçimi okur.
 */
(function () {
  var SECICI = 'input[inputmode="decimal"]';

  function grupla(tam) {
    return tam.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  /** '100000' → '100.000', '1234,5' → '1.234,5' (ondalık hane sayısına dokunmaz). */
  function bicimle(ham) {
    var s = String(ham === null || ham === undefined ? '' : ham).replace(/[^\d,]/g, '');
    var i = s.indexOf(',');
    var tam = (i < 0 ? s : s.slice(0, i)).replace(/^0+(?=\d)/, '');
    if (i < 0) return grupla(tam);
    return grupla(tam) + ',' + s.slice(i + 1).replace(/,/g, '');
  }

  /** '1.250,50' → 1250.5 (nokta binlik, virgül ondalık). */
  function num(v) {
    v = String(v === null || v === undefined ? '' : v).trim().replace(/\./g, '').replace(',', '.');
    return parseFloat(v) || 0;
  }

  /** Alanı biçimlendirir; yazarken imlecin bulunduğu rakamda kalmasını sağlar. */
  function uygula(el) {
    if (!el || typeof el.value !== 'string') return;
    var yeni = bicimle(el.value);
    if (yeni === el.value) return;
    var odakta = document.activeElement === el, solda = 0;
    if (odakta) {
      var kesit = el.value.slice(0, el.selectionStart === null ? el.value.length : el.selectionStart);
      solda = (kesit.match(/[\d,]/g) || []).length;
    }
    el.value = yeni;
    if (!odakta) return;
    var sayac = 0, i = 0;
    for (; i < yeni.length && sayac < solda; i++) {
      if (/[\d,]/.test(yeni.charAt(i))) sayac++;
    }
    try { el.setSelectionRange(i, i); } catch (e) { /* bazı tarayıcılarda desteklenmez */ }
  }

  function hepsi(kok) {
    (kok || document).querySelectorAll(SECICI).forEach(uygula);
  }

  document.addEventListener('input', function (e) {
    var el = e.target;
    if (el && el.matches && el.matches(SECICI)) uygula(el);
  });

  // Modal açılışında JS ile doldurulan tutarlar da biçimli görünsün (Bootstrap olayı document'a çıkar).
  document.addEventListener('shown.bs.modal', function (e) { hepsi(e.target); });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { hepsi(); });
  } else {
    hepsi();
  }

  window.fnSayi = { bicimle: bicimle, num: num, uygula: uygula, hepsi: hepsi };
})();
