# -*- coding: utf-8 -*-
"""
OpenClaw Agent API — Güllü Shoes Panel
=======================================
Agent'ın tüm panel işlemlerini yapabilmesi için REST API endpoint'leri.

Kimlik doğrulama: X-Agent-Key header'ı ile (AGENT_API_KEY env variable).
Prefix: /agent/api/v1/
"""

import os
import json
import uuid
import logging
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, request, jsonify
from sqlalchemy import func, or_, desc, asc

from models import (
    db,
    Product, CentralStock, RafUrun, Raf,
    OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled,
    OrderReadyToShip, OrderArchived,
    Degisim,
    ReturnOrder, ReturnProduct, Return,
    YeniSiparis, SiparisUrun,
    Kasa, AnaKasa, AnaKasaIslem, KasaKategori, Odeme, KasaDurum,
    BarcodeAlias,
    Rapor, User, UserLog,
)
from stock_management import sync_central_stock

logger = logging.getLogger(__name__)

agent_api = Blueprint('agent_api', __name__, url_prefix='/agent/api/v1')

# ══════════════════════════════════════════════════════════════════════════════
#  AUTH MIDDLEWARE
# ══════════════════════════════════════════════════════════════════════════════
AGENT_API_KEY = os.getenv('AGENT_API_KEY', 'gullu-agent-secret-key-2026')


def require_agent_key(f):
    """X-Agent-Key header kontrolü."""
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-Agent-Key', '')
        if key != AGENT_API_KEY:
            return jsonify(success=False, error='Yetkisiz erişim. Geçerli X-Agent-Key gerekli.'), 401
        return f(*args, **kwargs)
    return decorated


# ══════════════════════════════════════════════════════════════════════════════
#  YARDIMCI FONKSİYONLAR
# ══════════════════════════════════════════════════════════════════════════════
ORDER_TABLES = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled]

STATUS_LABEL = {
    OrderCreated: 'Oluşturuldu',
    OrderPicking: 'Hazırlanıyor',
    OrderShipped: 'Kargoda',
    OrderDelivered: 'Teslim Edildi',
    OrderCancelled: 'İptal',
}


def _order_to_dict(order, table_cls=None):
    """Sipariş objesini dict'e çevir."""
    details = []
    if order.details:
        try:
            details = json.loads(order.details) if isinstance(order.details, str) else order.details
        except Exception:
            details = []

    return {
        'id': order.id,
        'order_number': order.order_number,
        'order_date': order.order_date.isoformat() if order.order_date else None,
        'status': STATUS_LABEL.get(table_cls, order.status or ''),
        'raw_status': order.status,
        'customer_name': order.customer_name,
        'customer_surname': order.customer_surname,
        'customer_address': getattr(order, 'customer_address', None),
        'merchant_sku': order.merchant_sku,
        'product_barcode': order.product_barcode,
        'product_name': order.product_name,
        'product_code': order.product_code,
        'product_size': order.product_size,
        'product_color': order.product_color,
        'product_main_id': order.product_main_id,
        'amount': float(order.amount) if order.amount else None,
        'discount': float(order.discount) if order.discount else None,
        'commission': float(order.commission) if order.commission else None,
        'cargo_tracking_number': order.cargo_tracking_number,
        'cargo_provider_name': order.cargo_provider_name,
        'cargo_tracking_link': getattr(order, 'cargo_tracking_link', None),
        'source': getattr(order, 'source', 'trendyol'),
        'details': details,
    }


def _product_to_dict(p):
    """Ürün objesini dict'e çevir."""
    return {
        'barcode': p.barcode,
        'title': p.title,
        'product_main_id': p.product_main_id,
        'size': getattr(p, 'size', None),
        'color': getattr(p, 'color', None),
        'brand': getattr(p, 'brand', None),
        'category_name': getattr(p, 'category_name', None),
        'sale_price': float(p.sale_price) if p.sale_price else None,
        'list_price': float(p.list_price) if p.list_price else None,
        'cost_usd': float(p.cost_usd) if p.cost_usd else None,
        'cost_try': float(p.cost_try) if p.cost_try else None,
        'quantity': p.quantity,
        'on_sale': getattr(p, 'on_sale', None),
        'archived': getattr(p, 'archived', False),
        'locked': getattr(p, 'locked', False),
    }


def _degisim_to_dict(d):
    """Değişim objesini dict'e çevir."""
    urunler = []
    if d.urunler_json:
        try:
            urunler = json.loads(d.urunler_json)
        except Exception:
            urunler = []
    return {
        'id': d.id,
        'degisim_no': d.degisim_no,
        'siparis_no': d.siparis_no,
        'ad': d.ad,
        'soyad': d.soyad,
        'adres': d.adres,
        'telefon_no': d.telefon_no,
        'degisim_tarihi': d.degisim_tarihi.isoformat() if d.degisim_tarihi else None,
        'degisim_durumu': d.degisim_durumu,
        'kargo_kodu': d.kargo_kodu,
        'degisim_nedeni': d.degisim_nedeni,
        'musteri_kargo_takip': d.musteri_kargo_takip,
        'urunler': urunler,
    }


def _find_order_across_tables(order_number):
    """Sipariş numarasını tüm tablolarda ara."""
    for table_cls in ORDER_TABLES:
        orders = table_cls.query.filter_by(order_number=order_number).all()
        if orders:
            return orders, table_cls
    return [], None


# ══════════════════════════════════════════════════════════════════════════════
#  1. SİPARİŞ ENDPOİNT'LERİ
# ══════════════════════════════════════════════════════════════════════════════

@agent_api.route('/orders', methods=['GET'])
@require_agent_key
def list_orders():
    """Siparişleri listele.

    Query params:
      - status: Oluşturuldu | Hazırlanıyor | Kargoda | Teslim Edildi | İptal
      - search: sipariş no, müşteri adı, barkod ile arama
      - page (default=1), per_page (default=50)
      - start_date, end_date: YYYY-MM-DD formatında tarih filtresi
      - sort: date_asc | date_desc (default: date_desc)
    """
    status_filter = request.args.get('status', '').strip()
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    sort = request.args.get('sort', 'date_desc')

    status_map = {
        'Oluşturuldu': [OrderCreated],
        'Hazırlanıyor': [OrderPicking],
        'Kargoda': [OrderShipped],
        'Teslim Edildi': [OrderDelivered],
        'İptal': [OrderCancelled],
    }

    tables = status_map.get(status_filter, ORDER_TABLES)
    all_results = []

    for table_cls in tables:
        q = table_cls.query

        if search:
            q = q.filter(or_(
                table_cls.order_number.ilike(f'%{search}%'),
                table_cls.customer_name.ilike(f'%{search}%'),
                table_cls.customer_surname.ilike(f'%{search}%'),
                table_cls.product_barcode.ilike(f'%{search}%'),
                table_cls.merchant_sku.ilike(f'%{search}%'),
            ))

        if start_date:
            try:
                q = q.filter(table_cls.order_date >= datetime.strptime(start_date, '%Y-%m-%d'))
            except ValueError:
                pass
        if end_date:
            try:
                q = q.filter(table_cls.order_date <= datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1))
            except ValueError:
                pass

        for order in q.all():
            all_results.append(_order_to_dict(order, table_cls))

    # Sıralama
    reverse = sort != 'date_asc'
    all_results.sort(key=lambda x: x.get('order_date') or '', reverse=reverse)

    # Sayfalama
    total = len(all_results)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = all_results[start:end]

    return jsonify(
        success=True,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page,
        orders=paginated,
    )


@agent_api.route('/orders/<order_number>', methods=['GET'])
@require_agent_key
def get_order(order_number):
    """Tek sipariş detayını getir (tüm tablolarda arar)."""
    orders, table_cls = _find_order_across_tables(order_number)
    if not orders:
        return jsonify(success=False, error='Sipariş bulunamadı.'), 404

    return jsonify(
        success=True,
        order_count=len(orders),
        orders=[_order_to_dict(o, table_cls) for o in orders],
    )


@agent_api.route('/orders/stats', methods=['GET'])
@require_agent_key
def order_stats():
    """Sipariş istatistikleri — durumlara göre sayılar."""
    stats = {}
    for table_cls in ORDER_TABLES:
        label = STATUS_LABEL.get(table_cls, table_cls.__tablename__)
        stats[label] = table_cls.query.count()

    stats['Toplam'] = sum(stats.values())
    return jsonify(success=True, stats=stats)


# ══════════════════════════════════════════════════════════════════════════════
#  2. ÜRÜN ENDPOİNT'LERİ
# ══════════════════════════════════════════════════════════════════════════════

@agent_api.route('/products', methods=['GET'])
@require_agent_key
def list_products():
    """Ürünleri listele.

    Query params:
      - search: barkod, başlık, model kodu ile arama
      - model: product_main_id filtresi
      - color, size, brand: filtreler
      - in_stock: true ise sadece stokta olanlar
      - archived: true/false (default: false — arşivlenmemişler)
      - page (default=1), per_page (default=50)
      - sort: title | price_asc | price_desc | barcode
    """
    search = request.args.get('search', '').strip()
    model = request.args.get('model', '').strip()
    color = request.args.get('color', '').strip()
    size = request.args.get('size', '').strip()
    brand = request.args.get('brand', '').strip()
    in_stock = request.args.get('in_stock', '').lower() == 'true'
    archived = request.args.get('archived', 'false').lower() == 'true'
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)
    sort = request.args.get('sort', 'title')

    q = Product.query

    if not archived:
        q = q.filter(or_(Product.archived == False, Product.archived == None))

    if search:
        q = q.filter(or_(
            Product.barcode.ilike(f'%{search}%'),
            Product.title.ilike(f'%{search}%'),
            Product.product_main_id.ilike(f'%{search}%'),
        ))

    if model:
        q = q.filter(Product.product_main_id.ilike(f'%{model}%'))
    if color:
        q = q.filter(Product.color.ilike(f'%{color}%'))
    if size:
        q = q.filter(Product.size == size)
    if brand:
        q = q.filter(Product.brand.ilike(f'%{brand}%'))

    if in_stock:
        stocked = db.session.query(CentralStock.barcode).filter(CentralStock.qty > 0).subquery()
        q = q.filter(Product.barcode.in_(db.session.query(stocked.c.barcode)))

    sort_map = {
        'title': Product.title.asc(),
        'price_asc': Product.sale_price.asc(),
        'price_desc': Product.sale_price.desc(),
        'barcode': Product.barcode.asc(),
    }
    q = q.order_by(sort_map.get(sort, Product.title.asc()))

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify(
        success=True,
        total=pagination.total,
        page=page,
        per_page=per_page,
        total_pages=pagination.pages,
        products=[_product_to_dict(p) for p in pagination.items],
    )


@agent_api.route('/products/<barcode>', methods=['GET'])
@require_agent_key
def get_product(barcode):
    """Tek ürün detayı + stok bilgisi."""
    product = Product.query.get(barcode)
    if not product:
        return jsonify(success=False, error='Ürün bulunamadı.'), 404

    # Stok bilgisi
    cs = CentralStock.query.get(barcode)
    stock_qty = cs.qty if cs else 0

    # Raf detayları
    raf_items = RafUrun.query.filter_by(urun_barkodu=barcode).filter(RafUrun.adet > 0).all()
    shelves = [{'raf_kodu': r.raf_kodu, 'adet': r.adet} for r in raf_items]

    # Alias bilgisi
    aliases = BarcodeAlias.query.filter_by(main_barcode=barcode).all()
    alias_list = [a.alias_barcode for a in aliases]

    data = _product_to_dict(product)
    data['stock'] = {
        'total': stock_qty,
        'shelves': shelves,
    }
    data['aliases'] = alias_list

    return jsonify(success=True, product=data)


@agent_api.route('/products/models', methods=['GET'])
@require_agent_key
def list_models():
    """Benzersiz model kodlarını listele (product_main_id)."""
    search = request.args.get('search', '').strip()

    q = db.session.query(
        Product.product_main_id,
        func.count(Product.barcode).label('variant_count'),
        func.min(Product.sale_price).label('min_price'),
        func.max(Product.sale_price).label('max_price'),
    ).filter(
        Product.product_main_id != None,
        Product.product_main_id != '',
        or_(Product.archived == False, Product.archived == None),
    ).group_by(Product.product_main_id)

    if search:
        q = q.filter(Product.product_main_id.ilike(f'%{search}%'))

    q = q.order_by(Product.product_main_id.asc())
    results = q.all()

    models = [{
        'product_main_id': r.product_main_id,
        'variant_count': r.variant_count,
        'min_price': float(r.min_price) if r.min_price else None,
        'max_price': float(r.max_price) if r.max_price else None,
    } for r in results]

    return jsonify(success=True, total=len(models), models=models)


# ══════════════════════════════════════════════════════════════════════════════
#  3. STOK ENDPOİNT'LERİ
# ══════════════════════════════════════════════════════════════════════════════

@agent_api.route('/stock', methods=['GET'])
@require_agent_key
def list_stock():
    """Stok listesi.

    Query params:
      - search: barkod ile arama
      - min_qty, max_qty: stok miktarı filtresi
      - zero_stock: true ise sadece sıfır stoklular
      - page (default=1), per_page (default=100)
    """
    search = request.args.get('search', '').strip()
    min_qty = request.args.get('min_qty', type=int)
    max_qty = request.args.get('max_qty', type=int)
    zero_stock = request.args.get('zero_stock', '').lower() == 'true'
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 100, type=int), 500)

    q = db.session.query(CentralStock, Product).outerjoin(
        Product, CentralStock.barcode == Product.barcode
    )

    if search:
        q = q.filter(CentralStock.barcode.ilike(f'%{search}%'))
    if zero_stock:
        q = q.filter(CentralStock.qty == 0)
    else:
        if min_qty is not None:
            q = q.filter(CentralStock.qty >= min_qty)
        if max_qty is not None:
            q = q.filter(CentralStock.qty <= max_qty)

    q = q.order_by(CentralStock.barcode.asc())
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for cs, product in pagination.items:
        items.append({
            'barcode': cs.barcode,
            'qty': cs.qty,
            'updated_at': cs.updated_at.isoformat() if cs.updated_at else None,
            'product_title': product.title if product else None,
            'product_main_id': product.product_main_id if product else None,
            'color': product.color if product else None,
            'size': product.size if product else None,
        })

    return jsonify(
        success=True,
        total=pagination.total,
        page=page,
        per_page=per_page,
        total_pages=pagination.pages,
        items=items,
    )


@agent_api.route('/stock/<barcode>', methods=['GET'])
@require_agent_key
def get_stock(barcode):
    """Tek barkod stok detayı (merkez + raf bazlı dağılım)."""
    cs = CentralStock.query.get(barcode)
    total_qty = cs.qty if cs else 0

    raf_items = RafUrun.query.filter_by(urun_barkodu=barcode).filter(RafUrun.adet > 0).all()
    shelves = [{'raf_kodu': r.raf_kodu, 'adet': r.adet} for r in raf_items]

    product = Product.query.get(barcode)

    return jsonify(
        success=True,
        barcode=barcode,
        total_qty=total_qty,
        shelves=shelves,
        product_title=product.title if product else None,
        product_main_id=product.product_main_id if product else None,
    )


@agent_api.route('/stock/summary', methods=['GET'])
@require_agent_key
def stock_summary():
    """Genel stok özeti."""
    total_products = Product.query.filter(
        or_(Product.archived == False, Product.archived == None)
    ).count()

    total_stock = db.session.query(func.coalesce(func.sum(CentralStock.qty), 0)).scalar()
    total_stock = int(total_stock)

    zero_stock_count = CentralStock.query.filter(CentralStock.qty == 0).count()

    in_stock_count = CentralStock.query.filter(CentralStock.qty > 0).count()

    # Model bazlı stok
    model_stock = db.session.query(
        Product.product_main_id,
        func.sum(CentralStock.qty).label('total'),
    ).join(
        CentralStock, Product.barcode == CentralStock.barcode
    ).filter(
        Product.product_main_id != None,
        Product.product_main_id != '',
    ).group_by(Product.product_main_id).order_by(desc('total')).limit(20).all()

    top_models = [{'model': r.product_main_id, 'total_stock': int(r.total)} for r in model_stock]

    return jsonify(
        success=True,
        total_products=total_products,
        total_stock=total_stock,
        in_stock_count=in_stock_count,
        zero_stock_count=zero_stock_count,
        top_models=top_models,
    )


@agent_api.route('/stock/sync/<barcode>', methods=['POST'])
@require_agent_key
def sync_stock(barcode):
    """Tek barkod için CentralStock'u raflarla senkronize et."""
    try:
        new_qty = sync_central_stock(barcode, commit=True)
        db.session.commit()
        return jsonify(success=True, barcode=barcode, new_qty=new_qty)
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500


# ══════════════════════════════════════════════════════════════════════════════
#  4. DEĞİŞİM (EXCHANGE) ENDPOİNT'LERİ
# ══════════════════════════════════════════════════════════════════════════════

@agent_api.route('/exchanges', methods=['GET'])
@require_agent_key
def list_exchanges():
    """Değişim taleplerini listele.

    Query params:
      - status: Oluşturuldu | Kargoda | Tamamlandı | İptal vb.
      - search: sipariş no, ad/soyad, değişim no ile arama
      - start_date, end_date: YYYY-MM-DD
      - page (default=1), per_page (default=50)
    """
    status = request.args.get('status', '').strip()
    search = request.args.get('search', '').strip()
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)

    q = Degisim.query

    if status:
        q = q.filter(Degisim.degisim_durumu == status)
    if search:
        q = q.filter(or_(
            Degisim.degisim_no.ilike(f'%{search}%'),
            Degisim.siparis_no.ilike(f'%{search}%'),
            Degisim.ad.ilike(f'%{search}%'),
            Degisim.soyad.ilike(f'%{search}%'),
        ))
    if start_date:
        try:
            q = q.filter(Degisim.degisim_tarihi >= datetime.strptime(start_date, '%Y-%m-%d'))
        except ValueError:
            pass
    if end_date:
        try:
            q = q.filter(Degisim.degisim_tarihi <= datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1))
        except ValueError:
            pass

    q = q.order_by(Degisim.degisim_tarihi.desc())
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify(
        success=True,
        total=pagination.total,
        page=page,
        per_page=per_page,
        total_pages=pagination.pages,
        exchanges=[_degisim_to_dict(d) for d in pagination.items],
    )


@agent_api.route('/exchanges/<degisim_no>', methods=['GET'])
@require_agent_key
def get_exchange(degisim_no):
    """Tek değişim detayı."""
    d = Degisim.query.filter_by(degisim_no=degisim_no).first()
    if not d:
        return jsonify(success=False, error='Değişim bulunamadı.'), 404
    return jsonify(success=True, exchange=_degisim_to_dict(d))


@agent_api.route('/exchanges', methods=['POST'])
@require_agent_key
def create_exchange():
    """Yeni değişim talebi oluştur.

    JSON body:
    {
      "siparis_no": "123456",
      "ad": "Ali",
      "soyad": "Veli",
      "adres": "...",
      "telefon_no": "05xx...",
      "degisim_nedeni": "Beden uymuyor",
      "urunler": [
        {"barkod": "ABC123", "model_kodu": "GLL001", "renk": "Siyah", "beden": "38", "adet": 1}
      ]
    }
    """
    data = request.get_json(silent=True) or {}

    required = ['siparis_no', 'ad', 'soyad', 'adres', 'urunler']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify(success=False, error=f'Eksik alanlar: {", ".join(missing)}'), 400

    urunler = data['urunler']
    if not isinstance(urunler, list) or len(urunler) == 0:
        return jsonify(success=False, error='En az 1 ürün gerekli.'), 400

    try:
        from degisim import allocate_from_shelves_and_decrement_central, generate_kargo_kodu

        urunler_listesi = []
        toplam_tahsis = 0

        for item in urunler:
            barkod = (item.get('barkod') or '').strip()
            adet = max(1, int(item.get('adet', 1)))

            alloc = allocate_from_shelves_and_decrement_central(barkod, qty=adet)
            toplam_tahsis += alloc['allocated']

            raf_kodu_gosterim = ', '.join([rk for rk in alloc['shelf_codes'] if rk]) if alloc['shelf_codes'] else None

            urunler_listesi.append({
                'barkod': barkod,
                'model_kodu': item.get('model_kodu', ''),
                'renk': item.get('renk', ''),
                'beden': item.get('beden', ''),
                'adet': adet,
                'raf_kodlari': alloc['shelf_codes'],
                'raf_kodu': raf_kodu_gosterim,
                'tahsis_edilen': alloc['allocated'],
            })

        degisim_kaydi = Degisim(
            degisim_no=str(uuid.uuid4()),
            siparis_no=data['siparis_no'],
            ad=data['ad'],
            soyad=data['soyad'],
            adres=data['adres'],
            telefon_no=data.get('telefon_no', ''),
            degisim_tarihi=datetime.now(),
            degisim_durumu='Oluşturuldu',
            kargo_kodu=generate_kargo_kodu(),
            degisim_nedeni=data.get('degisim_nedeni', ''),
            urunler_json=json.dumps(urunler_listesi, ensure_ascii=False),
            musteri_kargo_takip=None,
        )

        db.session.add(degisim_kaydi)
        db.session.commit()

        return jsonify(
            success=True,
            message='Değişim talebi oluşturuldu.',
            degisim_no=degisim_kaydi.degisim_no,
            kargo_kodu=degisim_kaydi.kargo_kodu,
            toplam_tahsis=toplam_tahsis,
            exchange=_degisim_to_dict(degisim_kaydi),
        ), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f'Agent API: Değişim oluşturma hatası: {e}', exc_info=True)
        return jsonify(success=False, error=str(e)), 500


@agent_api.route('/exchanges/<degisim_no>/status', methods=['PUT'])
@require_agent_key
def update_exchange_status(degisim_no):
    """Değişim durumunu güncelle.

    JSON body:
    {
      "status": "Kargoda",
      "musteri_kargo_takip": "TRACK123"  // opsiyonel
    }
    """
    data = request.get_json(silent=True) or {}
    new_status = data.get('status', '').strip()

    if not new_status:
        return jsonify(success=False, error='status alanı gerekli.'), 400

    rec = Degisim.query.filter_by(degisim_no=degisim_no).first()
    if not rec:
        return jsonify(success=False, error='Değişim bulunamadı.'), 404

    musteri_kargo_takip = data.get('musteri_kargo_takip', '').strip()

    if not (rec.musteri_kargo_takip or musteri_kargo_takip):
        return jsonify(
            success=False,
            error='Müşteri kargo takip numarası olmadan durum güncellenemez.',
            need_tracking=True,
        ), 400

    if musteri_kargo_takip:
        rec.musteri_kargo_takip = musteri_kargo_takip

    old_status = rec.degisim_durumu
    rec.degisim_durumu = new_status
    db.session.commit()

    return jsonify(
        success=True,
        message=f'Durum güncellendi: {old_status} → {new_status}',
        exchange=_degisim_to_dict(rec),
    )


@agent_api.route('/exchanges/<degisim_no>', methods=['DELETE'])
@require_agent_key
def delete_exchange(degisim_no):
    """Değişim kaydını sil."""
    rec = Degisim.query.filter_by(degisim_no=degisim_no).first()
    if not rec:
        return jsonify(success=False, error='Değişim bulunamadı.'), 404

    db.session.delete(rec)
    db.session.commit()
    return jsonify(success=True, message='Değişim silindi.')


@agent_api.route('/exchanges/stats', methods=['GET'])
@require_agent_key
def exchange_stats():
    """Değişim istatistikleri."""
    stats = db.session.query(
        Degisim.degisim_durumu, func.count(Degisim.id)
    ).group_by(Degisim.degisim_durumu).all()

    result = {s[0] or 'Belirsiz': s[1] for s in stats}
    result['Toplam'] = sum(result.values())

    return jsonify(success=True, stats=result)


# ══════════════════════════════════════════════════════════════════════════════
#  5. İADE (RETURN) ENDPOİNT'LERİ
# ══════════════════════════════════════════════════════════════════════════════

@agent_api.route('/returns', methods=['GET'])
@require_agent_key
def list_returns():
    """İade taleplerini listele.

    Query params:
      - status: filtre
      - search: sipariş no, müşteri adı
      - page (default=1), per_page (default=50)
    """
    status = request.args.get('status', '').strip()
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)

    q = ReturnOrder.query

    if status:
        q = q.filter(ReturnOrder.status.ilike(f'%{status}%'))
    if search:
        q = q.filter(or_(
            ReturnOrder.order_number.ilike(f'%{search}%'),
            ReturnOrder.customer_first_name.ilike(f'%{search}%'),
            ReturnOrder.customer_last_name.ilike(f'%{search}%'),
            ReturnOrder.return_request_number.ilike(f'%{search}%'),
        ))

    q = q.order_by(ReturnOrder.return_date.desc())
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for r in pagination.items:
        products = [
            {
                'barcode': rp.barcode,
                'product_name': rp.product_name,
                'size': rp.size,
                'color': rp.color,
                'quantity': rp.quantity,
                'reason': rp.reason,
                'return_to_stock': rp.return_to_stock,
            }
            for rp in r.products.all()
        ]
        items.append({
            'id': str(r.id),
            'order_number': r.order_number,
            'return_request_number': r.return_request_number,
            'status': r.status,
            'return_date': r.return_date.isoformat() if r.return_date else None,
            'customer_first_name': r.customer_first_name,
            'customer_last_name': r.customer_last_name,
            'cargo_tracking_number': r.cargo_tracking_number,
            'return_reason': r.return_reason,
            'refund_amount': float(r.refund_amount) if r.refund_amount else None,
            'products': products,
        })

    return jsonify(
        success=True,
        total=pagination.total,
        page=page,
        per_page=per_page,
        total_pages=pagination.pages,
        returns=items,
    )


@agent_api.route('/returns/<return_id>', methods=['GET'])
@require_agent_key
def get_return(return_id):
    """Tek iade detayı."""
    r = ReturnOrder.query.get(return_id)
    if not r:
        return jsonify(success=False, error='İade bulunamadı.'), 404

    products = [
        {
            'barcode': rp.barcode,
            'product_name': rp.product_name,
            'size': rp.size,
            'color': rp.color,
            'quantity': rp.quantity,
            'reason': rp.reason,
            'return_to_stock': rp.return_to_stock,
        }
        for rp in r.products.all()
    ]

    return jsonify(
        success=True,
        return_order={
            'id': str(r.id),
            'order_number': r.order_number,
            'return_request_number': r.return_request_number,
            'status': r.status,
            'return_date': r.return_date.isoformat() if r.return_date else None,
            'process_date': r.process_date.isoformat() if r.process_date else None,
            'customer_first_name': r.customer_first_name,
            'customer_last_name': r.customer_last_name,
            'cargo_tracking_number': r.cargo_tracking_number,
            'cargo_provider_name': r.cargo_provider_name,
            'return_reason': r.return_reason,
            'customer_explanation': r.customer_explanation,
            'notes': r.notes,
            'refund_amount': float(r.refund_amount) if r.refund_amount else None,
            'products': products,
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
#  6. MANUEL SİPARİŞ ENDPOİNT'LERİ (YeniSiparis)
# ══════════════════════════════════════════════════════════════════════════════

@agent_api.route('/manual-orders', methods=['GET'])
@require_agent_key
def list_manual_orders():
    """Manuel siparişleri listele.

    Query params:
      - search: sipariş no, müşteri adı
      - status: durum filtresi
      - page (default=1), per_page (default=50)
    """
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)

    q = YeniSiparis.query

    if search:
        q = q.filter(or_(
            YeniSiparis.siparis_no.ilike(f'%{search}%'),
            YeniSiparis.musteri_adi.ilike(f'%{search}%'),
            YeniSiparis.musteri_soyadi.ilike(f'%{search}%'),
        ))
    if status:
        q = q.filter(YeniSiparis.durum == status)

    q = q.order_by(YeniSiparis.siparis_tarihi.desc())
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for s in pagination.items:
        urunler = [{
            'barkod': u.urun_barkod,
            'urun_adi': u.urun_adi,
            'adet': u.adet,
            'birim_fiyat': float(u.birim_fiyat) if u.birim_fiyat else None,
            'toplam_fiyat': float(u.toplam_fiyat) if u.toplam_fiyat else None,
            'renk': u.renk,
            'beden': u.beden,
            'raf_kodu': u.raf_kodu,
        } for u in s.urunler]

        items.append({
            'id': s.id,
            'siparis_no': s.siparis_no,
            'musteri_adi': s.musteri_adi,
            'musteri_soyadi': s.musteri_soyadi,
            'musteri_adres': s.musteri_adres,
            'musteri_telefon': s.musteri_telefon,
            'siparis_tarihi': s.siparis_tarihi.isoformat() if s.siparis_tarihi else None,
            'toplam_tutar': float(s.toplam_tutar) if s.toplam_tutar else None,
            'durum': s.durum,
            'notlar': s.notlar,
            'kapida_odeme': s.kapida_odeme,
            'kapida_odeme_tutari': float(s.kapida_odeme_tutari) if s.kapida_odeme_tutari else None,
            'urunler': urunler,
        })

    return jsonify(
        success=True,
        total=pagination.total,
        page=page,
        per_page=per_page,
        total_pages=pagination.pages,
        orders=items,
    )


@agent_api.route('/manual-orders', methods=['POST'])
@require_agent_key
def create_manual_order():
    """Manuel sipariş oluştur.

    JSON body:
    {
      "musteri_adi": "Ali",
      "musteri_soyadi": "Veli",
      "musteri_adres": "...",
      "musteri_telefon": "05xx...",
      "notlar": "...",
      "kapida_odeme": false,
      "kapida_odeme_tutari": 0,
      "urunler": [
        {"barkod": "ABC123", "adet": 1, "birim_fiyat": 500}
      ]
    }
    """
    data = request.get_json(silent=True) or {}

    required = ['musteri_adi', 'musteri_soyadi', 'musteri_adres', 'urunler']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify(success=False, error=f'Eksik alanlar: {", ".join(missing)}'), 400

    urunler = data['urunler']
    if not isinstance(urunler, list) or len(urunler) == 0:
        return jsonify(success=False, error='En az 1 ürün gerekli.'), 400

    try:
        from degisim import allocate_from_shelves_and_decrement_central

        siparis_no = f"MAN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        toplam_tutar = 0
        siparis_urunler = []

        for item in urunler:
            barkod = (item.get('barkod') or '').strip()
            adet = max(1, int(item.get('adet', 1)))
            birim_fiyat = float(item.get('birim_fiyat', 0))

            product = Product.query.get(barkod)
            if not product:
                return jsonify(success=False, error=f'Ürün bulunamadı: {barkod}'), 404

            if birim_fiyat <= 0:
                birim_fiyat = float(product.sale_price or 0)

            toplam_fiyat = birim_fiyat * adet
            toplam_tutar += toplam_fiyat

            alloc = allocate_from_shelves_and_decrement_central(barkod, qty=adet)

            raf_kodu = ', '.join([rk for rk in alloc['shelf_codes'] if rk]) if alloc['shelf_codes'] else None

            siparis_urunler.append(SiparisUrun(
                urun_barkod=barkod,
                urun_adi=product.title,
                adet=adet,
                birim_fiyat=birim_fiyat,
                toplam_fiyat=toplam_fiyat,
                renk=product.color,
                beden=product.size,
                raf_kodu=raf_kodu,
            ))

        siparis = YeniSiparis(
            siparis_no=siparis_no,
            musteri_adi=data['musteri_adi'],
            musteri_soyadi=data['musteri_soyadi'],
            musteri_adres=data['musteri_adres'],
            musteri_telefon=data.get('musteri_telefon', ''),
            siparis_tarihi=datetime.now(),
            toplam_tutar=toplam_tutar,
            durum='Yeni',
            notlar=data.get('notlar', ''),
            kapida_odeme=data.get('kapida_odeme', False),
            kapida_odeme_tutari=data.get('kapida_odeme_tutari', 0),
            urunler=siparis_urunler,
        )

        db.session.add(siparis)
        db.session.commit()

        return jsonify(
            success=True,
            message='Sipariş oluşturuldu.',
            siparis_no=siparis_no,
            toplam_tutar=toplam_tutar,
        ), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f'Agent API: Manuel sipariş hatası: {e}', exc_info=True)
        return jsonify(success=False, error=str(e)), 500


# ══════════════════════════════════════════════════════════════════════════════
#  7. KASA (FİNANS) ENDPOİNT'LERİ
# ══════════════════════════════════════════════════════════════════════════════

@agent_api.route('/finance/summary', methods=['GET'])
@require_agent_key
def finance_summary():
    """Finansal özet — ana kasa bakiyesi ve kasa istatistikleri."""
    ana_kasa = AnaKasa.query.first()

    gelir = db.session.query(func.coalesce(func.sum(Kasa.tutar), 0)).filter(Kasa.tip == 'gelir').scalar()
    gider = db.session.query(func.coalesce(func.sum(Kasa.tutar), 0)).filter(Kasa.tip == 'gider').scalar()

    odenmemis = Kasa.query.filter(Kasa.durum == KasaDurum.ODENMEDI).count()
    kismi_odenmis = Kasa.query.filter(Kasa.durum == KasaDurum.KISMI_ODENDI).count()
    tamamlanmis = Kasa.query.filter(Kasa.durum == KasaDurum.TAMAMLANDI).count()

    return jsonify(
        success=True,
        ana_kasa_bakiye=float(ana_kasa.bakiye) if ana_kasa else 0,
        toplam_gelir=float(gelir),
        toplam_gider=float(gider),
        odenmemis_kayit=odenmemis,
        kismi_odenmis_kayit=kismi_odenmis,
        tamamlanmis_kayit=tamamlanmis,
    )


@agent_api.route('/finance/transactions', methods=['GET'])
@require_agent_key
def list_transactions():
    """Kasa kayıtlarını listele.

    Query params:
      - tip: gelir | gider
      - kategori: kategori filtresi
      - durum: odenmedi | kismi_odendi | tamamlandi
      - start_date, end_date: YYYY-MM-DD
      - page (default=1), per_page (default=50)
    """
    tip = request.args.get('tip', '').strip()
    kategori = request.args.get('kategori', '').strip()
    durum = request.args.get('durum', '').strip()
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)

    q = Kasa.query

    if tip:
        q = q.filter(Kasa.tip == tip)
    if kategori:
        q = q.filter(Kasa.kategori.ilike(f'%{kategori}%'))
    if durum:
        durum_map = {
            'odenmedi': KasaDurum.ODENMEDI,
            'kismi_odendi': KasaDurum.KISMI_ODENDI,
            'tamamlandi': KasaDurum.TAMAMLANDI,
        }
        if durum in durum_map:
            q = q.filter(Kasa.durum == durum_map[durum])
    if start_date:
        try:
            q = q.filter(Kasa.tarih >= datetime.strptime(start_date, '%Y-%m-%d'))
        except ValueError:
            pass
    if end_date:
        try:
            q = q.filter(Kasa.tarih <= datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1))
        except ValueError:
            pass

    q = q.order_by(Kasa.tarih.desc())
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for k in pagination.items:
        items.append({
            'id': k.id,
            'tip': k.tip,
            'aciklama': k.aciklama,
            'tutar': float(k.tutar),
            'kategori': k.kategori,
            'tarih': k.tarih.isoformat() if k.tarih else None,
            'durum': k.durum.value if k.durum else None,
            'odenen_tutar': float(k.odenen_tutar),
            'kalan_tutar': float(k.kalan_tutar),
            'ana_kasadan': k.ana_kasadan,
        })

    return jsonify(
        success=True,
        total=pagination.total,
        page=page,
        per_page=per_page,
        total_pages=pagination.pages,
        transactions=items,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  8. RAF (DEPO) ENDPOİNT'LERİ
# ══════════════════════════════════════════════════════════════════════════════

@agent_api.route('/shelves', methods=['GET'])
@require_agent_key
def list_shelves():
    """Rafları listele.

    Query params:
      - search: raf kodu ile arama
      - page (default=1), per_page (default=100)
    """
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 100, type=int), 500)

    q = Raf.query
    if search:
        q = q.filter(Raf.kod.ilike(f'%{search}%'))

    q = q.order_by(Raf.kod.asc())
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for r in pagination.items:
        item_count = RafUrun.query.filter_by(raf_kodu=r.kod).filter(RafUrun.adet > 0).count()
        total_qty = db.session.query(func.coalesce(func.sum(RafUrun.adet), 0)).filter(
            RafUrun.raf_kodu == r.kod, RafUrun.adet > 0
        ).scalar()

        items.append({
            'kod': r.kod,
            'ana': r.ana,
            'ikincil': r.ikincil,
            'kat': r.kat,
            'urun_cesidi': item_count,
            'toplam_adet': int(total_qty),
        })

    return jsonify(
        success=True,
        total=pagination.total,
        page=page,
        per_page=per_page,
        total_pages=pagination.pages,
        shelves=items,
    )


@agent_api.route('/shelves/<shelf_code>/products', methods=['GET'])
@require_agent_key
def shelf_products(shelf_code):
    """Belirli raftaki ürünleri listele."""
    raf = Raf.query.filter_by(kod=shelf_code).first()
    if not raf:
        return jsonify(success=False, error='Raf bulunamadı.'), 404

    raf_items = RafUrun.query.filter_by(raf_kodu=shelf_code).filter(RafUrun.adet > 0).all()

    products = []
    for ri in raf_items:
        product = Product.query.get(ri.urun_barkodu)
        products.append({
            'barcode': ri.urun_barkodu,
            'adet': ri.adet,
            'product_title': product.title if product else None,
            'product_main_id': product.product_main_id if product else None,
            'color': product.color if product else None,
            'size': product.size if product else None,
        })

    return jsonify(
        success=True,
        shelf={
            'kod': raf.kod,
            'ana': raf.ana,
            'ikincil': raf.ikincil,
            'kat': raf.kat,
        },
        products=products,
        total_products=len(products),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  9. BARKOD ALİAS ENDPOİNT'LERİ
# ══════════════════════════════════════════════════════════════════════════════

@agent_api.route('/barcode-alias/check/<barcode>', methods=['GET'])
@require_agent_key
def check_barcode_alias(barcode):
    """Barkod alias kontrolü — asıl barkodu döner."""
    alias = BarcodeAlias.query.get(barcode)
    if alias:
        return jsonify(
            success=True,
            is_alias=True,
            alias_barcode=barcode,
            main_barcode=alias.main_barcode,
        )

    product = Product.query.get(barcode)
    if product:
        aliases = BarcodeAlias.query.filter_by(main_barcode=barcode).all()
        return jsonify(
            success=True,
            is_alias=False,
            main_barcode=barcode,
            aliases=[a.alias_barcode for a in aliases],
        )

    return jsonify(success=False, error='Barkod bulunamadı.'), 404


# ══════════════════════════════════════════════════════════════════════════════
#  10. DASHBOARD / GENEL İSTATİSTİKLER
# ══════════════════════════════════════════════════════════════════════════════

@agent_api.route('/dashboard', methods=['GET'])
@require_agent_key
def dashboard():
    """Genel panel özeti — agent'ın hızlıca durum öğrenmesi için."""
    # Sipariş sayıları
    order_counts = {}
    for table_cls in ORDER_TABLES:
        label = STATUS_LABEL.get(table_cls, table_cls.__tablename__)
        order_counts[label] = table_cls.query.count()

    # Bugünkü siparişler
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_orders = OrderCreated.query.filter(OrderCreated.order_date >= today).count()

    # Stok
    total_stock = int(db.session.query(func.coalesce(func.sum(CentralStock.qty), 0)).scalar())
    total_products = Product.query.filter(
        or_(Product.archived == False, Product.archived == None)
    ).count()

    # Değişimler
    active_exchanges = Degisim.query.filter(
        Degisim.degisim_durumu.notin_(['Tamamlandı', 'İptal'])
    ).count()

    # İadeler
    pending_returns = ReturnOrder.query.filter(
        ReturnOrder.status.notin_(['Completed', 'Rejected', 'Tamamlandı', 'Reddedildi'])
    ).count()

    # Kasa
    ana_kasa = AnaKasa.query.first()

    return jsonify(
        success=True,
        timestamp=datetime.now().isoformat(),
        orders=order_counts,
        today_new_orders=today_orders,
        total_stock=total_stock,
        total_products=total_products,
        active_exchanges=active_exchanges,
        pending_returns=pending_returns,
        ana_kasa_bakiye=float(ana_kasa.bakiye) if ana_kasa else 0,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  11. ARAMA ENDPOİNT'İ (GLOBAL)
# ══════════════════════════════════════════════════════════════════════════════

@agent_api.route('/search', methods=['GET'])
@require_agent_key
def global_search():
    """Global arama — ürün, sipariş, değişim, iade hepsinde arar.

    Query params:
      - q: arama terimi (zorunlu)
      - limit: her kategori için max sonuç (default=5)
    """
    query = request.args.get('q', '').strip()
    limit = min(request.args.get('limit', 5, type=int), 20)

    if not query or len(query) < 2:
        return jsonify(success=False, error='En az 2 karakter gerekli.'), 400

    results = {
        'products': [],
        'orders': [],
        'exchanges': [],
        'returns': [],
    }

    # Ürün arama
    products = Product.query.filter(or_(
        Product.barcode.ilike(f'%{query}%'),
        Product.title.ilike(f'%{query}%'),
        Product.product_main_id.ilike(f'%{query}%'),
    )).limit(limit).all()
    results['products'] = [_product_to_dict(p) for p in products]

    # Sipariş arama
    for table_cls in ORDER_TABLES:
        if len(results['orders']) >= limit:
            break
        orders = table_cls.query.filter(or_(
            table_cls.order_number.ilike(f'%{query}%'),
            table_cls.customer_name.ilike(f'%{query}%'),
            table_cls.product_barcode.ilike(f'%{query}%'),
        )).limit(limit - len(results['orders'])).all()
        for o in orders:
            results['orders'].append(_order_to_dict(o, table_cls))

    # Değişim arama
    exchanges = Degisim.query.filter(or_(
        Degisim.degisim_no.ilike(f'%{query}%'),
        Degisim.siparis_no.ilike(f'%{query}%'),
        Degisim.ad.ilike(f'%{query}%'),
        Degisim.soyad.ilike(f'%{query}%'),
    )).limit(limit).all()
    results['exchanges'] = [_degisim_to_dict(d) for d in exchanges]

    # İade arama
    returns = ReturnOrder.query.filter(or_(
        ReturnOrder.order_number.ilike(f'%{query}%'),
        ReturnOrder.customer_first_name.ilike(f'%{query}%'),
        ReturnOrder.return_request_number.ilike(f'%{query}%'),
    )).limit(limit).all()
    results['returns'] = [{
        'id': str(r.id),
        'order_number': r.order_number,
        'return_request_number': r.return_request_number,
        'status': r.status,
        'customer_name': f'{r.customer_first_name or ""} {r.customer_last_name or ""}'.strip(),
    } for r in returns]

    total = sum(len(v) for v in results.values())

    return jsonify(success=True, query=query, total_results=total, results=results)
