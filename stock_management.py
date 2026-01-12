import os
import json
import logging
from datetime import datetime
import hashlib
import time
from sqlalchemy.orm import joinedload
from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import func
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Modeller
from models import db, Product, RafUrun, CentralStock

# --- Loglama ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# -------------------------------
# CentralStock Senkronizasyon Fonksiyonları
# -------------------------------
def sync_central_stock(barcode: str) -> int:
    """
    Tek bir barkod için CentralStock'u raflardaki toplamla senkronize eder.
    
    Args:
        barcode: Senkronize edilecek ürün barkodu
        
    Returns:
        int: Yeni stok miktarı
    """
    # 🔧 Barkodu küçük harfe normalize et (case-insensitive)
    barcode = barcode.lower().strip()
    
    # Raflardaki toplam miktarı hesapla (case-insensitive)
    raf_toplam = db.session.query(
        func.coalesce(func.sum(RafUrun.adet), 0)
    ).filter(
        func.lower(RafUrun.urun_barkodu) == barcode,
        RafUrun.adet > 0
    ).scalar()
    
    raf_toplam = int(raf_toplam or 0)
    
    # CentralStock kaydını bul veya oluştur (case-insensitive arama)
    cs = CentralStock.query.filter(func.lower(CentralStock.barcode) == barcode).first()
    
    if cs:
        if cs.qty != raf_toplam:
            logger.info(f"🔄 CentralStock senkronize: {barcode} | {cs.qty} → {raf_toplam}")
            cs.qty = raf_toplam
            cs.updated_at = datetime.utcnow()
    else:
        if raf_toplam > 0:
            # Yeni kayıtta küçük harfli barkod kullan
            cs = CentralStock(barcode=barcode, qty=raf_toplam)
            db.session.add(cs)
            logger.info(f"➕ CentralStock oluşturuldu: {barcode} = {raf_toplam}")
    
    return raf_toplam


def sync_multiple_barcodes(barcodes: list) -> dict:
    """
    Birden fazla barkod için CentralStock'u senkronize eder.
    """
    results = {}
    for barcode in barcodes:
        results[barcode] = sync_central_stock(barcode)
    return results


# --- Çift İşlem Önleme Cache ---
# {request_hash: timestamp} - Son 60 saniyedeki istekleri tutar
_request_cache = {}
_CACHE_TIMEOUT = 60  # 60 saniye

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
        barcode_lower = barcode.lower().strip()
        product = Product.query.filter(func.lower(Product.barcode) == barcode_lower).first()
        cs = CentralStock.query.filter(func.lower(CentralStock.barcode) == barcode_lower).first()

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
    
    # 🔧 "=" ve "*" karakterlerini "-" ile değiştir (telefonlardan kaynaklanıyor)
    raf_kodu = raf_kodu.replace('=', '-').replace('*', '-')
    
    # 🛡️ Çift işlem kontrolü - Aynı istek 60 saniye içinde tekrar gelirse engelle
    request_data = f"{raf_kodu}|{update_type}|{len(items)}"
    request_hash = hashlib.md5(request_data.encode()).hexdigest()
    current_time = time.time()
    
    # Eski cache'leri temizle (60 saniyeden eski)
    global _request_cache
    _request_cache = {k: v for k, v in _request_cache.items() if current_time - v < _CACHE_TIMEOUT}
    
    # Bu istek daha önce yapıldı mı kontrol et
    if request_hash in _request_cache:
        time_diff = current_time - _request_cache[request_hash]
        logger.warning(f"🚫 ÇIFT İŞLEM ENGELLENDİ! Raf={raf_kodu}, Mod={update_type}, Ürün={len(items)}, Son işlemden {time_diff:.2f} saniye geçti")
        return jsonify(success=True, message="Bu işlem zaten yapıldı (önbellekten döndü)", cached=True), 200
    
    # İsteği cache'e kaydet
    _request_cache[request_hash] = current_time
    
    logger.info(f"🔹 Stok ekleme isteği alındı: Raf={raf_kodu}, Mod={update_type}, Ürün Sayısı={len(items)}")

    if not raf_kodu:
        logger.error("❌ Raf kodu boş geldi!")
        return jsonify(success=False, message="Raf kodu zorunludur."), 400
    if update_type not in ('add', 'renew'):
        logger.error(f"❌ Geçersiz işlem tipi: {update_type}")
        return jsonify(success=False, message="updateType 'add' veya 'renew' olmalı."), 400
    if not items and update_type == 'add': # 'renew' boş liste ile rafı temizleyebilir
         logger.warning(f"⚠️ İşlenecek ürün yok (mod: {update_type})")
         return jsonify(success=False, message="İşlenecek ürün yok."), 400

    errors = {}
    results = []
    affected_barcodes = set()  # 🔥 Etkilenen barkodları takip et

    try:
        with db.session.begin():  # Tek transaction
            logger.info(f"📦 Transaction başlatıldı - Raf: {raf_kodu}")
            
            # Gelen ürünlerin barkodlarını ve Product tablosundaki varlıklarını kontrol et
            barcode_set = [it.get('barcode') for it in items if it.get('barcode')]
            valid_products = {}
            if barcode_set:
                logger.info(f"🔍 {len(barcode_set)} barkod için Product tablosunda kontrol yapılıyor...")
                existing = Product.query.filter(func.lower(Product.barcode).in_([b.lower() for b in barcode_set])).all()
                valid_products = {p.barcode.lower(): True for p in existing}
                logger.info(f"✅ Product tablosunda {len(valid_products)} ürün bulundu.")
                
                # Bulunamayan ürünleri logla
                missing_barcodes = [bc for bc in barcode_set if bc.lower() not in valid_products]
                if missing_barcodes:
                    logger.warning(f"⚠️ Product tablosunda BULUNAMAYAN barkodlar ({len(missing_barcodes)}): {', '.join(missing_barcodes[:10])}{'...' if len(missing_barcodes) > 10 else ''}")

            # --- 'RENEW' (YENİLE) MANTIĞI ---
            if update_type == 'renew':
                logger.info(f"🔄 '{raf_kodu}' rafı için YENİLEME işlemi başlatıldı.")
                # 1. Bu raftaki TÜM mevcut ürünleri bul
                raftaki_eski_urunler = RafUrun.query.filter_by(raf_kodu=raf_kodu).all()
                logger.info(f"📋 Rafta mevcut {len(raftaki_eski_urunler)} kayıt bulundu.")

                # 2. Eski ürünleri affected_barcodes'a ekle (senkronizasyon için)
                for eski_urun in raftaki_eski_urunler:
                    affected_barcodes.add(eski_urun.urun_barkodu)
                
                # 3. Raftaki tüm eski kayıtları tek seferde sil
                if raftaki_eski_urunler:
                    silinen_sayisi = RafUrun.query.filter_by(raf_kodu=raf_kodu).delete()
                    logger.info(f"🗑️ '{raf_kodu}' rafından {silinen_sayisi} kayıt silindi.")

            # --- YENİ ÜRÜNLERİ İŞLEME (HEM 'ADD' HEM DE 'RENEW' İÇİN) ---
            logger.info(f"➕ '{raf_kodu}' rafına eklenecek ürün sayısı: {len(items)}")
            for it in items:
                barcode = (it.get('barcode') or '').strip().lower()  # 🔧 Küçük harfe normalize et
                try:
                    count = int(it.get('count', 0))
                except (TypeError, ValueError):
                    count = 0

                if not barcode or count < 0:
                    logger.warning(f"Geçersiz barkod veya adet: barkod={barcode}, count={count}")
                    errors[barcode or 'EMPTY'] = "Geçersiz barkod/adet"
                    continue
                if not valid_products.get(barcode.lower()):
                    logger.warning(f"Ürün veritabanında bulunamadı: {barcode}")
                    errors[barcode] = "Ürün veritabanında yok"
                    continue
                
                # RafUrun kaydını bul veya oluştur (case-insensitive arama)
                rec = RafUrun.query.filter(
                    RafUrun.raf_kodu == raf_kodu,
                    func.lower(RafUrun.urun_barkodu) == barcode
                ).first()
                
                # 'add' ise adedi ekle, 'renew' ise zaten silindiği için sıfırdan oluştur
                if rec:
                    eski_adet = rec.adet
                    rec.adet = (rec.adet or 0) + count
                    logger.info(f"Raf: {raf_kodu}, Barkod: {barcode}, Eski: {eski_adet}, Yeni: {rec.adet}")
                else:
                    rec = RafUrun(raf_kodu=raf_kodu, urun_barkodu=barcode, adet=count)
                    db.session.add(rec)
                    logger.info(f"Raf: {raf_kodu}, Barkod: {barcode}, İlk kez eklendi, Adet: {count}")
                
                # Etkilenen barkodları takip et
                affected_barcodes.add(barcode)
                
                results.append({
                    "barcode": barcode,
                    "count": count,
                    "raf_kodu": raf_kodu
                })

            # 🔥 TÜM ETKİLENEN BARKODLAR İÇİN CENTRALSTOCK'U YENİDEN HESAPLA
            logger.info(f"📊 {len(affected_barcodes)} barkod için CentralStock senkronize ediliyor...")
            for barcode in affected_barcodes:
                new_qty = sync_central_stock(barcode)
                # results listesinde bu barkodu güncelle
                for r in results:
                    if r["barcode"] == barcode:
                        r["central_qty"] = new_qty
                        break
            
            # Transaction başarıyla tamamlandı
            logger.info(f"✅ Transaction başarıyla tamamlandı - {len(results)} ürün işlendi, {len(errors)} hata.")

        # --- SONUÇLARI DÖNDÜR ---
        if errors:
            logger.warning(f"⚠️ '{raf_kodu}' rafı güncellenirken bazı ürünler eklenemedi:")
            for err_barcode, err_msg in list(errors.items())[:10]:
                logger.warning(f"   - {err_barcode}: {err_msg}")
            if len(errors) > 10:
                logger.warning(f"   ... ve {len(errors) - 10} hata daha.")
            
            return jsonify(success=False,
                           message="Bazı kalemler işlenemedi.",
                           errors=errors,
                           results=results), 207

        message = f"'{raf_kodu}' rafındaki {len(results)} ürün başarıyla güncellendi."
        if update_type == 'renew' and not items:
            message = f"'{raf_kodu}' rafı başarıyla boşaltıldı."
        
        logger.info(f"🎉 '{raf_kodu}' rafı başarıyla güncellendi. Toplam {len(results)} ürün işlendi. (Mod: {update_type})")

        return jsonify(success=True,
                       message=message,
                       results=results)

    except Exception as e:
        logger.error(f"❌ HATA - Raf: {raf_kodu}, Mod: {update_type}, Ürün Sayısı: {len(items)}")
        logger.error("Stok ekleme/güncelleme hatası: %s", e, exc_info=True)
        return jsonify(success=False, message=f"Sunucu hatası: {str(e)}"), 500
