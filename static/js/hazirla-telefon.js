/* Sipariş Hazırla — Telefon Eşlik (telefon tarafı)
 *
 * QR okut → /bagla → eşleşme. Sonra ~1 sn'de bir /telefon/senkron: PC'nin yazdığı ekran görüntüsü
 * (sipariş + kalemler + kutuların durumu) sürüm değişince yeniden çizilir. Okutulan raf/ürün
 * /telefon/okut ile olay olarak gider; PC kendi kutusuna yazar, doğrular ve bir sonraki görüntüde
 * kutu "ok" olarak döner (telefonda yeşil). Telefon stok düşürmez.
 */
(function () {
  'use strict';
  var app = document.getElementById('telefonApp');
  if (!app) return;

  var URL_BAGLA = app.dataset.urlBagla, URL_SENKRON = app.dataset.urlSenkron,
      URL_OKUT = app.dataset.urlOkut, URL_KES = app.dataset.urlKes;
  var DEPO_ANAHTAR = 'hazirlaTelefonEslesme', DEPO_CIHAZ = 'hazirlaTelefonCihaz';
  var ARALIK_MS = 1000, ARALIK_ARKA_MS = 3000;

  var eslesmeId = null, cihazAnahtar = null, surum = -1, yapiAnahtari = '', kalanSn = 0, tur = null, sayacTimer = null;
  var gonderilen = {};   // "tip:kalem:adet" → PC'ye gittiği an (onay bekleniyor)
  var qrTarayici = null, barkodTarayici = null;

  var $ = function (id) { return document.getElementById(id); };
  function post(url, body) {
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      body: JSON.stringify(body || {}) }).then(function (r) { return r.json().then(function (j) { j._status = r.status; return j; }); });
  }
  function ekran(ad) {
    ['ekranBagla', 'ekranBagli'].forEach(function (k) { $(k).classList.toggle('aktif', k === ad); });
  }
  function mesaj(metin, tur) {
    var el = $('baglaMesaj'); el.textContent = metin || ''; el.className = 'tel-mesaj' + (metin ? ' ' + (tur || 'bilgi') : '');
  }
  function titret(ms) { try { if (navigator.vibrate) navigator.vibrate(ms || 60); } catch (e) {} }
  function normRaf(s) { return (s || '').trim().toUpperCase().replace(/[=*]/g, '-'); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }

  // ── Jeton: QR içeriği "…/hazirla-telefon/?t=JETON" ya da çıplak jeton ──
  function tokenAyikla(metin) {
    metin = (metin || '').trim();
    var m = metin.match(/[?&]t=([A-Za-z0-9_\-]+)/);
    return m ? m[1] : metin;
  }

  // ── Bağlan ──
  function bagla(token) {
    token = tokenAyikla(token);
    if (!token) { mesaj('QR kodu okutun.', 'hata'); return; }
    $('baglaBtn').disabled = true; mesaj('Bağlanıyor…', 'bilgi');
    post(URL_BAGLA, { token: token }).then(function (j) {
      $('baglaBtn').disabled = false;
      if (!j.success) { mesaj(j.error || 'Bağlanamadı.', 'hata'); titret([80, 60, 80]); return; }
      mesaj('');
      qrTarayiciKapat();
      bagliBaslat(j);
    }).catch(function () { $('baglaBtn').disabled = false; mesaj('Sunucuya ulaşılamadı.', 'hata'); });
  }

  function bagliBaslat(durum) {
    eslesmeId = durum.eslesme_id;
    if (durum.anahtar) cihazAnahtar = durum.anahtar;
    try { sessionStorage.setItem(DEPO_ANAHTAR, String(eslesmeId)); sessionStorage.setItem(DEPO_CIHAZ, cihazAnahtar || ''); } catch (e) {}
    surum = -1; yapiAnahtari = ''; gonderilen = {};
    $('pcAd').textContent = 'PC: ' + (durum.pc_kullanici || '—');
    ekran('ekranBagli');
    $('ekranKapandi').classList.remove('goster');
    titret(80);
    uygula(durum);
    turPlanla(0);
    sayacBaslat();
  }

  // ── Senkron turu ──
  function turPlanla(ms) {
    if (tur) clearTimeout(tur);
    if (!eslesmeId) return;
    tur = setTimeout(turCalistir, ms == null ? (document.hidden ? ARALIK_ARKA_MS : ARALIK_MS) : ms);
  }
  function turCalistir() {
    if (!eslesmeId) return;
    post(URL_SENKRON, { eslesme_id: eslesmeId, anahtar: cihazAnahtar }).then(function (j) {
      if (!j.success) { kapandi('yok'); return; }
      uygula(j);
      turPlanla();
    }).catch(function () { $('pcNokta').classList.add('kopuk'); turPlanla(ARALIK_ARKA_MS); });
  }

  function uygula(j) {
    if (j.durum !== 'bagli') { kapandi(j.durum, j.kapanma_sebebi); return; }
    kalanSn = j.kalan_sn || 0; sayacYaz();
    $('pcNokta').classList.toggle('kopuk', !j.pc_canli);
    if (j.surum !== surum) { surum = j.surum; ciz(j.payload); }
  }

  // ── Kapanış ──
  function kapandi(durum, sebep) {
    eslesmeId = null; cihazAnahtar = null; if (tur) clearTimeout(tur); tur = null;
    if (sayacTimer) clearInterval(sayacTimer); sayacTimer = null;
    try { sessionStorage.removeItem(DEPO_ANAHTAR); sessionStorage.removeItem(DEPO_CIHAZ); } catch (e) {}
    var baslik = 'Bağlantı kapandı', metin = 'Bilgisayarda yeni QR üretip tekrar bağlan.';
    if (durum === 'suresi_doldu') { baslik = 'Süre doldu'; metin = '10 dakika işlem yapılmadı, güvenlik için bağlantı kapatıldı.'; }
    else if (sebep === 'pc_kapandi') { metin = 'Bilgisayardaki sipariş hazırla sayfası kapandı.'; }
    else if (sebep === 'pc_kes') { metin = 'Bilgisayardan bağlantı kesildi.'; }
    else if (sebep === 'yeni_qr') { metin = 'Bilgisayarda yeni bir QR üretildi; bu bağlantı kapandı.'; }
    else if (sebep === 'telefon_kes') { metin = 'Bağlantıyı sen kapattın.'; }
    $('kapandiBaslik').textContent = baslik; $('kapandiMetin').textContent = metin;
    $('ekranKapandi').classList.add('goster');
    titret([120, 80, 120]);
  }
  function yenidenBagla() {
    $('ekranKapandi').classList.remove('goster');
    $('kalemler').innerHTML = ''; $('siparisBaslik').style.display = 'none'; $('sipBos').style.display = '';
    $('tokenInput').value = ''; mesaj('');
    ekran('ekranBagla');
    setTimeout(function () { $('tokenInput').focus(); }, 100);
  }

  // ── Hareketsizlik sayacı (sunucu değeri; yerel geri sayım yalnız gösterim) ──
  function sayacYaz() {
    var el = $('kalanSure'); var m = Math.floor(kalanSn / 60), s = kalanSn % 60;
    el.textContent = m + ':' + (s < 10 ? '0' : '') + s;
    el.classList.toggle('az', kalanSn <= 60);
  }
  function sayacBaslat() {
    if (sayacTimer) clearInterval(sayacTimer);
    sayacTimer = setInterval(function () { if (kalanSn > 0) { kalanSn--; sayacYaz(); } }, 1000);
  }

  // ── Çizim: yapı (sipariş + kalem/adet) değişince kartlar baştan; aksi halde yalnız durumlar ──
  function yapiHesapla(p) {
    if (!p || !p.order_number) return 'bos';
    return p.order_number + '|' + (p.kalemler || []).map(function (k) { return k.idx + ':' + k.adet + ':' + (k.raf_gerekli ? 1 : 0); }).join(',');
  }
  function ciz(p) {
    var anahtar = yapiHesapla(p);
    if (anahtar !== yapiAnahtari) { yapiAnahtari = anahtar; gonderilen = {}; kartlariKur(p); }
    durumlariGuncelle(p);
  }

  function kartlariKur(p) {
    var kalemler = $('kalemler'); kalemler.innerHTML = '';
    var bos = !p || !p.order_number;
    $('sipBos').style.display = bos ? '' : 'none';
    $('siparisBaslik').style.display = bos ? 'none' : '';
    $('sipTamam').classList.remove('goster');
    if (bos) { $('sipNot').style.display = 'none'; return; }

    $('sipNo').textContent = p.gosterim_no || p.order_number;
    var roz = [];
    roz.push(p.kaynak === 'SHOPIFY' ? '<span class="tel-rozet shopify">🛍️ Shopify</span>' : '<span class="tel-rozet trendyol">📦 Trendyol</span>');
    if (p.kargo) {
      var kl = p.kargo.toLowerCase();
      roz.push('<span class="tel-rozet ' + (kl.indexOf('dhl') >= 0 ? 'dhl' : (kl.indexOf('trendyol') >= 0 || kl.indexOf('tyex') >= 0) ? 'tyex' : '') + '">🚚 ' + esc(p.kargo) + '</span>');
    }
    if (p.kapida_odeme) roz.push('<span class="tel-rozet kapida">💰 ' + esc(p.kapida_odeme) + '</span>');
    $('sipRozetler').innerHTML = roz.join('');
    $('sipMusteri').textContent = p.musteri || '';
    $('sipNot').style.display = p.not ? '' : 'none'; $('sipNot').textContent = p.not ? '📝 ' + p.not : '';

    (p.kalemler || []).forEach(function (k) {
      var kart = document.createElement('div');
      kart.className = 'tel-kart'; kart.dataset.kalem = k.idx;
      var html = '';
      if (k.gorsel) html += '<img class="tel-gorsel" src="' + esc(k.gorsel) + '" alt="">';
      html += '<div class="tel-govde">';
      html += '<div class="tel-sku">' + esc(k.sku || k.ad || '') + '</div>';
      html += '<div class="tel-meta">Barkod: <strong>' + esc(k.barkod || '') + '</strong> &nbsp; Adet: <span class="adet' + (k.adet > 1 ? ' coklu' : '') + '">' + esc(k.adet) + '</span></div>';
      if (k.raflar && k.raflar.length) {
        html += '<div class="tel-raflar">' + k.raflar.map(function (r) {
          return '<span class="tel-raf-chip' + (r.onerilen ? ' onerilen' : '') + '" data-kod="' + esc(r.kod) + '">📍 ' + esc(r.kod) + ' <small>' + esc(r.adet) + ' adet</small></span>';
        }).join('') + '</div>';
      }
      if (k.onerilen_bosaldi) html += '<div class="tel-uyari sari">⚠️ Atanan raf boşalmış, alternatif raftan al.</div>';
      if (k.stok_yok) html += '<div class="tel-uyari kirmizi">❌ Stokta yok — hiçbir rafta bulunmuyor.</div>';
      if (k.raf_gerekli) {
        html += '<div class="tel-alan raf" data-tip="raf" data-kalem="' + k.idx + '" data-adet="0"><label>📍 RAF BARKODU</label>' +
          '<input type="text" inputmode="text" autocomplete="off" autocapitalize="characters" placeholder="Rafı okut"><div class="durum"></div></div>';
      }
      for (var q = 0; q < (k.adet || 1); q++) {
        html += '<div class="tel-alan urun" data-tip="urun" data-kalem="' + k.idx + '" data-adet="' + q + '"><label>📦 KUTU BARKODU (' + (q + 1) + ')</label>' +
          '<input type="text" inputmode="numeric" autocomplete="off" placeholder="Ürünü okut"><div class="durum"></div></div>';
      }
      html += '</div>';
      kart.innerHTML = html;
      kalemler.appendChild(kart);
    });
    alanlariBagla();
    titret(40);
  }

  function alanlariGetir() { return Array.prototype.slice.call(document.querySelectorAll('#kalemler .tel-alan')); }
  function alanAnahtar(a) { return a.dataset.tip + ':' + a.dataset.kalem + ':' + a.dataset.adet; }

  function durumlariGuncelle(p) {
    if (!p || !p.order_number) return;
    var harita = {};
    (p.kalemler || []).forEach(function (k) {
      if (k.raf_gerekli) harita['raf:' + k.idx + ':0'] = k.raf || {};
      (k.kutular || []).forEach(function (ku) { harita['urun:' + k.idx + ':' + ku.q] = ku; });
    });
    alanlariGetir().forEach(function (a) {
      var key = alanAnahtar(a), d = harita[key] || {}, inp = a.querySelector('input'), durum = a.querySelector('.durum');
      var beklemede = gonderilen[key] && (Date.now() - gonderilen[key] < 8000);
      a.classList.remove('ok', 'bekliyor', 'yanlis');
      if (d.ok) {
        a.classList.add('ok'); inp.value = d.deger || inp.value; inp.readOnly = true;
        durum.textContent = (d.kaynak === 'telefon' ? '📱 ' : '🖥️ ') + 'Doğru'; delete gonderilen[key];
      } else if (d.yanlis) {
        a.classList.add('yanlis'); inp.readOnly = false; durum.textContent = '❌ Yanlış — tekrar okut';
        if (!beklemede) inp.value = '';
        delete gonderilen[key];
      } else if (beklemede) {
        a.classList.add('bekliyor'); durum.textContent = '⏳ Bilgisayara gönderildi…';
      } else {
        inp.readOnly = false; durum.textContent = d.deger ? '🖥️ Bilgisayarda yazıldı: ' + d.deger : '';
      }
    });
    // Kart tamam / aktif kart
    document.querySelectorAll('#kalemler .tel-kart').forEach(function (kart) {
      var alanlar = kart.querySelectorAll('.tel-alan');
      var tamam = alanlar.length > 0 && Array.prototype.every.call(alanlar, function (a) { return a.classList.contains('ok'); });
      kart.classList.toggle('tamam', tamam);
    });
    $('sipTamam').classList.toggle('goster', !!p.tamam);
    odakla();
  }

  // Odak: ilk okutulmamış alan (raf önce), kart vurgusu
  function odakla() {
    var hedef = alanlariGetir().filter(function (a) { return !a.classList.contains('ok') && !a.classList.contains('bekliyor'); })[0];
    document.querySelectorAll('#kalemler .tel-kart').forEach(function (k) { k.classList.remove('aktif-kart'); });
    if (!hedef) return;
    var kart = hedef.closest('.tel-kart'); if (kart) kart.classList.add('aktif-kart');
    var aktif = document.activeElement;
    if (!aktif || !aktif.closest || !aktif.closest('#kalemler .tel-alan') || aktif.readOnly) {
      var inp = hedef.querySelector('input');
      setTimeout(function () { try { inp.focus({ preventScroll: false }); } catch (e) {} }, 60);
    }
  }

  function alanlariBagla() {
    alanlariGetir().forEach(function (a) {
      var inp = a.querySelector('input');
      // Okuyucu (Zebra klavye modu) Enter/Tab sonekiyle biter; elle yazımda da Enter ile gönderilir
      inp.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== 'Tab') return;
        e.preventDefault(); okut(a);
      });
      inp.addEventListener('input', function () { a.classList.remove('yanlis'); a.querySelector('.durum').textContent = ''; });
    });
  }

  function okut(a) {
    var inp = a.querySelector('input'), deger = inp.value.trim();
    if (!deger || a.classList.contains('ok') || !eslesmeId) return;
    if (a.dataset.tip === 'raf') {
      deger = normRaf(deger); inp.value = deger;
      var kart = a.closest('.tel-kart'), cipler = kart ? kart.querySelectorAll('.tel-raf-chip') : [];
      var gecerli = Array.prototype.map.call(cipler, function (c) { return normRaf(c.dataset.kod); });
      if (gecerli.length && gecerli.indexOf(deger) === -1) {
        a.classList.remove('bekliyor'); a.classList.add('yanlis'); a.querySelector('.durum').textContent = '❌ Bu ürün bu rafta yok, doğru rafı okut';
        inp.value = ''; titret([80, 60, 80]); return;
      }
    }
    var key = alanAnahtar(a);
    gonderilen[key] = Date.now();
    a.classList.remove('yanlis'); a.classList.add('bekliyor'); a.querySelector('.durum').textContent = '⏳ Bilgisayara gönderildi…';
    post(URL_OKUT, { eslesme_id: eslesmeId, anahtar: cihazAnahtar, tip: a.dataset.tip, kalem: +a.dataset.kalem, adet: +a.dataset.adet, deger: deger })
      .then(function (j) {
        if (!j.success) {
          delete gonderilen[key]; a.classList.remove('bekliyor');
          if (j.durum && j.durum !== 'bagli') { kapandi(j.durum); return; }
          a.classList.add('yanlis'); a.querySelector('.durum').textContent = j.error || 'Gönderilemedi'; return;
        }
        titret(50);
        // Sonraki boş alana geç (PC onayı gelince yeşile döner)
        var sonraki = alanlariGetir().filter(function (x) { return x !== a && !x.classList.contains('ok') && !x.classList.contains('bekliyor'); })[0];
        if (sonraki) setTimeout(function () { sonraki.querySelector('input').focus(); }, 50);
        turPlanla(150);
      }).catch(function () { delete gonderilen[key]; a.classList.remove('bekliyor'); a.querySelector('.durum').textContent = 'Sunucuya ulaşılamadı'; });
  }

  // ── Kamera: QR (bağlan) ──
  function kameraHataMetni(e) {
    var ad = (e && (e.name || e)) ? String(e.name || e) : '';
    if (!window.isSecureContext) return 'Tarayıcı kamerayı yalnız HTTPS adreste açar (şu an ' + location.protocol + '). "Fotoğraf Çekerek Okut" ile devam et.';
    if (/NotAllowed|Permission/i.test(ad)) return 'Kamera izni verilmedi. Tarayıcı adres çubuğundaki kilit/kamera simgesinden izin ver ya da "Fotoğraf Çekerek Okut" kullan.';
    if (/NotFound|Devices/i.test(ad)) return 'Kamera bulunamadı. "Fotoğraf Çekerek Okut" ile dene.';
    if (/NotReadable|TrackStart/i.test(ad)) return 'Kamera başka bir uygulama tarafından kullanılıyor. Onu kapatıp tekrar dene.';
    return 'Kamera açılamadı' + (ad ? ' (' + ad + ')' : '') + '. "Fotoğraf Çekerek Okut" ile dene ya da kodu elle gir.';
  }
  function qrTarayiciKapat() {
    if (qrTarayici) { try { qrTarayici.stop().catch(function () {}); } catch (e) {} qrTarayici = null; }
    $('qrReader').innerHTML = ''; $('qrReader').classList.remove('acik');
    $('qrKameraBtn').textContent = '📷 Kamerayla QR Okut';
  }
  function qrTarayiciAc() {
    if (!window.Html5Qrcode) { mesaj('Kamera kütüphanesi yüklenemedi (internet/CDN). Kodu elle gir.', 'hata'); return; }
    if (qrTarayici) { qrTarayiciKapat(); return; }
    mesaj('');
    $('qrReader').classList.add('acik');   // kutu görünür olmalı: kütüphane genişliği buradan ölçer
    $('qrKameraBtn').textContent = '⏹ Kamerayı Kapat';
    qrTarayici = new Html5Qrcode('qrReader');
    qrTarayici.start({ facingMode: 'environment' }, { fps: 10, qrbox: function (w, h) { var k = Math.min(w, h, 280); return { width: k, height: k }; } },
      function (metin) { qrTarayiciKapat(); $('tokenInput').value = metin; bagla(metin); },
      function () {}).catch(function (e) { qrTarayici = null; qrTarayiciKapat(); mesaj(kameraHataMetni(e), 'hata'); });
  }
  // Fotoğraf çekerek okut: HTTPS/izin gerektirmez (telefonun kendi kamera uygulaması açılır)
  function qrFotoOkut(dosya) {
    if (!dosya) return;
    if (!window.Html5Qrcode) { mesaj('Kütüphane yüklenemedi; kodu elle gir.', 'hata'); return; }
    mesaj('Fotoğraf okunuyor…', 'bilgi');
    qrTarayiciKapat();
    var okuyucu = new Html5Qrcode('qrReader');
    okuyucu.scanFile(dosya, false).then(function (metin) {
      try { okuyucu.clear(); } catch (e) {}
      $('tokenInput').value = metin; bagla(metin);
    }).catch(function () {
      try { okuyucu.clear(); } catch (e) {}
      mesaj('Fotoğrafta QR okunamadı; QR kodunu yakından ve net çek ya da kodu elle gir.', 'hata');
    });
  }

  // ── Kamera: barkod (raf / ürün) → odaktaki ya da ilk boş alana yazar ──
  function barkodKameraAc() {
    if (!window.Html5Qrcode) { if (window.gsToast) gsToast('Kamera kütüphanesi yüklenemedi', 'warning'); return; }
    var hedef = (document.activeElement && document.activeElement.closest && document.activeElement.closest('#kalemler .tel-alan')) ||
      alanlariGetir().filter(function (a) { return !a.classList.contains('ok') && !a.classList.contains('bekliyor'); })[0];
    if (!hedef) return;
    $('kameraHedef').textContent = hedef.querySelector('label').textContent;
    $('ekranKamera').classList.add('goster');
    barkodTarayici = new Html5Qrcode('barkodReader');
    barkodTarayici.start({ facingMode: 'environment' }, { fps: 10, qrbox: { width: 280, height: 160 } },
      function (metin) { barkodKameraKapat(); hedef.querySelector('input').value = metin; okut(hedef); },
      function () {}).catch(function (e) { barkodKameraKapat(); if (window.gsToast) gsToast(kameraHataMetni(e), 'warning'); });
  }
  function barkodKameraKapat() {
    $('ekranKamera').classList.remove('goster');
    if (barkodTarayici) { try { barkodTarayici.stop().catch(function () {}); } catch (e) {} barkodTarayici = null; }
    $('barkodReader').innerHTML = '';
  }

  // ── Çık ──
  function cik() {
    if (!eslesmeId) { yenidenBagla(); return; }
    post(URL_KES, { eslesme_id: eslesmeId, anahtar: cihazAnahtar }).catch(function () {});
    kapandi('kapandi', 'telefon_kes');
  }

  // ── Başlangıç ──
  $('qrKameraBtn').addEventListener('click', qrTarayiciAc);
  $('qrFotoBtn').addEventListener('click', function () { $('qrFotoInput').value = ''; $('qrFotoInput').click(); });
  $('qrFotoInput').addEventListener('change', function () { qrFotoOkut(this.files && this.files[0]); });
  $('baglaBtn').addEventListener('click', function () { bagla($('tokenInput').value); });
  $('tokenInput').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); bagla(this.value); } });
  $('cikBtn').addEventListener('click', cik);
  $('yenidenBtn').addEventListener('click', yenidenBagla);
  $('barkodKameraBtn').addEventListener('click', barkodKameraAc);
  $('kameraKapatBtn').addEventListener('click', barkodKameraKapat);
  document.addEventListener('visibilitychange', function () { if (!document.hidden && eslesmeId) turPlanla(0); });

  var otoToken = app.dataset.otoToken;
  var eskiId = null, eskiCihaz = null;
  try { eskiId = sessionStorage.getItem(DEPO_ANAHTAR); eskiCihaz = sessionStorage.getItem(DEPO_CIHAZ); } catch (e) {}
  if (otoToken) { bagla(otoToken); }
  else if (eskiId && eskiCihaz) {
    // Sayfa yenilendi: eşleşme hâlâ bağlıysa kaldığı yerden devam
    cihazAnahtar = eskiCihaz;
    post(URL_SENKRON, { eslesme_id: +eskiId, anahtar: eskiCihaz }).then(function (j) {
      if (j.success && j.durum === 'bagli') bagliBaslat(j);
      else { try { sessionStorage.removeItem(DEPO_ANAHTAR); sessionStorage.removeItem(DEPO_CIHAZ); } catch (e) {} $('tokenInput').focus(); }
    }).catch(function () {});
  } else { setTimeout(function () { $('tokenInput').focus(); }, 100); }
})();
