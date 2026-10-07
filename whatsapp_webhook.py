"""
WhatsApp Business hesabı webhook'u — Meta buraya bildirim atar.

- Public endpoint: GET/POST /api/whatsapp/webhook. `/api/` öneki app.py'deki
  check_authentication'dan bilinçli olarak muaf (instagram_dm ile aynı desen);
  koruma GET'te doğrulama anahtarı, POST'ta X-Hub-Signature-256 imzasıdır
  (FB_APP_SECRET tanımlı değilse POST kabul edilmez).
- Neden var: Coexistence (şirket hattını telefondaki WhatsApp Business
  uygulamasıyla birlikte kullanma) seçeneği, uygulama şu webhook alanlarına
  abone olmadan Embedded Signup akışında HİÇ GÖRÜNMEZ:
  history, smb_app_state_sync, smb_message_echoes. Abonelik için Meta'nın
  çağırabileceği bir adres gerekir; bu modül o adrestir.
- Şimdilik gelen olayları yalnızca kabul edip loglar; mesaj/kişi senkronu
  işlenmez. (Meta 200 dışı cevapta tekrar dener; o yüzden her durumda 200.)

Ayarlar (.env):
  WHATSAPP_VERIFY_TOKEN   Webhook kurulumunda Meta paneline yazılan anahtar
  FB_APP_SECRET           Meta uygulama sırrı (webhook imzası; whatsapp_baglanti ile ortak)
"""
import hashlib
import hmac
import logging
import os

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

whatsapp_webhook_bp = Blueprint("whatsapp_webhook", __name__)

WEBHOOK_MAX_BYTES = 1024 * 1024
WEBHOOK_OBJECT = "whatsapp_business_account"


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _imza_gecerli(govde: bytes, baslik: str | None) -> bool:
    sir = _env("FB_APP_SECRET")
    if not sir or not baslik or not baslik.startswith("sha256="):
        return False
    beklenen = hmac.new(sir.encode("utf-8"), govde, hashlib.sha256).hexdigest()
    return hmac.compare_digest(beklenen, baslik[len("sha256="):])


def _ozet(payload: dict) -> list[str]:
    """Log için: her entry'deki WABA kimliği ve gelen alan adları."""
    satirlar = []
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        alanlar = [
            str(d.get("field"))
            for d in (entry.get("changes") or [])
            if isinstance(d, dict) and d.get("field")
        ]
        satirlar.append(f"waba={entry.get('id')} alanlar={','.join(alanlar) or '-'}")
    return satirlar


@whatsapp_webhook_bp.route("/api/whatsapp/webhook", methods=["GET", "POST"])
def whatsapp_webhook():
    if request.method == "GET":
        anahtar = _env("WHATSAPP_VERIFY_TOKEN")
        gelen = request.args.get("hub.verify_token") or ""
        if (anahtar and request.args.get("hub.mode") == "subscribe"
                and hmac.compare_digest(anahtar.encode("utf-8"), gelen.encode("utf-8"))):
            return (request.args.get("hub.challenge") or ""), 200, {"Content-Type": "text/plain"}
        return jsonify({"ok": False}), 403

    if (request.content_length or 0) > WEBHOOK_MAX_BYTES:
        return jsonify({"ok": False}), 413
    govde = request.get_data(cache=True)
    if not _imza_gecerli(govde, request.headers.get("X-Hub-Signature-256")):
        logger.warning("[WA-WEBHOOK] imza doğrulanamadı")
        return jsonify({"ok": False}), 403

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("object") != WEBHOOK_OBJECT:
        return jsonify({"ok": True})

    for satir in _ozet(payload):
        logger.info("[WA-WEBHOOK] %s", satir)
    return jsonify({"ok": True})
