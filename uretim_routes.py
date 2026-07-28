# uretim_routes.py
"""
Üretim Modu sayfası + JSON API'leri.

Tüm route'lar /uretim altında — app.py'deki check_authentication kalkanı
kapsamındadır (login zorunlu; /api/ öneki bilinçli olarak KULLANILMADI çünkü
o önek auth'tan muaf). Güvenlik kalkanı deseni: trendyol_qna/qna_routes.py.
"""
import json
import logging
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, session

from models import db, UretimSiparis

logger = logging.getLogger(__name__)

uretim_bp = Blueprint("uretim", __name__, url_prefix="/uretim")


@uretim_bp.before_request
def _guvenlik_kalkani():
    """
    1) 2FA kalkanı (derinlemesine savunma): app-level check_authentication
       zaten yönlendiriyor; global kalkanda gedik açılsa bile bu blueprint
       2FA doğrulanmadan çalışmaz.
    2) Hafif CSRF koruması: state değiştiren istekler yalnızca fetch'in
       ekleyebildiği özel başlıkla kabul edilir.
    """
    from flask import abort
    from flask_login import current_user
    try:
        dogrulanmis = current_user.is_authenticated and session.get("totp_verified")
    except Exception:
        dogrulanmis = False
    if not dogrulanmis:
        abort(403)
    if request.method == "POST" and request.headers.get("X-Requested-With") != "fetch":
        abort(403)


def _to_dict(r: UretimSiparis) -> dict:
    from time_utils import fmt_ist
    try:
        detaylar = json.loads(r.details) if r.details else []
    except (json.JSONDecodeError, TypeError):
        detaylar = []
    return {
        "id": r.id,
        "order_number": r.order_number,
        "package_number": r.package_number,
        "product_main_id": r.product_main_id,
        "details": detaylar,
        "customer_name": r.customer_name,
        "order_date": fmt_ist(r.order_date, "%d.%m.%Y %H:%M"),
        "uretildi": r.uretildi,
        "uretildi_at": fmt_ist(r.uretildi_at, "%d.%m.%Y %H:%M"),
        "mail_sent": bool(r.mail_sent_at),
        "created_at": fmt_ist(r.created_at, "%d.%m.%Y %H:%M"),
    }


@uretim_bp.route("/", methods=["GET"])
def index():
    return render_template("uretim.html")


@uretim_bp.route("/api/liste", methods=["GET"])
def liste():
    durum = (request.args.get("durum") or "bekleyen").strip()
    rows = (UretimSiparis.query
            .filter_by(uretildi=(durum == "uretildi"))
            .order_by(UretimSiparis.created_at.desc())
            .limit(500)
            .all())
    # Üretim beklerken Trendyol'da iptal edilen sipariş: üretici boşuna üretmesin
    # diye listede İPTAL rozetiyle işaretlenir (kayıt silinmez, iz kalır).
    iptaller = set()
    if rows:
        try:
            from models import OrderCancelled
            nolar = [r.order_number for r in rows]
            iptaller = {o.order_number for o in
                        OrderCancelled.query
                        .filter(OrderCancelled.order_number.in_(nolar))
                        .with_entities(OrderCancelled.order_number)}
        except Exception:
            logger.warning("[URETIM] iptal kontrolü yapılamadı", exc_info=True)
    sonuc = []
    for r in rows:
        d = _to_dict(r)
        d["iptal"] = r.order_number in iptaller
        sonuc.append(d)
    return jsonify({"success": True, "rows": sonuc})


@uretim_bp.route("/api/uretildi/<int:kayit_id>", methods=["POST"])
def uretildi_isaretle(kayit_id: int):
    kayit = db.session.get(UretimSiparis, kayit_id)
    if not kayit:
        return jsonify({"success": False, "message": "Kayıt bulunamadı"}), 404
    geri_al = bool((request.get_json(silent=True) or {}).get("geri_al"))
    kayit.uretildi = not geri_al
    kayit.uretildi_at = None if geri_al else datetime.utcnow()
    db.session.commit()
    mesaj = "Üretildi işareti geri alındı" if geri_al else "Üretildi olarak işaretlendi — sipariş normal akışına devam edecek"
    logger.info(f"[URETIM] {kayit.order_number}: {mesaj}")
    return jsonify({"success": True, "message": mesaj})


@uretim_bp.route("/api/ayar", methods=["GET"])
def ayar():
    # Mail alıcıları kullanıcı yönetiminden ('uretim_siparis' bildirimi) yönetilir;
    # burada yalnız model listesi döner.
    from uretim_modu import get_uretim_ayar
    return jsonify({"success": True, "ayar": get_uretim_ayar()})


@uretim_bp.route("/api/model-toggle", methods=["POST"])
def model_toggle():
    from uretim_modu import toggle_model, URETIM_SABIT_ADET
    data = request.get_json(silent=True) or {}
    model_id = str(data.get("model") or "").strip()
    if not model_id:
        return jsonify({"success": False, "message": "Model kodu boş"}), 400
    try:
        acik = toggle_model(model_id)
    except Exception:
        db.session.rollback()
        logger.exception("[URETIM] model toggle hatası")
        return jsonify({"success": False, "message": "Kaydedilemedi"}), 500
    mesaj = (f"{model_id} üretim moduna ALINDI — Trendyol'a sabit {URETIM_SABIT_ADET} stok gidecek"
             if acik else f"{model_id} üretim modundan çıkarıldı — ilk senkronla gerçek stok gider")
    logger.info(f"[URETIM] {mesaj}")
    return jsonify({"success": True, "acik": acik, "message": mesaj})
