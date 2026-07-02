"""
Trendyol Soru-Cevap panel sayfası + JSON API'leri.

Tüm route'lar /soru-cevap altında — app.py'deki check_authentication kalkanı
kapsamındadır (login zorunlu; /api/ öneki bilinçli olarak KULLANILMADI çünkü
o önek auth'tan muaf).
"""
import logging
from datetime import timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, render_template, request, session

from models import db, TrendyolQuestion

logger = logging.getLogger(__name__)

qna_bp = Blueprint("qna", __name__, url_prefix="/soru-cevap")


@qna_bp.before_request
def _guvenlik_kalkani():
    """
    1) 2FA kalkanı (derinlemesine savunma): app-level check_authentication
       zaten yönlendiriyor; global kalkanda gedik açılsa bile bu blueprint
       2FA doğrulanmadan çalışmaz.
    2) Hafif CSRF koruması: state değiştiren istekler yalnızca fetch'in
       ekleyebildiği özel başlıkla kabul edilir (basit cross-site form bu
       başlığı koyamaz; CORS preflight'ı da geçemez). Cevaplar Trendyol'da
       herkese açık yayınlandığı için ekstra önlem.
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

IST = ZoneInfo("Europe/Istanbul")
PAGE_SIZE = 25


def _tr(dt) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).strftime("%d.%m.%Y %H:%M")


def _to_dict(r: TrendyolQuestion) -> dict:
    return {
        "id": r.id,
        "text": r.text,
        "user_name": r.user_name if r.show_user_name else (r.user_name or "Müşteri"),
        "product_name": r.product_name,
        "product_main_id": r.product_main_id,
        "image_url": r.image_url,
        "web_url": r.web_url,
        "status": r.status,
        "public": r.public,
        "creation_date": _tr(r.creation_date),
        "answer_text": r.answer_text,
        "answer_date": _tr(r.answer_date),
        "rejected_answer_text": r.rejected_answer_text,
        "report_reason": r.report_reason,
        "answered_by": r.answered_by,
        "ai_draft": r.ai_draft,
        "ai_draft_status": r.ai_draft_status or "none",
    }


@qna_bp.route("/", methods=["GET"])
def index():
    return render_template("soru_cevap.html")


@qna_bp.route("/api/sorular", methods=["GET"])
def sorular():
    status = (request.args.get("status") or "WAITING_FOR_ANSWER").strip()
    q = (request.args.get("q") or "").strip()
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except ValueError:
        page = 1

    query = db.session.query(TrendyolQuestion)
    if status == "DIGER":
        query = query.filter(TrendyolQuestion.status.in_(("REJECTED", "REPORTED", "UNANSWERED")))
    elif status != "ALL":
        query = query.filter(TrendyolQuestion.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(
            TrendyolQuestion.text.ilike(like)
            | TrendyolQuestion.product_name.ilike(like)
            | TrendyolQuestion.product_main_id.ilike(like)
        )

    total = query.count()
    rows = (
        query.order_by(TrendyolQuestion.creation_date.desc().nullslast())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )
    return jsonify({
        "ok": True,
        "toplam": total,
        "sayfa": page,
        "sayfa_boyu": PAGE_SIZE,
        "sorular": [_to_dict(r) for r in rows],
    })


@qna_bp.route("/api/bekleyen-sayi", methods=["GET"])
def bekleyen_sayi():
    from trendyol_qna.qna_service import waiting_count
    return jsonify({"ok": True, "sayi": waiting_count()})


@qna_bp.route("/api/cevapla", methods=["POST"])
def cevapla():
    payload = request.get_json(silent=True) or {}
    try:
        qid = int(payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "hata": "Geçersiz soru ID."}), 400
    text = (payload.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "hata": "Cevap boş olamaz."}), 400

    from trendyol_qna.qna_service import answer_question
    sonuc = answer_question(qid, text, username=session.get("username"))
    return jsonify(sonuc), (200 if sonuc["ok"] else 422)


@qna_bp.route("/api/taslak/<int:qid>", methods=["POST"])
def taslak(qid: int):
    """
    AI taslağını (yeniden) üretmeyi TETİKLER — üretim arka plan thread'inde
    yapılır (claude ~1-2 dk sürebilir; web worker'ı bloklamayız). Ön yüz
    /api/taslak-durum/<id> ile sonucu yoklar.
    """
    row = db.session.get(TrendyolQuestion, qid)
    if not row:
        return jsonify({"ok": False, "hata": "Soru bulunamadı."}), 404
    from trendyol_qna.qna_ai import generate_drafts_async
    generate_drafts_async([qid])
    return jsonify({"ok": True, "durum": "pending"})


@qna_bp.route("/api/taslak-durum/<int:qid>", methods=["GET"])
def taslak_durum(qid: int):
    row = db.session.get(TrendyolQuestion, qid)
    if not row:
        return jsonify({"ok": False, "hata": "Soru bulunamadı."}), 404
    return jsonify({
        "ok": True,
        "durum": row.ai_draft_status or "none",
        "taslak": row.ai_draft if row.ai_draft_status == "ready" else None,
    })


@qna_bp.route("/api/senkron", methods=["POST"])
def senkron():
    """Elle tam senkron (son 14 gün, tüm statüler)."""
    from trendyol_qna.qna_service import sync_questions
    try:
        yeni = sync_questions(days=14)
        return jsonify({"ok": True, "yeni": len(yeni)})
    except Exception as e:
        logger.exception("[QNA] elle senkron hatası")
        return jsonify({"ok": False, "hata": str(e)}), 500
