/* Sipariş Hazırla — Telefon Eşlik (PC tarafı)
 *
 * "📱 Telefon" düğmesi → /pc/baslat → QR pencerede. Eşleşme varken ~1 sn'de bir /pc/senkron:
 * sayfanın anlık görüntüsü (aktif sipariş + kartlar + raf/kutu kutularının durumu) DOM'dan
 * okunup gönderilir (yalnız değişince), telefondan gelen okutmalar sayfadaki GERÇEK kutulara
 * yazılıp Enter tetiklenir — mevcut raf doğrulaması / paketleme akışı hiç değişmez.
 * Eşleşme kimliği sessionStorage'da: sayfa yenilenince (sıralı mod geçişi vb.) bağlantı kopmaz.
 */
(function () {
  'use strict';
  var cfg = document.getElementById('telefonPcCfg');
  if (!cfg) return;
  var URL_BASLAT = cfg.dataset.urlBaslat, URL_SENKRON = cfg.dataset.urlSenkron, URL_KES = cfg.dataset.urlKes;
  var DEPO_ANAHTAR = 'hazirlaTelefonPcEslesme', DEPO_OKUTMA = 'hazirlaTelefonPcSonOkutma', DEPO_CIHAZ = 'hazirlaTelefonPcCihaz';
  var ARALIK_MS = 1000;

  var eslesmeId = null, cihazAnahtar = null, sonOkutmaId = 0, sonPayloadJson = null, tur = null, qrSayac = null;
  var bagliydi = false, modal = null, kalanSn = 0;

  var $ = function (id) { return document.getElementById(id); };
  function post(url, body) {
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      body: JSON.stringify(body || {}) }).then(function (r) { return r.json(); });
  }
  function toast(msg, tip) { if (window.gsToast) gsToast(msg, tip || 'info'); }
  function normRaf(s) { return (s || '').trim().toUpperCase().replace(/[=*]/g, '-'); }
  function depoYaz(k, v) { try { if (v == null) sessionStorage.removeItem(k); else sessionStorage.setItem(k, String(v)); } catch (e) {} }
  function depoOku(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }

  // ── Rozet ──
  function rozet(durum, metin) {
    var el = $('telefonDurum'); if (!el) return;
    el.className = 'telefon-rozet ' + durum; el.textContent = metin;
    var btn = $('telefonBtn'); if (btn) btn.classList.toggle('bagli', durum === 'bagli');
  }

  // ── Görüntü: sayfadaki gerçek kutulardan ──
  function kalemOlustur(kart, idx) {
    var img = kart.querySelector('.product-image');
    var baslik = kart.querySelector('.card-title');
    var barkodEl = kart.querySelector('#productBarcode-' + idx);
    var raflar = Array.prototype.map.call(kart.querySelectorAll('.raf-bilgi-list span'), function (s) {
      var m = (s.textContent || '').trim().match(/^(.+?)\s+—\s+(\d+)\s*adet/);
      return { kod: m ? m[1].trim() : (s.textContent || '').trim(), adet: m ? +m[2] : 0,
               onerilen: (s.getAttribute('style') || '').indexOf('#e8f5e9') >= 0 };
    });
    var rafIn = kart.querySelector('.raf-kodu-input');
    var raf = null;
    if (rafIn) {
      var v = rafIn.value.trim(), gecerli = (rafIn.dataset.raflar || '').split(',').map(normRaf).filter(Boolean);
      raf = { deger: v, ok: !!v && (!gecerli.length || gecerli.indexOf(normRaf(v)) !== -1),
              yanlis: !!v && gecerli.length > 0 && gecerli.indexOf(normRaf(v)) === -1,
              kaynak: rafIn.classList.contains('tel-okutma') ? 'telefon' : 'pc' };
    }
    var kutular = Array.prototype.map.call(kart.querySelectorAll('.barkod-input'), function (inp) {
      var val = inp.value.trim();
      return { q: +inp.dataset.quantityIndex, deger: val, ok: inp.dataset.confirmed === 'true',
               yanlis: !!val && inp.dataset.confirmed !== 'true' && (inp.style.backgroundColor || '').indexOf('255, 233, 233') >= 0,
               kaynak: inp.classList.contains('tel-okutma') ? 'telefon' : 'pc' };
    });
    var uyari = kart.querySelector('.alert-warning'), stokYok = kart.querySelector('.alert-danger');
    return {
      idx: idx,
      sku: baslik ? baslik.textContent.trim() : '',
      barkod: barkodEl ? barkodEl.textContent.trim() : '',
      gorsel: img ? (img.getAttribute('data-image-src') || img.src) : '',
      adet: kutular.length,
      raflar: raflar,
      raf_gerekli: !!rafIn,
      raf: raf,
      kutular: kutular,
      onerilen_bosaldi: !!(uyari && uyari.textContent.indexOf('boşalmış') >= 0),
      stok_yok: !!(stokYok && stokYok.textContent.indexOf('Stokta yok') >= 0)
    };
  }

  function payloadOlustur() {
    var od = $('order-data');
    var orderNo = od ? (od.dataset.orderNumber || '') : '';
    if (!orderNo) return { order_number: '', kalemler: [] };
    var badge = document.querySelector('.active-order-title .order-badge');
    var kaynak = document.querySelector('.active-order-title .badge[style*="96bf48"]') ? 'SHOPIFY' : 'TRENDYOL';
    var kargoEl = document.querySelector('.active-order-title .badge.kargo-dhl, .active-order-title .badge.kargo-tyex');
    var kapida = document.querySelector('.active-order-title .badge.bg-danger');
    var yf = $('yazdirForm');
    var musteri = yf ? ((yf.customer_name ? yf.customer_name.value : '') + ' ' + (yf.customer_surname ? yf.customer_surname.value : '')).trim() : '';
    var notEl = $('siparisNotuMetin'), notBanner = $('siparisNotuBanner');
    var kartlar = document.querySelectorAll('#packingForm .product-card');
    var onayla = $('onaylaBtn');
    return {
      order_number: orderNo,
      gosterim_no: badge ? badge.textContent.trim() : orderNo,
      kaynak: kaynak,
      kargo: kargoEl ? kargoEl.textContent.replace('🚚', '').trim() : '',
      kapida_odeme: kapida ? kapida.textContent.replace('💰', '').trim() : '',
      musteri: musteri,
      not: (notBanner && !notBanner.classList.contains('d-none') && notEl) ? notEl.textContent.trim() : '',
      manuel: od.dataset.manuelMod === 'true',
      tamam: !!(onayla && !onayla.disabled),
      kalemler: Array.prototype.map.call(kartlar, kalemOlustur)
    };
  }

  // ── Telefondan gelen okutmayı gerçek kutuya yaz ──
  function enter(el) {
    el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
  }
  function uygula(o) {
    var kart = document.querySelectorAll('#packingForm .product-card')[o.kalem];
    if (!kart) return;
    var hedef = null;
    if (o.tip === 'raf') hedef = kart.querySelector('.raf-kodu-input');
    else hedef = kart.querySelector('#barkodInput-right-' + o.kalem + '-' + o.adet);
    if (!hedef) return;
    if (hedef.readOnly || hedef.dataset.confirmed === 'true') return;   // zaten doğrulanmış: üstüne yazma
    hedef.value = o.deger;
    hedef.classList.add('tel-okutma');
    hedef.title = '📱 Telefondan okutuldu';
    hedef.dispatchEvent(new Event('input', { bubbles: true }));
    enter(hedef);
  }

  // ── Senkron turu ──
  function turPlanla(ms) {
    if (tur) clearTimeout(tur);
    if (!eslesmeId) return;
    tur = setTimeout(turCalistir, ms == null ? ARALIK_MS : ms);
  }
  function turCalistir() {
    if (!eslesmeId) return;
    var p = payloadOlustur(), pj = JSON.stringify(p);
    var govde = { eslesme_id: eslesmeId, anahtar: cihazAnahtar, son_okutma_id: sonOkutmaId };
    if (pj !== sonPayloadJson) govde.payload = p;
    post(URL_SENKRON, govde).then(function (j) {
      if (!j.success) { bitti('yok', null); return; }
      if (govde.payload) sonPayloadJson = pj;
      kalanSn = j.kalan_sn || 0;
      if (j.durum === 'bagli') {
        if (!bagliydi) { bagliydi = true; toast('📱 ' + (j.telefon_kullanici || 'Telefon') + ' bağlandı', 'success'); if (modal) modal.hide(); }
        rozet('bagli', '📱 ' + (j.telefon_kullanici || 'Telefon') + ' · ' + sureYaz(kalanSn));
        var degisti = false;
        (j.okutmalar || []).forEach(function (o) { uygula(o); sonOkutmaId = Math.max(sonOkutmaId, o.id); degisti = true; });
        depoYaz(DEPO_OKUTMA, sonOkutmaId);
        turPlanla(degisti ? 400 : null);   // doğrulama 300 ms sonra biter; yeni görüntü hemen gitsin
      } else if (j.durum === 'bekliyor') {
        rozet('bekliyor', '📱 QR bekleniyor');
        turPlanla();
      } else {
        bitti(j.durum, j.kapanma_sebebi);
      }
    }).catch(function () { turPlanla(3000); });
  }
  function sureYaz(sn) { var m = Math.floor(sn / 60), s = sn % 60; return m + ':' + (s < 10 ? '0' : '') + s; }

  function bitti(durum, sebep) {
    if (tur) clearTimeout(tur); tur = null;
    eslesmeId = null; cihazAnahtar = null; bagliydi = false; sonPayloadJson = null;
    depoYaz(DEPO_ANAHTAR, null); depoYaz(DEPO_OKUTMA, null); depoYaz(DEPO_CIHAZ, null);
    var metin = 'Bağlı değil';
    if (durum === 'suresi_doldu') { metin = '⏱️ Süre doldu'; toast('📱 Telefon bağlantısı 10 dk hareketsizlikten kapandı', 'warning'); }
    else if (sebep === 'telefon_kes') { metin = 'Telefon ayrıldı'; toast('📱 Telefon bağlantıyı kesti', 'info'); }
    else if (sebep === 'qr_suresi') { metin = 'QR süresi doldu'; }
    rozet('kapali', metin);
    if ($('telefonQrKutu')) $('telefonQrKutu').classList.add('d-none');
    if ($('telefonKapaliKutu')) $('telefonKapaliKutu').classList.remove('d-none');
  }

  // ── QR başlat ──
  function baslat() {
    post(URL_BASLAT, { eski_eslesme_id: eslesmeId, eski_anahtar: cihazAnahtar }).then(function (j) {
      if (!j.success) { toast('QR üretilemedi', 'danger'); return; }
      eslesmeId = j.eslesme_id; cihazAnahtar = j.anahtar; sonOkutmaId = 0; sonPayloadJson = null; bagliydi = false;
      depoYaz(DEPO_ANAHTAR, eslesmeId); depoYaz(DEPO_OKUTMA, 0); depoYaz(DEPO_CIHAZ, cihazAnahtar);
      $('telefonQr').src = j.qr; $('telefonUrl').textContent = j.url; $('telefonToken').textContent = j.token;
      $('telefonQrKutu').classList.remove('d-none'); $('telefonKapaliKutu').classList.add('d-none');
      rozet('bekliyor', '📱 QR bekleniyor');
      var kalan = j.gecerlilik_sn || 120;
      if (qrSayac) clearInterval(qrSayac);
      $('telefonQrSayac').textContent = sureYaz(kalan);
      qrSayac = setInterval(function () { kalan--; if (kalan <= 0) { clearInterval(qrSayac); } $('telefonQrSayac').textContent = sureYaz(Math.max(0, kalan)); }, 1000);
      turPlanla(0);
    }).catch(function () { toast('Sunucuya ulaşılamadı', 'danger'); });
  }

  function kes() {
    if (!eslesmeId) return;
    post(URL_KES, { eslesme_id: eslesmeId, anahtar: cihazAnahtar }).catch(function () {});
    bitti('kapandi', 'pc_kes');
    toast('📱 Telefon bağlantısı kesildi', 'info');
  }

  // ── UI bağla ──
  var btn = $('telefonBtn');
  if (btn) btn.addEventListener('click', function () {
    if (window.bootstrap && $('telefonModal')) { modal = modal || new bootstrap.Modal($('telefonModal')); modal.show(); }
    if (!eslesmeId) baslat();
  });
  if ($('telefonYeniQrBtn')) $('telefonYeniQrBtn').addEventListener('click', baslat);
  if ($('telefonKesBtn')) $('telefonKesBtn').addEventListener('click', kes);
  if ($('telefonModal')) $('telefonModal').addEventListener('show.bs.modal', function () {
    // Bağlıyken pencere: durum + kes düğmesi; QR yalnız beklerken
    var bagli = !!eslesmeId && bagliydi;
    $('telefonQrKutu').classList.toggle('d-none', bagli || !eslesmeId);
    $('telefonBagliKutu').classList.toggle('d-none', !bagli);
    $('telefonKapaliKutu').classList.toggle('d-none', !!eslesmeId);
  });
  setInterval(function () {
    if (!eslesmeId || !bagliydi) return;
    if (kalanSn > 0) kalanSn--;
    var el = $('telefonDurum'); if (el) el.textContent = el.textContent.replace(/\d+:\d\d$/, sureYaz(kalanSn));
    if ($('telefonBagliSure')) $('telefonBagliSure').textContent = sureYaz(kalanSn);
  }, 1000);

  // Sayfa yenilendi (sıralı mod geçişi vb.): eşleşme bağlıysa devam
  var eskiId = depoOku(DEPO_ANAHTAR), eskiCihaz = depoOku(DEPO_CIHAZ);
  if (eskiId && eskiCihaz) {
    eslesmeId = +eskiId; cihazAnahtar = eskiCihaz; sonOkutmaId = +(depoOku(DEPO_OKUTMA) || 0);
    rozet('bekliyor', '📱 Bağlanıyor…');
    turPlanla(0);
  } else {
    rozet('kapali', 'Bağlı değil');
  }
})();
