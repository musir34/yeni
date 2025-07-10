import base64
import logging
import requests
from datetime import datetime, timedelta
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

# ------------------------------------------------------------------ #
# Genel ayarlar
# ------------------------------------------------------------------ #
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    url = f"https://api.trendyol.com/sapigw/suppliers/{SUPPLIER_ID}/claims"
    cred = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {cred}",
        "Content-Type": "application/json"
    }

    session = get_requests_session()
    page, size = 0, 50
    all_content = []

    while True:
        params = {
            "size": size,
            "page": page,
            "startDate": int(start_date.timestamp() * 1000),
            "endDate": int(end_date.timestamp() * 1000),
            "sortColumn": "CLAIM_DATE",
            "sortDirection": "DESC",
        }
        r = session.get(url, headers=headers, params=params)
        if r.status_code != 200:
            logger.error("API hatası [%s]: %s", r.status_code, r.text)
            return None

        data = r.json()
        content = data.get("content", [])
        if not content:
            break

        all_content.extend(content)
        page += 1

    logger.info("API’den toplam %d kayıt alındı.", len(all_content))
    return {"content": all_content}


# ------------------------------------------------------------------ #
# Veritabanı işlemleri
# ------------------------------------------------------------------ #
def save_to_database(data: dict, session):
    """ReturnOrder & ReturnProduct toplu kaydetme/upsert."""
    content = data.get("content", [])
    if not content:
        return True

    try:
        existing = {str(o.id) for o in session.query(ReturnOrder.id).all()}
    except Exception as e:
        logger.error("Mevcut iadeler alınamadı: %s", e)
        return False

    orders_to_upsert, products_to_upsert = [], []
    processed = set()

    for item in content:
        claim_id = item.get("id")
        if (not claim_id) or (claim_id in processed) or (str(claim_id) in existing) or (not is_valid_uuid(claim_id)):
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
        if claim_status in ("Accepted", "Onaylandı"):
            continue  # onaylanmış iadeleri kaydetme

        claim_date_ms = item.get("claimDate")
        claim_date = datetime.fromtimestamp(claim_date_ms / 1000) if claim_date_ms else None

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
        data = fetch_data_from_api(now - timedelta(days=1), now)
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
@with_db_session
def iade_listesi(session):
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "", type=str)

    query = session.query(ReturnOrder)
    if search:
        query = query.filter(ReturnOrder.order_number.ilike(f"%{search}%"))

    per_page = 100
    total = query.count()
    orders = (
        query.order_by(ReturnOrder.return_date.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    products = (
        session.query(ReturnProduct)
        .filter(ReturnProduct.return_order_id.in_([o.id for o in orders]))
        .all()
    )
    pdict = {}
    for p in products:
        pdict.setdefault(p.return_order_id, []).append(p)

    claims = [
        {
            "id": o.id,
            "order_number": o.order_number,
            "status": o.status,
            "return_date": o.return_date,
            "customer_first_name": o.customer_first_name,
            "customer_last_name": o.customer_last_name,
            "products": pdict.get(o.id, []),
        }
        for o in orders
    ]

    return render_template(
        "iade_listesi.html",
        claims=claims,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page,
        total_elements=total,
        search=search,
    )


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
        flash("İade durumu güncellendi.", "success")
    except Exception as e:
        session.rollback()
        logger.error("iade_guncelle hata: %s", e)
        flash("İade güncelleme hatası.", "danger")
    finally:
        session.close()

    return redirect(url_for("iade_islemleri.iade_listesi"))
