"""
Trendyol Müşteri Soruları (Q&A) servisi.

API dokümanı: https://developers.trendyol.com/docs/müşteri-sorularını-çekme
- Sorular:  GET  /integration/qna/sellers/{sellerId}/questions/filter
- Cevap:    POST /integration/qna/sellers/{sellerId}/questions/{id}/answers
Rate limit: soru çekme servisi 1000 istek/dk — 10 sn'lik polling (6/dk) çok altında.
"""
import base64
import json
import logging
import threading
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy.exc import IntegrityError

from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID
from models import db, TrendyolQuestion, Product, CentralStock

logger = logging.getLogger(__name__)

# Aynı süreçteki job'lar (10 sn poll ↔ 3 saatlik reconcile) üst üste binmesin.
# Süreçler arası (scheduler ↔ web worker'daki elle senkron) yarış ise
# _upsert_batch'in IntegrityError-retry'ı ile toleranslıdır.
_sync_lock = threading.Lock()

BASE_URL = "https://apigw.trendyol.com/integration/qna/sellers"
TIMEOUT = 15                 # HTTP istek zaman aşımı (sn)
PAGE_SIZE = 50               # Trendyol max 50
ANSWER_MIN, ANSWER_MAX = 10, 2000
SIGNATURE = "Güllü Shoes🌹"  # her cevabın sonunda zorunlu imza

# Cevaplanabilir tek statü (Trendyol kuralı)
ANSWERABLE_STATUS = "WAITING_FOR_ANSWER"
ALL_STATUSES = ("WAITING_FOR_ANSWER", "ANSWERED", "REJECTED", "REPORTED", "UNANSWERED")


def _headers() -> dict:
    auth = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode()).decode()
    return {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
        "User-Agent": f"{SUPPLIER_ID} - SelfIntegration",
    }


def _ms_to_dt(ms) -> datetime | None:
    """Trendyol epoch-millis → aware UTC datetime."""
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _fetch_page(params: dict) -> dict | None:
    """Tek sayfa soru çek; hata durumunda None (job'lar sessizce loglayıp geçer)."""
    url = f"{BASE_URL}/{SUPPLIER_ID}/questions/filter"
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=TIMEOUT)
    except requests.RequestException as e:
        logger.warning("[QNA] istek hatası: %s", e)
        return None
    if resp.status_code == 429:
        logger.warning("[QNA] rate limit (429) — bu tur atlanıyor")
        return None
    if not resp.ok:
        logger.warning("[QNA] API %s: %s", resp.status_code, resp.text[:300])
        return None
    try:
        return resp.json()
    except ValueError:
        logger.warning("[QNA] JSON parse hatası: %s", resp.text[:200])
        return None


def _upsert_question(item: dict) -> tuple[TrendyolQuestion, bool]:
    """API item'ını tabloya işle. (satır, yeni_mi) döner. Commit çağıranın işi."""
    qid = item.get("id")
    row = db.session.get(TrendyolQuestion, qid)
    is_new = row is None
    if is_new:
        row = TrendyolQuestion(id=qid, text=item.get("text") or "")
        db.session.add(row)

    incoming_status = item.get("status")
    # Panelden az önce cevaplanan soru, Trendyol read-API'sinin gecikmesiyle
    # hâlâ WAITING görünebilir; yerel ANSWERED'ı ezmesine izin verme.
    if (
        incoming_status == ANSWERABLE_STATUS
        and row.answered_via_panel_at
        and row.status == "ANSWERED"
    ):
        panel_ts = row.answered_via_panel_at
        if panel_ts.tzinfo is None:
            panel_ts = panel_ts.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - panel_ts < timedelta(minutes=15):
            incoming_status = row.status

    row.text = item.get("text") or row.text
    row.user_name = item.get("userName")
    row.show_user_name = item.get("showUserName")
    row.customer_id = item.get("customerId")
    row.product_name = item.get("productName")
    row.product_main_id = item.get("productMainId")
    row.image_url = item.get("imageUrl")
    row.web_url = item.get("webUrl")
    row.status = incoming_status
    row.public = item.get("public")
    row.reason = item.get("reason")
    row.report_reason = item.get("reportReason")
    row.creation_date = _ms_to_dt(item.get("creationDate")) or row.creation_date

    answer = item.get("answer") or {}
    if answer.get("text"):
        row.answer_id = answer.get("id")
        row.answer_text = answer.get("text")
        row.answer_date = _ms_to_dt(answer.get("creationDate"))
    rejected = item.get("rejectedAnswer") or {}
    if rejected.get("text"):
        row.rejected_answer_text = rejected.get("text")
        row.rejected_date = _ms_to_dt(item.get("rejectedDate") or rejected.get("creationDate"))

    row.raw_json = json.dumps(item, ensure_ascii=False)
    row.last_synced_at = datetime.now(timezone.utc)
    return row, is_new


def _upsert_batch(items: list[dict]) -> list[int]:
    """
    Bir sayfalık item'ı işleyip COMMIT eder; yeni soru ID'lerini döner.
    Başka bir süreç aynı anda aynı soruyu eklediyse (PK çakışması) rollback
    yapıp batch'i bir kez daha dener — ikinci turda satırlar artık DB'de
    olduğundan upsert güncellemeye dönüşür ve batch kaybolmaz.
    """
    for attempt in (1, 2):
        new_ids: list[int] = []
        try:
            for item in items:
                _, is_new = _upsert_question(item)
                if is_new:
                    new_ids.append(item.get("id"))
            db.session.commit()
            return new_ids
        except IntegrityError:
            db.session.rollback()
            if attempt == 2:
                logger.exception("[QNA] upsert batch iki denemede de çakıştı")
                return []
        except Exception:
            db.session.rollback()
            logger.exception("[QNA] upsert batch hatası")
            return []
    return []


def sync_questions(days: int = 3, statuses=ALL_STATUSES) -> list[int]:
    """
    Verilen pencerede tüm statüleri senkronla (upsert). Yeni soru ID'lerini döner.
    Trendyol tarih penceresi max 2 hafta — days 14 ile sınırlanır.
    """
    days = min(days, 14)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    new_ids: list[int] = []

    with _sync_lock:
        for status in statuses:
            page = 0
            while True:
                data = _fetch_page({
                    "supplierId": SUPPLIER_ID,
                    "status": status,
                    "startDate": int(start.timestamp() * 1000),
                    "endDate": int(end.timestamp() * 1000),
                    "page": page,
                    "size": PAGE_SIZE,
                    "orderByField": "LastModifiedDate",
                    "orderByDirection": "DESC",
                })
                if not data:
                    break
                # Sayfa başına commit: uzun süren reconcile'da tek dev
                # transaction tutulmaz, bir sayfanın hatası diğerlerini yakmaz.
                new_ids.extend(_upsert_batch(data.get("content") or []))
                page += 1
                if page >= (data.get("totalPages") or 1):
                    break

    if new_ids:
        logger.info("[QNA] senkron: %d yeni soru", len(new_ids))
    return new_ids


def quick_poll() -> list[int]:
    """
    10 sn'lik hafif tur: sadece cevap bekleyen soruların son sayfasına bakar.
    Yeni soru varsa kaydeder, AI taslağı tetikler ve mail bildirimi atar.
    """
    data = _fetch_page({
        "supplierId": SUPPLIER_ID,
        "status": ANSWERABLE_STATUS,
        "page": 0,
        "size": 20,
        "orderByField": "CreatedDate",
        "orderByDirection": "DESC",
    })
    if not data:
        return []

    with _sync_lock:
        new_ids = _upsert_batch(data.get("content") or [])

    if new_ids:
        logger.info("[QNA] %d yeni soru düştü: %s", len(new_ids), new_ids)
        rows = db.session.query(TrendyolQuestion).filter(TrendyolQuestion.id.in_(new_ids)).all()
        _notify_new_questions(rows)
        from trendyol_qna.qna_ai import generate_drafts_async
        generate_drafts_async(new_ids)
    return new_ids


def _notify_new_questions(rows) -> None:
    """Yeni sorular için 'yeni_soru' olayına abone kullanıcılara mail at."""
    try:
        from mail_service import notify
        lines = [
            f"- {r.product_name or 'Ürün'}: {(r.text or '')[:200]}"
            for r in rows
        ]
        notify(
            "yeni_soru",
            f"Trendyol: {len(rows)} yeni müşteri sorusu",
            "Cevap bekleyen yeni müşteri soruları:\n\n" + "\n".join(lines)
            + "\n\nPanel: /soru-cevap",
        )
    except Exception:
        logger.exception("[QNA] yeni soru bildirimi gönderilemedi")


def answer_question(question_id: int, text: str, username: str | None = None) -> dict:
    """
    Cevabı Trendyol'a gönder ve yerel kaydı güncelle.
    Dönen: {'ok': bool, 'hata': str|None}
    """
    text = (text or "").strip()
    if len(text) < ANSWER_MIN:
        return {"ok": False, "hata": f"Cevap en az {ANSWER_MIN} karakter olmalı."}
    # İmza garantisi: cevap 'Güllü Shoes🌹' ile bitmiyorsa otomatik ekle
    if not text.endswith(SIGNATURE):
        text = f"{text}\n\n{SIGNATURE}"
    if len(text) > ANSWER_MAX:
        return {"ok": False, "hata": f"Cevap imzayla birlikte en fazla {ANSWER_MAX} karakter olabilir, lütfen kısaltın."}

    row = db.session.get(TrendyolQuestion, question_id)
    if not row:
        return {"ok": False, "hata": "Soru bulunamadı."}
    if row.status != ANSWERABLE_STATUS:
        return {"ok": False, "hata": f"Bu soru cevaplanamaz (statü: {row.status})."}

    url = f"{BASE_URL}/{SUPPLIER_ID}/questions/{question_id}/answers"
    try:
        resp = requests.post(url, headers=_headers(), json={"text": text}, timeout=TIMEOUT)
    except requests.RequestException as e:
        return {"ok": False, "hata": f"Trendyol'a ulaşılamadı: {e}"}

    if not resp.ok:
        detail = resp.text[:300]
        logger.warning("[QNA] cevap reddedildi (%s): %s", resp.status_code, detail)
        return {"ok": False, "hata": f"Trendyol cevabı kabul etmedi ({resp.status_code}): {detail}"}

    now = datetime.now(timezone.utc)
    onceki_taslak = row.ai_draft
    row.status = "ANSWERED"
    row.answer_text = text
    row.answer_date = now
    row.answered_by = username
    row.answered_via_panel_at = now
    db.session.commit()
    logger.info("[QNA] soru %s cevaplandı (%s)", question_id, username)

    # İnsan onaylı cevabı bilgi bankasına not düş (AI sonraki taslaklarda öğrenir)
    from trendyol_qna.qna_notes import log_approved_answer, log_correction
    renk = question_renk(row.product_main_id, row.product_name)
    log_approved_answer(row.product_name, row.product_main_id, row.text, text, username,
                        renk=renk)
    # AI taslağı elle düzeltilerek gönderildiyse farkı ders olarak da not düş
    def _norm(s):
        return " ".join((s or "").replace(SIGNATURE, "").split())
    if onceki_taslak and _norm(onceki_taslak) != _norm(text):
        log_correction(row.product_name, row.product_main_id, row.text,
                       None, onceki_taslak, text, renk=renk)
    return {"ok": True, "hata": None}


def waiting_count() -> int:
    """Cevap bekleyen soru sayısı (anasayfa rozeti)."""
    try:
        return db.session.query(TrendyolQuestion).filter_by(status=ANSWERABLE_STATUS).count()
    except Exception:
        logger.exception("[QNA] bekleyen sayısı okunamadı")
        return 0


def _tr_lower(s: str) -> str:
    """Türkçe-uyumlu küçük harf (İ→i, I→ı)."""
    return (s or "").replace("İ", "i").replace("I", "ı").lower()


def question_renk(product_main_id: str | None, product_name: str | None) -> str | None:
    """
    Sorunun hangi RENK varyantına ait olduğunu tespit et: modelin (product_main_id)
    paneldeki renkleri içinden, soru ürün adında geçen en uzun eşleşme.
    Bulunamazsa None (model tek renkliyse o renk döner).
    """
    if not product_main_id:
        return None
    try:
        renkler = [
            r[0] for r in (
                db.session.query(Product.color)
                .filter(Product.product_main_id == product_main_id)
                .filter(Product.color.isnot(None))
                .distinct()
                .all()
            ) if r[0]
        ]
    except Exception:
        logger.exception("[QNA] renk tespiti sorgusu hata")
        return None
    if not renkler:
        return None
    if len(renkler) == 1:
        return renkler[0]
    # Kelime bazlı eşleşme: rengin TÜM kelimeleri ürün adında geçmeli
    # (başlık 'Bej Parlak Kırışık' → renk 'Bej Kırışık' yakalanır).
    ad_kelimeler = set(_tr_lower(product_name or "").split())
    eslesen = [r for r in renkler if set(_tr_lower(r).split()) <= ad_kelimeler]
    if eslesen:
        # En çok kelimesi eşleşen (en spesifik) renk: 'Rugan' değil 'Siyah Rugan'
        return max(eslesen, key=lambda r: (len(r.split()), len(r)))
    return None


def stock_context(product_main_id: str | None) -> str:
    """
    Model koduna ait varyantların CANLI stok özetini üret (AI promptu için).
    Örn: '36: 3 adet, 37: 0 (stok yok), 38: 5 adet'
    """
    if not product_main_id:
        return "Ürün model kodu bilinmiyor; stok bilgisi verilemedi."
    try:
        rows = (
            db.session.query(Product.size, Product.barcode, CentralStock.qty)
            .outerjoin(CentralStock, CentralStock.barcode == Product.barcode)
            .filter(Product.product_main_id == product_main_id)
            .filter((Product.archived.is_(False)) | (Product.archived.is_(None)))
            .all()
        )
    except Exception:
        logger.exception("[QNA] stok bağlamı sorgusu hata")
        return "Stok bilgisi alınamadı."
    if not rows:
        return f"'{product_main_id}' model koduna ait ürün panelde bulunamadı."

    def _size_key(s):
        try:
            return (0, float(s))
        except (TypeError, ValueError):
            return (1, 0)

    parts = []
    for size, _barcode, qty in sorted(rows, key=lambda r: _size_key(r[0])):
        q = int(qty or 0)
        parts.append(f"{size or '?'}: {q} adet" if q > 0 else f"{size or '?'}: stok yok")
    return f"Model {product_main_id} canlı stok — " + ", ".join(parts)


def ensure_table_exists() -> None:
    """Tablo yoksa oluştur (migration çalışmadıysa yedek)."""
    try:
        TrendyolQuestion.__table__.create(bind=db.engine, checkfirst=True)
    except Exception:
        logger.exception("[QNA] tablo oluşturma hatası")
