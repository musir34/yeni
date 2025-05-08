# stock_management.py

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
# Product modelini import et
from models import db, Product
import json
import logging

# Trendyol stok güncelleme fonksiyonunu kullanacağız
# get_products.py dosyasından Trendyol API bilgileri ve request kütüphanesini kullanıyoruz
import base64
import requests
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL

logger = logging.getLogger(__name__)
# Log seviyesini DEBUG yapalım ki detaylı bilgileri görelim
logger.setLevel(logging.DEBUG)

# Eğer handler ekli değilse ekleyelim (tekrar eklememek için kontrol edelim)
if not logger.handlers:
    handler = logging.StreamHandler() # Konsola yazması için StreamHandler kullanabiliriz
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


stock_management_bp = Blueprint('stock_management', __name__)

def update_trendyol_stock(barcode, quantity):
    """
    Trendyol API üzerinden tek bir ürünün stoğunu günceller.
    Trendyol'un /products/price-and-inventory endpoint'ini kullanır.
    """
    # DÜZELTİLEN ENDPOINT: /products/price-and-inventory kullanıyoruz
    url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/products/price-and-inventory"
    credentials = f"{API_KEY}:{API_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/json"
    }

    # Payload formatı (tek ürün için bile items listesi içinde)
    payload = {
        "items": [
            {
                "barcode": barcode,
                "quantity": quantity
                # Eğer bu endpoint price ve listPrice da bekliyorsa
                # ve bu bilgilere ihtiyacımız varsa product modelinden çekip eklemeliyiz.
                # product = Product.query.filter_by(barcode=barcode).first() # Bu ürün DB'de bulunmalı
                # if product:
                #     payload["items"][0]["salePrice"] = float(product.sale_price or 0)
                #     payload["items"][0]["listPrice"] = float(product.list_price or 0)
            }
        ]
    }

    logger.debug(f"Trendyol API'ye gönderilen payload: {json.dumps(payload)}")

    try:
        # Synchronous POST isteği Trendyol'a gönderilir
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)

        # Trendyol API'den başarılı yanıt (genellikle 200 OK) beklenir.
        # Trendyol'un API dokümantasyonuna göre 200 veya 202 dönebilir.
        # response_data = response.json() # Hata durumunda yanıtı loglamak için kalsın

        if response.status_code in [200, 202]: # 202 Accepted da dönebilir
            logger.info(f"Trendyol'a stok güncelleme isteği gönderildi: Barkod {barcode}, Miktar {quantity}. Yanıt Status: {response.status_code}")
            # Trendyol'un yanıtında bir hata listesi var mı kontrol edilebilir.
            # response_data = response.json()
            # if response_data.get('errors'):
            #     logger.error(f"Trendyol yanıtında hatalar var: {response_data.get('errors')}")
            #     return False # Hatalar varsa başarısız say
            return True
        else:
            logger.error(f"Trendyol'a stok güncelleme başarısız oldu: Barkod {barcode}, Miktar {quantity}. Status: {response.status_code}, Yanıt: {response.text}")
            # Hata durumında False döndür
            return False

    except requests.exceptions.RequestException as e:
        # Ağ hataları, timeout vb. yakala
        logger.error(f"Trendyol stok güncelleme sırasında ağ hatası: Barkod {barcode}, Hata: {e}")
        return False
    except Exception as e:
        # Diğer beklenmedik hatalar
        logger.error(f"Trendyol stok güncelleme sırasında beklenmedik hata: Barkod {barcode}, Hata: {e}")
        return False


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
        product = Product.query.filter(db.func.lower(Product.barcode) == barcode.lower()).first()

        if product:
            # Ürün bulunduğunda bilgileri JSON olarak döndür
            logger.debug(f"Ürün bulundu: Barkod {barcode}")
            return jsonify(
                success=True,
                product={
                    'barcode': product.barcode,
                    'product_main_id': product.product_main_id,
                    'color': product.color,
                    'size': product.size,
                    'image_url': product.images # models.py'deki 'images' kolonu resim yolunu tutuyor varsayılıyor
                }
            )
        else:
            # Ürün bulunamazsa hata döndür
            logger.warning(f"Ürün bulunamadı: Barkod {barcode}")
            return jsonify(success=False, message="Ürün bulunamadı"), 404

    except Exception as e:
        # Veritabanı sorgusu sırasında hata oluşursa
        logger.error(f"Veritabanından ürün bilgisi çekilirken hata: {e}", exc_info=True)
        return jsonify(success=False, message=f"Sunucu hatası: {str(e)}"), 500


@stock_management_bp.route('/stock-addition', methods=['POST'])
def handle_stock_update():
    """
    Frontend'den gelen barkod ve güncelleme tipi bilgisiyle stoğu günceller.
    """
    # JSON formatında veri bekleniyor
    data = request.get_json()

    if not data:
        return jsonify(success=False, message="Geçersiz veri formatı"), 400

    barcode_counts = data.get('barcodeCounts') # Gruplanmış barkodlar ve adetleri (ve artık ürün detayları)
    update_type = data.get('updateType')       # 'renew' veya 'add'

    if not barcode_counts or not update_type:
        return jsonify(success=False, message="Eksik veri: barkodlar veya güncelleme tipi belirtilmemiş"), 400

    logger.info(f"Stok güncelleme isteği alındı. Tip: {update_type}, İşlenecek Barkodlar: {list(barcode_counts.keys())}")

    updated_count = 0
    errors = {} # Veritabanı güncelleme sırasında oluşan hatalar (ürün bulunamaması vb.)
    trendyol_update_errors = {} # Trendyol API güncelleme sırasında oluşan hatalar
    items_to_update_trendyol = [] # Trendyol'a gönderilecek ürün listesi

    # Veritabanı işlemleri bir try-except bloğu içinde olmalı
    try:
        for barcode, item_data in barcode_counts.items():
            # item_data artık sadece adet değil, ürün detaylarını da içerecek
            # Adet bilgisini item_data.count'tan alıyoruz
            count = item_data.get('count', 0)
            # Ürün detayları item_data.details'ten alınabilir, ama DB'den çekmek daha güncel bilgi sağlar.
            # Bu yüzden yine DB sorgusu yapıyoruz.

            # Ürünü barkoda göre bul
            product = Product.query.filter_by(barcode=barcode).first()

            if not product:
                # Ürün bulunamazsa hata kaydet ve devam et
                errors[barcode] = f"Ürün veritabanında bulunamadı: {barcode}"
                logger.warning(f"Veritabanında ürün bulunamadı: Barkod {barcode}")
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
                errors[barcode] = f"Geçersiz güncelleme tipi: {update_type}"
                logger.error(f"Geçersiz güncelleme tipi: {update_type}")
                continue

            # Yeni stok miktarını Product modeline ata
            product.quantity = new_stock
            # Değişikliği session'a ekle
            db.session.add(product)

            # Trendyol güncellemesi için listeye ekle
            # update_trendyol_stock tek tek gönderdiği için burada her birini topluyoruz
            items_to_update_trendyol.append({"barcode": barcode, "quantity": new_stock})

            updated_count += 1
            logger.debug(f"Veritabanı için hazırlandı: Barkod {barcode}, Yeni Stok: {new_stock}")

        # Tüm değişiklikleri veritabanına kaydet
        db.session.commit()
        logger.info(f"Veritabanı güncellemeleri commit edildi. Güncellenen {updated_count} ürün.")

        # Trendyol API'ye toplu stok güncellemesi gönder
        # update_trendyol_stock tek tek gönderiyor, bu verimli değil.
        # Trendyol'un batch endpoint'ini kullanmak için tüm items_to_update_trendyol listesini
        # tek bir API çağrısı ile göndermeliyiz.
        # Mevcut update_trendyol_stock fonksiyonu tek tek çağrıldığı için aşağıdaki döngüyü kullanıyoruz.
        # Daha sonra bu Trendyol güncelleme kısmı için ayrı bir batch fonksiyonu yazılabilir.
        trendyol_update_success_count = 0


        logger.info(f"Trendyol'a güncellenecek ürün sayısı: {len(items_to_update_trendyol)}")
        for item in items_to_update_trendyol:
            barcode = item['barcode']
            quantity = item['quantity']
            # Trendyol'da stok güncelleme fonksiyonunu çağır (tekil olarak)
            # Bu fonksiyon artık düzeltilmiş endpoint'i kullanıyor.
            if update_trendyol_stock(barcode, quantity):
                 trendyol_update_success_count += 1
                 logger.debug(f"Trendyol güncelleme başarılı: Barkod {barcode}")
            else:
                 # update_trendyol_stock zaten logluyor
                 trendyol_update_errors[barcode] = f"Trendyol güncellemesi başarısız: {barcode}"
                 logger.error(f"Trendyol güncellemesi başarısız oldu: Barkod {barcode}")


        response_message = f"Veritabanında {updated_count} ürün başarıyla güncellendi."
        if trendyol_update_success_count > 0:
             response_message += f" Trendyol'da {trendyol_update_success_count} ürün stoğu güncellendi."
        if trendyol_update_errors:
             response_message += f" Trendyol'da bazı ürünler güncellenemedi: {list(trendyol_update_errors.keys())}"
             logger.error(f"Trendyol'da güncellenemeyen barkodlar: {list(trendyol_update_errors.keys())}")


        # Başarılı yanıt döndür
        return jsonify(
            success=True,
            message=response_message,
            updatedCount=updated_count,
            errors=errors, # DB'de bulunamayan ürünler vb.
            trendyolUpdateErrors=trendyol_update_errors # Trendyol'da güncellenemeyenler
        )

    except Exception as e:
        # Veritabanı işlemleri sırasında bir hata oluşursa rollback yap
        db.session.rollback()
        logger.error(f"Stok güncelleme sırasında genel hata: {e}", exc_info=True)
        # Hata yanıtı döndür
        return jsonify(success=False, message=f"Stok güncelleme sırasında bir hata oluştu: {str(e)}", errors=errors), 500