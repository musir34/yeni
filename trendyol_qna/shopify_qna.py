"""
Shopify (gullushoes.com) "Hızlı Soru Sor" widget'ı entegrasyonu.

- Public endpoint: POST /api/shopify-questions — sitedeki widget buraya gönderir.
  `/api/` öneki app.py'deki check_authentication'dan bilinçli olarak muaf;
  koruma CORS + honeypot + IP rate limit + doğrulama ile sağlanır.
- Panel tarafı (listeleme + cevaplama) qna_routes.py'den bu modülü çağırır;
  sorular /soru-cevap ekranında Trendyol sorularıyla birlikte gösterilir.
"""
import logging
import re
import threading
import time
from datetime import datetime, timezone
from urllib.parse import quote

from flask import Blueprint, jsonify, request
from markupsafe import escape

from models import db, ShopifyQuestion

logger = logging.getLogger(__name__)

shopify_q_bp = Blueprint("shopify_questions", __name__)

ALLOWED_ORIGINS = ("https://www.gullushoes.com", "https://gullushoes.com")
SITE_URL = "https://www.gullushoes.com"
QUESTION_MIN, QUESTION_MAX = 10, 2000
RATE_LIMIT_COUNT = 5          # aynı IP'den
RATE_LIMIT_WINDOW = 600       # 10 dakika (sn)

# Basit bellek-içi rate limit: {ip: [timestamp, ...]} — süreç bazlı yeterli
_rate_lock = threading.Lock()
_rate_hits: dict[str, list[float]] = {}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _client_ip() -> str:
    # Nginx → gunicorn tek proxy katmanı: XFF'in SON değeri kendi proxy'mizin
    # eklediği gerçek istemci IP'sidir; ilk değerler istemci tarafından spoof
    # edilebilir (rate limit bypass'ı). Proxy yoksa remote_addr kullanılır.
    xff = (request.headers.get("X-Forwarded-For") or "").split(",")[-1].strip()
    return (xff or request.remote_addr or "")[:64]


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        hits = [t for t in _rate_hits.get(ip, []) if now - t < RATE_LIMIT_WINDOW]
        if len(hits) >= RATE_LIMIT_COUNT:
            _rate_hits[ip] = hits
            return True
        hits.append(now)
        _rate_hits[ip] = hits
        # Sözlük şişmesin: penceresi boşalan IP'leri at
        if len(_rate_hits) > 1000:
            for k in [k for k, v in _rate_hits.items() if all(now - t >= RATE_LIMIT_WINDOW for t in v)]:
                del _rate_hits[k]
    return False


def normalize_phone(raw: str) -> str | None:
    """05xxxxxxxxx / 5xxxxxxxxx / 905xxxxxxxxx → 05xxxxxxxxx; uymazsa None."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("905"):
        return "0" + digits[2:]
    if len(digits) == 11 and digits.startswith("05"):
        return digits
    if len(digits) == 10 and digits.startswith("5"):
        return "0" + digits
    return None


def _safe_page_url(raw) -> str:
    """Yalnızca http(s) linki kabul et — anonim kaynaklı URL panelde ve mailde
    href olarak basıldığı için javascript: benzeri şemalar burada elenir."""
    url = (raw or "").strip()[:500]
    return url if url.lower().startswith(("https://", "http://")) else ""


def _safe_product_image(raw) -> str:
    """Ürün görseli yalnızca Shopify CDN'inden kabul edilir (talimat gereği)."""
    url = (raw or "").strip()[:500]
    return url if url.startswith("https://cdn.shopify.com/") else ""


def _cors_headers(resp):
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@shopify_q_bp.route("/api/shopify-questions", methods=["POST", "OPTIONS"])
def shopify_question_intake():
    if request.method == "OPTIONS":
        return _cors_headers(jsonify({"ok": True}))

    payload = request.get_json(silent=True) or {}

    # Honeypot: doluysa bot — kaydetme ama hata da gösterme
    if (payload.get("website") or "").strip():
        return _cors_headers(jsonify({"ok": True}))

    ip = _client_ip()
    if _rate_limited(ip):
        return _cors_headers(jsonify({"ok": False, "error": "Çok fazla istek, lütfen sonra deneyin."})), 429

    contact_type = (payload.get("contact_type") or "").strip()
    if contact_type not in ("email", "phone"):
        return _cors_headers(jsonify({"ok": False, "error": "Geçersiz iletişim tipi."})), 400

    email, phone = "", ""
    if contact_type == "email":
        email = (payload.get("email") or "").strip()[:255]
        if not _EMAIL_RE.match(email):
            return _cors_headers(jsonify({"ok": False, "error": "Geçersiz e-posta adresi."})), 400
    else:
        phone = normalize_phone(payload.get("phone") or "")
        if not phone:
            return _cors_headers(jsonify({"ok": False, "error": "Geçersiz telefon numarası."})), 400

    question = (payload.get("question") or "").strip()
    if not (QUESTION_MIN <= len(question) <= QUESTION_MAX):
        return _cors_headers(jsonify({"ok": False, "error": f"Soru {QUESTION_MIN}–{QUESTION_MAX} karakter olmalı."})), 400

    row = ShopifyQuestion(
        contact_type=contact_type,
        email=email,
        phone=phone,
        name=(payload.get("name") or "").strip()[:120],
        question=question,
        page_url=_safe_page_url(payload.get("page_url")),
        product_title=(payload.get("product_title") or "").strip()[:300],
        product_sku=(payload.get("product_sku") or "").strip()[:120],
        product_image=_safe_product_image(payload.get("product_image")),
        ip=ip,
        created_at=datetime.now(timezone.utc),
    )
    try:
        db.session.add(row)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("[SHOPIFY-QNA] soru kaydedilemedi")
        return _cors_headers(jsonify({"ok": False, "error": "Kayıt hatası, lütfen sonra deneyin."})), 500

    logger.info("[SHOPIFY-QNA] yeni soru #%s (%s)", row.id, contact_type)
    _notify_new_question(row)
    try:
        from trendyol_qna.qna_ai import generate_shopify_drafts_async
        generate_shopify_drafts_async([row.id])
    except Exception:
        logger.exception("[SHOPIFY-QNA] AI taslak tetiklenemedi (soru %s)", row.id)
    return _cors_headers(jsonify({"ok": True}))


def _notify_new_question(row: ShopifyQuestion) -> None:
    """Trendyol tarafındaki 'yeni_soru' olayıyla aynı abonelere mail bildirimi."""
    try:
        from mail_service import notify
        notify(
            "yeni_soru",
            "Site: 1 yeni müşteri sorusu",
            "gullushoes.com üzerinden yeni bir müşteri sorusu geldi:\n\n"
            f"- {row.product_title or 'Genel'}: {(row.question or '')[:200]}"
            "\n\nPanel: /soru-cevap",
        )
    except Exception:
        logger.exception("[SHOPIFY-QNA] yeni soru bildirimi gönderilemedi")


# ── Panel tarafı: cevaplama ──────────────────────────────────────────────────

def _soru_link(page_url: str) -> str:
    """Maildeki 'Başka Sorunuz mu Var?' linki — ?soru=1 sitede modalı otomatik açar."""
    base = (page_url or SITE_URL).strip() or SITE_URL
    return base + ("&soru=1" if "?" in base else "?soru=1")


def _answer_mail_html(row: ShopifyQuestion, answer: str) -> str:
    isim = f" {escape(row.name)}" if row.name else ""
    urun = ""
    if row.product_title:
        model = f" (Model: {escape(row.product_sku)})" if getattr(row, "product_sku", "") else ""
        urun = (f'<p>İlgili ürün: <a href="{escape(row.page_url or SITE_URL)}">'
                f'{escape(row.product_title)}</a>{model}</p>')
    return f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#1a1a1a">
  <h2 style="color:#1a1a1a">Güllü Shoes</h2>
  <p>Merhaba{isim},</p>
  <p>Sorunuza cevabımız aşağıdadır:</p>
  <div style="background:#f7f7f7;border-radius:10px;padding:14px;margin:14px 0">
    <p style="color:#888;font-size:13px;margin:0 0 6px">Sorunuz:</p>
    <p style="margin:0">{escape(row.question)}</p>
  </div>
  <div style="background:#fdf8f1;border-left:3px solid #d99d4b;border-radius:6px;padding:14px;margin:14px 0">
    <p style="color:#888;font-size:13px;margin:0 0 6px">Cevabımız:</p>
    <p style="margin:0">{escape(answer)}</p>
  </div>
  {urun}
  <a href="{escape(_soru_link(row.page_url))}"
     style="display:inline-block;background:#1a1a1a;color:#fff;text-decoration:none;
            padding:12px 22px;border-radius:8px;margin:10px 0">
    Başka Sorunuz mu Var?
  </a>
  <p style="color:#999;font-size:12px">Bu mail, gullushoes.com üzerinden sorduğunuz soruya istinaden gönderilmiştir.</p>
</div>"""


def whatsapp_link(row: ShopifyQuestion) -> str:
    """Telefonlu sorular için hazır wa.me linki (panel detayında gösterilir)."""
    isim = f" {row.name}" if row.name else ""
    mesaj = (f"Merhaba{isim}, Güllü Shoes'tan yazıyoruz. gullushoes.com'da sormuş "
             f"olduğunuz soruya istinaden dönüş yapıyoruz:\n\n\"{row.question}\"\n\n")
    return f"https://wa.me/90{row.phone[-10:]}?text={quote(mesaj)}"


def answer_shopify_question(question_id: int, text: str, username: str | None = None) -> dict:
    """
    Shopify sorusunu cevapla: email ise müşteriye mail gönderir; telefon ise
    yalnızca yanıtlandı işaretler (cevap WhatsApp'tan elle yazılır).
    Dönen: {'ok': bool, 'hata': str|None}
    """
    text = (text or "").strip()
    row = db.session.get(ShopifyQuestion, question_id)
    if not row:
        return {"ok": False, "hata": "Soru bulunamadı."}
    if row.status != "new":
        return {"ok": False, "hata": "Bu soru zaten yanıtlanmış."}

    if row.contact_type == "email":
        if len(text) < 2:
            return {"ok": False, "hata": "Cevap boş olamaz."}
        from mail_service import send_email
        gonderildi = send_email(
            "Sorunuza cevap geldi — Güllü Shoes",
            _answer_mail_html(row, text),
            [row.email],
        )
        if not gonderildi:
            return {"ok": False, "hata": "Mail gönderilemedi, SMTP ayarlarını kontrol edin."}

    row.status = "answered"
    row.answer = text
    row.answered_by = username
    row.answered_at = datetime.now(timezone.utc)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("[SHOPIFY-QNA] cevap kaydedilemedi (soru %s)", question_id)
        return {"ok": False, "hata": "Cevap kaydedilemedi."}
    logger.info("[SHOPIFY-QNA] soru %s cevaplandı (%s)", question_id, username)
    return {"ok": True, "hata": None}


def new_count() -> int:
    """Cevap bekleyen Shopify sorusu sayısı (rozet için)."""
    try:
        return db.session.query(ShopifyQuestion).filter_by(status="new").count()
    except Exception:
        db.session.rollback()
        logger.exception("[SHOPIFY-QNA] bekleyen sayısı okunamadı")
        return 0


def ensure_table_exists() -> None:
    """Tablo yoksa oluştur (prod'da alembic yok — TrendyolQuestion deseni).

    Tablo önceki deploy'da kolonsuz kurulmuş olabilir; AI taslak kolonları
    additive ALTER ile tamamlanır (her biri ayrı denenir — SQLite'ta
    IF NOT EXISTS desteklenmez, mevcut kolon hatası sessizce yutulur).
    """
    try:
        ShopifyQuestion.__table__.create(bind=db.engine, checkfirst=True)
    except Exception:
        logger.exception("[SHOPIFY-QNA] tablo oluşturma hatası")
    for ddl in (
        "ALTER TABLE shopify_questions ADD COLUMN ai_draft TEXT",
        "ALTER TABLE shopify_questions ADD COLUMN ai_draft_status VARCHAR(20) DEFAULT 'none'",
        "ALTER TABLE shopify_questions ADD COLUMN ai_draft_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE shopify_questions ADD COLUMN product_sku VARCHAR(120) DEFAULT ''",
        "ALTER TABLE shopify_questions ADD COLUMN product_image VARCHAR(500) DEFAULT ''",
    ):
        try:
            with db.engine.begin() as conn:
                conn.execute(db.text(ddl))
        except Exception:
            pass  # kolon zaten var
