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
from models import db, Product, RafUrun, CentralStock

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

    barcodes = [it['barcode'] for it in items]
    db_errors = {}
    items_for_trendyol = {}

    try:
        # Ürün var mı kontrol (sadece doğrulama için)
        products_in_db = Product.query.filter(func.lower(Product.barcode).in_([b.lower() for b in barcodes])).all()
        product_map = {p.barcode.lower(): p for p in products_in_db}

        for it in items:
            barcode = it['barcode']
            count = int(it['count'])
            if not product_map.get(barcode.lower()):
                db_errors[barcode] = "Ürün veritabanında bulunamadı."
                continue

            # CentralStock kaydını bul/oluştur
            cs = CentralStock.query.get(barcode)
            if not cs:
                cs = CentralStock(barcode=barcode, qty=0)
                db.session.add(cs)

            if update_type == 'add':
                # Merkez stoğu artır (Raf güncellemesi aşağıda yapılacak)
                cs.qty = (cs.qty or 0) + count

            elif update_type == 'renew':
                # Bu barkodun raf toplamını (yeni adetle) hesapla
                toplam_adet = db.session.query(func.sum(RafUrun.adet)).filter(
                    RafUrun.urun_barkodu == barcode
                ).scalar() or 0

                # Bu raftaki eski değeri çıkarıp yeni geleni ekle
                mevcut_raf = RafUrun.query.filter_by(raf_kodu=raf_kodu, urun_barkodu=barcode).first()
                eski = mevcut_raf.adet if mevcut_raf else 0
                yeni_toplam = (toplam_adet - (eski or 0)) + count

                cs.qty = max(0, int(yeni_toplam))

            else:
                db_errors[barcode] = f"Geçersiz güncelleme tipi: {update_type}"
                continue

            items_for_trendyol[barcode] = cs.qty  # Trendyol’a merkezden gidecek

        db.session.commit()
        logger.info(f"{len(items_for_trendyol)} barkod için CentralStock güncellendi.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Veritabanı hatası: {e}", exc_info=True)
        return {"db_errors": {"kritik_hata": str(e)}}, []

    # DÖNÜŞ: Trendyol için list hale çevir
    return db_errors, [{"barcode": b, "quantity": q} for b, q in items_for_trendyol.items()]


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
                'quantity': (cs.qty if cs else 0),
                'image_url': image_url
            })
        else:
            return jsonify(success=False, message="Ürün bulunamadı"), 404
    except Exception as e:
        logger.error(f"Ürün detayı alınırken hata (barkod: {barcode}): {e}", exc_info=True)
        return jsonify(success=False, message="Sunucu hatası oluştu."), 500

# DÜZENLENDİ:  artık ana ve tek stok güncelleme endpoint'imiz.
@stock_management_bp.route('/stock-addition', methods=['POST'])
@limiter.limit("60/minute")
def handle_stock_update_from_frontend():
    """
    Barkod okuyucudan gelen stokları:
      - Seçilen raf için RafUrun'a (add/renew) yazar,
      - CentralStock.qty'yi günceller,
    Trendyol'a hiçbir gönderim yapmaz.
    """
    data = request.get_json()
    if not data or 'items' not in data or 'updateType' not in data:
        return jsonify(success=False, message="Geçersiz istek formatı. 'items' ve 'updateType' gerekli."), 400

    items = data.get('items', [])
    update_type = data.get('updateType')
    raf_kodu = data.get("raf_kodu", "").strip()

    if not raf_kodu:
        return jsonify(success=False, message="Raf kodu zorunludur."), 400
    if update_type not in ('add', 'renew'):
        return jsonify(success=False, message="updateType 'add' veya 'renew' olmalı."), 400
    if not items:
        return jsonify(success=False, message="İşlenecek ürün yok."), 400

    errors = {}
    results = []

    try:
        with db.session.begin():  # tek transaction
            # Ürünleri doğrula (var mı yok mu)
            barcode_set = [it.get('barcode') for it in items if it.get('barcode')]
            existing = Product.query.filter(func.lower(Product.barcode).in_([b.lower() for b in barcode_set])).all()
            exist_map = {p.barcode.lower(): True for p in existing}

            for it in items:
                barcode = (it.get('barcode') or '').strip()
                try:
                    count = int(it.get('count', 0))
                except (TypeError, ValueError):
                    count = 0

                if not barcode or count < 0:
                    errors[barcode or 'EMPTY'] = "Geçersiz barkod/adet"
                    continue
                if not exist_map.get(barcode.lower()):
                    errors[barcode] = "Ürün veritabanında yok"
                    continue

                # CentralStock kaydını hazırla
                cs = CentralStock.query.get(barcode)
                if not cs:
                    cs = CentralStock(barcode=barcode, qty=0)
                    db.session.add(cs)

                # Raf kaydını çek
                rec = RafUrun.query.filter_by(raf_kodu=raf_kodu, urun_barkodu=barcode).first()

                if update_type == 'add':
                    # 1) Raf'a ekle
                    if rec:
                        rec.adet = (rec.adet or 0) + count
                    else:
                        db.session.add(RafUrun(raf_kodu=raf_kodu, urun_barkodu=barcode, adet=count))
                    # 2) Merkeze ekle
                    cs.qty = (cs.qty or 0) + count

                elif update_type == 'renew':
                    # 1) Raf'ta bu barkodun eski değerini öğren
                    eski = rec.adet if rec else 0
                    # 2) Bu barkodun raflardaki toplamını hesapla (şu anki)
                    toplam = db.session.query(func.coalesce(func.sum(RafUrun.adet), 0))\
                                       .filter(RafUrun.urun_barkodu == barcode).scalar()
                    # 3) Yeni toplam = mevcut toplam - bu rafın eski değeri + yeni değer
                    yeni_toplam = max(0, int((toplam or 0) - (eski or 0) + count))
                    # 4) Raf'ı yenile
                    if rec:
                        rec.adet = count
                    else:
                        db.session.add(RafUrun(raf_kodu=raf_kodu, urun_barkodu=barcode, adet=count))
                    # 5) Merkezi stoğu yeni toplama sabitle
                    cs.qty = yeni_toplam

                results.append({"barcode": barcode, "central_qty": int(cs.qty or 0)})

        # Transaction başarılı
        if errors:
            return jsonify(success=False,
                           message="Bazı kalemler işlenemedi.",
                           errors=errors,
                           results=results), 207
        return jsonify(success=True,
                       message=f"{len(results)} ürün güncellendi.",
                       results=results)
    except Exception as e:
        logger.error(f"Stok ekleme/güncelleme hatası: {e}", exc_info=True)
        return jsonify(success=False, message=f"Sunucu hatası: {str(e)}"), 500