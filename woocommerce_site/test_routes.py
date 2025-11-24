"""
WooCommerce Test Routes - Manuel test için
"""
from flask import Blueprint, jsonify, request
from models import db, OrderCreated
from datetime import datetime
import json

test_bp = Blueprint('woo_test', __name__, url_prefix='/woo-test')


@test_bp.route('/add-test-order', methods=['GET', 'POST'])
def add_test_order():
    """
    Test için manuel WooCommerce siparişi ekler
    URL: /woo-test/add-test-order
    """
    try:
        # Zaten test siparişi var mı kontrol et
        existing = OrderCreated.query.filter_by(order_number='WOO-TEST-001').first()
        if existing:
            return jsonify({
                'success': False,
                'message': 'Test siparişi zaten mevcut',
                'order_number': 'WOO-TEST-001'
            })
        
        # Test ürünleri
        line_items = [
            {
                'barcode': '8682344524311',  # Örnek barkod
                'product_name': 'Test Ayakkabı - Siyah',
                'quantity': 2,
                'price': 299.90,
                'line_id': 1
            },
            {
                'barcode': '8682344524328',  # Örnek barkod 2
                'product_name': 'Test Ayakkabı - Beyaz',
                'quantity': 1,
                'price': 349.90,
                'line_id': 2
            }
        ]
        
        # OrderCreated kaydı oluştur
        test_order = OrderCreated(
            order_number='WOO-TEST-001',
            order_date=datetime.utcnow(),
            status='processing',
            customer_name='Test',
            customer_surname='Müşteri',
            customer_address='Test Mahallesi, Test Sokak No:1',
            customer_id='test@example.com',
            product_barcode='8682344524311',  # İlk ürün
            product_name='Test Ayakkabı',
            quantity=3,  # Toplam
            amount=949.70,  # (299.90*2) + (349.90*1)
            currency_code='TRY',
            package_number='WOO-TEST-001',
            details=json.dumps(line_items, ensure_ascii=False),
            cargo_provider_name='MNG',
            shipment_package_id=None,
            # Platform bilgisi için özel alan yok, status'a ekleriz veya details'e
        )
        
        db.session.add(test_order)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Test WooCommerce siparişi eklendi!',
            'order_number': 'WOO-TEST-001',
            'instructions': 'Şimdi Sipariş Hazırla sayfasına gidin ve test siparişini görün.'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@test_bp.route('/remove-test-order', methods=['GET', 'POST'])
def remove_test_order():
    """
    Test siparişini siler
    URL: /woo-test/remove-test-order
    """
    try:
        test_order = OrderCreated.query.filter_by(order_number='WOO-TEST-001').first()
        
        if not test_order:
            return jsonify({
                'success': False,
                'message': 'Test siparişi bulunamadı'
            })
        
        db.session.delete(test_order)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Test siparişi silindi'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@test_bp.route('/remove-all-test-orders', methods=['GET', 'POST'])
def remove_all_test_orders():
    """
    Tüm WOO-TEST siparişlerini siler
    URL: /woo-test/remove-all-test-orders
    """
    try:
        # WOO-TEST ile başlayan tüm siparişleri bul
        test_orders = OrderCreated.query.filter(
            OrderCreated.order_number.like('WOO-TEST-%')
        ).all()
        
        count = len(test_orders)
        
        if count == 0:
            return jsonify({
                'success': False,
                'message': 'Test siparişi bulunamadı'
            })
        
        # Hepsini sil
        for order in test_orders:
            db.session.delete(order)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{count} adet test siparişi silindi',
            'deleted_count': count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@test_bp.route('/check-order/<int:order_id>', methods=['GET'])
def check_order(order_id):
    """
    WooCommerce siparişinin OrderCreated'a kaydedilip kaydedilmediğini kontrol eder
    URL: /woo-test/check-order/49792
    """
    try:
        from woocommerce_site.woo_service import WooCommerceService
        
        woo_service = WooCommerceService()
        
        # WooCommerce'ten sipariş çek
        order_data = woo_service.get_order(order_id)
        
        if not order_data:
            return jsonify({
                'success': False,
                'message': 'WooCommerce\'te sipariş bulunamadı'
            })
        
        # OrderCreated'da var mı kontrol et
        order_number = str(order_id)
        existing = OrderCreated.query.filter_by(order_number=order_number).first()
        
        # Durum ve bilgi kontrolü
        status = order_data.get('status', '')
        billing = order_data.get('billing', {})
        
        check_result = {
            'order_id': order_id,
            'woocommerce_status': status,
            'in_order_created': existing is not None,
            'checks': {
                'status_ok': status in ['processing', 'on-hold', 'shipped'],
                'has_first_name': bool(billing.get('first_name', '').strip()),
                'has_last_name': bool(billing.get('last_name', '').strip()),
                'has_phone': bool(billing.get('phone', '').strip()),
                'has_address': bool(billing.get('address_1', '').strip()),
                'has_payment_method': bool(order_data.get('payment_method', '').strip())
            },
            'customer_info': {
                'first_name': billing.get('first_name', ''),
                'last_name': billing.get('last_name', ''),
                'phone': billing.get('phone', ''),
                'address': billing.get('address_1', ''),
                'city': billing.get('city', ''),
                'payment_method': order_data.get('payment_method', '')
            }
        }
        
        # Neden kaydedilmediğini bul
        all_passed = all(check_result['checks'].values())
        
        return jsonify({
            'success': True,
            'result': check_result,
            'should_be_in_created': all_passed,
            'reason': 'Tüm kontroller geçti' if all_passed else 'Bazı kontroller başarısız'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@test_bp.route('/force-add-order/<int:order_id>', methods=['GET', 'POST'])
def force_add_order(order_id):
    """
    WooCommerce siparişini zorla OrderCreated'a ekler
    URL: /woo-test/force-add-order/49792
    """
    try:
        from woocommerce_site.woo_service import WooCommerceService
        import json
        
        woo_service = WooCommerceService()
        
        # Zaten var mı kontrol et
        order_number = str(order_id)
        existing = OrderCreated.query.filter_by(order_number=order_number).first()
        
        if existing:
            return jsonify({
                'success': False,
                'message': f'Sipariş #{order_id} zaten OrderCreated\'da var'
            })
        
        # WooCommerce'ten sipariş çek
        order_data = woo_service.get_order(order_id)
        
        if not order_data:
            return jsonify({
                'success': False,
                'message': 'WooCommerce\'te sipariş bulunamadı'
            })
        
        # OrderCreated'a ekle
        result = woo_service.sync_to_order_created([order_data])
        
        if result > 0:
            return jsonify({
                'success': True,
                'message': f'Sipariş #{order_id} OrderCreated\'a eklendi!',
                'order_number': order_number,
                'next_step': 'Şimdi Sipariş Hazırla sayfasına gidin'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Sipariş eklenemedi. Loglara bakın.',
                'order_data': order_data
            })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
