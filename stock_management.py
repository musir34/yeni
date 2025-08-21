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
    - Seçilen raf için RafUrun'u (add/renew) günceller,
    - CentralStock.qty'yi günceller,
    - ❌ Trendyol'a herhangi bir push YAPMAZ (bilerek kapalı).
    """
    data = request.get_json(silent=True) or {}
    items = data.get('items', [])
    update_type = data.get('updateType')
    raf_kodu = (data.get('raf_kodu') or '').strip()

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
            # Ürünleri doğrula
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

                # CentralStock hazırla
                cs = CentralStock.query.get(barcode)
                if not cs:
                    cs = CentralStock(barcode=barcode, qty=0)
                    db.session.add(cs)

                # Raf kaydı
                rec = RafUrun.query.filter_by(raf_kodu=raf_kodu, urun_barkodu=barcode).first()

                if update_type == 'add':
                    # Raf'a ekle
                    if rec:
                        rec.adet = (rec.adet or 0) + count
                    else:
                        db.session.add(RafUrun(raf_kodu=raf_kodu,
                                               urun_barkodu=barcode,
                                               adet=count))
                    # Merkeze ekle
                    cs.qty = (cs.qty or 0) + count

                elif update_type == 'renew':
                    # Bu rafın eski değeri
                    eski = rec.adet if rec else 0
                    # Barkodun tüm raflardaki toplamı
                    toplam = db.session.query(func.coalesce(func.sum(RafUrun.adet), 0))\
                                       .filter(RafUrun.urun_barkodu == barcode).scalar()
                    # Yeni toplam
                    yeni_toplam = max(0, int((toplam or 0) - (eski or 0) + count))
                    # Rafı yenile
                    if rec:
                        rec.adet = count
                    else:
                        db.session.add(RafUrun(raf_kodu=raf_kodu,
                                               urun_barkodu=barcode,
                                               adet=count))
                    # Merkezi stoğu sabitle
                    cs.qty = yeni_toplam

                results.append({"barcode": barcode, "central_qty": int(cs.qty or 0)})

        # ❌ Trendyol push BLOKU KALDIRILDI / DEVRE DIŞI
        # (Önceden burada _spawn_async(send_trendyol_stock_only_async(...)) vardı.)

        if errors:
            return jsonify(success=False,
                           message="Bazı kalemler işlenemedi. (Trendyol push devre dışı)",
                           errors=errors,
                           results=results), 207

        return jsonify(success=True,
                       message=f"{len(results)} ürün güncellendi. (Trendyol push devre dışı)",
                       results=results)

    except Exception as e:
        logger.error("Stok ekleme/güncelleme hatası: %s", e, exc_info=True)
        return jsonify(success=False, message=f"Sunucu hatası: {str(e)}"), 500
