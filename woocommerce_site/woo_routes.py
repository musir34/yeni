"""
WooCommerce Routes - Sipariş yönetimi sayfaları
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from functools import wraps
from datetime import datetime
from .woo_service import WooCommerceService
from .woo_config import WooConfig
from models import db

# Blueprint oluştur
woo_bp = Blueprint('woo', __name__, url_prefix='/site')

# Servis instance
woo_service = WooCommerceService()


def check_woo_config(f):
    """WooCommerce API ayarlarının yapılıp yapılmadığını kontrol eden decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not WooConfig.is_configured():
            flash('WooCommerce API ayarları yapılmamış. Lütfen .env dosyasını kontrol edin.', 'danger')
            return render_template('woocommerce_site/config_error.html'), 500
        return f(*args, **kwargs)
    return decorated_function


@woo_bp.route('/orders')
@check_woo_config
def orders():
    """Sipariş listesi sayfası - Veritabanından hızlı okuma"""
    from .models import WooOrder
    from sqlalchemy import or_
    
    # Query parametreleri
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', None)
    search = request.args.get('search', None)
    per_page = 50
    
    # Veritabanından sorgula (API yerine)
    query = WooOrder.query
    
    # 🔥 Çöp kutusu (trash) durumu özel olarak filtrelenir
    # Sadece status=trash seçildiğinde gösterilir, aksi halde gizlenir
    if status == 'trash':
        query = query.filter_by(status='trash')
    elif status:
        query = query.filter_by(status=status)
    else:
        # Tüm durumlar seçildiğinde trash hariç göster
        query = query.filter(WooOrder.status != 'trash')
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                WooOrder.order_number.ilike(search_term),
                WooOrder.customer_first_name.ilike(search_term),
                WooOrder.customer_last_name.ilike(search_term),
                WooOrder.customer_email.ilike(search_term)
            )
        )
    
    # Sıralama ve sayfalama
    orders_list = query.order_by(WooOrder.date_created.desc()).paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    # Format
    formatted_orders = []
    for order in orders_list.items:
        formatted_orders.append({
            'id': order.order_id,  # WooCommerce order ID
            'order_number': order.order_number,
            'status': order.status,
            'total': order.total,
            'currency': order.currency,
            'payment_method': order.payment_method,
            'date_created': order.date_created.isoformat() if order.date_created else None,
            'customer': {
                'first_name': order.customer_first_name,
                'last_name': order.customer_last_name,
                'email': order.customer_email,
                'phone': order.customer_phone
            },
            'billing_address': {
                'address_1': order.billing_address_1,
                'city': order.billing_city,
                'state': order.billing_state,
                'postcode': order.billing_postcode
            },
            'line_items': order.line_items or []
        })
    
    # Durum listesi
    statuses = woo_service.get_order_statuses()
    
    return render_template(
        'woocommerce_site/orders.html',
        orders=formatted_orders,
        statuses=statuses,
        current_status=status,
        current_page=page,
        search_term=search
    )


@woo_bp.route('/orders/<int:order_id>')
@check_woo_config
def order_detail(order_id):
    """
    Sipariş detay sayfası
    
    Args:
        order_id: Database ID (woo_orders.id) VEYA WooCommerce order ID
    """
    from woocommerce_site.models import WooOrder
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"[ORDER_DETAIL] Gelen order_id: {order_id}")
    
    # Önce database ID olarak kontrol et
    woo_order_db = WooOrder.query.get(order_id)
    
    if woo_order_db:
        # Database'den bulundu, WooCommerce ID'yi al
        logger.info(f"[ORDER_DETAIL] DB'den bulundu: #{woo_order_db.order_number}, WooCommerce ID: {woo_order_db.order_id}")
        woo_order_id = woo_order_db.order_id
    else:
        # Database'de yok, belki WooCommerce ID olarak gönderilmiş
        logger.info(f"[ORDER_DETAIL] DB'de bulunamadı, WooCommerce ID olarak deneniyor: {order_id}")
        woo_order_id = order_id
    
    # WooCommerce API'den çek
    order = woo_service.get_order(woo_order_id)
    
    if not order:
        logger.warning(f"[ORDER_DETAIL] Sipariş bulunamadı: {order_id}")
        flash('Sipariş bulunamadı.', 'warning')
        return redirect(url_for('woo.orders'))
    
    logger.info(f"[ORDER_DETAIL] API'den sipariş alındı: #{order.get('number')}")
    
    # Veritabanına kaydet
    saved_order = woo_service.save_order_to_db(order)
    if saved_order:
        logger.info(f"[ORDER_DETAIL] ✅ DB'ye kaydedildi: ID={saved_order.id}, order_id={saved_order.order_id}, order_number={saved_order.order_number}")
    else:
        logger.error(f"[ORDER_DETAIL] ❌ DB'ye kaydedilemedi!")
    
    formatted_order = WooCommerceService.format_order_data(order)
    notes = woo_service.get_order_notes(woo_order_id)
    statuses = woo_service.get_order_statuses()
    
    return render_template(
        'woocommerce_site/order_detail.html',
        order=formatted_order,
        notes=notes,
        statuses=statuses
    )


@woo_bp.route('/orders/<int:order_id>/update-status', methods=['POST'])
@check_woo_config
def update_order_status(order_id):
    """Sipariş durumunu güncelle (AJAX)"""
    new_status = request.json.get('status')
    
    if not new_status:
        return jsonify({'success': False, 'message': 'Durum belirtilmedi'}), 400
    
    # 'trash' özel durum - silme işlemi
    if new_status == 'trash':
        result = woo_service.delete_order(order_id, force=False)
        
        # Veritabanından sil (WooCommerce'de zaten silinmiş olsa bile)
        from .models import WooOrder
        woo_order = WooOrder.query.filter_by(order_id=order_id).first()
        if woo_order:
            db.session.delete(woo_order)
            db.session.commit()
        
        # WooCommerce'de başarılı silme VEYA zaten silinmiş
        if result or (not result):
            return jsonify({
                'success': True,
                'message': 'Sipariş çöp kutusuna taşındı',
                'deleted': True
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Sipariş silinirken hata oluştu'
            }), 500
    
    # Normal durum güncelleme
    result = woo_service.update_order_status(order_id, new_status)
    
    if result:
        return jsonify({
            'success': True,
            'message': 'Sipariş durumu güncellendi',
            'order': WooCommerceService.format_order_data(result)
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Durum güncellenirken hata oluştu'
        }), 500


@woo_bp.route('/orders/<int:order_id>/add-note', methods=['POST'])
@check_woo_config
def add_order_note(order_id):
    """Siparişe not ekle (AJAX)"""
    note_text = request.json.get('note')
    customer_note = request.json.get('customer_note', False)
    
    if not note_text:
        return jsonify({'success': False, 'message': 'Not metni boş olamaz'}), 400
    
    result = woo_service.add_order_note(order_id, note_text, customer_note)
    
    if result:
        return jsonify({
            'success': True,
            'message': 'Not eklendi',
            'note': result
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Not eklenirken hata oluştu'
        }), 500


@woo_bp.route('/api/orders')
@check_woo_config
def api_orders():
    """Siparişleri JSON olarak döndür (API endpoint)"""
    status = request.args.get('status', None)
    page = request.args.get('page', 1, type=int)
    
    orders_list = woo_service.get_orders(status=status, page=page)
    formatted_orders = [
        WooCommerceService.format_order_data(order) 
        for order in orders_list
    ]
    
    return jsonify({
        'success': True,
        'orders': formatted_orders,
        'page': page
    })


@woo_bp.route('/api/orders/<int:order_id>')
@check_woo_config
def api_order_detail(order_id):
    """Tek bir siparişi JSON olarak döndür"""
    order = woo_service.get_order(order_id)
    
    if not order:
        return jsonify({
            'success': False,
            'message': 'Sipariş bulunamadı'
        }), 404
    
    return jsonify({
        'success': True,
        'order': WooCommerceService.format_order_data(order)
    })


@woo_bp.route('/sync-orders')
@check_woo_config
def sync_orders():
    """Siparişleri WooCommerce'den çekip veritabanına kaydet"""
    days = request.args.get('days', 30, type=int)
    status = request.args.get('status', None)
    
    result = woo_service.sync_orders_to_db(status=status, days=days)
    
    flash(f"{result['total_saved']} sipariş veritabanına kaydedildi.", 'success')
    return redirect(url_for('woo.orders'))


@woo_bp.route('/orders/<int:order_id>/update-customer-info', methods=['POST'])
@check_woo_config
def update_customer_info(order_id):
    """Hızlı siparişler için müşteri bilgilerini güncelle"""
    try:
        data = request.json
        
        # Validasyon
        required_fields = ['first_name', 'last_name', 'phone', 'address', 'city', 'payment_method']
        missing = [f for f in required_fields if not data.get(f)]
        
        if missing:
            return jsonify({
                'success': False,
                'message': f'Eksik alanlar: {", ".join(missing)}'
            }), 400
        
        # WooCommerce API'ye güncelleme gönder
        update_data = {
            'billing': {
                'first_name': data.get('first_name'),
                'last_name': data.get('last_name'),
                'phone': data.get('phone'),
                'address_1': data.get('address'),
                'city': data.get('city'),
                'state': data.get('state', ''),
                'postcode': data.get('postcode', ''),
                'country': data.get('country', 'TR'),
                'email': data.get('email', '')
            },
            'shipping': {
                'first_name': data.get('first_name'),
                'last_name': data.get('last_name'),
                'address_1': data.get('address'),
                'city': data.get('city'),
                'state': data.get('state', ''),
                'postcode': data.get('postcode', ''),
                'country': data.get('country', 'TR')
            },
            'payment_method': data.get('payment_method'),
            'payment_method_title': data.get('payment_method_title', data.get('payment_method'))
        }
        
        # WooCommerce'e gönder
        updated_order = woo_service._make_request(
            f'orders/{order_id}',
            method='PUT',
            data=update_data
        )
        
        if updated_order:
            # Veritabanını güncelle (sadece woo_orders tablosu)
            woo_service.save_order_to_db(updated_order)
            
            # 🔥 WooCommerce siparişleri OrderCreated'a KAYDEDİLMEZ
            # WooCommerce siparişleri sadece woo_orders tablosunda kalır
            
            return jsonify({
                'success': True,
                'message': 'Müşteri bilgileri güncellendi',
                'order': WooCommerceService.format_order_data(updated_order)
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Güncelleme başarısız oldu'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Hata: {str(e)}'
        }), 500


@woo_bp.route('/orders/<int:order_id>/shipping-label')
@check_woo_config
def shipping_label(order_id):
    """Teslimat etiketi yazdırma sayfası (100x100mm)"""
    order = woo_service.get_order(order_id)
    
    if not order:
        flash('Sipariş bulunamadı.', 'warning')
        return redirect(url_for('woo.orders'))
    
    formatted_order = WooCommerceService.format_order_data(order)
    
    # Kapıda ödeme kontrolü
    is_cod = order.get('payment_method') in ['cod', 'cash_on_delivery', 'kapida_odeme']
    
    return render_template(
        'woocommerce_site/shipping_label.html',
        order=formatted_order,
        is_cod=is_cod
    )


@woo_bp.route('/label/<order_number>')
@check_woo_config
def shipping_label_by_number(order_number):
    """Sipariş numarası ile teslimat etiketi (sipariş hazırla için)"""
    from woocommerce_site.models import WooOrder
    
    # WooOrder tablosundan sipariş bul
    woo_order = WooOrder.query.filter_by(order_number=str(order_number)).first()
    
    if not woo_order:
        flash('WooCommerce siparişi bulunamadı.', 'warning')
        return redirect(url_for('siparis_hazirla.index'))
    
    # API'den güncel bilgileri al
    order = woo_service.get_order(woo_order.order_id)
    
    if not order:
        # API'den alamadıysa veritabanındaki raw_data kullan
        order = woo_order.raw_data
    
    formatted_order = WooCommerceService.format_order_data(order)
    
    # Kapıda ödeme kontrolü
    is_cod = order.get('payment_method') in ['cod', 'cash_on_delivery', 'kapida_odeme']
    
    return render_template(
        'woocommerce_site/shipping_label.html',
        order=formatted_order,
        is_cod=is_cod
    )
