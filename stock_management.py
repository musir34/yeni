# stock_management.py

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
# Product modelini import et
from models import db, Product
import json
import logging

# Trendyol stok güncelleme fonksiyonunu kullanacağız
# get_products.py dosyasından Trendyol API bilgileri ve request kütüphanesini kullanıyoruz
# Not: API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL gibi bilgiler trendyol_api.py dosyasında olmalı
import base64
import requests
try:
    from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL
    # Trendyol API bilgileri yüklendiğinde logla
    logger = logging.getLogger(__name__)
    logger.info("Trendyol API bilgileri başarıyla yüklendi.")
except ImportError:
    # trendyol_api.py bulunamazsa veya içinde bilgiler eksikse hata ver
    logger = logging.getLogger(__name__)
    logger.error("trendyol_api.py dosyası bulunamadı veya Trendyol API bilgileri (API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL) eksik.")
    # Eksik bilgileri tutacak placeholder değişkenler tanımla
    API_KEY = None
    API_SECRET = None
    SUPPLIER_ID = None
    BASE_URL = "https://api.trendyol.com/sapigw/" # Base URL'i yine de tanımlayalım


# Log ayarları (Zaten vardı, tekrar kontrol edelim)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.StreamHandler() # Konsola yazması için StreamHandler kullanabiliriz
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


stock_management_bp = Blueprint('stock_management', __name__)

# Eski update_trendyol_stock fonksiyonunu toplu gönderecek şekilde güncelliyoruz/yerine yenisini yazıyoruz
def send_trendyol_stock_update_batch(items_list):
    """
    Trendyol API üzerinden birden fazla ürünün stoğunu toplu olarak günceller.
    Trendyol'un /products/price-and-inventory endpoint'ini kullanır.

    items_list: [{"barcode": "BARKOD1", "quantity": 10}, {"barcode": "BARKOD2", "quantity": 5}, ...] formatında liste
    """
    if not API_KEY or not API_SECRET or not SUPPLIER_ID:
        logger.error("Trendyol API bilgileri eksik. Stok Trendyol'da güncellenemez.")
        return False, 0, {"general": "Trendyol API bilgileri sunucuda eksik."} # Genel hata döndür

    if not items_list:
        logger.info("Trendyol'a gönderilecek ürün listesi boş.")
        return True, 0, {} # Boş liste göndermek başarı sayılır ama güncellenen 0 olur

    url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/products/price-and-inventory"
    credentials = f"{API_KEY}:{API_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/json",
        "User-Agent": f"GulluAyakkabiApp - Supplier {SUPPLIER_ID}" # İyi pratik: API çağrılarında User-Agent göndermek
    }

    # Payload formatı (items listesi içinde toplu ürünler)
    payload = {
        "items": items_list
    }

    logger.debug(f"Trendyol API'ye gönderilen toplu payload: {json.dumps(payload)[:500]}...") # Payload'ın ilk 500 karakterini logla

    try:
        # Synchronous POST isteği Trendyol'a gönderilir (Tek istek!)
        # Timeout süresini biraz daha uzun tutabiliriz toplu gönderimlerde
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60) # Timeout'ı 60 sn'ye çıkardık

        # Trendyol API'den başarılı yanıt (genellikle 200 OK veya 202 Accepted) beklenir.
        # Trendyol'un batch yanıtı genellikle içinde hatalar barındıran bir 200/202 döner.
        response_data = response.json() if response.content else {} # Yanıt içeriği varsa JSON parse et

        if response.status_code in [200, 202]: # Başarılı veya Kabul Edildi
            logger.info(f"Trendyol'a toplu stok güncelleme isteği gönderildi. Yanıt Status: {response.status_code}")

            # Trendyol'un yanıt formatına göre başarıları ve hataları ayrıştır
            # Trendyol API dokümantasyonuna bakarak burayı daha kesin hale getirebiliriz.
            # Genellikle 'errors', 'failures', 'errorMessage' gibi alanlar dönebilir.
            # Basitçe, Trendyol'un döndürdüğü bir hata listesi var mı bakalım:
            trendyol_errors = response_data.get('errors', []) + response_data.get('failures', []) # Trendyol'un döndürdüğü hatalar
            overall_success = not bool(trendyol_errors) # Eğer Trendyol hata dönmediyse genel olarak başarılı say

            error_details = {}
            if trendyol_errors:
                 logger.error(f"Trendyol toplu güncelleme yanıtında hatalar var: {trendyol_errors}")
                 # Hata detaylarını frontenda göndermek için düzenleyelim
                 for err in trendyol_errors:
                     # Trendyol'un hata objesi farklı olabilir, barkodu bulmaya çalışalım
                     barcode_in_error = err.get('barcode', 'Bilinmeyen Barkod') # Hata objesi içinde barkod var mı bak
                     error_details[barcode_in_error] = err.get('message', 'Bilinmeyen Hata') # Varsa hata mesajını al

            # response_data içinde kaç ürünün başarılı güncellendiğine dair bilgi olabilir mi?
            # Trendyol dokümantasyonu lazım. Şimdilik, gönderilen toplam ürün sayısı eksi hatalı sayısı başarı sayılabilir.
            success_count = len(items_list) - len(trendyol_errors) if not trendyol_errors else 0 # Basit bir tahmin

            return overall_success, success_count, error_details

        else:
            # Başarısız HTTP status code döndü
            logger.error(f"Trendyol'a toplu stok güncelleme başarısız oldu. Status: {response.status_code}, Yanıt: {response.text}")
            return False, 0, {"general": f"Trendyol API hatası: Status {response.status_code}, Yanıt: {response.text[:200]}..."} # Genel hata

    except requests.exceptions.Timeout:
        logger.error(f"Trendyol toplu stok güncelleme sırasında zaman aşımı: {len(items_list)} ürün.")
        return False, 0, {"general": "Trendyol API'den yanıt alınırken zaman aşımı oluştu."}
    except requests.exceptions.RequestException as e:
        # Ağ hataları vb.
        logger.error(f"Trendyol toplu stok güncelleme sırasında ağ hatası: Hata: {e}")
        return False, 0, {"general": f"Trendyol API isteği sırasında ağ hatası: {str(e)}"}
    except json.JSONDecodeError:
         logger.error(f"Trendyol yanıtı JSON formatında değil: {response.text[:200]}...")
         return False, 0, {"general": "Trendyol API'den geçersiz yanıt formatı alındı."}
    except Exception as e:
        # Diğer beklenmedik hatalar
        logger.error(f"Trendyol toplu stok güncelleme sırasında beklenmedik hata: Hata: {e}", exc_info=True)
        return False, 0, {"general": f"Trendyol API güncelleme sırasında beklenmedik bir hata oluştu: {str(e)}"}


@stock_management_bp.route('/stock-addition', methods=['GET'])
def stock_addition_screen():
    """
    Stok ekleme ekranını render eder.
    """
    # HTML şablonunu render et
    return render_template('stock_addition.html')

# Yeni API endpoint'i: Barkoda göre ürün bilgisi döndürür
@stock_management_bp.route('/api/get-product-details-by-barcode/<barcode>', methods=['GET'])
def get_product_details_by_barcode(barcode):
    """
    Veritabanından barkoda göre ürün bilgilerini döndürür.
    """
    logger.debug(f"Ürün detayları isteği alındı: Barkod {barcode}")
    try:
        # Product modelinden barkoda göre ürünü bul
        # Büyük/küçük harf duyarlılığı olmaması için lower() kullanabiliriz
        # Trendyol bazen barkodları farklı kaydedebiliyor, her ihtimale karşı hem büyük hem küçük harfle arayalım
        # veya kaydederken hep büyük/küçük harfe çevirelim. Şimdilik ararken lower() yeterli.
        product = Product.query.filter(db.func.lower(Product.barcode) == barcode.lower()).first()

        if product:
            # Ürün bulunduğunda bilgileri JSON olarak döndür
            logger.debug(f"Ürün bulundu: Barkod {barcode}")
            # images kolonu bir JSON string olabilir, onu listeye çevirelim eğer öyleyse
            image_urls = []
            if product.images:
                try:
                    # images kolonunun JSON listesi formatında olduğunu varsayalım
                    # Örnek: '["url1", "url2"]'
                    image_data = json.loads(product.images)
                    if isinstance(image_data, list):
                         image_urls = image_data
                    elif isinstance(image_data, str): # Belki tek bir URL string olarak kaydedilmiştir
                         image_urls = [image_data]
                except json.JSONDecodeError:
                    # JSON formatında değilse, belki sadece tek bir URL stringidir
                    image_urls = [product.images]
                except TypeError:
                     # images None veya beklenmedik tipte ise
                     image_urls = []

            # İlk resmi gönderiyoruz frontende
            first_image_url = image_urls[0] if image_urls else 'https://placehold.co/50x50'


            return jsonify(
                success=True,
                product={
                    'barcode': product.barcode,
                    'product_main_id': product.product_main_id, # model kodu gibi
                    'color': product.color,
                    'size': product.size,
                    'image_url': first_image_url # Frontend için ilk resim
                    # 'all_image_urls': image_urls # Eğer tüm resimler lazımsa bu da gönderilebilir
                }
            )
        else:
            # Ürün bulunamazsa hata döndür
            logger.warning(f"Ürün bulunamadı: Barkod {barcode}")
            return jsonify(success=False, message="Ürün veritabanında bulunamadı."), 404 # 404 Not Found uygun

    except Exception as e:
        # Veritabanı sorgusu sırasında hata oluşursa
        logger.error(f"Veritabanından ürün bilgisi çekilirken hata: {e}", exc_info=True)
        return jsonify(success=False, message=f"Ürün bilgisi çekilirken sunucu hatası: {str(e)}"), 500 # 500 Internal Server Error

@stock_management_bp.route('/stock-addition', methods=['POST'])
def handle_stock_update():
    """
    Frontend'den gelen barkod ve güncelleme tipi bilgisiyle stoğu günceller.
    Veritabanını güncelledikten sonra Trendyol'a toplu güncelleme isteği gönderir.
    """
    # JSON formatında veri bekleniyor
    data = request.get_json()

    if not data:
        return jsonify(success=False, message="Geçersiz veri formatı"), 400

    # Frontend'den gelen yapı: {"barkod1": {"count": 5, "details": {...}}, "barkod2": {"count": 3, "details": {...}}, ...}
    # Bizim için önemli olan barkod ve count bilgisi
    barcode_counts_data = data.get('barcodeCounts')
    update_type = data.get('updateType')# 'renew' veya 'add'

    if not barcode_counts_data or not update_type:
        return jsonify(success=False, message="Eksik veri: Barkodlar veya güncelleme tipi belirtilmemiş"), 400

    logger.info(f"Stok güncelleme isteği alındı. Tip: {update_type}, İşlenecek Barkod Sayısı: {len(barcode_counts_data)}")

    updated_db_count = 0 # Veritabanında güncellenen ürün sayısı
    db_errors = {} # Veritabanı güncelleme sırasında oluşan hatalar (ürün bulunamaması vb.)
    items_to_update_trendyol = [] # Trendyol'a gönderilecek ürün listesi (toplu)

    # Veritabanı işlemleri ve Trendyol listesini hazırlama
    try:
        for barcode, item_data in barcode_counts_data.items():
            count = item_data.get('count', 0)

            # Ürünü barkoda göre bul
            # Tekrar DB sorgusu yapmak güncel bilgi sağlar
            product = Product.query.filter(db.func.lower(Product.barcode) == barcode.lower()).first()

            if not product:
                db_errors[barcode] = f"Ürün veritabanında bulunamadı: {barcode}"
                logger.warning(f"Veritabanında ürün bulunamadı, atlanıyor: Barkod {barcode}")
                continue

            # Mevcut stok miktarını al (None ise 0 say)
            current_stock = product.quantity if product.quantity is not None else 0

            # Güncelleme tipine göre yeni stok miktarını hesapla
            if update_type == 'renew':
                # Mevcut stoğu sıfırla ve yeni adeti ekle
                new_stock = count
                logger.debug(f"Stok yenileme: Barkod {barcode}, Eski Stok: {current_stock}, Yeni Stok: {new_stock}")
            elif update_type == 'add':
                # Mevcut stoğun üzerine ekle
                new_stock = current_stock + count
                logger.debug(f"Stok ekleme: Barkod {barcode}, Eski Stok: {current_stock}, Eklenecek: {count}, Yeni Stok: {new_stock}")
            else:
                # Geçersiz güncelleme tipi (frontend'de önlenmeli ama backend'de de kontrol iyi olur)
                db_errors[barcode] = f"Geçersiz güncelleme tipi: {update_type} (Barkod: {barcode})"
                logger.error(f"Geçersiz güncelleme tipi alındı: {update_type}")
                continue # Bu ürünü atla

            # Yeni stok miktarını Product modeline ata
            product.quantity = new_stock
            # Değişikliği session'a ekle
            db.session.add(product)

            # Trendyol güncellemesi için listeye ekle (Yeni stok miktarı ile)
            items_to_update_trendyol.append({"barcode": product.barcode, "quantity": new_stock}) # DB'den gelen barcode'u kullanmak daha güvenli olabilir

            updated_db_count += 1
            logger.debug(f"Veritabanı için hazırlandı ve Trendyol listesine eklendi: Barkod {barcode}, Yeni Stok: {new_stock}")

        # Tüm veritabanı değişikliklerini kaydet (Tek commit!)
        db.session.commit()
        logger.info(f"Veritabanı güncellemeleri başarıyla commit edildi. Güncellenen {updated_db_count} ürün.")

    except Exception as e:
        # Veritabanı işlemleri sırasında bir hata oluşursa rollback yap
        db.session.rollback()
        logger.error(f"Veritabanı işlemleri sırasında hata: {e}", exc_info=True)
        # Hata yanıtı döndür (Trendyol güncellemesi yapılmadı)
        return jsonify(
            success=False,
            message=f"Veritabanı güncellemesi sırasında bir hata oluştu: {str(e)}",
            errors=db_errors, # DB hatalarını da gönder
            trendyolUpdateErrors={} # Trendyol hatası oluşmadı
        ), 500 # Internal Server Error


    # --- Trendyol API'ye toplu stok güncellemesi gönderme ---
    trendyol_update_success = False
    trendyol_successful_count = 0
    trendyol_update_errors = {}

    if items_to_update_trendyol:
        logger.info(f"Trendyol'a toplu güncellenecek ürün sayısı: {len(items_to_update_trendyol)}")
        # Trendyol'a toplu güncelleme fonksiyonunu çağır (Tek çağrı!)
        trendyol_update_success, trendyol_successful_count, trendyol_update_errors = send_trendyol_stock_update_batch(items_to_update_trendyol)
    else:
         logger.info("Trendyol'a gönderilecek ürün listesi boş, Trendyol güncellemesi atlanıyor.")
         trendyol_update_success = True # Yapacak bir şey yoksa başarı sayabiliriz

    # Sonuç mesajını oluştur
    response_message = f"Veritabanında {updated_db_count} ürün güncellendi."

    if items_to_update_trendyol: # Trendyol güncellemesi denenmişse
        if trendyol_update_success:
             response_message += f" Trendyol'da {trendyol_successful_count} ürün stoğu topluca güncellendi."
             if trendyol_update_errors:
                 response_message += f" Ancak Trendyol yanıtında bazı hatalar bildirildi: {list(trendyol_update_errors.keys())}"
        else: # Genel Trendyol API çağrısı başarısız olduysa
            response_message += f" Trendyol stok güncellemesi başarısız oldu. Hata: {trendyol_update_errors.get('general', 'Bilinmeyen Trendyol hatası.')}"
            if len(trendyol_update_errors) > 1: # Genel hata mesajı dışında başka spesifik hatalar da varsa
                 response_message += f" Detaylı hatalar için loglara bakın veya hata listesini kontrol edin."

    # Başarılı yanıt döndür (Genel işlem başarılı sayılır eğer DB güncellendiyse ve Trendyol çağrısı yapıldıysa)
    # Trendyol'da kısmi hatalar olsa bile DB güncellendiği için success=True dönebiliriz.
    # Frontend bu hataları kullanıcıya gösterebilir.
    overall_success_status = updated_db_count > 0 # En az 1 ürün DB'de güncellendiyse başarılı say

    # Trendyol'da hiç ürün güncellenemedi ve genel bir Trendyol hatası varsa, genel success false olabilir.
    if not trendyol_update_success and items_to_update_trendyol:
         overall_success_status = False
         # Trendyol API bilgisi eksikse de false döndürelim
         if "Trendyol API bilgileri sunucuda eksik" in trendyol_update_errors.get("general", ""):
              overall_success_status = False


    return jsonify(
        success=overall_success_status,
        message=response_message,
        updatedDbCount=updated_db_count,
        errors=db_errors, # DB'de bulunamayan ürünler vb.
        trendyolUpdateErrors=trendyol_update_errors # Trendyol'da güncellenemeyenler veya API çağrısı hatası
    ), 200 # Başarılı yanıt kodu

# Not: trendyol_api.py dosyasını ve içindeki API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL bilgilerini doğru girdiğinden emin ol.
# Ayrıca models.py dosyasında Product modelinin 'barcode', 'quantity', 'product_main_id', 'color', 'size', 'images'
# kolonlarının tanımlı olduğundan emin ol. 'images' kolonu URL veya URL listesi tutmalı.