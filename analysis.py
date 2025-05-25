from flask import Blueprint, render_template, jsonify, request
from models import db, ReturnOrder, Degisim, Product
# Çok tablolu sipariş modelleri – lütfen kendi proje dosyanıza göre import edin
from models import OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled

from sqlalchemy import func, case, distinct, select, union_all
from datetime import datetime, timedelta
import logging

analysis_bp = Blueprint('analysis', __name__)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


########################
# 1) Tüm tabloları birleştiren "union_all" subquery fonksiyonu
########################
def all_orders_union(start_date, end_date):
    """
    5 tabloyu (Created, Picking, Shipped, Delivered, Cancelled) birleştirerek 
    tek bir sanal sorgu (alias) döndürür. 
    Her tabloda şu sütunların aynı isimle var olduğunu varsayıyoruz:
      id, order_date, status, amount, quantity, product_main_id, merchant_sku, product_color, product_size

    start_date ve end_date'e göre order_date filtresi uygulanır.
    """
    # Her tablo için SELECT sorgusu
    q1 = select(
        OrderCreated.id.label('id'),
        OrderCreated.order_date.label('order_date'),
        OrderCreated.status.label('status'),
        OrderCreated.amount.label('amount'),
        OrderCreated.quantity.label('quantity'),
        OrderCreated.product_main_id.label('product_main_id'),
        OrderCreated.merchant_sku.label('merchant_sku'),
        OrderCreated.product_color.label('product_color'),
        OrderCreated.product_size.label('product_size')
    ).where(OrderCreated.order_date.between(start_date, end_date))

    q2 = select(
        OrderPicking.id.label('id'),
        OrderPicking.order_date.label('order_date'),
        OrderPicking.status.label('status'),
        OrderPicking.amount.label('amount'),
        OrderPicking.quantity.label('quantity'),
        OrderPicking.product_main_id.label('product_main_id'),
        OrderPicking.merchant_sku.label('merchant_sku'),
        OrderPicking.product_color.label('product_color'),
        OrderPicking.product_size.label('product_size')
    ).where(OrderPicking.order_date.between(start_date, end_date))

    q3 = select(
        OrderShipped.id.label('id'),
        OrderShipped.order_date.label('order_date'),
        OrderShipped.status.label('status'),
        OrderShipped.amount.label('amount'),
        OrderShipped.quantity.label('quantity'),
        OrderShipped.product_main_id.label('product_main_id'),
        OrderShipped.merchant_sku.label('merchant_sku'),
        OrderShipped.product_color.label('product_color'),
        OrderShipped.product_size.label('product_size')
    ).where(OrderShipped.order_date.between(start_date, end_date))

    q4 = select(
        OrderDelivered.id.label('id'),
        OrderDelivered.order_date.label('order_date'),
        OrderDelivered.status.label('status'),
        OrderDelivered.amount.label('amount'),
        OrderDelivered.quantity.label('quantity'),
        OrderDelivered.product_main_id.label('product_main_id'),
        OrderDelivered.merchant_sku.label('merchant_sku'),
        OrderDelivered.product_color.label('product_color'),
        OrderDelivered.product_size.label('product_size')
    ).where(OrderDelivered.order_date.between(start_date, end_date))

    q5 = select(
        OrderCancelled.id.label('id'),
        OrderCancelled.order_date.label('order_date'),
        OrderCancelled.status.label('status'),
        OrderCancelled.amount.label('amount'),
        OrderCancelled.quantity.label('quantity'),
        OrderCancelled.product_main_id.label('product_main_id'),
        OrderCancelled.merchant_sku.label('merchant_sku'),
        OrderCancelled.product_color.label('product_color'),
        OrderCancelled.product_size.label('product_size')
    ).where(OrderCancelled.order_date.between(start_date, end_date))

    # Hepsini union_all ile birleştir
    full_union = union_all(q1, q2, q3, q4, q5)
    # Alias oluşturup döndürüyoruz
    return full_union.alias('all_orders')


########################
# 2) Günlük Satış İstatistikleri
########################
def get_daily_sales(session, start_date: datetime, end_date: datetime):
    """
    Belirtilen tarih aralığında, 5 tabloyu birleştiren subquery üzerinden günlük satış istatistikleri.
    """
    try:
        ao = all_orders_union(start_date, end_date)
        # ao.c => (id, order_date, status, amount, quantity, product_main_id, merchant_sku, product_color, product_size)

        q = session.query(
            func.date(ao.c.order_date).label('date'),
            func.count(ao.c.id).label('order_count'),
            func.sum(ao.c.amount).label('total_amount'),
            func.sum(ao.c.quantity).label('total_quantity'),
            func.avg(ao.c.amount).label('average_order_value'),
            func.count(case((ao.c.status == 'Delivered', 1), else_=None)).label('delivered_count'),
            func.count(case((ao.c.status == 'Cancelled', 1), else_=None)).label('cancelled_count')
        ).group_by(
            func.date(ao.c.order_date)
        ).order_by(
            func.date(ao.c.order_date).desc()
        )

        results = q.all()
        return results
    except Exception as e:
        logger.error(f"Günlük satış verileri çekilirken hata: {e}")
        session.rollback()
        return []

########################
# 3) Ürün Bazlı Satış Analizi
########################
def get_product_sales(session, start_date: datetime, end_date: datetime):
    """
    Belirtilen tarih aralığında ürün bazlı satış analizi (5 tablo union).
    Cancelled hariç tutuyoruz (örnek).
    """
    try:
        logger.info("Ürün satışları sorgusu (çok tablo) başlıyor...")
        ao = all_orders_union(start_date, end_date)

        q = session.query(
            ao.c.product_main_id.label('product_main_id'),
            ao.c.merchant_sku.label('merchant_sku'),
            ao.c.product_color.label('color'),
            ao.c.product_size.label('size'),
            func.count(ao.c.id).label('sale_count'),
            func.sum(ao.c.amount).label('total_revenue'),
            func.avg(ao.c.amount).label('average_price'),
            func.sum(ao.c.quantity).label('total_quantity')
        ).filter(
            ao.c.status != 'Cancelled'
        ).group_by(
            ao.c.product_main_id,
            ao.c.merchant_sku,
            ao.c.product_color,
            ao.c.product_size
        ).order_by(
            func.sum(ao.c.amount).desc()
        ).limit(50)

        results = q.all()
        logger.info(f"Bulunan ürün satışı sayısı: {len(results)}")
        return results
    except Exception as e:
        logger.exception("Ürün satış verisi (çok tablo) çekilirken hata oluştu:")
        return []


########################
# 4) İade İstatistikleri (ReturnOrder tablonuz değişmiyorsa)
########################
def get_return_stats(session, start_date: datetime, end_date: datetime):
    """
    ReturnOrder tablosundaki iade analizleri (tek tablo, aynen kalıyor).
    """
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        if not inspector.has_table('return_orders'):
            logger.warning("ReturnOrder tablosu veritabanında bulunamadı")
            return []

        result = session.query(
            func.coalesce(ReturnOrder.return_reason, 'Belirtilmemiş').label('return_reason'),
            func.count(ReturnOrder.id).label('return_count'),
            func.count(distinct(ReturnOrder.order_number)).label('unique_orders'),
            func.coalesce(func.avg(ReturnOrder.refund_amount), 0).label('average_refund')
        ).filter(
            ReturnOrder.return_date.between(start_date, end_date)
        ).group_by(
            ReturnOrder.return_reason
        ).all()
        return result
    except Exception as e:
        logger.error(f"İade istatistikleri sorgusu hatası: {e}")
        session.rollback()
        return []


########################
# 5) Değişim İstatistikleri (Degisim tablonuz değişmiyorsa)
########################
def get_exchange_stats(session, start_date: datetime, end_date: datetime):
    """
    Degisim tablosu üzerinden değişim analizleri.
    """
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        if not inspector.has_table('degisim'):
            logger.warning("Degisim tablosu veritabanında bulunamadı")
            return []

        result = session.query(
            func.coalesce(Degisim.degisim_nedeni, 'Belirtilmemiş').label('degisim_nedeni'),
            func.count(Degisim.degisim_no).label('exchange_count'),
            func.date(Degisim.degisim_tarihi).label('date')
        ).filter(
            Degisim.degisim_tarihi.between(start_date, end_date)
        ).group_by(
            Degisim.degisim_nedeni,
            func.date(Degisim.degisim_tarihi)
        ).order_by(
            func.date(Degisim.degisim_tarihi).desc()
        ).all()
        return result
    except Exception as e:
        logger.error(f"Değişim istatistikleri sorgusu hatası: {e}")
        session.rollback()
        return []


########################
# 6) HTML Sayfası (Opsiyonel)
########################
@analysis_bp.route('/analysis')
def sales_analysis():
    """
    Basit bir template render ediyor (analiz dashboard). 
    """
    try:
        return render_template('analysis.html')
    except Exception as e:
        logger.error(f"Analiz sayfası render hatası: {str(e)}")
        return render_template('error.html', error=str(e))


########################
# 7) API Endpoint (Tüm Verileri Döndürür)
########################
@analysis_bp.route('/api/sales-stats')
def get_sales_stats():
    """
    API endpoint'i: Belirtilen tarih aralığında (varsayılan 90 gün) 
    - Günlük satış istatistikleri (5 tablo union)
    - Ürün bazlı satış (5 tablo union)
    - ReturnOrder (iade) ve Degisim (değişim) tabloları
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import DATABASE_URI

    # Yeni bir session oluştur
    engine = create_engine(DATABASE_URI)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    logger.info("API isteği başladı")
    now = datetime.now()

    # Tarih parametrelerini al
    quick_filter = request.args.get('quick_filter')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if quick_filter:
        if quick_filter == 'last7':
            start_date = now - timedelta(days=7)
            end_date = now
        elif quick_filter == 'last30':
            start_date = now - timedelta(days=30)
            end_date = now
        elif quick_filter == 'today':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now
        elif quick_filter == 'this_month':
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = now
        else:
            logger.info("Geçersiz quick_filter değeri, varsayılan 90 gün kullanılıyor.")
            days = 90
            start_date = now - timedelta(days=days)
            end_date = now
    elif start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'error': 'Tarih formatı geçersiz (YYYY-MM-DD).', 'daily_sales': [], 'product_sales': [], 'returns': [], 'exchanges': []})
    else:
        days = int(request.args.get('days', 90))
        start_date = now - timedelta(days=days)
        end_date = now

    logger.info(f"Tarih aralığı: {start_date} - {end_date}")

    try:
        # 1) Günlük satış
        daily_sales = get_daily_sales(session, start_date, end_date)

        # 2) Ürün bazlı satış
        product_sales = get_product_sales(session, start_date, end_date)

        # 3) Return / Exchange
        returns_data = get_return_stats(session, start_date, end_date)
        exchanges_data = get_exchange_stats(session, start_date, end_date)

        # Toplam değerleri hesaplama
        total_orders = sum(stat.order_count or 0 for stat in daily_sales) if daily_sales else 0
        total_items_sold = sum(stat.total_quantity or 0 for stat in daily_sales) if daily_sales else 0
        total_revenue = sum(stat.total_amount or 0 for stat in daily_sales) if daily_sales else 0

        # JSON yanıt oluşturma
        response = {
            'success': True,

            'total_orders': total_orders,
            'total_items_sold': total_items_sold,
            'total_revenue': round(float(total_revenue), 2),

            'daily_sales': [{
                'date': stat.date.strftime('%Y-%m-%d') if stat.date else None,
                'order_count': int(stat.order_count or 0),
                'total_amount': float(stat.total_amount or 0),
                'total_quantity': int(stat.total_quantity or 0),
                'average_order_value': round(float(stat.average_order_value or 0), 2),
                'delivered_count': int(stat.delivered_count or 0),
                'cancelled_count': int(stat.cancelled_count or 0)
            } for stat in daily_sales] if daily_sales else [],

            'product_sales': [{
                'product_id': sale.product_main_id,
                'merchant_sku': sale.merchant_sku,
                'color': sale.color,
                'size': sale.size,
                'sale_count': int(sale.sale_count or 0),
                'total_revenue': round(float(sale.total_revenue or 0), 2),
                'average_price': round(float(sale.average_price or 0), 2),
                'total_quantity': int(sale.total_quantity or 0),
            } for sale in product_sales] if product_sales else [],

            # ReturnOrder verisi
            'returns': [{
                'return_reason': r.return_reason,
                'return_count': int(r.return_count or 0),
                'unique_orders': int(r.unique_orders or 0),
                'average_refund': round(float(r.average_refund or 0), 2)
            } for r in returns_data] if returns_data else [],

            # Degisim verisi
            'exchanges': [{
                'degisim_nedeni': x.degisim_nedeni,
                'exchange_count': int(x.exchange_count or 0),
                'date': x.date.strftime('%Y-%m-%d') if x.date else None
            } for x in exchanges_data] if exchanges_data else []
        }

        return jsonify(response)

    except Exception as e:
        logger.exception(f"API hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'daily_sales': [],
            'product_sales': [],
            'returns': [],
            'exchanges': []
        })

    finally:
        session.close()
