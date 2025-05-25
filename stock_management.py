# stock_management.py

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
# Product modelini import et
from models import db, Product
import json
import logging
import os
import time
from datetime import datetime
from threading import Thread
from functools import wraps
import aiohttp
import asyncio
from sqlalchemy import text, and_, or_, func
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Trendyol stok güncelleme fonksiyonunu kullanacağız
# get_products.py dosyasından Trendyol API bilgileri ve request kütüphanesini kullanıyoruz
# Not: API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL gibi bilgiler trendyol_api.py dosyasında olmalı
import base64
import requests
try:
    from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL
    # Trendyol API bilgileri yüklendiğinde logla
    logger = logging.getLogger(__name__)
    logger.info("Trendyol API bilgileri başarıyla yüklendi.")
except ImportError:
    # trendyol_api.py bulunamazsa veya içinde bilgiler eksikse hata ver
    logger = logging.getLogger(__name__)
    logger.error("trendyol_api.py dosyası bulunamadı veya Trendyol API bilgileri (API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL) eksik.")
    # Eksik bilgileri tutacak placeholder değişkenler tanımla
    API_KEY = None
    API_SECRET = None
    SUPPLIER_ID = None
    BASE_URL = "https://api.trendyol.com/sapigw/" # Base URL'i yine de tanımlayalım

# Uygulama ortamına göre log seviyesini ayarla
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
LOG_LEVEL_MAP = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR
}

# Log ayarları
logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL_MAP.get(LOG_LEVEL, logging.INFO))
if not logger.handlers:
    handler = logging.StreamHandler() # Konsola yazması için StreamHandler kullanabiliriz
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Rate limiting için limiter oluştur (uygulama başlatılırken app'i register edecek)
limiter = Limiter(key_func=get_remote_address)

# API token kontrolü için decorator
def require_api_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('X-API-Token')
        expected_token = current_app.config.get('API_TOKEN')
        
        # Token kontrolü
        if not token or token != expected_token:
            logger.warning(f"Geçersiz API token erişim denemesi: {request.remote_addr}")
            return jsonify(success=False, message="Geçersiz API token"), 403
        return f(*args, **kwargs)
    return decorated_function

# Son değerlerin cache'de tutulması için basit bir cache
stock_cache = {}  # {barcode: quantity} formatında önbellekte tutulan son stok değerleri

stock_management_bp = Blueprint('stock_management', __name__)

# Batch işleme için parça boyutu ayarı
BATCH_SIZE = 100  # Trendyol'a en fazla kaç ürünü tek seferde göndereceğiz

# Hatalı barkodları kaydetmek için fonksiyon
def log_failed_barcodes(failed_items, reason=""):
    """Hatalı barkodları bir dosyaya kaydeder"""
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

# Asenkron batch gönderimleri için fonksiyon
async def send_trendyol_stock_update_async(items_list, batch_size=BATCH_SIZE):
    """
    Trendyol API'ye asenkron olarak batch halinde stok güncellemesi gönderir.
    
    Args:
        items_list: Güncellenecek ürünlerin listesi
        batch_size: Her batch'te kaç ürün gönderileceği
        
    Returns:
        Tuple: (success, success_count, error_details)
    """
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

    # Ürünleri batch_size kadar gruplara böl
    batches = [items_list[i:i + batch_size] for i in range(0, len(items_list), batch_size)]
    logger.info(f"Toplam {len(items_list)} ürün, {len(batches)} batch'e bölündü (batch boyutu: {batch_size})")

    overall_success = True
    total_success_count = 0
    all_errors = {}
    
    async with aiohttp.ClientSession() as session:
        # Her batch için asenkron gönderi
        for batch_idx, batch_items in enumerate(batches):
            # API rate limit için bekleme - art arda çok hızlı istek göndermemek için
            if batch_idx > 0:
                await asyncio.sleep(0.5)  # Her batch arasında 500ms bekle
                
            try:
                payload = {"items": batch_items}
                logger.debug(f"Batch {batch_idx+1}/{len(batches)}: {len(batch_items)} ürün gönderiliyor")
                
                # Asenkron API çağrısı
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
                        # Trendyol'un döndürdüğü hataları kontrol et
                        trendyol_errors = response_data.get('errors', []) + response_data.get('failures', [])
                        
                        if trendyol_errors:
                            logger.warning(f"Batch {batch_idx+1}: Yanıtta {len(trendyol_errors)} hata var")
                            # Hata detaylarını topla
                            for err in trendyol_errors:
                                barcode = err.get('barcode', f'Bilinmeyen-Batch{batch_idx+1}')
                                all_errors[barcode] = err.get('message', 'Bilinmeyen Hata')
                                
                            # Başarısız ürünleri logla
                            failed_items = [item for item in batch_items if item.get('barcode') in all_errors]
                            log_failed_barcodes(failed_items, f"Batch {batch_idx+1} API hatası")
                        
                        # Bu batch'teki başarılı sayısını hesapla
                        batch_success_count = len(batch_items) - len(trendyol_errors)
                        total_success_count += batch_success_count
                        logger.info(f"Batch {batch_idx+1}: {batch_success_count}/{len(batch_items)} ürün başarıyla güncellendi")
                    else:
                        # HTTP hata kodu
                        logger.error(f"Batch {batch_idx+1}: HTTP hatası {response.status} - {response_text[:200]}")
                        overall_success = False
                        all_errors.update({f"batch{batch_idx+1}": f"HTTP {response.status}: {response_text[:200]}"})
                        # Bu batch'teki tüm ürünleri hataya logla
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
    
    # Özetleme
    success_rate = (total_success_count / len(items_list)) * 100 if items_list else 0
    logger.info(f"Toplam sonuç: {total_success_count}/{len(items_list)} ürün güncellendi (%{success_rate:.1f})")
    
    return overall_success, total_success_count, all_errors

# Eski senkron fonksiyonu da tutalım (geriye uyumluluk için)
def send_trendyol_stock_update_batch(items_list):
    """
    Trendyol API üzerinden birden fazla ürünün stoğunu toplu olarak günceller.
    Trendyol'un /products/price-and-inventory endpoint'ini kullanır.

    items_list: [{"barcode": "BARKOD1", "quantity": 10}, {"barcode": "BARKOD2", "quantity": 5}, ...] formatında liste
    """
    if not API_KEY or not API_SECRET or not SUPPLIER_ID:
        logger.error("Trendyol API bilgileri eksik. Stok Trendyol'da güncellenemez.")
        return False, 0, {"general": "Trendyol API bilgileri sunucuda eksik."} # Genel hata döndür

    if not items_list:
        logger.info("Trendyol'a gönderilecek ürün listesi boş.")
        return True, 0, {} # Boş liste göndermek başarı sayılır ama güncellenen 0 olur

    # Ürünleri BATCH_SIZE kadar parçalara böl
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
        "User-Agent": f"GulluAyakkabiApp - Supplier {SUPPLIER_ID}" # İyi pratik: API çağrılarında User-Agent göndermek
    }

    # Her batch için
    for batch_idx, batch_items in enumerate(batches):
        # API rate limit için bekleme
        if batch_idx > 0:
            time.sleep(0.5)  # Her batch arasında 500ms bekle
            
        payload = {"items": batch_items}
        logger.debug(f"Batch {batch_idx+1}/{len(batches)}: {len(batch_items)} ürün gönderiliyor") 

        try:
            # Synchronous POST isteği Trendyol'a gönderilir
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
                # Trendyol'un döndürdüğü hataları kontrol et
                trendyol_errors = response_data.get('errors', []) + response_data.get('failures', [])
                
                if trendyol_errors:
                    logger.warning(f"Batch {batch_idx+1}: Yanıtta {len(trendyol_errors)} hata var")
                    for err in trendyol_errors:
                        barcode = err.get('barcode', f'Bilinmeyen-Batch{batch_idx+1}')
                        all_errors[barcode] = err.get('message', 'Bilinmeyen Hata')
                    
                    # Başarısız ürünleri logla
                    failed_items = [item for item in batch_items if item.get('barcode') in all_errors]
                    log_failed_barcodes(failed_items, f"Batch {batch_idx+1} API hatası")
                
                # Bu batch'teki başarılı sayısını hesapla
                batch_success_count = len(batch_items) - len(trendyol_errors)
                total_success_count += batch_success_count
                logger.info(f"Batch {batch_idx+1}: {batch_success_count}/{len(batch_items)} ürün başarıyla güncellendi")
            else:
                # HTTP hata kodu
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

    # Özetleme
    success_rate = (total_success_count / len(items_list)) * 100 if items_list else 0
    logger.info(f"Toplam sonuç: {total_success_count}/{len(items_list)} ürün güncellendi (%{success_rate:.1f})")
    
    return overall_success, total_success_count, all_errors


# Senkron veya asenkron stok güncelleme yapan fonksiyon
def process_stock_update_batch(barcode_counts_data, update_type, async_mode=True):
    """
    Veritabanı ve Trendyol stok güncellemesini toplu olarak yapar.
    
    Args:
        barcode_counts_data: {"barkod1": {"count": 5, "details": {...}}, ...} formatında sözlük
        update_type: "renew" veya "add" formatında güncelleme tipi
        async_mode: True ise asenkron Trendyol güncellemesi, False ise senkron
        
    Returns:
        Tuple: (success, results_dict)
    """
    start_time = time.time()  # İşlemin başlangıç zamanı
    
    updated_db_count = 0  # Veritabanında güncellenen ürün sayısı
    db_errors = {}  # Veritabanı güncelleme sırasında oluşan hatalar
    items_to_update_trendyol = []  # Trendyol'a gönderilecek ürün listesi
    cached_items = 0  # Önbellekten dolayı güncellenmeyenler
    
    # Barkodları bir listede toplayalım (toplu sorgu için)
    all_barcodes = list(barcode_counts_data.keys())
    
    # Veritabanı işlemleri ve Trendyol listesini hazırlama
    try:
        # Tüm ürünleri tek seferde sorgula (N+1 sorgu problemini önlemek için)
        # Büyük/küçük harf duyarsız sorgu yapmak için
        # SQLAlchemy'nin func.lower kullanılıyor
        products = Product.query.filter(
            func.lower(Product.barcode).in_([b.lower() for b in all_barcodes])
        ).all()
        
        # Barkodlara göre hızlı erişim için sözlük oluştur (case-insensitive)
        product_dict = {p.barcode.lower(): p for p in products}
        
        # Önbellekte olmayan ürünler için batch güncelleme
        for barcode, item_data in barcode_counts_data.items():
            count = item_data.get('count', 0)
            
            # Ürünü barkod sözlüğünde bul (büyük/küçük harf duyarsız)
            product = product_dict.get(barcode.lower())
            
            if not product:
                db_errors[barcode] = f"Ürün veritabanında bulunamadı: {barcode}"
                logger.warning(f"Veritabanında ürün bulunamadı, atlanıyor: Barkod {barcode}")
                continue
            
            # Mevcut stok miktarını al (None ise 0 say)
            current_stock = product.quantity if product.quantity is not None else 0
            
            # Güncelleme tipine göre yeni stok miktarını hesapla
            if update_type == 'renew':
                new_stock = count
                logger.debug(f"Stok yenileme: Barkod {barcode}, Eski Stok: {current_stock}, Yeni Stok: {new_stock}")
            elif update_type == 'add':
                new_stock = current_stock + count
                logger.debug(f"Stok ekleme: Barkod {barcode}, Eski Stok: {current_stock}, Eklenecek: {count}, Yeni Stok: {new_stock}")
            else:
                db_errors[barcode] = f"Geçersiz güncelleme tipi: {update_type} (Barkod: {barcode})"
                logger.error(f"Geçersiz güncelleme tipi alındı: {update_type}")
                continue
            
            # Önbellekte son stok değeri varsa ve aynıysa güncelleme yapmayalım
            cached_stock = stock_cache.get(barcode)
            if cached_stock is not None and cached_stock == new_stock:
                logger.debug(f"Önbellekteki değer değişmedi, güncelleme atlanıyor: Barkod {barcode}, Stok: {new_stock}")
                cached_items += 1
                continue
            
            # Stok değişmişse veya önbellekte yoksa güncelleme yap
            product.quantity = new_stock
            db.session.add(product)
            
            # Önbelleğe yeni değeri kaydet
            stock_cache[barcode] = new_stock
            
            # Trendyol güncellemesi için listeye ekle
            items_to_update_trendyol.append({
                "barcode": product.barcode, 
                "quantity": new_stock
            })
            
            updated_db_count += 1
            
        # Tüm veritabanı değişikliklerini kaydet (Tek commit!)
        db.session.commit()
        logger.info(f"Veritabanı güncellemeleri başarıyla commit edildi. " 
                    f"Güncellenen: {updated_db_count}, Önbellekten atlanılan: {cached_items}, "
                    f"Hatalı: {len(db_errors)}")
        
    except Exception as e:
        # Veritabanı işlemleri sırasında bir hata oluşursa rollback yap
        db.session.rollback()
        logger.error(f"Veritabanı işlemleri sırasında hata: {e}", exc_info=True)
        return False, {
            "message": f"Veritabanı güncellemesi sırasında bir hata oluştu: {str(e)}",
            "errors": db_errors,
            "trendyolUpdateErrors": {}
        }
    
    # --- Trendyol API'ye toplu stok güncellemesi gönderme ---
    trendyol_update_success = False
    trendyol_successful_count = 0
    trendyol_update_errors = {}
    
    if items_to_update_trendyol:
        logger.info(f"Trendyol'a güncellenecek ürün sayısı: {len(items_to_update_trendyol)}")
        
        # Asenkron veya senkron güncelleme
        if async_mode:
            # asyncio.run() kullanmak yerine daha güvenli bir yöntem (Flask içinde çalıştığı için)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                trendyol_update_success, trendyol_successful_count, trendyol_update_errors = loop.run_until_complete(
                    send_trendyol_stock_update_async(items_to_update_trendyol)
                )
            finally:
                loop.close()
        else:
            # Senkron güncelleme (eski yöntem)
            trendyol_update_success, trendyol_successful_count, trendyol_update_errors = send_trendyol_stock_update_batch(items_to_update_trendyol)
    else:
        logger.info("Trendyol'a gönderilecek ürün listesi boş, Trendyol güncellemesi atlanıyor.")
        trendyol_update_success = True
    
    # İşlem süresi
    execution_time = time.time() - start_time
    logger.info(f"Toplam işlem süresi: {execution_time:.2f} saniye")
    
    # Sonuç mesajını oluştur
    response_message = f"Veritabanında {updated_db_count} ürün güncellendi, {cached_items} ürün önbellekten atlandı."
    
    if items_to_update_trendyol:
        if trendyol_update_success:
            response_message += f" Trendyol'da {trendyol_successful_count} ürün stoğu güncellendi."
            if trendyol_update_errors:
                response_message += f" Ancak {len(trendyol_update_errors)} üründe hata oluştu."
        else:
            response_message += f" Trendyol stok güncellemesi başarısız oldu."
    
    return True, {
        "message": response_message,
        "updatedDbCount": updated_db_count,
        "cachedItemsCount": cached_items,
        "trendyolUpdateSuccess": trendyol_update_success,
        "trendyolSuccessfulCount": trendyol_successful_count,
        "executionTime": f"{execution_time:.2f} saniye",
        "errors": db_errors,
        "trendyolUpdateErrors": trendyol_update_errors
    }

# Asenkron arka plan görevi
def background_stock_update(barcode_counts_data, update_type):
    """Stok güncellemesini arka planda çalıştırır"""
    try:
        with current_app.app_context():
            process_stock_update_batch(barcode_counts_data, update_type)
            logger.info("Arka plan stok güncelleme işlemi tamamlandı")
    except Exception as e:
        logger.error(f"Arka plan stok güncelleme hatası: {e}", exc_info=True)

@stock_management_bp.route('/stock-addition', methods=['GET'])
def stock_addition_screen():
    """
    Stok ekleme ekranını render eder.
    """
    # HTML şablonunu render et
    return render_template('stock_addition.html')

# Yeni, hızlı toplu stok güncelleme endpoint'i
@stock_management_bp.route('/api/v2/bulk-stock-update', methods=['POST'])
@limiter.limit("30/minute")  # Rate limiting ekle
# API token kontrolünü şimdilik devre dışı bıraktık
# @require_api_token
def bulk_stock_update_v2():
    """
    Toplu stok güncelleme işlemi için optimize edilmiş yeni API endpoint.
    
    Özellikler:
    - Toplu DB sorgusu (in_)
    - Batch API gönderimleri
    - Asenkron işleme
    - Önbellek kontrolü
    - Detaylı loglama
    
    JSON Giriş Formatı:
    {
        "items": [
            {"barcode": "1234567890", "quantity": 10}, 
            {"barcode": "0987654321", "quantity": 5}
        ],
        "updateType": "renew" veya "add",
        "backgroundMode": true/false (isteğe bağlı),
        "asyncMode": true/false (isteğe bağlı)
    }
    """
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
    
    # items listesini barcodeCounts formatına dönüştür
    barcode_counts_data = {}
    for item in items:
        barcode = item.get('barcode')
        quantity = item.get('quantity', 0)
        
        if not barcode:
            continue
            
        barcode_counts_data[barcode] = {"count": quantity}
    
    # İstek kaynağını logla
    client_info = {
        'ip': request.remote_addr,
        'user_agent': request.headers.get('User-Agent', 'Bilinmiyor'),
        'timestamp': datetime.now().isoformat()
    }
    logger.info(f"Toplu stok güncelleme isteği: {len(barcode_counts_data)} ürün, Tip: {update_type}, Arkaplanda: {background_mode}")
    
    if background_mode:
        # Arka planda çalıştır ve hemen cevap döndür
        thread = Thread(target=background_stock_update, args=(barcode_counts_data, update_type))
        thread.daemon = True
        thread.start()
        
        return jsonify(
            success=True,
            message=f"Stok güncelleme işlemi başlatıldı. {len(barcode_counts_data)} ürün arka planda işleniyor.",
            backgroundMode=True
        )
    else:
        # Senkron işle ve sonucu bekle
        start_time = time.time()
        success, result = process_stock_update_batch(barcode_counts_data, update_type, async_mode)
        execution_time = time.time() - start_time
        
        # İşlem süresini logla (performans analizi için)
        logger.info(f"Stok güncelleme işlemi toplam süresi: {execution_time:.2f} saniye, " 
                   f"ürün sayısı: {len(barcode_counts_data)}, "
                   f"ortalama: {(execution_time / len(barcode_counts_data) if barcode_counts_data else 0):.4f} saniye/ürün")
        
        if success:
            return jsonify(
                success=True,
                **result
            )
        else:
            return jsonify(
                success=False,
                **result
            ), 500

# Excel ile stok güncelleme endpoint'i
@stock_management_bp.route('/api/v2/excel-stock-update', methods=['POST'])
@limiter.limit("10/minute")  # Excel daha büyük veri olduğundan rate limit daha düşük
@require_api_token
def excel_stock_update():
    """
    Excel dosyası ile toplu stok güncelleme.
    
    Form alanları:
    - excel_file: Excel dosyası
    - update_type: 'renew' veya 'add'
    - background_mode: 'true' veya 'false'
    """
    if 'excel_file' not in request.files:
        return jsonify(success=False, message="Excel dosyası bulunamadı"), 400
        
    file = request.files['excel_file']
    if file.filename == '':
        return jsonify(success=False, message="Dosya seçilmedi"), 400
    
    update_type = request.form.get('update_type', 'renew')
    background_mode = request.form.get('background_mode', 'false').lower() == 'true'
    
    if update_type not in ['renew', 'add']:
        return jsonify(success=False, message="Geçersiz güncelleme tipi. 'renew' veya 'add' kullanın."), 400
    
    try:
        # Excel dosyasını işle - pandas veya openpyxl kullanarak
        import pandas as pd
        
        # Excel'den DataFrame oku
        df = pd.read_excel(file)
        
        # Excel'de beklenen kolonlar: 'barcode' ve 'quantity'
        required_columns = ['barcode', 'quantity']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return jsonify(success=False, 
                          message=f"Excel dosyasında eksik kolonlar: {', '.join(missing_columns)}. "
                                  f"Gerekli kolonlar: {', '.join(required_columns)}"), 400
        
        # DataFrame'den barcode_counts_data oluştur
        barcode_counts_data = {}
        for _, row in df.iterrows():
            barcode = str(row['barcode']).strip()
            quantity = row['quantity']
            
            # Boş veya geçersiz barkodları atla
            if not barcode or pd.isna(barcode) or barcode == 'nan':
                continue
                
            # Geçersiz sayıları atla
            if pd.isna(quantity) or quantity < 0:
                continue
                
            barcode_counts_data[barcode] = {"count": int(quantity)}
        
        if not barcode_counts_data:
            return jsonify(success=False, message="İşlenebilir ürün verisi bulunamadı"), 400
            
        logger.info(f"Excel'den {len(barcode_counts_data)} ürün işlenecek. Tip: {update_type}, Arkaplanda: {background_mode}")
        
        if background_mode:
            # Arka planda çalıştır ve hemen cevap döndür
            thread = Thread(target=background_stock_update, args=(barcode_counts_data, update_type))
            thread.daemon = True
            thread.start()
            
            return jsonify(
                success=True,
                message=f"Stok güncelleme işlemi başlatıldı. {len(barcode_counts_data)} ürün arka planda işleniyor.",
                backgroundMode=True
            )
        else:
            # Senkron işle ve sonucu bekle
            start_time = time.time()
            success, result = process_stock_update_batch(barcode_counts_data, update_type, True)
            execution_time = time.time() - start_time
            
            if success:
                return jsonify(
                    success=True,
                    **result
                )
            else:
                return jsonify(
                    success=False,
                    **result
                ), 500
                
    except Exception as e:
        logger.error(f"Excel işleme hatası: {e}", exc_info=True)
        return jsonify(success=False, message=f"Excel dosyası işlenemedi: {str(e)}"), 500

# Yeni API endpoint'i: Barkoda göre ürün bilgisi döndürür
@stock_management_bp.route('/api/get-product-details-by-barcode/<barcode>', methods=['GET'])
def get_product_details_by_barcode(barcode):
    """
    Veritabanından barkoda göre ürün bilgilerini döndürür.
    """
    logger.debug(f"Ürün detayları isteği alındı: Barkod {barcode}")
    try:
        # Product modelinden barkoda göre ürünü bul
        # Büyük/küçük harf duyarlılığı olmaması için lower() kullanabiliriz
        # Trendyol bazen barkodları farklı kaydedebiliyor, her ihtimale karşı hem büyük hem küçük harfle arayalım
        # veya kaydederken hep büyük/küçük harfe çevirelim. Şimdilik ararken lower() yeterli.
        product = Product.query.filter(db.func.lower(Product.barcode) == barcode.lower()).first()

        if product:
            # Ürün bulunduğunda bilgileri JSON olarak döndür
            logger.debug(f"Ürün bulundu: Barkod {barcode}")
            # images kolonu bir JSON string olabilir, onu listeye çevirelim eğer öyleyse
            image_urls = []
            if product.images:
                try:
                    # images kolonunun JSON listesi formatında olduğunu varsayalım
                    # Örnek: '["url1", "url2"]'
                    image_data = json.loads(product.images)
                    if isinstance(image_data, list):
                         image_urls = image_data
                    elif isinstance(image_data, str): # Belki tek bir URL string olarak kaydedilmiştir
                         image_urls = [image_data]
                except json.JSONDecodeError:
                    # JSON formatında değilse, belki sadece tek bir URL stringidir
                    image_urls = [product.images]
                except TypeError:
                     # images None veya beklenmedik tipte ise
                     image_urls = []

            # İlk resmi gönderiyoruz frontende
            first_image_url = image_urls[0] if image_urls else 'https://placehold.co/50x50'


            return jsonify(
                success=True,
                product={
                    'barcode': product.barcode,
                    'product_main_id': product.product_main_id, # model kodu gibi
                    'color': product.color,
                    'size': product.size,
                    'quantity': product.quantity, # Mevcut stok miktarını ekledim
                    'image_url': first_image_url # Frontend için ilk resim
                    # 'all_image_urls': image_urls # Eğer tüm resimler lazımsa bu da gönderilebilir
                }
            )
        else:
            # Ürün bulunamazsa hata döndür
            logger.warning(f"Ürün bulunamadı: Barkod {barcode}")
            return jsonify(success=False, message="Ürün veritabanında bulunamadı."), 404 # 404 Not Found uygun

    except Exception as e:
        # Veritabanı sorgusu sırasında hata oluşursa
        logger.error(f"Veritabanından ürün bilgisi çekilirken hata: {e}", exc_info=True)
        return jsonify(success=False, message=f"Ürün bilgisi çekilirken sunucu hatası: {str(e)}"), 500 # 500 Internal Server Error

@stock_management_bp.route('/stock-addition', methods=['POST'])
@limiter.limit("30/minute")  # Rate limiting ekle
# API token kontrolünü şimdilik devre dışı bıraktık
# @require_api_token
def handle_stock_update():
    """
    Frontend'den gelen barkod ve güncelleme tipi bilgisiyle stoğu günceller.
    Veritabanını güncelledikten sonra Trendyol'a toplu güncelleme isteği gönderir.
    
    Yeni özellikler:
    - Asenkron (arka planda) güncelleme desteği
    - Optimizasyon için önbellek kullanımı 
    - Batch işleme
    - Daha detaylı izleme
    """
    # JSON formatında veri bekleniyor
    data = request.get_json()

    if not data:
        return jsonify(success=False, message="Geçersiz veri formatı"), 400

    # Frontend'den gelen yapı: {"barkod1": {"count": 5, "details": {...}}, "barkod2": {"count": 3, "details": {...}}, ...}
    barcode_counts_data = data.get('barcodeCounts')
    update_type = data.get('updateType')  # 'renew' veya 'add'
    background_mode = data.get('backgroundMode', False)  # Arka planda çalıştırma modu
    async_mode = data.get('asyncMode', True)  # Varsayılan olarak asenkron çalıştır

    if not barcode_counts_data or not update_type:
        return jsonify(success=False, message="Eksik veri: Barkodlar veya güncelleme tipi belirtilmemiş"), 400

    logger.info(f"Stok güncelleme isteği alındı. Tip: {update_type}, İşlenecek Barkod Sayısı: {len(barcode_counts_data)}")
    
    # İstek kaynağını logla
    client_info = {
        'ip': request.remote_addr,
        'user_agent': request.headers.get('User-Agent', 'Bilinmiyor'),
        'timestamp': datetime.now().isoformat()
    }
    logger.info(f"Stok güncelleme isteği bilgileri: {client_info}")
    
    if background_mode:
        # Arka planda çalıştır ve hemen cevap döndür
        thread = Thread(target=background_stock_update, args=(barcode_counts_data, update_type))
        thread.daemon = True
        thread.start()
        
        return jsonify(
            success=True,
            message=f"Stok güncelleme işlemi başlatıldı. {len(barcode_counts_data)} ürün arka planda işleniyor.",
            backgroundMode=True
        )
    else:
        # Senkron işle ve sonucu bekle
        start_time = time.time()
        success, result = process_stock_update_batch(barcode_counts_data, update_type, async_mode)
        execution_time = time.time() - start_time
        
        # İşlem süresini logla (performans analizi için)
        logger.info(f"Stok güncelleme işlemi toplam süresi: {execution_time:.2f} saniye, " 
                    f"ürün sayısı: {len(barcode_counts_data)}, "
                    f"ortalama: {(execution_time / len(barcode_counts_data) if barcode_counts_data else 0):.4f} saniye/ürün")
        
        if success:
            return jsonify(
                success=True,
                **result
            )
        else:
            return jsonify(
                success=False,
                **result
            ), 500

    # Veritabanı işlemleri ve Trendyol listesini hazırlama
    try:
        for barcode, item_data in barcode_counts_data.items():
            count = item_data.get('count', 0)

            # Ürünü barkoda göre bul
            # Tekrar DB sorgusu yapmak güncel bilgi sağlar
            product = Product.query.filter(db.func.lower(Product.barcode) == barcode.lower()).first()

            if not product:
                db_errors[barcode] = f"Ürün veritabanında bulunamadı: {barcode}"
                logger.warning(f"Veritabanında ürün bulunamadı, atlanıyor: Barkod {barcode}")
                continue

            # Mevcut stok miktarını al (None ise 0 say)
            current_stock = product.quantity if product.quantity is not None else 0

            # Güncelleme tipine göre yeni stok miktarını hesapla
            if update_type == 'renew':
                # Mevcut stoğu sıfırla ve yeni adeti ekle
                new_stock = count
                logger.debug(f"Stok yenileme: Barkod {barcode}, Eski Stok: {current_stock}, Yeni Stok: {new_stock}")
            elif update_type == 'add':
                # Mevcut stoğun üzerine ekle
                new_stock = current_stock + count
                logger.debug(f"Stok ekleme: Barkod {barcode}, Eski Stok: {current_stock}, Eklenecek: {count}, Yeni Stok: {new_stock}")
            else:
                # Geçersiz güncelleme tipi (frontend'de önlenmeli ama backend'de de kontrol iyi olur)
                db_errors[barcode] = f"Geçersiz güncelleme tipi: {update_type} (Barkod: {barcode})"
                logger.error(f"Geçersiz güncelleme tipi alındı: {update_type}")
                continue # Bu ürünü atla

            # Yeni stok miktarını Product modeline ata
            product.quantity = new_stock
            # Değişikliği session'a ekle
            db.session.add(product)

            # Trendyol güncellemesi için listeye ekle (Yeni stok miktarı ile)
            items_to_update_trendyol.append({"barcode": product.barcode, "quantity": new_stock}) # DB'den gelen barcode'u kullanmak daha güvenli olabilir

            updated_db_count += 1
            logger.debug(f"Veritabanı için hazırlandı ve Trendyol listesine eklendi: Barkod {barcode}, Yeni Stok: {new_stock}")

        # Tüm veritabanı değişikliklerini kaydet (Tek commit!)
        db.session.commit()
        logger.info(f"Veritabanı güncellemeleri başarıyla commit edildi. Güncellenen {updated_db_count} ürün.")

    except Exception as e:
        # Veritabanı işlemleri sırasında bir hata oluşursa rollback yap
        db.session.rollback()
        logger.error(f"Veritabanı işlemleri sırasında hata: {e}", exc_info=True)
        # Hata yanıtı döndür (Trendyol güncellemesi yapılmadı)
        return jsonify(
            success=False,
            message=f"Veritabanı güncellemesi sırasında bir hata oluştu: {str(e)}",
            errors=db_errors, # DB hatalarını da gönder
            trendyolUpdateErrors={} # Trendyol hatası oluşmadı
        ), 500 # Internal Server Error


    # --- Trendyol API'ye toplu stok güncellemesi gönderme ---
    trendyol_update_success = False
    trendyol_successful_count = 0
    trendyol_update_errors = {}

    if items_to_update_trendyol:
        logger.info(f"Trendyol'a toplu güncellenecek ürün sayısı: {len(items_to_update_trendyol)}")
        # Trendyol'a toplu güncelleme fonksiyonunu çağır (Tek çağrı!)
        trendyol_update_success, trendyol_successful_count, trendyol_update_errors = send_trendyol_stock_update_batch(items_to_update_trendyol)
    else:
         logger.info("Trendyol'a gönderilecek ürün listesi boş, Trendyol güncellemesi atlanıyor.")
         trendyol_update_success = True # Yapacak bir şey yoksa başarı sayabiliriz

    # Sonuç mesajını oluştur
    response_message = f"Veritabanında {updated_db_count} ürün güncellendi."

    if items_to_update_trendyol: # Trendyol güncellemesi denenmişse
        if trendyol_update_success:
             response_message += f" Trendyol'da {trendyol_successful_count} ürün stoğu topluca güncellendi."
             if trendyol_update_errors:
                 response_message += f" Ancak Trendyol yanıtında bazı hatalar bildirildi: {list(trendyol_update_errors.keys())}"
        else: # Genel Trendyol API çağrısı başarısız olduysa
            response_message += f" Trendyol stok güncellemesi başarısız oldu. Hata: {trendyol_update_errors.get('general', 'Bilinmeyen Trendyol hatası.')}"
            if len(trendyol_update_errors) > 1: # Genel hata mesajı dışında başka spesifik hatalar da varsa
                 response_message += f" Detaylı hatalar için loglara bakın veya hata listesini kontrol edin."

    # Başarılı yanıt döndür (Genel işlem başarılı sayılır eğer DB güncellendiyse ve Trendyol çağrısı yapıldıysa)
    # Trendyol'da kısmi hatalar olsa bile DB güncellendiği için success=True dönebiliriz.
    # Frontend bu hataları kullanıcıya gösterebilir.
    overall_success_status = updated_db_count > 0 # En az 1 ürün DB'de güncellendiyse başarılı say

    # Trendyol'da hiç ürün güncellenemedi ve genel bir Trendyol hatası varsa, genel success false olabilir.
    if not trendyol_update_success and items_to_update_trendyol:
         overall_success_status = False
         # Trendyol API bilgisi eksikse de false döndürelim
         if "Trendyol API bilgileri sunucuda eksik" in trendyol_update_errors.get("general", ""):
              overall_success_status = False


    return jsonify(
        success=overall_success_status,
        message=response_message,
        updatedDbCount=updated_db_count,
        errors=db_errors, # DB'de bulunamayan ürünler vb.
        trendyolUpdateErrors=trendyol_update_errors # Trendyol'da güncellenemeyenler veya API çağrısı hatası
    ), 200 # Başarılı yanıt kodu

# Not: trendyol_api.py dosyasını ve içindeki API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL bilgilerini doğru girdiğinden emin ol.
# Ayrıca models.py dosyasında Product modelinin 'barcode', 'quantity', 'product_main_id', 'color', 'size', 'images'
# kolonlarının tanımlı olduğundan emin ol. 'images' kolonu URL veya URL listesi tutmalı.