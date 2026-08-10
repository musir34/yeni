import logging
import os
from urllib.parse import urlparse

import requests
from flask import Blueprint, current_app, jsonify, render_template, request


logger = logging.getLogger(__name__)

iade_yonetimi_bp = Blueprint("iade_yonetimi", __name__)

VALID_KATEGORILER = {"bekliyor", "kargoda", "teslim"}


class IadeKopruHatasi(Exception):
    """İade köprü servisi panel isteğini tamamlayamadığında kullanılır."""


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
