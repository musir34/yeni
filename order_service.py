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
    OrderArchived
)

# Trendyol API kimlik bilgileri
# trendyol_api.py dosyasından import ediliyorsa:
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL # BASE_URL eklendi

# İsteğe bağlı: Sipariş detayı işleme, update service
# Bu importların doğru dosya yollarından yapıldığından emin olalım
from order_list_service import process_order_details # order_list_service.py'den
from update_service import update_package_to_picking # update_service.py'den

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
STATUS_TABLE_MAP = {
    'Created':   OrderCreated,
    'Picking':   OrderPicking,
    'Invoiced':  OrderPicking,  # Invoiced -> picking tablosu
    'Shipped':   OrderShipped,
    'Delivered': OrderDelivered,
    'Cancelled': OrderCancelled
}

############################
# 1) Trendyol'dan Sipariş Çekme (Asenkron)
############################
@order_service_bp.route('/fetch-trendyol-orders', methods=['POST'])
# @role_required('admin', 'manager') # Yetkilendirme eklenmeli
async def fetch_trendyol_orders_route():
    """
    UI veya Postman vb. üzerinden tetiklenen endpoint.
    Asenkron olarak Trendyol siparişlerini çeker.
    """
    logger.info("Manuel Trendyol sipariş çekme işlemi tetiklendi.")
    try:
        # asyncio.run yerine Flask'ın async desteği varsa o kullanılmalı
        # Veya arka plan görevi olarak çalıştırmak daha uygun olabilir.
        # Şimdilik asyncio.run varsayımıyla devam edelim.
        await fetch_trendyol_orders_async()
        flash('Trendyol siparişleri başarıyla çekildi ve işlenmeye başlandı!', 'success')
    except Exception as e:
        logger.error(f"Hata: fetch_trendyol_orders_route - {e}", exc_info=True)
        # traceback.print_exc() # Loglama zaten yapıyor
        flash('Siparişler çekilirken veya işlenirken bir hata oluştu.', 'danger')
    # İşlem sonrası sipariş listesine yönlendir
    return redirect(url_for('order_list_service.order_list_all')) # Veya ilgili liste sayfasına


async def fetch_trendyol_orders_async():
    """
    Trendyol API'ye asenkron istek atar, tüm sayfaları paralel çekip
    process_all_orders fonksiyonuna iletir.
    """
    logger.info("Asenkron Trendyol sipariş çekme işlemi başlıyor...")
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        # BASE_URL trendyol_api.py'den import edildi varsayılıyor
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/orders"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }

        # Çekilecek statüler ve diğer parametreler
        statuses_to_fetch = "Created,Picking,Invoiced,Shipped,Delivered,Cancelled"
        params = {
            "status": statuses_to_fetch,
            "page": 0,
            "size": 200,  # Sayfa boyutu (API limitine göre ayarla, 500 yerine 200 daha stabil olabilir)
            "orderByField": "PackageLastModifiedDate", # Veya orderDate
            "orderByDirection": "DESC" # En yeniden eskiye
            # "startDate": ..., # Belirli bir tarih aralığı eklenebilir (performans için)
            # "endDate": ...
        }
        logger.debug(f"Trendyol API isteği: URL={url}, Params={params}")

        all_orders_data = []
        page_number = 0
        total_pages = 1 # İlk başta 1 sayfa varsay

        async with aiohttp.ClientSession() as session:
            # İlk sayfayı çek ve toplam sayfa sayısını öğren
            logger.info("İlk sayfa çekiliyor...")
            async with session.get(url, headers=headers, params=params, timeout=60) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"API Hatası (İlk Sayfa): {response.status} - {error_text[:500]}")
                    # Kimlik doğrulama hatasıysa flash mesaj verilebilir
                    if response.status == 401:
                         flash("Trendyol API kimlik bilgileri hatalı!", "danger")
                    return # İlk sayfa çekilemezse devam etme

                try:
                    data = await response.json()
                except Exception as json_e:
                     logger.error(f"API yanıtı JSON parse hatası (İlk Sayfa): {json_e} - Yanıt: {await response.text()[:500]}")
                     return

                if not isinstance(data, dict):
                     logger.error(f"API yanıtı beklenmedik formatta (dict değil): {data}")
                     return

                current_page_orders = data.get('content', [])
                if isinstance(current_page_orders, list):
                     all_orders_data.extend(current_page_orders)
                else:
                     logger.error(f"API yanıtındaki 'content' liste değil: {current_page_orders}")

                total_elements = data.get('totalElements', 0)
                total_pages = data.get('totalPages', 1)
                logger.info(f"Toplam sipariş sayısı (API): {total_elements}, Toplam sayfa sayısı: {total_pages}")

            # Eğer birden fazla sayfa varsa, kalanları paralel çek
            if total_pages > 1:
                 from asyncio import Semaphore, gather
                 sem = Semaphore(10) # Aynı anda max 10 istek
                 tasks = []
                 logger.info(f"Kalan {total_pages - 1} sayfa paralel olarak çekiliyor...")
                 for page_num in range(1, total_pages):
                      params_page = dict(params, page=page_num)
                      tasks.append(fetch_orders_page(session, url, headers, params_page, sem))

                 # Görevleri çalıştır ve sonuçları topla
                 pages_results = await gather(*tasks, return_exceptions=True) # Hataları da yakala

                 for result in pages_results:
                      if isinstance(result, list): # Başarılı sonuç (liste döndü)
                           all_orders_data.extend(result)
                      elif isinstance(result, Exception): # Görev hata ile sonuçlandı
                           logger.error(f"Paralel sayfa çekme sırasında hata: {result}")
                      # else: Beklenmedik durum (örn: None döndü), fetch_orders_page loglamış olmalı

            logger.info(f"Toplam {len(all_orders_data)} sipariş verisi çekildi.")

            # Çekilen veriyi işlemeye gönder (app context içinde)
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
        # flash('Siparişler çekilirken bilinmeyen bir hata oluştu.', 'danger') # Route zaten flash veriyor

async def fetch_orders_page(session, url, headers, params, semaphore):
    """
    Belirli sayfadaki siparişleri asenkron çekme fonksiyonu.
    """
    page_num_log = params.get('page', '?')
    async with semaphore: # Eş zamanlı istekleri sınırla
        try:
            logger.debug(f"Sayfa {page_num_log} çekiliyor...")
            async with session.get(url, headers=headers, params=params, timeout=60) as response:
                if response.status == 200:
                    try:
                         data = await response.json()
                         if isinstance(data, dict):
                              content = data.get('content', [])
                              if isinstance(content, list):
                                   logger.debug(f"Sayfa {page_num_log}: {len(content)} sipariş çekildi.")
                                   return content # Başarılı, sipariş listesini döndür
                              else:
                                   logger.error(f"API yanıtı 'content' liste değil (Sayfa {page_num_log}).")
                                   return [] # Hata, boş liste döndür
                         else:
                              logger.error(f"API yanıtı dict değil (Sayfa {page_num_log}): {await response.text()[:500]}")
                              return []
                    except Exception as json_e:
                         logger.error(f"API JSON parse hatası (Sayfa {page_num_log}): {json_e} - Yanıt: {await response.text()[:500]}")
                         return []
                else:
                    # API'den hata durumu döndü
                    error_text = await response.text()
                    logger.error(f"API isteği başarısız oldu (Sayfa {page_num_log}): {response.status} - {error_text[:500]}")
                    return [] # Hata, boş liste döndür
        except asyncio.TimeoutError:
            logger.error(f"API isteği zaman aşımı (Sayfa {page_num_log}).")
            return []
        except aiohttp.ClientError as client_e:
             logger.error(f"API bağlantı hatası (Sayfa {page_num_log}): {client_e}")
             return []
        except Exception as e:
            logger.error(f"Hata: fetch_orders_page (Sayfa {page_num_log}) - {e}", exc_info=True)
            return [] # Genel hata, boş liste döndür










############################
# 2) Gelen Siparişleri İşleme (Senkron ve Arka Plan Ayrımı)
############################
def process_all_orders(all_orders_data):
    """
    API'den gelen tüm siparişleri alır, statülerine göre ayırır ve ilgili
    işleme fonksiyonlarına yönlendirir. Arşiv kontrolü yapar.
    (Bu fonksiyon Flask app context içinde çağrılmalıdır)
    """
    logger.info(f"{len(all_orders_data)} adet sipariş verisi işleniyor...")
    try:
        if not all_orders_data:
            logger.info("İşlenecek sipariş verisi yok.")
            return

        # 1) Arşivdeki sipariş numaralarını çek (performans için sadece numaralar)
        archived_numbers = set(o.order_number for o in OrderArchived.query.with_entities(OrderArchived.order_number).all())
        logger.debug(f"Arşivde {len(archived_numbers)} sipariş bulundu.")

        # 2) Siparişleri statüye göre ayır ve arşiv kontrolü yap
        sync_orders = []  # Created / Picking / Invoiced / Cancelled
        bg_orders   = []  # Shipped / Delivered
        processed_numbers = set() # Aynı sipariş numarasını tekrar işlememek için

        for order_data in all_orders_data:
             if not isinstance(order_data, dict):
                  logger.warning(f"Geçersiz sipariş verisi formatı (dict değil), atlanıyor: {order_data}")
                  continue

             order_number = str(order_data.get('orderNumber') or order_data.get('id', '')) # id fallback?
             if not order_number:
                  logger.warning(f"Sipariş numarası alınamayan veri, atlanıyor: {order_data}")
                  continue

             # Daha önce işlenen veya arşivde olanları atla
             if order_number in processed_numbers:
                 continue
             if order_number in archived_numbers:
                 logger.debug(f"Sipariş {order_number} arşivde, işleme atlanıyor.")
                 continue

             processed_numbers.add(order_number)

             status = (order_data.get('status') or '').strip()
             if not status:
                  logger.warning(f"Sipariş {order_number} için statü bilgisi yok, atlanıyor.")
                  continue

             # Statüye göre ayır
             if status in ('Created', 'Picking', 'Invoiced', 'Cancelled'):
                 sync_orders.append(order_data)
             elif status in ('Shipped', 'Delivered'):
                 bg_orders.append(order_data)
             else:
                 logger.warning(f"Sipariş {order_number}: Tanımsız statü '{status}', işlenmiyor.")

        logger.info(f"İşlenecek Senkron Sipariş Sayısı: {len(sync_orders)}")
        logger.info(f"İşlenecek Arka Plan Sipariş Sayısı: {len(bg_orders)}")

        # 3) Senkron siparişleri işle (bulk)
        if sync_orders:
            _process_sync_orders_bulk(sync_orders)

        # 4) Arka plan siparişlerini işle (thread)
        if bg_orders:
            # Flask app context'ini thread'e geçmek için
            app = current_app._get_current_object()
            thread = threading.Thread(target=process_bg_orders_bulk, args=(bg_orders, app), daemon=True)
            thread.start()
            logger.info("Shipped/Delivered siparişleri için arka plan işleyici başlatıldı.")

    except SQLAlchemyError as db_e:
         logger.error(f"process_all_orders veritabanı hatası: {db_e}", exc_info=True)
         db.session.rollback() # Rollback yapalım
    except Exception as e:
        logger.error(f"Hata: process_all_orders - {e}", exc_info=True)
        # db.session.rollback() # Beklenmedik hatalarda da rollback faydalı olabilir

def _process_sync_orders_bulk(sync_orders):
    if not sync_orders:
        return

    logger.info(f"{len(sync_orders)} adet senkron sipariş işleniyor (Created / Picking / Cancelled)...")

    try:
        db.session.rollback()  # Önceki işlem varsa sıfırla

        order_numbers = {str(od.get('orderNumber') or od.get('id')) for od in sync_orders if od.get('orderNumber') or od.get('id')}

        existing_orders = {}
        relevant_tables = [OrderCreated, OrderPicking, OrderCancelled]

        for table_model in relevant_tables:
            try:
                records = table_model.query.filter(table_model.order_number.in_(order_numbers)).all()
                for record in records:
                    existing_orders.setdefault(record.order_number, {'record': record, 'table': table_model.__tablename__})
            except Exception as e:
                logger.error(f"{table_model.__tablename__} sorgusunda hata: {e}", exc_info=True)

        to_insert_created, to_insert_picking, to_insert_cancelled = [], [], []
        to_delete_ids = {tbl.__tablename__: [] for tbl in relevant_tables}

        for order_data in sync_orders:
            order_number = str(order_data.get('orderNumber') or order_data.get('id'))
            if not order_number:
                logger.error("order_number eksik, sipariş atlandı.")
                continue

            status = (order_data.get('status') or '').strip()
            if status == 'Invoiced':
                status = 'Picking'

            target_model = STATUS_TABLE_MAP.get(status)
            if not target_model:
                continue

            new_data_dict = combine_line_items(order_data, status)
            if not new_data_dict:
                logger.error(f"Sipariş {order_number} için veri oluşturulamadı.")
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
    """
    Mevcut veritabanı kaydını yeni veriyle karşılaştırır.
    Sadece değişen alanları günceller ve değişiklik olup olmadığını döner.
    """
    changed = False
    # Güncellenebilecek alanları ve dict'teki karşılıklarını tanımla
    fields_to_check = {
        'status': 'status',
        'order_date': 'order_date',
        'product_barcode': 'product_barcode', # Artık sadece orijinal barkod listesi
        'quantity': 'quantity',
        'commission': 'commission',
        'details': 'details', # JSON string olduğu için her zaman değişmiş gibi görünebilir, dikkatli karşılaştırılmalı
        'cargo_tracking_number': 'shipping_barcode', # Modelde 'cargo_tracking_number' ise
        'cargo_provider_name': 'cargo_provider_name',
        # ... diğer güncellenmesi gereken alanlar ...
        'customer_name': 'customer_name',
        'customer_surname': 'customer_surname',
        'customer_address': 'customer_address',
    }

    for attr_name, dict_key in fields_to_check.items():
        if hasattr(record_obj, attr_name):
            old_value = getattr(record_obj, attr_name)
            new_value = new_data_dict.get(dict_key)

            # JSON ('details') alanı için özel karşılaştırma (isteğe bağlı, performans etkileyebilir)
            if attr_name == 'details':
                 try:
                      # Stringleri JSON'a çevirip karşılaştır
                      old_json = json.loads(old_value) if isinstance(old_value, str) and old_value else None
                      new_json = json.loads(new_value) if isinstance(new_value, str) and new_value else None
                      if old_json != new_json: # İçerik farklıysa güncelle
                           setattr(record_obj, attr_name, new_value)
                           changed = True
                 except json.JSONDecodeError:
                      # Parse edilemiyorsa, string olarak karşılaştır veya her zaman güncelle
                      if old_value != new_value:
                           setattr(record_obj, attr_name, new_value)
                           changed = True
                 except Exception as json_comp_err:
                      logger.warning(f"Detay JSON karşılaştırma hatası: {json_comp_err}. Direkt güncelleme yapılıyor.")
                      if old_value != new_value: # Güvenli fallback
                            setattr(record_obj, attr_name, new_value)
                            changed = True

            # Diğer alanlar için normal karşılaştırma
            elif old_value != new_value:
                 # Tarih/saat alanları için tip kontrolü ve karşılaştırma
                 if isinstance(old_value, datetime) and isinstance(new_value, datetime):
                      # Zaman dilimi farkı varsa veya milisaniye hassasiyeti önemliyse dikkat!
                      # Basit karşılaştırma yeterli olabilir:
                      if old_value != new_value:
                           setattr(record_obj, attr_name, new_value)
                           changed = True
                 # Diğer tipler için direkt karşılaştırma
                 else:
                      setattr(record_obj, attr_name, new_value)
                      changed = True

    # Eğer değişiklik yapıldıysa updated_at gibi bir alanı güncellemek iyi olabilir
    if changed and hasattr(record_obj, 'updated_at'):
         setattr(record_obj, 'updated_at', datetime.utcnow())

    return changed


############################
# 3) Arka Plan Shipped/Delivered (Toplu Yaklaşım)
############################
def process_bg_orders_bulk(bg_orders, app):
    with app.app_context():
        logger.info(f"BG İşleyici: {len(bg_orders)} adet Shipped/Delivered sipariş işleniyor...")

        if not bg_orders:
            logger.info("İşlenecek arka plan siparişi yok.")
            return

        try:
            db.session.rollback()  # Aktif transaction varsa sıfırla

            order_numbers = {str(od.get('orderNumber') or od.get('id')) for od in bg_orders if od.get('orderNumber') or od.get('id')}
            relevant_tables = [OrderPicking, OrderShipped, OrderDelivered]

            existing_orders = {}
            for table_model in relevant_tables:
                try:
                    records = table_model.query.filter(table_model.order_number.in_(order_numbers)).all()
                    for record in records:
                        existing_orders.setdefault(record.order_number, {'record': record, 'table': table_model.__tablename__})
                except Exception as q_err:
                    logger.error(f"BG: {table_model.__tablename__} sorgulanırken hata: {q_err}", exc_info=True)

            to_insert_shipped, to_insert_delivered = [], []
            to_delete_ids = {tbl.__tablename__: [] for tbl in relevant_tables}

            for order_data in bg_orders:
                order_number = str(order_data.get('orderNumber') or order_data.get('id'))
                if not order_number:
                    logger.error("BG: order_number boş, işlem atlandı.")
                    continue

                status = (order_data.get('status') or '').strip()
                target_model = STATUS_TABLE_MAP.get(status)
                if not target_model or target_model not in (OrderShipped, OrderDelivered):
                    logger.warning(f"BG: {order_number} için geçersiz statü '{status}'")
                    continue

                new_data_dict = combine_line_items(order_data, status)
                if not new_data_dict:
                    logger.error(f"BG: {order_number} için veri oluşturulamadı.")
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
                    logger.info(f"BG: {len(ids)} kayıt {table_name} tablosundan silindi.")

            if to_insert_shipped:
                db.session.bulk_insert_mappings(OrderShipped, to_insert_shipped)
            if to_insert_delivered:
                db.session.bulk_insert_mappings(OrderDelivered, to_insert_delivered)

            db.session.commit()
            logger.info("BG: Tüm işlemler başarıyla tamamlandı ve commit edildi.")

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"⛔ BG SQLAlchemy hatası: {e}", exc_info=True)
        except Exception as e:
            db.session.rollback()
            logger.error(f"⛔ BG genel hata: {e}", exc_info=True)
        finally:
            db.session.remove()




############################
# Yardımcı Fonksiyonlar
############################
def safe_int(val, default=0):
    """String veya None'ı güvenli şekilde int'e çevirir."""
    if val is None: return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def safe_float(val, default=0.0):
    """String veya None'ı güvenli şekilde float'a çevirir."""
    if val is None: return default
    try:
        # Virgüllü sayıları da handle etmek için (örn: "10,5")
        if isinstance(val, str):
             val = val.replace(',', '.')
        return float(val)
    except (ValueError, TypeError):
        return default

# --- Barkod Dönüştürme Fonksiyonları KALDIRILDI ---
# def replace_turkish_characters_cached(text): ...
# def replace_turkish_characters(text): ...

def create_order_details(lines):
    """
    API'den gelen 'lines' listesini işleyerek detaylı ürün bilgilerini
    bir sözlük listesi olarak hazırlar. Barkod dönüştürme kaldırıldı.
    """
    details_dict = {}
    total_order_quantity = 0 # Siparişteki toplam ürün adedi
    if not isinstance(lines, list):
         logger.warning("create_order_details: 'lines' verisi liste değil.")
         return [], 0 # Boş liste ve 0 quantity döndür

    for line in lines:
        if not isinstance(line, dict):
             logger.warning(f"create_order_details: 'lines' içinde geçersiz veri (dict değil): {line}")
             continue

        barcode = line.get('barcode', '')
        # Barkod yoksa bu satırı işlemeyebiliriz veya loglayabiliriz
        if not barcode:
             logger.warning(f"Sipariş satırında barkod eksik: {line.get('id', 'ID Yok')}")
             # continue # Barkodsuz satırı atlayalım mı? Şimdilik atlamayalım, belki SKU vs vardır.

        color = line.get('productColor', '')
        size_ = line.get('productSize', '')
        quantity = safe_int(line.get('quantity'), 0) # Miktar 0 ise bile işleyelim
        total_order_quantity += quantity
        commission_fee = safe_float(line.get('commissionFee'), 0.0)
        line_id = str(line.get('id', '')) # Trendyol line ID
        amount = safe_float(line.get('amount'), 0.0) # Birim fiyat (KDV dahil?)

        # Ürünü (barkod, renk, beden) anahtarıyla grupla
        key = (barcode, color, size_)
        if key not in details_dict:
            details_dict[key] = {
                'barcode': barcode,              # Orijinal barkod
                # 'converted_barcode': ...,      # KALDIRILDI
                'color': color,
                'size': size_,
                'sku': line.get('merchantSku', ''), # Satıcı SKU'su
                'productName': line.get('productName', ''),
                'productCode': str(line.get('productCode', '')), # Trendyol ürün kodu?
                'product_main_id': str(line.get('productId', '')), # Trendyol ana ürün ID?
                'quantity': quantity,            # Bu varyantın miktarı
                'commissionFee': commission_fee, # Bu varyantın komisyonu
                'line_id': [line_id],            # Aynı varyant farklı satırlarda olabilir, ID'leri liste yapalım
                'unit_price': amount,            # Birim fiyat
                'line_total_price': amount * quantity # Bu satırın toplam fiyatı
            }
        else:
            # Aynı varyant tekrar gelirse (normalde olmamalı ama olabilir?)
            details_dict[key]['quantity'] += quantity
            details_dict[key]['commissionFee'] += commission_fee
            details_dict[key]['line_id'].append(line_id) # Line ID'yi listeye ekle
            details_dict[key]['line_total_price'] += amount * quantity

    # Her bir varyant detayı için 'total_quantity' (siparişin toplam adedi) ekle
    # Bu alan belki gereksiz? details_dict dışında döndürülebilir.
    # for item_details in details_dict.values():
    #     item_details['total_order_quantity'] = total_order_quantity

    # Line ID listelerini stringe çevir
    for item_details in details_dict.values():
         item_details['line_id'] = ','.join(item_details['line_id'])


    # Sözlüğü liste olarak döndür
    return list(details_dict.values()), total_order_quantity

def combine_line_items(order_data, status):
    """
    API'den gelen sipariş verisini alır ve ilgili veritabanı tablosuna
    yazılacak alanları içeren bir sözlük oluşturur.
    Barkod dönüştürme kaldırıldı, `product_barcode` orijinal barkodları içerir.
    `original_product_barcode` alanı kaldırıldı.
    """
    if not isinstance(order_data, dict):
         logger.error("combine_line_items: Geçersiz order_data (dict değil).")
         return None

    lines = order_data.get('lines', [])
    if not isinstance(lines, list):
         logger.warning(f"Sipariş {order_data.get('orderNumber')}: 'lines' verisi liste değil.")
         lines = [] # Hata vermemek için boş liste ata


    # Detaylı ürün bilgilerini ve toplam adedi al
    details_list, total_qty = create_order_details(lines)
    if not details_list and not lines: # Hem lines boş hem details boşsa işlem yapma?
         logger.warning(f"Sipariş {order_data.get('orderNumber')}: İşlenecek ürün satırı bulunamadı.")
         # Boş sipariş kaydedilmeli mi? Şimdilik None döndürelim.
         # Veya temel sipariş bilgileriyle kaydedilebilir. Duruma göre karar verilmeli.
         # return None # Veya temel bilgileri içeren dict döndür

    # Virgülle ayrılmış orijinal barkod listesini oluştur
    # Not: Her barkod, quantity'si kadar tekrar etmeli mi? Önceki kod öyle yapıyordu.
    # create_order_details grupladığı için barkodlar artık unique.
    # Eğer quantity kadar tekrar gerekiyorsa, logic değişmeli.
    # Şimdilik unique barkodları alalım:
    original_barcodes = [item.get('barcode', '') for item in details_list if item.get('barcode')]
    # Eğer quantity kadar tekrar gerekiyorsa:
    # original_barcodes_repeated = []
    # for item in details_list:
    #     bc = item.get('barcode', '')
    #     qty = item.get('quantity', 0)
    #     if bc: original_barcodes_repeated.extend([bc] * qty)


    # --- Dönüştürülmüş barkod listesi (cbc) oluşturma KALDIRILDI ---
    # cbc = [replace_turkish_characters_cached(x) for x in original_barcodes]

    from json import dumps # JSON'a çevirme için import

    # Zaman damgalarını datetime objesine çevirme fonksiyonu
    def ts_to_dt(timestamp_ms):
        if not timestamp_ms: return None
        try:
            # Gelen değerin int/float olduğundan emin ol
            ts = float(timestamp_ms)
            # Geçerli bir aralıkta mı kontrol et (örn: çok eski veya gelecek tarihleri engelle)
            # Bu kontrol isteğe bağlıdır.
            # min_ts = datetime(2000, 1, 1).timestamp() * 1000
            # max_ts = (datetime.utcnow() + timedelta(days=365)).timestamp() * 1000 # Gelecek 1 yıl
            # if not (min_ts <= ts <= max_ts):
            #      logger.warning(f"Geçersiz timestamp değeri: {timestamp_ms}")
            #      return None
            return datetime.utcfromtimestamp(ts / 1000.0)
        except (ValueError, TypeError, OverflowError) as e:
            logger.warning(f"Timestamp ({timestamp_ms}) datetime'e çevrilemedi: {e}")
            return None

    # Veritabanı için sözlüğü oluştur
    db_record_dict = {
        'order_number': str(order_data.get('orderNumber', order_data.get('id', ''))), # id fallback?
        'order_date': ts_to_dt(order_data.get('orderDate')),
        # Aşağıdaki alanlar 'details' içinde olduğu için tekrar tekrar birleştirmeye gerek yok gibi.
        # Ancak mevcut DB şeması böyleyse kalmalı.
        'merchant_sku': ', '.join(item.get('sku', '') for item in details_list),
        # 'product_barcode' artık dönüştürülmüş değil, orijinal barkodları içeriyor.
        # Quantity kadar tekrar isteniyorsa original_barcodes_repeated kullanılmalı.
        'product_barcode': ', '.join(original_barcodes),
        # 'original_product_barcode': ..., # KALDIRILDI
        'status': status,
        'line_id': ','.join(item.get('line_id', '') for item in details_list), # Detaydaki line_id'ler zaten birleşik
        'match_status': '', # Bu alanın amacı ne? Boş bırakılabilir veya kaldırılabilir.
        # Müşteri Adı/Soyadı ve Adres
        'customer_name': order_data.get('shipmentAddress', {}).get('firstName', ''),
        'customer_surname': order_data.get('shipmentAddress', {}).get('lastName', ''),
        'customer_address': order_data.get('shipmentAddress', {}).get('fullAddress', ''),
        # Kargo Bilgileri
        'shipping_barcode': order_data.get('cargoTrackingNumber', ''), # Takip no (barkod?)
        'cargo_tracking_number': order_data.get('cargoTrackingNumber', ''), # Modelde bu alan varsa
        'cargo_provider_name': order_data.get('cargoProviderName', ''),
        'cargo_tracking_link': order_data.get('cargoTrackingLink', ''), # API'de varsa
        # Ürün Bilgileri (tekrar?)
        'product_name': ', '.join(item.get('productName', '') for item in details_list),
        'product_code': ', '.join(item.get('productCode', '') for item in details_list),
        'product_size': ', '.join(item.get('size', '') for item in details_list),
        'product_color': ', '.join(item.get('color', '') for item in details_list),
        'product_main_id': ', '.join(item.get('product_main_id', '') for item in details_list),
        'stockCode': ', '.join(item.get('sku', '') for item in details_list), # stockCode = merchantSku?
        # Fiyat Bilgileri
        'amount': sum(item.get('line_total_price', 0.0) for item in details_list), # Toplam tutar
        'discount': sum(safe_float(line.get('discount'), 0) for line in lines), # İndirim (lines'dan)
        'currency_code': order_data.get('currencyCode', 'TRY'),
        'vat_base_amount': sum(safe_float(line.get('vatBaseAmount'), 0) for line in lines), # KDV matrahı? (lines'dan)
        # Diğer ID'ler ve Tarihler
        'package_number': str(order_data.get('id', '')), # Trendyol paket ID
        'shipment_package_id': str(order_data.get('shipmentPackageId', '')), # Trendyol kargo paket ID
        'estimated_delivery_start': ts_to_dt(order_data.get('estimatedDeliveryStartDate')),
        'estimated_delivery_end': ts_to_dt(order_data.get('estimatedDeliveryEndDate')),
        'origin_shipment_date': ts_to_dt(order_data.get('originShipmentDate')), # Sevk tarihi?
        'agreed_delivery_date': ts_to_dt(order_data.get('agreedDeliveryDate')), # Anlaşmalı teslimat?
        # Detaylar ve Toplamlar
        'details': dumps(details_list, ensure_ascii=False, indent=None, separators=(',', ':')), # Daha kompakt JSON
        'quantity': total_qty, # Siparişteki toplam ürün adedi
        'commission': sum(item.get('commissionFee', 0.0) for item in details_list) # Toplam komisyon
        # Modelde olmayan ama potansiyel olarak eklenebilecek alanlar:
        # 'gross_amount': order_data.get('grossAmount'),
        # 'total_discount': order_data.get('totalDiscount'),
        # 'tax_amount': order_data.get('taxAmount'),
        # 'invoice_address': ...,
        # 'customer_email': ...,
        # 'customer_id': order_data.get('customerId'),
        # 'package_state': order_data.get('packageStatus'), # status yerine packageStatus daha detaylı olabilir
    }
    # Eksik veya None olan alanları temizle (isteğe bağlı)
    # return {k: v for k, v in db_record_dict.items() if v is not None}
    return db_record_dict


############################
# 4) Sipariş Listeleme Rotaları (Değişiklik Yok)
############################
# Bu rotalarda barkod dönüştürme ile ilgili bir işlem yoktu,
# sadece veritabanından çekip process_order_details'e gönderiyorlar.
# process_order_details fonksiyonu da barkod dönüştürme yapmıyorsa,
# bu rotalar olduğu gibi kalabilir.

@order_service_bp.route('/order-list/new', methods=['GET'])
# @role_required(...)
def get_new_orders():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int) # Sayfa boyutunu URL'den almak daha esnek
    try:
        query = OrderCreated.query.order_by(OrderCreated.order_date.desc())
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        orders = paginated.items
        # process_order_details fonksiyonu details JSON'unu parse edip template'e uygun hale getiriyor varsayalım
        process_order_details(orders)
    except Exception as e:
         logger.error(f"Yeni sipariş listesi alınırken hata: {e}", exc_info=True)
         flash("Yeni siparişler yüklenirken bir hata oluştu.", "danger")
         orders = []
         paginated = None # Hata durumunda pagination olmaz

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
# @role_required(...)
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
         orders = []
         paginated = None

    return render_template(
        'order_list.html',
        orders=orders,
        pagination=paginated,
        page=paginated.page if paginated else 1,
        total_pages=paginated.pages if paginated else 1,
        total_orders_count=paginated.total if paginated else len(orders),
        list_title="Hazırlanan Siparişler",
        active_list='picking'
    )


@order_service_bp.route('/order-list/shipped', methods=['GET'])
# @role_required(...)
def get_shipped_orders():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    try:
        query = OrderShipped.query.order_by(OrderShipped.order_date.desc()) # order_date mi, shipped_date mi?
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        orders = paginated.items
        process_order_details(orders)
    except Exception as e:
         logger.error(f"Shipped sipariş listesi alınırken hata: {e}", exc_info=True)
         flash("Kargodaki siparişler yüklenirken bir hata oluştu.", "danger")
         orders = []
         paginated = None

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
# @role_required(...)
def get_delivered_orders():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    try:
        query = OrderDelivered.query.order_by(OrderDelivered.order_date.desc()) # order_date mi, delivered_date mi?
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        orders = paginated.items
        process_order_details(orders)
    except Exception as e:
         logger.error(f"Delivered sipariş listesi alınırken hata: {e}", exc_info=True)
         flash("Teslim Edilen siparişler yüklenirken bir hata oluştu.", "danger")
         orders = []
         paginated = None

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
# @role_required(...)
def get_cancelled_orders():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    try:
        query = OrderCancelled.query.order_by(OrderCancelled.order_date.desc()) # order_date mi, cancelled_date mi?
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        orders = paginated.items
        process_order_details(orders)
    except Exception as e:
         logger.error(f"Cancelled sipariş listesi alınırken hata: {e}", exc_info=True)
         flash("İptal Edilen siparişler yüklenirken bir hata oluştu.", "danger")
         orders = []
         paginated = None

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