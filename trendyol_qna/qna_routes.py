"""
Trendyol Soru-Cevap panel sayfası + JSON API'leri.

Tüm route'lar /soru-cevap altında — app.py'deki check_authentication kalkanı
kapsamındadır (login zorunlu; /api/ öneki bilinçli olarak KULLANILMADI çünkü
o önek auth'tan muaf).
"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, render_template, request, session

from models import (db, TrendyolQuestion, ShopifyQuestion, InstagramComment,
                    InstagramConversation, InstagramMessage)

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
        "source": "trendyol",
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


def _shopify_to_dict(r: ShopifyQuestion) -> dict:
    """Shopify sorusunu Trendyol kart sözlüğüyle aynı şekle getirir."""
    from trendyol_qna.shopify_qna import whatsapp_link
    return {
        "id": r.id,
        "source": "shopify",
        "text": r.question,
        "user_name": r.name or "Müşteri",
        "name": r.name or "",
        "contact_type": r.contact_type,
        "email": r.email,
        "phone": r.phone,
        "wa_link": whatsapp_link(r) if r.contact_type == "phone" else None,
        "product_name": r.product_title,
        "product_main_id": r.product_sku or None,
        "image_url": r.product_image or None,
        "web_url": r.page_url,
        "status": "WAITING_FOR_ANSWER" if r.status == "new" else "ANSWERED",
        "public": False,
        "creation_date": _tr(r.created_at),
        "answer_text": r.answer,
        "answer_date": _tr(r.answered_at),
        "rejected_answer_text": None,
        "report_reason": None,
        "answered_by": r.answered_by,
        "ai_draft": r.ai_draft,
        "ai_draft_status": r.ai_draft_status or "none",
    }


INSTAGRAM_KART_MESAJ = 20   # kartta gösterilen son mesaj sayısı


def yorum_cekme_acik() -> bool:
    """Gönderi yorumları yalnız INSTAGRAM_COMMENTS=1 ise çekilir (anahtarda yorum izni gerekir)."""
    import os
    return str(os.getenv("INSTAGRAM_COMMENTS", "0")).lower() in ("1", "true", "yes")


def _urun_sozlugu(bag) -> dict | None:
    """Ürün bağını kartın kullandığı sözlüğe çevirir (bağ yoksa None)."""
    if bag is None:
        return None
    return {
        "title": bag.title or "",
        "url": bag.url or "",
        "renk": bag.color or "",
        "onayli": bool(bag.confirmed),
        "product_id": bag.shopify_product_id,
    }


def _instagram_to_dict(c: InstagramConversation, mesajlar: list[InstagramMessage], bag=None) -> dict:
    """Instagram konuşmasını kart sözlüğüne çevirir (mesajlar eskiden yeniye; bag: ürün bağı)."""
    from trendyol_qna.instagram_dm import TEXT_MAX, pencere_acik, pencere_bitisi
    bitis = pencere_bitisi(c)
    son_giden = next((m for m in reversed(mesajlar) if m.direction == "out"), None)
    son_gelen = next((m for m in reversed(mesajlar) if m.direction == "in"), None)
    return {
        "id": c.id,
        "source": "instagram",
        "text": (son_gelen.text if son_gelen else "") or "",
        "user_name": c.name or (f"@{c.username}" if c.username else "Instagram kullanıcısı"),
        "username": c.username or "",
        "status": "WAITING_FOR_ANSWER" if c.status == "new" else "ANSWERED",
        "public": False,
        "creation_date": _tr(c.last_customer_at or c.last_message_at),
        "answer_text": son_giden.text if son_giden else None,
        "answer_date": _tr(c.answered_at),
        "answered_by": c.answered_by,
        "ai_draft": c.ai_draft,
        "ai_draft_status": c.ai_draft_status or "none",
        "pencere_acik": pencere_acik(c),
        "pencere_bitis": bitis.isoformat() if bitis else None,
        "metin_azami": TEXT_MAX,
        "urun": _urun_sozlugu(bag),
        "mesajlar": [
            {
                "yon": m.direction,
                "text": m.text or "",
                "ek_tipi": m.attachment_type or "",
                "ek_url": m.attachment_url or "",
                "tarih": _tr(m.created_at),
                "gonderen": m.sent_by,
            }
            for m in mesajlar
        ],
    }


def _instagram_yorum_to_dict(y: InstagramComment, bag=None) -> dict:
    """Instagram gönderi yorumunu kart sözlüğüne çevirir (bag: gönderinin ürün bağı)."""
    from trendyol_qna.instagram_dm import (TEXT_MAX, YORUM_NOTU_MAX, YORUM_NOTU_VARSAYILAN,
                                           ozel_yanit_bitisi)
    bitis = ozel_yanit_bitisi(y)
    durum = {"new": "WAITING_FOR_ANSWER", "answered": "ANSWERED"}.get(y.status, "IGNORED")
    return {
        "id": y.id,
        "source": "instagram_yorum",
        "text": y.text or "",
        "user_name": f"@{y.username}" if y.username else "Instagram kullanıcısı",
        "username": y.username or "",
        "product_name": (y.media_caption or "").strip()[:140],
        "image_url": y.media_thumb or None,
        "web_url": y.media_permalink or None,
        "status": durum,
        "public": True,
        "creation_date": _tr(y.created_at),
        "answer_text": y.answer or None,
        "yorum_notu": y.public_note or None,
        "answer_date": _tr(y.answered_at),
        "answered_by": y.answered_by,
        "ai_draft": y.ai_draft,
        "ai_draft_status": y.ai_draft_status or "none",
        "ozel_yanit_bitis": bitis.isoformat() if bitis else None,
        "metin_azami": TEXT_MAX,
        "not_azami": YORUM_NOTU_MAX,
        "not_varsayilan": YORUM_NOTU_VARSAYILAN,
        "urun": _urun_sozlugu(bag),
    }


def _instagram_mesajlari(conv_ids: list[int]) -> dict[int, list[InstagramMessage]]:
    """Verilen konuşmaların son mesajları, konuşma başına eskiden yeniye (tek sorgu)."""
    gruplar: dict[int, list[InstagramMessage]] = {cid: [] for cid in conv_ids}
    if not conv_ids:
        return gruplar
    satirlar = (
        db.session.query(InstagramMessage)
        .filter(InstagramMessage.conversation_id.in_(conv_ids))
        .order_by(InstagramMessage.created_at.desc(), InstagramMessage.id.desc())
        .limit(len(conv_ids) * INSTAGRAM_KART_MESAJ * 3)
        .all()
    )
    for m in satirlar:
        grup = gruplar.get(m.conversation_id)
        if grup is not None and len(grup) < INSTAGRAM_KART_MESAJ:
            grup.append(m)
    return {cid: grup[::-1] for cid, grup in gruplar.items()}


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

    # Shopify soruları aynı listeye tarihe göre karışır (DIGER sekmesi Shopify'da yok)
    sh_status = {"WAITING_FOR_ANSWER": "new", "ANSWERED": "answered", "ALL": None}
    sh_rows: list[ShopifyQuestion] = []
    sh_total = 0
    fetch_limit = page * PAGE_SIZE
    if status in sh_status:
        try:
            sh_query = db.session.query(ShopifyQuestion)
            if sh_status[status]:
                sh_query = sh_query.filter(ShopifyQuestion.status == sh_status[status])
            if q:
                like = f"%{q}%"
                sh_query = sh_query.filter(
                    ShopifyQuestion.question.ilike(like)
                    | ShopifyQuestion.product_title.ilike(like)
                    | ShopifyQuestion.name.ilike(like)
                )
            sh_total = sh_query.count()
            sh_rows = (
                sh_query.order_by(ShopifyQuestion.created_at.desc().nullslast())
                .limit(fetch_limit)
                .all()
            )
        except Exception:
            db.session.rollback()
            logger.exception("[QNA] Shopify soruları okunamadı (tablo yok olabilir)")

    # Instagram konuşmaları da aynı listeye karışır (kart = konuşma)
    ig_rows: list[InstagramConversation] = []
    ig_total = 0
    ig_mesaj: dict[int, list[InstagramMessage]] = {}
    ig_bag: dict = {}
    if status in sh_status:
        try:
            ig_query = db.session.query(InstagramConversation)
            if sh_status[status]:
                ig_query = ig_query.filter(InstagramConversation.status == sh_status[status])
            if q:
                like = f"%{q}%"
                eslesen = db.session.query(InstagramMessage.conversation_id).filter(
                    InstagramMessage.text.ilike(like))
                ig_query = ig_query.filter(
                    InstagramConversation.username.ilike(like)
                    | InstagramConversation.name.ilike(like)
                    | InstagramConversation.id.in_(eslesen)
                )
            ig_total = ig_query.count()
            ig_rows = (
                ig_query.order_by(InstagramConversation.last_message_at.desc().nullslast())
                .limit(fetch_limit)
                .all()
            )
            ig_mesaj = _instagram_mesajlari([r.id for r in ig_rows])
            if ig_rows:
                from models import InstagramMediaProduct
                from trendyol_qna.instagram_urun import konusma_anahtari
                anahtarlar = {konusma_anahtari(r.id): r.id for r in ig_rows}
                ig_bag = {anahtarlar[b.media_id]: b for b in db.session.query(InstagramMediaProduct)
                          .filter(InstagramMediaProduct.media_id.in_(list(anahtarlar))).all()}
        except Exception:
            db.session.rollback()
            ig_rows, ig_total, ig_bag = [], 0, {}
            logger.exception("[QNA] Instagram konuşmaları okunamadı (tablo yok olabilir)")

    # Instagram gönderi yorumları (yoksayılanlar yalnız "Tümü"nde görünür)
    yr_rows: list[InstagramComment] = []
    yr_total = 0
    yr_bag: dict = {}
    if status in sh_status:
        try:
            yr_query = db.session.query(InstagramComment)
            if sh_status[status]:
                yr_query = yr_query.filter(InstagramComment.status == sh_status[status])
            if q:
                like = f"%{q}%"
                yr_query = yr_query.filter(
                    InstagramComment.text.ilike(like)
                    | InstagramComment.username.ilike(like)
                    | InstagramComment.media_caption.ilike(like)
                )
            yr_total = yr_query.count()
            yr_rows = (
                yr_query.order_by(InstagramComment.created_at.desc().nullslast())
                .limit(fetch_limit)
                .all()
            )
            from models import InstagramMediaProduct
            yr_medyalar = {r.media_id for r in yr_rows}
            if yr_medyalar:
                yr_bag = {b.media_id: b for b in db.session.query(InstagramMediaProduct)
                          .filter(InstagramMediaProduct.media_id.in_(yr_medyalar)).all()}
        except Exception:
            db.session.rollback()
            yr_rows, yr_total, yr_bag = [], 0, {}
            logger.exception("[QNA] Instagram yorumları okunamadı (tablo yok olabilir)")

    total = query.count()
    t_rows = (
        query.order_by(TrendyolQuestion.creation_date.desc().nullslast())
        .limit(fetch_limit)
        .all()
    )

    def _key(dt):
        if not dt:
            return datetime.min.replace(tzinfo=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    merged = sorted(
        [(_key(r.creation_date), _to_dict(r)) for r in t_rows]
        + [(_key(r.created_at), _shopify_to_dict(r)) for r in sh_rows]
        + [(_key(r.last_message_at), _instagram_to_dict(r, ig_mesaj.get(r.id, []), ig_bag.get(r.id)))
           for r in ig_rows]
        + [(_key(r.created_at), _instagram_yorum_to_dict(r, yr_bag.get(r.media_id))) for r in yr_rows],
        key=lambda x: x[0],
        reverse=True,
    )
    offset = (page - 1) * PAGE_SIZE
    return jsonify({
        "ok": True,
        "toplam": total + sh_total + ig_total + yr_total,
        "sayfa": page,
        "sayfa_boyu": PAGE_SIZE,
        "sorular": [d for _, d in merged[offset:offset + PAGE_SIZE]],
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


@qna_bp.route("/api/shopify/cevapla", methods=["POST"])
def shopify_cevapla():
    """Shopify sorusu: email ise mail gönderir, telefon ise yanıtlandı işaretler."""
    payload = request.get_json(silent=True) or {}
    try:
        qid = int(payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "hata": "Geçersiz soru ID."}), 400

    from trendyol_qna.shopify_qna import answer_shopify_question
    sonuc = answer_shopify_question(qid, (payload.get("text") or "").strip(),
                                    username=session.get("username"))
    return jsonify(sonuc), (200 if sonuc["ok"] else 422)


@qna_bp.route("/api/shopify/taslak/<int:qid>", methods=["POST"])
def shopify_taslak(qid: int):
    """Shopify sorusu için AI taslağını (yeniden) üretmeyi tetikler (arka plan)."""
    row = db.session.get(ShopifyQuestion, qid)
    if not row:
        return jsonify({"ok": False, "hata": "Soru bulunamadı."}), 404
    payload = request.get_json(silent=True) or {}
    talimat = (payload.get("talimat") or "").strip()[:500] or None
    mevcut_metin = (payload.get("metin") or "").strip()[:2000] or None
    from trendyol_qna.qna_ai import generate_shopify_drafts_async
    generate_shopify_drafts_async([qid], talimat=talimat, mevcut_metin=mevcut_metin)
    return jsonify({"ok": True, "durum": "pending"})


@qna_bp.route("/api/shopify/taslak-durum/<int:qid>", methods=["GET"])
def shopify_taslak_durum(qid: int):
    row = db.session.get(ShopifyQuestion, qid)
    if not row:
        return jsonify({"ok": False, "hata": "Soru bulunamadı."}), 404
    return jsonify({
        "ok": True,
        "durum": row.ai_draft_status or "none",
        "taslak": row.ai_draft if row.ai_draft_status == "ready" else None,
    })


@qna_bp.route("/api/instagram/cevapla", methods=["POST"])
def instagram_cevapla():
    """Instagram konuşmasına cevabı direkt mesaj olarak gönderir (24 saat kuralı)."""
    payload = request.get_json(silent=True) or {}
    try:
        cid = int(payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "hata": "Geçersiz konuşma ID."}), 400

    from trendyol_qna.instagram_dm import answer_conversation
    sonuc = answer_conversation(cid, (payload.get("text") or "").strip(),
                                username=session.get("username"))
    return jsonify(sonuc), (200 if sonuc["ok"] else 422)


@qna_bp.route("/api/instagram/urun-bagla", methods=["POST"])
def instagram_urun_bagla():
    """DM konuşmasına site ürünü bağlar/kaldırır; taslağı ürün bilgisiyle yeniden üretir."""
    payload = request.get_json(silent=True) or {}
    try:
        conv = db.session.get(InstagramConversation, int(payload.get("id")))
    except (TypeError, ValueError):
        conv = None
    if not conv:
        return jsonify({"ok": False, "hata": "Konuşma bulunamadı."}), 404

    from trendyol_qna import instagram_urun
    anahtar = instagram_urun.konusma_anahtari(conv.id)
    if payload.get("kaldir"):
        instagram_urun.bagi_kaldir(anahtar)
        sonuc = {"ok": True, "hata": None}
    else:
        sonuc = instagram_urun.bagla(anahtar, str(payload.get("product_id") or ""),
                                     renk=str(payload.get("renk") or ""),
                                     username=session.get("username"), confirmed=True)
    if sonuc["ok"] and conv.status == "new":
        # Eski taslak başka ürünle/ürünsüz yazıldı; üretimi sürmüyorsa yenile
        if conv.ai_draft_status != "pending":
            conv.ai_draft, conv.ai_draft_status = None, "none"
            db.session.commit()
        from trendyol_qna.qna_ai import generate_instagram_drafts_async
        generate_instagram_drafts_async([conv.id])
    return jsonify(sonuc), (200 if sonuc["ok"] else 422)


@qna_bp.route("/api/instagram/taslak/<int:qid>", methods=["POST"])
def instagram_taslak(qid: int):
    """Instagram konuşması için AI taslağını (yeniden) üretmeyi tetikler (arka plan)."""
    row = db.session.get(InstagramConversation, qid)
    if not row:
        return jsonify({"ok": False, "hata": "Konuşma bulunamadı."}), 404
    payload = request.get_json(silent=True) or {}
    talimat = (payload.get("talimat") or "").strip()[:500] or None
    mevcut_metin = (payload.get("metin") or "").strip()[:2000] or None
    from trendyol_qna.qna_ai import generate_instagram_drafts_async
    generate_instagram_drafts_async([qid], talimat=talimat, mevcut_metin=mevcut_metin)
    return jsonify({"ok": True, "durum": "pending"})


@qna_bp.route("/api/instagram/taslak-durum/<int:qid>", methods=["GET"])
def instagram_taslak_durum(qid: int):
    row = db.session.get(InstagramConversation, qid)
    if not row:
        return jsonify({"ok": False, "hata": "Konuşma bulunamadı."}), 404
    return jsonify({
        "ok": True,
        "durum": row.ai_draft_status or "none",
        "taslak": row.ai_draft if row.ai_draft_status == "ready" else None,
    })


@qna_bp.route("/api/instagram-yorum/cevapla", methods=["POST"])
def instagram_yorum_cevapla():
    """Yorumu iki mesajla cevaplar: özelden asıl cevap + yorumun altına not."""
    payload = request.get_json(silent=True) or {}
    try:
        yid = int(payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "hata": "Geçersiz yorum ID."}), 400

    from trendyol_qna.instagram_dm import answer_comment
    sonuc = answer_comment(yid, (payload.get("text") or "").strip(),
                           public_note=(payload.get("not") or "").strip(),
                           username=session.get("username"))
    return jsonify(sonuc), (200 if sonuc["ok"] else 422)


@qna_bp.route("/api/instagram-yorum/yoksay", methods=["POST"])
def instagram_yorum_yoksay():
    """Cevap gerektirmeyen yorumu listeden düşürür."""
    payload = request.get_json(silent=True) or {}
    try:
        yid = int(payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "hata": "Geçersiz yorum ID."}), 400

    from trendyol_qna.instagram_dm import ignore_comment
    sonuc = ignore_comment(yid, username=session.get("username"))
    return jsonify(sonuc), (200 if sonuc["ok"] else 404)


@qna_bp.route("/api/instagram-yorum/urun-ara", methods=["GET"])
def instagram_yorum_urun_ara():
    """Gönderiye bağlanacak site ürününü ara (başlık/model kodu)."""
    from trendyol_qna.instagram_urun import urun_ara
    try:
        return jsonify({"ok": True, "urunler": urun_ara(request.args.get("q") or "")})
    except Exception:
        logger.exception("[QNA] ürün araması başarısız")
        return jsonify({"ok": False, "hata": "Ürün araması yapılamadı."}), 502


@qna_bp.route("/api/instagram-yorum/urun-bagla", methods=["POST"])
def instagram_yorum_urun_bagla():
    """Yorumun gönderisini site ürününe bağlar/onaylar; bekleyen yorumlara taslak üretir."""
    payload = request.get_json(silent=True) or {}
    try:
        row = db.session.get(InstagramComment, int(payload.get("id")))
    except (TypeError, ValueError):
        row = None
    if not row:
        return jsonify({"ok": False, "hata": "Yorum bulunamadı."}), 404

    from trendyol_qna import instagram_urun
    if payload.get("kaldir"):
        instagram_urun.bagi_kaldir(row.media_id)
        # Kaldırılan ürünün fiyatıyla yazılmış hazır taslaklar ekranda kalmasın
        (db.session.query(InstagramComment)
         .filter(InstagramComment.media_id == row.media_id, InstagramComment.status == "new",
                 InstagramComment.ai_draft_status == "ready")
         .update({"ai_draft": None, "ai_draft_status": "none"}, synchronize_session=False))
        db.session.commit()
        return jsonify({"ok": True, "hata": None})
    sonuc = instagram_urun.bagla(row.media_id, str(payload.get("product_id") or ""),
                                 renk=str(payload.get("renk") or ""),
                                 username=session.get("username"), confirmed=True)
    if sonuc["ok"]:
        instagram_urun.taslaklari_uret_async(row.media_id, yenile=True)
    return jsonify(sonuc), (200 if sonuc["ok"] else 422)


@qna_bp.route("/api/instagram-yorum/taslak/<int:qid>", methods=["POST"])
def instagram_yorum_taslak(qid: int):
    """Instagram yorumu için AI taslağını (yeniden) üretmeyi tetikler (arka plan)."""
    row = db.session.get(InstagramComment, qid)
    if not row:
        return jsonify({"ok": False, "hata": "Yorum bulunamadı."}), 404
    payload = request.get_json(silent=True) or {}
    talimat = (payload.get("talimat") or "").strip()[:500] or None
    mevcut_metin = (payload.get("metin") or "").strip()[:2000] or None
    from trendyol_qna.qna_ai import generate_instagram_comment_drafts_async
    generate_instagram_comment_drafts_async([qid], talimat=talimat, mevcut_metin=mevcut_metin)
    return jsonify({"ok": True, "durum": "pending"})


@qna_bp.route("/api/instagram-yorum/taslak-durum/<int:qid>", methods=["GET"])
def instagram_yorum_taslak_durum(qid: int):
    row = db.session.get(InstagramComment, qid)
    if not row:
        return jsonify({"ok": False, "hata": "Yorum bulunamadı."}), 404
    return jsonify({
        "ok": True,
        "durum": row.ai_draft_status or "none",
        "taslak": row.ai_draft if row.ai_draft_status == "ready" else None,
    })


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
    payload = request.get_json(silent=True) or {}
    talimat = (payload.get("talimat") or "").strip()[:500] or None
    mevcut_metin = (payload.get("metin") or "").strip()[:2000] or None
    from trendyol_qna.qna_ai import generate_drafts_async
    generate_drafts_async([qid], talimat=talimat, mevcut_metin=mevcut_metin)
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


@qna_bp.route("/api/genel-talimat", methods=["GET", "POST"])
def genel_talimat_api():
    """
    AI taslakları için kalıcı genel talimatı oku/değiştir. Değiştirme motor
    seçimiyle aynı gerekçeyle YALNIZCA yöneticiye açık; CSRF kalkanı
    before_request'te (fetch başlığı) zaten uygulanıyor.
    """
    from ai_asistan.blueprint import _yonetici_mi
    from trendyol_qna.qna_ayar import TALIMAT_MAX, genel_talimat, genel_talimat_ayarla

    if request.method == "GET":
        return jsonify({"ok": True, "talimat": genel_talimat(),
                        "azami": TALIMAT_MAX, "duzenleyebilir": _yonetici_mi()})

    if not _yonetici_mi():
        return jsonify({"ok": False, "hata": "Bu ayarı yalnızca yönetici değiştirebilir."}), 403

    payload = request.get_json(silent=True) or {}
    try:
        genel_talimat_ayarla(payload.get("talimat") or "")
    except Exception:
        db.session.rollback()
        logger.exception("[QNA-AYAR] genel talimat yazılamadı")
        return jsonify({"ok": False, "hata": "Talimat kaydedilemedi."}), 500
    return jsonify({"ok": True, "talimat": genel_talimat()})


@qna_bp.route("/api/senkron", methods=["POST"])
def senkron():
    """Elle tam senkron (son 14 gün, tüm statüler)."""
    from trendyol_qna.qna_service import sync_questions
    try:
        yeni = sync_questions(days=14)
        # Instagram ayarlıysa konuşmaları da çek; hatası Trendyol senkronunu bozmaz
        try:
            from trendyol_qna.instagram_dm import sync_conversations
            sync_conversations()
            if yorum_cekme_acik():
                from trendyol_qna.instagram_dm import sync_comments
                sync_comments()
        except Exception:
            db.session.rollback()
            logger.exception("[QNA] Instagram senkronu başarısız")
        return jsonify({"ok": True, "yeni": len(yeni)})
    except Exception as e:
        logger.exception("[QNA] elle senkron hatası")
        return jsonify({"ok": False, "hata": str(e)}), 500
