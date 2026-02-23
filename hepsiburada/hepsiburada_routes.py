"""
Hepsiburada Marketplace Routes - Sipariş, Listeleme ve Ayar sayfaları
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from functools import wraps
from datetime import datetime, timedelta
import logging
from .hepsiburada_service import HepsiburadaService
from .hepsiburada_config import HepsiburadaConfig

logger = logging.getLogger(__name__)

# Blueprint oluştur
hb_bp = Blueprint('hepsiburada', __name__, url_prefix='/hepsiburada')

# Servis instance
hb_service = HepsiburadaService()


def check_hb_config(f):
    """Hepsiburada API ayarlarının yapılıp yapılmadığını kontrol eden decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not HepsiburadaConfig.is_configured():
            return render_template('hepsiburada/config_error.html'), 500
        return f(*args, **kwargs)
    return decorated_function


# ═══════════════════════════════════════════════════════════════════════════════
# ANA SAYFA
# ═══════════════════════════════════════════════════════════════════════════════

@hb_bp.route('/')
def index():
    """Hepsiburada ana sayfa - Dashboard"""
    is_configured = HepsiburadaConfig.is_configured()
    return render_template('hepsiburada/index.html', is_configured=is_configured)


# ═══════════════════════════════════════════════════════════════════════════════
# SİPARİŞLER
# ═══════════════════════════════════════════════════════════════════════════════

@hb_bp.route('/orders')
@check_hb_config
def orders():
    """Ödemesi tamamlanmış sipariş listesi"""
    page = request.args.get('page', 0, type=int)
    limit = request.args.get('limit', 50, type=int)
    offset = page * limit

    orders_data = hb_service.get_new_orders(offset=offset, limit=limit)

    return render_template(
        'hepsiburada/siparisler.html',
        orders=orders_data.get('orders', []),
        total=orders_data.get('total', 0),
        page=page,
        limit=limit,
        page_count=orders_data.get('page_count', 1),
        error=orders_data.get('error'),
    )


@hb_bp.route('/orders/<order_number>')
@check_hb_config
def order_detail(order_number):
    """Sipariş detay sayfası"""
    result = hb_service.get_order_detail(order_number)
    if not result.get('success'):
        flash(f'Sipariş bulunamadı: {result.get("error", "")}', 'danger')
        return redirect(url_for('hepsiburada.orders'))

    return render_template('hepsiburada/siparis_detay.html', order=result['order'])


@hb_bp.route('/packages')
@check_hb_config
def packages():
    """Paket bilgilerini listele"""
    limit = request.args.get('limit', 10, type=int)
    offset = request.args.get('offset', 0, type=int)

    packages_data = hb_service.get_packages(offset=offset, limit=limit)

    return render_template(
        'hepsiburada/paketler.html',
        packages=packages_data.get('packages', []),
        total=packages_data.get('total', 0),
        offset=offset,
        limit=limit,
        error=packages_data.get('error'),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LİSTELEME (ÜRÜNLER / STOK / FİYAT)
# ═══════════════════════════════════════════════════════════════════════════════

@hb_bp.route('/listings')
@check_hb_config
def listings():
    """Listing (envanter) listesi"""
    page = request.args.get('page', 0, type=int)
    limit = request.args.get('limit', 50, type=int)
    search = request.args.get('search', None)
    offset = page * limit

    if search:
        result = hb_service.get_listings(offset=0, limit=50, merchant_sku=search)
        if not result.get('listings'):
            result = hb_service.get_listings(offset=0, limit=50, hbsku=search)
    else:
        result = hb_service.get_listings(offset=offset, limit=limit)

    return render_template(
        'hepsiburada/listeler.html',
        listings=result.get('listings', []),
        total=result.get('total', 0),
        page=page,
        limit=limit,
        search=search,
        error=result.get('error'),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@hb_bp.route('/api/orders')
@check_hb_config
def api_orders():
    """Sipariş listesi API"""
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 50, type=int)
    result = hb_service.get_new_orders(offset=offset, limit=limit)
    return jsonify(result)


@hb_bp.route('/api/order/<order_number>')
@check_hb_config
def api_order_detail(order_number):
    """Sipariş detay API"""
    result = hb_service.get_order_detail(order_number)
    return jsonify(result)


@hb_bp.route('/api/packages')
@check_hb_config
def api_packages():
    """Paket listesi API"""
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 10, type=int)
    result = hb_service.get_packages(offset=offset, limit=limit)
    return jsonify(result)


@hb_bp.route('/api/listings')
@check_hb_config
def api_listings():
    """Listing listesi API"""
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 50, type=int)
    result = hb_service.get_listings(offset=offset, limit=limit)
    return jsonify(result)


@hb_bp.route('/api/update-listing', methods=['POST'])
@check_hb_config
def api_update_listing():
    """Tek listing güncelleme (fiyat/stok)"""
    data = request.get_json()
    hbsku = data.get('hepsiburadaSku')
    merchant_sku = data.get('merchantSku')
    price = data.get('price')
    stock = data.get('stock')
    dispatch_time = data.get('dispatchTime', '3')

    if not (hbsku or merchant_sku):
        return jsonify({'success': False, 'error': 'HepsiburadaSku veya MerchantSku gerekli'}), 400

    listing_update = {}
    if hbsku:
        listing_update['HepsiburadaSku'] = hbsku
    if merchant_sku:
        listing_update['MerchantSku'] = merchant_sku
    if price is not None:
        listing_update['Price'] = str(price).replace('.', ',')
    if stock is not None:
        listing_update['AvailableStock'] = str(int(stock))
    if dispatch_time:
        listing_update['DispatchTime'] = str(dispatch_time)

    result = hb_service.update_listings([listing_update])
    return jsonify(result)


@hb_bp.route('/api/bulk-update-stock', methods=['POST'])
@check_hb_config
def api_bulk_update_stock():
    """Toplu stok güncelleme"""
    data = request.get_json()
    items = data.get('items', [])

    if not items:
        return jsonify({'success': False, 'error': 'Güncellenecek ürün yok'}), 400

    listings_data = []
    for item in items:
        listing = {}
        if item.get('hepsiburadaSku'):
            listing['HepsiburadaSku'] = item['hepsiburadaSku']
        if item.get('merchantSku'):
            listing['MerchantSku'] = item['merchantSku']
        listing['AvailableStock'] = str(int(item.get('stock', 0)))
        if item.get('price'):
            listing['Price'] = str(item['price']).replace('.', ',')
        if item.get('dispatchTime'):
            listing['DispatchTime'] = str(item['dispatchTime'])
        listings_data.append(listing)

    result = hb_service.update_listings(listings_data)
    return jsonify(result)


@hb_bp.route('/api/cancel-item', methods=['POST'])
@check_hb_config
def api_cancel_item():
    """Sipariş kalemi iptal et"""
    data = request.get_json()
    line_item_id = data.get('lineItemId')
    if not line_item_id:
        return jsonify({'success': False, 'error': 'lineItemId gerekli'}), 400

    result = hb_service.cancel_order_item(line_item_id)
    return jsonify(result)


@hb_bp.route('/api/package-items', methods=['POST'])
@check_hb_config
def api_package_items():
    """Kalemleri paketle"""
    data = request.get_json()
    line_item_ids = data.get('lineItemIds', [])
    quantities = data.get('quantities', [])

    if not line_item_ids:
        return jsonify({'success': False, 'error': 'lineItemIds gerekli'}), 400

    result = hb_service.package_items(line_item_ids, quantities)
    return jsonify(result)


@hb_bp.route('/api/unpack', methods=['POST'])
@check_hb_config
def api_unpack():
    """Paket boz"""
    data = request.get_json()
    package_number = data.get('packageNumber')
    if not package_number:
        return jsonify({'success': False, 'error': 'packageNumber gerekli'}), 400

    result = hb_service.unpack_package(package_number)
    return jsonify(result)


@hb_bp.route('/api/fetch-listings', methods=['POST'])
@check_hb_config
def api_fetch_listings():
    """Tüm listingleri çekip cache'le"""
    try:
        result = hb_service.fetch_and_cache_all_listings()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ═══════════════════════════════════════════════════════════════════════════════
# AYARLAR
# ═══════════════════════════════════════════════════════════════════════════════

@hb_bp.route('/settings')
def settings():
    """Hepsiburada ayarları sayfası"""
    return render_template(
        'hepsiburada/ayarlar.html',
        config={
            'is_configured': HepsiburadaConfig.is_configured(),
            'merchant_id': HepsiburadaConfig.MERCHANT_ID[:8] + '...' if HepsiburadaConfig.MERCHANT_ID else 'Ayarlanmamış',
            'environment': HepsiburadaConfig.get_env_label(),
            'order_url': HepsiburadaConfig.get_order_base_url(),
            'listing_url': HepsiburadaConfig.get_listing_base_url(),
        }
    )


@hb_bp.route('/test-connection')
def test_connection():
    """API bağlantı testi"""
    if not HepsiburadaConfig.is_configured():
        return jsonify({
            'success': False,
            'message': 'API ayarları yapılmamış'
        })

    result = hb_service.test_connection()
    return jsonify(result)
