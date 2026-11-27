"""Shopify sipariş webhook'u — siparişte değişiklik olunca (kalem çıkarma/ekleme) MNG tahsilat
tutarı ve etiketi 5 dk'lık taramayı beklemeden güncellenir.

- Public endpoint: POST /api/shopify/webhook/siparis. `/api/` öneki check_authentication'dan muaf
  (whatsapp_webhook ile aynı desen); koruma X-Shopify-Hmac-Sha256 imzasıdır (SHOPIFY_CLIENT_SECRET
  tanımlı değilse istek kabul edilmez).
- Konular: orders/updated (gövde: sipariş, 'id') ve orders/edited (gövde: order_edit.order_id).
  Abonelik bir kez kurulur: scripts/shopify_webhook_kur.py.
- Shopify 5 sn içinde cevap ister: iş arka plan ipliğinde yapılır. Barkodu kesilmiş gönderi yeniden
  açıldıysa MNG varış şubesini çözene kadar beklenip (≈45 sn) yeni barkod hemen alınır; alınamazsa
  takip işi (5 dk) dener. Webhook hiç gelmezse tarama (shopify_tarama.tutarlari_tara) yine yakalar.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import threading
import time

from flask import Blueprint, current_app, jsonify, request

from models import db

logger = logging.getLogger(__name__)

shopify_webhook_bp = Blueprint("shopify_webhook", __name__)

WEBHOOK_YOLU = "/api/shopify/webhook/siparis"
WEBHOOK_MAX_BYTES = 2 * 1024 * 1024
BARKOD_BEKLEME_SN = 45          # MNG varış şubesini sipariş açıldıktan 30-60 sn sonra çözer


def _imza_gecerli(govde: bytes, baslik: str | None) -> bool:
    sir = (os.environ.get("SHOPIFY_CLIENT_SECRET") or "").strip()
    if not sir or not baslik:
        return False
    beklenen = base64.b64encode(hmac.new(sir.encode("utf-8"), govde, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(beklenen, baslik.strip())


def siparis_id(payload: dict) -> str:
    """orders/updated → id; orders/edited → order_edit.order_id."""
    ham = (payload.get("order_edit") or {}).get("order_id") or payload.get("id") or ""
    return str(ham).split("/")[-1]


def siparis_degisti(order_id: str, barkod_bekleme: int = BARKOD_BEKLEME_SN) -> bool:
    """Siparişin açık kapıda ödemeli MNG gönderisi varsa tutarı eşitle; etiketi basılmışsa yeni barkodu al."""
    from .servis import KAYNAK_SHOPIFY, barkod_al, gonderi_bul
    from .shopify_tarama import tutari_esitle
    kayit = gonderi_bul(KAYNAK_SHOPIFY, order_id)
    if not kayit or not kayit.kapida_odeme_tutari:
        return False
    barkodlu = bool(kayit.shipment_id or kayit.barkod)
    if not tutari_esitle(kayit):
        return False
    if barkodlu:
        time.sleep(barkod_bekleme)
        barkod_al(kayit, bekle=True)
        db.session.commit()
    return True


def _arka_planda(app, order_id: str) -> None:
    with app.app_context():
        try:
            siparis_degisti(order_id)
        except Exception:
            db.session.rollback()
            logger.exception("[MNG] Shopify webhook işleme hatası (sipariş %s) — yutuldu, tarama yakalar", order_id)
        finally:
            db.session.remove()


@shopify_webhook_bp.route(WEBHOOK_YOLU, methods=["POST"])
def shopify_siparis_webhook():
    if (request.content_length or 0) > WEBHOOK_MAX_BYTES:
        return jsonify({"ok": False}), 413
    govde = request.get_data(cache=True)
    if not _imza_gecerli(govde, request.headers.get("X-Shopify-Hmac-Sha256")):
        logger.warning("[MNG] Shopify webhook imzası doğrulanamadı")
        return jsonify({"ok": False}), 401
    payload = request.get_json(silent=True)
    order_id = siparis_id(payload) if isinstance(payload, dict) else ""
    if order_id.isdigit():
        threading.Thread(target=_arka_planda, args=(current_app._get_current_object(), order_id),
                         daemon=True).start()
    return jsonify({"ok": True})
