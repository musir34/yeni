# -*- coding: utf-8 -*-

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
import asyncio
import aiohttp
import base64
import json
import traceback
import logging
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
import threading
import os
from barcode_utils import generate_barcode
# Tablolar: Created, Picking, Shipped, Delivered, Cancelled, Archive
# models.py içindeki doğru import yolu varsayılıyor
from models import (
    db,
    OrderCreated,
    OrderPicking,
    OrderShipped,
    OrderDelivered,
    OrderCancelled,
    Archive
)

# Trendyol API kimlik bilgileri
# trendyol_api.py dosyasından import ediliyorsa:
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID # BASE_URL eklendi

# İsteğe bağlı: Sipariş detayı işleme, update service
# Bu importların doğru dosya yollarından yapıldığından emin olalım
from order_list_service import process_order_details # order_list_service.py'den
from update_service import update_package_to_picking # update_service.py'den

# Trendyol API için temel URL
BASE_URL = "https://api.trendyol.com/sapigw/"

# Blueprint
order_service_bp = Blueprint('order_service', __name__)

# Log ayarları
logger = logging.getLogger(__name__)
# Loglama yapılandırması merkezi bir yerden (örn: app factory) yapılmalı
# Ama şimdilik dosya bazlı loglama kalabilir.
log_file_path = os.path.join(os.path.dirname(__file__), 'logs', 'order_service.log')
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
handler = logging.FileHandler(log_file_path)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
if not logger.hasHandlers():
    logger.addHandler(handler)
    logger.setLevel(logging.INFO) # Veya DEBUG seviyesi

############################
# Statü -> Model eşlemesi
############################

STATUS_NORMALIZE = {
    'Created': 'Created',
    'Picking': 'Picking',
    'Invoiced': 'Picking',     # ← normalize
    'ReadyToShip': 'Created',  # ← normalize (kritik)
    'Cancelled': 'Cancelled',
    'Shipped': 'Shipped',
    'Delivered': 'Delivered',
}

STATUS_TABLE_MAP = {
    'Created':   OrderCreated,
    'Picking':   OrderPicking,
    'Cancelled': OrderCancelled,
    'Shipped':   OrderShipped,
    'Delivered': OrderDelivered,
}

############################
# 1) Trendyol'dan Sipariş Çekme (Asenkron)
############################
@order_service_bp.route('/fetch-trendyol-orders', methods=['POST'])
async def fetch_trendyol_orders_route():
    logger.info("Manuel Trendyol sipariş çekme işlemi tetiklendi.")
    try:
        await fetch_trendyol_orders_async()
        flash('Trendyol siparişleri başarıyla çekildi ve işlenmeye başlandı!', 'success')
    except Exception as e:
        logger.error(f"Hata: fetch_trendyol_orders_route - {e}", exc_info=True)
        flash('Siparişler çekilirken veya işlenirken bir hata oluştu.', 'danger')
    return redirect(url_for('order_list_service.order_list_all'))


async def fetch_trendyol_orders_async():
    logger.info("Asenkron Trendyol sipariş çekme işlemi başlıyor...")
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/orders"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }

        # ← ReadyToShip eklendi
        statuses_to_fetch = "Created,Picking,Invoiced,ReadyToShip,Shipped,Delivered,Cancelled"
        params = {
            "status": statuses_to_fetch,
            "page": 0,
            "size": 200,
            "orderByField": "PackageLastModifiedDate",
            "orderByDirection": "DESC"
        }

        all_orders_data = []
        total_pages = 1

        async with aiohttp.ClientSession() as session:
            logger.info("İlk sayfa çekiliyor...")
            async with session.get(url, headers=headers, params=params, timeout=60) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"API Hatası (İlk Sayfa): {response.status} - {error_text[:500]}")
                    if response.status == 401:
                        flash("Trendyol API kimlik bilgileri hatalı!", "danger")
                    return

                try:
                    data = await response.json()
                except Exception as json_e:
                    logger.error(f"API yanıtı JSON parse hatası (İlk Sayfa): {json_e}")
                    return

                content = data.get('content', []) or []
                all_orders_data.extend(content)
                total_pages = data.get('totalPages', 1)
                logger.info(f"Toplam sipariş sayısı (API): {data.get('totalElements', 0)}, Toplam sayfa sayısı: {total_pages}")

            if total_pages > 1:
                from asyncio import Semaphore, gather
                sem = Semaphore(10)
                tasks = []
                logger.info(f"Kalan {total_pages - 1} sayfa paralel olarak çekiliyor...")
                for page_num in range(1, total_pages):
                    params_page = dict(params, page=page_num)
                    tasks.append(fetch_orders_page(session, url, headers, params_page, sem))
                pages_results = await gather(*tasks, return_exceptions=True)
                for result in pages_results:
                    if isinstance(result, list):
                        all_orders_data.extend(result)
                    elif isinstance(result, Exception):
                        logger.error(f"Paralel sayfa çekme sırasında hata: {result}")

            logger.info(f"Toplam {len(all_orders_data)} sipariş verisi çekildi.")
            if all_orders_data:
                with current_app.app_context():
                    process_all_orders(all_orders_data)
            else:
                logger.info("İşlenecek yeni sipariş verisi bulunamadı.")

    except aiohttp.ClientError as client_e:
        logger.error(f"API bağlantı hatası: {client_e}")
        flash(f"Trendyol API'sine bağlanırken hata oluştu: {client_e}", "danger")
    except Exception as e:
        logger.error(f"Hata: fetch_trendyol_orders_async - {e}", exc_info=True)




async def fetch_orders_page(session, url, headers, params, semaphore):
    page_num_log = params.get('page', '?')
    async with semaphore:
        try:
            async with session.get(url, headers=headers, params=params, timeout=60) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                        content = data.get('content', []) or []
                        return content
                    except Exception as json_e:
                        logger.error(f"API JSON parse hatası (Sayfa {page_num_log}): {json_e}")
                        return []
                else:
                    error_text = await response.text()
                    logger.error(f"API isteği başarısız (Sayfa {page_num_log}): {response.status} - {error_text[:500]}")
                    return []
        except asyncio.TimeoutError:
            logger.error(f"API isteği zaman aşımı (Sayfa {page_num_log}).")
            return []
        except aiohttp.ClientError as client_e:
            logger.error(f"API bağlantı hatası (Sayfa {page_num_log}): {client_e}")
            return []
        except Exception as e:
            logger.error(f"Hata: fetch_orders_page (Sayfa {page_num_log}) - {e}", exc_info=True)
            return []



############################
# 2) Gelen Siparişleri İşleme (Senkron ve Arka Plan Ayrımı)
############################
def process_all_orders(all_orders_data):
    logger.info(f"{len(all_orders_data)} adet sipariş verisi işleniyor...")
    try:
        if not all_orders_data:
            logger.info("İşlenecek sipariş verisi yok.")
            return

        archived_numbers = set(
            o.order_number for o in Archive.query.with_entities(Archive.order_number).all()
        )

        sync_orders = []  # Created / Picking (/ Invoiced / ReadyToShip → Picking) / Cancelled
        bg_orders   = []  # Shipped / Delivered
        processed_numbers = set()

        for order_data in all_orders_data:
            if not isinstance(order_data, dict):
                continue

            order_number = str(order_data.get('orderNumber') or order_data.get('id', ''))
            if not order_number:
                continue
            if order_number in processed_numbers or order_number in archived_numbers:
                continue
            processed_numbers.add(order_number)

            raw_status = (order_data.get('status') or '').strip()
            norm = STATUS_NORMALIZE.get(raw_status)
            if not norm:
                logger.warning(f"Sipariş {order_number}: Tanımsız statü '{raw_status}', atlandı.")
                continue

            if norm in ('Created', 'Picking', 'Cancelled'):
                sync_orders.append({**order_data, '_normalizedStatus': norm})
            elif norm in ('Shipped', 'Delivered'):
                bg_orders.append({**order_data, '_normalizedStatus': norm})

        logger.info(f"İşlenecek Senkron Sipariş Sayısı: {len(sync_orders)}")
        logger.info(f"İşlenecek Arka Plan Sipariş Sayısı: {len(bg_orders)}")

        if sync_orders:
            _process_sync_orders_bulk(sync_orders)

        if bg_orders:
            app = current_app._get_current_object()
            thread = threading.Thread(target=process_bg_orders_bulk, args=(bg_orders, app), daemon=True)
            thread.start()
            logger.info("Shipped/Delivered siparişleri için arka plan işleyici başlatıldı.")

    except SQLAlchemyError as db_e:
        logger.error(f"process_all_orders veritabanı hatası: {db_e}", exc_info=True)
        db.session.rollback()
    except Exception as e:
        logger.error(f"Hata: process_all_orders - {e}", exc_info=True)


def _process_sync_orders_bulk(sync_orders):
    if not sync_orders:
        return

    logger.info(f"{len(sync_orders)} adet senkron sipariş işleniyor (Created / Picking / Cancelled)...")
    try:
        db.session.rollback()

        order_numbers = {
            str(od.get('orderNumber') or od.get('id')) for od in sync_orders if od.get('orderNumber') or od.get('id')
        }

        existing_orders = {}
        relevant_tables = [OrderCreated, OrderPicking, OrderCancelled]

        for table_model in relevant_tables:
            try:
                records = table_model.query.filter(table_model.order_number.in_(order_numbers)).all()
                for record in records:
                    existing_orders.setdefault(
                        record.order_number, {'record': record, 'table': table_model.__tablename__}
                    )
            except Exception as e:
                logger.error(f"{table_model.__tablename__} sorgusunda hata: {e}", exc_info=True)

        to_insert_created, to_insert_picking, to_insert_cancelled = [], [], []
        to_delete_ids = {tbl.__tablename__: [] for tbl in relevant_tables}

        for order_data in sync_orders:
            order_number = str(order_data.get('orderNumber') or order_data.get('id'))
            if not order_number:
                continue

            # normalize edilmiş statü ile devam
            status = order_data.get('_normalizedStatus') or (order_data.get('status') or '').strip()
            target_model = STATUS_TABLE_MAP.get(status)
            if not target_model:
                continue

            new_data_dict = combine_line_items(order_data, status)
            if not new_data_dict:
                continue

            existing_info = existing_orders.get(order_number)
            if existing_info:
                current_record = existing_info['record']
                current_table = existing_info['table']
                target_table = target_model.__tablename__

                if current_table != target_table:
                    logger.info(f"Statü değişimi: {order_number} {current_table} ➝ {target_table}")
                    to_delete_ids[current_table].append(current_record.id)
                    if target_model == OrderCreated:
                        to_insert_created.append(new_data_dict)
                    elif target_model == OrderPicking:
                        to_insert_picking.append(new_data_dict)
                    elif target_model == OrderCancelled:
                        to_insert_cancelled.append(new_data_dict)
                else:
                    _minimal_update_if_needed(current_record, new_data_dict)
            else:
                if target_model == OrderCreated:
                    to_insert_created.append(new_data_dict)
                elif target_model == OrderPicking:
                    to_insert_picking.append(new_data_dict)
                elif target_model == OrderCancelled:
                    to_insert_cancelled.append(new_data_dict)

        for table_name, ids in to_delete_ids.items():
            if ids:
                model = next(t for t in relevant_tables if t.__tablename__ == table_name)
                model.query.filter(model.id.in_(ids)).delete(synchronize_session=False)
                logger.info(f"{len(ids)} kayıt {table_name} tablosundan silindi.")

        if to_insert_created:
            db.session.bulk_insert_mappings(OrderCreated, to_insert_created)
        if to_insert_picking:
            db.session.bulk_insert_mappings(OrderPicking, to_insert_picking)
        if to_insert_cancelled:
            db.session.bulk_insert_mappings(OrderCancelled, to_insert_cancelled)

        db.session.commit()
        logger.info("Senkron sipariş işlemleri başarıyla tamamlandı.")

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"SQLAlchemy Hatası (Sync Orders): {e}", exc_info=True)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Genel Hata (Sync Orders): {e}", exc_info=True)
    finally:
        db.session.remove()




def _minimal_update_if_needed(record_obj, new_data_dict):
    changed = False
    fields_to_check = {
        'status': 'status',
        'order_date': 'order_date',
        'product_barcode': 'product_barcode',
        'quantity': 'quantity',
        'commission': 'commission',
        'details': 'details',
        'cargo_tracking_number': 'shipping_barcode',
        'cargo_provider_name': 'cargo_provider_name',
        'customer_name': 'customer_name',
        'customer_surname': 'customer_surname',
        'customer_address': 'customer_address',
    }

    for attr_name, dict_key in fields_to_check.items():
        if hasattr(record_obj, attr_name):
            old_value = getattr(record_obj, attr_name)
            new_value = new_data_dict.get(dict_key)

            if attr_name == 'details':
                try:
                    old_json = json.loads(old_value) if isinstance(old_value, str) and old_value else None
                    new_json = json.loads(new_value) if isinstance(new_value, str) and new_value else None
                    if old_json != new_json:
                        setattr(record_obj, attr_name, new_value)
                        changed = True
                except Exception:
                    if old_value != new_value:
                        setattr(record_obj, attr_name, new_value)
                        changed = True
            elif old_value != new_value:
                setattr(record_obj, attr_name, new_value)
                changed = True

    if changed and hasattr(record_obj, 'updated_at'):
        setattr(record_obj, 'updated_at', datetime.utcnow())

    return changed


############################
# 3) BG: Shipped/Delivered
############################
def process_bg_orders_bulk(bg_orders, app):
    with app.app_context():
        logger.info(f"BG İşleyici: {len(bg_orders)} adet Shipped/Delivered sipariş işleniyor...")

        if not bg_orders:
            return

        try:
            db.session.rollback()

            order_numbers = {
                str(od.get('orderNumber') or od.get('id')) for od in bg_orders if od.get('orderNumber') or od.get('id')
            }
            relevant_tables = [OrderPicking, OrderShipped, OrderDelivered]

            existing_orders = {}
            for table_model in relevant_tables:
                try:
                    records = table_model.query.filter(table_model.order_number.in_(order_numbers)).all()
                    for record in records:
                        existing_orders.setdefault(
                            record.order_number, {'record': record, 'table': table_model.__tablename__}
                        )
                except Exception as q_err:
                    logger.error(f"BG: {table_model.__tablename__} sorgulanırken hata: {q_err}", exc_info=True)

            to_insert_shipped, to_insert_delivered = [], []
            to_delete_ids = {tbl.__tablename__: [] for tbl in relevant_tables}

            for order_data in bg_orders:
                order_number = str(order_data.get('orderNumber') or order_data.get('id'))
                if not order_number:
                    continue

                norm = order_data.get('_normalizedStatus') or (order_data.get('status') or '').strip()
                target_model = STATUS_TABLE_MAP.get(norm)
                if not target_model or target_model not in (OrderShipped, OrderDelivered):
                    logger.warning(f"BG: {order_number} için geçersiz statü '{norm}'")
                    continue

                new_data_dict = combine_line_items(order_data, norm)
                if not new_data_dict:
                    continue

                existing_info = existing_orders.get(order_number)
                if existing_info:
                    current_record = existing_info['record']
                    current_table = existing_info['table']
                    target_table = target_model.__tablename__

                    if current_table != target_table:
                        logger.info(f"BG: {order_number} statü geçişi: {current_table} ➝ {target_table}")
                        to_delete_ids[current_table].append(current_record.id)
                        if target_model == OrderShipped:
                            to_insert_shipped.append(new_data_dict)
                        elif target_model == OrderDelivered:
                            to_insert_delivered.append(new_data_dict)
                    else:
                        _minimal_update_if_needed(current_record, new_data_dict)
                else:
                    if target_model == OrderShipped:
                        to_insert_shipped.append(new_data_dict)
                    elif target_model == OrderDelivered:
                        to_insert_delivered.append(new_data_dict)

            for table_name, ids in to_delete_ids.items():
                if ids:
                    model = next(t for t in relevant_tables if t.__tablename__ == table_name)
                    model.query.filter(model.id.in_(ids)).delete(synchronize_session=False)

            if to_insert_shipped:
                db.session.bulk_insert_mappings(OrderShipped, to_insert_shipped)
            if to_insert_delivered:
                db.session.bulk_insert_mappings(OrderDelivered, to_insert_delivered)

            db.session.commit()
            logger.info("BG: Tüm işlemler tamamlandı.")

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"⛔ BG SQLAlchemy hatası: {e}", exc_info=True)
        except Exception as e:
            db.session.rollback()
            logger.error(f"⛔ BG genel hata: {e}", exc_info=True)
        finally:
            db.session.remove()




############################
# Yardımcılar
############################
def safe_int(val, default=0):
    if val is None: return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def safe_float(val, default=0.0):
    if val is None: return default
    try:
        if isinstance(val, str):
            val = val.replace(',', '.')
        return float(val)
    except (ValueError, TypeError):
        return default



def create_order_details(lines):
    details_dict = {}
    total_order_quantity = 0
    if not isinstance(lines, list):
        logger.warning("create_order_details: 'lines' liste değil.")
        return [], 0

    for line in lines:
        if not isinstance(line, dict):
            continue

        barcode = line.get('barcode', '')
        color = line.get('productColor', '')
        size_ = line.get('productSize', '')
        quantity = safe_int(line.get('quantity'), 0)
        total_order_quantity += quantity
        commission_fee = safe_float(line.get('commissionFee'), 0.0)
        line_id = str(line.get('id', ''))
        amount = safe_float(line.get('amount'), 0.0)

        key = (barcode, color, size_)
        if key not in details_dict:
            details_dict[key] = {
                'barcode': barcode,
                'color': color,
                'size': size_,
                'sku': line.get('merchantSku', ''),
                'productName': line.get('productName', ''),
                'productCode': str(line.get('productCode', '')),
                'product_main_id': str(line.get('productId', '')),
                'quantity': quantity,
                'commissionFee': commission_fee,
                'line_id': [line_id],
                'unit_price': amount,
                'line_total_price': amount * quantity
            }
        else:
            details_dict[key]['quantity'] += quantity
            details_dict[key]['commissionFee'] += commission_fee
            details_dict[key]['line_id'].append(line_id)
            details_dict[key]['line_total_price'] += amount * quantity

    for item_details in details_dict.values():
        item_details['line_id'] = ','.join(item_details['line_id'])

    return list(details_dict.values()), total_order_quantity


def combine_line_items(order_data, status):
    if not isinstance(order_data, dict):
        return None

    lines = order_data.get('lines', [])
    if not isinstance(lines, list):
        lines = []

    details_list, total_qty = create_order_details(lines)

    original_barcodes = [item.get('barcode', '') for item in details_list if item.get('barcode')]

    from json import dumps
    def ts_to_dt(timestamp_ms):
        if not timestamp_ms: return None
        try:
            ts = float(timestamp_ms)
            return datetime.utcfromtimestamp(ts / 1000.0)
        except (ValueError, TypeError, OverflowError):
            return None

    db_record_dict = {
        'order_number': str(order_data.get('orderNumber', order_data.get('id', ''))),
        'order_date': ts_to_dt(order_data.get('orderDate')),
        'merchant_sku': ', '.join(item.get('sku', '') for item in details_list),
        'product_barcode': ', '.join(original_barcodes),
        'status': status,  # ← normalize edilmiş statü
        'line_id': ','.join(item.get('line_id', '') for item in details_list),
        'match_status': '',
        'customer_name': order_data.get('shipmentAddress', {}).get('firstName', ''),
        'customer_surname': order_data.get('shipmentAddress', {}).get('lastName', ''),
        'customer_address': order_data.get('shipmentAddress', {}).get('fullAddress', ''),
        'shipping_barcode': order_data.get('cargoTrackingNumber', ''),
        'cargo_tracking_number': order_data.get('cargoTrackingNumber', ''),
        'cargo_provider_name': order_data.get('cargoProviderName', ''),
        'cargo_tracking_link': order_data.get('cargoTrackingLink', ''),
        'product_name': ', '.join(item.get('productName', '') for item in details_list),
        'product_code': ', '.join(item.get('productCode', '') for item in details_list),
        'product_size': ', '.join(item.get('size', '') for item in details_list),
        'product_color': ', '.join(item.get('color', '') for item in details_list),
        'product_main_id': ', '.join(item.get('product_main_id', '') for item in details_list),
        'stockCode': ', '.join(item.get('sku', '') for item in details_list),
        'amount': sum(item.get('line_total_price', 0.0) for item in details_list),
        'discount': sum(safe_float(line.get('discount'), 0) for line in lines),
        'currency_code': order_data.get('currencyCode', 'TRY'),
        'vat_base_amount': sum(safe_float(line.get('vatBaseAmount'), 0) for line in lines),
        'package_number': str(order_data.get('id', '')),
        'shipment_package_id': str(order_data.get('shipmentPackageId', '')),
        'estimated_delivery_start': ts_to_dt(order_data.get('estimatedDeliveryStartDate')),
        'estimated_delivery_end': ts_to_dt(order_data.get('estimatedDeliveryEndDate')),
        'origin_shipment_date': ts_to_dt(order_data.get('originShipmentDate')),
        'agreed_delivery_date': ts_to_dt(order_data.get('agreedDeliveryDate')),
        'details': dumps(details_list, ensure_ascii=False, indent=None, separators=(',', ':')),
        'quantity': total_qty,
        'commission': sum(item.get('commissionFee', 0.0) for item in details_list),
        'source': 'TRENDYOL'  # 🔥 KAYNAK BİLGİSİ
    }
    return db_record_dict


############################
# 4) Sipariş Listeleme Rotaları (Değişiklik Yok)
############################
# Bu rotalarda barkod dönüştürme ile ilgili bir işlem yoktu,
# sadece veritabanından çekip process_order_details'e gönderiyorlar.
# process_order_details fonksiyonu da barkod dönüştürme yapmıyorsa,
# bu rotalar olduğu gibi kalabilir.

############################
# 4) Listeleme Rotaları
############################
@order_service_bp.route('/order-list/new', methods=['GET'])
def get_new_orders():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    try:
        query = OrderCreated.query.order_by(OrderCreated.order_date.desc())
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        orders = paginated.items
        process_order_details(orders)
    except Exception as e:
        logger.error(f"Yeni sipariş listesi alınırken hata: {e}", exc_info=True)
        flash("Yeni siparişler yüklenirken bir hata oluştu.", "danger")
        orders, paginated = [], None

    return render_template(
        'order_list.html',
        orders=orders,
        pagination=paginated,
        page=paginated.page if paginated else 1,
        total_pages=paginated.pages if paginated else 1,
        total_orders_count=paginated.total if paginated else len(orders),
        list_title="Yeni Siparişler",
        active_list='new'
    )



@order_service_bp.route('/order-list/picking', methods=['GET'])
def get_picking_orders():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    try:
        query = OrderPicking.query.order_by(OrderPicking.order_date.desc())
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        orders = paginated.items
        process_order_details(orders)
    except Exception as e:
        logger.error(f"Picking sipariş listesi alınırken hata: {e}", exc_info=True)
        flash("Hazırlanan siparişler yüklenirken bir hata oluştu.", "danger")
        orders, paginated = [], None

    return render_template(
        'order_list.html',
        orders=orders,
        pagination=paginated,
        page=paginated.page if paginated else 1,
        total_pages=paginated.pages if paginated else 1,
        total_orders_count=paginated.total if paginated else len(orders),
        list_title="Hazırlanan (Picking) + ReadyToShip",
        active_list='picking'
    )


@order_service_bp.route('/order-list/shipped', methods=['GET'])
def get_shipped_orders():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    try:
        query = OrderShipped.query.order_by(OrderShipped.order_date.desc())
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        orders = paginated.items
        process_order_details(orders)
    except Exception as e:
        logger.error(f"Shipped sipariş listesi alınırken hata: {e}", exc_info=True)
        flash("Kargodaki siparişler yüklenirken bir hata oluştu.", "danger")
        orders, paginated = [], None

    return render_template(
        'order_list.html',
        orders=orders,
        pagination=paginated,
        page=paginated.page if paginated else 1,
        total_pages=paginated.pages if paginated else 1,
        total_orders_count=paginated.total if paginated else len(orders),
        list_title="Kargodaki Siparişler",
        active_list='shipped'
    )



@order_service_bp.route('/order-list/delivered', methods=['GET'])
def get_delivered_orders():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    try:
        query = OrderDelivered.query.order_by(OrderDelivered.order_date.desc())
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        orders = paginated.items
        process_order_details(orders)
    except Exception as e:
        logger.error(f"Delivered sipariş listesi alınırken hata: {e}", exc_info=True)
        flash("Teslim Edilen siparişler yüklenirken bir hata oluştu.", "danger")
        orders, paginated = [], None

    return render_template(
        'order_list.html',
        orders=orders,
        pagination=paginated,
        page=paginated.page if paginated else 1,
        total_pages=paginated.pages if paginated else 1,
        total_orders_count=paginated.total if paginated else len(orders),
        list_title="Teslim Edilen Siparişler",
        active_list='delivered'
    )


@order_service_bp.route('/order-list/cancelled', methods=['GET'])
def get_cancelled_orders():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    try:
        query = OrderCancelled.query.order_by(OrderCancelled.order_date.desc())
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        orders = paginated.items
        process_order_details(orders)
    except Exception as e:
        logger.error(f"Cancelled sipariş listesi alınırken hata: {e}", exc_info=True)
        flash("İptal Edilen siparişler yüklenirken bir hata oluştu.", "danger")
        orders, paginated = [], None

    return render_template(
        'order_list.html',
        orders=orders,
        pagination=paginated,
        page=paginated.page if paginated else 1,
        total_pages=paginated.pages if paginated else 1,
        total_orders_count=paginated.total if paginated else len(orders),
        list_title="İptal Edilen Siparişler",
        active_list='cancelled'
    )