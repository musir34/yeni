# stock_management.py

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
# Product modelini import et
from models import db, Product # models.py dosyasında Product modelinin title alanı olduğunu varsayıyorum
import json
import logging
import os
import time
from datetime import datetime
from threading import Thread
from functools import wraps
import aiohttp
import asyncio
from sqlalchemy import text, and_, or_, func, distinct # distinct eklendi
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Trendyol stok güncelleme fonksiyonunu kullanacağız
# get_products.py dosyasından Trendyol API bilgileri ve request kütüphanesini kullanıyoruz
# Not: API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL gibi bilgiler trendyol_api.py dosyasında olmalı
import base64
import requests
try:
    from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL
    logger = logging.getLogger(__name__)
    logger.info("Trendyol API bilgileri başarıyla yüklendi.")
except ImportError:
    logger = logging.getLogger(__name__)
    logger.error("trendyol_api.py dosyası bulunamadı veya Trendyol API bilgileri (API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL) eksik.")
    API_KEY = None
    API_SECRET = None
    SUPPLIER_ID = None
    BASE_URL = "https://api.trendyol.com/sapigw/"

LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
LOG_LEVEL_MAP = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR
}

logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL_MAP.get(LOG_LEVEL, logging.INFO))
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

limiter = Limiter(key_func=get_remote_address)

def require_api_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('X-API-Token')
        expected_token = current_app.config.get('API_TOKEN')

        if not token or token != expected_token:
            logger.warning(f"Geçersiz API token erişim denemesi: {request.remote_addr}")
            return jsonify(success=False, message="Geçersiz API token"), 403
        return f(*args, **kwargs)
    return decorated_function

stock_cache = {}
stock_management_bp = Blueprint('stock_management', __name__)
BATCH_SIZE = 100

def log_failed_barcodes(failed_items, reason=""):
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = "logs/failed_stock_updates"
        os.makedirs(log_dir, exist_ok=True)

        with open(f"{log_dir}/failed_stock_update_{timestamp}.json", "w") as f:
            json.dump({
                "timestamp": timestamp,
                "reason": reason,
                "items": failed_items
            }, f, indent=2)
        logger.info(f"{len(failed_items)} hatalı barkod kaydedildi: {log_dir}")
    except Exception as e:
        logger.error(f"Hatalı barkodları kaydetme hatası: {e}")

async def send_trendyol_stock_update_async(items_list, batch_size=BATCH_SIZE):
    if not API_KEY or not API_SECRET or not SUPPLIER_ID:
        logger.error("Trendyol API bilgileri eksik. Stok Trendyol'da güncellenemez.")
        return False, 0, {"general": "Trendyol API bilgileri sunucuda eksik."}

    if not items_list:
        logger.info("Trendyol'a gönderilecek ürün listesi boş.")
        return True, 0, {}

    url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/products/price-and-inventory"
    credentials = f"{API_KEY}:{API_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/json",
        "User-Agent": f"GulluAyakkabiApp - Supplier {SUPPLIER_ID}"
    }

    batches = [items_list[i:i + batch_size] for i in range(0, len(items_list), batch_size)]
    logger.info(f"Toplam {len(items_list)} ürün, {len(batches)} batch'e bölündü (batch boyutu: {batch_size})")

    overall_success = True
    total_success_count = 0
    all_errors = {}

    async with aiohttp.ClientSession() as session:
        for batch_idx, batch_items in enumerate(batches):
            if batch_idx > 0:
                await asyncio.sleep(0.5) 

            try:
                payload = {"items": batch_items}
                logger.debug(f"Batch {batch_idx+1}/{len(batches)}: {len(batch_items)} ürün gönderiliyor")

                async with session.post(url, headers=headers, json=payload, timeout=60) as response:
                    response_text = await response.text()

                    try:
                        response_data = json.loads(response_text) if response_text else {}
                    except json.JSONDecodeError:
                        logger.error(f"Batch {batch_idx+1}: Geçersiz JSON yanıtı: {response_text[:200]}...")
                        overall_success = False
                        all_errors.update({f"batch{batch_idx+1}": "Geçersiz JSON yanıtı"})
                        continue

                    if response.status in [200, 202]:
                        trendyol_errors = response_data.get('errors', []) + response_data.get('failures', [])

                        if trendyol_errors:
                            logger.warning(f"Batch {batch_idx+1}: Yanıtta {len(trendyol_errors)} hata var")
                            for err in trendyol_errors:
                                barcode = err.get('barcode', f'Bilinmeyen-Batch{batch_idx+1}')
                                all_errors[barcode] = err.get('message', 'Bilinmeyen Hata')

                            failed_items_in_batch = [item for item in batch_items if item.get('barcode') in all_errors]
                            if failed_items_in_batch: 
                               log_failed_barcodes(failed_items_in_batch, f"Batch {batch_idx+1} API hatası")

                        batch_success_count = len(batch_items) - len(trendyol_errors)
                        total_success_count += batch_success_count
                        logger.info(f"Batch {batch_idx+1}: {batch_success_count}/{len(batch_items)} ürün başarıyla güncellendi")
                    else:
                        logger.error(f"Batch {batch_idx+1}: HTTP hatası {response.status} - {response_text[:200]}")
                        overall_success = False
                        all_errors.update({f"batch{batch_idx+1}": f"HTTP {response.status}: {response_text[:200]}"})
                        log_failed_barcodes(batch_items, f"Batch {batch_idx+1} HTTP {response.status}")

            except asyncio.TimeoutError:
                logger.error(f"Batch {batch_idx+1}: Zaman aşımı hatası")
                overall_success = False
                all_errors.update({f"batch{batch_idx+1}": "Zaman aşımı"})
                log_failed_barcodes(batch_items, f"Batch {batch_idx+1} zaman aşımı")

            except Exception as e:
                logger.error(f"Batch {batch_idx+1}: Beklenmeyen hata: {e}", exc_info=True)
                overall_success = False
                all_errors.update({f"batch{batch_idx+1}": f"Hata: {str(e)}"})
                log_failed_barcodes(batch_items, f"Batch {batch_idx+1} beklenmeyen hata: {str(e)}")

    success_rate = (total_success_count / len(items_list)) * 100 if items_list else 0
    logger.info(f"Toplam sonuç: {total_success_count}/{len(items_list)} ürün güncellendi (%{success_rate:.1f})")

    return overall_success, total_success_count, all_errors

def send_trendyol_stock_update_batch(items_list):
    if not API_KEY or not API_SECRET or not SUPPLIER_ID:
        logger.error("Trendyol API bilgileri eksik. Stok Trendyol'da güncellenemez.")
        return False, 0, {"general": "Trendyol API bilgileri sunucuda eksik."}

    if not items_list:
        logger.info("Trendyol'a gönderilecek ürün listesi boş.")
        return True, 0, {}

    batches = [items_list[i:i + BATCH_SIZE] for i in range(0, len(items_list), BATCH_SIZE)]
    logger.info(f"Toplam {len(items_list)} ürün, {len(batches)} batch'e bölündü (batch boyutu: {BATCH_SIZE})")

    overall_success = True
    total_success_count = 0
    all_errors = {}

    url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/products/price-and-inventory"
    credentials = f"{API_KEY}:{API_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/json",
        "User-Agent": f"GulluAyakkabiApp - Supplier {SUPPLIER_ID}"
    }

    for batch_idx, batch_items in enumerate(batches):
        if batch_idx > 0:
            time.sleep(0.5) 

        payload = {"items": batch_items}
        logger.debug(f"Batch {batch_idx+1}/{len(batches)}: {len(batch_items)} ürün gönderiliyor")

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)

            try:
                response_data = response.json() if response.content else {}
            except json.JSONDecodeError:
                logger.error(f"Batch {batch_idx+1}: Geçersiz JSON yanıtı: {response.text[:200]}...")
                overall_success = False
                all_errors.update({f"batch{batch_idx+1}": "Geçersiz JSON yanıtı"})
                log_failed_barcodes(batch_items, f"Batch {batch_idx+1} geçersiz JSON yanıtı")
                continue

            if response.status_code in [200, 202]:
                trendyol_errors = response_data.get('errors', []) + response_data.get('failures', [])

                if trendyol_errors:
                    logger.warning(f"Batch {batch_idx+1}: Yanıtta {len(trendyol_errors)} hata var")
                    for err in trendyol_errors:
                        barcode = err.get('barcode', f'Bilinmeyen-Batch{batch_idx+1}')
                        all_errors[barcode] = err.get('message', 'Bilinmeyen Hata')

                    failed_items_in_batch = [item for item in batch_items if item.get('barcode') in all_errors]
                    if failed_items_in_batch:
                        log_failed_barcodes(failed_items_in_batch, f"Batch {batch_idx+1} API hatası")

                batch_success_count = len(batch_items) - len(trendyol_errors)
                total_success_count += batch_success_count
                logger.info(f"Batch {batch_idx+1}: {batch_success_count}/{len(batch_items)} ürün başarıyla güncellendi")
            else:
                logger.error(f"Batch {batch_idx+1}: HTTP hatası {response.status_code} - {response.text[:200]}")
                overall_success = False
                all_errors.update({f"batch{batch_idx+1}": f"HTTP {response.status_code}: {response.text[:200]}"})
                log_failed_barcodes(batch_items, f"Batch {batch_idx+1} HTTP {response.status_code}")

        except requests.exceptions.Timeout:
            logger.error(f"Batch {batch_idx+1}: Zaman aşımı hatası")
            overall_success = False
            all_errors.update({f"batch{batch_idx+1}": "Zaman aşımı"})
            log_failed_barcodes(batch_items, f"Batch {batch_idx+1} zaman aşımı")

        except Exception as e:
            logger.error(f"Batch {batch_idx+1}: Beklenmeyen hata: {e}", exc_info=True)
            overall_success = False
            all_errors.update({f"batch{batch_idx+1}": f"Hata: {str(e)}"})
            log_failed_barcodes(batch_items, f"Batch {batch_idx+1} beklenmeyen hata: {str(e)}")

    success_rate = (total_success_count / len(items_list)) * 100 if items_list else 0
    logger.info(f"Toplam sonuç: {total_success_count}/{len(items_list)} ürün güncellendi (%{success_rate:.1f})")

    return overall_success, total_success_count, all_errors


def process_stock_update_batch(barcode_counts_data, update_type, async_mode=True):
    start_time = time.time()

    updated_db_count = 0
    db_errors = {}
    items_to_update_trendyol = []
    cached_items = 0

    all_barcodes = list(barcode_counts_data.keys())

    try:
        products = Product.query.filter(
            func.lower(Product.barcode).in_([b.lower() for b in all_barcodes])
        ).all()

        product_dict = {p.barcode.lower(): p for p in products}

        for barcode, item_data in barcode_counts_data.items():
            count = item_data.get('count', 0)
            product = product_dict.get(barcode.lower())

            if not product:
                db_errors[barcode] = f"Ürün veritabanında bulunamadı: {barcode}"
                logger.warning(f"Veritabanında ürün bulunamadı, atlanıyor: Barkod {barcode}")
                continue

            current_stock = product.quantity if product.quantity is not None else 0

            if update_type == 'renew':
                new_stock = count
            elif update_type == 'add':
                new_stock = current_stock + count
            else:
                db_errors[barcode] = f"Geçersiz güncelleme tipi: {update_type} (Barkod: {barcode})"
                logger.error(f"Geçersiz güncelleme tipi alındı: {update_type}")
                continue

            cached_stock = stock_cache.get(barcode)
            if cached_stock is not None and cached_stock == new_stock:
                logger.debug(f"Önbellekteki değer değişmedi, güncelleme atlanıyor: Barkod {barcode}, Stok: {new_stock}")
                cached_items += 1
                continue

            product.quantity = new_stock
            db.session.add(product)
            stock_cache[barcode] = new_stock

            items_to_update_trendyol.append({
                "barcode": product.barcode, 
                "quantity": new_stock
            })
            updated_db_count += 1

        db.session.commit()
        logger.info(f"Veritabanı güncellemeleri: Güncellenen: {updated_db_count}, Önbellekten: {cached_items}, Hatalı: {len(db_errors)}")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Veritabanı işlemleri sırasında hata: {e}", exc_info=True)
        return False, {
            "message": f"Veritabanı güncellemesi sırasında bir hata oluştu: {str(e)}",
            "dbErrors": db_errors, # 'errors' -> 'dbErrors'
            "trendyolUpdateErrors": {}
        }

    trendyol_update_success = False
    trendyol_successful_count = 0
    trendyol_update_errors = {}

    if items_to_update_trendyol:
        logger.info(f"Trendyol'a güncellenecek ürün sayısı: {len(items_to_update_trendyol)}")
        if async_mode:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                trendyol_update_success, trendyol_successful_count, trendyol_update_errors = loop.run_until_complete(
                    send_trendyol_stock_update_async(items_to_update_trendyol)
                )
            finally:
                loop.close()
        else:
            trendyol_update_success, trendyol_successful_count, trendyol_update_errors = send_trendyol_stock_update_batch(items_to_update_trendyol)
    else:
        logger.info("Trendyol'a gönderilecek ürün listesi boş, Trendyol güncellemesi atlanıyor.")
        trendyol_update_success = True 

    execution_time = time.time() - start_time
    logger.info(f"Toplam işlem süresi: {execution_time:.2f} saniye")

    response_message = f"Veritabanında {updated_db_count} ürün güncellendi, {cached_items} ürün önbellekten atlandı."

    if items_to_update_trendyol:
        if trendyol_update_success:
            response_message += f" Trendyol'da {trendyol_successful_count} ürün stoğu güncellendi."
            if trendyol_update_errors:
                response_message += f" Ancak {len(trendyol_update_errors)} üründe/batch'te hata oluştu."
        else:
            response_message += f" Trendyol stok güncellemesi başarısız oldu."
            if trendyol_update_errors.get("general"):
                 response_message += f" Genel Hata: {trendyol_update_errors.get('general')}"

    return True, {
        "message": response_message,
        "updatedDbCount": updated_db_count,
        "cachedItemsCount": cached_items,
        "trendyolUpdateSuccess": trendyol_update_success,
        "trendyolSuccessfulCount": trendyol_successful_count,
        "executionTime": f"{execution_time:.2f} saniye",
        "dbErrors": db_errors, 
        "trendyolUpdateErrors": trendyol_update_errors
    }

def background_stock_update(barcode_counts_data, update_type, async_mode=True):
    try:
        with current_app.app_context(): 
            logger.info(f"Arka plan stok güncelleme görevi başlatılıyor. Tip: {update_type}, Asenkron Trendyol: {async_mode}")
            process_stock_update_batch(barcode_counts_data, update_type, async_mode) 
            logger.info("Arka plan stok güncelleme işlemi tamamlandı.")
    except Exception as e:
        logger.error(f"Arka plan stok güncelleme hatası: {e}", exc_info=True)

@stock_management_bp.route('/stock-addition', methods=['GET'])
def stock_addition_screen():
    return render_template('stock_addition.html')

@stock_management_bp.route('/api/v2/bulk-stock-update', methods=['POST'])
@limiter.limit("30/minute")
def bulk_stock_update_v2():
    data = request.get_json()

    if not data or 'items' not in data:
        return jsonify(success=False, message="Geçersiz veri formatı. 'items' alanı gerekli."), 400

    items = data.get('items', [])
    update_type = data.get('updateType', 'renew')
    background_mode = data.get('backgroundMode', False)
    async_mode = data.get('asyncMode', True) 

    if not items:
        return jsonify(success=False, message="Güncellenecek ürün bulunamadı."), 400

    if update_type not in ['renew', 'add']:
        return jsonify(success=False, message="Geçersiz güncelleme tipi. 'renew' veya 'add' kullanın."), 400

    barcode_counts_data = {}
    for item in items:
        barcode = item.get('barcode')
        quantity = item.get('quantity', 0)
        if not barcode:
            continue
        barcode_counts_data[barcode] = {"count": quantity}

    logger.info(f"Toplu stok güncelleme isteği: {len(barcode_counts_data)} ürün, Tip: {update_type}, Arkaplanda: {background_mode}, Async Trendyol: {async_mode}")

    if background_mode:
        thread = Thread(target=background_stock_update, args=(barcode_counts_data, update_type, async_mode)) 
        thread.daemon = True
        thread.start()
        return jsonify(
            success=True,
            message=f"Stok güncelleme işlemi başlatıldı. {len(barcode_counts_data)} ürün arka planda işleniyor.",
            backgroundMode=True
        )
    else:
        start_time = time.time()
        success, result = process_stock_update_batch(barcode_counts_data, update_type, async_mode) 
        execution_time = time.time() - start_time

        logger.info(f"Stok güncelleme işlemi toplam süresi: {execution_time:.2f} saniye, "
                    f"ürün sayısı: {len(barcode_counts_data)}, "
                    f"ortalama: {(execution_time / len(barcode_counts_data) if barcode_counts_data else 0):.4f} saniye/ürün")

        if success: 
             return jsonify(success=True, **result)
        else: 
             return jsonify(success=False, **result), 500


@stock_management_bp.route('/api/v2/excel-stock-update', methods=['POST'])
@limiter.limit("10/minute")
@require_api_token 
def excel_stock_update():
    if 'excel_file' not in request.files:
        return jsonify(success=False, message="Excel dosyası bulunamadı"), 400

    file = request.files['excel_file']
    if file.filename == '':
        return jsonify(success=False, message="Dosya seçilmedi"), 400

    update_type = request.form.get('update_type', 'renew')
    background_mode = request.form.get('background_mode', 'false').lower() == 'true'
    async_mode = request.form.get('async_mode', 'true').lower() == 'true' 

    if update_type not in ['renew', 'add']:
        return jsonify(success=False, message="Geçersiz güncelleme tipi. 'renew' veya 'add' kullanın."), 400

    try:
        import pandas as pd
        df = pd.read_excel(file)
        required_columns = ['barcode', 'quantity']
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            return jsonify(success=False, 
                           message=f"Excel dosyasında eksik kolonlar: {', '.join(missing_columns)}. "
                                   f"Gerekli kolonlar: {', '.join(required_columns)}"), 400

        barcode_counts_data = {}
        for _, row in df.iterrows():
            barcode = str(row['barcode']).strip()
            quantity = row['quantity']

            if not barcode or pd.isna(barcode) or barcode.lower() == 'nan': 
                continue

            if pd.isna(quantity) or not isinstance(quantity, (int, float)) or quantity < 0: 
                logger.warning(f"Excel'de geçersiz quantity: Barkod {barcode}, Quantity {quantity} - atlanıyor.")
                continue

            barcode_counts_data[barcode] = {"count": int(quantity)}

        if not barcode_counts_data:
            return jsonify(success=False, message="İşlenebilir ürün verisi bulunamadı"), 400

        logger.info(f"Excel'den {len(barcode_counts_data)} ürün işlenecek. Tip: {update_type}, Arkaplanda: {background_mode}, Async Trendyol: {async_mode}")

        if background_mode:
            thread = Thread(target=background_stock_update, args=(barcode_counts_data, update_type, async_mode)) 
            thread.daemon = True
            thread.start()
            return jsonify(
                success=True,
                message=f"Stok güncelleme işlemi başlatıldı. {len(barcode_counts_data)} ürün arka planda işleniyor.",
                backgroundMode=True
            )
        else:
            start_time = time.time()
            success, result = process_stock_update_batch(barcode_counts_data, update_type, async_mode) 
            execution_time = time.time() - start_time
            logger.info(f"Excel stok güncelleme işlemi toplam süresi: {execution_time:.2f} saniye")

            if success:
                return jsonify(success=True, **result)
            else:
                return jsonify(success=False, **result), 500

    except ImportError:
        logger.error("Pandas kütüphanesi kurulu değil. Excel işleme yapılamıyor.")
        return jsonify(success=False, message="Sunucu hatası: Excel işleme için gerekli kütüphane eksik."), 500
    except Exception as e:
        logger.error(f"Excel işleme hatası: {e}", exc_info=True)
        return jsonify(success=False, message=f"Excel dosyası işlenemedi: {str(e)}"), 500

# --- YENİ ENDPOINT'LER (Model Kodu Bazlı Analiz için) ---

@stock_management_bp.route('/api/get-unique-main-ids', methods=['GET'])
@limiter.limit("60/minute")
def get_unique_main_ids():
    """
    Veritabanındaki tüm benzersiz product_main_id (model kodu) değerlerini,
    o modele ait bir örnek başlık ve toplam varyant sayısıyla birlikte döndürür.
    Dropdown'da "MODEL_KODU (X Varyant)" şeklinde gösterilmesi hedeflenir.
    """
    logger.info("Benzersiz model kodları listesi isteği (Stok Analizi için).")
    try:
        # Her product_main_id için varyant sayısını ve alfabetik ilk başlığı çek
        results = db.session.query(
            Product.product_main_id,
            func.min(Product.title).label("sample_title"), 
            func.count(Product.id).label("variant_count")
        ).filter(
            Product.product_main_id.isnot(None),
            Product.product_main_id != ''
        ).group_by(
            Product.product_main_id
        ).order_by(
            Product.product_main_id
        ).all()

        unique_models_for_dropdown = []
        if results:
            for main_id, _sample_title, variant_count in results: # sample_title'ı şimdilik display_text'te kullanmıyoruz
                # Dropdown'da gösterilecek metin: "MODEL_KODU (X Varyant)"
                # Model kodunun temiz olduğunu varsayıyoruz (örn: "0023", "ABC01" gibi).
                # Eğer product_main_id veritabanında zaten "0023 - Siyah Ayakkabı" gibi ise,
                # bu fonksiyonun mantığı değişmeli veya veritabanı düzeltilmeli.
                display_text = f"{main_id} ({variant_count} varyant)"

                unique_models_for_dropdown.append({
                    "id_for_select": main_id,              # Seçildiğinde bu değer kullanılacak
                    "text_for_select": display_text,       # Dropdown'da bu görünecek
                    "representative_title": _sample_title  # Ek bilgi olarak, frontend'de farklı bir yerde kullanılabilir
                })

        logger.info(f"{len(unique_models_for_dropdown)} adet benzersiz model seçeneği oluşturuldu (Stok Analizi için).")
        return jsonify(success=True, unique_model_options=unique_models_for_dropdown)

    except Exception as e:
        logger.error(f"Benzersiz model kodları çekilirken hata (Stok Analizi için): {e}", exc_info=True)
        return jsonify(success=False, message="Model kodları alınamadı."), 500

@stock_management_bp.route('/api/get-products-by-main-id/<string:product_main_id_param>', methods=['GET'])
@limiter.limit("60/minute") 
def get_products_by_main_id(product_main_id_param):
    """
    Veritabanından verilen product_main_id'ye (model kodu) sahip tüm ürünleri
    (farklı barkodlar, renkler, bedenler, başlıklar dahil) döndürür.
    NOT: Route parametresi 'product_main_id_param' olarak değiştirildi, Python değişkeniyle karışmasın diye.
    """
    logger.info(f"Model koduna göre ürün listesi isteği alındı: Model Kodu {product_main_id_param}")
    try:
        products_query = Product.query.filter(
            Product.product_main_id == product_main_id_param
        ).order_by(Product.color, Product.size).all()

        if products_query:
            logger.debug(f"{len(products_query)} adet ürün bulundu: Model Kodu {product_main_id_param}")

            product_list_response = []
            model_general_title = products_query[0].title # İlk ürünün başlığını genel başlık olarak alabiliriz
                                                       # veya product_main_id'den sonraki kısmı

            for product_item in products_query:
                image_urls = []
                if product_item.images:
                    try:
                        image_data = json.loads(product_item.images)
                        if isinstance(image_data, list):
                            image_urls = image_data
                        elif isinstance(image_data, str): 
                            image_urls = [image_data]
                    except (json.JSONDecodeError, TypeError): 
                        image_urls = [product_item.images] if isinstance(product_item.images, str) else []

                first_image_url = image_urls[0] if image_urls else 'https://placehold.co/80x80'

                product_list_response.append({
                    'id': product_item.id, 
                    'barcode': product_item.barcode,
                    'product_main_id': product_item.product_main_id,
                    'title': product_item.title, 
                    'color': product_item.color,
                    'size': product_item.size,
                    'quantity': product_item.quantity if product_item.quantity is not None else 0,
                    'image_url': first_image_url,
                })

            return jsonify(
                success=True,
                products=product_list_response,
                model_code=product_main_id_param, # Seçilen model kodunu geri döndür
                model_title=model_general_title 
            )
        else:
            logger.warning(f"Bu model koduna ait ürün bulunamadı: Model Kodu {product_main_id_param}")
            return jsonify(success=False, message=f"'{product_main_id_param}' model koduna ait ürün bulunamadı."), 404

    except Exception as e:
        logger.error(f"Model koduna göre ürün bilgisi çekilirken hata: {e}", exc_info=True)
        return jsonify(success=False, message=f"Ürün bilgisi çekilirken sunucu hatası: {str(e)}"), 500

# --- MEVCUT ENDPOINT'LERİN GÜNCELLENMİŞ HALLERİ ---

@stock_management_bp.route('/api/get-product-details-by-barcode/<barcode>', methods=['GET'])
@limiter.limit("120/minute") 
def get_product_details_by_barcode(barcode):
    logger.debug(f"Ürün detayları isteği alındı: Barkod {barcode}")
    try:
        product = Product.query.filter(func.lower(Product.barcode) == barcode.lower()).first()

        if product:
            logger.debug(f"Ürün bulundu: Barkod {barcode}")
            image_urls = []
            if product.images:
                try:
                    image_data = json.loads(product.images)
                    if isinstance(image_data, list):
                        image_urls = image_data
                    elif isinstance(image_data, str):
                        image_urls = [image_data]
                except (json.JSONDecodeError, TypeError):
                    image_urls = [product.images] if isinstance(product.images, str) else []

            first_image_url = image_urls[0] if image_urls else 'https://placehold.co/50x50'

            return jsonify(
                success=True,
                product={
                    'id': product.id,
                    'barcode': product.barcode,
                    'product_main_id': product.product_main_id,
                    'title': product.title, # Product modelinde title alanı olduğunu varsayıyoruz
                    'color': product.color,
                    'size': product.size,
                    'quantity': product.quantity if product.quantity is not None else 0,
                    'image_url': first_image_url
                }
            )
        else:
            logger.warning(f"Ürün bulunamadı: Barkod {barcode}")
            return jsonify(success=False, message="Ürün veritabanında bulunamadı."), 404

    except Exception as e:
        logger.error(f"Veritabanından ürün bilgisi çekilirken hata: {e}", exc_info=True)
        return jsonify(success=False, message=f"Ürün bilgisi çekilirken sunucu hatası: {str(e)}"), 500

@stock_management_bp.route('/stock-addition', methods=['POST']) 
@limiter.limit("30/minute")
def handle_stock_update():
    data = request.get_json()

    if not data:
        return jsonify(success=False, message="Geçersiz veri formatı"), 400

    barcode_counts_data = data.get('barcodeCounts') 
    update_type = data.get('updateType')
    background_mode = data.get('backgroundMode', False)
    async_mode = data.get('asyncMode', True) 

    if not barcode_counts_data or not update_type:
        return jsonify(success=False, message="Eksik veri: Barkodlar veya güncelleme tipi belirtilmemiş"), 400

    if not isinstance(barcode_counts_data, dict): # Ekstra kontrol
        return jsonify(success=False, message="'barcodeCounts' bir sözlük olmalı."), 400

    logger.info(f"Stok güncelleme isteği (/stock-addition POST): Tip: {update_type}, İşlenecek Barkod Sayısı: {len(barcode_counts_data)}, Arkaplan: {background_mode}, Async Trendyol: {async_mode}")

    client_info = {
        'ip': request.remote_addr,
        'user_agent': request.headers.get('User-Agent', 'Bilinmiyor'),
        'timestamp': datetime.now().isoformat()
    }
    logger.info(f"Stok güncelleme isteği bilgileri: {client_info}")

    if background_mode:
        thread = Thread(target=background_stock_update, args=(barcode_counts_data, update_type, async_mode)) 
        thread.daemon = True
        thread.start()

        return jsonify(
            success=True,
            message=f"Stok güncelleme işlemi başlatıldı. {len(barcode_counts_data)} ürün arka planda işleniyor.",
            backgroundMode=True
        )
    else:
        start_time = time.time()
        success, result = process_stock_update_batch(barcode_counts_data, update_type, async_mode) 
        execution_time = time.time() - start_time

        logger.info(f"Stok güncelleme işlemi toplam süresi: {execution_time:.2f} saniye, "
                    f"ürün sayısı: {len(barcode_counts_data)}, "
                    f"ortalama: {(execution_time / len(barcode_counts_data) if barcode_counts_data else 0):.4f} saniye/ürün")

        if success: 
            return jsonify(success=True, **result)
        else: 
            return jsonify(success=False, **result), 500