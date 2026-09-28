"""
WhatsApp duyuru sayfası (/whatsapp-duyuru).

Yönetici başlık + metin yazar, alıcıları seçer; mesaj whatsapp_notify
(Meta test numarası hattı) üzerinden çalışanlara gider. Alıcılar .env'deki
WHATSAPP_STAFF_NUMBERS listesidir; sayfaya numaraların yalnız son 4 hanesi iner.

Güvenlik kalkanı deseni: whatsapp_baglanti (2FA + fetch başlığı) + admin rolü.
"""
import logging

from flask import Blueprint, jsonify, render_template, request, session

logger = logging.getLogger(__name__)

whatsapp_duyuru_bp = Blueprint("whatsapp_duyuru", __name__,
                               url_prefix="/whatsapp-duyuru")

BASLIK_MAX = 60
# Pencere kapalıyken mesaj şablonla gider; şablon parametresi 200 karakterde
# kesilir. Yazılanla gidenin aynı olması için metin de bu sınırla alınır.
METIN_MAX = 200


@whatsapp_duyuru_bp.before_request
def _guvenlik_kalkani():
    from flask import abort
    from flask_login import current_user
    try:
        dogrulanmis = (current_user.is_authenticated
                       and session.get("totp_verified")
                       and getattr(current_user, "role", "") == "admin")
    except Exception:
        dogrulanmis = False
    if not dogrulanmis:
        abort(403)
    if request.method == "POST" and request.headers.get("X-Requested-With") != "fetch":
        abort(403)


@whatsapp_duyuru_bp.route("", methods=["GET"])
@whatsapp_duyuru_bp.route("/", methods=["GET"])
def sayfa():
    from whatsapp_notify import is_configured, staff_last4
    return render_template(
        "whatsapp_duyuru.html",
        hazir=is_configured(),
        alicilar=staff_last4(),
        baslik_max=BASLIK_MAX,
        metin_max=METIN_MAX,
    )


@whatsapp_duyuru_bp.route("/api/gonder", methods=["POST"])
def gonder():
    """Seçilen alıcılara duyuruyu gönderir; alıcı bazında sonucu döner."""
    from whatsapp_notify import is_configured, notify_staff, staff_last4

    veri = request.get_json(silent=True) or {}
    baslik = " ".join(str(veri.get("baslik") or "").split())
    metin = " ".join(str(veri.get("metin") or "").split())
    secilen = veri.get("alicilar")

    if not is_configured():
        return jsonify({"success": False,
                        "message": "Sunucu .env dosyasında WHATSAPP_STAFF_* ayarları eksik."}), 500
    if not baslik or len(baslik) > BASLIK_MAX:
        return jsonify({"success": False,
                        "message": f"Başlık 1–{BASLIK_MAX} karakter olmalı."}), 400
    if not metin or len(metin) > METIN_MAX:
        return jsonify({"success": False,
                        "message": f"Metin 1–{METIN_MAX} karakter olmalı."}), 400
    if not isinstance(secilen, list):
        return jsonify({"success": False, "message": "Alıcı seçilmedi."}), 400
    gecerli = [a for a in staff_last4() if a in {str(s) for s in secilen}]
    if not gecerli:
        return jsonify({"success": False, "message": "Alıcı seçilmedi."}), 400

    sonuclar = notify_staff(baslik, metin, only_last4=gecerli)
    giden = [s for s in sonuclar if s.get("ok")]

    try:
        from user_logs import log_user_action
        log_user_action("CREATE: whatsapp_duyuru", {
            "sayfa": "WhatsApp Duyuru",
            "başlık": baslik,
            "alıcı": ", ".join(f"…{a}" for a in gecerli),
            "giden": f"{len(giden)}/{len(sonuclar)}",
        })
    except Exception:
        logger.exception("[WA-DUYURU] hareket logu yazılamadı")

    return jsonify({
        "success": bool(giden) and len(giden) == len(sonuclar),
        "sonuclar": [{
            "alici": s.get("to_last4"),
            "ok": bool(s.get("ok")),
            "kanal": s.get("via"),
            "hata": None if s.get("ok") else f"{s.get('code')}: {s.get('message')}",
        } for s in sonuclar],
    })
