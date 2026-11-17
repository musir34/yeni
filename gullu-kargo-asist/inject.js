// MAIN world - DHL sayfasinda QZ Tray'e giden WebSocket mesajlarini yakalar
// Print cagrilarinin ZPL payload'ini ayiklar ve content-script'e postMessage ile iletir
(function() {
  if (window.__gulluWsHooked) return;
  window.__gulluWsHooked = true;

  var OrigWS = window.WebSocket;
  if (!OrigWS) return;

  function gulluZplYakala(data) {
    try {
      if (typeof data !== "string") return;
      // QZ Tray mesajlari JSON. Hizli on-eleme:
      if (data.indexOf("\"call\"") === -1 && data.indexOf("^XA") === -1) return;

      var parsed = JSON.parse(data);
      if (!parsed || typeof parsed !== "object") return;

      // QZ Tray sign-then-call protokolu: { call: "print", params: { data: [{type, format, data}] } }
      var liste = parsed.params && parsed.params.data;
      if (!Array.isArray(liste)) return;

      for (var i = 0; i < liste.length; i++) {
        var item = liste[i];
        if (item && typeof item.data === "string" && item.data.indexOf("^XA") !== -1) {
          window.postMessage({ __gulluZpl: true, zpl: item.data }, "*");
        }
      }
    } catch (e) {
      // JSON degil ya da farkli format - sessizce yut
    }
  }

  function PatchedWS(url, protocols) {
    var ws = (protocols !== undefined) ? new OrigWS(url, protocols) : new OrigWS(url);
    try {
      var u = String(url || "");
      // Sadece QZ Tray ile uyumlu lokal WS bağlantilarini hook'la
      if (u.indexOf("localhost") !== -1 || u.indexOf("127.0.0.1") !== -1 || u.toLowerCase().indexOf("qz") !== -1) {
        var origSend = ws.send.bind(ws);
        ws.send = function(data) {
          gulluZplYakala(data);
          return origSend(data);
        };
        console.log("[Gullu Asist] QZ Tray WebSocket hook aktif:", u);
      }
    } catch (e) {}
    return ws;
  }

  PatchedWS.prototype = OrigWS.prototype;
  PatchedWS.CONNECTING = OrigWS.CONNECTING;
  PatchedWS.OPEN = OrigWS.OPEN;
  PatchedWS.CLOSING = OrigWS.CLOSING;
  PatchedWS.CLOSED = OrigWS.CLOSED;
  window.WebSocket = PatchedWS;

  console.log("[Gullu Asist] WebSocket override yuklendi (ZPL yakalayici hazir)");
})();
