# -*- coding: utf-8 -*-

import logging
import base64
import re
import requests
from collections import Counter
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime
import uuid
import random
import os
import json

from models import db, Degisim, Product
from user_logs import log_user_action
# Çok tablolu sipariş modelleriniz
from models import OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled
# Raf ve central stok
from models import RafUrun, CentralStock
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID

# Güvenli barkod deseni: Unicode harf/rakam (Türkçe karakterler dahil), tire, alt çizgi.
# Path traversal koruması için /, \, ., null byte ve diğer ayraçlar dışlanır.
_SAFE_BARCODE_RE = re.compile(r'^[\w\-]{1,64}$', re.UNICODE)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

degisim_bp = Blueprint('degisim', __name__)


# helpers
def _resolve_col(model, candidates):
    for name in candidates:
        if hasattr(model, name):
            return getattr(model, name), name
    raise AttributeError(f"{model.__name__} içinde bu adaylardan hiçbiri yok: {candidates}")

def _get_attr(obj, candidates, default=None):
    for name in candidates:
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _safe_barcode(barcode: str) -> str | None:
    """Barkodu doğrular; geçersizse None döner. Path traversal koruması."""
    if not barcode:
        return None
    barcode = barcode.strip()
    if not _SAFE_BARCODE_RE.match(barcode):
        return None
    return barcode


def _safe_image_url(barcode: str) -> str:
    """Barkoda göre güvenli görsel yolu üretir; barkod geçersizse default döner."""
    safe = _safe_barcode(barcode)
    if not safe:
        return "static/images/default.jpg"
    path = f"static/images/{safe}.jpg"
    return path if os.path.exists(path) else "static/images/default.jpg"


def _safe_json_loads(raw, default=None):
    """raw hem str hem dict/list olabilir; güvenli şekilde deserialize eder."""
    if raw is None or raw == "":
        return default if default is not None else []
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as exc:
        logger.warning(f"JSON parse hatası: {exc} — veri: {str(raw)[:120]}")
        return default if default is not None else []


def _safe_log(action: str, details: dict) -> None:
    try:
        log_user_action(action, details)
    except Exception as exc:
        logger.warning(f"Kullanıcı log kaydı başarısız ({action}): {exc}")

# ──────────────────────────────────────────────────────────────────────────────
# Yardımcı: Siparişi her tabloda ara
# ──────────────────────────────────────────────────────────────────────────────
def find_order_across_tables(order_number):
    for table_cls in [OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled]:
        order = table_cls.query.filter_by(order_number=order_number).first()
        if order:
            return order, table_cls
    return None, None


def _fetch_trendyol_phone(order_number: str) -> str:
    """Trendyol API'den sipariş numarasıyla müşteri telefonunu çeker."""
    try:
        auth = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode()).decode()
        url = f"https://api.trendyol.com/sapigw/suppliers/{SUPPLIER_ID}/orders"
        resp = requests.get(url, headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json"
        }, params={"orderNumber": order_number, "size": 1}, timeout=10)
        data = resp.json()
        orders = data.get("content", [])
        if orders:
            return orders[0].get("shipmentAddress", {}).get("phone", "") or ""
    except Exception as e:
        logger.warning(f"Trendyol telefon çekme hatası ({order_number}): {e}")
    return ""


def _fetch_shopify_order_info(order_number: str) -> dict | None:
    """Shopify sipariş numarasıyla müşteri bilgilerini ve ürünleri çeker."""
    try:
        from shopify_site.shopify_service import shopify_service

        shopify_id = order_number.replace("SH-", "")
        result = shopify_service.get_order(shopify_id)
        if not result.get("success") or not result.get("order"):
            return None

        order = result["order"]
        customer = order.get("customer") or {}
        shipping = order.get("shippingAddress") or {}
        billing = order.get("billingAddress") or {}

        phone = (customer.get("phone") or shipping.get("phone")
                 or billing.get("phone") or "")

        address_parts = [
            shipping.get("address1", ""),
            shipping.get("address2", ""),
            shipping.get("city", ""),
            shipping.get("province", ""),
            shipping.get("country", ""),
        ]
        address = " ".join(p for p in address_parts if p).strip()

        line_items = order.get("lineItems", {}).get("edges", [])
        details_list = []
        for edge in line_items:
            li = edge.get("node", {})
            variant = li.get("variant") or {}
            remote_img = (variant.get("image") or {}).get("url", "") or ""
            barcode = variant.get("barcode") or ""
            # Shopify mutlak URL dönebilir; frontend aynı mantıkla handle eder
            image_url = remote_img if remote_img else _safe_image_url(barcode)
            details_list.append({
                "sku": li.get("sku") or variant.get("sku") or "",
                "barcode": barcode,
                "image_url": image_url,
            })

        return {
            "ad": customer.get("firstName") or (shipping.get("name", "").split(" ")[0] if shipping.get("name") else ""),
            "soyad": customer.get("lastName") or (" ".join(shipping.get("name", "").split(" ")[1:]) if shipping.get("name") else ""),
            "adres": address,
            "telefon_no": phone,
            "details": details_list,
        }
    except Exception as e:
        logger.warning(f"Shopify sipariş bilgisi çekme hatası ({order_number}): {e}")
    return None

# ──────────────────────────────────────────────────────────────────────────────
# Yardımcı: Raflardan tahsis (qty kadar). CentralStock, models.py içindeki
# event listener tarafından commit sonrası OTOMATİK senkronize edilir — burada
# manuel commit yapılmaz, böylece çok ürünlü bir değişimde tek transaction'da
# atomik çalışır.
# ──────────────────────────────────────────────────────────────────────────────
def allocate_from_shelves(barcode: str, qty: int = 1) -> dict:
    """
    RafUrun.urun_barkodu üzerinden raflardan 'qty' adet tahsis eder.
    Hiçbir commit yapmaz — çağıran transaction'ı yönetir.
    Dönüş: {"allocated": int, "shelf_codes": [..]}
    """
    if not barcode or qty <= 0:
        return {"allocated": 0, "shelf_codes": []}

    raflar = (
        RafUrun.query
        .filter(RafUrun.urun_barkodu == barcode, RafUrun.adet > 0)
        .order_by(RafUrun.adet.desc())
        .with_for_update()  # Eşzamanlı değişim taleplerinde yarış koşulunu önle
        .all()
    )

    shelf_codes: list[str] = []
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
        shelf_codes.extend([raf.raf_kodu] * take)
        allocated += take
        need -= take

    return {"allocated": allocated, "shelf_codes": shelf_codes}


def restore_to_shelves(shelf_code_counts: dict) -> int:
    """
    Silinen/iptal edilen değişim kaydının stoğunu raflara geri yazar.
    shelf_code_counts: { (raf_kodu, barcode): adet } sözlüğü.
    Dönüş: toplam iade edilen adet.
    """
    if not shelf_code_counts:
        return 0

    toplam = 0
    for (raf_kodu, barcode), adet in shelf_code_counts.items():
        if not raf_kodu or not barcode or adet <= 0:
            continue
        rec = (
            RafUrun.query
            .filter_by(raf_kodu=raf_kodu, urun_barkodu=barcode)
            .with_for_update()
            .first()
        )
        if rec:
            rec.adet = (rec.adet or 0) + adet
        else:
            db.session.add(RafUrun(raf_kodu=raf_kodu, urun_barkodu=barcode, adet=adet))
        toplam += adet
    return toplam


def _aggregate_shelf_restore(urunler: list) -> dict:
    """urunler_json'dan (raf_kodu, barcode) → adet toplamı çıkarır."""
    counts: Counter = Counter()
    for urun in urunler or []:
        barcode = (urun.get("barkod") or "").strip()
        if not barcode:
            continue
        shelf_list = urun.get("raf_kodlari") or []
        if shelf_list:
            for rk in shelf_list:
                if rk:
                    counts[(rk, barcode)] += 1
        else:
            # Tek raf_kodu alanı (virgülle ayrılmış olabilir)
            raf_kodu = urun.get("raf_kodu")
            if raf_kodu:
                for rk in str(raf_kodu).split(","):
                    rk = rk.strip()
                    if rk:
                        counts[(rk, barcode)] += 1
    return dict(counts)


# ──────────────────────────────────────────────────────────────────────────────
# 1) Değişim Kaydetme (Tek transaction — raf düşüşü + kayıt atomik)
# ──────────────────────────────────────────────────────────────────────────────
@degisim_bp.route('/degisim-kaydet', methods=['POST'])
def degisim_kaydet():
    try:
        logger.info("--- /degisim-kaydet isteği alındı ---")

        siparis_no     = (request.form.get('siparis_no') or '').strip()
        ad             = (request.form.get('ad') or '').strip()
        soyad          = (request.form.get('soyad') or '').strip()
        adres          = (request.form.get('adres') or '').strip()
        telefon_no     = (request.form.get('telefon_no') or '').strip()
        degisim_nedeni = (request.form.get('degisim_nedeni') or '').strip()

        if not siparis_no:
            return jsonify(success=False, message='Sipariş numarası zorunludur.'), 400
        if not degisim_nedeni:
            return jsonify(success=False, message='Değişim sebebi zorunludur.'), 400

        urun_barkodlari = request.form.getlist('urun_barkod')
        urun_modelleri  = request.form.getlist('urun_model_kodu')
        urun_renkleri   = request.form.getlist('urun_renk')
        urun_bedenleri  = request.form.getlist('urun_beden')
        urun_adetleri   = request.form.getlist('urun_adet')

        n = len(urun_barkodlari)
        if (n == 0
                or len(urun_modelleri) != n
                or len(urun_renkleri) != n
                or len(urun_bedenleri) != n):
            logger.error(
                f"Form liste uzunlukları uyuşmuyor: "
                f"barkod={n}, model={len(urun_modelleri)}, "
                f"renk={len(urun_renkleri)}, beden={len(urun_bedenleri)}"
            )
            return jsonify(
                success=False,
                message='Ürün bilgileri eksik veya hatalı. Lütfen barkod girip "Getir" ile bilgileri doldurun.'
            ), 400

        # Adet normalizasyonu (form adet göndermiyorsa varsayılan 1)
        adet_listesi = []
        for i in range(n):
            try:
                adet_val = int(urun_adetleri[i]) if i < len(urun_adetleri) else 1
            except (ValueError, TypeError):
                adet_val = 1
            adet_listesi.append(max(1, adet_val))

        urunler_listesi = []
        toplam_tahsis = 0
        stok_hatalari = []

        # Tek transaction: herhangi bir ürün yetersizse rollback olur.
        for i in range(n):
            barkod = _safe_barcode(urun_barkodlari[i])
            if not barkod:
                stok_hatalari.append(f"{i+1}. satır: geçersiz barkod")
                continue

            model = (urun_modelleri[i] or '').strip()
            renk  = (urun_renkleri[i]  or '').strip()
            beden = (urun_bedenleri[i] or '').strip()
            adet  = adet_listesi[i]

            alloc = allocate_from_shelves(barkod, qty=adet)

            if alloc["allocated"] < adet:
                stok_hatalari.append(
                    f"{barkod}: istenen {adet}, mevcut {alloc['allocated']}"
                )
                continue

            toplam_tahsis += alloc["allocated"]
            raf_kodu_gosterim = (
                ", ".join([rk for rk in alloc["shelf_codes"] if rk])
                if alloc["shelf_codes"] else None
            )

            urunler_listesi.append({
                "barkod": barkod,
                "model_kodu": model,
                "renk": renk,
                "beden": beden,
                "adet": adet,
                "raf_kodlari": alloc["shelf_codes"],
                "raf_kodu": raf_kodu_gosterim,
                "tahsis_edilen": alloc["allocated"],
            })

        if stok_hatalari:
            db.session.rollback()
            hata_mesaji = "Stok yetersiz veya hatalı: " + "; ".join(stok_hatalari)
            logger.warning(hata_mesaji)
            return jsonify(success=False, message=hata_mesaji), 400

        urunler_json_str = json.dumps(urunler_listesi, ensure_ascii=False)

        degisim_kaydi = Degisim(
            degisim_no=str(uuid.uuid4()),
            siparis_no=siparis_no,
            ad=ad,
            soyad=soyad,
            adres=adres,
            telefon_no=telefon_no,
            degisim_tarihi=datetime.utcnow(),
            degisim_durumu='Oluşturuldu',
            kargo_kodu=generate_kargo_kodu(),
            degisim_nedeni=degisim_nedeni,
            urunler_json=urunler_json_str,
            musteri_kargo_takip=None,
        )

        db.session.add(degisim_kaydi)
        db.session.commit()
        # CentralStock & Product.quantity event listener tarafından commit sonrası
        # otomatik senkronize edilir (models.py).

        _safe_log("CREATE", {
            "işlem_açıklaması": f"Değişim talebi oluşturuldu — {degisim_kaydi.degisim_no}, {toplam_tahsis} adet",
            "sayfa": "Değişim Talepleri",
            "değişim_no": degisim_kaydi.degisim_no,
            "toplam_tahsis": toplam_tahsis,
        })
        logger.info(
            f"Değişim kaydı oluşturuldu: {degisim_kaydi.degisim_no} | "
            f"Toplam tahsis: {toplam_tahsis}"
        )
        flash('Değişim talebiniz başarıyla oluşturuldu!', 'success')
        return redirect(url_for('degisim.degisim_talep'))

    except Exception as e:
        logger.error(f"Değişim kaydında kritik hata: {e}", exc_info=True)
        db.session.rollback()
        return jsonify(success=False, message=f'Beklenmedik bir hata oluştu: {e}'), 500

# ──────────────────────────────────────────────────────────────────────────────
# 2) Durum Güncelle
# ──────────────────────────────────────────────────────────────────────────────
@degisim_bp.route('/update_status', methods=['POST'])
def update_status():
    degisim_no = (request.form.get('degisim_no') or '').strip()
    status = (request.form.get('status') or '').strip()
    musteri_kargo_takip = (request.form.get('musteri_kargo_takip') or '').strip()

    if not degisim_no or not status:
        return jsonify(success=False, message="Eksik parametre"), 400

    try:
        rec = Degisim.query.filter_by(degisim_no=degisim_no).first()
        if not rec:
            return jsonify(success=False, message="Kayıt bulunamadı"), 404

        # Takip no kontrolü (her statü için)
        if not (rec.musteri_kargo_takip or musteri_kargo_takip):
            return jsonify(
                success=False,
                need_tracking=True,
                message="Müşteri kargo takip numarası olmadan statü güncellenemez.",
            )

        if musteri_kargo_takip:
            rec.musteri_kargo_takip = musteri_kargo_takip

        rec.degisim_durumu = status
        db.session.commit()

        _safe_log("UPDATE", {
            "işlem_açıklaması": f"Değişim durumu güncellendi — {degisim_no} → {status}",
            "sayfa": "Değişim Talepleri",
            "değişim_no": degisim_no,
            "yeni_durum": status,
        })
        return jsonify(success=True)
    except Exception as exc:
        db.session.rollback()
        logger.error(f"update_status hatası: {exc}", exc_info=True)
        return jsonify(success=False, message="Sunucu hatası"), 500



# ──────────────────────────────────────────────────────────────────────────────
# 3) Sil (silerken raflardan düşülen stok geri iade edilir)
# ──────────────────────────────────────────────────────────────────────────────
@degisim_bp.route('/delete_exchange', methods=['POST'])
def delete_exchange():
    degisim_no = (request.form.get('degisim_no') or '').strip()
    if not degisim_no:
        return jsonify(success=False, message="degisim_no eksik"), 400

    try:
        rec = Degisim.query.filter_by(degisim_no=degisim_no).first()
        if not rec:
            return jsonify(success=False, message="Kayıt bulunamadı"), 404

        # Stok iadesi — kayıttaki urunler_json'dan raf kodlarını topla, geri yaz
        urunler = _safe_json_loads(rec.urunler_json, default=[])
        shelf_counts = _aggregate_shelf_restore(urunler if isinstance(urunler, list) else [])
        iade_edilen = restore_to_shelves(shelf_counts)

        db.session.delete(rec)
        db.session.commit()
        # CentralStock otomatik senkronize edilir (models.py event listener).

        _safe_log("DELETE", {
            "işlem_açıklaması": f"Değişim talebi silindi — {degisim_no} (stok iade: {iade_edilen})",
            "sayfa": "Değişim Talepleri",
            "değişim_no": degisim_no,
            "stok_iade": iade_edilen,
        })
        logger.info(
            f"Değişim silindi: {degisim_no} | İade edilen adet: {iade_edilen}"
        )
        return jsonify(success=True, stok_iade=iade_edilen)
    except Exception as exc:
        db.session.rollback()
        logger.error(f"delete_exchange hatası: {exc}", exc_info=True)
        return jsonify(success=False, message="Sunucu hatası"), 500

# ──────────────────────────────────────────────────────────────────────────────
# 4) Ürün detay getir
# ──────────────────────────────────────────────────────────────────────────────
@degisim_bp.route('/get_product_details', methods=['POST'])
def get_product_details():
    raw_barcode = (request.form.get('barcode') or '').strip()
    barcode = _safe_barcode(raw_barcode)
    if not barcode:
        return jsonify({'success': False, 'message': 'Geçersiz barkod'}), 400

    product = Product.query.filter_by(barcode=barcode).first()
    if product:
        return jsonify({
            'success': True,
            'product_main_id': product.product_main_id,
            'size': product.size,
            'color': product.color,
            'barcode': barcode,
            'image_url': _safe_image_url(barcode),
        })
    return jsonify({'success': False, 'message': 'Ürün bulunamadı'})

# ──────────────────────────────────────────────────────────────────────────────
# 5) Sipariş detay getir (değişim formunda otomatik doldurma)
# ──────────────────────────────────────────────────────────────────────────────
@degisim_bp.route('/get_order_details', methods=['POST'])
def get_order_details():
    siparis_no = (request.form.get('siparis_no') or '').strip()
    if not siparis_no:
        return jsonify({'success': False, 'message': 'Sipariş numarası eksik'}), 400

    # Shopify siparişi
    if siparis_no.startswith("SH-"):
        info = _fetch_shopify_order_info(siparis_no)
        if info:
            return jsonify({'success': True, **info})
        return jsonify({'success': False, 'message': 'Shopify siparişi bulunamadı'})

    # Trendyol / WooCommerce — DB'den
    order, _table_cls = find_order_across_tables(siparis_no)
    if not order:
        return jsonify({'success': False, 'message': 'Sipariş bulunamadı'})

    order_details = _safe_json_loads(getattr(order, 'details', None), default=[])
    details_list = []
    for detail in order_details if isinstance(order_details, list) else []:
        bc = detail.get('barcode') or ''
        details_list.append({
            'sku': detail.get('sku') or '',
            'barcode': bc,
            'image_url': _safe_image_url(bc),
        })

    telefon = getattr(order, 'telefon_no', '') or ''
    if not telefon:
        telefon = _fetch_trendyol_phone(siparis_no)

    return jsonify({
        'success': True,
        'ad': getattr(order, 'customer_name', '') or '',
        'soyad': getattr(order, 'customer_surname', '') or '',
        'adres': getattr(order, 'customer_address', '') or '',
        'telefon_no': telefon,
        'details': details_list,
    })

# ──────────────────────────────────────────────────────────────────────────────
# 6) Listeleme (kartlarda raf_kodu/raf_kodlari görünür)
# ──────────────────────────────────────────────────────────────────────────────
@degisim_bp.route('/degisim_talep')
def degisim_talep():
    page = request.args.get('page', 1, type=int)
    try:
        per_page = int(request.args.get('per_page', 12))
        per_page = max(5, min(100, per_page))
    except (ValueError, TypeError):
        per_page = 12

    filter_status = request.args.get('filter_status')
    sort = request.args.get('sort', 'desc')
    siparis_no = request.args.get('siparis_no')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    reason_keyword = request.args.get('reason_keyword')

    query = Degisim.query

    if filter_status:
        query = query.filter(Degisim.degisim_durumu == filter_status)
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(Degisim.degisim_tarihi >= start_date)
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(Degisim.degisim_tarihi <= end_date)
        except ValueError:
            pass
    if reason_keyword and reason_keyword.strip():
        query = query.filter(Degisim.degisim_nedeni.ilike(f"%{reason_keyword.strip()}%"))
    if siparis_no and siparis_no.strip():
        query = query.filter(Degisim.siparis_no.ilike(f"%{siparis_no.strip()}%"))

    if sort == 'asc':
        query = query.order_by(Degisim.degisim_tarihi.asc())
    else:
        query = query.order_by(Degisim.degisim_tarihi.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    degisim_kayitlari = pagination.items

    for exchange in degisim_kayitlari:
        exchange.urunler = []
        urun_listesi = _safe_json_loads(getattr(exchange, 'urunler_json', None), default=[])
        if isinstance(urun_listesi, list):
            exchange.urunler = urun_listesi

    current_filters = {
        'per_page': per_page, 'filter_status': filter_status,
        'sort': sort, 'siparis_no': siparis_no, 'start_date': start_date_str,
        'end_date': end_date_str, 'reason_keyword': reason_keyword
    }

    return render_template(
        'degisim_talep.html',
        degisim_kayitlari=degisim_kayitlari,
        page=page,
        total_pages=pagination.pages,
        total_exchanges_count=pagination.total,
        current_filters=current_filters
    )

# ──────────────────────────────────────────────────────────────────────────────
# 7) Yeni Değişim Talebi Formu
# ──────────────────────────────────────────────────────────────────────────────
@degisim_bp.route('/yeni-degisim-talebi', methods=['GET', 'POST'])
def yeni_degisim_talebi():
    if request.method == 'POST':
        siparis_no = (request.form.get('siparis_no') or '').strip()
        if not siparis_no:
            return jsonify({'success': False, 'message': 'Sipariş numarası eksik'}), 400

        if siparis_no.startswith("SH-"):
            info = _fetch_shopify_order_info(siparis_no)
            if info:
                return jsonify({
                    'success': True,
                    'ad': info['ad'],
                    'soyad': info['soyad'],
                    'adres': info['adres'],
                    'telefon_no': info['telefon_no'],
                    'urunler': info['details'],
                })
            return jsonify({'success': False, 'message': 'Shopify siparişi bulunamadı'})

        order, _table_cls = find_order_across_tables(siparis_no)
        if not order:
            return jsonify({'success': False, 'message': 'Sipariş bulunamadı'})

        order_details = _safe_json_loads(getattr(order, 'details', None), default=[])
        details_list = [
            {'sku': d.get('sku') or '', 'barcode': d.get('barcode') or ''}
            for d in (order_details if isinstance(order_details, list) else [])
        ]

        telefon = getattr(order, 'telefon_no', '') or ''
        if not telefon:
            telefon = _fetch_trendyol_phone(siparis_no)

        return jsonify({
            'success': True,
            'ad': getattr(order, 'customer_name', '') or '',
            'soyad': getattr(order, 'customer_surname', '') or '',
            'adres': getattr(order, 'customer_address', '') or '',
            'telefon_no': telefon,
            'urunler': details_list,
        })
    return render_template('yeni_degisim_talebi.html')

# ──────────────────────────────────────────────────────────────────────────────
# 8) Kargo Kodu Üretme (DB'de benzersizlik garanti)
# ──────────────────────────────────────────────────────────────────────────────
def generate_kargo_kodu(max_attempts: int = 10) -> str:
    """Benzersiz bir kargo kodu üretir. 10 denemede bulamazsa UUID suffix ekler."""
    for _ in range(max_attempts):
        kod = "555" + str(random.randint(1000000, 9999999))
        if not Degisim.query.filter_by(kargo_kodu=kod).first():
            return kod
    # Son çare: çakışmayı garanti önlemek için UUID parçası ekle
    return "555" + uuid.uuid4().hex[:10].upper()
