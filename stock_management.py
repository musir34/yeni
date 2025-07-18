import os
import json
import logging
import time
import base64
from datetime import datetime
import asyncio
import aiohttp
import requests
from threading import Thread
from functools import wraps
from sqlalchemy.orm import joinedload
from flask import Blueprint, render_template, request, jsonify, current_app
from sqlalchemy import func
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Modelleri ve veritabanı bağlantısını import et
from models import db, Product, RafUrun

# Trendyol API bilgilerini import et (yoksa None olarak ayarla)
try:
    from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL
except ImportError:
    API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL = None, None, None, "https://api.trendyol.com/sapigw/"

# --- Loglama Ayarları ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Blueprint ve Limiter ---
stock_management_bp = Blueprint('stock_management', __name__)
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])

# AÇIKLAMA: Trendyol'a tek seferde gönderilecek ürün sayısı.
BATCH_SIZE = 100

# --- Hata Loglama Fonksiyonu ---
def log_failed_items(failed_items, reason=""):
    """Hatalı ürünleri JSON formatında bir dosyaya kaydeder."""
    try:
        log_dir = "logs/failed_updates"
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = f"{log_dir}/failed_{timestamp}.json"
        with open(filepath, "w", encoding='utf-8') as f:
            json.dump({"timestamp": timestamp, "reason": reason, "items": failed_items}, f, indent=2, ensure_ascii=False)
        logger.info(f"{len(failed_items)} hatalı ürün loglandı: {filepath}")
    except Exception as e:
        logger.error(f"Hatalı ürünleri loglarken hata oluştu: {e}")

# --- Trendyol API Fonksiyonu (Asenkron) ---
async def send_trendyol_update_async(items_to_update):
    """Trendyol API'ye asenkron olarak ve paketler halinde stok güncellemesi gönderir."""
    if not all([API_KEY, API_SECRET, SUPPLIER_ID]):
        logger.error("Trendyol API bilgileri eksik. Güncelleme yapılamıyor.")
        return {"general_error": "Trendyol API bilgileri sunucuda eksik."}

    url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/products/price-and-inventory"
    credentials = f"{API_KEY}:{API_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/json",
        "User-Agent": f"GulluAyakkabiApp-V2/{SUPPLIER_ID}"
    }

    batches = [items_to_update[i:i + BATCH_SIZE] for i in range(0, len(items_to_update), BATCH_SIZE)]
    logger.info(f"Trendyol için {len(items_to_update)} ürün {len(batches)} pakete bölündü.")

    all_errors = {}

    async with aiohttp.ClientSession(headers=headers) as session:
        for i, batch in enumerate(batches):
            if i > 0:
                await asyncio.sleep(0.5) # Rate limit için her paket arasında bekle

            payload = {"items": batch}
            try:
                async with session.post(url, json=payload, timeout=60) as response:
                    if response.status not in [200, 202]:
                        response_text = await response.text()
                        logger.error(f"Trendyol Paket {i+1} Hatası | Status: {response.status} | Yanıt: {response_text[:200]}")
                        for item in batch:
                            all_errors[item['barcode']] = f"HTTP Hatası: {response.status}"
                        continue

                    response_data = await response.json()
                    failures = response_data.get('batchRequestItems', []) # Yeni API yanıt formatı
                    for fail in failures:
                        if fail.get('status') != 'SUCCESS':
                            barcode = fail.get('requestItem', {}).get('barcode', 'Bilinmeyen')
                            error_reason = fail.get('failureReasons', ['Bilinmeyen hata'])[0]
                            all_errors[barcode] = error_reason
                            logger.warning(f"Trendyol ürün hatası | Barkod: {barcode} | Hata: {error_reason}")

            except Exception as e:
                logger.error(f"Trendyol Paket {i+1} gönderiminde genel hata: {e}", exc_info=True)
                for item in batch:
                    all_errors[item['barcode']] = f"Genel Hata: {str(e)}"

    if all_errors:
        log_failed_items(list(all_errors.keys()), "Trendyol API Güncelleme Hatası")

    return all_errors

# --- ANA İŞLEM FONKSİYONU ---
def process_stock_updates(items, update_type, raf_kodu=None):
    if not items:
        return {"db_errors": {"genel": "İşlenecek ürün listesi boş."}}, []

    barcodes = [item['barcode'] for item in items]
    db_errors = {}
    items_for_trendyol = []

    try:
        products_in_db = Product.query.filter(func.lower(Product.barcode).in_([b.lower() for b in barcodes])).all()
        product_map = {p.barcode.lower(): p for p in products_in_db}

        for item in items:
            barcode = item['barcode']
            count = item['count']
            product = product_map.get(barcode.lower())

            if not product:
                db_errors[barcode] = "Ürün veritabanında bulunamadı."
                continue

            if update_type == 'add':
                product.quantity = (product.quantity or 0) + count

            elif update_type == 'renew':
                # Bu barkodun tüm raflardaki toplamını hesapla
                toplam_adet = db.session.query(func.sum(RafUrun.adet)).filter(
                    RafUrun.urun_barkodu == barcode
                ).scalar() or 0

                # Yeni gelen raf güncellemesini de ekle
                toplam_adet += count

                # Ama eğer bu rafta zaten varsa, eskisini çıkar yeni ekleneni koy
                mevcut_raf = RafUrun.query.filter_by(raf_kodu=raf_kodu, urun_barkodu=barcode).first()
                if mevcut_raf:
                    toplam_adet = toplam_adet - (mevcut_raf.adet or 0)

                product.quantity = toplam_adet

            else:
                db_errors[barcode] = f"Geçersiz güncelleme tipi: {update_type}"
                continue

            items_for_trendyol.append({"barcode": product.barcode, "quantity": product.quantity})

        db.session.commit()
        logger.info(f"{len(items_for_trendyol)} ürün güncellendi.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Veritabanı hatası: {e}", exc_info=True)
        return {"db_errors": {"kritik_hata": str(e)}}, []

    return db_errors, items_for_trendyol


# --- FLASK ENDPOINT'LERİ ---

@stock_management_bp.route('/stock-addition', methods=['GET'])
def stock_addition_page():
    """Stok ekleme arayüzünü (HTML) render eder."""
    return render_template('stock_addition.html')

@stock_management_bp.route('/api/get-product-details-by-barcode/<string:barcode>', methods=['GET'])
@limiter.limit("120/minute")
def get_product_details(barcode):
    """Verilen barkoda ait ürün detaylarını veritabanından çeker."""
    try:
        product = Product.query.filter(func.lower(Product.barcode) == barcode.lower()).first()
        if product:
            image_url = 'https://placehold.co/80x80'
            if product.images:
                try:
                    # '["url1", "url2"]' formatındaki JSON string'i listeye çevir
                    image_list = json.loads(product.images)
                    if image_list and isinstance(image_list, list):
                        image_url = image_list[0]
                except (json.JSONDecodeError, TypeError):
                    # Eğer JSON değilse veya format bozuksa, direkt string olarak al
                    image_url = product.images

            return jsonify(success=True, product={
                'barcode': product.barcode,
                'product_main_id': product.product_main_id,
                'color': product.color,
                'size': product.size,
                'quantity': product.quantity,
                'image_url': image_url
            })
        else:
            return jsonify(success=False, message="Ürün bulunamadı"), 404
    except Exception as e:
        logger.error(f"Ürün detayı alınırken hata (barkod: {barcode}): {e}", exc_info=True)
        return jsonify(success=False, message="Sunucu hatası oluştu."), 500

# DÜZENLENDİ: Bu artık ana ve tek stok güncelleme endpoint'imiz.
@stock_management_bp.route('/stock-addition', methods=['POST'])
@limiter.limit("60/minute")
def handle_stock_update_from_frontend():
    """
    Barkod okuyucu arayüzünden gelen ve paketlere bölünmüş stok güncelleme isteklerini işler.
    """
    data = request.get_json()
    if not data or 'items' not in data or 'updateType' not in data:
        return jsonify(success=False, message="Geçersiz istek formatı. 'items' ve 'updateType' gerekli."), 400

    items = data.get('items', [])
    update_type = data.get('updateType')

    # 1. RAF KODUNU AL VE KONTROL ET
    raf_kodu = data.get("raf_kodu")
    if not raf_kodu:
        return jsonify(success=False, message="Raf kodu zorunludur."), 400

    logger.info(f"Stok güncelleme paketi alındı. Ürün: {len(items)}, Tip: {update_type}, Raf: {raf_kodu}")

    # 2. ANA ÜRÜN STOKLARINI GÜNCELLE
    db_errors, items_for_trendyol = process_stock_updates(items, update_type, raf_kodu)

    # 3. RAFA AİT STOKLARI GÜNCELLE
    try:
        for item in items:
            barcode = item["barcode"]
            count = item["count"]

            # Ana ürün güncellemesinde zaten hata almış ürünleri atla
            if barcode in db_errors:
                logger.warning(f"Raf güncellemesi atlanıyor (önceki hata): Barkod {barcode}, Raf {raf_kodu}")
                continue

            mevcut_kayit = RafUrun.query.filter_by(raf_kodu=raf_kodu, urun_barkodu=barcode).first()

            if mevcut_kayit:
                if update_type == "add":
                    mevcut_kayit.adet = (mevcut_kayit.adet or 0) + count
                elif update_type == "renew":
                    mevcut_kayit.adet = count
            else:
                yeni_kayit = RafUrun(
                    raf_kodu=raf_kodu,
                    urun_barkodu=barcode,
                    adet=count
                )
                db.session.add(yeni_kayit)

        # Raf güncellemelerini veritabanına kaydet
        db.session.commit()
        logger.info(f"Raf ({raf_kodu}) stokları başarıyla güncellendi.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Raf stoklarını güncellerken kritik hata: {e}", exc_info=True)
        # Oluşan hatayı ön yüze gönderilecek genel hata listesine ekle
        db_errors['raf_guncelleme_hatasi'] = f"Raf stokları güncellenemedi: {str(e)}"

    updated_db_count = len(items) - len(db_errors)
    if updated_db_count < 0: updated_db_count = 0

    # 4. TRENDYOL'U GÜNCELLE (eğer DB'de güncellenen ürün varsa)
    trendyol_errors = {}
    if items_for_trendyol:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            trendyol_errors = loop.run_until_complete(send_trendyol_update_async(items_for_trendyol))
        finally:
            loop.close()

    # 5. SONUCU ÖN YÜZE BİLDİR
    total_errors = {**db_errors, **trendyol_errors}

    if not total_errors:
        return jsonify(success=True, message=f"{updated_db_count} ürün başarıyla güncellendi.")
    else:
        return jsonify(
            success=False,
            message=f"İşlem hatalarla tamamlandı. Lütfen detayları kontrol edin.",
            errors=total_errors
        ), 207