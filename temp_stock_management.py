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
