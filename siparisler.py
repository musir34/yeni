from flask import (
    Blueprint, render_template, request, jsonify,
    flash, redirect, url_for
)
from datetime import datetime
import json, traceback
from sqlalchemy import or_

# models.py dosyasından modelleri ve db'yi import ettiğini varsayıyorum
# Örnek: from .models import db, Product, YeniSiparis, SiparisUrun
# Eğer farklı bir yapıdaysa, bu kısmı kendi projenize göre düzenleyin.
try:
    from models import db, Product, YeniSiparis, SiparisUrun, RafUrun, CentralStock
except ImportError:
    print("UYARI: 'models' modülü bulunamadı. Lütfen doğru import yolunu kontrol edin.")
    class FakeDB:
        def __init__(self):
            self.session = None 
    db = FakeDB()
    class BasePlaceholderModel:
        query = None 
        # Gerçek modelinizdeki alanları buraya ekleyebilirsiniz (test amaçlı)
        id = siparis_no = musteri_adi = musteri_soyadi = toplam_tutar = siparis_tarihi = durum = None
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
        @classmethod
        def filter_by(cls, **kwargs): return cls # Sahte filter_by
        def first(self): return None # Sahte first
        def all(self): return [] # Sahte all
        def desc(self): return self # Sahte desc
        def order_by(self, *args): return self # Sahte order_by
        def ilike(self, *args): return True # Sahte ilike
        def delete(self): pass # Sahte delete

    Product = SiparisUrun = YeniSiparis = BasePlaceholderModel


# logger_config.py dosyasından logger'ı import ettiğini varsayıyorum
try:
    from logger_config import order_logger
except ImportError:
    import logging
    print("UYARI: 'logger_config' modülü bulunamadı. Standart logging kullanılacak.")
    order_logger = logging.getLogger('siparisler_bp_fallback')
    order_logger.setLevel(logging.DEBUG)
    if not order_logger.hasHandlers():
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        order_logger.addHandler(handler)

logger = order_logger

siparisler_bp = Blueprint('siparisler_bp', __name__)


# ------------------------------------------------------------- #
#  YARDIMCI FONKSİYON: RAF TAHSIS VE STOK DÜŞÜRME
# ------------------------------------------------------------- #
def allocate_from_shelf_and_decrement(barcode, qty=1):
    """
    Raflardan stok tahsis eder ve central stoktan düşer.
    Returns: {"allocated": int, "shelf_codes": [..]}
    """
    if not barcode or qty <= 0:
        return {"allocated": 0, "shelf_codes": []}
    
    # 🔧 Barkodu küçük harfe normalize et
    barcode = str(barcode).strip().lower()
    
    # Raflardan stok çoktan aza sırala
    raflar = (RafUrun.query
              .filter_by(urun_barkodu=barcode)
              .filter(RafUrun.adet > 0)
              .order_by(RafUrun.adet.desc())
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
        
        # Tahsis edilen her adet için raf kodunu ekle
        shelf_codes.extend([raf.raf_kodu] * take)
        allocated += take
        need -= take
    
    # CentralStock'tan düş
    if allocated > 0:
        cs = CentralStock.query.get(barcode)
        if cs:
            cs.qty = max(0, (cs.qty or 0) - allocated)
            db.session.flush()
    
    return {"allocated": allocated, "shelf_codes": shelf_codes}


# ------------------------------------------------------------- #
#  YENİ SİPARİŞ – Liste (GET) • Oluştur (POST)
# ------------------------------------------------------------- #
@siparisler_bp.route('/yeni-siparis', methods=['GET', 'POST'])
def yeni_siparis():
    logger.info(f"Yeni sipariş isteği alındı. Method: {request.method}")

    # ---------------- GET ---------------- #
    if request.method == 'GET':
        try:
            q_no   = (request.args.get('siparis_no')  or '').strip()
            q_name = (request.args.get('musteri_adi') or '').strip()
            q_stat = (request.args.get('durum')       or '').strip()
            logger.debug(f"GET /yeni-siparis - Filtreler: siparis_no='{q_no}', musteri_adi='{q_name}', durum='{q_stat}'")

            query = YeniSiparis.query 
            if q_no:
                query = query.filter(YeniSiparis.siparis_no.ilike(f'%{q_no}%'))
            if q_name:
                query = query.filter(
                    (YeniSiparis.musteri_adi + ' ' +
                     YeniSiparis.musteri_soyadi).ilike(f'%{q_name}%'))
            if q_stat:
                query = query.filter(YeniSiparis.durum == q_stat)

            # Eğer query hala placeholder ise (import hatası durumunda)
            if hasattr(query, 'order_by') and callable(query.order_by):
                 siparisler_query = query.order_by(getattr(YeniSiparis.siparis_tarihi, 'desc', lambda: None)())
                 if hasattr(siparisler_query, 'all') and callable(siparisler_query.all):
                     siparisler = siparisler_query.all()
                 else:
                     siparisler = [] # Sorgu zinciri tamamlanamıyorsa boş liste
                     logger.warning("YeniSiparis.all() çağrılamadı, siparisler boş liste olarak ayarlandı.")
            else:
                siparisler = [] # Query özelliği yoksa boş liste
                logger.warning("YeniSiparis.query.order_by çağrılamadı, siparisler boş liste olarak ayarlandı.")


            logger.info(f"{len(siparisler)} adet sipariş bulundu ve listeleniyor.")

            # !!!!! HAM VERİ KONTROL LOGLARI BAŞLANGIÇ !!!!!
            for i, s_kontrol in enumerate(siparisler):
                logger.debug(
                    f"SIPARIS KONTROL #{i} - "
                    f"ID: '{getattr(s_kontrol, 'id', 'N/A')}', "
                    f"No: '{getattr(s_kontrol, 'siparis_no', 'N/A')}', "
                    f"Müşteri Adı: '{getattr(s_kontrol, 'musteri_adi', 'N/A')}', "
                    f"Müşteri Soyadı: '{getattr(s_kontrol, 'musteri_soyadi', 'N/A')}', "
                    f"Toplam Tutar (Ham): '{getattr(s_kontrol, 'toplam_tutar', 'N/A')}' (Tip: {type(getattr(s_kontrol, 'toplam_tutar', None))}), "
                    f"Sipariş Tarihi (Ham): '{getattr(s_kontrol, 'siparis_tarihi', 'N/A')}' (Tip: {type(getattr(s_kontrol, 'siparis_tarihi', None))}), "
                    f"Durum: '{getattr(s_kontrol, 'durum', 'N/A')}'"
                )
            # !!!!! HAM VERİ KONTROL LOGLARI SON !!!!!

            for s in siparisler:
                original_tutar_value = str(getattr(s, 'toplam_tutar', 'N/A'))
                try:
                    current_tutar = getattr(s, 'toplam_tutar', None)
                    if current_tutar is None:
                        s.toplam_tutar = 0.0
                    elif isinstance(current_tutar, (int, float)):
                        s.toplam_tutar = float(current_tutar)
                    else: 
                        s.toplam_tutar = float(str(current_tutar)) # Önce str'ye çevirip sonra float'a zorla
                except (ValueError, TypeError) as e_convert: 
                    logger.warning(
                        f"Sipariş {getattr(s, 'siparis_no', 'N/A')} için toplam_tutar ('{original_tutar_value}') "
                        f"float'a dönüştürülürken hata: {e_convert}. Değer 0.0 olarak ayarlandı."
                    )
                    s.toplam_tutar = 0.0 
                except Exception as e_general_conversion: 
                    logger.error(
                        f"Sipariş {getattr(s, 'siparis_no', 'N/A')} için toplam_tutar ('{original_tutar_value}') "
                        f"dönüştürme sırasında genel hata: {e_general_conversion}. Değer 0.0 olarak ayarlandı."
                    )
                    s.toplam_tutar = 0.0


            return render_template('yeni_siparis.html', siparisler=siparisler)

        except Exception as e:
            logger.error(f"Siparişler listelenirken genel bir hata oluştu: {e}")
            logger.error(f"Hata tipi: {type(e)}")
            logger.error(f"Hata detayı: {repr(e)}")
            logger.debug(f"Traceback:\n{traceback.format_exc()}") 
            return render_template('error.html', hata=str(e)), 500

    # ---------------- POST --------------- #
    try:
        if request.is_json:
            data = request.get_json()
            logger.debug("POST /yeni-siparis - JSON verisi alındı: %s", data)
        else:
            # Form verisi için güvenli JSON parsing
            urunler_str = request.form.get('urunler', '[]')
            try:
                urunler_data = json.loads(urunler_str) if urunler_str else []
            except json.JSONDecodeError as je:
                logger.error(f"Form'dan gelen ürünler JSON formatı bozuk: {je}")
                logger.debug(f"Bozuk JSON: {urunler_str}")
                urunler_data = []
            
            data = {
                'musteri_adi'     : request.form.get('musteri_adi'),
                'musteri_soyadi'  : request.form.get('musteri_soyadi'),
                'musteri_adres'   : request.form.get('musteri_adres'),
                'musteri_telefon' : request.form.get('musteri_telefon'),
                'toplam_tutar'    : request.form.get('toplam_tutar'), 
                'notlar'          : request.form.get('notlar', ''),
                'kapida_odeme'    : request.form.get('kapida_odeme') == 'on',
                'kapida_odeme_tutari' : request.form.get('kapida_odeme_tutari'),
                'urunler'         : urunler_data,
            }
            logger.info(f"🔍 KAPIDA ÖDEME DEBUG - Raw form data:")
            logger.info(f"   kapida_odeme checkbox: {request.form.get('kapida_odeme')}")
            logger.info(f"   kapida_odeme_tutari: {request.form.get('kapida_odeme_tutari')}")
            logger.info(f"   kapida_odeme (boolean): {data.get('kapida_odeme')}")
            logger.debug("POST /yeni-siparis - Form verisi alındı: %s", data)

        if not data.get('musteri_adi') or not data.get('urunler'): # Temel doğrulama
            logger.warning("Eksik veri ile sipariş oluşturma denemesi: %s", data)
            return jsonify(success=False, message='Müşteri adı ve ürünler zorunludur.'), 400

        try:
            siparis_toplam_tutar = float(data.get('toplam_tutar') or 0.0)
        except (ValueError, TypeError):
            logger.warning(f"POST /yeni-siparis: Geçersiz toplam tutar formatı: {data.get('toplam_tutar')}. 0.0 olarak ayarlanacak.")
            siparis_toplam_tutar = 0.0

        siparis_no = f"SP{datetime.now():%Y%m%d%H%M%S%f}"
        logger.info(f"Yeni sipariş oluşturuluyor. Sipariş No: {siparis_no}")

        # Kapıda ödeme tutarını işle
        kapida_odeme = data.get('kapida_odeme', False)
        kapida_odeme_tutari = None
        if kapida_odeme:
            try:
                kapida_odeme_tutari = float(data.get('kapida_odeme_tutari') or 0.0)
            except (ValueError, TypeError):
                logger.warning(f"Geçersiz kapıda ödeme tutarı: {data.get('kapida_odeme_tutari')}. 0.0 olarak ayarlanacak.")
                kapida_odeme_tutari = 0.0

        sip = YeniSiparis(
            siparis_no=siparis_no,
            musteri_adi=data['musteri_adi'],
            musteri_soyadi=data.get('musteri_soyadi', ''), # Soyad opsiyonel olabilir, varsayılan boş string
            musteri_adres=data.get('musteri_adres', ''),
            musteri_telefon=data.get('musteri_telefon', ''),
            toplam_tutar=siparis_toplam_tutar,
            notlar=data.get('notlar', ''),
            durum=data.get('durum', 'Yeni Sipariş'), # Varsayılan durum
            kapida_odeme=kapida_odeme,
            kapida_odeme_tutari=kapida_odeme_tutari
        )
        db.session.add(sip)
        logger.debug(f"YeniSiparis nesnesi session'a eklendi: {siparis_no}")
        db.session.flush() 
        sip_id = getattr(sip, 'id', None) # ID'yi al, yoksa None
        logger.debug(f"YeniSiparis nesnesi flush edildi. ID: {sip_id}")

        if sip_id is None: # Eğer sipariş ID'si alınamadıysa (flush başarısızsa)
            logger.error("Sipariş ID'si flush sonrası alınamadı. Sipariş ürünleri eklenemiyor.")
            db.session.rollback()
            return jsonify(success=False, message='Sipariş oluşturulurken ID alınamadı.'), 500

        for idx, u_data in enumerate(data['urunler']):
            adet_raw, fiyat_raw = u_data.get('adet'), u_data.get('birim_fiyat')
            try:
                urun_adet = int(adet_raw or 0)
            except (ValueError, TypeError):
                urun_adet = 0
            try:
                urun_birim_fiyat = float(fiyat_raw or 0.0)
            except (ValueError, TypeError):
                urun_birim_fiyat = 0.0

            # Raftan tahsis et ve stok düş
            barkod = u_data.get('barkod', '')
            alloc = allocate_from_shelf_and_decrement(barkod, qty=urun_adet)
            raf_kodu = ", ".join([rk for rk in alloc["shelf_codes"] if rk]) if alloc["shelf_codes"] else None

            db.session.add(SiparisUrun(
                siparis_id   = sip_id,
                urun_barkod  = barkod,
                urun_adi     = u_data.get('urun_adi', ''),
                adet         = urun_adet,
                birim_fiyat  = urun_birim_fiyat,
                toplam_fiyat = urun_adet * urun_birim_fiyat,
                renk         = u_data.get('renk', ''),
                beden        = u_data.get('beden', ''),
                urun_gorseli = u_data.get('urun_gorseli', ''),
                raf_kodu     = raf_kodu  # Hangi raftan alındığı
            ))
        logger.info(f"{len(data['urunler'])} adet ürün SiparisUrun tablosuna eklenecek.")

        db.session.commit()
        logger.info(f"Sipariş {siparis_no} başarıyla veritabanına kaydedildi.")
        return jsonify(success=True, message='Sipariş başarıyla kaydedildi', siparis_no=siparis_no)

    except json.JSONDecodeError as je:
        db.session.rollback()
        logger.error(f"Sipariş kaydedilirken JSON parse hatası: {je}")
        logger.debug(f"Hatalı JSON verisi (formdan geldiyse): {request.form.get('urunler')}")
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return jsonify(success=False, message=f'JSON formatı bozuk: {je}'), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Sipariş kaydedilirken genel hata: {e}")
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return jsonify(success=False, message=f'Sunucu hatası: {e}'), 500


# ------------------------------------------------------------- #
#  ÜRÜN GETİR (API)
# ------------------------------------------------------------- #
@siparisler_bp.route('/api/product/<barcode>')
def get_product(barcode):
    logger.info(f"Ürün getirme isteği alındı. Barkod: {barcode}")
    try:
        p = Product.query.filter_by(barcode=barcode).first()
        if not p:
            logger.warning(f"Barkod {barcode} için ürün bulunamadı.")
            return jsonify(success=False, message='Ürün bulunamadı'), 404

        sale_price_raw = getattr(p, 'sale_price', 0.0)
        try:
            sale_price = float(sale_price_raw or 0.0)
        except (ValueError, TypeError):
            logger.warning(f"Ürün {barcode} için sale_price ('{sale_price_raw}') float'a dönüştürülemedi. 0.0 olarak ayarlandı.")
            sale_price = 0.0

        product_data = {
            'barcode': getattr(p, 'barcode', ''),
            'title': getattr(p, 'title', 'N/A'),
            'product_main_id': getattr(p, 'product_main_id', ''),
            'color': getattr(p, 'color', ''),
            'size': getattr(p, 'size', ''),
            'images': getattr(p, 'images', None), 
            'sale_price': sale_price,
            'quantity': getattr(p, 'quantity', 0)
        }
        return jsonify(success=True, product=product_data)
    except Exception as e:
        logger.error(f"Ürün getirilirken hata (barkod: {barcode}): {e}")
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return jsonify(success=False, message=f'Sunucu hatası: {e}'), 500


# ------------------------------------------------------------- #
#  SİPARİŞ ARAMA (API)
# ------------------------------------------------------------- #
@siparisler_bp.route('/api/siparisler/search')
def siparis_ara():
    q     = (request.args.get('q')     or '').strip()
    field = (request.args.get('field') or 'all').strip()
    logger.info(f"Sipariş arama isteği. Sorgu: '{q}', Alan: '{field}'")

    if not q:
        return jsonify(success=True, siparisler=[], count=0, message='Boş arama')

    try:
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

        if hasattr(query, 'order_by') and callable(query.order_by):
            rows_query = query.order_by(getattr(YeniSiparis.siparis_tarihi, 'desc', lambda: None)()).limit(100)
            if hasattr(rows_query, 'all') and callable(rows_query.all):
                rows = rows_query.all()
            else:
                rows = []
                logger.warning("Sipariş arama sorgusu .all() çağrılamadı.")
        else:
            rows = []
            logger.warning("Sipariş arama YeniSiparis.query.order_by çağrılamadı.")


        logger.info(f"Arama sonucu {len(rows)} adet sipariş bulundu.")

        result_list = []
        for r in rows:
            tutar_raw = getattr(r, 'toplam_tutar', 0.0)
            try:
                tutar = float(tutar_raw or 0.0)
            except (ValueError, TypeError):
                tutar = 0.0

            tarih_obj = getattr(r, 'siparis_tarihi', None)
            tarih_str = tarih_obj.strftime('%d.%m.%Y %H:%M') if tarih_obj and hasattr(tarih_obj, 'strftime') else ''

            result_list.append({
                'siparis_no': getattr(r, 'siparis_no', 'N/A'),
                'musteri'   : f"{getattr(r, 'musteri_adi', '')} {getattr(r, 'musteri_soyadi', '')}".strip(),
                'tutar'     : tutar,
                'tarih'     : tarih_str,
                'durum'     : getattr(r, 'durum', 'N/A'),
                'id'        : getattr(r, 'id', None)
            })

        return jsonify(success=True, count=len(rows), siparisler=result_list)

    except Exception as e:
        logger.error(f"Sipariş arama sırasında hata (sorgu: {q}, alan: {field}): {e}")
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return jsonify(success=False, error=f'Sunucu hatası: {e}'), 500


# ------------------------------------------------------------- #
#  SİPARİŞ DETAY (modal için partial HTML)
# ------------------------------------------------------------- #
@siparisler_bp.route('/siparis-detay/<siparis_no>')
def siparis_detay(siparis_no):
    logger.info(f"Sipariş detay isteği. Sipariş No: {siparis_no}")
    try:
        sip = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
        if not sip:
            logger.warning(f"Sipariş detayı için sipariş bulunamadı: {siparis_no}")
            return "Sipariş bulunamadı", 404

        original_tutar_value = str(getattr(sip, 'toplam_tutar', 'N/A'))
        try:
            current_tutar = getattr(sip, 'toplam_tutar', None)
            if current_tutar is None:
                sip.toplam_tutar = 0.0
            elif isinstance(current_tutar, (int, float)):
                 sip.toplam_tutar = float(current_tutar)
            else:
                sip.toplam_tutar = float(str(current_tutar))
        except (ValueError, TypeError) as e_convert:
            logger.warning(
                f"Sipariş detay {getattr(sip, 'siparis_no', 'N/A')} için toplam_tutar ('{original_tutar_value}') "
                f"float'a dönüştürülürken hata: {e_convert}. Değer 0.0 olarak ayarlandı."
            )
            sip.toplam_tutar = 0.0

        urunler_query = SiparisUrun.query.filter_by(siparis_id=getattr(sip, 'id', None))
        urunler = urunler_query.all() if hasattr(urunler_query, 'all') and callable(urunler_query.all) else []
        
        # Her ürün için Product tablosundan model bilgilerini al
        for urun in urunler:
            if hasattr(urun, 'urun_barkod') and urun.urun_barkod:
                try:
                    product = Product.query.filter_by(barcode=urun.urun_barkod).first()
                    if product:
                        # Product tablosundan model bilgilerini al
                        urun.product_main_id = getattr(product, 'product_main_id', '')
                        # Eğer ürün görseli SiparisUrun'da yoksa Product'tan al
                        if not getattr(urun, 'urun_gorseli', None):
                            images = getattr(product, 'images', None)
                            if images and isinstance(images, list) and len(images) > 0:
                                urun.urun_gorseli = images[0].get('url', '') if isinstance(images[0], dict) else str(images[0])
                            else:
                                urun.urun_gorseli = None
                    else:
                        urun.product_main_id = None
                        if not getattr(urun, 'urun_gorseli', None):
                            urun.urun_gorseli = None
                except Exception as e:
                    logger.warning(f"Ürün {urun.urun_barkod} için Product bilgisi alınırken hata: {e}")
                    urun.product_main_id = None
                    if not getattr(urun, 'urun_gorseli', None):
                        urun.urun_gorseli = None


        for urun in urunler:
            for attr_name in ['birim_fiyat', 'toplam_fiyat']:
                original_val = str(getattr(urun, attr_name, 'N/A'))
                try:
                    current_val = getattr(urun, attr_name, None)
                    if current_val is None:
                        setattr(urun, attr_name, 0.0)
                    elif isinstance(current_val, (int, float)):
                        setattr(urun, attr_name, float(current_val))
                    else:
                        setattr(urun, attr_name, float(str(current_val)))
                except (ValueError, TypeError):
                    logger.warning(f"Sipariş detay {getattr(sip, 'siparis_no', 'N/A')}, ürün {getattr(urun, 'urun_barkod', 'N/A')} için {attr_name} ('{original_val}') float'a dönüştürülemedi. 0.0 olarak ayarlandı.")
                    setattr(urun, attr_name, 0.0)

        return render_template('siparis_detay_partial.html', 
                               siparis=sip, urunler=urunler)
    except Exception as e:
        logger.error(f"Sipariş detayı getirilirken hata (siparis_no: {siparis_no}): {e}")
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return "Bir hata oluştu, lütfen logları kontrol edin.", 500


# ------------------------------------------------------------- #
#  MÜŞTERİ BİLGİSİ JSON (Yazdırma için)
# ------------------------------------------------------------- #
@siparisler_bp.route('/siparis-musteri-bilgisi/<siparis_no>')
def siparis_musteri_bilgisi(siparis_no):
    """Müşteri bilgilerini JSON olarak döndürür (yazdırma için)"""
    logger.info(f"Müşteri bilgisi isteği. Sipariş No: {siparis_no}")
    try:
        sip = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
        if not sip:
            return jsonify(success=False, message='Sipariş bulunamadı'), 404
        
        # Kapıda ödeme tutarını güvenli şekilde al
        kapida_odeme_tutari = 0.0
        if sip.kapida_odeme_tutari:
            try:
                kapida_odeme_tutari = float(sip.kapida_odeme_tutari)
            except (ValueError, TypeError):
                kapida_odeme_tutari = 0.0
        
        return jsonify({
            'success': True,
            'siparis_no': sip.siparis_no,
            'musteri_adi': sip.musteri_adi or '',
            'musteri_soyadi': sip.musteri_soyadi or '',
            'musteri_telefon': sip.musteri_telefon or '',
            'musteri_adres': sip.musteri_adres or '',
            'kapida_odeme': bool(sip.kapida_odeme),
            'kapida_odeme_tutari': kapida_odeme_tutari
        })
    except Exception as e:
        logger.error(f"Müşteri bilgisi getirilirken hata (siparis_no: {siparis_no}): {e}")
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return jsonify(success=False, message='Bir hata oluştu'), 500


# ------------------------------------------------------------- #
#  SİPARİŞ GÜNCELLE
# ------------------------------------------------------------- #
@siparisler_bp.route('/siparis-guncelle/<siparis_no>', methods=['POST'])
def siparis_guncelle(siparis_no):
    logger.info(f"Sipariş güncelleme isteği. Sipariş No: {siparis_no}")
    try:
        sip = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
        if not sip:
            return jsonify(success=False, message='Sipariş bulunamadı'), 404

        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict() # Form verilerini al

        if 'urunler' in data and isinstance(data['urunler'], str):
            try:
                data['urunler'] = json.loads(data['urunler'])
            except json.JSONDecodeError as je:
                return jsonify(success=False, message=f"'urunler' alanı hatalı JSON formatında: {je}"), 400

        # Alanları güncelle
        sip.musteri_adi     = data.get('musteri_adi', sip.musteri_adi)
        sip.musteri_soyadi  = data.get('musteri_soyadi', sip.musteri_soyadi)
        sip.musteri_adres   = data.get('musteri_adres', sip.musteri_adres)
        sip.musteri_telefon = data.get('musteri_telefon', sip.musteri_telefon)
        sip.durum           = data.get('durum', sip.durum)
        sip.notlar          = data.get('notlar', sip.notlar)

        if 'urunler' in data and isinstance(data['urunler'], list): 
            SiparisUrun.query.filter_by(siparis_id=sip.id).delete() # Eski ürünleri sil

            hesaplanan_toplam_tutar = 0.0
            for u_data in data['urunler']:
                adet_raw, fiyat_raw = u_data.get('adet'), u_data.get('birim_fiyat')
                try: adet = int(adet_raw or 0)
                except (ValueError, TypeError): adet = 0
                try: fiyat = float(fiyat_raw or 0.0)
                except (ValueError, TypeError): fiyat = 0.0

                db.session.add(SiparisUrun(
                    siparis_id   = sip.id,
                    urun_barkod  = u_data.get('barkod', ''),
                    urun_adi     = u_data.get('urun_adi', ''),
                    adet         = adet,
                    birim_fiyat  = fiyat,
                    toplam_fiyat = adet * fiyat, # Doğrudan hesapla
                    renk         = u_data.get('renk', ''),
                    beden        = u_data.get('beden', ''),
                ))
                hesaplanan_toplam_tutar += adet * fiyat
            sip.toplam_tutar = hesaplanan_toplam_tutar
        elif 'toplam_tutar' in data and 'urunler' not in data : # Sadece toplam tutar güncelleniyorsa
            try:
                sip.toplam_tutar = float(data.get('toplam_tutar') or 0.0)
            except (ValueError, TypeError):
                logger.warning(f"Sipariş {siparis_no} için 'toplam_tutar' güncellenirken format hatası: {data.get('toplam_tutar')}")

        db.session.commit()
        return jsonify(success=True, message='Sipariş güncellendi')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Sipariş güncellenirken hata (siparis_no: {siparis_no}): {e}")
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return jsonify(success=False, message=f'Sunucu hatası: {str(e)}'), 500


# ------------------------------------------------------------- #
#  SİPARİŞ SİL
# ------------------------------------------------------------- #
@siparisler_bp.route('/siparis-sil/<siparis_no>', methods=['DELETE'])
def siparis_sil(siparis_no):
    logger.info(f"Sipariş silme isteği. Sipariş No: {siparis_no}")
    try:
        sip = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
        if not sip:
            return jsonify(success=False, message='Sipariş bulunamadı'), 404

        SiparisUrun.query.filter_by(siparis_id=sip.id).delete() # İlişkili ürünleri sil
        db.session.delete(sip) # Siparişi sil
        db.session.commit()
        return jsonify(success=True, message='Sipariş silindi')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Sipariş silinirken hata (siparis_no: {siparis_no}): {e}")
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return jsonify(success=False, message=f'Sunucu hatası: {str(e)}'), 500


# ------------------------------------------------------------- #
#  TOPLU SİPARİŞ SİL
# ------------------------------------------------------------- #
@siparisler_bp.route('/siparis-toplu-sil', methods=['POST'])
def siparis_toplu_sil():
    logger.info("Toplu sipariş silme isteği alındı")
    try:
        data = request.get_json()
        siparis_nolar = data.get('siparis_nolar', [])
        
        if not siparis_nolar or not isinstance(siparis_nolar, list):
            return jsonify(success=False, message='Geçersiz sipariş listesi'), 400

        silinen_sayisi = 0
        for siparis_no in siparis_nolar:
            sip = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
            if sip:
                SiparisUrun.query.filter_by(siparis_id=sip.id).delete()
                db.session.delete(sip)
                silinen_sayisi += 1

        db.session.commit()
        logger.info(f"{silinen_sayisi} adet sipariş toplu olarak silindi")
        return jsonify(success=True, message=f'{silinen_sayisi} sipariş silindi', deleted_count=silinen_sayisi)

    except Exception as e:
        db.session.rollback()
        logger.error(f"Toplu sipariş silinirken hata: {e}")
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return jsonify(success=False, message=f'Sunucu hatası: {str(e)}'), 500


# ------------------------------------------------------------- #
#  SİPARİŞ DURUMU GÜNCELLE
# ------------------------------------------------------------- #
@siparisler_bp.route('/siparis-durum-guncelle/<siparis_no>', methods=['POST'])
def siparis_durum_guncelle(siparis_no):
    logger.info(f"Sipariş durum güncelleme isteği. Sipariş No: {siparis_no}")
    try:
        data = request.get_json()
        yeni_durum = data.get('durum')
        
        if not yeni_durum:
            return jsonify(success=False, message='Yeni durum belirtilmedi'), 400

        sip = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
        if not sip:
            return jsonify(success=False, message='Sipariş bulunamadı'), 404

        sip.durum = yeni_durum
        db.session.commit()
        
        logger.info(f"Sipariş {siparis_no} durumu '{yeni_durum}' olarak güncellendi")
        return jsonify(success=True, message='Sipariş durumu güncellendi', new_status=yeni_durum)

    except Exception as e:
        db.session.rollback()
        logger.error(f"Sipariş durumu güncellenirken hata (siparis_no: {siparis_no}): {e}")
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return jsonify(success=False, message=f'Sunucu hatası: {str(e)}'), 500


# ------------------------------------------------------------- #
#  KARGO ETİKETİ YAZDIR
# ------------------------------------------------------------- #
@siparisler_bp.route('/siparis-kargo-etiketi/<siparis_no>')
def siparis_kargo_etiketi(siparis_no):
    logger.info(f"Kargo etiketi yazdırma isteği. Sipariş No: {siparis_no}")
    try:
        sip = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
        if not sip:
            return "Sipariş bulunamadı", 404

        # Ürün bilgilerini al
        urunler = SiparisUrun.query.filter_by(siparis_id=sip.id).all()
        
        # Her ürün için model bilgilerini ekle
        for urun in urunler:
            if hasattr(urun, 'urun_barkod') and urun.urun_barkod:
                try:
                    product = Product.query.filter_by(barcode=urun.urun_barkod).first()
                    if product:
                        urun.product_main_id = getattr(product, 'product_main_id', '')
                    else:
                        urun.product_main_id = ''
                except Exception as e:
                    logger.warning(f"Ürün {urun.urun_barkod} için Product bilgisi alınırken hata: {e}")
                    urun.product_main_id = ''

        return render_template('kargo_etiketi.html', siparis=sip, urunler=urunler)

    except Exception as e:
        logger.error(f"Kargo etiketi oluşturulurken hata (siparis_no: {siparis_no}): {e}")
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return "Bir hata oluştu, lütfen logları kontrol edin.", 500