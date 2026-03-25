/**
 * GS Dialog — Custom alert/confirm/toast replacements
 * Usage:
 *   gsAlert('Mesaj')                        → info alert
 *   gsAlert('Hata!', 'error')               → error alert
 *   gsAlert('Silindi', 'success')            → success alert
 *   gsConfirm('Emin misin?').then(ok => {})  → returns Promise<boolean>
 *   gsToast('İşlem tamam', 'success')        → bottom-right toast
 */
(function(){
  // Inject CSS once
  const style = document.createElement('style');
  style.textContent = `
    .gsd-overlay{position:fixed;inset:0;background:rgba(0,0,0,.45);backdrop-filter:blur(3px);display:flex;align-items:center;justify-content:center;z-index:99999;padding:16px;opacity:0;transition:opacity .2s ease}
    .gsd-overlay.show{opacity:1}
    .gsd-box{background:#fff;border-radius:16px;box-shadow:0 24px 60px rgba(0,0,0,.25);max-width:400px;width:100%;overflow:hidden;transform:scale(.9) translateY(12px);transition:transform .25s cubic-bezier(.34,1.56,.64,1),opacity .2s;opacity:0}
    .gsd-overlay.show .gsd-box{transform:none;opacity:1}
    .gsd-icon{width:56px;height:56px;border-radius:50%;display:grid;place-items:center;margin:24px auto 12px;font-size:26px}
    .gsd-icon.info{background:rgba(14,165,233,.1)}
    .gsd-icon.success{background:rgba(34,197,94,.1)}
    .gsd-icon.error{background:rgba(239,68,68,.1)}
    .gsd-icon.warning{background:rgba(245,158,11,.1)}
    .gsd-msg{text-align:center;padding:0 24px 20px;font-size:15px;color:#343a40;line-height:1.5;font-weight:500}
    .gsd-btns{display:flex;border-top:1px solid #e5e7eb}
    .gsd-btns button{flex:1;padding:14px;border:none;background:none;font-size:14px;font-weight:700;cursor:pointer;transition:background .15s}
    .gsd-btns button:hover{background:#f3f5f7}
    .gsd-btns button:not(:last-child){border-right:1px solid #e5e7eb}
    .gsd-btns .gsd-cancel{color:#6b7280}
    .gsd-btns .gsd-ok{color:#B76E79}
    .gsd-btns .gsd-ok.danger{color:#ef4444}
    .gsd-btns .gsd-ok.success{color:#22c55e}

    /* Toast */
    .gsd-toast{position:fixed;bottom:24px;right:24px;padding:14px 20px;border-radius:12px;font-size:13px;font-weight:600;color:#fff;z-index:99999;box-shadow:0 8px 24px rgba(0,0,0,.2);transform:translateY(80px);opacity:0;transition:all .35s cubic-bezier(.34,1.56,.64,1);display:flex;align-items:center;gap:8px;max-width:400px}
    .gsd-toast.show{transform:translateY(0);opacity:1}
    .gsd-toast.info{background:#0ea5e9}
    .gsd-toast.success{background:#22c55e}
    .gsd-toast.error{background:#ef4444}
    .gsd-toast.warning{background:#f59e0b;color:#1a1a1a}

    /* Dark mode */
    html.gs-dark .gsd-box{background:#1e1e1e;border:1px solid #333}
    html.gs-dark .gsd-msg{color:#e0e0e0}
    html.gs-dark .gsd-btns{border-top-color:#333}
    html.gs-dark .gsd-btns button{color:#ddd}
    html.gs-dark .gsd-btns button:not(:last-child){border-right-color:#333}
    html.gs-dark .gsd-btns button:hover{background:#2a2a2a}
    html.gs-dark .gsd-btns .gsd-cancel{color:#888}
  `;
  document.head.appendChild(style);

  const ICONS = {
    info: '💬', success: '✅', error: '❌', warning: '⚠️'
  };

  function _createOverlay() {
    const el = document.createElement('div');
    el.className = 'gsd-overlay';
    document.body.appendChild(el);
    requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('show')));
    return el;
  }

  function _destroy(overlay) {
    overlay.classList.remove('show');
    setTimeout(() => overlay.remove(), 250);
  }

  // ── gsAlert ──
  window.gsAlert = function(msg, type) {
    type = type || 'info';
    return new Promise(resolve => {
      const overlay = _createOverlay();
      overlay.innerHTML = `
        <div class="gsd-box">
          <div class="gsd-icon ${type}">${ICONS[type] || ICONS.info}</div>
          <div class="gsd-msg">${msg}</div>
          <div class="gsd-btns"><button class="gsd-ok ${type}">Tamam</button></div>
        </div>`;
      const btn = overlay.querySelector('.gsd-ok');
      btn.onclick = () => { _destroy(overlay); resolve(); };
      overlay.onclick = (e) => { if (e.target === overlay) { _destroy(overlay); resolve(); } };
      btn.focus();
    });
  };

  // ── gsConfirm ──
  window.gsConfirm = function(msg, opts) {
    opts = opts || {};
    const type = opts.type || 'warning';
    const okText = opts.okText || 'Evet';
    const cancelText = opts.cancelText || 'Vazgeç';
    const okClass = opts.danger ? 'danger' : (type === 'success' ? 'success' : '');

    return new Promise(resolve => {
      const overlay = _createOverlay();
      overlay.innerHTML = `
        <div class="gsd-box">
          <div class="gsd-icon ${type}">${ICONS[type] || ICONS.warning}</div>
          <div class="gsd-msg">${msg}</div>
          <div class="gsd-btns">
            <button class="gsd-cancel">${cancelText}</button>
            <button class="gsd-ok ${okClass}">${okText}</button>
          </div>
        </div>`;
      overlay.querySelector('.gsd-cancel').onclick = () => { _destroy(overlay); resolve(false); };
      overlay.querySelector('.gsd-ok').onclick = () => { _destroy(overlay); resolve(true); };
      overlay.onclick = (e) => { if (e.target === overlay) { _destroy(overlay); resolve(false); } };
    });
  };

  // ── gsToast ──
  let _toastTimer = null;
  window.gsToast = function(msg, type) {
    type = type || 'info';
    let el = document.getElementById('gsd-toast-singleton');
    if (!el) {
      el = document.createElement('div');
      el.id = 'gsd-toast-singleton';
      el.className = 'gsd-toast';
      document.body.appendChild(el);
    }
    clearTimeout(_toastTimer);
    el.classList.remove('show');
    el.className = 'gsd-toast ' + type;
    el.textContent = msg;
    requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('show')));
    _toastTimer = setTimeout(() => el.classList.remove('show'), 3500);
  };
})();
