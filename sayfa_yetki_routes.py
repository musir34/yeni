"""Sayfa yetkisi düzenleme uçları — YALNIZ SAHİP (users.is_owner).

Kullanıcı Yönetimi ekranındaki "Sayfa Yetkileri" paneli buraya yazar. Admin dahil kimse
sahip değilse 403. Değişiklik user_logs'a yazılır (kim, kime, hangi sayfalar).
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request, session
from flask_login import current_user

from models import User
from sayfa_yetki import SAYFA_MAP, istisnalari_kaydet, kullanici_yetki_durumu

logger = logging.getLogger(__name__)
sayfa_yetki_bp = Blueprint("sayfa_yetki", __name__)


@sayfa_yetki_bp.before_request
def _sadece_sahip():
    if not (getattr(current_user, "is_authenticated", False) and session.get("totp_verified")):
        return jsonify({"success": False, "error": "Yetkisiz erişim"}), 401
    if not getattr(current_user, "is_owner", False):
        return jsonify({"success": False, "error": "Sayfa yetkilerini yalnız sahip düzenleyebilir"}), 403
    if request.method == "POST" and request.headers.get("X-Requested-With") != "fetch":
        return jsonify({"success": False, "error": "Geçersiz istek"}), 403
    return None


@sayfa_yetki_bp.route("/admin/sayfa-yetki/<username>", methods=["GET"])
def yetki_oku(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"success": False, "error": "Kullanıcı bulunamadı"}), 404
    return jsonify({"success": True, "username": username, "rol": user.role,
                    "sahip": bool(user.is_owner), "sayfalar": kullanici_yetki_durumu(user)})


@sayfa_yetki_bp.route("/admin/sayfa-yetki/<username>", methods=["POST"])
def yetki_kaydet(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"success": False, "error": "Kullanıcı bulunamadı"}), 404
    if user.is_owner:
        return jsonify({"success": False, "error": "Sahibin yetkisi kısıtlanamaz"}), 400
    veri = request.get_json(silent=True) or {}
    kodlar = veri.get("kodlar")
    if not isinstance(kodlar, list):
        return jsonify({"success": False, "error": "kodlar listesi bekleniyor"}), 400
    bilinmeyen = [k for k in kodlar if k not in SAYFA_MAP]
    if bilinmeyen:
        return jsonify({"success": False, "error": f"Bilinmeyen sayfa kodu: {', '.join(bilinmeyen)}"}), 400

    fark = istisnalari_kaydet(user, set(kodlar))
    eklenen = sorted(SAYFA_MAP[k].ad for k, izin in fark.items() if izin)
    kaldirilan = sorted(SAYFA_MAP[k].ad for k, izin in fark.items() if not izin)
    try:
        from user_logs import log_user_action
        log_user_action("UPDATE", {
            "işlem_açıklaması": f"{username} sayfa yetkileri güncellendi — rol: {user.role}; "
                                f"eklenen: {', '.join(eklenen) or '-'}; kaldırılan: {', '.join(kaldirilan) or '-'}",
            "sayfa": "Kullanıcı Yönetimi",
        })
    except Exception:
        logger.warning("[SAYFA-YETKI] hareket loglanamadı", exc_info=True)
    logger.info("[SAYFA-YETKI] %s → %s: +%s −%s", current_user.username, username, eklenen, kaldirilan)
    return jsonify({"success": True, "eklenen": eklenen, "kaldirilan": kaldirilan,
                    "sayfalar": kullanici_yetki_durumu(user)})
