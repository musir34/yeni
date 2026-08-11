import base64
import logging
import os
import requests
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (
    Blueprint, jsonify, render_template, request,
    redirect, url_for, flash, current_app
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from apscheduler.schedulers.background import BackgroundScheduler

from models import db, ReturnOrder, ReturnProduct
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID
try:
    from user_logs import log_user_action
except ImportError:
    def log_user_action(*a, **kw): pass

# ------------------------------------------------------------------ #
# Genel ayarlar
# ------------------------------------------------------------------ #
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _bounded_env_int(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


CLAIMS_PAGE_SIZE = 200
CLAIMS_RESULT_CAP = 500
CLAIMS_MIN_SPLIT = timedelta(minutes=5)
LIVE_RETURN_CACHE_SECONDS = 55
LIVE_RETURN_LOOKBACK_DAYS = _bounded_env_int(
    "TRENDYOL_RETURN_LOOKBACK_DAYS", 30, 7, 180
)

_live_return_cache = {"payload": None, "stored_at": 0.0}
_live_return_lock = threading.Lock()

iade_islemleri = Blueprint("iade_islemleri", __name__)

# ------------------------------------------------------------------ #
# Yardımcılar
# ------------------------------------------------------------------ #
def with_db_session(func):
    """Her çağrıda aynı `db.session`’ı verip otomatik kapatır."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        session = db.session  # Flask-SQLAlchemy global session
        try:
            return func(session, *args, **kwargs)
        finally:
            session.close()
    return wrapper


def get_requests_session():
    """Otomatik retry’lı requests oturumu."""
    sess = requests.Session()
    retry = Retry(
        total=5, backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PUT"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    return sess


def safe_strip(val):
    return val.strip() if isinstance(val, str) else val


def is_valid_uuid(uuid_str):
    import uuid
    try:
        uuid.UUID(str(uuid_str))
        return True
    except ValueError:
        return False


# ------------------------------------------------------------------ #
# API’den veri çekme
# ------------------------------------------------------------------ #
def fetch_data_from_api(start_date: datetime, end_date: datetime):
    logger.info("API’den iade verileri çekiliyor: %s – %s", start_date, end_date)

    if not API_KEY or not API_SECRET or not SUPPLIER_ID:
        logger.error("Trendyol iade API bilgileri eksik; canlı istek atlanıyor.")
        return None

    url = f"https://apigw.trendyol.com/integration/order/sellers/{SUPPLIER_ID}/claims"
    cred = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {cred}",
        "Content-Type": "application/json",
        "User-Agent": f"{SUPPLIER_ID} - SelfIntegration",
    }

    def fetch_page(window_start, window_end, page):
        params = {
            "size": CLAIMS_PAGE_SIZE,
            "page": page,
            "startDate": int(window_start.timestamp() * 1000),
            "endDate": int(window_end.timestamp() * 1000),
            "sortColumn": "CLAIM_DATE",
            "sortDirection": "DESC",
        }
        page_session = get_requests_session()
        try:
            r = page_session.get(
                url,
                headers=headers,
                params=params,
                timeout=(5, 30),
            )
        except requests.RequestException as exc:
            logger.error("Trendyol iade API bağlantı hatası: %s", exc)
            return None
        finally:
            close = getattr(page_session, "close", None)
            if close:
                close()
        if r.status_code != 200:
            logger.error("API hatası [%s]: %s", r.status_code, r.text)
            return None
        try:
            return r.json()
        except ValueError:
            logger.error("Trendyol iade API geçersiz JSON döndürdü.")
            return None

    def fetch_window(window_start, window_end):
        first = fetch_page(window_start, window_end, 0)
        if first is None:
            return None

        total_elements = int(first.get("totalElements") or 0)
        duration = window_end - window_start

        # Claims servisi tek sorguyu 500 kayıtta sessizce kesiyor. Sınıra
        # gelindiyse zaman aralığını böl; birleşimde claim id ile dedupe yapılır.
        if total_elements >= CLAIMS_RESULT_CAP and duration > CLAIMS_MIN_SPLIT:
            midpoint = window_start + (duration / 2)
            left = fetch_window(window_start, midpoint)
            right = fetch_window(midpoint, window_end)
            if left is None or right is None:
                return None
            return left + right

        content = list(first.get("content", []))
        total_pages = int(first.get("totalPages") or (1 if content else 0))
        pages = range(1, total_pages)
        if total_pages > 1:
            page_results = {}
            with ThreadPoolExecutor(max_workers=min(4, total_pages - 1)) as executor:
                futures = {
                    executor.submit(fetch_page, window_start, window_end, page): page
                    for page in pages
                }
                for future in as_completed(futures):
                    page = futures[future]
                    try:
                        data = future.result()
                    except Exception as exc:
                        logger.error("Trendyol iade sayfası %s alınamadı: %s", page, exc)
                        return None
                    if data is None:
                        return None
                    page_results[page] = data.get("content", [])
            for page in sorted(page_results):
                content.extend(page_results[page])
        if total_elements >= CLAIMS_RESULT_CAP:
            logger.warning(
                "Claims API en küçük zaman diliminde de %s kayıt sınırına ulaştı: %s – %s",
                CLAIMS_RESULT_CAP, window_start, window_end,
            )
        return content

    rows = fetch_window(start_date, end_date)
    if rows is None:
        return None

    unique = {}
    for item in rows:
        claim_id = item.get("id") or item.get("claimId")
        if claim_id:
            unique[str(claim_id)] = item
    all_content = sorted(
        unique.values(),
        key=lambda item: item.get("lastModifiedDate") or item.get("claimDate") or 0,
        reverse=True,
    )
    logger.info("API’den toplam %d benzersiz kayıt alındı.", len(all_content))
    return {"content": all_content}


# ------------------------------------------------------------------ #
# Veritabanı işlemleri
# ------------------------------------------------------------------ #
def save_to_database(data: dict, session):
    """ReturnOrder & ReturnProduct toplu kaydetme/upsert."""
    content = data.get("content", [])
    if not content:
        return True

    orders_to_upsert, products_to_upsert = [], []
    processed = set()

    for item in content:
        claim_id = item.get("id")
        if (not claim_id) or (claim_id in processed) or (not is_valid_uuid(claim_id)):
            continue
        processed.add(claim_id)

        claim_items = item.get("items", [])
        if not claim_items:
            continue

        claim_status = safe_strip(
            claim_items[0].get("claimItems", [{}])[0]
            .get("claimItemStatus", {})
            .get("name", "")
        )
        claim_date_ms = item.get("claimDate")
        # DİKKAT: claims API'sinin `claimDate`'i GERÇEK UTC epoch'tur (orders API'sinin
        # `orderDate`'inden farklı — o İstanbul duvar saati kodluyor).
        # Eski kod `fromtimestamp` kullanıyordu; app.py TZ'yi Europe/Istanbul yaptığı için
        # bu +3 kaymış İstanbul saati yazıyordu. Doğrusu doğrudan naive UTC.
        claim_date = datetime.utcfromtimestamp(claim_date_ms / 1000) if claim_date_ms else None

        orders_to_upsert.append(
            {
                "id": claim_id,
                "order_number": safe_strip(item.get("orderNumber")),
                "return_request_number": claim_id,
                "status": claim_status,
                "return_date": claim_date,
                "customer_first_name": safe_strip(item.get("customerFirstName")),
                "customer_last_name": safe_strip(item.get("customerLastName")),
                "cargo_tracking_number": str(item.get("cargoTrackingNumber", "")),
                "cargo_provider_name": safe_strip(item.get("cargoProviderName")),
                "cargo_sender_number": safe_strip(item.get("cargoSenderNumber")),
                "cargo_tracking_link": safe_strip(item.get("cargoTrackingLink")),
            }
        )

        for p in claim_items:
            order_line = p.get("orderLine", {})
            for ci in p.get("claimItems", []):
                products_to_upsert.append(
                    {
                        "return_order_id": claim_id,
                        "barcode": safe_strip(order_line.get("barcode")),
                        "product_name": safe_strip(order_line.get("productName")),
                        "size": safe_strip(order_line.get("productSize")),
                        "color": safe_strip(order_line.get("productColor")),
                        "quantity": 1,
                        "reason": safe_strip(ci.get("customerClaimItemReason", {}).get("name")),
                        "claim_line_item_id": safe_strip(ci.get("id")),
                    }
                )

    try:
        # orders
        for o in orders_to_upsert:
            stmt = (
                pg_insert(ReturnOrder)
                .values(**o)
                .on_conflict_do_update(index_elements=["id"], set_=o)
            )
            session.execute(stmt)

        # products
        for p in products_to_upsert:
            stmt = (
                pg_insert(ReturnProduct)
                .values(**p)
                .on_conflict_do_update(index_elements=["claim_line_item_id"], set_=p)
            )
            session.execute(stmt)

        session.commit()
        logger.info("İade kayıtları başarıyla upsert edildi.")
        return True
    except SQLAlchemyError as e:
        session.rollback()
        logger.error("DB hatası: %s", e)
        return False


# ------------------------------------------------------------------ #
# Canlı panel veri katmanı
# ------------------------------------------------------------------ #
STATUS_GROUPS = {
    "Created": "new",
    "WaitingInAction": "action",
    "WaitingFraudCheck": "action",
    "Unresolved": "action",
    "InAnalysis": "action",
    "Accepted": "accepted",
    "Rejected": "rejected",
    "Cancelled": "cancelled",
}

STATUS_PRIORITY = {
    "WaitingInAction": 0,
    "Unresolved": 1,
    "InAnalysis": 2,
    "WaitingFraudCheck": 3,
    "Created": 4,
    "Rejected": 5,
    "Cancelled": 6,
    "Accepted": 7,
}


def _millis_to_iso(value):
    try:
        return datetime.fromtimestamp(int(value) / 1000, timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError):
        return None


def _status_group(status):
    return STATUS_GROUPS.get(status, "action")


def _normalize_claim(claim):
    products = []
    statuses = []

    for group in claim.get("items") or []:
        order_line = group.get("orderLine") or {}
        claim_items = group.get("claimItems") or [{}]
        for claim_item in claim_items:
            status = (claim_item.get("claimItemStatus") or {}).get("name") or "Unknown"
            statuses.append(status)
            products.append({
                "claimItemId": claim_item.get("id"),
                "barcode": order_line.get("barcode"),
                "merchantSku": order_line.get("merchantSku"),
                "productName": order_line.get("productName"),
                "size": order_line.get("productSize"),
                "color": order_line.get("productColor"),
                "quantity": 1,
                "reason": (claim_item.get("customerClaimItemReason") or {}).get("name"),
                "customerNote": claim_item.get("customerNote") or claim_item.get("note") or "",
                "status": status,
                "autoAccepted": bool(claim_item.get("autoAccepted")),
                "acceptedBySeller": bool(claim_item.get("acceptedBySeller")),
            })

    status = min(statuses, key=lambda value: STATUS_PRIORITY.get(value, 99)) if statuses else "Unknown"
    claim_id = claim.get("id") or claim.get("claimId")
    tracking_number = claim.get("cargoTrackingNumber")

    return {
        "id": str(claim_id) if claim_id else None,
        "returnRequestNumber": str(claim_id) if claim_id else None,
        "orderNumber": str(claim.get("orderNumber") or ""),
        "customerFirstName": claim.get("customerFirstName") or "",
        "customerLastName": claim.get("customerLastName") or "",
        "status": status,
        "statusGroup": _status_group(status),
        "statuses": sorted(set(statuses), key=lambda value: STATUS_PRIORITY.get(value, 99)),
        "returnDate": _millis_to_iso(claim.get("claimDate")),
        "lastModifiedAt": _millis_to_iso(claim.get("lastModifiedDate") or claim.get("claimDate")),
        "cargoTrackingNumber": str(tracking_number) if tracking_number else None,
        "cargoProviderName": claim.get("cargoProviderName"),
        "cargoSenderNumber": claim.get("cargoSenderNumber"),
        "cargoTrackingLink": claim.get("cargoTrackingLink"),
        "products": products,
    }


def _build_live_payload(claims, *, source, stale=False, warning=None, updated_at=None):
    normalized = [_normalize_claim(claim) for claim in claims]
    normalized.sort(
        key=lambda item: item.get("lastModifiedAt") or item.get("returnDate") or "",
        reverse=True,
    )
    counts = {"all": len(normalized), "new": 0, "action": 0, "accepted": 0, "rejected": 0, "cancelled": 0}
    for item in normalized:
        group = item["statusGroup"]
        counts[group] = counts.get(group, 0) + 1

    return {
        "success": True,
        "source": source,
        "stale": stale,
        "warning": warning,
        "updatedAt": updated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "windowDays": LIVE_RETURN_LOOKBACK_DAYS,
        "total": len(normalized),
        "itemTotal": sum(len(item["products"]) for item in normalized),
        "counts": counts,
        "returns": normalized,
    }


def _database_fallback_payload():
    cutoff = datetime.utcnow() - timedelta(days=LIVE_RETURN_LOOKBACK_DAYS)
    orders = (
        db.session.query(ReturnOrder)
        .filter(ReturnOrder.return_date >= cutoff)
        .order_by(ReturnOrder.return_date.desc())
        .limit(2000)
        .all()
    )
    order_ids = [order.id for order in orders]
    products = (
        db.session.query(ReturnProduct)
        .filter(ReturnProduct.return_order_id.in_(order_ids))
        .all()
        if order_ids else []
    )
    product_map = {}
    for product in products:
        product_map.setdefault(product.return_order_id, []).append(product)

    claims = []
    for order in orders:
        claim_products = []
        for product in product_map.get(order.id, []):
            claim_products.append({
                "orderLine": {
                    "barcode": product.barcode,
                    "productName": product.product_name,
                    "productSize": product.size,
                    "productColor": product.color,
                },
                "claimItems": [{
                    "id": product.claim_line_item_id,
                    "customerClaimItemReason": {"name": product.reason},
                    "claimItemStatus": {"name": order.status or "Unknown"},
                }],
            })
        timestamp = int(order.return_date.replace(tzinfo=timezone.utc).timestamp() * 1000) if order.return_date else None
        claims.append({
            "id": str(order.id),
            "orderNumber": order.order_number,
            "customerFirstName": order.customer_first_name,
            "customerLastName": order.customer_last_name,
            "claimDate": timestamp,
            "lastModifiedDate": timestamp,
            "cargoTrackingNumber": order.cargo_tracking_number,
            "cargoProviderName": order.cargo_provider_name,
            "cargoSenderNumber": order.cargo_sender_number,
            "cargoTrackingLink": order.cargo_tracking_link,
            "items": claim_products,
        })

    return _build_live_payload(
        claims,
        source="database",
        stale=True,
        warning="Trendyol'a ulaşılamadı; son kayıtlı veriler gösteriliyor.",
    )


def get_live_return_payload(force=False):
    now_monotonic = time.monotonic()
    cached = _live_return_cache["payload"]
    cache_age = now_monotonic - _live_return_cache["stored_at"]
    if cached and not force and cache_age < LIVE_RETURN_CACHE_SECONDS:
        return {**cached, "source": "cache"}

    with _live_return_lock:
        now_monotonic = time.monotonic()
        cached = _live_return_cache["payload"]
        cache_age = now_monotonic - _live_return_cache["stored_at"]
        if cached and not force and cache_age < LIVE_RETURN_CACHE_SECONDS:
            return {**cached, "source": "cache"}

        now = datetime.now(timezone.utc)
        data = fetch_data_from_api(now - timedelta(days=LIVE_RETURN_LOOKBACK_DAYS), now)
        if data is None:
            if cached:
                return {
                    **cached,
                    "source": "cache",
                    "stale": True,
                    "warning": "Trendyol'a şu anda ulaşılamıyor; son başarılı veri gösteriliyor.",
                }
            return _database_fallback_payload()

        payload = _build_live_payload(data.get("content", []), source="trendyol")
        _live_return_cache["payload"] = payload
        _live_return_cache["stored_at"] = time.monotonic()
        return payload


# ------------------------------------------------------------------ #
# Planlayıcı
# ------------------------------------------------------------------ #
def schedule_daily_return_fetch(app):
    scheduler = BackgroundScheduler(timezone="Europe/Istanbul")
    scheduler.add_job(
        func=lambda: fetch_and_save_daily_returns(app),
        trigger="cron",
        hour=23,
        minute=50,
        id="daily_return_fetch",
    )
    scheduler.start()
    logger.info("Günlük iade çekme görevi tanımlandı.")


def fetch_and_save_daily_returns(app):
    with app.app_context():
        logger.info("Günlük iade çekme başladı")
        now = datetime.now()
        # Durumu sonradan Accepted/Rejected olan talepleri de upsert edebilmek için
        # yalnız son 24 saati değil yakın geçmişi yeniden tara.
        data = fetch_data_from_api(now - timedelta(days=60), now)
        if data:
            save_to_database(data, db.session)


# ------------------------------------------------------------------ #
# Routes
# ------------------------------------------------------------------ #
@iade_islemleri.route("/iade-verileri")
def iade_verileri():
    now = datetime.now()
    data = fetch_data_from_api(now - timedelta(days=7), now)
    save_to_database(data, db.session)
    return jsonify(data)


@iade_islemleri.route("/iade-listesi")
def iade_listesi():
    return render_template("iade_listesi.html")


@iade_islemleri.route("/iade-listesi/veri")
def iade_listesi_veri():
    force = request.args.get("sync") == "1"
    try:
        return jsonify(get_live_return_payload(force=force))
    except Exception as exc:
        db.session.rollback()
        logger.exception("Canlı Trendyol iade verisi alınamadı: %s", exc)
        return jsonify({
            "success": False,
            "message": "Trendyol iade verileri şu anda alınamıyor.",
        }), 503


# --------------------------- Onay / Güncelle ---------------------- #
def _get_return_order_or_404(session, claim_id):
    order = session.query(ReturnOrder).get(claim_id)
    if not order:
        flash("İade bulunamadı.", "danger")
        raise ValueError("ReturnOrder not found")
    return order


@iade_islemleri.route("/iade-onayla/<uuid:claim_id>", methods=["POST"])
def iade_onayla(claim_id):
    session = db.session
    try:
        order = _get_return_order_or_404(session, claim_id)
        if order.status in ("Accepted", "Onaylandı"):
            flash("Bu iade zaten onaylanmış.", "warning")
            return redirect(url_for("iade_islemleri.iade_listesi"))

        # Form alanları
        order.status = "Accepted"
        order.process_date = datetime.now()
        order.approval_reason = request.form.get("approval_reason")
        order.refund_amount = float(request.form.get("refund_amount") or 0)
        order.return_category = request.form.get("return_category")
        order.return_reason = request.form.get("return_reason")
        order.customer_explanation = request.form.get("customer_explanation")

        # Ürünler
        ids = request.form.getlist("claim_line_item_ids")
        cond = request.form.getlist("product_conditions")
        dmg = request.form.getlist("damage_descriptions")
        insp = request.form.getlist("inspection_notes")
        rts = request.form.getlist("return_to_stock")

        for idx, cid in enumerate(ids):
            p = session.query(ReturnProduct).filter_by(claim_line_item_id=cid).first()
            if not p:
                continue
            p.product_condition = cond[idx] if idx < len(cond) else None
            p.damage_description = dmg[idx] if idx < len(dmg) else None
            p.inspection_notes = insp[idx] if idx < len(insp) else None
            p.return_to_stock = (rts[idx] == "true") if idx < len(rts) else False

        session.commit()
        try: log_user_action("UPDATE", {"işlem_açıklaması": f"İade onaylandı — {len(ids)} ürün", "sayfa": "İade Listesi", "onaylanan_ürün": len(ids)})
        except: pass
        flash("İade onaylandı.", "success")
    except Exception as e:
        session.rollback()
        logger.error("iade_onayla hata: %s", e)
        flash("İade onaylama hatası.", "danger")
    finally:
        session.close()

    return redirect(url_for("iade_islemleri.iade_listesi"))


@iade_islemleri.route("/iade-guncelle/<uuid:claim_id>", methods=["POST"])
def iade_guncelle(claim_id):
    new_status = request.form.get("status")
    if not new_status:
        flash("Yeni durum belirtilmedi.", "warning")
        return redirect(url_for("iade_islemleri.iade_listesi"))

    session = db.session
    try:
        order = _get_return_order_or_404(session, claim_id)
        order.status = new_status
        session.commit()
        try: log_user_action("UPDATE", {"işlem_açıklaması": f"İade durumu güncellendi — {claim_id} → {new_status}", "sayfa": "İade Listesi", "claim_id": str(claim_id), "yeni_durum": new_status})
        except: pass
        flash("İade durumu güncellendi.", "success")
    except Exception as e:
        session.rollback()
        logger.error("iade_guncelle hata: %s", e)
        flash("İade güncelleme hatası.", "danger")
    finally:
        session.close()

    return redirect(url_for("iade_islemleri.iade_listesi"))
