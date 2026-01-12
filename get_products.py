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
from sqlalchemy import func
from login_logout import roles_required
from sqlalchemy.dialects.postgresql import insert
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID
from models import db, Product, ProductArchive, RafUrun, CentralStock
from cache_config import cache, CACHE_TIMES
from sqlalchemy import event

get_products_bp = Blueprint('get_products', __name__)



load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('get_products.log')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

BASE_URL = "https://apigw.trendyol.com/integration/"

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
            timeout = aiohttp.ClientTimeout(total=10)
            async with session.get(url, timeout=timeout) as response:
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
        # Sadece anahtar değil, tüm ürün listesini ekle
        if key not in grouped_products:
            grouped_products[key] = []
        grouped_products[key].append(product)

    # Her grubu bedene göre sırala
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


"""async def fetch_all_product_stocks_async():
    all_products = await fetch_all_products_async()
    if not all_products:
        return []
    return [
        {
            "barcode": p.get("barcode"),
            "quantity": p.get("quantity", 0)
        }
        for p in all_products if p.get("barcode")
    ]"""



@get_products_bp.route('/update_products', methods=['POST'])
async def update_products_route():
    """
    Trendyol ürün senkronu (tam): 
    1) approved=true & archived=false ürünleri çek
    2) DB'ye upsert et
    3) Trendyol'da archived=true olanları DB'den sil
    4) Aktif listede görünmeyenleri (Trendyol'dan kalkmış) DB'den sil
    """
    try:
        logger.debug("Trendyol'dan ürün çekme başlıyor (approved=true, archived=false).")
        products = await fetch_all_products_async()

        if products is None:
            raise ValueError("Trendyol API yanıtı None döndü.")

        if not isinstance(products, list):
            logger.error(f"Beklenmeyen veri türü: {type(products)} - İçerik: {products}")
            raise ValueError("Trendyol ürün verisi liste değil.")

        logger.debug(f"Trendyol'dan çekilen aktif ürün sayısı: {len(products)}")

        if products:
            # 1) Upsert
            logger.debug("Ürünler veritabanına kaydediliyor/güncelleniyor...")
            await save_products_to_db_async(products)

            # 2) Silinecekleri senkronla
            logger.debug("Trendyol'da silinen/archived ürünlerin DB senkronu başlıyor...")
            sync_result = await sync_trendyol_deletions(products)


            msg = (f"Ürünler güncellendi. "
                   f"Arşivde olanlardan silinen: {sync_result.get('deleted_archived', 0)}, "
                   f"Aktif listede görünmeyip silinen: {sync_result.get('deleted_inactive', 0)}.")
            logger.info(msg)
            flash(msg, "info")

            logger.info("Ürün senkronu başarıyla tamamlandı.")
            flash('Ürünler başarıyla güncellendi.', 'success')
        else:
            logger.warning("Trendyol'dan ürün gelmedi (aktif liste boş).")
            # Aktif liste boş gelirse, tüm DB’yi silmek istemeyiz; bilerek dokunmuyoruz.
            flash('Aktif ürün bulunamadı. (Trendyol liste boş döndü)', 'warning')

    except Exception as e:
        logger.error(f"update_products_route hata: {e}", exc_info=True)
        flash('Ürünler güncellenirken bir hata oluştu.', 'danger')

    return redirect(url_for('get_products.product_list'))


"""@get_products_bp.route('/update_stocks_route', methods=['POST'])
async def update_stocks_route():
    logger.info("Trendyol'dan stokları çekme ve veritabanını güncelleme işlemi başlatıldı.")

    if not all([API_KEY, API_SECRET, SUPPLIER_ID]):
        msg = "Trendyol API bilgileri sunucuda eksik. Stoklar çekilemez."
        logger.error(msg)
        return jsonify({'success': False, 'message': msg})

    try:
        # 1. YENİ VE VERİMLİ FONKSİYON: Trendyol'dan SADECE stokları çek
        trendyol_stock_data = await fetch_all_product_stocks_async()

        if trendyol_stock_data is None: # Fonksiyon hata dönerse None gelir
            logger.error("Trendyol'dan stok bilgisi çekilemedi veya API hatası oluştu.")
            return jsonify({'success': False, 'message': 'Trendyol API hatası nedeniyle stoklar çekilemedi.'})

        if not trendyol_stock_data:
            logger.warning("Trendyol'dan hiç stok bilgisi gelmedi.")
            return jsonify({'success': True, 'message': 'Trendyol\'dan güncellenecek stok bilgisi bulunamadı.'})

        # 2. Trendyol verisinden barkod -> miktar eşleşmesini oluştur
        barcode_quantity_map = {
            p.get('barcode'): int(p.get('quantity', 0))
            for p in trendyol_stock_data if p.get('barcode')
        }

        if not barcode_quantity_map:
            logger.info("Trendyol'dan geçerli barkod/miktar bilgisi alınamadı.")
            return jsonify({'success': False, 'message': 'Trendyol\'dan güncellenecek stok bilgisi (geçerli barkod) alınamadı.'})

        # 3. Kendi veritabanındaki ürünlerin stoğunu güncelle
        all_db_products = Product.query.filter(Product.barcode.in_(barcode_quantity_map.keys())).all()
        logger.debug(f"Veritabanından Trendyol barkodlarına karşılık gelen toplam ürün sayısı: {len(all_db_products)}")

        updated_count = 0
        for product in all_db_products:
            trendyol_quantity = barcode_quantity_map.get(product.barcode)

            # Sadece miktar gerçekten değişmişse güncelle
            if trendyol_quantity is not None and product.quantity != trendyol_quantity:
                logger.debug(f"DB Stoğu Güncelleniyor: Barkod {product.barcode}, Eski: {product.quantity}, Yeni (Trendyol): {trendyol_quantity}")
                product.quantity = trendyol_quantity
                db.session.add(product)
                updated_count += 1

        # 4. Veritabanı değişikliklerini tek seferde kaydet
        if updated_count > 0:
            try:
                db.session.commit()
                logger.info(f"Veritabanında {updated_count} ürün stoğu başarıyla güncellendi.")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Veritabanına stok güncellenirken commit hatası: {e}", exc_info=True)
                return jsonify({'success': False, 'message': f'Veritabanı commit hatası: {str(e)}'})
        else:
            logger.info("Veritabanında güncellenecek stok farkı olan ürün bulunamadı.")

        return jsonify({'success': True, 'message': f'Stoklar başarıyla Trendyol\'dan çekildi. Veritabanında {updated_count} ürün güncellendi.'})

    except Exception as e:
        db.session.rollback()
        logger.error(f"update_stocks_route sırasında genel hata: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Stok güncelleme sırasında genel bir sunucu hatası oluştu: {str(e)}'})"""



async def save_products_to_db_async(products):
    products = [p for p in products if isinstance(p, dict)]
    archived_barcodes = {x.barcode for x in ProductArchive.query.with_entities(ProductArchive.barcode).all()}

    images_folder = os.path.join(current_app.root_path, 'static', 'images')
    os.makedirs(images_folder, exist_ok=True)

    product_objects = []
    seen_barcodes = set()
    image_downloads = [] # DÜZELTME: İndirilecek görseller için boş liste oluşturuldu.

    for product_data in products:
        original_barcode = product_data.get('barcode', '').strip().lower()  # 🔧 Küçük harfe normalize et
        if not original_barcode or original_barcode in seen_barcodes or original_barcode in archived_barcodes:
            continue
        seen_barcodes.add(original_barcode)

        def safe_datetime_from_timestamp(ts):
            if not ts: return None
            try: return datetime.fromtimestamp(int(ts) / 1000)
            except (ValueError, TypeError, OSError): return None

        last_update_date_obj = safe_datetime_from_timestamp(product_data.get('lastUpdateDate'))
        create_date_time_obj = safe_datetime_from_timestamp(product_data.get('createDateTime'))

        # DÜZELTME 1: GÖRSEL İNDİRME LİSTESİNİ DOLDURMA MANTIĞI EKLENDİ
        image_urls = [img.get('url', '') for img in product_data.get('images', []) if isinstance(img, dict)]
        images_path_db = ''
        if image_urls and image_urls[0]:
            image_url = image_urls[0]
            parsed_url = urlparse(image_url)
            image_extension = os.path.splitext(parsed_url.path)[1] or '.jpg'
            image_filename = f"{original_barcode}{image_extension.lower()}"
            image_path_local = os.path.join(images_folder, image_filename)
            images_path_db = f"/static/images/{image_filename}"
            # İndirme listesine (url, yerel_dosya_yolu) olarak ekle
            image_downloads.append((image_url, image_path_local))

        # DÜZELTME 2: STATÜ BİLGİSİNİ ANLAMLI METNE ÇEVİRME
        status_str = "Beklemede" # Varsayılan
        if product_data.get('rejected'):
            status_str = "Reddedildi"
        elif product_data.get('approved'):
            status_str = "Onaylandı"
        if product_data.get('archived'):
            status_str = f"{status_str} (Arşivde)"

        size = next((attr.get('attributeValue', 'N/A') for attr in product_data.get('attributes', []) if attr.get('attributeName') == 'Beden'), 'N/A')
        color = next((attr.get('attributeValue', 'N/A') for attr in product_data.get('attributes', []) if attr.get('attributeName') == 'Renk'), 'N/A')

        product_objects.append({
            "barcode": original_barcode,
            "title": product_data.get('title'),
            "images": images_path_db, # Görselin veritabanına kaydedilecek yolu
            "product_main_id": product_data.get('productMainId'),
            "size": size, "color": color,
            "archived": product_data.get('archived', False),
            "locked": product_data.get('locked', False),
            "on_sale": product_data.get('onSale', False),
            "sale_price": product_data.get('salePrice', 0),
            "list_price": product_data.get('listPrice', 0),
            "currency_type": product_data.get('currencyType'),
            "description": product_data.get('description'),
            "attributes": json.dumps(product_data.get('attributes', [])),
            "reject_reason": '; '.join([r.get('reason', 'N/A') for r in product_data.get('rejectReasonDetails', [])]),
            "brand": product_data.get('brand'),
            "category_name": product_data.get('categoryName'),
            "vat_rate": product_data.get('vatRate'),
            "status": status_str, # DÜZELTME: Artık anlamlı metin olarak kaydediliyor
            "gtin": product_data.get('gtin'),
            "last_update_date": last_update_date_obj,
            "brand_id": product_data.get('brandId'),
            "create_date_time": create_date_time_obj,
            "gender": product_data.get('gender'),
            "has_active_campaign": product_data.get('hasActiveCampaign'),
            "trendyol_id": product_data.get('id'),
            "pim_category_id": product_data.get('pimCategoryId'),
            "platform_listing_id": product_data.get('platformListingId'),
            "product_code": product_data.get('productCode'),
            "product_content_id": product_data.get('productContentId'),
            "stock_unit_type": product_data.get('stockUnitType'),
            "supplier_id": product_data.get('supplierId'),
            "is_rejected": product_data.get('rejected'),
            "is_blacklisted": product_data.get('blacklisted'),
            "has_html_content": product_data.get('hasHtmlContent'),
            "product_url": product_data.get('productUrl'),
            "is_approved": product_data.get('approved')
        })

    if not product_objects: return

    # Veritabanına toplu kayıt/güncelleme
    batch_size = 200
    for i in range(0, len(product_objects), batch_size):
        batch = product_objects[i:i + batch_size]
        insert_stmt = insert(Product).values(batch)

        set_payload = {
            'title': insert_stmt.excluded.title, 
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
            'images': insert_stmt.excluded.images # Görsel yolu değişirse diye bunu da ekleyelim
        }

        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=['barcode'],
            set_=set_payload
        )
        db.session.execute(upsert_stmt)

    db.session.commit()

    # DÜZELTME 1 (devamı): GÖRSELLERİ İNDİRME KISMI EKLENDİ
    if image_downloads:
        logger.info(f"{len(image_downloads)} adet yeni görsel indirilecek...")
        # Bu fonksiyonun dosyanın başka bir yerinde tanımlı olduğundan emin ol
        await download_images_async(image_downloads) 
        logger.info("Tüm görsellerin indirme işlemi tamamlandı.")

    flash("Tüm ürün verileri başarıyla veritabanına kaydedildi/güncellendi.", "success")
    
async def fetch_all_products_async():
    """Sadece onaylı ve arşivde olmayan ürünleri Trendyol'dan çeker."""
    all_products = []
    page_size = 1000
    url = f"{BASE_URL}product/sellers/{SUPPLIER_ID}/products"
    credentials = f"{API_KEY}:{API_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    headers = {"Authorization": f"Basic {encoded_credentials}"}

    base_params = {
        "size": page_size,
        "approved": "true",
        "archived": "false"
    }

    async with aiohttp.ClientSession() as session:
        timeout = aiohttp.ClientTimeout(total=60)
        try:
            # İlk sayfa
            params = {"page": 0, **base_params}
            async with session.get(url, headers=headers, params=params, timeout=timeout) as response:
                response.raise_for_status()
                data = await response.json()
                total_pages = data.get('totalPages', 1)
                logging.info(f"Toplam ürün detay sayfası sayısı: {total_pages}")
                if 'content' in data and isinstance(data['content'], list):
                    all_products.extend(data['content'])

                # Diğer sayfalar
                tasks = [
                    fetch_products_page(session, url, headers, {"page": page_number, **base_params})
                    for page_number in range(1, total_pages)
                ]
                pages_data = await asyncio.gather(*tasks)
                for page in pages_data:
                    if isinstance(page, list):
                        all_products.extend(page)
        except Exception as e:
            logger.error(f"fetch_all_products_async hata: {e}", exc_info=True)
            return None

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
                logging.debug(f"Sayfa {params.get('page', 'N/A')} başarıyla çekildi, içerik boyutu: {len(data['content'])}")
                return data.get('content', [])
            except Exception as e:
                error_text = await response.text()
                logging.error(f"JSON çözümleme hatası: {e} - Yanıt: {error_text}")
                return []
    except Exception as e:
        logging.error(f"fetch_products_page hata: {e}")
        return []


async def download_images_async(image_urls):
    if not image_urls:
        logger.info("İndirilecek görsel bulunmuyor")
        return

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = []
        semaphore = asyncio.Semaphore(50)  # Daha az eşzamanlı indirme
        for image_url, image_path in image_urls:
            tasks.append(download_image(session, image_url, image_path, semaphore))

        # Tüm indirmeleri bekle ve hataları yakala
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
            # Dizin yoksa oluştur
            os.makedirs(os.path.dirname(image_path), exist_ok=True)

            async with session.get(image_url) as response:
                if response.status != 200:
                    logger.warning(f"Resim indirme hatası: {response.status} - {image_url}")
                    return False

                content = await response.read()
                if len(content) < 100:  # Çok küçük dosyalar muhtemelen hatalı
                    logger.warning(f"Geçersiz görsel boyutu: {len(content)} bytes - {image_url}")
                    return False

                with open(image_path, 'wb') as img_file:
                    img_file.write(content)

                logger.debug(f"Resim kaydedildi: {os.path.basename(image_path)}")
                return True

        except Exception as e:
            logger.error(f"Resim indirme hatası ({os.path.basename(image_path)}): {e}")
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
            'sale_price': insert_stmt.excluded.sale_price,
            'list_price': insert_stmt.excluded.list_price,
            'images': insert_stmt.excluded.images,
            'size': insert_stmt.excluded.size,
            'color': insert_stmt.excluded.color,
            # YENİ: Güncellenecek alanlar
            'description': insert_stmt.excluded.description,
            'attributes': insert_stmt.excluded.attributes,
        }
    )
    db.session.execute(upsert_stmt)
    db.session.commit()


@get_products_bp.route('/fetch-products')
async def fetch_products_route():
    try:
        products = await fetch_all_products_async()  # filtreli çağrı (approved=true, archived=false)
        if products:
            await save_products_to_db_async(products)  # save içi: archived/approved/blacklisted ikinci süzgeç
            
            # Kullanıcı işlemini logla
            try:
                from user_logs import log_user_action
                log_details = {
                    'sayfa': 'Ürün Listesi',
                    'çekilen_ürün_sayısı': len(products),
                    'işlem_açıklaması': f'Trendyol\'dan {len(products)} ürün başarıyla çekildi ve veritabanına kaydedildi'
                }
                log_user_action(
                    action='FETCH',
                    details=log_details
                )
            except Exception as e:
                logger.error(f"Kullanıcı log hatası: {e}")
                
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

        archived_count = len(products)
        
        for product in products:
            # Tüm alanları dinamik olarak kopyala
            archive_data = {c.name: getattr(product, c.name) for c in product.__table__.columns}
            archive_data['archived'] = True # Arşivlendi olarak işaretle

            archive_product = ProductArchive(**archive_data)
            db.session.add(archive_product)
            db.session.delete(product)

        db.session.commit()
        
        # Kullanıcı işlemini logla
        try:
            from user_logs import log_user_action
            log_details = {
                'sayfa': 'Ürün Listesi',
                'model_kodu': product_main_id,
                'arşivlenen_adet': archived_count,
                'işlem_açıklaması': f'{product_main_id} model koduna ait {archived_count} ürün arşivlendi'
            }
            log_user_action(
                action='ARCHIVE',
                details=log_details
            )
        except Exception as e:
            logger.error(f"Kullanıcı log hatası: {e}")
            
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

        restored_count = len(archived_products)
        
        for archived in archived_products:
            # Tüm alanları dinamik olarak kopyala
            product_data = {c.name: getattr(archived, c.name) for c in archived.__table__.columns if hasattr(Product, c.name)}
            product_data['archived'] = False # Arşivden çıkarıldı olarak işaretle

            # archive_date gibi Product modelinde olmayan alanları kaldır
            product_data.pop('archive_date', None)

            product = Product(**product_data)
            db.session.add(product)
            db.session.delete(archived)

        db.session.commit()
        
        # Kullanıcı işlemini logla
        try:
            from user_logs import log_user_action
            log_details = {
                'sayfa': 'Ürün Listesi',
                'model_kodu': product_main_id,
                'geri_yüklenen_adet': restored_count,
                'işlem_açıklaması': f'{product_main_id} model koduna ait {restored_count} ürün arşivden geri yüklendi'
            }
            log_user_action(
                action='RESTORE',
                details=log_details
            )
        except Exception as e:
            logger.error(f"Kullanıcı log hatası: {e}")
            
        return jsonify({'success': True, 'message': 'Ürünler başarıyla arşivden çıkarıldı'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Arşivden geri yükleme hatası: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)})


def group_products_by_model_and_then_color(products):
    """Ürünleri önce modele, sonra renge göre hiyerarşik olarak gruplar."""
    grouped_by_model = {}
    for product in products:
        model_id = product.product_main_id
        if not model_id:
            continue

        # Model için anahtar daha önce oluşturulmadıysa oluştur
        if model_id not in grouped_by_model:
            grouped_by_model[model_id] = {
                'main_product_info': product, # Ana görsel, başlık vs. için temsilci ürün
                'colors': {}
            }

        color = product.color or 'Diğer'
        # Renk için anahtar daha önce oluşturulmadıysa oluştur
        if color not in grouped_by_model[model_id]['colors']:
            grouped_by_model[model_id]['colors'][color] = []

        grouped_by_model[model_id]['colors'][color].append(product)

    # Her rengin içindeki bedenleri numaraya göre büyükten küçüğe sırala
    for model_id, data in grouped_by_model.items():
        for color, variants in data['colors'].items():
            try:
                data['colors'][color] = sorted(variants, key=lambda x: float(x.size), reverse=True)
            except (ValueError, TypeError):
                data['colors'][color] = sorted(variants, key=lambda x: x.size, reverse=True)

    return grouped_by_model


# get_products.py içindeki GÜNCELLENECEK ROUTE
@get_products_bp.route('/product_list')
def product_list():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 12

        # Ürünleri çek
        all_products = Product.query.order_by(Product.product_main_id).all()

        # CentralStock map
        cs_rows = db.session.query(CentralStock.barcode, CentralStock.qty).all()
        cs_map = {b: int(q or 0) for b, q in cs_rows}

        # Raf map
        raf_rows = RafUrun.query.with_entities(RafUrun.urun_barkodu, RafUrun.raf_kodu).all()
        raf_map = {b: rk for b, rk in raf_rows}

        # Görünüm için CENTRAL stok ile override
        for p in all_products:
            p.raf_bilgisi = raf_map.get(p.barcode)
            p.central_qty = cs_map.get(p.barcode, 0)
            p.quantity = p.central_qty  # şablon {{ variant.quantity }} ise artık central_stock görünür

        # Model → Renk → Ürün hiyerarşisi
        hierarchical_products = group_products_by_model_and_then_color(all_products)

        # Sayfalama
        model_keys = sorted(hierarchical_products.keys())
        total_models = len(model_keys)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        current_page_keys = model_keys[start_idx:end_idx]
        current_page_products = {k: hierarchical_products[k] for k in current_page_keys}
        total_pages = (total_models + per_page - 1) // per_page

        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total_models,
            'pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None,
            'iter_pages': lambda left_edge=1, right_edge=1, left_current=2, right_current=2:
                range(max(1, page - left_current), min(total_pages, page + right_current) + 1)
        }

        return render_template(
            'product_list.html',
            grouped_products=current_page_products,
            pagination=pagination,
            search_mode=False
        )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Ürün listesi oluşturulurken hata: {e}", exc_info=True)
        flash("Ürün listesi yüklenirken bir hata oluştu.", "danger")
        return render_template('product_list.html', grouped_products={}, pagination=None)



@get_products_bp.route('/api/get_product_variants', methods=['GET'])
def get_product_variants():
    model_id = request.args.get('model', '').strip()
    color = request.args.get('color', '').strip()
    if not model_id or not color:
        return jsonify({'success': False, 'message': 'Model veya renk bilgisi eksik.'})

    try:
        rows = (
            db.session.query(
                Product.size.label('size'),
                Product.barcode.label('barcode'),
                CentralStock.qty.label('qty')
            )
            .outerjoin(CentralStock, CentralStock.barcode == Product.barcode)
            .filter(func.lower(Product.product_main_id) == model_id.lower(),
                    func.lower(Product.color) == color.lower())
            .all()
        )

        products_list = [
            {'size': r.size, 'barcode': r.barcode, 'quantity': int(r.qty or 0)}
            for r in rows
        ]

        try:
            products_list.sort(key=lambda x: float(x['size']), reverse=True)
        except (ValueError, TypeError):
            products_list.sort(key=lambda x: str(x['size']), reverse=True)

        return jsonify({'success': True, 'products': products_list})
    except Exception as e:
        logger.error(f"get_product_variants hata: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Sunucu hatası.'}), 500


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
            'sayfa': 'Ürün Listesi',
            'model_kodu': model_id,
            'renk': color,
            'silinen_adet': len(products),
            'barkodlar': ', '.join([p.barcode for p in products][:5]) + (f' (+{len(products)-5} daha)' if len(products) > 5 else ''),
            'işlem_açıklaması': f'{model_id} model kodu ve {color} rengine ait {len(products)} ürün silindi'
        }

        # Ürünleri sil
        for product in products:
            db.session.delete(product)

        db.session.commit()

        # Kullanıcı işlemini logla
        try:
            from user_logs import log_user_action
            log_user_action(
                action='DELETE_PRODUCTS',
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
# Arama fonksiyonu - İSTEĞE GÖRE GÜNCELLENMİŞ HALİ
############################################
@get_products_bp.route('/search_products')
def search_products():
    query = request.args.get('query', '').strip()
    search_type = request.args.get('search_type', 'model_code').strip()

    if not query:
        return redirect(url_for('get_products.product_list'))

    # Ürünleri bul
    if search_type == 'model_code':
        found_products = Product.query.filter(func.lower(Product.product_main_id) == query.lower()).all()
    elif search_type == 'barcode':
        pbb = Product.query.filter_by(barcode=query).first()
        found_products = Product.query.filter_by(product_main_id=pbb.product_main_id).all() if pbb and pbb.product_main_id else []
    else:
        found_products = []

    # CENTRAL stok ve raf bilgisini iliştir + quantity override
    if found_products:
        bcs = [p.barcode for p in found_products]
        cs_rows = db.session.query(CentralStock.barcode, CentralStock.qty).filter(CentralStock.barcode.in_(bcs)).all()
        cs_map = {b: int(q or 0) for b, q in cs_rows}
        raf_rows = RafUrun.query.filter(RafUrun.urun_barkodu.in_(bcs)).all()
        raf_map = {r.urun_barkodu: r.raf_kodu for r in raf_rows}
        for p in found_products:
            p.raf_bilgisi = raf_map.get(p.barcode)
            p.central_qty = cs_map.get(p.barcode, 0)
            p.quantity = p.central_qty

    # (model, renk) gruplu gönder
    grouped_results = group_products_by_model_and_color(found_products)

    return render_template(
        'product_list.html',
        grouped_products=grouped_results,
        pagination=None,
        search_mode=True,
        search_query=query,
        search_type=search_type
    )



@get_products_bp.route('/api/delete-product', methods=['POST'])
@roles_required('admin', 'manager')
def delete_product_api():
    """
    API endpoint for deleting all variants of a product by model ID and color
    """
    from utils import error_response, success_response, validation_error_response
    
    try:
        model_id = request.form.get('model_id')
        color = request.form.get('color')

        # Validasyon
        if not model_id or not color:
            return validation_error_response({
                'model_id': 'Model ID gereklidir' if not model_id else None,
                'color': 'Renk gereklidir' if not color else None
            })

        # Bu modele ve renge ait tüm ürünleri bul
        products = Product.query.filter_by(product_main_id=model_id, color=color).all()

        if not products:
            return error_response(
                'Silinecek ürün bulunamadı',
                status_code=404,
                error_code='NOT_FOUND'
            )

        # İşlem logunu hazırla
        log_details = {
            'sayfa': 'Ürün Listesi',
            'model_kodu': model_id,
            'renk': color,
            'silinen_adet': len(products),
            'barkodlar': ', '.join([p.barcode for p in products][:5]) + (f' (+{len(products)-5} daha)' if len(products) > 5 else ''),
            'işlem_açıklaması': f'{model_id} model kodu ve {color} rengine ait {len(products)} ürün silindi'
        }

        # Ürünleri sil
        for product in products:
            db.session.delete(product)

        db.session.commit()

        # Kullanıcı işlemini logla
        try:
            from user_logs import log_user_action
            log_user_action(
                action='DELETE_PRODUCTS',
                details=log_details
            )
        except Exception as e:
            logger.error(f"Kullanıcı log hatası: {e}")

        return success_response(
            f'Toplam {len(products)} ürün başarıyla silindi',
            data={'deleted_count': len(products)}
        )

    except Exception as e:
        db.session.rollback()
        logger.error(f"Ürün silme hatası: {e}", exc_info=True)
        return error_response(
            'Ürün silinirken hata oluştu',
            status_code=500,
            error_code='DATABASE_ERROR'
        )

@get_products_bp.route('/product_label')
def product_label():
    return render_template('product_label.html')


@get_products_bp.route('/api/get_variants_with_cost', methods=['GET'])
def get_variants_with_cost():
    model = request.args.get('model', '').strip()
    color = request.args.get('color', '').strip()
    if not model or not color:
        return jsonify({'success': False, 'message': 'Model veya renk eksik.'})

    try:
        rows = (
            db.session.query(
                Product.barcode.label('barcode'),
                Product.size.label('size'),
                Product.cost_usd.label('cost_usd'),
                Product.cost_try.label('cost_try'),
                CentralStock.qty.label('qty')
            )
            .outerjoin(CentralStock, CentralStock.barcode == Product.barcode)
            .filter(func.lower(Product.product_main_id) == model.lower(),
                    func.lower(Product.color) == color.lower())
            .all()
        )

        variants = [
            {
                'barcode': r.barcode,
                'size': r.size,
                'quantity': int(r.qty or 0),
                'cost_usd': float(r.cost_usd or 0),
                'cost_try': float(r.cost_try or 0),
            }
            for r in rows if r.barcode and r.barcode != 'undefined'
        ]

        try:
            variants.sort(key=lambda x: float(x['size']), reverse=True)
        except (ValueError, TypeError):
            variants.sort(key=lambda x: str(x['size']), reverse=True)

        return jsonify({'success': True, 'products': variants})
    except Exception as e:
        logger.error(f"get_variants_with_cost hata: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Sunucu hatası.'}), 500



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
@roles_required('admin', 'manager')
def update_product_cost():
    model_id = request.form.get('model_id', '').strip()
    cost_usd_str = request.form.get('cost_usd')
    if not model_id:
        return jsonify({'success': False, 'message': 'Model ID gerekli'})
    try:
        if cost_usd_str is None or cost_usd_str == '':
            cost_usd = 0.0
        else:
            cost_usd = float(cost_usd_str)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Geçerli bir maliyet değeri giriniz'})
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    usd_rate = loop.run_until_complete(fetch_usd_rate())
    loop.close()
    if not usd_rate or usd_rate is None:
        usd_rate = 1.0
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
        
        # Kullanıcı işlemini logla
        try:
            from user_logs import log_user_action
            log_details = {
                'sayfa': 'Ürün Listesi',
                'model_kodu': model_id,
                'güncellenen_adet': len(products),
                'yeni_maliyet_usd': f'{cost_usd:.2f} USD',
                'yeni_maliyet_try': f'{cost_usd * usd_rate:.2f} TL',
                'usd_kuru': f'{usd_rate:.4f}',
                'işlem_açıklaması': f'{model_id} model koduna ait {len(products)} ürünün maliyeti güncellendi'
            }
            log_user_action(
                action='COST_UPDATE',
                details=log_details
            )
        except Exception as e:
            logger.error(f"Kullanıcı log hatası: {e}")
            
        return jsonify({'success': True, 'message': 'Ürün maliyetleri güncellendi'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Maliyet güncelleme hatası: {e}")
        return jsonify({'success': False, 'message': f'Bir hata oluştu: {str(e)}'})


@get_products_bp.route('/api/update_product_prices', methods=['POST'])
@roles_required('admin', 'manager')
def update_product_prices():
    """Ürün varyantlarının satış fiyatlarını günceller"""
    try:
        # Yetki kontrolü
        if not session.get('user_id'):
            return jsonify({'success': False, 'message': 'Oturum açmanız gerekli'})

        user_role = session.get('role', '').lower()
        if user_role != 'admin':
            return jsonify({'success': False, 'message': 'Bu işlem için admin yetkisine sahip değilsiniz'})

        updated_count = 0
        errors = []
        price_updates = []

        for key, value in request.form.items():
            if key and value:  # Boş olmayan değerler
                try:
                    barcode = key
                    new_price = float(value)

                    product = Product.query.filter_by(barcode=barcode).first()
                    if product:
                        product.sale_price = new_price
                        db.session.add(product)
                        updated_count += 1
                        price_updates.append((barcode, new_price))
                    else:
                        errors.append(f"Barkod {barcode} bulunamadı")

                except (ValueError, TypeError):
                    errors.append(f"Geçersiz fiyat değeri: {value}")
                except Exception as e:
                    errors.append(f"Barkod {key} güncellenirken hata: {str(e)}")

        if updated_count > 0:
            db.session.commit()
            
            # Kullanıcı işlemini logla
            try:
                from user_logs import log_user_action
                log_details = {
                    'sayfa': 'Ürün Listesi',
                    'güncellenen_adet': updated_count,
                    'işlem_açıklaması': f'{updated_count} ürünün satış fiyatı güncellendi',
                    'güncellenen_ürünler': ', '.join([f'{barcode}: {price}₺' for barcode, price in price_updates[:5]]) + 
                                           (f' (+{updated_count-5} daha)' if updated_count > 5 else '')
                }
                log_user_action(
                    action='PRICE_UPDATE',
                    details=log_details
                )
            except Exception as e:
                logger.error(f"Kullanıcı log hatası: {e}")

        # Trendyol'da toplu fiyat güncelleme
        trendyol_errors = []
        if price_updates:
            try:
                import asyncio
                trendyol_errors = asyncio.run(update_prices_in_trendyol_bulk(price_updates))
            except Exception as e:
                logger.error(f"Trendyol toplu güncelleme hatası: {e}")
                trendyol_errors = [barcode for barcode, _ in price_updates]

        # Sonuç mesajını hazırla
        message = f"{updated_count} adet ürünün fiyatı güncellendi."
        if trendyol_errors:
            message += f" {len(trendyol_errors)} üründe Trendyol güncellemesi başarısız oldu."
        else:
            message += " Trendyol fiyatları da güncellendi."

        if errors:
            message += f" {len(errors)} hata oluştu."

        return jsonify({
            'success': updated_count > 0,
            'message': message,
            'updated_count': updated_count,
            'trendyol_errors': len(trendyol_errors),
            'errors': errors
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Fiyat güncelleme hatası: {e}")
        return jsonify({'success': False, 'message': f'Fiyat güncelleme sırasında hata oluştu: {str(e)}'})


async def update_prices_in_trendyol_bulk(price_updates):
    """Trendyol'da toplu fiyat güncelleme yapar"""
    try:
        import aiohttp
        import os

        api_key = os.getenv('TRENDYOL_API_KEY')
        secret_key = os.getenv('TRENDYOL_SECRET_KEY') 
        supplier_id = os.getenv('TRENDYOL_SUPPLIER_ID')

        if not all([api_key, secret_key, supplier_id]):
            logger.error("Trendyol API anahtarları eksik")
            return []

        if not price_updates:
            return []

        url = f"https://api.trendyol.com/sapigw/suppliers/{supplier_id}/products/price-and-inventory"

        import base64
        credentials = base64.b64encode(f"{api_key}:{secret_key}".encode()).decode()

        headers = {
            'Authorization': f'Basic {credentials}',
            'Content-Type': 'application/json',
            'User-Agent': f'SupplierId {supplier_id} - SendIntegrationInfo'
        }

        # Tüm fiyat güncellemelerini tek payload'da topla
        items = []
        for barcode, price in price_updates:
            items.append({
                "barcode": barcode,
                "salePrice": price,
                "listPrice": price
            })

        payload = {"items": items}

        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(total=60)
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status == 200:
                    logger.info(f"Trendyol toplu fiyat güncellendi - {len(items)} ürün başarılı")
                    return []  # Başarılı, hata yok
                else:
                    error_text = await response.text()
                    logger.error(f"Trendyol toplu fiyat güncelleme hatası - Status: {response.status}, Error: {error_text}")
                    return [barcode for barcode, _ in price_updates]  # Tüm barkodlar hatalı

    except Exception as e:
        logger.error(f"Trendyol API genel hatası: {e}")
        return [barcode for barcode, _ in price_updates]  # Tüm barkodlar hatalı


@get_products_bp.route('/api/update_model_price', methods=['POST'])
@roles_required('admin', 'manager')
def update_model_price():
    """Bir modelin tüm varyantlarının satış fiyatını günceller"""
    try:
        # Yetki kontrolü
        if not session.get('user_id'):
            return jsonify({'success': False, 'message': 'Oturum açmanız gerekli'})

        user_role = session.get('role', '').lower()
        if user_role != 'admin':
            return jsonify({'success': False, 'message': 'Bu işlem için admin yetkisine sahip değilsiniz'})

        model_id = request.form.get('model_id', '').strip()
        sale_price_str = request.form.get('sale_price', '').strip()

        if not model_id:
            return jsonify({'success': False, 'message': 'Model ID gerekli'})

        if not sale_price_str:
            return jsonify({'success': False, 'message': 'Satış fiyatı gerekli'})

        try:
            sale_price = float(sale_price_str)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Geçerli bir fiyat değeri giriniz'})

        if sale_price < 0:
            return jsonify({'success': False, 'message': 'Fiyat negatif olamaz'})

        # Model ID'ye sahip tüm ürünleri bul
        products = Product.query.filter_by(product_main_id=model_id).all()

        if not products:
            return jsonify({'success': False, 'message': 'Bu model için ürün bulunamadı'})

        # Veritabanında fiyatları güncelle
        updated_count = 0
        price_updates = []

        for product in products:
            product.sale_price = sale_price
            db.session.add(product)
            updated_count += 1
            price_updates.append((product.barcode, sale_price))

        db.session.commit()
        
        # Kullanıcı işlemini logla
        try:
            from user_logs import log_user_action
            log_details = {
                'sayfa': 'Ürün Listesi',
                'model_kodu': model_id,
                'güncellenen_adet': updated_count,
                'yeni_fiyat': f'{sale_price:.2f} TL',
                'işlem_açıklaması': f'{model_id} model koduna ait {updated_count} varyantın fiyatı {sale_price:.2f} TL olarak güncellendi'
            }
            log_user_action(
                action='PRICE_UPDATE',
                details=log_details
            )
        except Exception as e:
            logger.error(f"Kullanıcı log hatası: {e}")

        # Trendyol'da toplu fiyat güncelleme
        trendyol_errors = []
        if price_updates:
            try:
                import asyncio
                trendyol_errors = asyncio.run(update_prices_in_trendyol_bulk(price_updates))
            except Exception as e:
                logger.error(f"Trendyol toplu güncelleme hatası: {e}")
                trendyol_errors = [barcode for barcode, _ in price_updates]

        # Sonuç mesajını hazırla
        message = f'{model_id} modeli için {updated_count} varyantın fiyatı {sale_price} TL olarak güncellendi'

        if trendyol_errors:
            message += f'\n\nUyarı: {len(trendyol_errors)} üründe Trendyol fiyat güncellemesi başarısız oldu.'
            message += f'\nSorunlu barkodlar: {", ".join(trendyol_errors[:5])}'
            if len(trendyol_errors) > 5:
                message += f' ve {len(trendyol_errors) - 5} diğer...'
        else:
            message += '\n\nTrendyol fiyatları da başarıyla güncellendi.'

        return jsonify({
            'success': True,
            'message': message,
            'updated_count': updated_count,
            'trendyol_errors': len(trendyol_errors)
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Model fiyat güncelleme hatası: {e}")
        return jsonify({'success': False, 'message': f'Model fiyat güncelleme sırasında hata oluştu: {str(e)}'})


@get_products_bp.route('/api/update-woo-mapping', methods=['POST'])
@roles_required('admin', 'manager')
def update_woo_mapping():
    """Bir ürünün WooCommerce mapping bilgilerini günceller"""
    try:
        # Yetki kontrolü
        if not session.get('user_id'):
            return jsonify({'success': False, 'message': 'Oturum açmanız gerekli'})

        barcode = request.form.get('barcode', '').strip()
        woo_product_id_str = request.form.get('woo_product_id', '').strip()
        woo_barcode = request.form.get('woo_barcode', '').strip()

        if not barcode:
            return jsonify({'success': False, 'message': 'Barkod gerekli'})

        # Ürünü bul
        product = Product.query.filter_by(barcode=barcode).first()
        if not product:
            return jsonify({'success': False, 'message': 'Ürün bulunamadı'})

        # Woo Product ID'yi kontrol et ve kaydet
        woo_product_id = None
        if woo_product_id_str:
            try:
                woo_product_id = int(woo_product_id_str)
            except (ValueError, TypeError):
                return jsonify({'success': False, 'message': 'Geçersiz WooCommerce Product ID'})

        # Güncelleme yap
        old_woo_id = product.woo_product_id
        old_woo_barcode = product.woo_barcode
        
        product.woo_product_id = woo_product_id
        product.woo_barcode = woo_barcode if woo_barcode else None
        
        db.session.add(product)
        db.session.commit()

        # Kullanıcı işlemini logla
        try:
            from user_logs import log_user_action
            log_details = {
                'sayfa': 'Ürün Listesi',
                'barkod': barcode,
                'eski_woo_id': old_woo_id,
                'yeni_woo_id': woo_product_id,
                'eski_woo_barcode': old_woo_barcode,
                'yeni_woo_barcode': woo_barcode,
                'işlem_açıklaması': f'{barcode} barkodlu ürünün WooCommerce mapping bilgileri güncellendi'
            }
            log_user_action(
                action='WOO_MAPPING_UPDATE',
                details=log_details
            )
        except Exception as e:
            logger.error(f"Kullanıcı log hatası: {e}")

        message = f'WooCommerce mapping bilgileri başarıyla güncellendi.'
        if woo_product_id:
            message += f' Woo ID: {woo_product_id}'
        if woo_barcode:
            message += f', Woo Barkod: {woo_barcode}'

        return jsonify({
            'success': True,
            'message': message,
            'woo_product_id': woo_product_id,
            'woo_barcode': woo_barcode
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Woo mapping güncelleme hatası: {e}")
        return jsonify({'success': False, 'message': f'Güncelleme sırasında hata oluştu: {str(e)}'})


@get_products_bp.route('/api/bulk-delete-products', methods=['POST'])
@roles_required('admin', 'manager')
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
                'sayfa': 'Ürün Listesi',
                'silinen_toplam_adet': deleted_count,
                'işlem_açıklaması': f'Toplu silme işlemi ile {deleted_count} ürün silindi',
                'silinen_ürünler': ', '.join([f"{item['title']} ({item['barcode']})" for item in deleted_items[:5]]) + 
                                   (f' (+{deleted_count-5} daha)' if deleted_count > 5 else '')
            }

            db.session.commit()

            # Kullanıcı işlemini logla
            try:
                from user_logs import log_user_action
                log_user_action(
                    action='BULK_DELETE_PRODUCTS',
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



@get_products_bp.route('/api/get_variants_for_stock_update')
def get_variants_for_stock_update():
    model_id = request.args.get('model')
    if not model_id:
        return jsonify({'success': False, 'message': 'Model ID eksik.'}), 400

    try:
        products = (Product.query
                    .filter_by(product_main_id=model_id)
                    .order_by(Product.color, Product.size)
                    .all())

        variants = []
        for p in products:
            raflar = RafUrun.query.filter_by(urun_barkodu=p.barcode).all()
            raf_bilgisi = ', '.join([r.raf_kodu for r in raflar]) if raflar else '-'

            cs = CentralStock.query.get(p.barcode)
            qty = int(cs.qty) if cs and cs.qty is not None else 0

            variants.append({
                'barcode': p.barcode,
                'color': p.color,
                'size': p.size,
                'quantity': qty,
                'raf_bilgisi': raf_bilgisi,
                'woo_product_id': p.woo_product_id
            })

        return jsonify({'success': True, 'products': variants})
    except Exception as e:
        logger.error(f"get_variants_for_stock_update hata: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Hata oluştu: {str(e)}'}), 500

    

@get_products_bp.route('/api/get_variants_for_cost_update')
def get_variants_for_cost_update():
    model_id = request.args.get('model')
    if not model_id:
        return jsonify({'success': False, 'message': 'Model ID eksik.'}), 400

    products = Product.query.filter_by(product_main_id=model_id).order_by(Product.color, Product.size).all()
    variants = [{'barcode': p.barcode, 'color': p.color, 'size': p.size, 'cost_usd': p.cost_usd or 0} for p in products]
    return jsonify({'success': True, 'products': variants})
    

@get_products_bp.route('/api/delete-model', methods=['POST'])
@roles_required('admin', 'manager')
def delete_model():
    model_id = request.form.get('model_id')
    if not model_id:
        return jsonify({'success': False, 'message': 'Model ID eksik.'})

    try:
        products_to_delete = Product.query.filter_by(product_main_id=model_id).all()
        if not products_to_delete:
            return jsonify({'success': False, 'message': 'Silinecek ürün bulunamadı.'})

        deleted_count = len(products_to_delete)
        
        for product in products_to_delete:
            db.session.delete(product)

        db.session.commit()
        
        # Kullanıcı işlemini logla
        try:
            from user_logs import log_user_action
            log_details = {
                'sayfa': 'Ürün Listesi',
                'model_kodu': model_id,
                'silinen_toplam_adet': deleted_count,
                'işlem_açıklaması': f'{model_id} model kodu ve tüm varyantları ({deleted_count} ürün) tamamen silindi'
            }
            log_user_action(
                action='DELETE',
                details=log_details
            )
        except Exception as e:
            logger.error(f"Kullanıcı log hatası: {e}")
            
        return jsonify({'success': True, 'message': f"'{model_id}' modeli ve tüm varyantları başarıyla silindi."})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Model silinirken hata oluştu: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Bir sunucu hatası oluştu.'})



@get_products_bp.route('/api/get_model_info')
def get_model_info():
    model_id = request.args.get('model_id')
    if not model_id:
        return jsonify({'success': False, 'message': 'Model ID eksik.'}), 400

    # Modelin herhangi bir varyantını referans olarak alalım
    product = Product.query.filter_by(product_main_id=model_id).first()

    if product:
        return jsonify({
            'success': True,
            'sale_price': product.sale_price or 0,
            'cost_usd': product.cost_usd or 0
        })
    else:
        return jsonify({'success': False, 'message': 'Ürün bulunamadı.'}), 404


async def fetch_archived_barcodes_async():
    """Trendyol'da ARŞİVDE olan ürünlerin barkod listesini döner."""
    page_size = 1000
    url = f"{BASE_URL}product/sellers/{SUPPLIER_ID}/products"
    creds = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {creds}"}

    archived_barcodes = set()
    base_params = {"size": page_size, "archived": "true"}  # sadece arşivdekiler

    async with aiohttp.ClientSession() as session:
        timeout = aiohttp.ClientTimeout(total=60)
        # İlk sayfa
        async with session.get(url, headers=headers, params={**base_params, "page": 0}, timeout=timeout) as resp:
            resp.raise_for_status()
            data = await resp.json()
            total_pages = data.get("totalPages", 1)
            for p in data.get("content", []):
                if p.get("barcode"): archived_barcodes.add(p["barcode"])
        # Diğer sayfalar
        tasks = [
            fetch_products_page(session, url, headers, {**base_params, "page": page})
            for page in range(1, total_pages)
        ]
        pages = await asyncio.gather(*tasks)
        for content in pages:
            for p in content:
                b = p.get("barcode")
                if b: archived_barcodes.add(b)

    return archived_barcodes


def delete_archived_in_db(barcodes: set) -> int:
    if not barcodes: return 0
    deleted = Product.query.filter(Product.barcode.in_(barcodes)).delete(synchronize_session=False)
    db.session.commit()
    return deleted


def extract_active_barcodes(api_products: list[str|dict]) -> set[str]:
    """fetch_all_products_async ile gelen (approved=true, archived=false) ürünlerin barkod seti"""
    active = set()
    for p in api_products or []:
        b = (p or {}).get("barcode")
        if b:
            active.add(b)
    return active


def delete_missing_products_in_db(active_barcodes: set[str]) -> int:
    if not active_barcodes:
        logger.warning("Aktif barkod seti boş; herhangi bir ürün silinmeyecek.")
        return 0
    to_delete = Product.query.filter(~Product.barcode.in_(active_barcodes)).all()
    for p in to_delete:
        db.session.delete(p)
    if to_delete:
        db.session.commit()
    return len(to_delete)




async def sync_trendyol_deletions(api_products: list[dict]) -> dict:
    """
    1) Trendyol 'archived=true' barkodlarını çek → DB’den sil
    2) Trendyol 'approved=true & archived=false' listesinde olmayanları da DB’den sil
    """
    # 1) Arşivdekiler
    archived_barcodes = await fetch_archived_barcodes_async()
    deleted_archived = delete_archived_in_db(archived_barcodes)

    # 2) Aktif listede görünmeyenler
    active_barcodes = extract_active_barcodes(api_products)
    deleted_inactive = delete_missing_products_in_db(active_barcodes)

    return {
        "deleted_archived": deleted_archived,
        "deleted_inactive": deleted_inactive
    }



def _abs_from_static(static_path: str) -> str | None:
    if not static_path:
        return None
    rel = static_path[1:] if static_path.startswith('/') else static_path
    abs_path = os.path.join(current_app.root_path, rel.replace('/', os.sep))
    static_root = os.path.join(current_app.root_path, 'static')
    # static dışına çıkma
    if os.path.commonpath([abs_path, static_root]) != static_root:
        return None
    return abs_path

@event.listens_for(Product, 'after_delete')
def _delete_product_image(mapper, connection, target):
    try:
        abs_path = _abs_from_static(getattr(target, 'images', None))
        if abs_path and os.path.exists(abs_path):
            os.remove(abs_path)
    except Exception as e:
        current_app.logger.error(f"Görsel silinirken hata (barcode={getattr(target,'barcode',None)}): {e}")