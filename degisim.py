import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime
import uuid
import random
import os
import json
from models import db, Degisim, Product

# Çok tablolu sipariş modelleriniz:
# (Örnek: Created / Picking / Shipped / Delivered / Cancelled)
from models import OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

degisim_bp = Blueprint('degisim', __name__)

##################################
# Yardımcı fonksiyon: Siparişi her tabloda arar
##################################
def find_order_across_tables(order_number):
    """
    order_number'a sahip siparişi Created, Picking, Shipped, Delivered, Cancelled tablolarında arar.
    Bulursa (order_obj, tablo_sinifi), bulamazsa (None, None) döndürür.
    """
    # Projenizde farklı tablo varsa ekleyin
    for table_cls in [OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled]:
        order = table_cls.query.filter_by(order_number=order_number).first()
        if order:
            return order, table_cls
    return None, None

##################################
# 1) Değişim Kaydetme
##################################
@degisim_bp.route('/degisim-kaydet', methods=['POST'])
def degisim_kaydet():
    try:
        degisim_no = str(uuid.uuid4())
        siparis_no = request.form['siparis_no']
        ad = request.form['ad']
        soyad = request.form['soyad']
        adres = request.form['adres']
        telefon_no = request.form.get('telefon_no', '')
        urun_barkod = request.form['urun_barkod']
        urun_model_kodu = request.form['urun_model_kodu']
        urun_renk = request.form['urun_renk']
        urun_beden = request.form['urun_beden']
        degisim_tarihi = datetime.now()
        degisim_durumu = 'Beklemede'
        kargo_kodu = generate_kargo_kodu()
        degisim_nedeni = request.form.get('degisim_nedeni', '')

        degisim_kaydi = Degisim(
            degisim_no=degisim_no,
            siparis_no=siparis_no,
            ad=ad,
            soyad=soyad,
            adres=adres,
            telefon_no=telefon_no,
            urun_barkod=urun_barkod,
            urun_model_kodu=urun_model_kodu,
            urun_renk=urun_renk,
            urun_beden=urun_beden,
            degisim_tarihi=degisim_tarihi,
            degisim_durumu=degisim_durumu,
            kargo_kodu=kargo_kodu,
            degisim_nedeni=degisim_nedeni
        )

        db.session.add(degisim_kaydi)
        db.session.commit()

        logging.info(f"Değişim kaydı oluşturuldu: {degisim_no}")
        flash('Değişim talebi başarıyla oluşturuldu ve kargo kodu kaydedildi!', 'success')
        return redirect(url_for('degisim.degisim_talep'))

    except Exception as e:
        logging.error(f"Değişim kaydında hata: {e}")
        flash('Bir hata oluştu. Lütfen tekrar deneyin.', 'danger')
        return redirect(url_for('degisim.degisim_talep'))

##################################
# 2) Değişim Durumu Güncelleme
##################################
@degisim_bp.route('/update_status', methods=['POST'])
def update_status():
    degisim_no = request.form.get('degisim_no')
    status = request.form.get('status')
    logging.info(f"Statü güncelleniyor: degisim_no={degisim_no}, status={status}")

    degisim_kaydi = Degisim.query.filter_by(degisim_no=degisim_no).first()
    if degisim_kaydi:
        degisim_kaydi.degisim_durumu = status
        db.session.commit()
        logging.info(f"Statü başarıyla güncellendi: degisim_no={degisim_no}")
        return jsonify(success=True)
    else:
        logging.warning(f"Statü güncellenirken hata oluştu: degisim_no={degisim_no}")
        return jsonify(success=False), 500

##################################
# 3) Değişim Kaydı Silme
##################################
@degisim_bp.route('/delete_exchange', methods=['POST'])
def delete_exchange():
    degisim_no = request.form.get('degisim_no')
    logging.info(f"Değişim kaydı siliniyor: degisim_no={degisim_no}")

    degisim_kaydi = Degisim.query.filter_by(degisim_no=degisim_no).first()
    if degisim_kaydi:
        db.session.delete(degisim_kaydi)
        db.session.commit()
        logging.info(f"Değişim kaydı başarıyla silindi: degisim_no={degisim_no}")
        return jsonify(success=True)
    else:
        logging.warning(f"Değişim kaydı silinirken hata oluştu: degisim_no={degisim_no}")
        return jsonify(success=False), 500

##################################
# 4) Ürün Detaylarını Getirme
##################################
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
    else:
        return jsonify({'success': False, 'message': 'Ürün bulunamadı'})

##################################
# 5) Sipariş Detaylarını Getirme (Çok Tablolu)
##################################
@degisim_bp.route('/get_order_details', methods=['POST'])
def get_order_details():
    siparis_no = request.form['siparis_no']

    # Eski: order = Order.query.filter_by(order_number=siparis_no).first()
    # Yeni: çok tabloda ara
    order, _table_cls = find_order_across_tables(siparis_no)

    if order:
        details_list = []
        # 'order.details' her tabloda aynı sütun ismiyle varsa
        order_details = json.loads(order.details) if order.details else []
        for detail in order_details:
            barcode = detail.get('barcode')
            sku = detail.get('sku')
            image_path = f"static/images/{barcode}.jpg"
            if not os.path.exists(image_path):
                image_path = "static/images/default.jpg"

            details_list.append({
                'sku': sku,
                'barcode': barcode,
                'image_url': image_path
            })

        # Her tabloda 'customer_name', 'customer_surname', 'customer_address' vb. kolonlarının olduğunu varsayıyoruz
        return jsonify({
            'success': True,
            'ad': order.customer_name,
            'soyad': order.customer_surname,
            'adres': order.customer_address,
            'telefon_no': getattr(order, 'telefon_no', ''),
            'details': details_list
        })
    else:
        return jsonify({'success': False, 'message': 'Sipariş bulunamadı'})

##################################
# 6) Değişim Taleplerini Listeleme
##################################
@degisim_bp.route('/degisim_talep')
def degisim_talep():
    page = request.args.get('page', 1, type=int)
    per_page = 10

    # Filtre, sıralama ve arama parametrelerini alıyoruz
    filter_status = request.args.get('filter_status')
    sort = request.args.get('sort', 'desc')
    siparis_no = request.args.get('siparis_no')

    logging.info(f"Değişim talepleri filtreleniyor: sayfa={page}, durum={filter_status}, sıralama={sort}, siparis_no={siparis_no}")

    # Veritabanı sorgusu
    query = Degisim.query

    # Duruma göre filtre
    if filter_status:
        query = query.filter(Degisim.degisim_durumu == filter_status)

    # Sipariş numarası filtre
    if siparis_no:
        # Tam eşleşme deniyoruz
        if len(siparis_no) >= 10:
            exact_match = query.filter(Degisim.siparis_no == siparis_no).all()
            if exact_match:
                return render_template(
                    'degisim_talep.html',
                    degisim_kayitlari=exact_match,
                    page=1,
                    total_pages=1,
                    total_exchanges_count=len(exact_match)
                )
        # Tam eşleşme yoksa partial arama
        query = query.filter(Degisim.siparis_no.ilike(f"%{siparis_no}%"))

    # Sıralama
    if sort == 'asc':
        query = query.order_by(Degisim.degisim_tarihi.asc())
    else:
        query = query.order_by(Degisim.degisim_tarihi.desc())

    # Sayfalama
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    degisim_kayitlari = pagination.items
    total_records = pagination.total
    total_pages = pagination.pages

    logging.info(f"Toplam {total_records} değişim talebi bulundu, {len(degisim_kayitlari)} adet gösteriliyor")

    return render_template(
        'degisim_talep.html',
        degisim_kayitlari=degisim_kayitlari,
        page=page,
        total_pages=total_pages,
        total_exchanges_count=total_records
    )

##################################
# 7) Yeni Değişim Talebi Formu
##################################
@degisim_bp.route('/yeni-degisim-talebi', methods=['GET', 'POST'])
def yeni_degisim_talebi():
    if request.method == 'POST':
        siparis_no = request.form['siparis_no']

        # Çok tablolu arama
        order, _table_cls = find_order_across_tables(siparis_no)

        if order:
            details = []
            order_details = json.loads(order.details) if order.details else []
            for detail in order_details:
                details.append({
                    'sku': detail.get('sku'),
                    'barcode': detail.get('barcode')
                })

            return jsonify({
                'success': True,
                'ad': order.customer_name,
                'soyad': order.customer_surname,
                'adres': order.customer_address,
                'urunler': details
            })
        else:
            return jsonify({'success': False, 'message': 'Sipariş bulunamadı'})

    return render_template('yeni_degisim_talebi.html')

##################################
# 8) Kargo Kodu Üretme
##################################
def generate_kargo_kodu():
    return "555" + str(random.randint(1000000, 9999999))
