"""
Amazon SP-API Routes - Sipariş ve ürün yönetimi sayfaları
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from functools import wraps
from datetime import datetime, timedelta
import logging
from .amazon_service import AmazonService
from .amazon_config import AmazonConfig

logger = logging.getLogger(__name__)

# Blueprint oluştur
amazon_bp = Blueprint('amazon', __name__, url_prefix='/amazon')

# Servis instance
amazon_service = AmazonService()


def check_amazon_config(f):
    """Amazon API ayarlarının yapılıp yapılmadığını kontrol eden decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not AmazonConfig.is_configured():
            return render_template('amazon/config_error.html'), 500
        return f(*args, **kwargs)
    return decorated_function


# ═══════════════════════════════════════════════════════════════════════════════
# ANA SAYFA
# ═══════════════════════════════════════════════════════════════════════════════

@amazon_bp.route('/')
def index():
    """Amazon ana sayfa - Dashboard"""
    is_configured = AmazonConfig.is_configured()
    return render_template('amazon/index.html', is_configured=is_configured)


# ═══════════════════════════════════════════════════════════════════════════════
# SİPARİŞLER
# ═══════════════════════════════════════════════════════════════════════════════

@amazon_bp.route('/orders')
@check_amazon_config
def orders():
    """Sipariş listesi sayfası"""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', None)
    days = request.args.get('days', 7, type=int)
    
    # Siparişleri çek
    orders_data = amazon_service.get_orders(days_back=days, status=status)
    
    return render_template(
        'amazon/siparisler.html',
        orders=orders_data.get('orders', []),
        total=orders_data.get('total', 0),
        page=page,
        status=status,
        days=days
    )


@amazon_bp.route('/orders/<order_id>')
@check_amazon_config
def order_detail(order_id):
    """Sipariş detay sayfası"""
    order = amazon_service.get_order_detail(order_id)
    if not order:
        flash('Sipariş bulunamadı', 'danger')
        return redirect(url_for('amazon.orders'))
    
    return render_template('amazon/siparis_detay.html', order=order)


# ═══════════════════════════════════════════════════════════════════════════════
# ÜRÜNLER
# ═══════════════════════════════════════════════════════════════════════════════

@amazon_bp.route('/products')
@check_amazon_config
def products():
    """Ürün listesi sayfası"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', None)
    
    products_data = amazon_service.get_products(page=page, search=search)
    
    return render_template(
        'amazon/urunler.html',
        products=products_data.get('products', []),
        total=products_data.get('total', 0),
        page=page,
        per_page=products_data.get('per_page', 20),
        total_pages=products_data.get('total_pages', 1),
        search=search,
        error=products_data.get('error')
    )


# ═══════════════════════════════════════════════════════════════════════════════
# STOK YÖNETİMİ
# ═══════════════════════════════════════════════════════════════════════════════

@amazon_bp.route('/inventory')
@check_amazon_config
def inventory():
    """Stok yönetimi sayfası"""
    inventory_data = amazon_service.get_inventory()
    
    return render_template(
        'amazon/stok.html',
        inventory=inventory_data.get('items', []),
        total=inventory_data.get('total', 0)
    )


@amazon_bp.route('/inventory/update', methods=['POST'])
@check_amazon_config
def update_inventory():
    """Stok güncelleme API endpoint"""
    data = request.get_json()
    sku = data.get('sku')
    quantity = data.get('quantity')
    
    if not sku or quantity is None:
        return jsonify({'success': False, 'error': 'SKU ve miktar gerekli'}), 400
    
    result = amazon_service.update_inventory(sku, quantity)
    
    return jsonify({
        'success': result,
        'message': 'Stok güncellendi' if result else 'Stok güncellenemedi'
    })


# ═══════════════════════════════════════════════════════════════════════════════
# RAPORLAR
# ═══════════════════════════════════════════════════════════════════════════════

@amazon_bp.route('/reports')
@check_amazon_config
def reports():
    """Rapor sayfası"""
    return render_template('amazon/raporlar.html')


@amazon_bp.route('/reports/sales')
@check_amazon_config
def sales_report():
    """Satış raporu"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    report = amazon_service.get_sales_report(start_date, end_date)
    
    return jsonify(report)


# ═══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@amazon_bp.route('/api/orders')
@check_amazon_config
def api_orders():
    """Sipariş listesi API"""
    days = request.args.get('days', 7, type=int)
    status = request.args.get('status', None)
    
    orders = amazon_service.get_orders(days_back=days, status=status)
    return jsonify(orders)


@amazon_bp.route('/api/products')
@check_amazon_config
def api_products():
    """Ürün listesi API"""
    page = request.args.get('page', 1, type=int)
    products = amazon_service.get_products(page=page)
    return jsonify(products)


@amazon_bp.route('/api/sync-orders', methods=['POST'])
@check_amazon_config
def sync_orders():
    """Siparişleri senkronize et"""
    result = amazon_service.sync_orders()
    return jsonify(result)


@amazon_bp.route('/api/sync-inventory', methods=['POST'])
@check_amazon_config
def sync_inventory():
    """Stok senkronizasyonu"""
    result = amazon_service.sync_inventory()
    return jsonify(result)


@amazon_bp.route('/api/push-stock', methods=['POST'])
@check_amazon_config
def push_stock():
    """CentralStock'tan Amazon'a stok gönder (arka planda çalışır)"""
    import threading
    from flask import current_app
    
    def run_push():
        """Arka plan thread'inde stok gönder"""
        with current_app._get_current_object().app_context():
            try:
                result = amazon_service.push_central_stock()
                if result.get('success'):
                    logger.info(f"[AMAZON] ✅ Stok gönderimi tamamlandı: {result.get('success_count')}/{result.get('items_count')}")
                else:
                    logger.error(f"[AMAZON] ❌ Stok gönderimi başarısız: {result.get('error')}")
            except Exception as e:
                logger.error(f"[AMAZON] ❌ Kritik hata: {e}")
    
    # Arka plan thread'inde başlat
    thread = threading.Thread(target=run_push, name="AmazonPushStock", daemon=True)
    thread.start()
    
    return jsonify({
        'success': True,
        'message': 'Stok gönderimi arka planda başlatıldı. İşlem birkaç dakika sürebilir.',
        'background': True
    })


# ═══════════════════════════════════════════════════════════════════════════════
# AYARLAR
# ═══════════════════════════════════════════════════════════════════════════════

@amazon_bp.route('/settings')
def settings():
    """Amazon ayarları sayfası"""
    return render_template(
        'amazon/ayarlar.html',
        config={
            'is_configured': AmazonConfig.is_configured(),
            'marketplace_id': AmazonConfig.MARKETPLACE_ID,
            'seller_id': AmazonConfig.SELLER_ID[:8] + '...' if AmazonConfig.SELLER_ID else 'Ayarlanmamış',
            'region': AmazonConfig.AWS_REGION
        }
    )


@amazon_bp.route('/test-connection')
def test_connection():
    """API bağlantı testi"""
    if not AmazonConfig.is_configured():
        return jsonify({
            'success': False,
            'message': 'API ayarları yapılmamış'
        })
    
    result = amazon_service.test_connection()
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════════════════════
# ASIN EŞLEŞTİRME
# ═══════════════════════════════════════════════════════════════════════════════

@amazon_bp.route('/matching')
@check_amazon_config
def matching():
    """Amazon ASIN eşleştirme sayfası"""
    from models import Product, db
    
    # Amazon ürünlerini çek (cache'den veya API'dan)
    amazon_products = amazon_service.get_all_products_cached()
    
    # Eşleştirilmiş ürünleri bul
    matched_products = Product.query.filter(Product.amazon_asin.isnot(None)).all()
    matched_asins = {p.amazon_asin: p.barcode for p in matched_products}
    
    # Eşleştirme bilgilerini ekle
    for product in amazon_products:
        asin = product.get('asin')
        if asin in matched_asins:
            product['matched_barcode'] = matched_asins[asin]
        else:
            product['matched_barcode'] = None
    
    # İstatistikler
    total = len(amazon_products)
    matched_count = len([p for p in amazon_products if p.get('matched_barcode')])
    unmatched_count = total - matched_count
    match_rate = round((matched_count / total * 100) if total > 0 else 0, 1)
    
    # Tüm barkodlar (autocomplete için)
    all_barcodes = [p.barcode for p in Product.query.with_entities(Product.barcode).limit(5000).all()]
    
    return render_template(
        'amazon/eslestirme.html',
        amazon_products=amazon_products,
        matched_count=matched_count,
        unmatched_count=unmatched_count,
        match_rate=match_rate,
        all_barcodes=all_barcodes
    )


@amazon_bp.route('/api/fetch-products', methods=['POST'])
@check_amazon_config
def api_fetch_products():
    """Amazon'dan tüm ürünleri çek ve cache'le"""
    try:
        result = amazon_service.fetch_and_cache_all_products()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@amazon_bp.route('/api/auto-match', methods=['POST'])
@check_amazon_config
def api_auto_match():
    """SKU-barkod benzerliğine göre otomatik eşleştir"""
    from models import Product, db
    
    try:
        amazon_products = amazon_service.get_all_products_cached()
        
        # Tüm ürünleri barkod ve product_main_id ile indexle
        products = Product.query.all()
        barcode_map = {p.barcode.lower(): p for p in products if p.barcode}
        main_id_map = {p.product_main_id.lower(): p for p in products if p.product_main_id}
        
        matched = 0
        for ap in amazon_products:
            asin = ap.get('asin')
            sku = ap.get('sku', '').lower().strip()
            
            if not asin or not sku:
                continue
            
            # Zaten eşleştirilmiş mi?
            existing = Product.query.filter_by(amazon_asin=asin).first()
            if existing:
                continue
            
            # SKU ile direkt eşleştir
            if sku in barcode_map:
                product = barcode_map[sku]
                product.amazon_asin = asin
                product.amazon_sku = ap.get('sku')
                product.amazon_status = ap.get('status')
                product.amazon_last_sync = datetime.now()
                matched += 1
                continue
            
            # product_main_id ile eşleştir
            if sku in main_id_map:
                product = main_id_map[sku]
                product.amazon_asin = asin
                product.amazon_sku = ap.get('sku')
                product.amazon_status = ap.get('status')
                product.amazon_last_sync = datetime.now()
                matched += 1
                continue
            
            # SKU parçalarıyla eşleştir (örn: "ABC-123-XL" -> "ABC-123")
            sku_parts = sku.replace('-', ' ').replace('_', ' ').split()
            for part in sku_parts:
                if len(part) >= 5 and part in barcode_map:
                    product = barcode_map[part]
                    product.amazon_asin = asin
                    product.amazon_sku = ap.get('sku')
                    product.amazon_status = ap.get('status')
                    product.amazon_last_sync = datetime.now()
                    matched += 1
                    break
        
        db.session.commit()
        return jsonify({'success': True, 'matched': matched})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@amazon_bp.route('/api/match-product', methods=['POST'])
@check_amazon_config
def api_match_product():
    """Tek ürün eşleştir"""
    from models import Product, db
    
    try:
        data = request.get_json()
        asin = data.get('asin')
        barcode = data.get('barcode')
        
        if not asin or not barcode:
            return jsonify({'success': False, 'error': 'ASIN ve barkod gerekli'})
        
        # Ürünü bul
        product = Product.query.filter_by(barcode=barcode).first()
        if not product:
            return jsonify({'success': False, 'error': 'Ürün bulunamadı'})
        
        # Amazon bilgilerini cache'den al
        amazon_products = amazon_service.get_all_products_cached()
        amazon_product = next((p for p in amazon_products if p.get('asin') == asin), None)
        
        # Eşleştir
        product.amazon_asin = asin
        product.amazon_sku = amazon_product.get('sku') if amazon_product else None
        product.amazon_status = amazon_product.get('status') if amazon_product else None
        product.amazon_last_sync = datetime.now()
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@amazon_bp.route('/api/unmatch-product', methods=['POST'])
@check_amazon_config
def api_unmatch_product():
    """Ürün eşleştirmesini kaldır"""
    from models import Product, db
    
    try:
        data = request.get_json()
        asin = data.get('asin')
        
        if not asin:
            return jsonify({'success': False, 'error': 'ASIN gerekli'})
        
        product = Product.query.filter_by(amazon_asin=asin).first()
        if product:
            product.amazon_asin = None
            product.amazon_sku = None
            product.amazon_status = None
            product.amazon_last_sync = None
            db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@amazon_bp.route('/api/bulk-match', methods=['POST'])
@check_amazon_config
def api_bulk_match():
    """
    Toplu barkod eşleştirme
    Girilen barkodları Amazon SKU'larıyla karşılaştırır ve eşleştirir
    """
    from models import Product, db
    import pandas as pd
    import os
    
    try:
        data = request.get_json()
        barcodes = data.get('barcodes', [])
        
        if not barcodes:
            return jsonify({'success': False, 'error': 'Barkod listesi boş'})
        
        # Excel dosyasından mapping oluştur
        excel_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Ürünleriniz_22.12.2025-15.43.xlsx')
        
        # Excel varsa oku, yoksa cache'den Amazon ürünlerini al
        barcode_to_sku = {}
        
        if os.path.exists(excel_path):
            df = pd.read_excel(excel_path)
            for _, row in df.iterrows():
                stok_kodu = str(row.get('Tedarikçi Stok Kodu', '')).strip()
                barkod = str(row.get('Barkod', '')).strip()
                if barkod and stok_kodu and barkod != 'nan':
                    barcode_to_sku[barkod] = stok_kodu
        
        # Amazon ürünlerini al
        amazon_products = amazon_service.get_all_products_cached()
        sku_to_amazon = {p.get('sku', '').lower().strip(): p for p in amazon_products}
        
        results = []
        matched = 0
        not_found = 0
        already_matched = 0
        no_amazon = 0
        
        for barcode in barcodes:
            barcode = str(barcode).strip()
            if not barcode:
                continue
            
            # Ürünü veritabanında bul
            product = Product.query.filter_by(barcode=barcode).first()
            
            if not product:
                results.append({'barcode': barcode, 'status': 'not_found'})
                not_found += 1
                continue
            
            # Zaten eşleşik mi?
            if product.amazon_asin:
                results.append({'barcode': barcode, 'status': 'already', 'amazon_sku': product.amazon_sku})
                already_matched += 1
                continue
            
            # Excel'den SKU bul
            sku = barcode_to_sku.get(barcode, '')
            
            # Amazon'da bu SKU var mı?
            amazon_product = sku_to_amazon.get(sku.lower().strip()) if sku else None
            
            if not amazon_product:
                # Doğrudan barkod ile dene
                amazon_product = sku_to_amazon.get(barcode.lower().strip())
            
            if amazon_product:
                product.amazon_asin = amazon_product.get('asin')
                product.amazon_sku = amazon_product.get('sku')
                product.amazon_status = amazon_product.get('status', 'Active')
                product.amazon_last_sync = datetime.now()
                
                results.append({
                    'barcode': barcode, 
                    'status': 'matched', 
                    'amazon_sku': amazon_product.get('sku'),
                    'asin': amazon_product.get('asin')
                })
                matched += 1
            else:
                results.append({'barcode': barcode, 'status': 'no_amazon'})
                no_amazon += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'matched': matched,
            'not_found': not_found,
            'already_matched': already_matched,
            'no_amazon': no_amazon,
            'total': len(barcodes),
            'results': results
        })
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})
