// Kargo işlem paneli — toplu kargo firması değişiminin onayı ve canlı ilerlemesi.
// Tarayıcının yerel confirm/alert'i YERİNE kullanılır (Chrome uyarısı çıkmaz).
// Bağımsızdır: kendi CSS'ini sayfaya bir kez enjekte eder, kütüphane gerektirmez.
//
// Kullanım:
//   const onay = await KargoIslem.onayla({ baslik, html, okText });        // Promise<bool>
//   const p = KargoIslem.ac({ baslik, altBaslik, satirlar: [{ id, etiket }] });
//   p.adim('Trendyol\'a gönderiliyor', i, n);                              // adım + ilerleme
//   p.satir(id, 'calisiyor' | 'ok' | 'atlandi' | 'hata' | 'bekliyor', mesaj, ekHtml);
//   p.bitir({ ozet, tur: 'success' | 'warning' | 'error' });               // kapat düğmesi açılır
(function () {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const CSS = `
.ki-overlay{position:fixed;inset:0;z-index:2000;display:flex;align-items:center;justify-content:center;padding:16px;
  background:rgba(20,16,18,.45);backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px);opacity:0;transition:opacity .22s ease}
.ki-overlay.ki-show{opacity:1}
.ki-card{width:min(560px,100%);max-height:min(86vh,720px);display:flex;flex-direction:column;background:#fff;color:#1f1b1d;
  border-radius:18px;box-shadow:0 24px 64px rgba(0,0,0,.28);overflow:hidden;transform:translateY(14px) scale(.98);
  transition:transform .26s cubic-bezier(.2,.9,.3,1.2);font-family:Inter,system-ui,Arial,sans-serif}
.ki-overlay.ki-show .ki-card{transform:none}
.ki-head{padding:16px 20px 12px;border-bottom:1px solid #efe9eb}
.ki-title{display:flex;align-items:center;gap:10px;font-weight:800;font-size:1.02rem}
.ki-title .bi,.ki-title .fas{color:#b76e79}
.ki-sub{margin-top:3px;font-size:.82rem;color:#6b6468}
.ki-road{position:relative;height:38px;margin:10px 20px 0;overflow:hidden}
.ki-road::before{content:"";position:absolute;left:0;right:0;bottom:9px;height:0;border-bottom:3px dashed #d9cfd2}
.ki-road.ki-run::before{animation:ki-road 1s linear infinite}
.ki-truck{position:absolute;bottom:4px;left:0;font-size:26px;color:#b76e79;transition:left .5s cubic-bezier(.3,.8,.4,1);
  filter:drop-shadow(0 2px 2px rgba(0,0,0,.18))}
.ki-road.ki-run .ki-truck{animation:ki-bump .55s ease-in-out infinite}
.ki-truck .ki-puff{position:absolute;left:-10px;bottom:4px;width:6px;height:6px;border-radius:50%;background:#cfc5c8;opacity:0}
.ki-road.ki-run .ki-puff{animation:ki-puff 1s ease-out infinite}
.ki-road.ki-run .ki-puff:nth-child(2){animation-delay:.33s}.ki-road.ki-run .ki-puff:nth-child(3){animation-delay:.66s}
.ki-bar{height:8px;margin:8px 20px 0;border-radius:999px;background:#f1ecee;overflow:hidden}
.ki-fill{height:100%;width:0;border-radius:999px;background:linear-gradient(90deg,#b76e79,#e3a2ad);transition:width .4s ease;position:relative}
.ki-fill::after{content:"";position:absolute;inset:0;background:repeating-linear-gradient(45deg,rgba(255,255,255,.28) 0 8px,transparent 8px 16px);
  background-size:24px 24px;animation:ki-stripe .7s linear infinite}
.ki-done .ki-fill::after{animation:none;opacity:0}
.ki-step{display:flex;justify-content:space-between;gap:10px;margin:8px 20px 0;font-size:.82rem;color:#6b6468;min-height:1.2em}
.ki-step b{color:#1f1b1d}
.ki-list{margin:10px 0 0;padding:0 20px 8px;overflow:auto;flex:1;min-height:0}
.ki-row{display:flex;align-items:flex-start;gap:10px;padding:8px 10px;border-radius:10px;font-size:.86rem;
  animation:ki-in .28s ease both}
.ki-row+.ki-row{margin-top:4px}
.ki-row .ki-ic{width:22px;height:22px;flex:0 0 22px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;
  font-size:13px;background:#f1ecee;color:#9a8f94}
.ki-row .ki-no{font-weight:800;white-space:nowrap}
.ki-row .ki-msg{color:#6b6468;flex:1;min-width:0}
.ki-row--calisiyor{background:#fbf5f6}
.ki-row--calisiyor .ki-ic{background:#f6e3e6;color:#b76e79}
.ki-row--calisiyor .ki-ic i{animation:ki-spin 1s linear infinite}
.ki-row--ok .ki-ic{background:#dff5e8;color:#16865c;animation:ki-pop .35s cubic-bezier(.3,1.6,.5,1) both}
.ki-row--atlandi .ki-ic{background:#fff3d6;color:#8a6410}
.ki-row--hata .ki-ic{background:#fde5e3;color:#c0392b;animation:ki-shake .4s ease both}
.ki-row--hata .ki-msg{color:#c0392b}
.ki-foot{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 20px 16px;border-top:1px solid #efe9eb}
.ki-ozet{font-size:.86rem;font-weight:700;flex:1;min-width:0}
.ki-ozet--success{color:#16865c}.ki-ozet--warning{color:#8a6410}.ki-ozet--error{color:#c0392b}
.ki-btn{border:0;border-radius:10px;padding:9px 16px;font-weight:800;font-size:.86rem;cursor:pointer;transition:transform .12s,box-shadow .12s,opacity .2s}
.ki-btn:disabled{opacity:.45;cursor:not-allowed}
.ki-btn--ok{background:#b76e79;color:#fff;box-shadow:0 6px 16px rgba(183,110,121,.35)}
.ki-btn--ok:not(:disabled):hover{transform:translateY(-1px)}
.ki-btn--ghost{background:#f1ecee;color:#1f1b1d}
.ki-body{padding:6px 20px 10px;font-size:.92rem;line-height:1.5}
.ki-body small{display:block;margin-top:6px;color:#6b6468}
html.gs-dark .ki-card{background:#1f1c1e;color:#f1ecee}
html.gs-dark .ki-head,html.gs-dark .ki-foot{border-color:#332e30}
html.gs-dark .ki-sub,html.gs-dark .ki-step,html.gs-dark .ki-row .ki-msg,html.gs-dark .ki-body small{color:#a79da1}
html.gs-dark .ki-step b{color:#f1ecee}
html.gs-dark .ki-bar,html.gs-dark .ki-row .ki-ic,html.gs-dark .ki-btn--ghost{background:#2c2729;color:#f1ecee}
html.gs-dark .ki-row--calisiyor{background:#2a2224}
html.gs-dark .ki-road::before{border-color:#3d3538}
@keyframes ki-road{from{background-position:0 0;transform:translateX(0)}to{transform:translateX(-24px)}}
@keyframes ki-bump{0%,100%{transform:translateY(0)}50%{transform:translateY(-2px)}}
@keyframes ki-puff{0%{opacity:.8;transform:translate(0,0) scale(.6)}100%{opacity:0;transform:translate(-18px,-8px) scale(1.6)}}
@keyframes ki-stripe{from{background-position:0 0}to{background-position:24px 0}}
@keyframes ki-in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@keyframes ki-pop{from{transform:scale(.4)}to{transform:scale(1)}}
@keyframes ki-spin{to{transform:rotate(360deg)}}
@keyframes ki-shake{0%,100%{transform:translateX(0)}25%{transform:translateX(-3px)}75%{transform:translateX(3px)}}
@media (prefers-reduced-motion:reduce){.ki-road.ki-run::before,.ki-road.ki-run .ki-truck,.ki-road.ki-run .ki-puff,.ki-fill::after{animation:none}}
`;
  function cssYukle() {
    if (document.getElementById('ki-css')) return;
    const st = document.createElement('style');
    st.id = 'ki-css';
    st.textContent = CSS;
    document.head.appendChild(st);
  }
  function overlayOlustur() {
    cssYukle();
    const ov = document.createElement('div');
    ov.className = 'ki-overlay';
    document.body.appendChild(ov);
    requestAnimationFrame(() => requestAnimationFrame(() => ov.classList.add('ki-show')));
    return ov;
  }
  function overlayKapat(ov) {
    ov.classList.remove('ki-show');
    setTimeout(() => ov.remove(), 240);
  }
  const IKON = { bekliyor: 'bi bi-clock', calisiyor: 'bi bi-arrow-repeat', ok: 'bi bi-check-lg',
                 atlandi: 'bi bi-dash-lg', hata: 'bi bi-x-lg' };

  // ── Onay diyaloğu (yerel confirm yerine) ──
  function onayla(opts) {
    opts = opts || {};
    return new Promise(resolve => {
      const ov = overlayOlustur();
      ov.innerHTML = `
        <div class="ki-card" role="dialog" aria-modal="true">
          <div class="ki-head"><div class="ki-title"><i class="bi bi-truck"></i> ${esc(opts.baslik || 'Onay')}</div></div>
          <div class="ki-body">${opts.html || ''}</div>
          <div class="ki-foot">
            <span></span>
            <span style="display:flex;gap:8px">
              <button type="button" class="ki-btn ki-btn--ghost" data-ki="iptal">${esc(opts.cancelText || 'Vazgeç')}</button>
              <button type="button" class="ki-btn ki-btn--ok" data-ki="ok">${esc(opts.okText || 'Evet')}</button>
            </span>
          </div>
        </div>`;
      const bitir = v => { overlayKapat(ov); document.removeEventListener('keydown', esc_); resolve(v); };
      const esc_ = e => { if (e.key === 'Escape') bitir(false); };
      document.addEventListener('keydown', esc_);
      ov.querySelector('[data-ki="ok"]').onclick = () => bitir(true);
      ov.querySelector('[data-ki="iptal"]').onclick = () => bitir(false);
      ov.onclick = e => { if (e.target === ov) bitir(false); };
      ov.querySelector('[data-ki="ok"]').focus();
    });
  }

  // ── İlerleme paneli ──
  function ac(opts) {
    opts = opts || {};
    const ov = overlayOlustur();
    ov.innerHTML = `
      <div class="ki-card" role="dialog" aria-modal="true" aria-live="polite">
        <div class="ki-head">
          <div class="ki-title"><i class="bi bi-truck"></i> ${esc(opts.baslik || 'Kargo işlemi')}</div>
          ${opts.altBaslik ? `<div class="ki-sub">${opts.altBaslik}</div>` : ''}
        </div>
        <div class="ki-road ki-run"><span class="ki-truck"><span class="ki-puff"></span><span class="ki-puff"></span><span class="ki-puff"></span><i class="bi bi-truck"></i></span></div>
        <div class="ki-bar"><div class="ki-fill"></div></div>
        <div class="ki-step"><span class="ki-step-text">Başlıyor…</span><b class="ki-step-count"></b></div>
        <div class="ki-list"></div>
        <div class="ki-foot">
          <span class="ki-ozet"></span>
          <button type="button" class="ki-btn ki-btn--ok" data-ki="kapat" disabled>Kapat</button>
        </div>
      </div>`;
    const el = {
      road: ov.querySelector('.ki-road'), truck: ov.querySelector('.ki-truck'), fill: ov.querySelector('.ki-fill'),
      stepText: ov.querySelector('.ki-step-text'), stepCount: ov.querySelector('.ki-step-count'),
      list: ov.querySelector('.ki-list'), ozet: ov.querySelector('.ki-ozet'), kapat: ov.querySelector('[data-ki="kapat"]'),
      card: ov.querySelector('.ki-card'),
    };
    const satirlar = new Map();
    function satirEkle(id, etiket) {
      const row = document.createElement('div');
      row.className = 'ki-row ki-row--bekliyor';
      row.innerHTML = `<span class="ki-ic"><i class="${IKON.bekliyor}"></i></span><span class="ki-no">#${esc(etiket || id)}</span><span class="ki-msg">Bekliyor</span>`;
      el.list.appendChild(row);
      satirlar.set(String(id), row);
      return row;
    }
    (opts.satirlar || []).forEach(s => satirEkle(s.id, s.etiket));

    let kapandi = false;
    const api = {
      adim(metin, i, n) {
        el.stepText.textContent = metin || '';
        if (n) {
          const oran = Math.max(0, Math.min(1, i / n));
          el.stepCount.textContent = `${i}/${n}`;
          el.fill.style.width = (oran * 100) + '%';
          el.truck.style.left = `calc(${(oran * 100).toFixed(1)}% - ${(oran * 30).toFixed(0)}px)`;
        } else {
          el.stepCount.textContent = '';
        }
      },
      satir(id, durum, mesaj, ekHtml) {
        const row = satirlar.get(String(id)) || satirEkle(id, id);
        row.className = 'ki-row ki-row--' + (IKON[durum] ? durum : 'bekliyor');
        row.querySelector('.ki-ic').innerHTML = `<i class="${IKON[durum] || IKON.bekliyor}"></i>`;
        row.querySelector('.ki-msg').innerHTML = (ekHtml || '') + esc(mesaj || '');
        if (durum === 'calisiyor') row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      },
      bitir(o) {
        o = o || {};
        el.road.classList.remove('ki-run');
        el.card.classList.add('ki-done');
        el.fill.style.width = '100%';
        el.truck.style.left = 'calc(100% - 30px)';
        el.stepText.textContent = o.adim || 'Tamamlandı';
        el.stepCount.textContent = '';
        el.ozet.className = 'ki-ozet ki-ozet--' + (o.tur || 'success');
        el.ozet.textContent = o.ozet || '';
        el.kapat.disabled = false;
        el.kapat.focus();
      },
      kapat() { if (kapandi) return; kapandi = true; overlayKapat(ov); if (typeof opts.onKapat === 'function') opts.onKapat(); },
    };
    el.kapat.onclick = api.kapat;
    return api;
  }

  window.KargoIslem = { onayla, ac };
})();
