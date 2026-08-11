import logging
import os
import re
import uuid
from urllib.parse import urlparse

import requests
from flask import Blueprint, current_app, jsonify, render_template, request, session


logger = logging.getLogger(__name__)

iade_yonetimi_bp = Blueprint("iade_yonetimi", __name__)

VALID_KATEGORILER = {"bekliyor", "kargoda", "teslim"}
VALID_KAYNAKLAR = {"degisim", "trendyol", "shopify", "manuel"}
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class IadeKopruHatasi(Exception):
    """İade köprü servisi panel isteğini tamamlayamadığında kullanılır."""

    def __init__(self, message, status_code=503):
        super().__init__(message)
        self.status_code = status_code


def _config_value(name, default=""):
    return current_app.config.get(name) or os.getenv(name, default)


def fetch_iadeler(kategori=None, sync=False):
    """Köprü servisinden iade listesini sunucu tarafında güvenli biçimde alır."""
    if kategori and kategori not in VALID_KATEGORILER:
        raise ValueError("Geçersiz iade kategorisi.")

    panel_key = _config_value("IADE_PANEL_KEY")
    if not panel_key:
        raise IadeKopruHatasi("İade Panel API anahtarı henüz yapılandırılmamış.")

    base_url = _config_value("IADE_API_URL", "http://localhost:3434").rstrip("/")
    params = {}
    if kategori:
        params["durum"] = kategori
    if sync:
        params["sync"] = "1"

    try:
        response = requests.get(
            f"{base_url}/api/admin/iadeler",
            headers={"X-Admin-Key": panel_key, "Accept": "application/json"},
            params=params,
            timeout=(3.05, 45 if sync else 15),
        )
    except requests.Timeout as exc:
        raise IadeKopruHatasi("İade servisi zaman aşımına uğradı. Lütfen tekrar deneyin.") from exc
    except requests.RequestException as exc:
        logger.warning("İade köprü servisine ulaşılamadı: %s", exc)
        raise IadeKopruHatasi("İade servisine şu anda ulaşılamıyor.") from exc

    if response.status_code == 401:
        raise IadeKopruHatasi("İade Panel API anahtarı eksik veya geçersiz.")
    if response.status_code >= 400:
        logger.warning("İade köprü servisi HTTP %s döndürdü.", response.status_code)
        raise IadeKopruHatasi("İade servisi isteği tamamlayamadı.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise IadeKopruHatasi("İade servisinden geçersiz bir cevap alındı.") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("iadeler"), list):
        raise IadeKopruHatasi("İade servisinin cevap biçimi beklenenden farklı.")

    payload.setdefault("toplam", len(payload["iadeler"]))
    payload.setdefault("sayac", {"bekliyor": 0, "kargoda": 0, "teslim": 0})
    return payload


def create_iade(payload):
    """Admin anahtarıyla köprü serviste gerçek DHL eCommerce iade kodu oluşturur."""
    panel_key = _config_value("IADE_PANEL_KEY")
    if not panel_key:
        raise IadeKopruHatasi("İade Panel API anahtarı henüz yapılandırılmamış.")

    base_url = _config_value("IADE_API_URL", "http://localhost:3434").rstrip("/")
    try:
        response = requests.post(
            f"{base_url}/api/admin/iadeler",
            headers={
                "X-Admin-Key": panel_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(5, 45),
        )
    except requests.Timeout as exc:
        raise IadeKopruHatasi(
            "DHL eCommerce kod oluşturma isteği zaman aşımına uğradı. Aynı formu tekrar gönderirseniz çift kod oluşturulmaz."
        ) from exc
    except requests.RequestException as exc:
        logger.warning("İade oluştururken köprü servisine ulaşılamadı: %s", exc)
        raise IadeKopruHatasi("İade servisine şu anda ulaşılamıyor.") from exc

    try:
        result = response.json()
    except ValueError as exc:
        raise IadeKopruHatasi("İade servisinden geçersiz bir cevap alındı.") from exc

    if response.status_code == 401:
        raise IadeKopruHatasi("İade Panel API anahtarı eksik veya geçersiz.")
    if response.status_code >= 400:
        message = result.get("mesaj") if isinstance(result, dict) else None
        status_code = 400 if response.status_code in {400, 413, 422} else 503
        raise IadeKopruHatasi(message or "DHL eCommerce iade kodu oluşturulamadı.", status_code)
    if not isinstance(result, dict) or not result.get("ok") or not result.get("iadeKodu"):
        raise IadeKopruHatasi("İade servisinin cevap biçimi beklenenden farklı.")
    return result


@iade_yonetimi_bp.route("/iade-yonetimi")
def index():
    shop_domain = _config_value("SHOPIFY_SHOP_DOMAIN")
    if shop_domain:
        parsed = urlparse(shop_domain if "://" in shop_domain else f"https://{shop_domain}")
        shopify_admin_base = f"https://{parsed.netloc}/admin/orders" if parsed.netloc else ""
    else:
        shopify_admin_base = ""
    return render_template(
        "iade_yonetimi.html",
        shopify_admin_base=shopify_admin_base,
    )


@iade_yonetimi_bp.route("/iade-yonetimi/veri")
def veri():
    kategori = request.args.get("durum", "").strip().lower() or None
    sync = request.args.get("sync") == "1"

    if kategori and kategori not in VALID_KATEGORILER:
        return jsonify({"mesaj": "Geçersiz iade kategorisi."}), 400

    try:
        return jsonify(fetch_iadeler(kategori=kategori, sync=sync))
    except IadeKopruHatasi as exc:
        logger.warning("İade yönetimi verisi alınamadı: %s", exc)
        return jsonify({"mesaj": str(exc)}), 503


@iade_yonetimi_bp.route("/iade-yonetimi/olustur", methods=["POST"])
def olustur():
    if session.get("role") not in {"admin", "manager"}:
        return jsonify({"mesaj": "İade kodu oluşturmak için yönetici yetkisi gerekli."}), 403
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return jsonify({"mesaj": "Geçersiz istek."}), 400

    data = request.get_json(silent=True) or {}
    order_number = str(data.get("orderNumber") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    customer_name = str(data.get("customerName") or "").strip()
    reason = str(data.get("reason") or "").strip()
    source = str(data.get("source") or "").strip().lower()
    request_id = str(data.get("requestId") or "").strip()

    if not order_number or len(order_number) > 64 or not re.search(r"[A-Za-z0-9]", order_number):
        return jsonify({"mesaj": "Geçerli bir sipariş numarası girin."}), 400
    if source not in VALID_KAYNAKLAR:
        return jsonify({"mesaj": "Geçerli bir sipariş kaynağı seçin."}), 400
    if not reason or len(reason) > 400:
        return jsonify({"mesaj": "İade veya değişim nedenini girin (en fazla 400 karakter)."}), 400
    if len(customer_name) > 150:
        return jsonify({"mesaj": "Müşteri adı en fazla 150 karakter olabilir."}), 400
    if email and (len(email) > 255 or not EMAIL_PATTERN.fullmatch(email)):
        return jsonify({"mesaj": "Geçerli bir e-posta adresi girin."}), 400
    try:
        uuid.UUID(request_id)
    except (ValueError, TypeError, AttributeError):
        return jsonify({"mesaj": "Geçersiz işlem kimliği. Formu kapatıp yeniden açın."}), 400

    created_by = session.get("username") or " ".join(filter(None, [
        session.get("first_name"), session.get("last_name")
    ])) or "panel"
    payload = {
        "orderNumber": order_number,
        "email": email,
        "customerName": customer_name,
        "reason": reason,
        "source": source,
        "requestId": request_id,
        "createdBy": str(created_by)[:120],
    }

    try:
        result = create_iade(payload)
        try:
            from user_logs import log_user_action
            log_user_action("CREATE", {
                "işlem_açıklaması": f"DHL eCommerce iade kodu oluşturuldu — {order_number}",
                "sayfa": "Site İade Yönetimi",
                "sipariş_no": order_number,
                "kaynak": source,
                "iade_kodu": result.get("iadeKodu"),
            })
        except Exception:
            logger.exception("İade kodu kullanıcı loguna yazılamadı.")
        return jsonify(result), 200
    except IadeKopruHatasi as exc:
        logger.warning("İade kodu oluşturulamadı: %s", exc)
        return jsonify({"mesaj": str(exc)}), exc.status_code
