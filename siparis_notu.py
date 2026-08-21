# siparis_notu.py
"""
📝 Sipariş Notları — siparişe özel serbest metin not.

"Bu siparişi bilerek şu ufak ayrıntıyla gönderiyoruz" gibi ayrıntılar sonradan
unutulmasın diye: not, sipariş listesi kartında ve sipariş hazırla ekranında
görünür ve düzenlenir. Sipariş satırları statü değişiminde tablolar arasında
fiziksel taşındığı için not yaşam döngüsü tablolarına değil, order_number ile
ayrı `siparis_notu` tablosuna yazılır (models.SiparisNotu, tablo additive:
scripts/create_siparis_notu_table.py).

Route güvenliği takip_notu ile birebir: 2FA kalkanı + fetch başlığı CSRF'i.
"""
import logging

from flask import Blueprint, jsonify, request, session

from models import db, SiparisNotu

logger = logging.getLogger(__name__)

siparis_notu_bp = Blueprint("siparis_notu", __name__, url_prefix="/siparis-notu")


@siparis_notu_bp.before_request
def _guvenlik_kalkani():
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


def get_notes_map(order_numbers) -> dict:
    """order_number → not metni. Hata → boş sözlük (liste akışı durmaz)."""
    numbers = [n for n in {str(n or "").strip() for n in (order_numbers or [])} if n]
    if not numbers:
        return {}
    try:
        rows = (SiparisNotu.query
                .filter(SiparisNotu.order_number.in_(numbers))
                .with_entities(SiparisNotu.order_number, SiparisNotu.note)
                .all())
        return {on: note for on, note in rows}
    except Exception:
        logger.warning("[SIPARIS-NOT] notlar okunamadı", exc_info=True)
        db.session.rollback()
        return {}


def get_note(order_number) -> str:
    """Tek siparişin notu (yoksa boş metin)."""
    on = str(order_number or "").strip()
    return get_notes_map([on]).get(on, "")


@siparis_notu_bp.route("/api/kaydet", methods=["POST"])
def kaydet():
    """Notu ekle/güncelle; boş not gönderilirse kaydı siler."""
    from flask_login import current_user
    data = request.get_json(silent=True) or {}
    order_number = str(data.get("order_number") or "").strip()
    note = str(data.get("note") or "").strip()
    if not order_number:
        return jsonify({"success": False, "message": "Sipariş numarası boş"}), 400
    try:
        kayit = SiparisNotu.query.filter_by(order_number=order_number).first()
        if not note:
            if kayit is not None:
                db.session.delete(kayit)
                db.session.commit()
            return jsonify({"success": True, "note": "", "message": "Not silindi"})
        kullanici = getattr(current_user, "username", None) or ""
        if kayit is not None:
            kayit.note = note
            kayit.updated_by = kullanici
        else:
            db.session.add(SiparisNotu(order_number=order_number, note=note,
                                       updated_by=kullanici))
        db.session.commit()
        return jsonify({"success": True, "note": note, "message": "Not kaydedildi"})
    except Exception:
        db.session.rollback()
        logger.exception("[SIPARIS-NOT] kaydetme hatası")
        return jsonify({"success": False, "message": "Kaydedilemedi"}), 500
