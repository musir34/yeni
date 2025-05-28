from flask import (
    Blueprint, render_template, request, jsonify,
    flash, redirect, url_for
)
from datetime import datetime
import json, traceback
from sqlalchemy import or_

from models import db, Product, YeniSiparis, SiparisUrun
from logger_config import order_logger
logger = order_logger

def safe_json_loads(data, default=None):
    """JSON parsing için güvenli fonksiyon - HTML içeriği kontrolü yapar"""
    if default is None:
        default = []
    
    if not data:
        return default
    
    try:
        # HTML içeriği kontrolü
        if isinstance(data, str) and ('<' in data or '>' in data):
            logger.warning(f"HTML içeriği tespit edildi, varsayılan değer döndürülüyor: {data[:50]}...")
            return default
        
        return json.loads(data)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"JSON parse hatası: {e}, varsayılan değer döndürülüyor")
        return default

siparisler_bp = Blueprint('siparisler_bp', __name__)


# ------------------------------------------------------------- #
#  YENİ SİPARİŞ – Liste (GET) • Oluştur (POST)
# ------------------------------------------------------------- #
@siparisler_bp.route('/yeni-siparis', methods=['GET', 'POST'])
def yeni_siparis():
    logger.debug(">> yeni_siparis: %s", request.method)

    # ---------------- GET ---------------- #
    if request.method == 'GET':
        try:
            q_no   = (request.args.get('siparis_no')  or '').strip()
            q_name = (request.args.get('musteri_adi') or '').strip()
            q_stat = (request.args.get('durum')       or '').strip()

            query = YeniSiparis.query
            if q_no:
                query = query.filter(YeniSiparis.siparis_no.ilike(f'%{q_no}%'))
            if q_name:
                query = query.filter(
                    (YeniSiparis.musteri_adi + ' ' +
                     YeniSiparis.musteri_soyadi).ilike(f'%{q_name}%'))
            if q_stat:
                query = query.filter(YeniSiparis.durum == q_stat)

            siparisler = query.order_by(
                YeniSiparis.siparis_tarihi.desc()
            ).all()

            # None veya HTML kırıntılarını temizle
            for s in siparisler:
                try:
                    # Toplam tutarı güvenli şekilde float'a çevir
                    if s.toplam_tutar is None:
                        s.toplam_tutar = 0
                    elif isinstance(s.toplam_tutar, str):
                        # HTML içeriği kontrolü
                        if '<' in s.toplam_tutar or '>' in s.toplam_tutar:
                            logger.warning(f"Sipariş {s.siparis_no} HTML içeriği tespit edildi, 0 atanıyor")
                            s.toplam_tutar = 0
                        else:
                            s.toplam_tutar = float(s.toplam_tutar or 0)
                    else:
                        s.toplam_tutar = float(s.toplam_tutar or 0)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Sipariş {s.siparis_no} tutar dönüştürme hatası: {e}")
                    s.toplam_tutar = 0

            return render_template('yeni_siparis.html', siparisler=siparisler)

        except Exception as e:
            logger.error("Siparişler listelenirken hata: %s", e)
            logger.debug("Traceback:\n%s", traceback.format_exc())
            return render_template('error.html', hata=str(e)), 500

    # ---------------- POST --------------- #
    try:
        data = request.get_json() if request.is_json else {
            'musteri_adi'     : request.form.get('musteri_adi'),
            'musteri_soyadi'  : request.form.get('musteri_soyadi'),
            'musteri_adres'   : request.form.get('musteri_adres'),
            'musteri_telefon' : request.form.get('musteri_telefon'),
            'toplam_tutar'    : float(request.form.get('toplam_tutar') or 0),
            'notlar'          : request.form.get('notlar', ''),
            'urunler'         : safe_json_loads(request.form.get('urunler', '[]')),
        }

        siparis_no = f"SP{datetime.now():%Y%m%d%H%M%S}"
        sip = YeniSiparis(
            siparis_no       = siparis_no,
            musteri_adi      = data['musteri_adi'],
            musteri_soyadi   = data['musteri_soyadi'],
            musteri_adres    = data['musteri_adres'],
            musteri_telefon  = data['musteri_telefon'],
            toplam_tutar     = data['toplam_tutar'],
            notlar           = data.get('notlar', ''),
        )
        db.session.add(sip); db.session.flush()

        for u in data['urunler']:
            adet  = u.get('adet') or 0
            fiyat = u.get('birim_fiyat') or 0
            db.session.add(SiparisUrun(
                siparis_id   = sip.id,
                urun_barkod  = u.get('barkod', ''),
                urun_adi     = u.get('urun_adi', ''),
                adet         = adet,
                birim_fiyat  = fiyat,
                toplam_fiyat = adet * fiyat,
                renk         = u.get('renk', ''),
                beden        = u.get('beden', ''),
                urun_gorseli = u.get('urun_gorseli', ''),
            ))

        db.session.commit()
        return jsonify(success=True, message='Sipariş başarıyla kaydedildi')

    except Exception as e:
        db.session.rollback()
        logger.error("Sipariş kaydedilirken hata: %s", e)
        logger.debug("Traceback:\n%s", traceback.format_exc())
        return render_template('error.html', hata=str(e)), 500


# ------------------------------------------------------------- #
#  ÜRÜN GETİR (API)
# ------------------------------------------------------------- #
@siparisler_bp.route('/api/product/<barcode>')
def get_product(barcode):
    try:
        p = Product.query.filter_by(barcode=barcode).first()
        if not p:
            return jsonify(success=False, message='Ürün bulunamadı')
        return jsonify(success=True, product={
            'barcode': p.barcode,
            'title': p.title,
            'product_main_id': p.product_main_id,
            'color': p.color,
            'size': p.size,
            'images': p.images,
            'sale_price': float(p.sale_price or 0),
            'quantity': p.quantity
        })
    except Exception as e:
        logger.error("Ürün hatası: %s", e)
        return jsonify(success=False, message=str(e)), 500


# ------------------------------------------------------------- #
#  SİPARİŞ ARAMA (API)
# ------------------------------------------------------------- #
@siparisler_bp.route('/api/siparisler/search')
def siparis_ara():
    try:
        q     = (request.args.get('q')     or '').strip()
        field = (request.args.get('field') or 'all').strip()
        if not q:
            return jsonify(success=True, siparisler=[], message='Boş arama')

        query = YeniSiparis.query
        if field == 'siparis_no':
            query = query.filter(YeniSiparis.siparis_no.ilike(f'%{q}%'))
        elif field == 'musteri':
            query = query.filter(
                (YeniSiparis.musteri_adi + ' ' +
                 YeniSiparis.musteri_soyadi).ilike(f'%{q}%'))
        elif field == 'durum':
            query = query.filter(YeniSiparis.durum.ilike(f'%{q}%'))
        else:
            query = query.filter(or_(
                YeniSiparis.siparis_no.ilike(f'%{q}%'),
                (YeniSiparis.musteri_adi + ' ' +
                 YeniSiparis.musteri_soyadi).ilike(f'%{q}%'),
                YeniSiparis.durum.ilike(f'%{q}%')
            ))

        rows = query.order_by(
            YeniSiparis.siparis_tarihi.desc()
        ).limit(100).all()

        return jsonify(success=True, count=len(rows), siparisler=[{
            'siparis_no': r.siparis_no,
            'musteri'   : f"{r.musteri_adi} {r.musteri_soyadi}",
            'tutar'     : float(r.toplam_tutar or 0),
            'tarih'     : r.siparis_tarihi.strftime('%d.%m.%Y %H:%M') if r.siparis_tarihi else '',
            'durum'     : r.durum
        } for r in rows])

    except Exception as e:
        logger.error("Arama hatası: %s", e)
        logger.debug("Traceback:\n%s", traceback.format_exc())
        return jsonify(success=False, error=str(e)), 500


# ------------------------------------------------------------- #
#  SİPARİŞ DETAY (modal)
# ------------------------------------------------------------- #
@siparisler_bp.route('/siparis-detay/<siparis_no>')
def siparis_detay(siparis_no):
    try:
        sip = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
        if not sip:
            return "Sipariş bulunamadı", 404
        urunler = SiparisUrun.query.filter_by(siparis_id=sip.id).all()
        return render_template('siparis_detay_partial.html',
                               siparis=sip, urunler=urunler)
    except Exception as e:
        logger.error("Detay hatası: %s", e)
        return "Bir hata oluştu", 500


# ------------------------------------------------------------- #
#  SİPARİŞ GÜNCELLE
# ------------------------------------------------------------- #
@siparisler_bp.route('/siparis-guncelle/<siparis_no>', methods=['POST'])
def siparis_guncelle(siparis_no):
    try:
        sip = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
        if not sip:
            return jsonify(success=False, message='Sipariş bulunamadı')

        data = request.get_json() if request.is_json else request.form.to_dict()
        if 'urunler' in data and isinstance(data['urunler'], str):
            data['urunler'] = json.loads(data['urunler'])

        sip.musteri_adi     = data.get('musteri_adi', sip.musteri_adi)
        sip.musteri_soyadi  = data.get('musteri_soyadi', sip.musteri_soyadi)
        sip.musteri_adres   = data.get('musteri_adres', sip.musteri_adres)
        sip.musteri_telefon = data.get('musteri_telefon', sip.musteri_telefon)
        sip.durum           = data.get('durum', sip.durum)
        sip.notlar          = data.get('notlar', sip.notlar)

        if 'urunler' in data:
            SiparisUrun.query.filter_by(siparis_id=sip.id).delete()
            toplam = 0
            for u in data['urunler']:
                adet, fiyat = u.get('adet') or 0, u.get('birim_fiyat') or 0
                db.session.add(SiparisUrun(
                    siparis_id   = sip.id,
                    urun_barkod  = u.get('barkod', ''),
                    urun_adi     = u.get('urun_adi', ''),
                    adet         = adet,
                    birim_fiyat  = fiyat,
                    toplam_fiyat = adet * fiyat,
                    renk         = u.get('renk', ''),
                    beden        = u.get('beden', ''),
                ))
                toplam += adet * fiyat
            sip.toplam_tutar = toplam

        db.session.commit()
        return jsonify(success=True, message='Sipariş güncellendi')

    except Exception as e:
        db.session.rollback()
        logger.error("Güncelleme hatası: %s", e)
        return jsonify(success=False, message=str(e)), 500


# ------------------------------------------------------------- #
#  SİPARİŞ SİL
# ------------------------------------------------------------- #
@siparisler_bp.route('/siparis-sil/<siparis_no>', methods=['DELETE'])
def siparis_sil(siparis_no):
    try:
        sip = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
        if not sip:
            return jsonify(success=False, message='Sipariş bulunamadı')

        SiparisUrun.query.filter_by(siparis_id=sip.id).delete()
        db.session.delete(sip)
        db.session.commit()
        return jsonify(success=True, message='Sipariş silindi')

    except Exception as e:
        db.session.rollback()
        logger.error("Silme hatası: %s", e)
        return jsonify(success=False, message=str(e)), 500