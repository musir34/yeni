import asyncio
import aiohttp
import os
import base64
import json
import logging
import threading
import qrcode
import qrcode.constants
from datetime import datetime
from urllib.parse import urlparse
from dotenv import load_dotenv
from io import BytesIO
from sqlalchemy import case
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, send_file, current_app, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import insert
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
#-------------------------------------------------------------------

async def fetch_usd_rate():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(total=10)
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    try:
                        return float(data.get('rates', {}).get('TRY', 0))
                    except (ValueError, TypeError) as e:
                        logger.error(f"Kur değeri dönüştürme hatası: {e}")
                        return 34.0
                else:
                    logger.error(f"Döviz API hatası: {response.status} {await response.text()}")
                    return 34.0
    except Exception as e:
        logger.error(f"fetch_usd_rate hata: {e}")
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
    import qrcode
    import qrcode.constants
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
        if key not in grouped_products:
            grouped_products[key] = []
        grouped_products[key].append(product)

    for key, group in grouped_products.items():
        try:
            grouped_products[key] = sorted(group, key=lambda p: float(p.size), reverse=True)
        except (ValueError, TypeError):
            grouped_products[key] = sorted(group, key=lambda p: p.size, reverse=True)

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

        if products:
            logger.debug("Ürünler veritabanına kaydediliyor...")
            await save_products_to_db_async(products)
            logger.info("Ürünler başarıyla güncellendi.")
        else:
            logger.warning("Ürünler bulunamadı veya güncelleme sırasında bir hata oluştu.")

    except Exception as e:
        logger.error(f"update_products_route hata: {e}", exc_info=True)
        flash('Ürünler güncellenirken bir hata oluştu.', 'danger')

    return redirect(url_for('get_products.product_list'))


@get_products_bp.route('/update_stocks_route', methods=['POST'])
async def update_stocks_route():
    logger.info("Trendyol'dan stokları çekme ve veritabanını güncelleme işlemi başlatıldı.")

    if not API_KEY or not API_SECRET or not SUPPLIER_ID:
        msg = "Trendyol API bilgileri sunucuda eksik. Stoklar Trendyol'dan çekilemez."
        logger.error(msg)
        return jsonify({'success': False, 'message': msg})

    try:
        trendyol_products = await fetch_all_products_async()

        if not trendyol_products:
            logger.warning("Trendyol'dan ürün çekilemedi. Stok güncellenemiyor.")
            return jsonify({'success': False, 'message': 'Trendyol\'dan güncel ürün (stok) bilgisi çekilemedi.'})

        barcode_quantity_map = {
            p.get('barcode'): int(p.get('quantity', 0))
            for p in trendyol_products
            if p.get('barcode')
        }

        if not barcode_quantity_map:
            logger.info("Trendyol'dan güncellenecek geçerli stok bilgisi (barkod/miktar) alınamadı.")
            return jsonify({'success': False, 'message': 'Trendyol\'dan güncellenecek stok bilgisi alınamadı (Geçerli barkod bulunamadı).'})

        all_trendyol_barcodes = list(barcode_quantity_map.keys())
        logger.debug(f"Trendyol'dan çekilen ve DB'de aranacak toplam barkod sayısı: {len(all_trendyol_barcodes)}")

        batch_size = 1000
        local_products_to_update = []

        for i in range(0, len(all_trendyol_barcodes), batch_size):
            barcode_batch = all_trendyol_barcodes[i : i + batch_size]
            logger.debug(f"DB'den ürünler çekiliyor: Batch {i//batch_size + 1} / { (len(all_trendyol_barcodes) + batch_size - 1) // batch_size }")

            batch_results = Product.query.filter(Product.barcode.in_(barcode_batch)).all()
            local_products_to_update.extend(batch_results)

        logger.debug(f"Veritabanından Trendyol barkodlarına karşılık gelen toplam ürün sayısı: {len(local_products_to_update)}")

        updated_count = 0
        products_marked_for_update = []

        for product in local_products_to_update:
            trendyol_quantity = barcode_quantity_map.get(product.barcode)
            if trendyol_quantity is not None and isinstance(trendyol_quantity, int):
                if product.quantity != trendyol_quantity:
                    logger.debug(f"DB Stoğu Güncelleniyor: Barkod {product.barcode}, Eski: {product.quantity}, Yeni (Trendyol): {trendyol_quantity}")
                    product.quantity = trendyol_quantity
                    db.session.add(product)
                    products_marked_for_update.append(product)
                    updated_count += 1
                else:
                    logger.debug(f"DB Stoğu Aynı: Barkod {product.barcode}, Miktar: {product.quantity}")
            else:
                logger.warning(f"Trendyol'dan {product.barcode} barkodu için geçersiz miktar geldi: {trendyol_quantity}. DB güncellenmedi.")

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

        return jsonify({'success': True, 'message': f'Stoklar başarıyla Trendyol\'dan çekildi ve veritabanında güncellendi ({updated_count} ürün güncellendi).'})

    except Exception as e:
        db.session.rollback()
        logger.error(f"update_stocks_route (Trendyol Stok Çekme) sırasında genel hata: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Stok güncelleme sırasında bir hata oluştu: {str(e)}'})



async def save_products_to_db_async(products):
    products = [p for p in products if isinstance(p, dict)]
    archived_barcodes = {x.barcode for x in ProductArchive.query.with_entities(ProductArchive.barcode).all()}

    images_folder = os.path.join(current_app.root_path, 'static', 'images')
    os.makedirs(images_folder, exist_ok=True)

    product_objects = []
    seen_barcodes = set()
    image_downloads = []
    for product_data in products:
        original_barcode = product_data.get('barcode', '').strip()
        if not original_barcode or original_barcode in seen_barcodes or original_barcode in archived_barcodes:
            continue
        seen_barcodes.add(original_barcode)

        def safe_datetime_from_timestamp(ts):
            if not ts: return None
            try: return datetime.fromtimestamp(int(ts) / 1000)
            except (ValueError, TypeError, OSError): return None

        last_update_date_obj = safe_datetime_from_timestamp(product_data.get('lastUpdateDate'))
        create_date_time_obj = safe_datetime_from_timestamp(product_data.get('createDateTime'))

        image_urls = [img.get('url', '') for img in product_data.get('images', []) if isinstance(img, dict)]
        images_path_db = ''
        if image_urls and image_urls[0]:
            image_url = image_urls[0]
            parsed_url = urlparse(image_url)
            image_extension = os.path.splitext(parsed_url.path)[1] or '.jpg'
            image_filename = f"{original_barcode}{image_extension.lower()}"
            image_path_local = os.path.join(images_folder, image_filename)
            images_path_db = f"/static/images/{image_filename}"
            image_downloads.append((image_url, image_path_local))

        status_str = "Beklemede"
        if product_data.get('rejected'):
            status_str = "Reddedildi"
        elif product_data.get('approved'):
            status_str = "Onaylandı"
        if product_data.get('archived'):
            status_str = f"{status_str} (Arşivde)"

        size = next((attr.get('attributeValue', 'N/A') for attr in product_data.get('attributes', []) if attr.get('attributeName') == 'Beden'), 'N/A')
        color = next((attr.get('attributeValue', 'N/A') for attr in product_data.get('attributes', []) if attr.get('attributeName') == 'Renk'), 'N/A')

        product_objects.append({
            "barcode": original_barcode, "title": product_data.get('title'),
            "images": images_path_db, "product_main_id": product_data.get('productMainId'),
            "quantity": product_data.get('quantity', 0), "size": size, "color": color,
            "archived": product_data.get('archived', False), "locked": product_data.get('locked', False),
            "on_sale": product_data.get('onSale', False), "sale_price": product_data.get('salePrice', 0),
            "list_price": product_data.get('listPrice', 0), "currency_type": product_data.get('currencyType'),
            "description": product_data.get('description'), "attributes": json.dumps(product_data.get('attributes', [])),
            "reject_reason": '; '.join([r.get('reason', 'N/A') for r in product_data.get('rejectReasonDetails', [])]),
            "brand": product_data.get('brand'), "category_name": product_data.get('categoryName'),
            "vat_rate": product_data.get('vatRate'), "status": status_str, "gtin": product_data.get('gtin'),
            "last_update_date": last_update_date_obj, "brand_id": product_data.get('brandId'),
            "create_date_time": create_date_time_obj, "gender": product_data.get('gender'),
            "has_active_campaign": product_data.get('hasActiveCampaign'), "trendyol_id": product_data.get('id'),
            "pim_category_id": product_data.get('pimCategoryId'), "platform_listing_id": product_data.get('platformListingId'),
            "product_code": product_data.get('productCode'), "product_content_id": product_data.get('productContentId'),
            "stock_unit_type": product_data.get('stockUnitType'), "supplier_id": product_data.get('supplierId'),
            "is_rejected": product_data.get('rejected'), "is_blacklisted": product_data.get('blacklisted'),
            "has_html_content": product_data.get('hasHtmlContent'), "product_url": product_data.get('productUrl'),
            "is_approved": product_data.get('approved')
        })

    if not product_objects: return

    batch_size = 200
    for i in range(0, len(product_objects), batch_size):
        batch = product_objects[i:i + batch_size]
        insert_stmt = insert(Product).values(batch)

        set_payload = {
            'title': insert_stmt.excluded.title, 'quantity': insert_stmt.excluded.quantity,
            'sale_price': insert_stmt.excluded.sale_price, 'list_price': insert_stmt.excluded.list_price,
            'on_sale': insert_stmt.excluded.on_sale, 'locked': insert_stmt.excluded.locked,
            'is_approved': insert_stmt.excluded.is_approved, 'last_update_date': insert_stmt.excluded.last_update_date,
            'vat_rate': insert_stmt.excluded.vat_rate, 'reject_reason': insert_stmt.excluded.reject_reason,
            'description': insert_stmt.excluded.description, 'attributes': insert_stmt.excluded.attributes,
            'is_rejected': insert_stmt.excluded.is_rejected, 'brand': insert_stmt.excluded.brand,
            'category_name': insert_stmt.excluded.category_name, 'gender': insert_stmt.excluded.gender,
            'product_url': insert_stmt.excluded.product_url,
            'has_active_campaign': insert_stmt.excluded.has_active_campaign,
            'is_blacklisted': insert_stmt.excluded.is_blacklisted, 'status': insert_stmt.excluded.status,
            'images': insert_stmt.excluded.images
        }

        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=['barcode'], set_=set_payload
        )
        db.session.execute(upsert_stmt)

    db.session.commit()

    if image_downloads:
        logger.info(f"{len(image_downloads)} adet yeni görsel indirilecek...")
        await download_images_async(image_downloads)
        logger.info("Tüm görsellerin indirme işlemi tamamlandı.")

    flash("Tüm ürün verileri başarıyla veritabanına kaydedildi/güncellendi.", "success")


async def fetch_all_products_async():
    """
    Bu fonksiyon, API anahtarlarını kontrol ederek ve istekleri sıralayarak
    Trendyol'dan ürünleri güvenli bir şekilde çeker.
    """
    logger.debug("fetch_all_products_async fonksiyonu başlatıldı.")

    # ADIM 1: KRİTİK KONTROL - API Bilgileri .env dosyasından doğru geliyor mu?
    if not all([API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL]):
        logger.error("KRİTİK HATA: API_KEY, API_SECRET, SUPPLIER_ID veya BASE_URL bilgileri eksik! Lütfen .env dosyanızı ve trendyol_api.py dosyanızı kontrol edin.")
        return []  # Bilgiler eksikse fonksiyonu hemen durdur.

    logger.debug(f"Kullanılan Supplier ID: {SUPPLIER_ID}")
    logger.debug(f"API Key değeri var mı?: {'Evet' if API_KEY else 'Hayır'}")
    logger.debug(f"BASE_URL doğru mu?: {BASE_URL}")

    page_size = 500
    url = f"{BASE_URL}integration/product/sellers/{SUPPLIER_ID}/products"
    logger.debug(f"Kullandığım Yeni Trendyol endpoint: {url}")

    credentials = f"{API_KEY}:{API_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "User-Agent": f"SellerId={SUPPLIER_ID} - SelfIntegration",
        # Ekstra güvenlik için Accept header'ı eklendi.
        "Accept": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        params = {"page": 0, "size": page_size, "approved": "true"}
        timeout = aiohttp.ClientTimeout(total=30)

        data = None
        try:
            # İlk sayfa isteği
            async with session.get(url, headers=headers, params=params, timeout=timeout) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logging.error(f"API Hatası (ilk sayfa): {response.status} - {error_text}")
                    return []

                data = await response.json()
                logging.debug(f"İlk sayfa API yanıtının tamamı: {json.dumps(data, indent=2)}")

        except Exception as e:
            logging.error(f"İlk sayfa çekme veya JSON çözümleme hatası: {e}", exc_info=True)
            return []

        if not data:
            logging.error("API'den veri alınamadı (data is None).")
            return []

        total_pages = data.get('totalPages', 0)
        logging.info(f"Toplam sayfa sayısı: {total_pages}")

        if total_pages == 0:
            logging.info("API'den hiç ürün gelmedi (totalPages = 0).")
            return []

        # İstekleri tek tek göndermek için Semaphore(1) kullanıyoruz.
        semaphore = asyncio.Semaphore(1)

        tasks = [
            fetch_products_page(session, url, headers, {"page": page_number, "size": page_size, "approved": "true"}, semaphore)
            for page_number in range(total_pages)
        ]

        pages_data = await asyncio.gather(*tasks)

        all_products = [product for page in pages_data if isinstance(page, list) for product in page]
        logging.info(f"Toplam çekilen ürün sayısı: {len(all_products)}")
        return all_products



async def fetch_products_page(session, url, headers, params, semaphore):
    async with semaphore:
        try:
            # Her istek arasında çok kısa bir bekleme (0.2 saniye) ekliyoruz.
            await asyncio.sleep(0.2) 
            async with session.get(url, headers=headers, params=params, timeout=30) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logging.error(f"Sayfa {params['page']} çekme hatası: {response.status} - {error_text}")
                    return []

                try:
                    data = await response.json()
                    items = data.get('content', []) 

                    if not isinstance(items, list):
                        logging.error(f"Sayfa {params['page']} verisi 'content' beklenen bir liste değil: {type(items)}")
                        return []

                    logging.debug(f"Sayfa {params['page']} başarıyla çekildi, içerik boyutu: {len(items)}")
                    return items

                except Exception as e:
                    error_text = await response.text()
                    logging.error(f"Sayfa {params['page']} JSON çözümleme hatası: {e} - Yanıt: {error_text}")
                    return []
        except Exception as e:
            logging.error(f"fetch_products_page (Sayfa {params['page']}) genel hata: {e}", exc_info=True)
            return []


async def download_images_async(image_urls):
    if not image_urls:
        logger.info("İndirilecek görsel bulunmuyor")
        return

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = []
        semaphore = asyncio.Semaphore(50)
        for image_url, image_path in image_urls:
            tasks.append(download_image(session, image_url, image_path, semaphore))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if r is True)
        error_count = len(results) - success_count

        logger.info(f"Görsel indirme tamamlandı: {success_count} başarılı, {error_count} hatalı")


async def download_image(session, image_url, image_path, semaphore):
    async with semaphore:
        if os.path.exists(image_path):
            logger.debug(f"Resim zaten mevcut, atlanıyor: {os.path.basename(image_path)}")
            return True

        try:
            os.makedirs(os.path.dirname(image_path), exist_ok=True)

            async with session.get(image_url) as response:
                if response.status != 200:
                    logger.warning(f"Resim indirme hatası: {response.status} - {image_url}")
                    return False

                content = await response.read()
                if len(content) < 100:
                    logger.warning(f"Geçersiz görsel boyutu: {len(content)} bytes - {image_url}")
                    return False

                with open(image_path, 'wb') as img_file:
                    img_file.write(content)

                logger.debug(f"Resim kaydedildi: {os.path.basename(image_path)}")
                return True

        except Exception as e:
            logger.error(f"Resim indirme hatası ({os.path.basename(image_path)}): {e}", exc_info=True)
            return False


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
            'quantity': insert_stmt.excluded.quantity, 'sale_price': insert_stmt.excluded.sale_price,
            'list_price': insert_stmt.excluded.list_price, 'images': insert_stmt.excluded.images,
            'size': insert_stmt.excluded.size, 'color': insert_stmt.excluded.color,
            'description': insert_stmt.excluded.description, 'attributes': insert_stmt.excluded.attributes,
        }
    )
    db.session.execute(upsert_stmt)
    db.session.commit()


async def update_stock_levels_with_items_async(items):
    if not items:
        logger.error("Güncellenecek ürün bulunamadı.")
        return False

    url = f"{BASE_URL}integration/inventory/sellers/{SUPPLIER_ID}/products/price-and-inventory"
    logger.info(f"Kullanılan yeni Stok/Fiyat güncelleme URL'i: {url}")

    credentials = f"{API_KEY}:{API_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    headers = {
        "Authorization": f"Basic {encoded_credentials}", "Content-Type": "application/json",
        "User-Agent": f"SellerId={SUPPLIER_ID} - SelfIntegration"
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
            timeout = aiohttp.ClientTimeout(total=30)
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status in [200, 201, 202]:
                    logger.info("Ürünler API üzerinden başarıyla güncellendi.")
                    return True
                else:
                    logger.error(f"HTTP Hatası: {response.status}, Yanıt: {await response.text()}")
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
        logger.error(f"fetch_products_route hata: {e}", exc_info=True)
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
            archive_data = {c.name: getattr(product, c.name) for c in product.__table__.columns}
            archive_data['archived'] = True
            archive_product = ProductArchive(**archive_data)
            db.session.add(archive_product)
            db.session.delete(product)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Ürünler başarıyla arşivlendi'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Arşivleme hatası: {e}", exc_info=True)
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
            product_data = {c.name: getattr(archived, c.name) for c in archived.__table__.columns if hasattr(Product, c.name)}
            product_data['archived'] = False
            product_data.pop('archive_date', None)
            product = Product(**product_data)
            db.session.add(product)
            db.session.delete(archived)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Ürünler başarıyla arşivden çıkarıldı'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Arşivden geri yükleme hatası: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)})


def group_products_by_model_and_then_color(products):
    grouped_by_model = {}
    for product in products:
        model_id = product.product_main_id
        if not model_id:
            continue
        if model_id not in grouped_by_model:
            grouped_by_model[model_id] = {'main_product_info': product, 'colors': {}}
        color = product.color or 'Diğer'
        if color not in grouped_by_model[model_id]['colors']:
            grouped_by_model[model_id]['colors'][color] = []
        grouped_by_model[model_id]['colors'][color].append(product)

    for model_id, data in grouped_by_model.items():
        for color, variants in data['colors'].items():
            try:
                data['colors'][color] = sorted(variants, key=lambda x: float(x.size), reverse=True)
            except (ValueError, TypeError):
                data['colors'][color] = sorted(variants, key=lambda x: x.size, reverse=True)
    return grouped_by_model


@get_products_bp.route('/product_list')
def product_list():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 12 
        all_products = Product.query.order_by(Product.product_main_id).all()
        hierarchical_products = group_products_by_model_and_then_color(all_products)
        model_keys = sorted(list(hierarchical_products.keys()))
        total_models = len(model_keys)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        current_page_keys = model_keys[start_idx:end_idx]
        current_page_products = {key: hierarchical_products[key] for key in current_page_keys}
        total_pages = (total_models + per_page - 1) // per_page
        pagination = {
            'page': page, 'per_page': per_page, 'total': total_models,
            'pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None,
            'iter_pages': lambda left_edge=1, right_edge=1, left_current=2, right_current=2: 
                            range(max(1, page - left_current), min(total_pages, page + right_current) + 1)
        }
        return render_template('product_list.html', grouped_products=current_page_products, pagination=pagination, search_mode=False)
    except Exception as e:
        logger.error(f"Ürün listesi oluşturulurken hata: {e}", exc_info=True)
        flash("Ürün listesi yüklenirken bir hata oluştu.", "danger")
        return render_template('product_list.html', grouped_products={}, pagination=None)


@get_products_bp.route('/api/get_product_variants', methods=['GET'])
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
            products_list.append({'size': p.size, 'barcode': p.barcode, 'quantity': p.quantity})
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
    try:
        model_id = request.form.get('model_id')
        color = request.form.get('color')
        if not model_id or not color:
            return jsonify({'success': False, 'message': 'Model ID ve renk gereklidir'})
        products = Product.query.filter_by(product_main_id=model_id, color=color).all()
        if not products:
            return jsonify({'success': False, 'message': 'Silinecek ürün bulunamadı'})
        log_details = {
            'model_id': model_id, 'color': color, 'deleted_count': len(products),
            'barcodes': [p.barcode for p in products]
        }
        for product in products:
            db.session.delete(product)
        db.session.commit()
        try:
            from user_logs import log_user_action
            log_user_action(action=f"DELETE_PRODUCTS: {model_id} - {color}", details=log_details)
        except Exception as e:
            logger.error(f"Kullanıcı log hatası: {e}")
        return jsonify({
            'success': True, 'message': f'Toplam {len(products)} ürün başarıyla silindi',
            'deleted_count': len(products)
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ürün silme hatası: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Hata oluştu: {str(e)}'})


@get_products_bp.route('/search_products')
def search_products():
    query = request.args.get('query', '').strip()
    search_type = request.args.get('search_type', 'model_code').strip()
    if not query:
        return redirect(url_for('get_products.product_list'))
    found_products_query = None
    if search_type == 'model_code':
        found_products_query = Product.query.filter(func.lower(Product.product_main_id) == query.lower())
    elif search_type == 'barcode':
        product_by_barcode = Product.query.filter_by(barcode=query).first()
        if product_by_barcode and product_by_barcode.product_main_id:
            found_products_query = Product.query.filter_by(product_main_id=product_by_barcode.product_main_id)
    found_products = found_products_query.all() if found_products_query else []
    grouped_results = group_products_by_model_and_color(found_products)
    return render_template(
        'product_list.html', grouped_products=grouped_results, pagination=None,
        search_mode=True, search_query=query, search_type=search_type
    )


@get_products_bp.route('/api/delete-product', methods=['POST'])
def delete_product_api():
    try:
        model_id = request.form.get('model_id')
        color = request.form.get('color')
        if not model_id or not color:
            return jsonify({'success': False, 'message': 'Model ID ve renk gereklidir'})
        products = Product.query.filter_by(product_main_id=model_id, color=color).all()
        if not products:
            return jsonify({'success': False, 'message': 'Silinecek ürün bulunamadı'})
        log_details = {
            'model_id': model_id, 'color': color, 'deleted_count': len(products),
            'barcodes': [p.barcode for p in products]
        }
        for product in products:
            db.session.delete(product)
        db.session.commit()
        try:
            from user_logs import log_user_action
            log_user_action(action=f"DELETE_PRODUCTS: {model_id} - {color}", details=log_details)
        except Exception as e:
            logger.error(f"Kullanıcı log hatası: {e}")
        return jsonify({
            'success': True, 'message': f'Toplam {len(products)} ürün başarıyla silindi',
            'deleted_count': len(products)
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ürün silme hatası: {e}", exc_info=True)
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
                'barcode': p.barcode, 'size': p.size, 'quantity': p.quantity,
                'cost_usd': p.cost_usd or 0, 'cost_try': p.cost_try or 0
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
        if not usd_rate: usd_rate = 1.0
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
        logger.error(f"Maliyet güncelleme hatası: {e}", exc_info=True)
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
        'success': True, 'cost_usd': product.cost_usd or 0,
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
        cost_usd = float(cost_usd_str) if cost_usd_str else 0.0
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Geçerli bir maliyet değeri giriniz'})
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    usd_rate = loop.run_until_complete(fetch_usd_rate())
    loop.close()
    if not usd_rate or usd_rate is None: usd_rate = 1.0
    usd_rate = float(usd_rate)
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
        logger.error(f"Maliyet güncelleme hatası: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Bir hata oluştu: {str(e)}'})


@get_products_bp.route('/api/update_product_prices', methods=['POST'])
def update_product_prices():
    try:
        if not session.get('user_id') or session.get('role', '').lower() != 'admin':
            return jsonify({'success': False, 'message': 'Bu işlem için yetkiniz yok'})
        updated_count = 0; errors = []; price_updates = []
        for key, value in request.form.items():
            if key and value:
                try:
                    barcode, new_price = key, float(value)
                    product = Product.query.filter_by(barcode=barcode).first()
                    if product:
                        product.sale_price = new_price
                        db.session.add(product)
                        updated_count += 1
                        price_updates.append((barcode, new_price))
                    else: errors.append(f"Barkod {barcode} bulunamadı")
                except (ValueError, TypeError): errors.append(f"Geçersiz fiyat değeri: {value}")
                except Exception as e: errors.append(f"Barkod {key} güncellenirken hata: {str(e)}")
        if updated_count > 0: db.session.commit()
        trendyol_errors = []
        if price_updates:
            try:
                trendyol_errors = asyncio.run(update_prices_in_trendyol_bulk(price_updates))
            except Exception as e:
                logger.error(f"Trendyol toplu güncelleme hatası: {e}", exc_info=True)
                trendyol_errors = [barcode for barcode, _ in price_updates]
        message = f"{updated_count} adet ürünün fiyatı güncellendi."
        if trendyol_errors: message += f" {len(trendyol_errors)} üründe Trendyol güncellemesi başarısız oldu."
        else: message += " Trendyol fiyatları da güncellendi."
        if errors: message += f" {len(errors)} hata oluştu."
        return jsonify({
            'success': updated_count > 0, 'message': message, 'updated_count': updated_count,
            'trendyol_errors': len(trendyol_errors), 'errors': errors
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Fiyat güncelleme hatası: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Fiyat güncelleme sırasında hata oluştu: {str(e)}'})


async def update_prices_in_trendyol_bulk(price_updates):
    try:
        api_key, secret_key, supplier_id = (os.getenv('TRENDYOL_API_KEY'), os.getenv('TRENDYOL_API_SECRET'), os.getenv('TRENDYOL_SUPPLIER_ID'))
        if not all([api_key, secret_key, supplier_id]):
            logger.error("Trendyol API anahtarları eksik")
            return [barcode for barcode, _ in price_updates]
        if not price_updates: return []
        url = f"https://api.trendyol.com/integration/inventory/sellers/{supplier_id}/products/price-and-inventory"
        logger.info(f"Kullanılan yeni Toplu Fiyat Güncelleme URL'i: {url}")
        credentials = base64.b64encode(f"{api_key}:{secret_key}".encode()).decode()
        headers = {
            'Authorization': f'Basic {credentials}', 'Content-Type': 'application/json',
            'User-Agent': f'SellerId={supplier_id} - SelfIntegration'
        }
        items = [{"barcode": barcode, "salePrice": price, "listPrice": price} for barcode, price in price_updates]
        payload = {"items": items}
        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(total=60)
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status in [200, 202]:
                    logger.info(f"Trendyol toplu fiyat güncellendi - {len(items)} ürün başarılı")
                    return []
                else:
                    error_text = await response.text()
                    logger.error(f"Trendyol toplu fiyat güncelleme hatası - Status: {response.status}, Error: {error_text}")
                    return [barcode for barcode, _ in price_updates]
    except Exception as e:
        logger.error(f"Trendyol API genel hatası: {e}", exc_info=True)
        return [barcode for barcode, _ in price_updates]


@get_products_bp.route('/api/update_model_price', methods=['POST'])
def update_model_price():
    try:
        if not session.get('user_id') or session.get('role', '').lower() != 'admin':
            return jsonify({'success': False, 'message': 'Bu işlem için yetkiniz yok'})
        model_id = request.form.get('model_id', '').strip()
        sale_price_str = request.form.get('sale_price', '').strip()
        if not model_id: return jsonify({'success': False, 'message': 'Model ID gerekli'})
        if not sale_price_str: return jsonify({'success': False, 'message': 'Satış fiyatı gerekli'})
        try:
            sale_price = float(sale_price_str)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Geçerli bir fiyat değeri giriniz'})
        if sale_price < 0: return jsonify({'success': False, 'message': 'Fiyat negatif olamaz'})
        products = Product.query.filter_by(product_main_id=model_id).all()
        if not products: return jsonify({'success': False, 'message': 'Bu model için ürün bulunamadı'})
        updated_count = 0
        price_updates = []
        for product in products:
            product.sale_price = sale_price
            db.session.add(product)
            updated_count += 1
            price_updates.append((product.barcode, sale_price))
        db.session.commit()
        trendyol_errors = []
        if price_updates:
            try:
                trendyol_errors = asyncio.run(update_prices_in_trendyol_bulk(price_updates))
            except Exception as e:
                logger.error(f"Trendyol toplu güncelleme hatası: {e}", exc_info=True)
                trendyol_errors = [barcode for barcode, _ in price_updates]
        message = f'{model_id} modeli için {updated_count} varyantın fiyatı {sale_price} TL olarak güncellendi'
        if trendyol_errors:
            message += f'\n\nUyarı: {len(trendyol_errors)} üründe Trendyol fiyat güncellemesi başarısız oldu.'
            message += f'\nSorunlu barkodlar: {", ".join(trendyol_errors[:5])}'
            if len(trendyol_errors) > 5: message += f' ve {len(trendyol_errors) - 5} diğer...'
        else: message += '\n\nTrendyol fiyatları da başarıyla güncellendi.'
        return jsonify({
            'success': True, 'message': message, 'updated_count': updated_count,
            'trendyol_errors': len(trendyol_errors)
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Model fiyat güncelleme hatası: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Model fiyat güncelleme sırasında hata oluştu: {str(e)}'})


@get_products_bp.route('/api/bulk-delete-products', methods=['POST'])
def bulk_delete_products():
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
            model_id, color = product_info.get('model_id'), product_info.get('color')
            if not model_id or not color: continue
            products = Product.query.filter_by(product_main_id=model_id, color=color).all()
            if not products: continue
            for product in products:
                deleted_items.append({'barcode': product.barcode, 'title': product.title, 'size': product.size})
                db.session.delete(product)
                deleted_count += 1
        if deleted_count > 0:
            log_details = {'total_deleted': deleted_count, 'deleted_items': deleted_items}
            db.session.commit()
            try:
                from user_logs import log_user_action
                log_user_action(action=f"BULK_DELETE_PRODUCTS: {deleted_count} ürün silindi", details=log_details)
            except Exception as e:
                logger.error(f"Kullanıcı log hatası: {e}")
            return jsonify({
                'success': True, 'message': f'Toplam {deleted_count} ürün başarıyla silindi',
                'deleted_count': deleted_count
            })
        else:
            return jsonify({'success': False, 'message': 'Hiçbir ürün silinemedi'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Toplu ürün silme hatası: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Hata oluştu: {str(e)}'})


@get_products_bp.route('/api/get_variants_for_stock_update')
def get_variants_for_stock_update():
    model_id = request.args.get('model')
    if not model_id: return jsonify({'success': False, 'message': 'Model ID eksik.'}), 400
    products = Product.query.filter_by(product_main_id=model_id).order_by(Product.color, Product.size).all()
    variants = [{'barcode': p.barcode, 'color': p.color, 'size': p.size, 'quantity': p.quantity} for p in products]
    return jsonify({'success': True, 'products': variants})

@get_products_bp.route('/api/get_variants_for_cost_update')
def get_variants_for_cost_update():
    model_id = request.args.get('model')
    if not model_id: return jsonify({'success': False, 'message': 'Model ID eksik.'}), 400
    products = Product.query.filter_by(product_main_id=model_id).order_by(Product.color, Product.size).all()
    variants = [{'barcode': p.barcode, 'color': p.color, 'size': p.size, 'cost_usd': p.cost_usd or 0} for p in products]
    return jsonify({'success': True, 'products': variants})

@get_products_bp.route('/api/delete-model', methods=['POST'])
def delete_model():
    model_id = request.form.get('model_id')
    if not model_id: return jsonify({'success': False, 'message': 'Model ID eksik.'})
    try:
        products_to_delete = Product.query.filter_by(product_main_id=model_id).all()
        if not products_to_delete:
            return jsonify({'success': False, 'message': 'Silinecek ürün bulunamadı.'})
        for product in products_to_delete:
            db.session.delete(product)
        db.session.commit()
        return jsonify({'success': True, 'message': f"'{model_id}' modeli ve tüm varyantları başarıyla silindi."})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Model silinirken hata oluştu: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Bir sunucu hatası oluştu.'})

@get_products_bp.route('/api/get_model_info')
def get_model_info():
    model_id = request.args.get('model_id')
    if not model_id: return jsonify({'success': False, 'message': 'Model ID eksik.'}), 400
    product = Product.query.filter_by(product_main_id=model_id).first()
    if product:
        return jsonify({'success': True, 'sale_price': product.sale_price or 0, 'cost_usd': product.cost_usd or 0})
    else:
        return jsonify({'success': False, 'message': 'Ürün bulunamadı.'}), 404