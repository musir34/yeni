import os
import json
import logging
import base64
from datetime import datetime
import asyncio
import aiohttp
from sqlalchemy.orm import joinedload
from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import func
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Modeller
from models import db, Product, RafUrun, CentralStock

# Trendyol API bilgileri
try:
    from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL
except ImportError:
    API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL = None, None, None, "https://api.trendyol.com/sapigw/"

# --- Loglama ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Blueprint ve Rate Limit ---
stock_management_bp = Blueprint('stock_management', __name__)
limiter = Limiter(key_func=get_remote_address,
                  default_limits=["200 per day", "50 per hour"])

# Trendyol’a tek seferde gönderilecek ürün sayısı
BATCH_SIZE = 100


# -------------------------------
# Yardımcı: Hatalı barkodları dosyaya yaz
# -------------------------------
def log_failed_items(failed_items, reason=""):
    try:
        log_dir = "logs/failed_updates"
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = f"{log_dir}/failed_{timestamp}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"timestamp": timestamp,
                       "reason": reason,
                       "items": failed_items}, f, indent=2, ensure_ascii=False)
        logger.info("%s hatalı barkod loglandı: %s", len(failed_items), filepath)
    except Exception as e:
        logger.error("Hatalı ürünleri loglarken hata: %s", e)


# -------------------------------
# Trendyol STOCK-ONLY push (PUT stock-quantity)
# -------------------------------
async def send_trendyol_stock_only_async(items):
    """
    items: [{"barcode": "...", "quantity": int}]
    Trendyol stock-quantity endpoint (sadece stok).
    """
    if not all([API_KEY, API_SECRET, SUPPLIER_ID]):
        logger.error("Trendyol API bilgileri eksik. Stok push iptal.")
        return {"general_error": "API creds missing"}

    # Base URL sapigw; sonuna suppliers/... eklenir
    url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/products/stock-quantity"
    auth = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
        "User-Agent": f"GulluAyakkabi-StockSync/{SUPPLIER_ID}"
    }

    # Temizle ve negatifleri 0’a sabitle
    cleaned = []
    for it in items:
        bc = (it.get("barcode") or "").strip()
        if not bc:
            continue
        try:
            q = int(it.get("quantity", 0))
        except (TypeError, ValueError):
            q = 0
        if q < 0:
            q = 0
        cleaned.append({"barcode": bc, "quantity": q})

    if not cleaned:
        logger.info("Push edilecek stok yok.")
        return {}

    batches = [cleaned[i:i + BATCH_SIZE] for i in range(0, len(cleaned), BATCH_SIZE)]
    errors = {}

    async with aiohttp.ClientSession(headers=headers) as session:
        for idx, batch in enumerate(batches, start=1):
            # Rate limit nazikliği
            if idx > 1:
                await asyncio.sleep(0.5)
            payload = {"items": batch}
            try:
                async with session.put(url, json=payload, timeout=60) as resp:
                    text = await resp.text()
                    logger.info("[STOCK %d/%d] %s %s", idx, len(batches), resp.status, text[:200])
                    if resp.status not in (200, 202):
                        for it in batch:
                            errors[it["barcode"]] = f"http {resp.status}"
            except Exception as e:
                logger.error("Batch %d exception: %s", idx, e, exc_info=True)
                for it in batch:
                    errors[it["barcode"]] = f"exc {str(e)[:120]}"

    if errors:
        log_failed_items(list(errors.keys()), "stock-quantity errors")
    return errors


# Fire-and-forget helper (Flask senkron bağlamda async tetikleme)
def _spawn_async(coro):
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        asyncio.run(coro)


# -------------------------------
# HTML Sayfası
# -------------------------------
@stock_management_bp.route('/stock-addition', methods=['GET'])
def stock_addition_page():
    return render_template('stock_addition.html')


# -------------------------------
# Barkod detay API
# -------------------------------
@stock_management_bp.route('/api/get-product-details-by-barcode/<string:barcode>', methods=['GET'])
@limiter.limit("120/minute")
def get_product_details(barcode):
    try:
        product = Product.query.filter(func.lower(Product.barcode) == barcode.lower()).first()
        cs = CentralStock.query.get(barcode)

        if not product:
            return jsonify(success=False, message="Ürün bulunamadı"), 404

        image_url = 'https://placehold.co/80x80'
        if product.images:
            try:
                image_list = json.loads(product.images)
                if image_list and isinstance(image_list, list):
                    image_url = image_list[0]
            except (json.JSONDecodeError, TypeError):
                image_url = product.images

        return jsonify(success=True, product={
            "barcode": product.barcode,
            "product_main_id": product.product_main_id,
            "color": product.color,
            "size": product.size,
            "quantity": (cs.qty if cs else 0),
            "image_url": image_url
        })
    except Exception as e:
        logger.error("Ürün detayı alınırken hata (barkod: %s): %s", barcode, e, exc_info=True)
        return jsonify(success=False, message="Sunucu hatası."), 500


# -------------------------------
# Stok ekleme/güncelleme (ANA ENDPOINT)
# -------------------------------
@stock_management_bp.route('/stock-addition', methods=['POST'])
@limiter.limit("60/minute")
def handle_stock_update_from_frontend():
    """
    - 'add': Seçilen rafa ürün ekler, CentralStock'u artırır.
    - 'renew': Seçilen raftaki TÜM ürünleri siler, CentralStock'u düşürür,
               ardından SADECE yeni gelen ürünleri rafa ekler ve CentralStock'u artırır.
               (Rafı sıfırdan kurar)
    - ❌ Trendyol'a herhangi bir push YAPMAZ.
    """
    data = request.get_json(silent=True) or {}
    items = data.get('items', [])
    update_type = data.get('updateType')
    raf_kodu = (data.get('raf_kodu') or '').strip()

    if not raf_kodu:
        return jsonify(success=False, message="Raf kodu zorunludur."), 400
    if update_type not in ('add', 'renew'):
        return jsonify(success=False, message="updateType 'add' veya 'renew' olmalı."), 400
    if not items and update_type == 'add': # 'renew' boş liste ile rafı temizleyebilir
         return jsonify(success=False, message="İşlenecek ürün yok."), 400

    errors = {}
    results = []

    try:
        with db.session.begin():  # Tek transaction
            # Gelen ürünlerin barkodlarını ve Product tablosundaki varlıklarını kontrol et
            barcode_set = [it.get('barcode') for it in items if it.get('barcode')]
            valid_products = {}
            if barcode_set:
                existing = Product.query.filter(func.lower(Product.barcode).in_([b.lower() for b in barcode_set])).all()
                valid_products = {p.barcode.lower(): True for p in existing}

            # --- 'RENEW' (YENİLE) MANTIĞI ---
            if update_type == 'renew':
                logger.info(f"'{raf_kodu}' rafı için YENİLEME işlemi başlatıldı.")
                # 1. Bu raftaki TÜM mevcut ürünleri bul
                raftaki_eski_urunler = RafUrun.query.filter_by(raf_kodu=raf_kodu).all()

                # 2. Bu ürünlerin stoklarını merkezi stoktan düş
                for eski_urun in raftaki_eski_urunler:
                    cs_eski = CentralStock.query.get(eski_urun.urun_barkodu)
                    if cs_eski and cs_eski.qty is not None:
                        cs_eski.qty = max(0, cs_eski.qty - eski_urun.adet)
                
                # 3. Raftaki tüm eski kayıtları tek seferde sil
                if raftaki_eski_urunler:
                    RafUrun.query.filter_by(raf_kodu=raf_kodu).delete()
                    logger.info(f"'{raf_kodu}' rafından {len(raftaki_eski_urunler)} kalem ürün silindi.")

            # --- YENİ ÜRÜNLERİ İŞLEME (HEM 'ADD' HEM DE 'RENEW' İÇİN) ---
            for it in items:
                barcode = (it.get('barcode') or '').strip()
                try:
                    count = int(it.get('count', 0))
                except (TypeError, ValueError):
                    count = 0

                if not barcode or count < 0:
                    errors[barcode or 'EMPTY'] = "Geçersiz barkod/adet"
                    continue
                if not valid_products.get(barcode.lower()):
                    errors[barcode] = "Ürün veritabanında yok"
                    continue
                
                # CentralStock kaydını bul veya oluştur
                cs = CentralStock.query.get(barcode)
                if not cs:
                    cs = CentralStock(barcode=barcode, qty=0)
                    db.session.add(cs)
                
                # RafUrun kaydını bul veya oluştur
                rec = RafUrun.query.filter_by(raf_kodu=raf_kodu, urun_barkodu=barcode).first()
                
                # 'add' ise adedi ekle, 'renew' ise zaten silindiği için sıfırdan oluştur
                if rec:
                    rec.adet = (rec.adet or 0) + count
                else:
                    rec = RafUrun(raf_kodu=raf_kodu, urun_barkodu=barcode, adet=count)
                    db.session.add(rec)
                
                # Merkezi stoğu GÜNCEL adede göre artır
                cs.qty = (cs.qty or 0) + count

                results.append({"barcode": barcode, "central_qty": int(cs.qty or 0)})

        # --- SONUÇLARI DÖNDÜR ---
        if errors:
            return jsonify(success=False,
                           message="Bazı kalemler işlenemedi.",
                           errors=errors,
                           results=results), 207

        message = f"'{raf_kodu}' rafındaki {len(results)} ürün başarıyla güncellendi."
        if update_type == 'renew' and not items:
            message = f"'{raf_kodu}' rafı başarıyla boşaltıldı."

        return jsonify(success=True,
                       message=message,
                       results=results)

    except Exception as e:
        logger.error("Stok ekleme/güncelleme hatası: %s", e, exc_info=True)
        return jsonify(success=False, message=f"Sunucu hatası: {str(e)}"), 500