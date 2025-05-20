# -*- coding: utf-8 -*-

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
import asyncio
import aiohttp
import base64
import json
# import traceback # Kullanılmıyor, logger.error(..., exc_info=True) daha iyi
import logging
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError, IntegrityError # IntegrityError eklendi
import threading
import os
# from barcode_utils import generate_barcode # Kodda direkt kullanımı görünmüyor, eğer başka bir yerde (örn. template) gerekmiyorsa kaldırılabilir.
# Tablolar: Created, Picking, Shipped, Delivered, Cancelled, Archive
# models.py içindeki doğru import yolu varsayılıyor
from models import (
    db,
    OrderCreated,
    OrderPicking,
    OrderShipped,
    OrderDelivered,
    OrderCancelled,
    Archive # OrderArchived -> Archive olarak değiştirildi
)

# Trendyol API kimlik bilgileri
# trendyol_api.py dosyasından import ediliyorsa:
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL

# İsteğe bağlı: Sipariş detayı işleme
from order_list_service import process_order_details # order_list_service.py'den
# from update_service import update_package_to_picking # Kodda kullanımı görünmüyor, gerekmiyorsa kaldırılabilir.

# Blueprint
order_service_bp = Blueprint('order_service', __name__)

# Log ayarları
logger = logging.getLogger(__name__)
# Log dosya yolu ve oluşturma (zaten vardı, iyi)
log_file_path = os.path.join(os.path.dirname(__file__), 'logs', 'order_service.log')
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

# Handler'ların tekrar tekrar eklenmesini engelleme (zaten vardı, iyi)
if not logger.hasHandlers():
    handler = logging.FileHandler(log_file_path, encoding='utf-8') # encoding eklendi
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s') # threadName eklendi
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO) # Canlıda INFO, geliştirmede DEBUG olabilir.

############################
# Statü -> Model Eşlemesi
############################
STATUS_TABLE_MAP = {
    'Created':   OrderCreated,
    'Picking':   OrderPicking,
    'Invoiced':  OrderPicking,  # Invoiced statüsü de OrderPicking tablosuna yazılacak
    'Shipped':   OrderShipped,
    'Delivered': OrderDelivered,
    'Cancelled': OrderCancelled
    # Archive (eski OrderArchived) buraya dahil değil, çünkü o farklı bir akışla yönetiliyor (son durak).
}

############################
# 1) Trendyol'dan Sipariş Çekme (Asenkron)
############################
@order_service_bp.route('/fetch-trendyol-orders', methods=['POST'])
# @role_required('admin', 'manager') # Yetkilendirme eklenmeli (örneğin Flask-Login veya Flask-Principal ile)
async def fetch_trendyol_orders_route():
    """
    Kullanıcı arayüzünden veya bir araçla tetiklenerek Trendyol'dan siparişleri çeker.
    """
    logger.info("Manuel Trendyol sipariş çekme işlemi kullanıcı tarafından tetiklendi.")
    try:
        await fetch_trendyol_orders_async()
        flash('Trendyol siparişleri başarıyla çekildi ve işlenmeye başlandı!', 'success')
    except Exception as e:
        logger.error(f"fetch_trendyol_orders_route sırasında hata: {e}", exc_info=True)
        flash(f'Siparişler çekilirken veya işlenirken bir hata oluştu: {str(e)}', 'danger')
    return redirect(url_for('order_list_service.order_list_all'))

async def fetch_trendyol_orders_async():
    logger.info("Asenkron Trendyol sipariş çekme işlemi (fetch_trendyol_orders_async) başlıyor...")
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        base_api_url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/orders"
        request_headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json",
            "User-Agent": "GulluAyakkabiERP/1.0 (Python-aiohttp)"
        }
        statuses_to_fetch = "Created,Picking,Invoiced,Shipped,Delivered,Cancelled"
        common_params = {
            "status": statuses_to_fetch,
            "page": 0,
            "size": 200,
            "orderByField": "PackageLastModifiedDate",
            "orderByDirection": "DESC"
        }
        logger.debug(f"Trendyol API isteği için temel URL: {base_api_url}, Parametreler (ilk sayfa): {common_params}")
        all_orders_from_api = []
        total_pages = 1
        timeout_config = aiohttp.ClientTimeout(total=120, connect=30)

        async with aiohttp.ClientSession(headers=request_headers, timeout=timeout_config) as session:
            logger.info("Trendyol API'den ilk sayfa siparişler çekiliyor...")
            async with session.get(base_api_url, params=common_params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Trendyol API Hatası (İlk Sayfa): Durum Kodu {response.status} - Mesaj: {error_text[:500]}")
                    if response.status == 401:
                        logger.critical("Trendyol API kimlik bilgileri (API_KEY, API_SECRET) hatalı veya geçersiz!")
                    return
                try:
                    api_response_data = await response.json(content_type=None)
                except json.JSONDecodeError as json_e:
                    raw_response_text = await response.text()
                    logger.error(f"Trendyol API yanıtı JSON formatında değil veya parse edilemedi (İlk Sayfa): {json_e}. Yanıt: {raw_response_text[:500]}")
                    return
                except aiohttp.ClientResponseError as content_err:
                    raw_response_text = await response.text()
                    logger.error(f"Trendyol API yanıt içeriğiyle ilgili sorun (İlk Sayfa): {content_err}. Yanıt: {raw_response_text[:500]}")
                    return
                if not isinstance(api_response_data, dict):
                    logger.error(f"Trendyol API yanıtı beklenmedik formatta (dict değil, {type(api_response_data)} geldi). Yanıt: {str(api_response_data)[:200]}")
                    return
                current_page_orders_content = api_response_data.get('content', [])
                if isinstance(current_page_orders_content, list):
                    all_orders_from_api.extend(current_page_orders_content)
                else:
                    logger.error(f"Trendyol API yanıtındaki 'content' alanı bir liste değil (Tip: {type(current_page_orders_content)}). İçerik: {str(current_page_orders_content)[:200]}")
                total_elements_api = api_response_data.get('totalElements', 0)
                total_pages = api_response_data.get('totalPages', 1)
                logger.info(f"Trendyol API: Toplam {total_elements_api} sipariş bulundu. Toplam sayfa: {total_pages}. İlk sayfadan {len(current_page_orders_content)} sipariş çekildi.")

            if total_pages > 1:
                concurrent_requests_semaphore = asyncio.Semaphore(10)
                tasks_to_run = []
                logger.info(f"Kalan {total_pages - 1} sayfa ({common_params['size']} boyutunda) paralel olarak çekilecek...")
                for page_num in range(1, total_pages):
                    page_specific_params = dict(common_params, page=page_num)
                    tasks_to_run.append(
                        fetch_single_orders_page(session, base_api_url, page_specific_params, concurrent_requests_semaphore)
                    )
                page_results_list = await asyncio.gather(*tasks_to_run, return_exceptions=True)
                for single_page_result in page_results_list:
                    if isinstance(single_page_result, list):
                        all_orders_from_api.extend(single_page_result)
                    elif isinstance(single_page_result, Exception):
                        logger.error(f"Paralel sayfa çekme sırasında bir görev hata ile sonuçlandı: {single_page_result}", exc_info=True)

        logger.info(f"Trendyol API'den tüm sayfalardan toplam {len(all_orders_from_api)} sipariş verisi çekildi.")
        if all_orders_from_api:
            if current_app:
                with current_app.app_context():
                    process_all_orders(all_orders_from_api)
            else:
                logger.warning("Flask current_app bulunamadı. App context manuel olarak yönetilmeli (örn: app factory ile).")
        else:
            logger.info("Trendyol API'den işlenecek yeni sipariş verisi bulunamadı.")
    except aiohttp.ClientError as client_e:
        logger.error(f"Trendyol API'ye bağlanırken veya istek yaparken ClientError oluştu: {client_e}", exc_info=True)
    except Exception as e:
        logger.error(f"fetch_trendyol_orders_async fonksiyonunda genel bir hata oluştu: {e}", exc_info=True)

async def fetch_single_orders_page(session, url, params, semaphore):
    page_num_for_log = params.get('page', 'BilinmeyenSayfa')
    async with semaphore:
        try:
            logger.debug(f"Trendyol API'den Sayfa {page_num_for_log} çekiliyor... (Parametreler: {params})")
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    try:
                        data = await response.json(content_type=None)
                        if isinstance(data, dict):
                            content = data.get('content', [])
                            if isinstance(content, list):
                                logger.debug(f"Sayfa {page_num_for_log}: {len(content)} sipariş başarıyla çekildi.")
                                return content
                            else:
                                logger.error(f"Trendyol API yanıtı 'content' liste değil (Sayfa {page_num_for_log}). Tip: {type(content)}. İçerik: {str(content)[:100]}")
                                return []
                        else:
                            logger.error(f"Trendyol API yanıtı dict değil (Sayfa {page_num_for_log}). Tip: {type(data)}. Yanıt: {str(await response.text())[:100]}")
                            return []
                    except json.JSONDecodeError as json_e:
                        raw_text = await response.text()
                        logger.error(f"Trendyol API JSON parse hatası (Sayfa {page_num_for_log}): {json_e}. Yanıt: {raw_text[:100]}")
                        return []
                    except aiohttp.ClientResponseError as content_err:
                        raw_text = await response.text()
                        logger.error(f"Trendyol API yanıt içeriğiyle ilgili sorun (Sayfa {page_num_for_log}): {content_err}. Yanıt: {raw_text[:100]}")
                        return []
                else:
                    error_text = await response.text()
                    logger.error(f"Trendyol API isteği başarısız oldu (Sayfa {page_num_for_log}): Durum Kodu {response.status}. Mesaj: {error_text[:100]}")
                    return []
        except asyncio.TimeoutError:
            logger.error(f"Trendyol API isteği zaman aşımına uğradı (Sayfa {page_num_for_log}).")
            return []
        except aiohttp.ClientError as client_e:
            logger.error(f"Trendyol API bağlantı/istek hatası (Sayfa {page_num_for_log}): {client_e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"fetch_single_orders_page fonksiyonunda (Sayfa {page_num_for_log}) genel bir hata oluştu: {e}", exc_info=True)
            return []

############################
# 2) Gelen Siparişleri İşleme (Ana Mantık)
############################
def process_all_orders(all_orders_data_from_api):
    logger.info(f"Toplam {len(all_orders_data_from_api)} adet ham Trendyol sipariş verisi işlenmeye başlıyor...")
    if not all_orders_data_from_api:
        logger.info("İşlenecek ham sipariş verisi bulunmuyor.")
        return

    try:
        # OrderArchived -> Archive olarak değiştirildi
        archived_order_numbers_set = {
            str(o.order_number) for o in Archive.query.with_entities(Archive.order_number).all()
        }
        logger.info(f"Veritabanı arşivinden {len(archived_order_numbers_set)} adet sipariş numarası kontrol için çekildi.")

        valid_orders_for_processing = []
        skipped_archived_count = 0
        order_numbers_processed_in_this_batch = set()

        for order_data_item in all_orders_data_from_api:
            if not isinstance(order_data_item, dict):
                logger.warning(f"Geçersiz sipariş verisi formatı (dict değil), atlanıyor: {str(order_data_item)[:150]}")
                continue
            order_number = str(order_data_item.get('orderNumber') or order_data_item.get('id', '')).strip()
            if not order_number:
                logger.warning(f"Sipariş numarası (orderNumber veya id) alınamayan veri, atlanıyor: {str(order_data_item)[:150]}")
                continue
            if order_number in order_numbers_processed_in_this_batch:
                logger.debug(f"Sipariş {order_number} bu işlem partisinde zaten değerlendirildi, tekrar işlenmeyecek.")
                continue
            order_numbers_processed_in_this_batch.add(order_number)
            if order_number in archived_order_numbers_set:
                logger.info(f"Sipariş {order_number} arşivde kayıtlı. API'den tekrar gelse bile İŞLENMEYECEK.")
                skipped_archived_count += 1
                continue
            status_from_api = (order_data_item.get('status') or '').strip()
            if not status_from_api:
                logger.warning(f"Sipariş {order_number} için API'den statü bilgisi alınamadı, atlanıyor.")
                continue
            target_model_for_status = STATUS_TABLE_MAP.get(status_from_api)
            if not target_model_for_status:
                logger.warning(f"Sipariş {order_number}: API statüsü '{status_from_api}' için sistemde tanımlı bir model (tablo) yok. Bu statü işlenmeyecek.")
                continue
            valid_orders_for_processing.append(order_data_item)

        logger.info(f"{skipped_archived_count} sipariş, arşivde bulunduğu için işleme alınmadı.")
        logger.info(f"Arşiv ve diğer ön kontroller sonrası işlenmek üzere {len(valid_orders_for_processing)} geçerli sipariş kaldı.")

        if not valid_orders_for_processing:
            logger.info("Ön kontroller sonrası işlenecek geçerli sipariş kalmadı.")
            return

        # *** İPTAL İÇİN GÜNCELLENMİŞ AYIRIM MANTIĞI ***
        sync_processing_orders_data = []
        background_processing_orders_data = []
        cancelled_processing_orders_data = []

        for order_data_item in valid_orders_for_processing:
            status_from_api = (order_data_item.get('status') or '').strip()
            if status_from_api == 'Cancelled':
                cancelled_processing_orders_data.append(order_data_item)
            elif status_from_api in ('Created', 'Picking', 'Invoiced'):
                sync_processing_orders_data.append(order_data_item)
            elif status_from_api in ('Shipped', 'Delivered'):
                background_processing_orders_data.append(order_data_item)

        logger.info(f"Senkron işleme için ayrılan sipariş sayısı (Created/Picking): {len(sync_processing_orders_data)}")
        logger.info(f"Arka plan işleme için ayrılan sipariş sayısı (Shipped/Delivered): {len(background_processing_orders_data)}")
        logger.info(f"İptal işleme için ayrılan sipariş sayısı (Cancelled): {len(cancelled_processing_orders_data)}")

        # 4a) İptal edilen siparişleri işle (tüm potansiyel kaynak tablolardan sil)
        if cancelled_processing_orders_data:
            logger.info(f"İptal edilen {len(cancelled_processing_orders_data)} sipariş işleniyor...")
            _process_orders_in_bulk(
                cancelled_processing_orders_data,
                # Kaynak olarak KONTROL edilecek ve potansiyel olarak SİLİNECEK tablolar:
                [OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled],
                # Not: OrderCancelled'ın da listede olması, eğer sipariş zaten iptal edilmişse
                # ve API'den tekrar aynı statüde gelirse, _minimal_update_if_needed ile güncellenmesini sağlar.
                # Hedef tablo `OrderCancelled` olacak (STATUS_TABLE_MAP ile belirlenir).
                processing_type="İptal Edilenler (Cancelled)"
            )

        # 4b) Diğer Senkron siparişleri işle (Created, Picking)
        if sync_processing_orders_data:
            logger.info(f"Senkron ({len(sync_processing_orders_data)}) (Created/Picking) siparişler işleniyor...")
            _process_orders_in_bulk(
                sync_processing_orders_data,
                [OrderCreated, OrderPicking], # İlgili kaynak/hedef tablolar. (OrderCancelled artık burada değil)
                processing_type="Senkron (Created/Picking)"
            )

        # 5) Arka plan siparişlerini işle (Shipped, Delivered) (ayrı bir thread'de)
        if background_processing_orders_data:
            logger.info(f"Arka plan ({len(background_processing_orders_data)}) (Shipped/Delivered) siparişler için thread başlatılıyor...")
            flask_app_instance = current_app._get_current_object()
            bg_thread = threading.Thread(
                target=_process_bg_orders_with_context,
                args=(background_processing_orders_data, flask_app_instance),
                daemon=True,
                name="BGOrderProcessingThread"
            )
            bg_thread.start()
            logger.info(f"Arka plan işleyici thread'i ({bg_thread.name}) Shipped/Delivered siparişleri için başlatıldı.")

    except SQLAlchemyError as db_err:
        logger.error(f"process_all_orders fonksiyonunda genel bir veritabanı hatası oluştu: {db_err}", exc_info=True)
    except Exception as e:
        logger.error(f"process_all_orders fonksiyonunda beklenmedik genel bir hata oluştu: {e}", exc_info=True)

def _process_bg_orders_with_context(bg_orders_data_list, flask_app):
    with flask_app.app_context():
        current_thread_name = threading.current_thread().name
        logger.info(f"Arka plan thread'i ({current_thread_name}) app context'i ile başlatıldı.")
        # OrderPicking, Shipped'e geçiş için kaynak olabilir.
        # OrderShipped, Delivered'a geçiş için kaynak olabilir.
        # OrderDelivered hedef olabilir veya sadece güncellenebilir.
        relevant_bg_tables = [OrderPicking, OrderShipped, OrderDelivered]
        _process_orders_in_bulk(
            bg_orders_data_list,
            relevant_bg_tables,
            processing_type="ArkaPlan (Shipped/Delivered)"
        )
        logger.info(f"Arka plan thread'i ({current_thread_name}) görevini tamamladı.")

def _process_orders_in_bulk(orders_data_list_to_process, relevant_table_models_for_this_processor, processing_type="Bilinmeyen"):
    if not orders_data_list_to_process:
        logger.info(f"[{processing_type}] İşlenecek sipariş verisi yok.")
        return

    logger.info(f"[{processing_type}] {len(orders_data_list_to_process)} adet sipariş toplu olarak işlenmeye başlıyor. İlgili tablolar: {[m.__name__ for m in relevant_table_models_for_this_processor]}")
    order_numbers_in_this_batch = {
        str(od.get('orderNumber') or od.get('id')) for od in orders_data_list_to_process if od.get('orderNumber') or od.get('id')
    }
    if not order_numbers_in_this_batch:
        logger.warning(f"[{processing_type}] Gelen sipariş verilerinde hiç sipariş numarası bulunamadı.")
        return

    existing_db_records_map = {}
    for table_model_class in relevant_table_models_for_this_processor:
        try:
            records_from_db = table_model_class.query.filter(table_model_class.order_number.in_(order_numbers_in_this_batch)).all()
            for db_record in records_from_db:
                order_num = str(db_record.order_number)
                if order_num in existing_db_records_map:
                    logger.error(
                        f"[{processing_type}] KRİTİK VERİ TUTARSIZLIĞI: Sipariş {order_num} birden fazla ilgili tabloda bulundu! "
                        f"Mevcut kayıtlı tablo: {existing_db_records_map[order_num]['table_name']}, Yeni bulunan tablo: {table_model_class.__tablename__}."
                    )
                else:
                    existing_db_records_map[order_num] = {
                        'record': db_record,
                        'table_name': table_model_class.__tablename__
                    }
        except SQLAlchemyError as query_err:
            logger.error(f"[{processing_type}] {table_model_class.__tablename__} tablosu sorgulanırken veritabanı hatası: {query_err}", exc_info=True)
            return

    data_to_insert_map = {model_class: [] for model_class in STATUS_TABLE_MAP.values()} # Tüm olası hedef tablolar için liste
    ids_to_delete_map = {model_class.__tablename__: [] for model_class in relevant_table_models_for_this_processor}
    updated_records_counter = 0

    for order_data_from_api in orders_data_list_to_process:
        order_number_api = str(order_data_from_api.get('orderNumber') or order_data_from_api.get('id'))
        if not order_number_api:
            logger.warning(f"[{processing_type}] Sipariş verisinde order_number (veya id) eksik, atlanıyor: {str(order_data_from_api)[:100]}")
            continue
        api_status = (order_data_from_api.get('status') or '').strip()
        target_model_class_for_api_status = STATUS_TABLE_MAP.get(api_status)

        # Bu kontrol önemli: Hedef modelin bu işlemcinin yönettiği tablolardan biri olması gerekmiyor.
        # Örneğin, "Cancelled" işlemi için relevant_tables [Created, Picking, Shipped, Delivered, Cancelled] iken
        # target_model_class_for_api_status her zaman OrderCancelled olacak.
        if not target_model_class_for_api_status: # API statüsü haritalanamıyorsa
            logger.error(
                f"[{processing_type}] MANTIK HATASI: Sipariş {order_number_api} (API statüsü: {api_status}) "
                f"için STATUS_TABLE_MAP'de bir hedef model bulunamadı. Atlanıyor."
            )
            continue

        new_data_dict_for_db = combine_line_items(order_data_from_api, api_status)
        if not new_data_dict_for_db:
            logger.error(f"[{processing_type}] Sipariş {order_number_api} için veritabanı sözlüğü oluşturulamadı. Atlanıyor.")
            continue

        existing_record_info = existing_db_records_map.get(order_number_api)
        target_table_name_for_api_status = target_model_class_for_api_status.__tablename__

        if existing_record_info:
            current_db_record_object = existing_record_info['record']
            current_db_table_name = existing_record_info['table_name']

            if current_db_table_name != target_table_name_for_api_status:
                logger.info(
                    f"[{processing_type}] Statü Değişimi: Sipariş {order_number_api} "
                    f"('{current_db_table_name}' -> '{target_table_name_for_api_status}')."
                )
                # Sadece relevant_table_models_for_this_processor listesindeki tablolardan sil.
                if current_db_table_name in ids_to_delete_map: # Yani, bu işlemcinin kontrolündeki bir tablodan silinecek.
                     ids_to_delete_map[current_db_table_name].append(current_db_record_object.id)
                else:
                    logger.warning(f"[{processing_type}] Sipariş {order_number_api} mevcut tablosu ({current_db_table_name}) bu işlemcinin silme yetkisindeki tablolarda değil. Silme atlanıyor.")


                # Yeni tabloya eklenecekler listesine ekle
                # data_to_insert_map anahtarları artık tüm STATUS_TABLE_MAP değerlerini içeriyor.
                data_to_insert_map[target_model_class_for_api_status].append(new_data_dict_for_db)
            else: # Aynı tabloda, sadece güncelleme
                if _minimal_update_if_needed(current_db_record_object, new_data_dict_for_db):
                    logger.info(f"[{processing_type}] Sipariş {order_number_api} ({target_table_name_for_api_status}) güncellendi.")
                    updated_records_counter +=1
                else:
                    logger.debug(f"[{processing_type}] Sipariş {order_number_api} ({target_table_name_for_api_status}) için güncelleme gerekmedi.")
        else: # Sipariş DB'de (bu işlemcinin baktığı tablolarda) hiç yok, yeni kayıt
            logger.info(f"[{processing_type}] Yeni Sipariş: {order_number_api} -> {target_table_name_for_api_status} tablosuna eklenecek.")
            data_to_insert_map[target_model_class_for_api_status].append(new_data_dict_for_db)

    try:
        items_deleted_count = 0
        for table_name_to_delete_from, ids_list_to_delete in ids_to_delete_map.items():
            if ids_list_to_delete:
                model_class_to_delete_from = next((m for m in relevant_table_models_for_this_processor if m.__tablename__ == table_name_to_delete_from), None)
                if model_class_to_delete_from:
                    delete_statement = model_class_to_delete_from.__table__.delete().where(model_class_to_delete_from.id.in_(ids_list_to_delete))
                    result = db.session.execute(delete_statement)
                    items_deleted_count += result.rowcount
                    logger.info(f"[{processing_type}] {result.rowcount} kayıt {table_name_to_delete_from} tablosundan silinmek üzere işaretlendi.")
                else:
                    logger.error(f"[{processing_type}] Silme için {table_name_to_delete_from} modeli bulunamadı!")

        items_inserted_count = 0
        for model_class_to_insert_to, data_dicts_list_to_insert in data_to_insert_map.items():
            if data_dicts_list_to_insert: # Sadece içinde veri olanları işle
                db.session.bulk_insert_mappings(model_class_to_insert_to, data_dicts_list_to_insert)
                items_inserted_count += len(data_dicts_list_to_insert)
                logger.info(f"[{processing_type}] {len(data_dicts_list_to_insert)} kayıt {model_class_to_insert_to.__name__} tablosuna eklenmek üzere işaretlendi.")

        if items_deleted_count > 0 or items_inserted_count > 0 or updated_records_counter > 0:
            db.session.commit()
            logger.info(
                f"[{processing_type}] Veritabanı işlemleri commit edildi. "
                f"Silinen: {items_deleted_count}, Eklenen: {items_inserted_count}, Güncellenen: {updated_records_counter}."
            )
        else:
            logger.info(f"[{processing_type}] Veritabanında değişiklik yok. Commit atlanıyor.")
    except IntegrityError as int_err:
        db.session.rollback()
        logger.error(f"[{processing_type}] DB Bütünlük Hatası: {int_err}", exc_info=True)
        flash(f"{processing_type} işlemleri sırasında DB bütünlük hatası. Logları kontrol edin.", "warning")
    except SQLAlchemyError as sql_err:
        db.session.rollback()
        logger.error(f"[{processing_type}] SQLAlchemy Hatası: {sql_err}", exc_info=True)
        flash(f"{processing_type} işlemleri sırasında DB hatası.", "danger")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[{processing_type}] Genel Hata: {e}", exc_info=True)
        flash(f"{processing_type} işlemleri sırasında beklenmedik hata.", "danger")
    finally:
        db.session.remove()
        logger.debug(f"[{processing_type}] Veritabanı session'ı kapatıldı.")


def _minimal_update_if_needed(db_record_object, new_data_dict_from_api):
    changed_flag = False
    fields_to_compare_and_update = {
        'status': 'status', 'order_date': 'order_date', 'product_barcode': 'product_barcode',
        'quantity': 'quantity', 'commission': 'commission', 'details': 'details',
        'cargo_tracking_number': 'cargo_tracking_number', 'cargo_provider_name': 'cargo_provider_name',
        'customer_name': 'customer_name', 'customer_surname': 'customer_surname', 'customer_address': 'customer_address',
        'merchant_sku': 'merchant_sku', 'line_id': 'line_id', 'product_name': 'product_name',
        'product_code': 'product_code', 'product_size': 'product_size', 'product_color': 'product_color',
        'product_main_id': 'product_main_id', 'stockCode': 'stockCode', 'amount': 'amount',
        'discount': 'discount', 'currency_code': 'currency_code', 'gross_amount': 'gross_amount',
        'tax_amount': 'tax_amount', 'customer_id': 'customer_id',
        'shipment_package_status': 'shipment_package_status', 'package_number': 'package_number',
        'shipment_package_id': 'shipment_package_id', 'estimated_delivery_start': 'estimated_delivery_start',
        'estimated_delivery_end': 'estimated_delivery_end', 'origin_shipment_date': 'origin_shipment_date',
        'agreed_delivery_date': 'agreed_delivery_date', 'last_modified_date': 'last_modified_date',
    }
    for model_attr_name, api_dict_key in fields_to_compare_and_update.items():
        if hasattr(db_record_object, model_attr_name):
            current_value_in_db = getattr(db_record_object, model_attr_name)
            new_value_from_api = new_data_dict_from_api.get(api_dict_key)
            if new_value_from_api is None and (current_value_in_db is None or str(current_value_in_db).strip() == ""):
                continue
            if isinstance(current_value_in_db, datetime) and isinstance(new_value_from_api, datetime):
                if current_value_in_db.replace(tzinfo=None, microsecond=0) != new_value_from_api.replace(tzinfo=None, microsecond=0):
                    setattr(db_record_object, model_attr_name, new_value_from_api)
                    changed_flag = True
            elif model_attr_name == 'details':
                try:
                    current_json_obj = json.loads(current_value_in_db) if isinstance(current_value_in_db, str) and current_value_in_db.strip() else (current_value_in_db if isinstance(current_value_in_db, (dict, list)) else None)
                    new_json_obj = json.loads(new_value_from_api) if isinstance(new_value_from_api, str) and new_value_from_api.strip() else (new_value_from_api if isinstance(new_value_from_api, (dict, list)) else None)
                    if current_json_obj != new_json_obj:
                        setattr(db_record_object, model_attr_name, new_value_from_api)
                        changed_flag = True
                except (json.JSONDecodeError, TypeError) as json_compare_err:
                    logger.warning(f"Detaylar ('{model_attr_name}') JSON karşılaştırma/parse hatası (Sipariş: {getattr(db_record_object, 'order_number', 'N/A')}): {json_compare_err}. String olarak karşılaştırılacak.")
                    if str(current_value_in_db) != str(new_value_from_api):
                        setattr(db_record_object, model_attr_name, new_value_from_api)
                        changed_flag = True
            elif type(current_value_in_db) != type(new_value_from_api) and new_value_from_api is not None and current_value_in_db is not None:
                try:
                    converted_new_value = type(current_value_in_db)(new_value_from_api)
                    if current_value_in_db != converted_new_value:
                        setattr(db_record_object, model_attr_name, converted_new_value)
                        changed_flag = True
                except (ValueError, TypeError) as conversion_err:
                    logger.debug(f"Tip dönüşümü başarısız ({model_attr_name}): {conversion_err}. Direkt karşılaştırılıyor.")
                    if str(current_value_in_db) != str(new_value_from_api):
                        setattr(db_record_object, model_attr_name, new_value_from_api)
                        changed_flag = True
            elif current_value_in_db != new_value_from_api:
                setattr(db_record_object, model_attr_name, new_value_from_api)
                changed_flag = True
    if changed_flag and hasattr(db_record_object, 'updated_at'):
        setattr(db_record_object, 'updated_at', datetime.utcnow())
        logger.debug(f"Sipariş {getattr(db_record_object, 'order_number', 'N/A')} için 'updated_at' alanı güncellendi.")
    return changed_flag

def safe_int(value, default_if_error=0):
    if value is None: return default_if_error
    try: return int(value)
    except (ValueError, TypeError): return default_if_error

def safe_float(value, default_if_error=0.0):
    if value is None: return default_if_error
    try:
        if isinstance(value, str): value_str = value.replace('.', '').replace(',', '.')
        else: value_str = str(value)
        return float(value_str)
    except (ValueError, TypeError): return default_if_error

def create_order_details(api_lines_list):
    processed_details_map = {}
    total_quantity_for_order = 0
    if not isinstance(api_lines_list, list):
        logger.warning("create_order_details: 'lines' verisi liste değil.")
        return [], 0
    for line_item_from_api in api_lines_list:
        if not isinstance(line_item_from_api, dict):
            logger.warning(f"create_order_details: 'lines' içinde geçersiz öğe: {str(line_item_from_api)[:100]}")
            continue
        barcode = str(line_item_from_api.get('barcode', '')).strip()
        if not barcode: logger.warning(f"Sipariş satırında (API Line ID: {line_item_from_api.get('id', 'N/A')}) BARKOD eksik.")
        product_color = line_item_from_api.get('productColor', '')
        product_size = line_item_from_api.get('productSize', '')
        quantity_in_line = safe_int(line_item_from_api.get('quantity'), 0)
        total_quantity_for_order += quantity_in_line
        variant_key = (barcode, product_color, product_size)
        commission_fee_for_line = safe_float(line_item_from_api.get('commissionFee'), 0.0)
        api_line_id = str(line_item_from_api.get('id', ''))
        unit_price_from_api = safe_float(line_item_from_api.get('price'), 0.0)
        line_total_price_from_api = safe_float(line_item_from_api.get('amount'), 0.0)
        if unit_price_from_api == 0.0 and line_total_price_from_api > 0.0 and quantity_in_line > 0:
            unit_price_from_api = round(line_total_price_from_api / quantity_in_line, 2)
        if variant_key not in processed_details_map:
            processed_details_map[variant_key] = {
                'barcode': barcode, 'color': product_color, 'size': product_size,
                'sku': str(line_item_from_api.get('merchantSku', '')).strip(),
                'productName': line_item_from_api.get('productName', ''),
                'productCode': str(line_item_from_api.get('productCode', '')),
                'product_main_id': str(line_item_from_api.get('productId', '')),
                'quantity': quantity_in_line, 'commissionFee': commission_fee_for_line,
                'line_ids_api': [api_line_id] if api_line_id else [],
                'unit_price': unit_price_from_api, 'line_total_price': line_total_price_from_api,
                'vatRate': safe_float(line_item_from_api.get('vatRate'), 0.0),
                'discountDetails': line_item_from_api.get('discountDetails', [])
            }
        else:
            existing_variant_data = processed_details_map[variant_key]
            existing_variant_data['quantity'] += quantity_in_line
            existing_variant_data['commissionFee'] += commission_fee_for_line
            if api_line_id: existing_variant_data['line_ids_api'].append(api_line_id)
            existing_variant_data['line_total_price'] += line_total_price_from_api
    final_details_list_for_json = []
    for item_details_dict in processed_details_map.values():
        item_details_dict['line_ids_api'] = ','.join(filter(None, item_details_dict['line_ids_api']))
        final_details_list_for_json.append(item_details_dict)
    return final_details_list_for_json, total_quantity_for_order

def combine_line_items(single_order_data_from_api, api_status_for_db_record):
    if not isinstance(single_order_data_from_api, dict):
        logger.error("combine_line_items: Geçersiz 'single_order_data_from_api'.")
        return None
    api_lines_list = single_order_data_from_api.get('lines', [])
    if not isinstance(api_lines_list, list):
        logger.warning(f"Sipariş {single_order_data_from_api.get('orderNumber', 'N/A')}: 'lines' liste değil.")
        api_lines_list = []
    processed_details_list, total_quantity_for_order = create_order_details(api_lines_list)
    if not processed_details_list and api_lines_list: logger.warning(f"Sipariş {single_order_data_from_api.get('orderNumber', 'N/A')}: Ürün satırları var ama detaylar oluşturulamadı.")
    elif not api_lines_list: logger.info(f"Sipariş {single_order_data_from_api.get('orderNumber', 'N/A')} API'den ürün satırı olmadan geldi.")
    unique_original_barcodes_list = [item.get('barcode', '') for item in processed_details_list if item.get('barcode')]
    def convert_timestamp_ms_to_datetime(timestamp_ms_value):
        if not timestamp_ms_value: return None
        try:
            ts_float = float(timestamp_ms_value)
            if ts_float < 0: return None
            return datetime.utcfromtimestamp(ts_float / 1000.0)
        except (ValueError, TypeError, OverflowError) as e:
            logger.warning(f"Timestamp ({timestamp_ms_value}) çevirme hatası: {e}")
            return None
    shipment_address_dict = single_order_data_from_api.get('shipmentAddress', {}) if isinstance(single_order_data_from_api.get('shipmentAddress'), dict) else {}
    db_record_dict = {
        'order_number': str(single_order_data_from_api.get('orderNumber') or single_order_data_from_api.get('id', '')).strip(),
        'order_date': convert_timestamp_ms_to_datetime(single_order_data_from_api.get('orderDate')),
        'status': api_status_for_db_record,
        'merchant_sku': ','.join(filter(None, {str(item.get('sku', '')).strip() for item in processed_details_list if item.get('sku')})),
        'product_barcode': ','.join(filter(None, unique_original_barcodes_list)),
        'product_name': ','.join(filter(None, {str(item.get('productName', '')).strip() for item in processed_details_list if item.get('productName')})),
        'product_code': ','.join(filter(None, {str(item.get('productCode', '')).strip() for item in processed_details_list if item.get('productCode')})),
        'product_size': ','.join(filter(None, {str(item.get('size', '')).strip() for item in processed_details_list if item.get('size')})),
        'product_color': ','.join(filter(None, {str(item.get('color', '')).strip() for item in processed_details_list if item.get('color')})),
        'product_main_id': ','.join(filter(None, {str(item.get('product_main_id', '')).strip() for item in processed_details_list if item.get('product_main_id')})),
        'stockCode': ','.join(filter(None, {str(item.get('sku', '')).strip() for item in processed_details_list if item.get('sku')})),
        'line_id': ','.join(item['line_ids_api'] for item in processed_details_list if item.get('line_ids_api')),
        'customer_name': shipment_address_dict.get('firstName', ''),
        'customer_surname': shipment_address_dict.get('lastName', ''),
        'customer_address': shipment_address_dict.get('fullAddress', ''),
        'customer_id': str(single_order_data_from_api.get('customerId', '')),
        'shipping_barcode': single_order_data_from_api.get('cargoTrackingNumber', ''),
        'cargo_tracking_number': single_order_data_from_api.get('cargoTrackingNumber', ''),
        'cargo_provider_name': single_order_data_from_api.get('cargoProviderName', ''),
        'cargo_tracking_link': single_order_data_from_api.get('cargoTrackingLink', ''),
        'shipment_package_status': single_order_data_from_api.get('packageStatus', ''),
        'amount': safe_float(single_order_data_from_api.get('totalPrice'), 0.0),
        'discount': safe_float(single_order_data_from_api.get('totalDiscount'), 0.0),
        'gross_amount': safe_float(single_order_data_from_api.get('grossAmount'), 0.0),
        'tax_amount': safe_float(single_order_data_from_api.get('taxTotal') or single_order_data_from_api.get('totalVat'), 0.0),
        'currency_code': single_order_data_from_api.get('currencyCode', 'TRY'),
        'commission': safe_float(single_order_data_from_api.get('commissionTotal', sum(item.get('commissionFee', 0.0) for item in processed_details_list)), 0.0),
        'quantity': total_quantity_for_order,
        'package_number': str(single_order_data_from_api.get('id', '')),
        'shipment_package_id': str(single_order_data_from_api.get('shipmentPackageId', '')),
        'estimated_delivery_start': convert_timestamp_ms_to_datetime(single_order_data_from_api.get('estimatedDeliveryStartDate')),
        'estimated_delivery_end': convert_timestamp_ms_to_datetime(single_order_data_from_api.get('estimatedDeliveryEndDate')),
        'origin_shipment_date': convert_timestamp_ms_to_datetime(single_order_data_from_api.get('originShipmentDate')),
        'agreed_delivery_date': convert_timestamp_ms_to_datetime(single_order_data_from_api.get('agreedDeliveryDate')),
        'last_modified_date': convert_timestamp_ms_to_datetime(single_order_data_from_api.get('lastModifiedDate') or single_order_data_from_api.get('packageLastModifiedDate')),
        'details': json.dumps(processed_details_list, ensure_ascii=False, default=str, separators=(',', ':')),
        'match_status': '',
    }
    return db_record_dict

############################
# 4) Sipariş Listeleme Rotaları
############################
def _render_order_list_template(query_obj, list_title_for_page, active_list_identifier, current_page_num, items_per_page):
    try:
        paginated_orders_result = query_obj.paginate(page=current_page_num, per_page=items_per_page, error_out=False)
        orders_to_display_on_page = paginated_orders_result.items
        if orders_to_display_on_page:
            process_order_details(orders_to_display_on_page)
    except Exception as e:
        logger.error(f"'{list_title_for_page}' listesi alınırken hata: {e}", exc_info=True)
        flash(f"'{list_title_for_page}' yüklenirken hata. Yöneticiye başvurun.", "danger")
        orders_to_display_on_page = []
        paginated_orders_result = None
    template_context = {
        'orders': orders_to_display_on_page, 'pagination': paginated_orders_result,
        'page': paginated_orders_result.page if paginated_orders_result else current_page_num,
        'total_pages': paginated_orders_result.pages if paginated_orders_result else 1,
        'total_orders_count': paginated_orders_result.total if paginated_orders_result else len(orders_to_display_on_page),
        'list_title': list_title_for_page, 'active_list': active_list_identifier, 'per_page': items_per_page
    }
    return render_template('order_list.html', **template_context)

@order_service_bp.route('/order-list/new', methods=['GET'])
def get_new_orders():
    page_num = request.args.get('page', 1, type=int)
    orders_per_page = request.args.get('per_page', current_app.config.get('ORDERS_PER_PAGE', 50), type=int)
    base_query = OrderCreated.query.order_by(OrderCreated.order_date.desc(), OrderCreated.id.desc())
    return _render_order_list_template(base_query, "Yeni Siparişler", "new", page_num, orders_per_page)

@order_service_bp.route('/order-list/picking', methods=['GET'])
def get_picking_orders():
    page_num = request.args.get('page', 1, type=int)
    orders_per_page = request.args.get('per_page', current_app.config.get('ORDERS_PER_PAGE', 50), type=int)
    base_query = OrderPicking.query.order_by(OrderPicking.order_date.desc(), OrderPicking.id.desc())
    return _render_order_list_template(base_query, "Hazırlanan Siparişler", "picking", page_num, orders_per_page)

@order_service_bp.route('/order-list/shipped', methods=['GET'])
def get_shipped_orders():
    page_num = request.args.get('page', 1, type=int)
    orders_per_page = request.args.get('per_page', current_app.config.get('ORDERS_PER_PAGE', 50), type=int)
    base_query = OrderShipped.query.order_by(OrderShipped.last_modified_date.desc(), OrderShipped.id.desc())
    return _render_order_list_template(base_query, "Kargodaki Siparişler", "shipped", page_num, orders_per_page)

@order_service_bp.route('/order-list/delivered', methods=['GET'])
def get_delivered_orders():
    page_num = request.args.get('page', 1, type=int)
    orders_per_page = request.args.get('per_page', current_app.config.get('ORDERS_PER_PAGE', 50), type=int)
    base_query = OrderDelivered.query.order_by(OrderDelivered.last_modified_date.desc(), OrderDelivered.id.desc())
    return _render_order_list_template(base_query, "Teslim Edilen Siparişler", "delivered", page_num, orders_per_page)

@order_service_bp.route('/order-list/cancelled', methods=['GET'])
def get_cancelled_orders():
    page_num = request.args.get('page', 1, type=int)
    orders_per_page = request.args.get('per_page', current_app.config.get('ORDERS_PER_PAGE', 50), type=int)
    base_query = OrderCancelled.query.order_by(OrderCancelled.last_modified_date.desc(), OrderCancelled.id.desc())
    return _render_order_list_template(base_query, "İptal Edilen Siparişler", "cancelled", page_num, orders_per_page)

@order_service_bp.route('/order-list/archived', methods=['GET'])
def get_archived_orders():
    page_num = request.args.get('page', 1, type=int)
    orders_per_page = request.args.get('per_page', current_app.config.get('ORDERS_PER_PAGE', 50), type=int)
    # OrderArchived -> Archive olarak değiştirildi
    base_query = Archive.query.order_by(Archive.order_date.desc(), Archive.id.desc())
    return _render_order_list_template(base_query, "Arşivlenmiş Siparişler", "archived", page_num, orders_per_page)