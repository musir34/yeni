# order_list_service.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import literal, desc, or_
from sqlalchemy.orm import aliased
import json
import os
from cache_config import cache, CACHE_TIMES
import logging
from datetime import datetime
from barcode_utils import generate_barcode_data_uri

from models import db, Product, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled, PlatformConfig
from barcode_utils import generate_barcode
import qrcode
import os

order_list_service_bp = Blueprint('order_list_service', __name__)
logger = logging.getLogger(__name__)


def _get_order_pull_enabled() -> bool:
    cfg = PlatformConfig.query.filter_by(platform='order_pull').first()
    return cfg.is_active if cfg else True


@order_list_service_bp.route('/api/order-pull/toggle', methods=['POST'])
def api_toggle_order_pull():
    from flask import jsonify
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
        OrderCreated.shipping_barcode.label('shipping_barcode'), OrderCreated.agreed_delivery_date.label('agreed_delivery_date'),
        OrderCreated.estimated_delivery_end.label('estimated_delivery_end'), literal('Created').label('status_name')
    )
    p = db.session.query(
        OrderPicking.id.label('id'), OrderPicking.order_number.label('order_number'),
        OrderPicking.order_date.label('order_date'), OrderPicking.details.label('details'),
        OrderPicking.merchant_sku.label('merchant_sku'), OrderPicking.product_barcode.label('product_barcode'),
        OrderPicking.cargo_provider_name.label('cargo_provider_name'), OrderPicking.customer_name.label('customer_name'),
        OrderPicking.customer_surname.label('customer_surname'), OrderPicking.customer_address.label('customer_address'),
        OrderPicking.shipping_barcode.label('shipping_barcode'), OrderPicking.agreed_delivery_date.label('agreed_delivery_date'),
        OrderPicking.estimated_delivery_end.label('estimated_delivery_end'), literal('Picking').label('status_name')
    )
    s = db.session.query(
        OrderShipped.id.label('id'), OrderShipped.order_number.label('order_number'),
        OrderShipped.order_date.label('order_date'), OrderShipped.details.label('details'),
        OrderShipped.merchant_sku.label('merchant_sku'), OrderShipped.product_barcode.label('product_barcode'),
        OrderShipped.cargo_provider_name.label('cargo_provider_name'), OrderShipped.customer_name.label('customer_name'),
        OrderShipped.customer_surname.label('customer_surname'), OrderShipped.customer_address.label('customer_address'),
        OrderShipped.shipping_barcode.label('shipping_barcode'), OrderShipped.agreed_delivery_date.label('agreed_delivery_date'),
        OrderShipped.estimated_delivery_end.label('estimated_delivery_end'), literal('Shipped').label('status_name')
    )
    d = db.session.query(
        OrderDelivered.id.label('id'), OrderDelivered.order_number.label('order_number'),
        OrderDelivered.order_date.label('order_date'), OrderDelivered.details.label('details'),
        OrderDelivered.merchant_sku.label('merchant_sku'), OrderDelivered.product_barcode.label('product_barcode'),
        OrderDelivered.cargo_provider_name.label('cargo_provider_name'), OrderDelivered.customer_name.label('customer_name'),
        OrderDelivered.customer_surname.label('customer_surname'), OrderDelivered.customer_address.label('customer_address'),
        OrderDelivered.shipping_barcode.label('shipping_barcode'), OrderDelivered.agreed_delivery_date.label('agreed_delivery_date'),
        OrderDelivered.estimated_delivery_end.label('estimated_delivery_end'), literal('Delivered').label('status_name')
    )
    x = db.session.query(
        OrderCancelled.id.label('id'), OrderCancelled.order_number.label('order_number'),
        OrderCancelled.order_date.label('order_date'), OrderCancelled.details.label('details'),
        OrderCancelled.merchant_sku.label('merchant_sku'), OrderCancelled.product_barcode.label('product_barcode'),
        OrderCancelled.cargo_provider_name.label('cargo_provider_name'), OrderCancelled.customer_name.label('customer_name'),
        OrderCancelled.customer_surname.label('customer_surname'), OrderCancelled.customer_address.label('customer_address'),
        OrderCancelled.shipping_barcode.label('shipping_barcode'), OrderCancelled.agreed_delivery_date.label('agreed_delivery_date'),
        OrderCancelled.estimated_delivery_end.label('estimated_delivery_end'), literal('Cancelled').label('status_name')
    )
    return c.union_all(p, s, d, x)

def get_order_list():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50
        search_query = request.args.get('search', None)
        union_query = get_union_all_orders()
        sub = union_query.subquery()
        AllOrders = aliased(sub)
        q = db.session.query(AllOrders)

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

        q = q.order_by(desc(AllOrders.c.order_date))
        paginated_orders = q.paginate(page=page, per_page=per_page, error_out=False)
        rows = paginated_orders.items
        total_pages = paginated_orders.pages
        total_orders_count = paginated_orders.total

        orders = []
        class MockOrder: pass
        seen_orders = {}
        for r in rows:
            on = r.order_number
            if on in seen_orders:
                # Aynı sipariş numaralı satırın details'ini mevcut siparişe ekle
                existing = seen_orders[on]
                if r.details:
                    try:
                        new_details = json.loads(r.details) if isinstance(r.details, str) else r.details
                        cur_details = json.loads(existing.details) if isinstance(existing.details, str) else (existing.details or [])
                        cur_details.extend(new_details)
                        existing.details = json.dumps(cur_details)
                    except (json.JSONDecodeError, TypeError):
                        pass
                continue
            mock = MockOrder()
            mock.id = r.id
            mock.order_number = on
            mock.order_date = r.order_date
            mock.details = r.details
            mock.merchant_sku = r.merchant_sku
            mock.product_barcode = r.product_barcode
            mock.status = r.status_name
            mock.cargo_provider_name = getattr(r, 'cargo_provider_name', '')
            mock.customer_name = getattr(r, 'customer_name', '')
            mock.customer_surname = getattr(r, 'customer_surname', '')
            mock.customer_address = getattr(r, 'customer_address', '')
            mock.shipping_barcode = getattr(r, 'shipping_barcode', '')
            mock.agreed_delivery_date = getattr(r, 'agreed_delivery_date', None)
            mock.estimated_delivery_end = getattr(r, 'estimated_delivery_end', None)
            seen_orders[on] = mock
            orders.append(mock)

        process_order_details(orders)

        return render_template(
            'order_list.html', orders=orders, page=page, total_pages=total_pages,
            total_orders_count=total_orders_count, search_query=search_query,
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
        per_page = 50
        search_query = request.args.get('search', None)
        status_map = {
            'Yeni': OrderCreated, 'Created': OrderCreated, 'İşleme Alındı': OrderPicking,
            'Picking': OrderPicking, 'Kargoda': OrderShipped, 'Shipped': OrderShipped,
            'Teslim Edildi': OrderDelivered, 'Delivered': OrderDelivered,
            'İptal Edildi': OrderCancelled, 'Cancelled': OrderCancelled
        }
        model_cls = status_map.get(status)
        if not model_cls:
            flash(f"{status} durumuna ait tablo bulunamadı.", "warning")
            return redirect(url_for('siparis_hazirla.index'))


        orders_query = model_cls.query
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

        orders_query = orders_query.order_by(model_cls.order_date.desc())
        paginated_orders = orders_query.paginate(page=page, per_page=per_page, error_out=False)
        raw_orders = paginated_orders.items

        # Aynı sipariş numaralı satırları birleştir
        seen = {}
        orders = []
        for order in raw_orders:
            on = order.order_number
            if on in seen:
                existing = seen[on]
                if order.details:
                    try:
                        new_d = json.loads(order.details) if isinstance(order.details, str) else order.details
                        cur_d = json.loads(existing.details) if isinstance(existing.details, str) else (existing.details or [])
                        cur_d.extend(new_d)
                        existing.details = json.dumps(cur_d)
                    except (json.JSONDecodeError, TypeError):
                        pass
                continue
            seen[on] = order
            orders.append(order)

        for order in orders:
            order.status = status_map[status].__name__.replace("Order", "")

        process_order_details(orders)

        return render_template(
            'order_list.html', orders=orders, page=page, total_pages=paginated_orders.pages,
            total_orders_count=paginated_orders.total, search_query=search_query,
            order_pull_enabled=_get_order_pull_enabled()
        )
    except Exception as e:
        logger.error(f"Hata: get_filtered_orders - {e}")
        flash(f'{status} durumundaki siparişler yüklenirken bir hata oluştu.', 'danger')
        return redirect(url_for('siparis_hazirla.index'))


def search_order_by_number(order_number):
    try:
        logger.debug(f"Sipariş aranıyor: {order_number}")
        for model_cls in (OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled):
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

        # Barkod dosya YOK: inline (base64) veri
        barcode_data_uri = generate_barcode_data_uri(shipping_barcode) if shipping_barcode else None
        # QR kaydetmeye devam (istersen bunu da inline’a çevirebiliriz)
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
            telefon_no=telefon_no
        )
    except Exception as e:
        logger.error(f"🔥 Hata: order_label - {e}", exc_info=True)
        flash('Kargo etiketi oluşturulurken bir hata oluştu.', 'danger')
        return redirect(url_for('siparis_hazirla.index'))  # yeni akışa uygun
