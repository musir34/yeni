# order_list_service.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import literal, desc, or_, func, nullslast, false
from sqlalchemy.orm import aliased
import json
import os
from cache_config import cache, CACHE_TIMES
import logging
import math
from datetime import datetime
from barcode_utils import generate_barcode_data_uri

from models import db, Product, OrderCreated, OrderHazirlaniyor, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled, PlatformConfig
from overdue_orders import OVERDUE_STATUSES, STATUS_CODE, overdue_orders_query
from barcode_utils import generate_barcode
import qrcode
import os

order_list_service_bp = Blueprint('order_list_service', __name__)
logger = logging.getLogger(__name__)


def _get_order_pull_enabled() -> bool:
    # Toggle başka worker/request'te commit edilmiş olabilir; taze oku (stale read'i önle).
    # pull_orders_job de aynı sebeple expire_all yapıyor.
    db.session.expire_all()
    cfg = PlatformConfig.query.filter_by(platform='order_pull').first()
    return cfg.is_active if cfg else True


@order_list_service_bp.route('/api/order-pull/toggle', methods=['POST'])
def api_toggle_order_pull():
    from flask import jsonify, session
    from flask_login import current_user
    if not current_user.is_authenticated or not session.get('totp_verified'):
        return jsonify({"success": False, "error": "Yetkisiz erişim"}), 401

    try:
        cfg = PlatformConfig.query.filter_by(platform='order_pull').first()
        if not cfg:
            cfg = PlatformConfig(platform='order_pull', is_active=True, batch_size=100, rate_limit_delay=0.1, max_retries=3)
            db.session.add(cfg)
        cfg.is_active = not cfg.is_active
        db.session.commit()
        status = "aktif" if cfg.is_active else "devre dışı"
        logger.info(f"[ORDER-PULL] Otomatik sipariş çekme {status} yapıldı")
        return jsonify({"success": True, "enabled": cfg.is_active, "message": f"Otomatik sipariş çekme {status}"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

def generate_qr_code(shipping_barcode):
    """
    Kargo barkodu için QR kod oluşturur ve statik klasöre kaydeder.
    """
    if not shipping_barcode:
        logger.warning("❌ [generate_qr_code] Barkod değeri boş!")
        return None
    try:
        qr_dir = os.path.join('static', 'qr_codes')
        os.makedirs(qr_dir, exist_ok=True)
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=16,
            border=1,
        )
        qr.add_data(shipping_barcode)
        qr.make(fit=True)
        qr_path = os.path.join(qr_dir, f"qr_{shipping_barcode}.png")
        qr.make_image(fill_color="black", back_color="white").save(qr_path)
        logger.info(f"✅ QR kod başarıyla kaydedildi: {qr_path}")
        return f"qr_codes/qr_{shipping_barcode}.png"
    except Exception as e:
        logger.error(f"🔥 [generate_qr_code] QR kod oluşturma hatası: {e}")
        return None

def get_product_image(barcode):
    """
    Ürün barkoduna göre resim dosyası yolunu döndürür.
    """
    images_folder = os.path.join('static', 'images')
    extensions = ['.jpg', '.jpeg', '.png', '.gif']
    for ext in extensions:
        image_filename = f"{barcode}{ext}"
        image_path = os.path.join(images_folder, image_filename)
        if os.path.exists(image_path):
            return f"/static/images/{image_filename}"
    return "/static/logo/gullu.png"

def get_union_all_orders():
    """
    Beş tabloda ortak kolonları seçip UNION ALL ile birleştirir.
    """
    c = db.session.query(
        OrderCreated.id.label('id'), OrderCreated.order_number.label('order_number'),
        OrderCreated.order_date.label('order_date'), OrderCreated.details.label('details'),
        OrderCreated.merchant_sku.label('merchant_sku'), OrderCreated.product_barcode.label('product_barcode'),
        OrderCreated.cargo_provider_name.label('cargo_provider_name'), OrderCreated.customer_name.label('customer_name'),
        OrderCreated.customer_surname.label('customer_surname'), OrderCreated.customer_address.label('customer_address'),
        OrderCreated.cargo_tracking_number.label('cargo_tracking_number'), OrderCreated.agreed_delivery_date.label('agreed_delivery_date'),
        OrderCreated.estimated_delivery_end.label('estimated_delivery_end'), literal('Created').label('status_name')
    )
    h = db.session.query(
        OrderHazirlaniyor.id.label('id'), OrderHazirlaniyor.order_number.label('order_number'),
        OrderHazirlaniyor.order_date.label('order_date'), OrderHazirlaniyor.details.label('details'),
        OrderHazirlaniyor.merchant_sku.label('merchant_sku'), OrderHazirlaniyor.product_barcode.label('product_barcode'),
        OrderHazirlaniyor.cargo_provider_name.label('cargo_provider_name'), OrderHazirlaniyor.customer_name.label('customer_name'),
        OrderHazirlaniyor.customer_surname.label('customer_surname'), OrderHazirlaniyor.customer_address.label('customer_address'),
        OrderHazirlaniyor.cargo_tracking_number.label('cargo_tracking_number'), OrderHazirlaniyor.agreed_delivery_date.label('agreed_delivery_date'),
        OrderHazirlaniyor.estimated_delivery_end.label('estimated_delivery_end'), literal('Hazirlaniyor').label('status_name')
    )
    p = db.session.query(
        OrderPicking.id.label('id'), OrderPicking.order_number.label('order_number'),
        OrderPicking.order_date.label('order_date'), OrderPicking.details.label('details'),
        OrderPicking.merchant_sku.label('merchant_sku'), OrderPicking.product_barcode.label('product_barcode'),
        OrderPicking.cargo_provider_name.label('cargo_provider_name'), OrderPicking.customer_name.label('customer_name'),
        OrderPicking.customer_surname.label('customer_surname'), OrderPicking.customer_address.label('customer_address'),
        OrderPicking.cargo_tracking_number.label('cargo_tracking_number'), OrderPicking.agreed_delivery_date.label('agreed_delivery_date'),
        OrderPicking.estimated_delivery_end.label('estimated_delivery_end'), literal('Picking').label('status_name')
    )
    s = db.session.query(
        OrderShipped.id.label('id'), OrderShipped.order_number.label('order_number'),
        OrderShipped.order_date.label('order_date'), OrderShipped.details.label('details'),
        OrderShipped.merchant_sku.label('merchant_sku'), OrderShipped.product_barcode.label('product_barcode'),
        OrderShipped.cargo_provider_name.label('cargo_provider_name'), OrderShipped.customer_name.label('customer_name'),
        OrderShipped.customer_surname.label('customer_surname'), OrderShipped.customer_address.label('customer_address'),
        OrderShipped.cargo_tracking_number.label('cargo_tracking_number'), OrderShipped.agreed_delivery_date.label('agreed_delivery_date'),
        OrderShipped.estimated_delivery_end.label('estimated_delivery_end'), literal('Shipped').label('status_name')
    )
    d = db.session.query(
        OrderDelivered.id.label('id'), OrderDelivered.order_number.label('order_number'),
        OrderDelivered.order_date.label('order_date'), OrderDelivered.details.label('details'),
        OrderDelivered.merchant_sku.label('merchant_sku'), OrderDelivered.product_barcode.label('product_barcode'),
        OrderDelivered.cargo_provider_name.label('cargo_provider_name'), OrderDelivered.customer_name.label('customer_name'),
        OrderDelivered.customer_surname.label('customer_surname'), OrderDelivered.customer_address.label('customer_address'),
        OrderDelivered.cargo_tracking_number.label('cargo_tracking_number'), OrderDelivered.agreed_delivery_date.label('agreed_delivery_date'),
        OrderDelivered.estimated_delivery_end.label('estimated_delivery_end'), literal('Delivered').label('status_name')
    )
    x = db.session.query(
        OrderCancelled.id.label('id'), OrderCancelled.order_number.label('order_number'),
        OrderCancelled.order_date.label('order_date'), OrderCancelled.details.label('details'),
        OrderCancelled.merchant_sku.label('merchant_sku'), OrderCancelled.product_barcode.label('product_barcode'),
        OrderCancelled.cargo_provider_name.label('cargo_provider_name'), OrderCancelled.customer_name.label('customer_name'),
        OrderCancelled.customer_surname.label('customer_surname'), OrderCancelled.customer_address.label('customer_address'),
        OrderCancelled.cargo_tracking_number.label('cargo_tracking_number'), OrderCancelled.agreed_delivery_date.label('agreed_delivery_date'),
        OrderCancelled.estimated_delivery_end.label('estimated_delivery_end'), literal('Cancelled').label('status_name')
    )
    return c.union_all(h, p, s, d, x)

# Geçerli sıralama seçenekleri (UI dropdown ile eşleşir)
SORT_OPTIONS = ('date_desc', 'deadline_asc', 'deadline_desc')
DEFAULT_SORT = 'date_desc'
PER_PAGE_OPTIONS = (50, 100, 200)
DEFAULT_PER_PAGE = 50


def _get_sort_key():
    """Query param'dan güvenli sıralama anahtarı döndürür (whitelist)."""
    sort_key = request.args.get('sort', DEFAULT_SORT)
    return sort_key if sort_key in SORT_OPTIONS else DEFAULT_SORT


def _get_per_page():
    """Sayfa başına sipariş adedini güvenli seçeneklerle sınırla."""
    per_page = request.args.get('per_page', DEFAULT_PER_PAGE, type=int)
    return per_page if per_page in PER_PAGE_OPTIONS else DEFAULT_PER_PAGE


def _sort_clause(sort_key, order_date_col, agreed_col, estimated_col):
    """Sıralama anahtarına göre SQLAlchemy order_by ifadesi üretir.

    deadline_* seçeneklerinde teslimata kalan süre, taahhüt teslim tarihi
    (yoksa tahmini teslim sonu) baz alınır. Tarihi olmayan siparişler en sona.
    """
    deadline = func.coalesce(agreed_col, estimated_col)
    if sort_key == 'deadline_asc':
        # Son teslim tarihi en yakın (en acil) en üstte
        return (nullslast(deadline.asc()), desc(order_date_col))
    if sort_key == 'deadline_desc':
        return (nullslast(deadline.desc()), desc(order_date_col))
    return (desc(order_date_col),)


def _group_sort_clause(sort_key, order_date_col, agreed_col, estimated_col):
    """Benzersiz order_number sayfalaması için aggregate sıralama üretir."""
    deadline = func.coalesce(agreed_col, estimated_col)
    if sort_key == 'deadline_asc':
        return (nullslast(func.min(deadline).asc()), desc(func.max(order_date_col)))
    if sort_key == 'deadline_desc':
        return (nullslast(func.max(deadline).desc()), desc(func.max(order_date_col)))
    return (desc(func.max(order_date_col)),)


def _normalize_details(details):
    if not details:
        return []
    try:
        parsed = json.loads(details) if isinstance(details, str) else details
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    return []


def _append_details(existing, new_details):
    merged = _normalize_details(existing.details)
    merged.extend(_normalize_details(new_details))
    existing.details = json.dumps(merged)


def _page_bounds(page, per_page, total):
    total_pages = math.ceil(total / per_page) if total else 0
    if page < 1:
        page = 1
    if total_pages and page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page if total else 0
    return page, total_pages, offset


def _merge_order_rows(rows, status_getter):
    class MockOrder:
        pass

    orders = []
    seen_orders = {}
    for r in rows:
        on = r.order_number
        if on in seen_orders:
            _append_details(seen_orders[on], r.details)
            continue

        mock = MockOrder()
        mock.id = r.id
        mock.order_number = on
        mock.order_date = r.order_date
        mock.details = r.details
        mock.merchant_sku = r.merchant_sku
        mock.product_barcode = r.product_barcode
        mock.status = status_getter(r)
        mock.cargo_provider_name = getattr(r, 'cargo_provider_name', '')
        mock.customer_name = getattr(r, 'customer_name', '')
        mock.customer_surname = getattr(r, 'customer_surname', '')
        mock.customer_address = getattr(r, 'customer_address', '')
        mock.cargo_tracking_number = getattr(r, 'cargo_tracking_number', '')
        mock.agreed_delivery_date = getattr(r, 'agreed_delivery_date', None)
        mock.estimated_delivery_end = getattr(r, 'estimated_delivery_end', None)
        seen_orders[on] = mock
        orders.append(mock)
    return orders


def _get_overdue_orders():
    """Yeni/Hazırlanıyor/İşleme statülerindeki teslim süresi geçmiş (geciken) siparişler.

    En gecikmiş (teslim tarihi en eski) önce gelir. Varsayılan görünümde bu
    siparişler kart listesinden ayrılır; deadline_asc statü sıralamasında tekrar
    listeye dahil edilip en üstte gösterilir.
    """
    raw_overdue = []
    for key, model, _label in OVERDUE_STATUSES:
        for order in overdue_orders_query(model).all():
            order._display_status = STATUS_CODE[key]
            raw_overdue.append(order)

    raw_overdue.sort(key=lambda o: (
        o.agreed_delivery_date or o.estimated_delivery_end or datetime.max,
        o.order_number or ''
    ))
    overdue = _merge_order_rows(raw_overdue, lambda r: getattr(r, '_display_status', ''))
    process_order_details(overdue)
    return overdue


def _overdue_order_numbers(overdue_orders):
    """Geciken siparişleri normal listeden ayırmak için order_number kümesi."""
    return {o.order_number for o in overdue_orders if getattr(o, 'order_number', None)}


def _decorate_order_priority(orders):
    """Kartlarda hızlı öncelik sinyali için süre durumunu ekle."""
    now = datetime.utcnow()
    for order in orders:
        deadline = getattr(order, 'agreed_delivery_date', None) or getattr(order, 'estimated_delivery_end', None)
        order.is_overdue = False
        order.is_urgent = False
        if not deadline:
            continue
        remaining_seconds = (deadline - now).total_seconds()
        order.is_overdue = remaining_seconds <= 0
        order.is_urgent = 0 < remaining_seconds <= 7200


def get_order_list():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = _get_per_page()
        search_query = request.args.get('search', None)
        sort_key = _get_sort_key()
        show_overdue = sort_key == 'deadline_asc' and request.args.get('show_overdue') == '1'
        overdue_orders = _get_overdue_orders()
        overdue_numbers = _overdue_order_numbers(overdue_orders)
        union_query = get_union_all_orders()
        sub = union_query.subquery()
        AllOrders = aliased(sub)
        q = db.session.query(AllOrders)

        # Geciken = SADECE Yeni/Hazırlanıyor/İşleme Alındı statülerinde teslim
        # süresi geçmiş sipariş. (Teslim Edildi/Kargoda/İptal asla geciken sayılmaz.)
        _overdue_clause = (
            AllOrders.c.status_name.in_(('Created', 'Hazirlaniyor', 'Picking')) &
            AllOrders.c.order_number.in_(overdue_numbers)
        ) if overdue_numbers else None

        if show_overdue:
            # "Geciken" rozetine tıklama → YALNIZCA geciken siparişler gösterilir;
            # teslim edilenler vb. listeye karışmaz.
            q = q.filter(_overdue_clause if _overdue_clause is not None else false())
        elif _overdue_clause is not None and not search_query:
            # Normal liste (arama yok) → geciken siparişleri ana listeden gizle
            # (ayrı rozette toplanır). ARAMADA gizleme YOK → geciken sipariş no'su
            # normal aramada da bulunabilsin.
            q = q.filter(~_overdue_clause)

        if search_query:
            search_query = search_query.strip()
            q = q.filter(
                or_(
                    AllOrders.c.order_number.ilike(f"%{search_query}%"),
                    AllOrders.c.customer_name.ilike(f"%{search_query}%"),
                    AllOrders.c.customer_surname.ilike(f"%{search_query}%"),
                    (AllOrders.c.customer_name + ' ' + AllOrders.c.customer_surname).ilike(f"%{search_query}%")
                )
            )
            logger.debug(f"Arama sorgusuna göre filtre: {search_query}")

        grouped_orders = (
            q.with_entities(AllOrders.c.order_number.label('order_number'))
            .group_by(AllOrders.c.order_number)
        )
        total_orders_count = grouped_orders.count()
        page, total_pages, offset = _page_bounds(page, per_page, total_orders_count)
        page_order_rows = (
            grouped_orders
            .order_by(*_group_sort_clause(
                sort_key, AllOrders.c.order_date,
                AllOrders.c.agreed_delivery_date, AllOrders.c.estimated_delivery_end
            ))
            .offset(offset)
            .limit(per_page)
            .all()
        ) if total_orders_count else []
        page_order_numbers = [r.order_number for r in page_order_rows]

        rows = []
        if page_order_numbers:
            order_index = {order_number: idx for idx, order_number in enumerate(page_order_numbers)}
            rows = (
                q.filter(AllOrders.c.order_number.in_(page_order_numbers))
                .order_by(*_sort_clause(
                    sort_key, AllOrders.c.order_date,
                    AllOrders.c.agreed_delivery_date, AllOrders.c.estimated_delivery_end
                ))
                .all()
            )
            rows.sort(key=lambda r: order_index.get(r.order_number, len(order_index)))

        orders = _merge_order_rows(rows, lambda r: r.status_name)

        process_order_details(orders)
        _decorate_order_priority(orders)

        return render_template(
            'order_list.html', orders=orders, page=page, total_pages=total_pages,
            total_orders_count=total_orders_count, search_query=search_query,
            sort_key=sort_key, overdue_orders=overdue_orders,
            active_list='all', per_page=per_page, per_page_options=PER_PAGE_OPTIONS,
            show_overdue=show_overdue,
            order_pull_enabled=_get_order_pull_enabled()
        )
    except Exception as e:
        logger.error(f"Hata: get_order_list - {e}")
        flash("Sipariş listesi yüklenirken hata oluştu.", "danger")
        return redirect(url_for('siparis_hazirla.index'))


# --- BU FONKSİYON GÜNCELLENDİ ---
def process_order_details(orders):
    """
    Her sipariş için 'details' alanını işleyerek ve Product tablosundan sorgu yaparak
    model kodu, renk, beden gibi zenginleştirilmiş ürün detayları hazırlar.
    """
    try:
        barcodes = set()
        for order in orders:
            if not order.details: continue
            try:
                details_list = json.loads(order.details) if isinstance(order.details, str) else order.details
                for d in details_list:
                    if d.get('barcode'): barcodes.add(d.get('barcode'))
            except (json.JSONDecodeError, TypeError):
                continue

        products_dict = {}
        if barcodes:
            products_list = Product.query.filter(Product.barcode.in_(barcodes)).all()
            products_dict = {p.barcode: p for p in products_list}

        for order in orders:
            if not order.details:
                order.processed_details = []
                continue

            try:
                details_list = json.loads(order.details) if isinstance(order.details, str) else order.details
                processed_details = []
                for d in details_list:
                    product_barcode = d.get('barcode', '')
                    product = products_dict.get(product_barcode) # Veritabanından çekilen ürünü al

                    # --- DÜZELTME BURADA ---
                    # Product veritabanından gelen bilgileri `detail` objesine ekliyoruz.
                    processed_details.append({
                        'sku': d.get('sku', 'Bilinmeyen SKU'),
                        'barcode': product_barcode,
                        'image_url': get_product_image(product_barcode),
                        'quantity': d.get('quantity', 0),
                        # Product bulunduysa model kodu, renk ve beden bilgilerini ekle
                        'model_code': product.product_main_id if product else 'N/A',
                        'color': product.color if product else d.get('color', 'N/A'),
                        'size': product.size if product else d.get('size', 'N/A')
                    })
                order.processed_details = processed_details
            except (json.JSONDecodeError, TypeError):
                order.processed_details = []

    except Exception as e:
        logger.error(f"Hata: process_order_details - {e}")

def get_filtered_orders(status):
    try:
        page = request.args.get('page', 1, type=int)
        per_page = _get_per_page()
        search_query = request.args.get('search', None)
        sort_key = _get_sort_key()
        overdue_orders = _get_overdue_orders()
        overdue_numbers = _overdue_order_numbers(overdue_orders)
        status_map = {
            'Yeni': OrderCreated, 'Created': OrderCreated,
            'Hazırlanıyor': OrderHazirlaniyor, 'Hazirlaniyor': OrderHazirlaniyor,
            'İşleme Alındı': OrderPicking,
            'Picking': OrderPicking, 'Kargoda': OrderShipped, 'Shipped': OrderShipped,
            'Teslim Edildi': OrderDelivered, 'Delivered': OrderDelivered,
            'İptal Edildi': OrderCancelled, 'Cancelled': OrderCancelled
        }
        active_map = {
            OrderCreated: 'new',
            OrderHazirlaniyor: 'hazirlaniyor',
            OrderPicking: 'processed',
            OrderShipped: 'shipped',
            OrderDelivered: 'delivered',
            OrderCancelled: 'cancelled',
        }
        model_cls = status_map.get(status)
        if not model_cls:
            flash(f"{status} durumuna ait tablo bulunamadı.", "warning")
            return redirect(url_for('siparis_hazirla.index'))


        orders_query = model_cls.query
        # Arama varken geciken gizleme UYGULANMAZ → aranan geciken sipariş no'su bulunur.
        hide_overdue_in_status = sort_key != 'deadline_asc' and not search_query
        if hide_overdue_in_status and overdue_numbers and model_cls in (OrderCreated, OrderHazirlaniyor, OrderPicking):
            orders_query = orders_query.filter(~model_cls.order_number.in_(overdue_numbers))

        if search_query:
            sq = search_query.strip()
            orders_query = orders_query.filter(
                or_(
                    model_cls.order_number.ilike(f"%{sq}%"),
                    model_cls.customer_name.ilike(f"%{sq}%"),
                    model_cls.customer_surname.ilike(f"%{sq}%"),
                    (model_cls.customer_name + ' ' + model_cls.customer_surname).ilike(f"%{sq}%")
                )
            )

        grouped_orders = (
            orders_query.with_entities(model_cls.order_number.label('order_number'))
            .group_by(model_cls.order_number)
        )
        total_orders_count = grouped_orders.count()
        page, total_pages, offset = _page_bounds(page, per_page, total_orders_count)
        page_order_rows = (
            grouped_orders
            .order_by(*_group_sort_clause(
                sort_key, model_cls.order_date,
                model_cls.agreed_delivery_date, model_cls.estimated_delivery_end
            ))
            .offset(offset)
            .limit(per_page)
            .all()
        ) if total_orders_count else []
        page_order_numbers = [r.order_number for r in page_order_rows]

        raw_orders = []
        if page_order_numbers:
            order_index = {order_number: idx for idx, order_number in enumerate(page_order_numbers)}
            raw_orders = (
                orders_query
                .filter(model_cls.order_number.in_(page_order_numbers))
                .order_by(*_sort_clause(
                    sort_key, model_cls.order_date,
                    model_cls.agreed_delivery_date, model_cls.estimated_delivery_end
                ))
                .all()
            )
            raw_orders.sort(key=lambda r: order_index.get(r.order_number, len(order_index)))

        status_code = status_map[status].__name__.replace("Order", "")
        orders = _merge_order_rows(raw_orders, lambda _r: status_code)

        process_order_details(orders)
        _decorate_order_priority(orders)

        return render_template(
            'order_list.html', orders=orders, page=page, total_pages=total_pages,
            total_orders_count=total_orders_count, search_query=search_query,
            sort_key=sort_key, overdue_orders=overdue_orders,
            active_list=active_map.get(model_cls), per_page=per_page,
            per_page_options=PER_PAGE_OPTIONS, show_overdue=False,
            order_pull_enabled=_get_order_pull_enabled()
        )
    except Exception as e:
        logger.error(f"Hata: get_filtered_orders - {e}")
        flash(f'{status} durumundaki siparişler yüklenirken bir hata oluştu.', 'danger')
        return redirect(url_for('siparis_hazirla.index'))


def search_order_by_number(order_number):
    try:
        logger.debug(f"Sipariş aranıyor: {order_number}")
        for model_cls in (OrderCreated, OrderHazirlaniyor, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled):
            order = model_cls.query.filter_by(order_number=order_number).first()
            if order:
                logger.debug(f"Buldum: {order} tablo {model_cls.__tablename__}")
                return order
        logger.debug("Sipariş bulunamadı.")
        return None
    except Exception as e:
        logger.error(f"Hata: search_order_by_number - {e}")
        return None

# Route kısımları
@order_list_service_bp.route('/order-list/all', methods=['GET'])
def order_list_all(): return get_order_list()

@order_list_service_bp.route('/order-list/new', methods=['GET'])
def order_list_new(): return get_filtered_orders('Yeni')

@order_list_service_bp.route('/order-list/hazirlaniyor', methods=['GET'])
def order_list_hazirlaniyor(): return get_filtered_orders('Hazırlanıyor')

@order_list_service_bp.route('/order-list/processed', methods=['GET'])
def order_list_processed(): return get_filtered_orders('İşleme Alındı')

@order_list_service_bp.route('/order-list/shipped', methods=['GET'])
def order_list_shipped(): return get_filtered_orders('Kargoda')

@order_list_service_bp.route('/order-list/delivered', methods=['GET'])
def order_list_delivered(): return get_filtered_orders('Teslim Edildi')

@order_list_service_bp.route('/order-list/cancelled')
def order_list_cancelled(): return get_filtered_orders('İptal Edildi') 

@order_list_service_bp.route('/order-label', methods=['POST'])
def order_label():
    from urllib.parse import unquote
    try:
        logger.info("🚀 /order-label POST isteği alındı.")
        order_number = request.form.get('order_number')
        shipping_barcode = request.form.get('shipping_barcode')
        cargo_provider = unquote(unquote(request.form.get('cargo_provider', '')))
        customer_name = unquote(unquote(request.form.get('customer_name', '')))
        customer_surname = unquote(unquote(request.form.get('customer_surname', '')))
        customer_address = unquote(unquote(request.form.get('customer_address', '')))
        telefon_no = request.form.get('telefon_no', 'Bilinmiyor')

        # Kapıda ödeme bilgileri
        kapida_odeme = request.form.get('kapida_odeme', '0') == '1'
        kapida_odeme_tutari = float(request.form.get('kapida_odeme_tutari', 0) or 0)

        # Barkod dosya YOK: inline (base64) veri
        barcode_data_uri = generate_barcode_data_uri(shipping_barcode) if shipping_barcode else None
        # QR kaydetmeye devam (istersen bunu da inline'a çevirebiliriz)
        qr_code_path = generate_qr_code(shipping_barcode) if shipping_barcode else None

        return render_template(
            'order_label.html',
            order_number=order_number,
            shipping_barcode=shipping_barcode,
            barcode_data_uri=barcode_data_uri,     # <— DÜZGÜN AD
            qr_code_path=qr_code_path,
            cargo_provider_name=cargo_provider,
            customer_name=customer_name,
            customer_surname=customer_surname,
            customer_address=customer_address,
            telefon_no=telefon_no,
            kapida_odeme=kapida_odeme,
            kapida_odeme_tutari=kapida_odeme_tutari,
        )
    except Exception as e:
        logger.error(f"🔥 Hata: order_label - {e}", exc_info=True)
        flash('Kargo etiketi oluşturulurken bir hata oluştu.', 'danger')
        return redirect(url_for('siparis_hazirla.index'))  # yeni akışa uygun
