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
    
    if status:
        query = query.filter_by(status=status)
    
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
    """Sipariş detay sayfası"""
    order = woo_service.get_order(order_id)
    
    if not order:
        flash('Sipariş bulunamadı.', 'warning')
        return redirect(url_for('woo.orders'))
    
    # Veritabanına kaydet
    woo_service.save_order_to_db(order)
    
    formatted_order = WooCommerceService.format_order_data(order)
    notes = woo_service.get_order_notes(order_id)
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
            # Veritabanını güncelle
            woo_service.save_order_to_db(updated_order)
            
            # ✅ OrderCreated'a kaydet (artık bilgiler tam)
            try:
                from models import OrderCreated
                import json
                
                order_number = str(order_id)
                
                # Zaten var mı kontrol et
                existing = OrderCreated.query.filter_by(order_number=order_number).first()
                
                if not existing:
                    # Line items hazırla
                    line_items = []
                    for item in updated_order.get('line_items', []):
                        line_items.append({
                            'barcode': item.get('sku', ''),
                            'product_name': item.get('name', ''),
                            'quantity': item.get('quantity', 1),
                            'price': float(item.get('price', 0)),
                            'line_id': item.get('id')
                        })
                    
                    # OrderCreated'a ekle
                    new_order = OrderCreated(
                        order_number=order_number,
                        order_date=datetime.fromisoformat(updated_order.get('date_created', '').replace('Z', '+00:00')) if updated_order.get('date_created') else datetime.utcnow(),
                        status=updated_order.get('status', 'processing'),
                        customer_name=data.get('first_name'),
                        customer_surname=data.get('last_name'),
                        customer_address=data.get('address'),
                        customer_id=data.get('email', ''),
                        product_barcode='',
                        product_name='',
                        quantity=sum(item.get('quantity', 0) for item in updated_order.get('line_items', [])),
                        amount=float(updated_order.get('total', 0)),
                        currency_code=updated_order.get('currency', 'TRY'),
                        package_number=order_number,
                        details=json.dumps(line_items, ensure_ascii=False),
                        cargo_provider_name='MNG',
                        shipment_package_id=None
                    )
                    
                    db.session.add(new_order)
                    db.session.commit()
            except Exception as e:
                print(f"OrderCreated'a kaydetme hatası: {e}")
                # Hata olsa da devam et
            
            return jsonify({
                'success': True,
                'message': 'Müşteri bilgileri güncellendi ve sipariş hazırlamaya eklendi',
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
