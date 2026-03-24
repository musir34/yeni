/**
 * app-shell.js — Güllü Shoes Global Shell
 * Toast, Confirm Sheet, Count Tween, Refresh Manager
 *
 * Tüm animasyonlar yalnızca transform + opacity kullanır.
 * prefers-reduced-motion otomatik algılanır.
 * window.GS üzerinden erişilir.
 */
(function (G) {
  'use strict';

  var prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ─── Toast Sistemi ─────────────────────────────────────────────────────────
  var TOAST_COLORS = {
    success: { bg: '#22c55e', text: '#fff', icon: '✓' },
    danger:  { bg: '#ef4444', text: '#fff', icon: '✕' },
    warning: { bg: '#f59e0b', text: '#fff', icon: '⚠' },
    info:    { bg: '#0ea5e9', text: '#fff', icon: 'ℹ' },
  };

  function _toastContainer() {
    var c = document.getElementById('gs-toast-container');
    if (!c) {
      c = document.createElement('div');
      c.id = 'gs-toast-container';
      c.setAttribute('aria-live', 'polite');
      c.style.cssText = [
        'position:fixed',
        'bottom:1.5rem',
        'right:1.5rem',
        'z-index:99999',
        'display:flex',
        'flex-direction:column',
        'gap:.5rem',
        'pointer-events:none',
        'max-width:340px',
      ].join(';');
      document.body.appendChild(c);
    }
    return c;
  }

  /**
   * showToast(msg, type, duration)
   * type: 'success' | 'danger' | 'warning' | 'info'
   * duration: ms (default 3500)
   */
  function showToast(msg, type, duration) {
    type = type || 'info';
    duration = (typeof duration === 'number') ? duration : 3500;
    var col = TOAST_COLORS[type] || TOAST_COLORS.info;
    var c = _toastContainer();
    var t = document.createElement('div');
    var dur = prefersReduced ? 'none' : 'opacity .18s ease, transform .18s ease';
    t.style.cssText = [
      'background:' + col.bg,
      'color:' + col.text,
      'padding:.65rem 1.1rem',
      'border-radius:10px',
      'font-size:.87rem',
      'font-weight:600',
      'box-shadow:0 4px 16px rgba(0,0,0,.2)',
      'display:flex',
      'align-items:center',
      'gap:.6rem',
      'pointer-events:all',
      'cursor:pointer',
      'opacity:' + (prefersReduced ? '1' : '0'),
      'transform:' + (prefersReduced ? 'none' : 'translateX(18px)'),
      'transition:' + dur,
    ].join(';');
    t.innerHTML = '<span style="font-size:1rem;flex-shrink:0">' + col.icon + '</span>' +
                  '<span style="line-height:1.4">' + msg + '</span>';
    t.onclick = function () { _dismissToast(t); };
    c.appendChild(t);

    if (!prefersReduced) {
      requestAnimationFrame(function () {
        t.style.opacity = '1';
        t.style.transform = 'translateX(0)';
      });
    }

    var tid = setTimeout(function () { _dismissToast(t); }, duration);
    t._tid = tid;
    return t;
  }

  function _dismissToast(t) {
    if (t._dismissed) return;
    t._dismissed = true;
    clearTimeout(t._tid);
    if (prefersReduced) {
      t.remove();
    } else {
      t.style.opacity = '0';
      t.style.transform = 'translateX(18px)';
      setTimeout(function () { t.remove(); }, 200);
    }
  }

  // ─── Confirm Sheet (browser confirm() yerine) ──────────────────────────────
  /**
   * showConfirmSheet(msg, onConfirm, onCancel)
   * Mobil-uyumlu, animasyonlu onay kutusu.
   */
  function showConfirmSheet(msg, onConfirm, onCancel) {
    var overlay = document.createElement('div');
    overlay.style.cssText = [
      'position:fixed',
      'inset:0',
      'z-index:99998',
      'background:rgba(0,0,0,.45)',
      'display:flex',
      'align-items:flex-end',
      'justify-content:center',
    ].join(';');

    var sheet = document.createElement('div');
    sheet.style.cssText = [
      'background:#fff',
      'width:100%',
      'max-width:480px',
      'border-radius:16px 16px 0 0',
      'padding:1.5rem 1.5rem 2rem',
      'box-shadow:0 -4px 24px rgba(0,0,0,.15)',
      'transform:' + (prefersReduced ? 'none' : 'translateY(100%)'),
      'transition:' + (prefersReduced ? 'none' : 'transform .22s ease'),
    ].join(';');

    sheet.innerHTML =
      '<p style="margin:0 0 1.25rem;font-weight:600;font-size:.97rem;color:#212529;text-align:center;">' +
        msg +
      '</p>' +
      '<div style="display:flex;gap:.75rem;">' +
        '<button id="_gscs_cancel" style="flex:1;padding:.65rem;border:1px solid #dee2e6;border-radius:8px;background:#fff;color:#495057;font-weight:600;font-size:.9rem;cursor:pointer;">İptal</button>' +
        '<button id="_gscs_ok" style="flex:1;padding:.65rem;border:none;border-radius:8px;background:#B76E79;color:#fff;font-weight:600;font-size:.9rem;cursor:pointer;">Devam Et</button>' +
      '</div>';

    overlay.appendChild(sheet);
    document.body.appendChild(overlay);

    if (!prefersReduced) {
      requestAnimationFrame(function () { sheet.style.transform = 'translateY(0)'; });
    }

    function close(cb) {
      if (prefersReduced) {
        overlay.remove();
        if (cb) cb();
      } else {
        sheet.style.transform = 'translateY(100%)';
        setTimeout(function () { overlay.remove(); if (cb) cb(); }, 240);
      }
    }

    sheet.querySelector('#_gscs_ok').onclick     = function () { close(onConfirm); };
    sheet.querySelector('#_gscs_cancel').onclick  = function () { close(onCancel); };
    overlay.onclick = function (e) { if (e.target === overlay) close(onCancel); };
  }

  // ─── Count Tween ───────────────────────────────────────────────────────────
  /**
   * countTween(el, from, to, duration)
   * Sayıyı animasyonlu olarak günceller.
   */
  function countTween(el, from, to, duration) {
    if (prefersReduced || from === to) { el.textContent = to; return; }
    duration = duration || 220;
    var start = performance.now();
    var delta = to - from;
    function step(now) {
      var t = Math.min(1, (now - start) / duration);
      // ease in-out quad
      var e = t < .5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
      el.textContent = Math.round(from + delta * e);
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  // ─── Refresh Manager ───────────────────────────────────────────────────────
  /**
   * registerRefresh(id, fetchFn, intervalMs)
   * Görünmez sekmelerde duraklar. AbortController ile istek iptali.
   * fetchFn(signal) → async function.
   * Returns { stop() }
   */
  var _tasks = {};

  function registerRefresh(id, fetchFn, intervalMs) {
    if (_tasks[id]) _tasks[id].stop();

    var active = true;
    var controller = null;

    function run() {
      if (!active) return;
      if (document.visibilityState === 'hidden') return;
      try { if (controller) controller.abort(); } catch(e) {}
      controller = (typeof AbortController !== 'undefined') ? new AbortController() : null;
      var sig = controller ? controller.signal : undefined;
      fetchFn(sig).catch(function (e) {
        if (e && e.name !== 'AbortError') {
          console.warn('[GS.RefreshManager]', id, e.message || e);
        }
      });
    }

    run();
    var timer = setInterval(run, intervalMs);

    function onVisibility() {
      if (document.visibilityState === 'visible') run();
    }
    document.addEventListener('visibilitychange', onVisibility);

    var handle = {
      stop: function () {
        active = false;
        clearInterval(timer);
        try { if (controller) controller.abort(); } catch(e) {}
        document.removeEventListener('visibilitychange', onVisibility);
        delete _tasks[id];
      }
    };
    _tasks[id] = handle;
    return handle;
  }

  // ─── Fade-out + remove element ────────────────────────────────────────────
  function fadeRemove(el, duration, cb) {
    duration = duration || 200;
    if (prefersReduced) { el.remove(); if (cb) cb(); return; }
    el.style.transition = 'opacity ' + duration + 'ms ease, transform ' + duration + 'ms ease';
    el.style.opacity = '0';
    el.style.transform = 'scale(0.95)';
    setTimeout(function () { el.remove(); if (cb) cb(); }, duration + 20);
  }

  // ─── Dark Mode ─────────────────────────────────────────────────────────────
  var DM_KEY = 'gs_dark_mode';      // 'on' | 'off' | 'auto'
  var DM_CLASS = 'gs-dark';

  function _isDarkByTime() {
    var h = new Date().getHours();
    return h >= 20 || h < 7; // 20:00 – 07:00 arası karanlık
  }

  function _resolveDark(mode) {
    if (mode === 'on') return true;
    if (mode === 'off') return false;
    return _isDarkByTime(); // 'auto'
  }

  function _applyDark(dark) {
    if (dark) {
      document.documentElement.classList.add(DM_CLASS);
    } else {
      document.documentElement.classList.remove(DM_CLASS);
    }
  }

  function getDarkMode() {
    return localStorage.getItem(DM_KEY) || 'auto';
  }

  function setDarkMode(mode) {
    // mode: 'on' | 'off' | 'auto'
    localStorage.setItem(DM_KEY, mode);
    _applyDark(_resolveDark(mode));
    _updateAllToggles(mode);
    _highlightActiveOpt(mode);
  }

  function toggleDarkMode() {
    var cur = getDarkMode();
    // Döngü: auto → on → off → auto
    var next = cur === 'auto' ? 'on' : cur === 'on' ? 'off' : 'auto';
    setDarkMode(next);
    var labels = { on: 'Karanlık Mod: Açık', off: 'Karanlık Mod: Kapalı', auto: 'Karanlık Mod: Otomatik' };
    showToast(labels[next], 'info', 2000);
    return next;
  }

  function _updateAllToggles(mode) {
    // Sayfadaki tüm toggle butonlarını güncelle
    document.querySelectorAll('[data-gs-dark-toggle]').forEach(function(el) {
      var icons = { on: 'fa-moon', off: 'fa-sun', auto: 'fa-clock' };
      var labels = { on: 'Karanlık', off: 'Aydınlık', auto: 'Otomatik' };
      var icon = el.querySelector('i.gs-dm-icon');
      var txt = el.querySelector('.gs-dm-label');
      if (icon) { icon.className = 'fas ' + (icons[mode] || 'fa-clock') + ' gs-dm-icon'; }
      if (txt) { txt.textContent = labels[mode] || 'Otomatik'; }
    });
  }

  function _highlightActiveOpt(mode) {
    document.querySelectorAll('.gs-dm-opt').forEach(function(el) {
      if (el.dataset.dm === mode) {
        el.style.fontWeight = '700';
        el.style.background = 'rgba(183,110,121,.12)';
      } else {
        el.style.fontWeight = '';
        el.style.background = '';
      }
    });
  }

  // Sayfa yüklendiğinde hemen uygula (FOUC engelle)
  _applyDark(_resolveDark(getDarkMode()));

  // Auto modda her dakika kontrol et (gün batımı/doğumu geçişi)
  setInterval(function() {
    if (getDarkMode() === 'auto') {
      _applyDark(_isDarkByTime());
    }
  }, 60000);

  // Diğer sekmelerden gelen değişiklikleri dinle
  window.addEventListener('storage', function(e) {
    if (e.key === DM_KEY) {
      _applyDark(_resolveDark(e.newValue || 'auto'));
      _updateAllToggles(e.newValue || 'auto');
    }
  });

  // ─── Expose ───────────────────────────────────────────────────────────────
  G.GS = {
    showToast: showToast,
    showConfirmSheet: showConfirmSheet,
    countTween: countTween,
    registerRefresh: registerRefresh,
    fadeRemove: fadeRemove,
    prefersReduced: prefersReduced,
    getDarkMode: getDarkMode,
    setDarkMode: setDarkMode,
    toggleDarkMode: toggleDarkMode,
  };

})(window);
