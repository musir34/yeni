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
from user_logs import log_user_action
from barcode_alias_helper import normalize_barcode

# --- Loglama ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# -------------------------------
# CentralStock Senkronizasyon Fonksiyonları
# -------------------------------
def sync_central_stock(barcode: str, commit: bool = True) -> int:
    """
    Tek bir barkod için CentralStock'u raflardaki toplamla senkronize eder.

    Args:
        barcode: Senkronize edilecek ürün barkodu
        commit: True ise değişiklikleri commit eder (varsayılan).
                Bir transaction içinden çağrılıyorsa False geçin.

    Returns:
        int: Yeni stok miktarı
    """
    # Raflardaki toplam miktarı hesapla
    raf_toplam = db.session.query(
        func.coalesce(func.sum(RafUrun.adet), 0)
    ).filter(
        RafUrun.urun_barkodu == barcode,
        RafUrun.adet > 0
    ).scalar()
    
    raf_toplam = int(raf_toplam or 0)
    
    # CentralStock kaydını bul veya oluştur
    cs = CentralStock.query.get(barcode)
    
    if cs:
        if cs.qty != raf_toplam:
            logger.info(f"🔄 CentralStock senkronize: {barcode} | {cs.qty} → {raf_toplam}")
            cs.qty = raf_toplam
            cs.updated_at = datetime.utcnow()
    else:
        if raf_toplam > 0:
            cs = CentralStock(barcode=barcode, qty=raf_toplam)
            db.session.add(cs)
            logger.info(f"➕ CentralStock oluşturuldu: {barcode} = {raf_toplam}")

    # Product.quantity'yi de senkronize et
    product = Product.query.get(barcode)
    if product and product.quantity != raf_toplam:
        product.quantity = raf_toplam
        logger.info(f"🔄 Product.quantity senkronize: {barcode} | → {raf_toplam}")

    if commit:
        db.session.commit()
    return raf_toplam


def sync_multiple_barcodes(barcodes: list, commit: bool = True) -> dict:
    """
    Birden fazla barkod için CentralStock'u senkronize eder.
    """
    results = {}
    for barcode in barcodes:
        results[barcode] = sync_central_stock(barcode, commit=False)
    if commit:
        db.session.commit()
    return results


# -------------------------------
# Stok Tutarlılık Kontrolü
# -------------------------------
def verify_stock_integrity(auto_fix: bool = False) -> dict:
    """
    CentralStock ile RafUrun toplamlarını karşılaştırır, tutarsızlıkları tespit eder.

    Args:
        auto_fix: True ise tutarsızlıkları otomatik düzeltir

    Returns:
        Tutarlılık raporu
    """
    report = {
        'checked_at': datetime.utcnow().isoformat(),
        'auto_fix': auto_fix,
        'issues': [],
        'cleaned_zero_records': 0,
        'orphaned_central_stock': 0,
        'mismatched_quantities': 0,
        'missing_central_stock': 0,
        'total_checked': 0,
        'all_ok': True
    }

    # 1. adet<=0 olan RafUrun kayıtlarını temizle
    zero_count = RafUrun.query.filter(RafUrun.adet <= 0).count()
    if zero_count > 0:
        report['cleaned_zero_records'] = zero_count
        report['all_ok'] = False
        if auto_fix:
            RafUrun.query.filter(RafUrun.adet <= 0).delete()
            report['issues'].append(f"{zero_count} adet<=0 RafUrun kaydı silindi")
        else:
            report['issues'].append(f"{zero_count} adet<=0 RafUrun kaydı bulundu")

    # 2. RafUrun'dan barkod toplamlarını hesapla
    raf_totals = db.session.query(
        RafUrun.urun_barkodu,
        func.sum(RafUrun.adet).label('total')
    ).filter(
        RafUrun.adet > 0
    ).group_by(
        RafUrun.urun_barkodu
    ).all()

    raf_dict = {r.urun_barkodu: int(r.total) for r in raf_totals}

    # 3. CentralStock ile karşılaştır
    all_cs = CentralStock.query.all()
    report['total_checked'] = len(all_cs)

    for cs in all_cs:
        raf_toplam = raf_dict.pop(cs.barcode, 0)

        if cs.qty != raf_toplam:
            report['mismatched_quantities'] += 1
            report['all_ok'] = False
            report['issues'].append(
                f"TUTARSIZ: {cs.barcode} — CentralStock={cs.qty}, Raf toplam={raf_toplam}"
            )
            if auto_fix:
                cs.qty = raf_toplam
                cs.updated_at = datetime.utcnow()

    # 4. RafUrun'da var ama CentralStock'ta yok
    for barcode, total in raf_dict.items():
        if total > 0:
            report['missing_central_stock'] += 1
            report['all_ok'] = False
            report['issues'].append(
                f"KAYIP: {barcode} — Rafta {total} adet var ama CentralStock kaydı yok"
            )
            if auto_fix:
                db.session.add(CentralStock(barcode=barcode, qty=total))

    # 5. Product.quantity'yi CentralStock ile eşitle
    product_synced = 0
    if auto_fix:
        all_cs_fresh = CentralStock.query.all()
        for cs in all_cs_fresh:
            product = Product.query.get(cs.barcode)
            if product and product.quantity != cs.qty:
                product.quantity = cs.qty
                product_synced += 1
    report['product_quantity_synced'] = product_synced

    if auto_fix and (not report['all_ok'] or product_synced > 0):
        db.session.commit()
        logger.info(f"[INTEGRITY] Otomatik düzeltme tamamlandı: "
                     f"{report['mismatched_quantities']} tutarsız, "
                     f"{report['missing_central_stock']} kayıp, "
                     f"{report['cleaned_zero_records']} boş kayıt, "
                     f"{product_synced} Product.quantity güncellendi")

    return report


# -------------------------------
# Raf Stok Tahsis ve İade Fonksiyonları
# -------------------------------
def allocate_from_shelf_and_decrement(barcode: str, qty: int = 1) -> dict:
    """
    Raflardan stok tahsis eder ve CentralStock'u günceller.
    Race condition önlemek için with_for_update() kullanır.

    Returns: {"allocated": int, "shelf_codes": [...]}
    """
    barcode = normalize_barcode(barcode)

    if not barcode or qty <= 0:
        return {"allocated": 0, "shelf_codes": []}

    raflar = (RafUrun.query
              .filter_by(urun_barkodu=barcode)
              .filter(RafUrun.adet > 0)
              .order_by(RafUrun.adet.desc())
              .with_for_update()
              .all())

    shelf_codes = []
    allocated = 0
    need = qty

    for raf in raflar:
        if need <= 0:
            break
        cur = raf.adet or 0
        if cur <= 0:
            continue
        take = min(cur, need)
        raf.adet = cur - take
        db.session.flush()

        shelf_codes.extend([raf.raf_kodu] * take)
        allocated += take
        need -= take

    if allocated > 0:
        sync_central_stock(barcode, commit=False)

    if allocated < qty:
        logger.warning(
            f"[STOK-TAHSİS] Kısmi tahsis: {barcode} — istenen={qty}, tahsis={allocated}"
        )

    return {"allocated": allocated, "shelf_codes": shelf_codes}


def restore_stock_to_shelf(barcode: str, qty: int, shelf_code: str = None, commit: bool = True) -> dict:
    """
    Stoğu rafa geri yükler. Sipariş silme/iptal durumlarında kullanılır.
    shelf_code verilirse o rafa, yoksa ürünün mevcut olduğu ilk rafa ekler.

    Returns: {"restored": int, "shelf_code": str|None}
    """
    barcode = normalize_barcode(barcode)

    if not barcode or qty <= 0:
        return {"restored": 0, "shelf_code": None}

    target_raf = None

    if shelf_code:
        target_raf = (RafUrun.query
                      .filter_by(raf_kodu=shelf_code, urun_barkodu=barcode)
                      .with_for_update()
                      .first())
        if not target_raf:
            target_raf = RafUrun(raf_kodu=shelf_code, urun_barkodu=barcode, adet=0)
            db.session.add(target_raf)
            db.session.flush()
    else:
        target_raf = (RafUrun.query
                      .filter_by(urun_barkodu=barcode)
                      .with_for_update()
                      .first())

    if not target_raf:
        logger.warning(
            f"[STOK-İADE] {barcode} için raf bulunamadı, {qty} adet iade edilemedi"
        )
        return {"restored": 0, "shelf_code": None}

    target_raf.adet += qty
    db.session.flush()
    sync_central_stock(barcode, commit=False)

    logger.info(
        f"[STOK-İADE] {barcode} → {target_raf.raf_kodu} rafına {qty} adet iade edildi"
    )

    if commit:
        db.session.commit()

    return {"restored": qty, "shelf_code": target_raf.raf_kodu}


def allocate_stock_for_order_details(details_json, commit: bool = True) -> dict:
    """
    Sipariş detayları JSON'unu parse edip her ürün için raf stoğunu düşer.
    Platform siparişleri (OrderCreated) için kullanılır.

    Args:
        details_json: JSON string veya list — [{barcode, quantity}, ...]
        commit: True ise transaction commit eder

    Returns: {barcode: {"allocated": int, "shelf_codes": [...]}, ...}
    """
    import json as _json

    results = {}
    try:
        details = _json.loads(details_json) if isinstance(details_json, str) else details_json
        if not isinstance(details, list):
            return results

        for item in details:
            barcode = normalize_barcode(str(item.get('barcode', '') or '').strip())
            qty = int(item.get('quantity', 1) or 1)
            if not barcode or qty <= 0:
                continue

            alloc = allocate_from_shelf_and_decrement(barcode, qty)
            results[barcode] = alloc

        if commit:
            db.session.commit()
    except Exception as e:
        logger.error(f"[STOK-TAHSİS] Sipariş detayları işlenirken hata: {e}")
        if commit:
            db.session.rollback()

    return results


def restore_stock_for_order_details(details_json, shelf_code: str = None, commit: bool = True) -> dict:
    """
    Sipariş detayları JSON'unu parse edip her ürün için stoğu rafa geri yükler.
    Sipariş silme/iptal durumlarında kullanılır.

    Args:
        details_json: JSON string veya list — [{barcode, quantity}, ...]
        shelf_code: Hedef raf kodu (siparişin atanan_raf'ı). Verilirse o rafa iade eder,
                    yoksa ürünün mevcut olduğu ilk rafa ekler.
        commit: True ise transaction commit eder

    Returns: {barcode: {"restored": int, "shelf_code": str|None}, ...}
    """
    import json as _json

    results = {}
    try:
        details = _json.loads(details_json) if isinstance(details_json, str) else details_json
        if not isinstance(details, list):
            return results

        for item in details:
            barcode = normalize_barcode(str(item.get('barcode', '') or '').strip())
            qty = int(item.get('quantity', 1) or 1)
            if not barcode or qty <= 0:
                continue

            result = restore_stock_to_shelf(barcode, qty, shelf_code=shelf_code, commit=False)
            results[barcode] = result

        if commit:
            db.session.commit()
    except Exception as e:
        logger.error(f"[STOK-İADE] Sipariş detayları işlenirken hata: {e}")
        if commit:
            db.session.rollback()

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
        barcode = normalize_barcode(barcode)
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
    
    # 🔧 "=" ve "*" karakterlerini "-" ile değiştir (telefonlardan kaynaklanıyor)
    raf_kodu = raf_kodu.replace('=', '-').replace('*', '-')
    
    # 🛡️ Çift işlem kontrolü - Aynı istek 60 saniye içinde tekrar gelirse engelle
    items_key = "|".join(sorted(f"{it.get('barcode','')}:{it.get('count',0)}" for it in items))
    request_data = f"{raf_kodu}|{update_type}|{items_key}"
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
            barcode_set = [normalize_barcode(it.get('barcode')) for it in items if it.get('barcode')]
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
                barcode = normalize_barcode((it.get('barcode') or '').strip())
                try:
                    count = int(it.get('count', 0))
                except (TypeError, ValueError):
                    count = 0

                if not barcode or count <= 0:
                    logger.warning(f"Geçersiz barkod veya adet: barkod={barcode}, count={count}")
                    errors[barcode or 'EMPTY'] = "Geçersiz barkod/adet"
                    continue
                if not valid_products.get(barcode.lower()):
                    logger.warning(f"Ürün veritabanında bulunamadı: {barcode}")
                    errors[barcode] = "Ürün veritabanında yok"
                    continue
                
                # RafUrun kaydını bul veya oluştur
                rec = RafUrun.query.filter_by(raf_kodu=raf_kodu, urun_barkodu=barcode).first()
                
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

            # Transaction başarıyla tamamlandı
            logger.info(f"✅ Transaction başarıyla tamamlandı - {len(results)} ürün işlendi, {len(errors)} hata.")

        # 🔥 TÜM ETKİLENEN BARKODLAR İÇİN CENTRALSTOCK'U YENİDEN HESAPLA (transaction dışında)
        logger.info(f"📊 {len(affected_barcodes)} barkod için CentralStock senkronize ediliyor...")
        for barcode in affected_barcodes:
            new_qty = sync_central_stock(barcode, commit=False)
            # results listesinde bu barkodu güncelle
            for r in results:
                if r["barcode"] == barcode:
                    r["central_qty"] = new_qty
                    break
        db.session.commit()

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
        try: log_user_action("STOCK_UPDATE", {"işlem_açıklaması": f"Stok {'eklendi' if update_type=='add' else 'yenilendi'} — {raf_kodu}, {len(results)} ürün", "sayfa": "Stok Ekleme", "raf_kodu": raf_kodu, "işlem_tipi": update_type, "ürün_sayısı": len(results)})
        except: pass

        return jsonify(success=True,
                       message=message,
                       results=results)

    except Exception as e:
        logger.error(f"❌ HATA - Raf: {raf_kodu}, Mod: {update_type}, Ürün Sayısı: {len(items)}")
        logger.error("Stok ekleme/güncelleme hatası: %s", e, exc_info=True)
        return jsonify(success=False, message=f"Sunucu hatası: {str(e)}"), 500
