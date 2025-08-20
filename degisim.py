# -*- coding: utf-8 -*-

import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime, timedelta
import uuid
import random
import os
import json

from models import db, Degisim, Product
# Çok tablolu sipariş modelleriniz
from models import OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled
# Raf ve central stok
from models import RafUrun, CentralStock

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

degisim_bp = Blueprint('degisim', __name__)

# ──────────────────────────────────────────────────────────────────────────────
# Yardımcı: Siparişi her tabloda ara
# ──────────────────────────────────────────────────────────────────────────────
def find_order_across_tables(order_number):
    for table_cls in [OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled]:
        order = table_cls.query.filter_by(order_number=order_number).first()
        if order:
            return order, table_cls
    return None, None

# ──────────────────────────────────────────────────────────────────────────────
# Yardımcı: Raflardan tahsis (qty kadar), Central’dan düş (aynı miktar)
# ──────────────────────────────────────────────────────────────────────────────
def allocate_from_shelves_and_decrement_central(barcode, qty=1):
    """
    Verilen barkod için raflarda stok arar ve en çok stoğu olandan başlayarak
    'qty' adet tahsis eder. Tahsis edilen her adet için CentralStock da 1 düşer.
    Dönüş: {"allocated": int, "shelf_codes": [..]}  (allocated kadar raf_kodu döner)
    Not: Raf bulunamazsa central düşülmez; tahsis edilen kadar düşülür.
    """
    shelf_codes = []
    allocated = 0
    if not barcode or qty <= 0:
        return {"allocated": 0, "shelf_codes": []}

    # Rafları çoktan aza sırala (daha dengeli tahsis)
    raflar = (RafUrun.query
              .filter(RafUrun.barcode == barcode, RafUrun.quantity > 0)
              .order_by(RafUrun.quantity.desc())
              .all())

    need = qty
    for raf in raflar:
        if need <= 0:
            break
        take = min(raf.quantity or 0, need)
        if take <= 0:
            continue

        # Bu raftan 'take' kadar düş
        raf.quantity = (raf.quantity or 0) - take
        db.session.flush()
        shelf_codes.extend([getattr(raf, 'raf_kodu', None)] * take)
        allocated += take
        need -= take

    if allocated > 0:
        # CentralStock: tahsis edilen kadar 1:1 düş
        cs = CentralStock.query.filter_by(barcode=barcode).first()
        if cs:
            cs.qty = max(0, (cs.qty or 0) - allocated)
            db.session.flush()
        else:
            logger.warning(f"CentralStock kaydı yok (barcode={barcode}), raf düşüldü ama central yok.")

    return {"allocated": allocated, "shelf_codes": shelf_codes}

# ──────────────────────────────────────────────────────────────────────────────
# 1) Değişim Kaydetme (Raf + Central stok düşme entegre)
# ──────────────────────────────────────────────────────────────────────────────
@degisim_bp.route('/degisim-kaydet', methods=['POST'])
def degisim_kaydet():
    try:
        logger.info("--- /degisim-kaydet isteği alındı ---")
        logger.info(f"Form Verisi (request.form): {request.form}")

        siparis_no = request.form['siparis_no']
        ad         = request.form['ad']
        soyad      = request.form['soyad']
        adres      = request.form['adres']
        telefon_no = request.form.get('telefon_no', '')
        degisim_nedeni = request.form.get('degisim_nedeni', '')

        # Birden çok ürün satırı
        urun_barkodlari = request.form.getlist('urun_barkod')
        urun_modelleri  = request.form.getlist('urun_model_kodu')
        urun_renkleri   = request.form.getlist('urun_renk')
        urun_bedenleri  = request.form.getlist('urun_beden')
        # (opsiyonel) adet listesi varsa kullan, yoksa hepsi 1 kabul
        urun_adetleri   = request.form.getlist('urun_adet')  # varsa formda

        logger.info(f"Gelen Barkod Sayısı: {len(urun_barkodlari)} | Model Sayısı: {len(urun_modelleri)}")

        if (not urun_barkodlari or not urun_modelleri
            or len(urun_barkodlari) != len(urun_modelleri)
            or len(urun_barkodlari) != len(urun_renkleri)
            or len(urun_barkodlari) != len(urun_bedenleri)):
            flash('Ürün bilgileri eksik veya hatalı. Lütfen tekrar deneyin.', 'danger')
            logger.error("Ürün listeleri eşleşmiyor veya boş!")
            return redirect(url_for('degisim.yeni_degisim_talebi'))

        # Normalize adet listesi
        adet_listesi = []
        for i in range(len(urun_barkodlari)):
            try:
                adet_val = int(urun_adetleri[i]) if i < len(urun_adetleri) else 1
                adet_listesi.append(max(1, adet_val))
            except Exception:
                adet_listesi.append(1)

        urunler_listesi = []
        toplam_tahsis = 0

        # Aynı transaction içinde raf/central düşeceğiz
        for i in range(len(urun_barkodlari)):
            barkod = (urun_barkodlari[i] or "").strip()
            model  = urun_modelleri[i]
            renk   = urun_renkleri[i]
            beden  = urun_bedenleri[i]
            adet   = adet_listesi[i]

            # Raflardan tahsis + central düş (adet kadar)
            alloc = allocate_from_shelves_and_decrement_central(barkod, qty=adet)
            toplam_tahsis += alloc["allocated"]

            # Kartta göstermek üzere raf kodları (1’den fazlaysa liste döner)
            # UI tarafında tek alan istiyorsan join edebilirsin:
            raf_kodu_gosterim = ", ".join([rk for rk in alloc["shelf_codes"] if rk]) if alloc["shelf_codes"] else None

            urunler_listesi.append({
                "barkod": barkod,
                "model_kodu": model,
                "renk": renk,
                "beden": beden,
                "adet": adet,
                "raf_kodlari": alloc["shelf_codes"],   # detay
                "raf_kodu": raf_kodu_gosterim,         # kartta pratik gösterim
                "tahsis_edilen": alloc["allocated"]    # güvenlik için kayıt
            })

        urunler_json_str = json.dumps(urunler_listesi, ensure_ascii=False)

        degisim_kaydi = Degisim(
            degisim_no=str(uuid.uuid4()),
            siparis_no=siparis_no,
            ad=ad,
            soyad=soyad,
            adres=adres,
            telefon_no=telefon_no,
            degisim_tarihi=datetime.now(),
            degisim_durumu='Beklemede',
            kargo_kodu=generate_kargo_kodu(),
            degisim_nedeni=degisim_nedeni,
            urunler_json=urunler_json_str
        )

        db.session.add(degisim_kaydi)
        db.session.commit()

        logger.info(f"Değişim kaydı oluşturuldu: {degisim_kaydi.degisim_no} | Toplam tahsis: {toplam_tahsis}")
        flash('Değişim talebiniz başarıyla oluşturuldu!', 'success')
        return redirect(url_for('degisim.degisim_talep'))

    except Exception as e:
        logger.error(f"Değişim kaydında kritik hata: {e}", exc_info=True)
        db.session.rollback()
        flash(f'Beklenmedik bir hata oluştu: {e}', 'danger')
        return redirect(url_for('degisim.yeni_degisim_talebi'))

# ──────────────────────────────────────────────────────────────────────────────
# 2) Durum Güncelle
# ──────────────────────────────────────────────────────────────────────────────
@degisim_bp.route('/update_status', methods=['POST'])
def update_status():
    degisim_no = request.form.get('degisim_no')
    status = request.form.get('status')
    degisim_kaydi = Degisim.query.filter_by(degisim_no=degisim_no).first()
    if degisim_kaydi:
        degisim_kaydi.degisim_durumu = status
        db.session.commit()
        return jsonify(success=True)
    return jsonify(success=False), 500

# ──────────────────────────────────────────────────────────────────────────────
# 3) Sil
# ──────────────────────────────────────────────────────────────────────────────
@degisim_bp.route('/delete_exchange', methods=['POST'])
def delete_exchange():
    degisim_no = request.form.get('degisim_no')
    degisim_kaydi = Degisim.query.filter_by(degisim_no=degisim_no).first()
    if degisim_kaydi:
        db.session.delete(degisim_kaydi)
        db.session.commit()
        return jsonify(success=True)
    return jsonify(success=False), 500

# ──────────────────────────────────────────────────────────────────────────────
# 4) Ürün detay getir
# ──────────────────────────────────────────────────────────────────────────────
@degisim_bp.route('/get_product_details', methods=['POST'])
def get_product_details():
    barcode = request.form['barcode']
    product = Product.query.filter_by(barcode=barcode).first()
    if product:
        image_path = f"static/images/{barcode}.jpg"
        if not os.path.exists(image_path):
            image_path = "static/images/default.jpg"
        return jsonify({
            'success': True,
            'product_main_id': product.product_main_id,
            'size': product.size,
            'color': product.color,
            'barcode': barcode,
            'image_url': image_path
        })
    return jsonify({'success': False, 'message': 'Ürün bulunamadı'})

# ──────────────────────────────────────────────────────────────────────────────
# 5) Sipariş detay getir (değişim formunda otomatik doldurma)
# ──────────────────────────────────────────────────────────────────────────────
@degisim_bp.route('/get_order_details', methods=['POST'])
def get_order_details():
    siparis_no = request.form['siparis_no']
    order, _table_cls = find_order_across_tables(siparis_no)
    if order:
        details_list = []
        order_details = json.loads(order.details) if order.details else []
        for detail in order_details:
            details_list.append({
                'sku': detail.get('sku'),
                'barcode': detail.get('barcode'),
                'image_url': f"static/images/{detail.get('barcode')}.jpg"
            })
        return jsonify({
            'success': True,
            'ad': order.customer_name,
            'soyad': order.customer_surname,
            'adres': order.customer_address,
            'telefon_no': getattr(order, 'telefon_no', ''),
            'details': details_list
        })
    return jsonify({'success': False, 'message': 'Sipariş bulunamadı'})

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
        if hasattr(exchange, 'urunler_json') and exchange.urunler_json:
            try:
                urun_listesi = json.loads(exchange.urunler_json)
                if isinstance(urun_listesi, list):
                    exchange.urunler = urun_listesi
            except json.JSONDecodeError:
                logger.error(f"JSON Decode Hatası - degisim_no: {exchange.degisim_no} - Hatalı Veri: '{exchange.urunler_json}'")

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
        siparis_no = request.form['siparis_no']
        order, _table_cls = find_order_across_tables(siparis_no)
        if order:
            details_list = []
            order_details = json.loads(order.details) if order.details else []
            for detail in order_details:
                details_list.append({
                    'sku': detail.get('sku'),
                    'barcode': detail.get('barcode')
                })
            return jsonify({
                'success': True,
                'ad': order.customer_name,
                'soyad': order.customer_surname,
                'adres': order.customer_address,
                'urunler': details_list
            })
        else:
            return jsonify({'success': False, 'message': 'Sipariş bulunamadı'})
    return render_template('yeni_degisim_talebi.html')

# ──────────────────────────────────────────────────────────────────────────────
# 8) Kargo Kodu Üretme
# ──────────────────────────────────────────────────────────────────────────────
def generate_kargo_kodu():
    return "555" + str(random.randint(1000000, 9999999))
