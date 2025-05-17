import asyncio
import aiohttp
import os
import base64
import json
import logging
import threading
import qrcode
from datetime import datetime
from urllib.parse import urlparse
from dotenv import load_dotenv
from io import BytesIO
from sqlalchemy import case
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, send_file, current_app
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import insert
# or_ operatörüne gerek kalmadı, func yeterli. İstersen import'u silebilirsin.
from sqlalchemy import func
from trendyol_api import API_KEY, SUPPLIER_ID, API_SECRET, BASE_URL
from login_logout import roles_required

from models import db, Product, ProductArchive
from cache_config import cache, CACHE_TIMES

get_products_bp = Blueprint('get_products', __name__)

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('get_products.log')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


#-------------------------------------------------------------------
# HAREM DÖVİZ'DEN KUR ÇEKME (ÖRNEK)
# Gerçek bir endpoint olarak "https://kur.haremaltin.com/today.json"
# üzerinden USD kuru çekiyoruz. (JSON verisi, "USD" alanı vb.)
#-------------------------------------------------------------------

async def fetch_usd_rate():
    try:
        # Merkez Bankası veya açık API servislerine bağlanma
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    # Bu API'de TRY değeri rates altında yer alır
                    try:
                        # USD/TRY kuru (1 USD kaç TL)
                        return float(data.get('rates', {}).get('TRY', 0))
                    except (ValueError, TypeError) as e:
                        logger.error(f"Kur değeri dönüştürme hatası: {e}")
                        return 34.0  # Varsayılan değer
                else:
                    logger.error(f"Döviz API hatası: {response.status} {await response.text()}")
                    return 34.0  # Hata durumunda varsayılan değer
    except Exception as e:
        logger.error(f"fetch_usd_rate hata: {e}")
        # Yedek değer döndür
        return 34.0


def update_all_cost_try(usd_rate):
    if not usd_rate:
        logger.error("Geçersiz usd_rate, güncelleme yapılamadı.")
        return
    products = Product.query.all()
    for p in products:
        if p.cost_usd is not None:
            p.cost_try = p.cost_usd * usd_rate
            db.session.add(p)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"update_all_cost_try hata: {e}")


async def _update_exchange_rates():
    rate = await fetch_usd_rate()
    if rate:
        update_all_cost_try(rate)


@get_products_bp.route('/update_exchange_rates_manually')
def update_exchange_rates_manually():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_update_exchange_rates())
        loop.close()
        flash("Döviz kurları başarıyla güncellendi.", "success")
    except Exception as e:
        logger.error(f"update_exchange_rates_manually hata: {e}")
        flash("Döviz kurları güncellenirken hata oluştu.", "danger")
    return redirect(url_for('get_products.product_list'))


@get_products_bp.route('/generate_qr')
def generate_qr():
    barcode = request.args.get('barcode', '').strip()
    if not barcode:
        return jsonify({'success': False, 'message': 'Barkod eksik!'})
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(barcode)
    qr.make(fit=True)
    qr_dir = os.path.join(current_app.root_path, 'static', 'qr_codes')
    os.makedirs(qr_dir, exist_ok=True)
    qr_path = os.path.join(qr_dir, f"{barcode}.png")
    qr.make_image(fill_color="black", back_color="white").save(qr_path)
    return jsonify({'success': True, 'qr_code_path': f"/static/qr_codes/{barcode}.png"})


def group_products_by_model_and_color(products):
    grouped_products = {}
    for product in products:
        key = (product.product_main_id or '', product.color or '')
        grouped_products.setdefault(key, []).append(product)
    return grouped_products


def sort_variants_by_size(product_group):
    try:
        return sorted(product_group, key=lambda x: float(x.size), reverse=True)
    except (ValueError, TypeError):
        return sorted(product_group, key=lambda x: x.size, reverse=True)


def render_product_list(products, pagination=None):
    grouped_products = group_products_by_model_and_color(products)
    for key in grouped_products:
        grouped_products[key] = sort_variants_by_size(grouped_products[key])
    return render_template('product_list.html', grouped_products=grouped_products, pagination=pagination, search_mode=False)


@get_products_bp.route('/update_products', methods=['POST'])
async def update_products_route():
    try:
        logger.debug("update_products_route fonksiyonu çağrıldı.")
        products = await fetch_all_products_async()

        if not isinstance(products, list):
            logger.error(f"Beklenmeyen veri türü: {type(products)} - İçerik: {products}")
            raise ValueError("Beklenen liste değil.")

        logger.debug(f"Çekilen ürün sayısı: {len(products)}")

        if products:
            logger.debug("Ürünler veritabanına kaydediliyor...")
            await save_products_to_db_async(products)
            flash('Ürünler başarıyla güncellendi.', 'success')
            logger.info("Ürünler başarıyla güncellendi.")
        else:
            logger.warning("Ürünler bulunamadı veya güncelleme sırasında bir hata oluştu.")
            flash('Ürünler bulunamadı veya güncelleme sırasında bir hata oluştu.', 'danger')

    except Exception as e:
        logger.error(f"update_products_route hata: {e}")
        flash('Ürünler güncellenirken bir hata oluştu.', 'danger')

    return redirect(url_for('get_products.product_list'))


@get_products_bp.route('/update_stocks_route', methods=['POST'])
async def update_stocks_route(): # Bu fonksiyon Trendyol'daki STOK bilgilerini çekip DB'deki stokları günceller
    logger.info("Trendyol'dan stokları çekme ve veritabanını güncelleme işlemi başlatıldı.")

    # trendyol_api.py bilgileri kontrolü
    if not API_KEY or not API_SECRET or not SUPPLIER_ID:
         msg = "Trendyol API bilgileri sunucuda eksik. Stoklar Trendyol'dan çekilemez."
         logger.error(msg)
         # Bu endpoint frontend'e JSON dönüyor, flash değil
         return jsonify({'success': False, 'message': msg})


    try:
        # 1. Trendyol'dan TÜM ürünleri çek (quantity bilgisi de gelir)
        # fetch_all_products_async zaten Trendyol'un ürün listeleme endpoint'ini kullanır
        # ve her ürünün güncel quantity bilgisini içerir.
        trendyol_products = await fetch_all_products_async()

        if not trendyol_products:
            logger.warning("Trendyol'dan ürün çekilemedi. Stok güncellenemiyor.")
            return jsonify({'success': False, 'message': 'Trendyol\'dan güncel ürün (stok) bilgisi çekilemedi.'})

        # 2. Trendyol verisinden barkod -> miktar eşleşmesini oluştur
        # Sadece geçerli barkodu olanları al
        barcode_quantity_map = {
            p.get('barcode'): int(p.get('quantity', 0)) # quantity'yi int yapalım
            for p in trendyol_products
            if p.get('barcode') # Barkod var mı kontrol et
        }

        if not barcode_quantity_map:
            logger.info("Trendyol'dan güncellenecek geçerli stok bilgisi (barkod/miktar) alınamadı.")
            return jsonify({'success': False, 'message': 'Trendyol\'dan güncellenecek stok bilgisi alınamadı (Geçerli barkod bulunamadı).'})

        # 3. Kendi veritabanındaki ilgili ürünleri çek (BURASI BATCH YAPILDI)
        all_trendyol_barcodes = list(barcode_quantity_map.keys())
        logger.debug(f"Trendyol'dan çekilen ve DB'de aranacak toplam barkod sayısı: {len(all_trendyol_barcodes)}")

        batch_size = 1000 # Veritabanı sorguları için batch boyutu (Bu değeri DB limitine göre ayarlayabilirsin, 1000 genelde güvenlidir)
        local_products_to_update = [] # Güncellenecek yerel ürünleri burada toplayacağız

        # Barkod listesini batch'lere böl ve her batch için DB'den çek
        for i in range(0, len(all_trendyol_barcodes), batch_size):
            barcode_batch = all_trendyol_barcodes[i : i + batch_size]
            logger.debug(f"DB'den ürünler çekiliyor: Batch {i//batch_size + 1} / { (len(all_trendyol_barcodes) + batch_size - 1) // batch_size } (Barkod aralığı: {barcode_batch[0]} - {barcode_batch[-1] if barcode_batch else 'Boş'})") # Log mesajı iyileştirildi

            # SQLAlchemy sorgusu ile batch'teki barkodlara sahip ürünleri çek
            # .all() burada senkron çalışır, async context içinde olmasına rağmen.
            # Büyük veri setleri için burada performans darboğazı olabilir, ama IN limitini aşar.
            batch_results = Product.query.filter(Product.barcode.in_(barcode_batch)).all()
            local_products_to_update.extend(batch_results) # Batch sonuçlarını ana listeye ekle

        logger.debug(f"Veritabanından Trendyol barkodlarına karşılık gelen toplam ürün sayısı: {len(local_products_to_update)}")


        # 4. Kendi veritabanındaki ürünlerin stoğunu Trendyol verisine göre güncelle
        updated_count = 0
        products_marked_for_update = [] # session.add ile işaretlenen ürünler

        for product in local_products_to_update:
            trendyol_quantity = barcode_quantity_map.get(product.barcode) # Trendyol'daki miktar

            # Trendyol'dan gelen miktarın None veya farklı bir şey olmaması lazım, Trendyol 0 veya pozitif int döner
            # Yine de kontrol ekleyelim
            if trendyol_quantity is not None and isinstance(trendyol_quantity, int):
                 # Sadece miktar gerçekten değişmişse güncelle
                 if product.quantity != trendyol_quantity:
                     logger.debug(f"DB Stoğu Güncelleniyor: Barkod {product.barcode}, Eski: {product.quantity}, Yeni (Trendyol): {trendyol_quantity}")
                     product.quantity = trendyol_quantity
                     db.session.add(product) # Mark as changed
                     products_marked_for_update.append(product) # Commit için listeye ekle
                     updated_count += 1
                 else:
                     logger.debug(f"DB Stoğu Aynı: Barkod {product.barcode}, Miktar: {product.quantity}")
            else:
                 logger.warning(f"Trendyol'dan {product.barcode} barkodu için geçersiz miktar geldi: {trendyol_quantity}. DB güncellenmedi.")
                 # Bu durumda bu ürünün DB'deki stoğunu Trendyol'a göre çekmemiş oluyoruz.

        # 5. Veritabanı değişikliklerini kaydet (Tek commit!)
        if products_marked_for_update:
            try:
                db.session.commit()
                logger.info(f"Trendyol stok bilgisine göre veritabanında {updated_count} ürün stoğu başarıyla güncellendi.")
            except Exception as e:
                 db.session.rollback()
                 logger.error(f"Veritabanına stok güncellenirken commit hatası: {e}", exc_info=True)
                 return jsonify({'success': False, 'message': f'Veritabanına stok güncellenirken hata oluştu: {str(e)}'})
        else:
            logger.info("Veritabanında güncellenecek stok farkı olan ürün bulunamadı.")


        # 6. Başarılı yanıt döndür
        return jsonify({'success': True, 'message': f'Stoklar başarıyla Trendyol\'dan çekildi ve veritabanında güncellendi ({updated_count} ürün güncellendi).'})

    except Exception as e:
        # Süreç sırasında herhangi bir hata oluşursa (fetch_all_products_async hatası vb.)
        db.session.rollback() # Olası yarım kalan DB işlemleri için
        logger.error(f"update_stocks_route (Trendyol Stok Çekme) sırasında genel hata: {e}", exc_info=True)
        # Frontend'e JSON hata yanıtı döndür
        return jsonify({'success': False, 'message': f'Stok güncelleme sırasında bir hata oluştu: {str(e)}'})




async def save_products_to_db_async(products):
    products = [p for p in products if isinstance(p, dict)]
    archived_barcodes = set(x.barcode for x in ProductArchive.query.all())

    images_folder = os.path.join(current_app.root_path, 'static', 'images')
    os.makedirs(images_folder, exist_ok=True)

    image_downloads = []
    product_objects = []
    seen_barcodes = set()

    for product_data in products:
        original_barcode = product_data.get('barcode', '').strip()

        if not original_barcode or original_barcode in seen_barcodes or original_barcode in archived_barcodes:
            continue

        seen_barcodes.add(original_barcode)

        image_urls = [img.get('url', '') for img in product_data.get('images', []) if isinstance(img, dict)]
        image_url = image_urls[0] if image_urls else ''
        if image_url:
            parsed_url = urlparse(image_url)
            image_extension = os.path.splitext(parsed_url.path)[1] or '.jpg'
            image_filename = f"{original_barcode}{image_extension.lower()}"
            image_path = os.path.join(images_folder, image_filename)
            image_downloads.append((image_url, image_path))
            images_path_db = f"/static/images/{image_filename}"
        else:
            images_path_db = ''

        size = next((attr.get('attributeValue', 'N/A') for attr in product_data.get('attributes', []) if attr.get('attributeName') == 'Beden'), 'N/A')
        color = next((attr.get('attributeValue', 'N/A') for attr in product_data.get('attributes', []) if attr.get('attributeName') == 'Renk'), 'N/A')

        reject_reason_str = '; '.join([r.get('reason', 'N/A') for r in product_data.get('rejectReasonDetails', [])])

        product_objects.append({
            "barcode": original_barcode,
            "title": product_data.get('title', 'N/A'),
            "product_main_id": product_data.get('productMainId', 'N/A'),
            "quantity": int(product_data.get('quantity', 0)),
            "images": images_path_db,
            "variants": json.dumps(product_data.get('variants', [])),
            "size": size,
            "color": color,
            "archived": product_data.get('archived', False),
            "locked": product_data.get('locked', False),
            "on_sale": product_data.get('onSale', False),
            "reject_reason": reject_reason_str,
            "sale_price": float(product_data.get('salePrice', 0)),
            "list_price": float(product_data.get('listPrice', 0)),
            "currency_type": product_data.get('currencyType', 'TRY'),
        })

    batch_size = 500
    for i in range(0, len(product_objects), batch_size):
        batch = product_objects[i:i + batch_size]
        insert_stmt = insert(Product).values(batch)
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=['barcode'],
            set_={
                'quantity': insert_stmt.excluded.quantity,
                'sale_price': insert_stmt.excluded.sale_price,
                'list_price': insert_stmt.excluded.list_price,
                'images': insert_stmt.excluded.images,
                'size': insert_stmt.excluded.size,
                'color': insert_stmt.excluded.color,
            }
        )
        db.session.execute(upsert_stmt)
    db.session.commit()

    flash("Ürünler başarıyla veritabanına kaydedildi.", "success")

    image_downloads = check_and_prepare_image_downloads(image_downloads, images_folder)
    if image_downloads:
        threading.Thread(target=background_download_images, args=(image_downloads,)).start()


async def fetch_all_products_async():
    page_size = 1000
    url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/products"
    credentials = f"{API_KEY}:{API_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    headers = {"Authorization": f"Basic {encoded_credentials}"}
    async with aiohttp.ClientSession() as session:
        params = {"page": 0, "size": page_size}
        async with session.get(url, headers=headers, params=params, timeout=30) as response:
            if response.status != 200:
                error_text = await response.text()
                logging.error(f"API Hatası: {response.status} - {error_text}")
                return []
            try:
                data = await response.json()
                logging.debug(f"API Yanıtı: Tür: {type(data)}, İçerik: {data}")
            except Exception as e:
                error_text = await response.text()
                logging.error(f"JSON çözümleme hatası: {e} - Yanıt: {error_text}")
                return []
            total_pages = data.get('totalPages', 1)
            logging.info(f"Toplam sayfa sayısı: {total_pages}")
        tasks = [
            fetch_products_page(session, url, headers, {"page": page_number, "size": page_size})
            for page_number in range(total_pages)
        ]
        pages_data = await asyncio.gather(*tasks)
        all_products = [product for page in pages_data if isinstance(page, list) for product in page]
        logging.info(f"Toplam çekilen ürün sayısı: {len(all_products)}")
        return all_products


async def fetch_products_page(session, url, headers, params):
    try:
        async with session.get(url, headers=headers, params=params, timeout=30) as response:
            if response.status != 200:
                error_text = await response.text()
                logging.error(f"Sayfa çekme hatası: {response.status} - {error_text}")
                return []
            try:
                data = await response.json()
                if not isinstance(data.get('content'), list):
                    logging.error(f"Sayfa verisi content beklenen bir liste değil: {type(data.get('content'))}")
                    return []
                logging.debug(f"Sayfa {params['page']} başarıyla çekildi, içerik boyutu: {len(data['content'])}")
                return data.get('content', [])
            except Exception as e:
                error_text = await response.text()
                logging.error(f"JSON çözümleme hatası: {e} - Yanıt: {error_text}")
                return []
    except Exception as e:
        logging.error(f"fetch_products_page hata: {e}")
        return []


async def download_images_async(image_urls):
    async with aiohttp.ClientSession() as session:
        tasks = []
        semaphore = asyncio.Semaphore(100)
        for image_url, image_path in image_urls:
            tasks.append(download_image(session, image_url, image_path, semaphore))
        await asyncio.gather(*tasks)


async def download_image(session, image_url, image_path, semaphore):
    async with semaphore:
        if os.path.exists(image_path):
            logger.info(f"Resim zaten mevcut, atlanıyor: {image_path}")
            return
        try:
            async with session.get(image_url, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"Resim indirme hatası: {response.status} - {image_url}")
                    return
                content = await response.read()
                with open(image_path, 'wb') as img_file:
                    img_file.write(content)
                logger.info(f"Resim kaydedildi: {image_path}")
        except Exception as e:
            logger.error(f"Resim indirme sırasında hata oluştu ({image_url}): {e}")


def background_download_images(image_downloads):
    asyncio.run(download_images_async(image_downloads))





def check_and_prepare_image_downloads(image_urls, images_folder):
    existing_files = set(os.listdir(images_folder))
    download_list = []
    for image_url, image_path in image_urls:
        image_filename = os.path.basename(image_path)
        if image_filename not in existing_files:
            download_list.append((image_url, image_path))
    return download_list


def upsert_products(products):
    insert_stmt = insert(Product).values(products)
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=['barcode'],
        set_={
            'quantity': insert_stmt.excluded.quantity,
            'sale_price': insert_stmt.excluded.sale_price,
            'list_price': insert_stmt.excluded.list_price,
            'images': insert_stmt.excluded.images,
            'size': insert_stmt.excluded.size,
            'color': insert_stmt.excluded.color,
        }
    )
    db.session.execute(upsert_stmt)
    db.session.commit()


async def update_stock_levels_with_items_async(items):
    if not items:
        logger.error("Güncellenecek ürün bulunamadı.")
        return False
    url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/products/price-and-inventory"
    credentials = f"{API_KEY}:{API_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/json"
    }
    product_dict = {p.barcode: p for p in Product.query.all()}
    logger.info(f"Veritabanındaki ürün sayısı: {len(product_dict)}")
    payload_items = []
    for item in items:
        barcode = item['barcode']
        quantity = item['quantity']
        logger.info(f"İşlenen barkod: {barcode}, miktar: {quantity}")
        product_info = product_dict.get(barcode)
        if product_info:
            try:
                sale_price = float(product_info.sale_price or 0)
                list_price = float(product_info.list_price or 0)
                currency_type = product_info.currency_type or 'TRY'
                payload_item = {"barcode": barcode, "quantity": quantity}
                payload_items.append(payload_item)
            except ValueError as e:
                logger.error(f"Fiyat bilgileri hatalı: {e}")
                continue
        else:
            logger.warning(f"Barkod için ürün bulunamadı: {barcode}")
            continue
    logger.info(f"API'ye gönderilecek ürün sayısı: {len(payload_items)}")
    payload = {"items": payload_items}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=payload, timeout=30) as response:
                if response.status != 200:
                    logger.error(f"HTTP Hatası: {response.status}, Yanıt: {await response.text()}")
                    return False
                data = await response.json()
                logger.info(f"API yanıtı: {data}")
                batch_request_id = data.get('batchRequestId')
                if batch_request_id:
                    logger.info("Ürünler API üzerinden başarıyla güncellendi.")
                    return True
                else:
                    logger.error("Batch Request ID alınamadı.")
                    return False
        except aiohttp.ClientError as e:
            logger.error(f"İstek Hatası: {e}")
            return False


@get_products_bp.route('/fetch-products')
async def fetch_products_route():
    try:
        products = await fetch_all_products_async()
        if products:
            await save_products_to_db_async(products)
            flash('Ürünler başarıyla güncellendi.', 'success')
        else:
            flash('Ürünler bulunamadı veya güncelleme sırasında bir hata oluştu.', 'danger')
    except Exception as e:
        logger.error(f"fetch_products_route hata: {e}")
        flash('Ürünler güncellenirken bir hata oluştu.', 'danger')
    return redirect(url_for('get_products.product_list'))


@get_products_bp.route('/archive_product', methods=['POST'])
def archive_product():
    try:
        product_main_id = request.form.get('product_main_id')
        if not product_main_id:
            return jsonify({'success': False, 'message': 'Model kodu gerekli'})
        products = Product.query.filter_by(product_main_id=product_main_id).all()
        if not products:
            return jsonify({'success': False, 'message': 'Ürün bulunamadı'})
        for product in products:
            archive_product = ProductArchive(
                barcode=product.barcode,
                title=product.title,
                product_main_id=product.product_main_id,
                quantity=product.quantity,
                images=product.images,
                variants=product.variants,
                size=product.size,
                color=product.color,
                archived=True,
                locked=product.locked,
                on_sale=product.on_sale,
                reject_reason=product.reject_reason,
                sale_price=product.sale_price,
                list_price=product.list_price,
                currency_type=product.currency_type
            )
            db.session.add(archive_product)
            db.session.delete(product)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Ürünler başarıyla arşivlendi'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})


@get_products_bp.route('/restore_from_archive', methods=['POST'])
def restore_from_archive():
    try:
        product_main_id = request.form.get('product_main_id')
        if not product_main_id:
            return jsonify({'success': False, 'message': 'Model kodu gerekli'})
        archived_products = ProductArchive.query.filter_by(product_main_id=product_main_id).all()
        if not archived_products:
            return jsonify({'success': False, 'message': 'Arşivde ürün bulunamadı'})
        for archived in archived_products:
            product = Product(
                barcode=archived.barcode,
                title=archived.title,
                product_main_id=archived.product_main_id,
                quantity=archived.quantity,
                images=archived.images,
                variants=archived.variants,
                size=archived.size,
                color=archived.color,
                archived=False,
                locked=archived.locked,
                on_sale=archived.on_sale,
                reject_reason=archived.reject_reason,
                sale_price=archived.sale_price,
                list_price=archived.list_price,
                currency_type=archived.currency_type
            )
            db.session.add(product)
            db.session.delete(archived)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Ürünler başarıyla arşivden çıkarıldı'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})


@get_products_bp.route('/product_list')
@cache.cached(timeout=CACHE_TIMES['products'])
def product_list():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 12
        base_query = Product.query
        products = base_query.all()
        grouped_products = group_products_by_model_and_color(products)
        sorted_keys = sorted(grouped_products.keys(), key=lambda x: (x[0].lower(), x[1].lower()))
        total_groups = len(sorted_keys)
        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, total_groups)
        current_page_keys = sorted_keys[start_idx:end_idx]
        current_page_products = {key: sort_variants_by_size(grouped_products[key]) for key in current_page_keys}
        total_pages = (total_groups + per_page - 1) // per_page
        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total_groups,
            'pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'iter_pages': lambda left_edge=2, right_edge=2, left_current=2, right_current=2:
                range(1, total_pages + 1)
        }
    except Exception as e:
        logger.error(f"Ürünler veritabanından çekilirken bir hata oluştu: {e}")
        flash("Ürünler bulunamadı veya veritabanı okunamadı.", "danger")
        return render_template('error.html', message="Ürün bulunamadı.")
    return render_template(
        'product_list.html',
        grouped_products=current_page_products,
        pagination=pagination,
        total_pages=total_pages,
        search_mode=False
    )


@get_products_bp.route('/get_product_variants', methods=['GET'])
def get_product_variants():
    model_id = request.args.get('model', '').strip()
    color = request.args.get('color', '').strip()
    if not model_id or not color:
        logger.warning("Model veya renk bilgisi eksik.")
        return jsonify({'success': False, 'message': 'Model veya renk bilgisi eksik.'})
    products = Product.query.filter(
        func.lower(Product.product_main_id) == model_id.lower(),
        func.lower(Product.color) == color.lower()
    ).all()
    products_list = []
    if products:
        for p in products:
            if not p.barcode or p.quantity is None:
                logger.warning(f"Eksik veri - Barkod: {p.barcode}, Stok: {p.quantity}")
                continue
            products_list.append({
                'size': p.size,
                'barcode': p.barcode,
                'quantity': p.quantity
            })
        try:
            products_list = sorted(products_list, key=lambda x: float(x['size']), reverse=True)
        except (ValueError, TypeError):
            products_list = sorted(products_list, key=lambda x: x['size'], reverse=True)
        return jsonify({'success': True, 'products': products_list})
    else:
        return jsonify({'success': False, 'message': 'Ürün bulunamadı.'})


@get_products_bp.route('/update_stocks_ajax', methods=['POST'])
async def update_stocks_ajax():
    form_data = request.form
    if not form_data:
        return jsonify({'success': False, 'message': 'Güncellenecek ürün bulunamadı.'})
    items_to_update = []
    for barcode, quantity in form_data.items():
        try:
            items_to_update.append({'barcode': barcode, 'quantity': int(quantity)})
        except ValueError:
            return jsonify({'success': False, 'message': f"Barkod {barcode} için geçersiz miktar girdiniz."})
    result = await update_stock_levels_with_items_async(items_to_update)
    if result:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': 'Stok güncelleme başarısız oldu.'})


@get_products_bp.route('/delete_product_variants', methods=['POST'])
def delete_product_variants():
    """
    Bir modele ve renge ait tüm varyantları sil
    """
    try:
        model_id = request.form.get('model_id')
        color = request.form.get('color')

        if not model_id or not color:
            return jsonify({'success': False, 'message': 'Model ID ve renk gereklidir'})

        # Bu modele ve renge ait tüm ürünleri bul
        products = Product.query.filter_by(product_main_id=model_id, color=color).all()

        if not products:
            return jsonify({'success': False, 'message': 'Silinecek ürün bulunamadı'})

        # İşlem logunu hazırla
        log_details = {
            'model_id': model_id,
            'color': color,
            'deleted_count': len(products),
            'barcodes': [p.barcode for p in products]
        }

        # Ürünleri sil
        for product in products:
            db.session.delete(product)

        db.session.commit()

        # Kullanıcı işlemini logla
        try:
            from user_logs import log_user_action
            log_user_action(
                action=f"DELETE_PRODUCTS: {model_id} - {color}",
                details=log_details
            )
        except Exception as e:
            logger.error(f"Kullanıcı log hatası: {e}")

        return jsonify({
            'success': True, 
            'message': f'Toplam {len(products)} ürün başarıyla silindi',
            'deleted_count': len(products)
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Ürün silme hatası: {e}")
        return jsonify({'success': False, 'message': f'Hata oluştu: {str(e)}'})





############################################
# Yardımcı fonksiyon - zaten sende mevcuttu
############################################
def group_products_by_model_and_color(products):
    grouped_products = {}
    for product in products:
        # Anahtar oluştururken None kontrolü ekleyelim
        main_id = product.product_main_id if product.product_main_id else ''
        color = product.color if product.color else ''
        key = (main_id, color)
        grouped_products.setdefault(key, []).append(product)
    return grouped_products



############################################
# Arama fonksiyonu - İSTEĞE GÖRE GÜNCELLENMİŞ HALİ
############################################
@get_products_bp.route('/search_products', methods=['GET'])
def search_products():
    # Formdan gelen arama tipi ve sorguyu al
    search_type = request.args.get('search_type', 'model_code').strip() # Varsayılan: model_code
    query = request.args.get('query', '').strip()

    # Sorgu boşsa uyarı ver ve ana listeye dön
    if not query:
        flash('Lütfen bir arama sorgusu girin.', 'warning')
        return redirect(url_for('get_products.product_list'))

    products_query = None
    # Arama tipine göre SQLAlchemy sorgusunu oluştur
    if search_type == 'model_code':
        # Model koduna göre büyük/küçük harf duyarsız tam eşleşme
        products_query = Product.query.filter(func.lower(Product.product_main_id) == query.lower())
        logger.debug(f"Model kodu ile arama yapılıyor: {query}")
    elif search_type == 'barcode':
        # Barkoda göre tam eşleşme
        products_query = Product.query.filter(Product.barcode == query)
        logger.debug(f"Barkod ile arama yapılıyor: {query}")
    else:
        # Geçersiz bir arama tipi gelirse (normalde olmamalı)
        flash('Geçersiz arama tipi seçildi.', 'danger')
        return redirect(url_for('get_products.product_list'))

    # Sorguyu çalıştır ve tüm sonuçları al
    products = products_query.all()
    logger.debug(f"Arama sonucu bulunan ürün sayısı: {len(products)}")

    # Sonuç bulunamazsa kullanıcıyı bilgilendir
    if not products:
        flash(f"'{query}' için sonuç bulunamadı.", 'info')
        # Boş bir grouped_products göndererek template'in hata vermesini engelle
        return render_template(
            'product_list.html',
            grouped_products={},
            pagination=None,
            search_mode=True,
            search_query=query, # Arama kutusunu dolu tutmak için
            search_type=search_type
        )

    # Bulunan ürünleri model ve renge göre grupla
    # group_products_by_model_and_color zaten listenin boş olup olmadığını kontrol etmeli
    grouped_products = group_products_by_model_and_color(products)
    logger.debug(f"Gruplanmış ürün anahtarları: {list(grouped_products.keys())}")

    # Sonuçları template'e gönder
    return render_template(
        'product_list.html',
        grouped_products=grouped_products,
        pagination=None,  # Arama sonuçlarında genellikle sayfalama olmaz
        search_mode=True,
        search_query=query, # Arama kutusunu dolu tutmak için
        search_type=search_type
    )





@get_products_bp.route('/api/delete-product', methods=['POST'])
def delete_product_api():
    """
    API endpoint for deleting all variants of a product by model ID and color
    """
    try:
        model_id = request.form.get('model_id')
        color = request.form.get('color')

        if not model_id or not color:
            return jsonify({'success': False, 'message': 'Model ID ve renk gereklidir'})

        # Bu modele ve renge ait tüm ürünleri bul
        products = Product.query.filter_by(product_main_id=model_id, color=color).all()

        if not products:
            return jsonify({'success': False, 'message': 'Silinecek ürün bulunamadı'})

        # İşlem logunu hazırla
        log_details = {
            'model_id': model_id,
            'color': color,
            'deleted_count': len(products),
            'barcodes': [p.barcode for p in products]
        }

        # Ürünleri sil
        for product in products:
            db.session.delete(product)

        db.session.commit()

        # Kullanıcı işlemini logla
        try:
            from user_logs import log_user_action
            log_user_action(
                action=f"DELETE_PRODUCTS: {model_id} - {color}",
                details=log_details
            )
        except Exception as e:
            logger.error(f"Kullanıcı log hatası: {e}")

        return jsonify({
            'success': True, 
            'message': f'Toplam {len(products)} ürün başarıyla silindi',
            'deleted_count': len(products)
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Ürün silme hatası: {e}")
        return jsonify({'success': False, 'message': f'Hata oluştu: {str(e)}'})

@get_products_bp.route('/product_label')
def product_label():
    return render_template('product_label.html')


@get_products_bp.route('/api/get_variants_with_cost', methods=['GET'])
def get_variants_with_cost():
    model = request.args.get('model', '').strip()
    color = request.args.get('color', '').strip()
    if not model or not color:
        return jsonify({'success': False, 'message': 'Model veya renk eksik.'})
    products = Product.query.filter(
        func.lower(Product.product_main_id) == model.lower(),
        func.lower(Product.color) == color.lower()
    ).all()
    if not products:
        return jsonify({'success': False, 'message': 'Ürün bulunamadı.'})
    variants = []
    for p in products:
        if p.barcode and p.barcode != 'undefined':
            variants.append({
                'barcode': p.barcode,
                'size': p.size,
                'quantity': p.quantity,
                'cost_usd': p.cost_usd or 0,
                'cost_try': p.cost_try or 0
            })
    try:
        variants = sorted(variants, key=lambda x: float(x['size']), reverse=True)
    except (ValueError, TypeError):
        variants = sorted(variants, key=lambda x: x['size'], reverse=True)
    return jsonify({'success': True, 'products': variants})


@get_products_bp.route('/api/update_product_costs', methods=['POST'])
def update_product_costs():
    form_data = request.form
    if not form_data:
        return jsonify({'success': False, 'message': 'Güncellenecek veri bulunamadı.'})
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        usd_rate = loop.run_until_complete(fetch_usd_rate())
        loop.close()
        if not usd_rate:
            usd_rate = 1.0
    except:
        usd_rate = 1.0
    updated_count = 0
    errors = []
    for barcode, cost_str in form_data.items():
        try:
            new_cost = float(cost_str)
        except ValueError:
            errors.append(f"Barkod {barcode} için geçersiz maliyet değeri.")
            continue
        product = Product.query.filter_by(barcode=barcode).first()
        if not product:
            errors.append(f"Barkod bulunamadı: {barcode}")
            continue
        product.cost_usd = new_cost
        product.cost_try= new_cost * usd_rate
        product.cost_date = datetime.now()
        db.session.add(product)
        updated_count += 1
    if updated_count == 0 and errors:
        return jsonify({'success': False, 'message': 'Maliyet güncellemesi yapılamadı.', 'errors': errors})
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Maliyet güncelleme hatası: {e}")
        return jsonify({'success': False, 'message': str(e)})
    return jsonify({'success': True, 'message': f"{updated_count} adet varyant güncellendi.", 'errors': errors})


@get_products_bp.route('/api/product-cost', methods=['GET'])
def get_product_cost():
    model_id = request.args.get('model_id', '').strip()
    if not model_id:
        return jsonify({'success': False, 'message': 'Model ID gerekli'})
    product = Product.query.filter_by(product_main_id=model_id).first()
    if not product:
        return jsonify({'success': False, 'message': 'Ürün bulunamadı'})
    return jsonify({
        'success': True,
        'cost_usd': product.cost_usd or 0,
        'cost_try': product.cost_try or 0,
        'cost_date': product.cost_date.strftime('%Y-%m-%d %H:%M') if product.cost_date else None
    })


@get_products_bp.route('/api/update-product-cost', methods=['POST'])
def update_product_cost():
    model_id = request.form.get('model_id', '').strip()
    cost_usd_str = request.form.get('cost_usd')
    if not model_id:
        return jsonify({'success': False, 'message': 'Model ID gerekli'})
    try:
        cost_usd = float(cost_usd_str)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Geçerli bir maliyet değeri giriniz'})
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    usd_rate = loop.run_until_complete(fetch_usd_rate())
    loop.close()
    if not usd_rate:
        usd_rate = 1.0
    try:
        products = Product.query.filter_by(product_main_id=model_id).all()
        if not products:
            return jsonify({'success': False, 'message': 'Ürün bulunamadı'})
        for product in products:
            product.cost_usd = cost_usd
            product.cost_try = cost_usd * usd_rate
            product.cost_date = datetime.now()
            db.session.add(product)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Ürün maliyetleri güncellendi'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Maliyet güncelleme hatası: {e}")
        return jsonify({'success': False, 'message': f'Bir hata oluştu: {str(e)}'})
@get_products_bp.route('/api/bulk-delete-products', methods=['POST'])
def bulk_delete_products():
    """
    Birden fazla ürünü toplu halde silmek için API endpoint'i
    """
    try:
        data = request.get_json()
        if not data or 'products' not in data:
            return jsonify({'success': False, 'message': 'Geçersiz veri formatı'}), 400

        products_to_delete = data['products']
        if not products_to_delete:
            return jsonify({'success': False, 'message': 'Silinecek ürün bulunamadı'}), 400

        deleted_count = 0
        deleted_items = []

        for product_info in products_to_delete:
            model_id = product_info.get('model_id')
            color = product_info.get('color')

            if not model_id or not color:
                continue

            # Bu modele ve renge ait tüm ürünleri bul
            products = Product.query.filter_by(product_main_id=model_id, color=color).all()

            if not products:
                continue

            # Ürünleri sil
            for product in products:
                deleted_items.append({
                    'barcode': product.barcode,
                    'title': product.title,
                    'size': product.size
                })
                db.session.delete(product)
                deleted_count += 1

        if deleted_count > 0:
            # İşlem logunu hazırla
            log_details = {
                'total_deleted': deleted_count,
                'deleted_items': deleted_items
            }

            db.session.commit()

            # Kullanıcı işlemini logla
            try:
                from user_logs import log_user_action
                log_user_action(
                    action=f"BULK_DELETE_PRODUCTS: {deleted_count} ürün silindi",
                    details=log_details
                )
            except Exception as e:
                logger.error(f"Kullanıcı log hatası: {e}")

            return jsonify({
                'success': True,
                'message': f'Toplam {deleted_count} ürün başarıyla silindi',
                'deleted_count': deleted_count
            })
        else:
            return jsonify({'success': False, 'message': 'Hiçbir ürün silinemedi'})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Toplu ürün silme hatası: {e}")
        return jsonify({'success': False, 'message': f'Hata oluştu: {str(e)}'})



