import requests
import base64
from datetime import datetime, timedelta
from functools import wraps
import time
import logging
from models import ReturnProduct, ReturnOrder
from sqlalchemy.exc import SQLAlchemyError
from flask import Blueprint, jsonify, render_template, request, current_app, redirect, url_for, flash
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from sqlalchemy.dialects.postgresql import insert as pg_insert
from apscheduler.schedulers.background import BackgroundScheduler

from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

iade_islemleri = Blueprint('iade_islemleri', __name__)

def with_db_session(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        Session = current_app.config['Session']
        db_session = Session()
        try:
            return f(db_session, *args, **kwargs)
        finally:
            db_session.close()
    return decorated_function

def get_session_with_retries():
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PUT"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session

def safe_strip(val):
    return val.strip() if isinstance(val, str) else val

def is_valid_uuid(uuid_str):
    import uuid
    try:
        uuid.UUID(str(uuid_str))
        return True
    except ValueError:
        return False

def fetch_data_from_api(start_date, end_date):
    logger.info(f"API'den {start_date} - {end_date} tarihleri arası iade verileri çekilmeye başlanıyor.")

    url = f'https://api.trendyol.com/sapigw/suppliers/{SUPPLIER_ID}/claims'
    credentials = f'{API_KEY}:{API_SECRET}'
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    headers = {
        'Authorization': f'Basic {encoded_credentials}',
        'Content-Type': 'application/json'
    }

    all_content = []
    page = 0
    size = 50

    while True:
        logger.debug(f"Sayfa: {page}, Boyut: {size}")
        params = {
            'size': size,
            'page': page,
            'startDate': int(start_date.timestamp() * 1000),
            'endDate': int(end_date.timestamp() * 1000),
            'sortColumn': 'CLAIM_DATE',
            'sortDirection': 'DESC'
        }

        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            logger.error(f"API isteği başarısız oldu: {response.status_code} - {response.text}")
            return None

        try:
            data = response.json()
        except Exception as e:
            logger.error(f"JSON parse hatası: {e}")
            return None

        if not isinstance(data, dict):
            logger.error("API beklenen formatta JSON dönmedi.")
            return None

        content = data.get('content')
        if not content:
            logger.debug("Daha fazla iade yok, döngü sonlandırılıyor.")
            break

        logger.debug(f"Bu sayfada {len(content)} adet iade bulundu.")
        all_content.extend(content)
        page += 1

    full_data = {'content': all_content}
    logger.info(f"API'den toplam {len(all_content)} adet iade alındı.")
    return full_data


def save_to_database(data, db_session):
    logger.info("Veriler veritabanına kaydedilmeye başlanıyor.")
    content = data.get('content', [])
    logger.debug(f"İçerikteki öğe sayısı: {len(content)}")

    orders_to_upsert = []
    products_to_upsert = []
    processed_ids = set()

    try:
        existing_orders = {str(order.id): True for order in db_session.query(ReturnOrder.id).all()}
        logger.debug(f"Veritabanında hali hazırda {len(existing_orders)} adet iade var.")
    except Exception as e:
        logger.error(f"Mevcut iade sorgusu hata verdi: {e}")
        return False

    for item in content:
        try:
            claim_id = item.get('id')
            if not claim_id:
                logger.debug("claim_id yok, bu kaydı atlıyoruz.")
                continue

            if not is_valid_uuid(claim_id):
                logger.debug(f"Geçersiz UUID formatı için id: {claim_id}, atlanıyor.")
                continue

            if str(claim_id) in existing_orders:
                logger.debug(f"{claim_id} zaten veritabanında var, tekrar eklenmiyor.")
                continue

            if claim_id in processed_ids:
                logger.debug(f"{claim_id} zaten işlenmiş, tekrar işlenmiyor.")
                continue
            processed_ids.add(claim_id)

            claim_date_ms = item.get('claimDate')
            claim_date = datetime.fromtimestamp(claim_date_ms / 1000) if claim_date_ms else None
            customer_first_name = safe_strip(item.get('customerFirstName', ''))
            customer_last_name = safe_strip(item.get('customerLastName', ''))
            items = item.get('items', [])
            if not items:
                logger.debug(f"İade {claim_id} için öğe bulunamadı, atlanıyor.")
                continue

            claim_status = safe_strip(items[0].get('claimItems', [{}])[0].get('claimItemStatus', {}).get('name', ''))
            if claim_status in ['Accepted', 'Onaylandı']:
                logger.debug(f"İade {claim_id} statüsü 'Accepted/Onaylandı', kaydedilmiyor.")
                continue

            orders_to_upsert.append({
                'id': claim_id,
                'order_number': safe_strip(item.get('orderNumber', '')),
                'return_request_number': claim_id,
                'status': claim_status,
                'return_date': claim_date,
                'customer_first_name': customer_first_name,
                'customer_last_name': customer_last_name,
                'cargo_tracking_number': str(item.get('cargoTrackingNumber', '')),
                'cargo_provider_name': safe_strip(item.get('cargoProviderName', '')),
                'cargo_sender_number': safe_strip(item.get('cargoSenderNumber', '')),
                'cargo_tracking_link': safe_strip(item.get('cargoTrackingLink', ''))
            })

            for product_item in items:
                order_line = product_item.get('orderLine', {})
                claim_items = product_item.get('claimItems', [])
                for claim_item in claim_items:
                    products_to_upsert.append({
                        'return_order_id': claim_id,
                        'product_id': safe_strip(order_line.get('id', '')),
                        'barcode': safe_strip(order_line.get('barcode', '')),
                        'model_number': safe_strip(order_line.get('merchantSku', '')),
                        'size': safe_strip(order_line.get('productSize', '')),
                        'color': safe_strip(order_line.get('productColor', '')),
                        'quantity': 1,
                        'reason': safe_strip(claim_item.get('customerClaimItemReason', {}).get('name', '')),
                        'claim_line_item_id': safe_strip(claim_item.get('id', ''))
                    })

        except Exception as e:
            logger.error(f"Veritabanına kaydetme sırasında hata oluştu (id={item.get('id')}): {e}")
            continue

    try:
        # Upsert işlemleri
        for ord in orders_to_upsert:
            stmt = pg_insert(ReturnOrder).values(**ord).on_conflict_do_update(
                index_elements=['id'],
                set_={
                    'order_number': ord['order_number'],
                    'return_request_number': ord['return_request_number'],
                    'status': ord['status'],
                    'return_date': ord['return_date'],
                    'customer_first_name': ord['customer_first_name'],
                    'customer_last_name': ord['customer_last_name'],
                    'cargo_tracking_number': ord.get('cargo_tracking_number'),
                    'cargo_provider_name': ord.get('cargo_provider_name'),
                    'cargo_sender_number': ord.get('cargo_sender_number'),
                    'cargo_tracking_link': ord.get('cargo_tracking_link')
                }
            )
            db_session.execute(stmt)
            logger.debug(f"İade {ord['id']} eklendi veya güncellendi.")

        for prod in products_to_upsert:
            stmt = pg_insert(ReturnProduct).values(**prod).on_conflict_do_update(
                index_elements=['claim_line_item_id'],
                set_={
                    'reason': prod['reason'],
                    'product_id': prod.get('product_id'),
                    'barcode': prod.get('barcode'),
                    'model_number': prod.get('model_number'),
                    'size': prod.get('size'),
                    'color': prod.get('color'),
                    'quantity': prod.get('quantity'),
                    'return_order_id': prod.get('return_order_id')
                }
            )
            db_session.execute(stmt)
            logger.debug(f"Ürün {prod['claim_line_item_id']} eklendi veya güncellendi.")

        db_session.commit()
        logger.info("Tüm iade siparişleri ve ürünleri toplu olarak kaydedildi.")
        return True

    except SQLAlchemyError as e:
        db_session.rollback()
        logger.error(f"Toplu kaydetme sırasında SQLAlchemy hatası: {e}")
        return False
    except Exception as e:
        db_session.rollback()
        logger.error(f"Toplu kaydetme sırasında genel hata: {e}")
        return False


def schedule_daily_return_fetch(app):
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=fetch_and_save_daily_returns,
        trigger="cron",
        hour=23,
        minute=50,
        args=[app],
        id="daily_return_fetch"
    )
    scheduler.start()
    logger.info("Günlük iade çekme görevi planlandı.")


def fetch_and_save_daily_returns(app):
    with app.app_context():
        logger.info("Günlük iade verileri çekme işlemi başladı.")
        Session = current_app.config['Session']
        db_session = Session()

        end_date = datetime.now()
        start_date = end_date - timedelta(days=1)

        try:
            data = fetch_data_from_api(start_date, end_date)
            if data:
                if save_to_database(data, db_session):
                    logger.info("Günlük iade verileri başarıyla çekilip kaydedildi.")
                else:
                    logger.error("Günlük iade verileri kaydedilirken bir hata oluştu.")
            else:
                logger.warning("API'den günlük iade verisi çekilemedi.")
        except Exception as e:
            logger.error(f"Günlük iade çekme sırasında hata: {e}")
        finally:
            db_session.close()
            logger.info("Günlük iade çekme işlemi tamamlandı.")


@iade_islemleri.route('/iade-verileri', methods=['GET'])
def iade_verileri():
    data = fetch_data_from_api(datetime.now() - timedelta(days=7), datetime.now())
    save_to_database(data, current_app.config['Session']())
    return jsonify(data)


@iade_islemleri.route('/iade-listesi', methods=['GET'])
@with_db_session
def iade_listesi(db_session):
    try:
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '', type=str)

        query = db_session.query(ReturnOrder)

        if search:
            query = query.filter(
                ReturnOrder.order_number.ilike(f'%{search}%')
            )

        per_page = 100
        total_elements = query.count()
        total_pages = (total_elements + per_page - 1) // per_page

        logger.debug(f"Toplam öğe sayısı: {total_elements}, Toplam sayfa sayısı: {total_pages}, Mevcut sayfa: {page}")

        return_orders = query.order_by(ReturnOrder.return_date.desc()) \
                               .offset((page - 1) * per_page) \
                               .limit(per_page) \
                               .all()

        claims = []
        product_ids = [order.id for order in return_orders]
        products = db_session.query(ReturnProduct).filter(ReturnProduct.return_order_id.in_(product_ids)).all()
        products_dict = {}
        for product in products:
            products_dict.setdefault(product.return_order_id, []).append(product)

        for order in return_orders:
            claims.append({
                'id': order.id,
                'order_number': order.order_number,
                'status': order.status,
                'return_date': order.return_date,
                'customer_first_name': order.customer_first_name,
                'customer_last_name': order.customer_last_name,
                'products': products_dict.get(order.id, [])
            })
            logger.debug(f"İade siparişi: {order.id}, Ürün sayısı: {len(products_dict.get(order.id, []))}")

        return render_template('iade_listesi.html',
                                     claims=claims,
                                     page=page,
                                     per_page=per_page,
                                     total_pages=total_pages,
                                     total_elements=total_elements,
                                     search=search)
    except Exception as e:
        logger.error(f"Hata oluştu: {e}")
        return jsonify({'error': str(e)})


@iade_islemleri.route('/iade-onayla/<claim_id>', methods=['POST'])
def iade_onayla(claim_id):
    logger.info(f"İade onaylama işlemi başlatıldı (claim_id={claim_id})")

    # Form verilerini al
    claim_line_item_ids = request.form.getlist('claim_line_item_ids')
    product_conditions = request.form.getlist('product_conditions')
    damage_descriptions = request.form.getlist('damage_descriptions')
    inspection_notes = request.form.getlist('inspection_notes')
    return_to_stock = request.form.getlist('return_to_stock')
    approval_reason = request.form.get('approval_reason')
    refund_amount = request.form.get('refund_amount')
    return_category = request.form.get('return_category')
    return_reason = request.form.get('return_reason')
    customer_explanation = request.form.get('customer_explanation')

    if not claim_line_item_ids:
        flash('Onaylanacak ürün seçilmedi.', 'warning')
        logger.debug("Onaylanacak ürün seçilmedi.")
        return redirect(url_for('iade_islemleri.iade_listesi'))

    Session = current_app.config['Session']
    db_session = Session()

    try:
        # İade kaydını güncelle
        return_order = db_session.query(ReturnOrder).filter_by(id=claim_id).first()
        if return_order:
            if return_order.status in ['Accepted', 'Onaylandı']:
                flash('Bu iade zaten onaylanmış.', 'warning')
                logger.debug(f"İade {claim_id} zaten onaylanmış.")
                return redirect(url_for('iade_islemleri.iade_listesi'))

            return_order.status = 'Accepted'
            return_order.process_date = datetime.now()
            # return_order.processed_by = session.get('username') # Session bilgisi burada nasıl alınacak kontrol etmelisin
            return_order.approval_reason = approval_reason
            return_order.refund_amount = float(refund_amount) if refund_amount else 0
            return_order.return_category = return_category
            return_order.return_reason = return_reason
            return_order.customer_explanation = customer_explanation

            # Ürün detaylarını güncelle
            for i, claim_line_item_id in enumerate(claim_line_item_ids):
                product = db_session.query(ReturnProduct).filter_by(claim_line_item_id=claim_line_item_id).first()
                if (product and i < len(product_conditions) and i < len(damage_descriptions) and
                        i < len(inspection_notes) and i < len(return_to_stock)):
                    product.product_condition = product_conditions[i]
                    product.damage_description = damage_descriptions[i]
                    product.inspection_notes = inspection_notes[i]
                    product.return_to_stock = return_to_stock[i] == 'true'

            db_session.commit()
            flash('İade başarıyla onaylandı ve detaylar kaydedildi.', 'success')

        else:
            flash('İade bulunamadı.', 'danger')
            logger.debug(f"İade {claim_id} bulunamadı.")

    except Exception as e:
        db_session.rollback()
        logger.error(f"İade onaylama sırasında hata: {e}")
        flash('İade onaylama sırasında bir hata oluştu.', 'danger')
    finally:
        db_session.close()

    return redirect(url_for('iade_islemleri.iade_listesi'))


@iade_islemleri.route('/iade-guncelle/<claim_id>', methods=['POST'])
def iade_guncelle(claim_id):
    logger.info(f"İade güncelleme işlemi başlatıldı (claim_id={claim_id})")
    new_status = request.form.get('status')
    if not new_status:
        flash('Yeni durum belirtilmedi.', 'warning')
        logger.debug("İade güncelleme için status belirtilmedi.")
        return redirect(url_for('iade_islemleri.iade_listesi'))

    Session = current_app.config['Session']
    db_session = Session()
    try:
        return_order = db_session.query(ReturnOrder).filter_by(id=claim_id).first()
        if return_order:
            return_order.status = new_status
            db_session.commit()
            flash('İade durumu başarıyla güncellendi.', 'success')
            logger.info(f"İade durumu güncellendi (id={claim_id}, new_status={new_status}).")
        else:
            flash('İade siparişi bulunamadı.', 'danger')
            logger.debug(f"İade siparişi bulunamadı (id={claim_id}).")
        db_session.close()
    except Exception as e:
        db_session.rollback()
        logger.error(f"Hata oluştu (iade güncelleme, id={claim_id}): {e}")
        flash('Bir hata oluştu.', 'danger')
    return redirect(url_for('iade_islemleri.iade_listesi'))


# Uygulama başlatıldığında schedule_jobs(app) çağrılır. Örneğin:
# from iade_islemleri import schedule_daily_return_fetch
# schedule_daily_return_fetch(app)