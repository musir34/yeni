
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
import base64
import aiohttp
import asyncio
import json
from datetime import datetime
from models import db, Product
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL
import logging

# Loglama ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('product_service.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

product_service_bp = Blueprint('product_service', __name__)

@product_service_bp.route('/fetch-trendyol-products', methods=['POST'])
async def fetch_trendyol_products_route():
    try:
        await fetch_trendyol_products_async()
        flash('Ürün kataloğu başarıyla güncellendi!', 'success')
    except Exception as e:
        logger.error(f"Hata: fetch_trendyol_products_route - {e}")
        flash('Ürün kataloğu güncellenirken bir hata oluştu.', 'danger')

    return redirect(url_for('get_products.get_products_list'))


async def fetch_trendyol_products_async():
    """
    Trendyol API'den tüm ürünleri asenkron olarak çeker
    """
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/products"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }

        # İlk isteği yaparak toplam ürün ve sayfa sayısını alalım
        params = {
            "page": 0,
            "size": 200,  # Maksimum sayfa boyutu
            "approved": "true"  # Sadece onaylanmış ürünler
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                response_data = await response.json()
                if response.status != 200:
                    logger.error(f"API Error: {response.status} - {response_data}")
                    return

                total_elements = response_data.get('totalElements', 0)
                total_pages = response_data.get('totalPages', 1)
                logger.info(f"Toplam ürün sayısı: {total_elements}, Toplam sayfa sayısı: {total_pages}")

                # Tüm sayfalar için istek hazırlayalım
                tasks = []
                semaphore = asyncio.Semaphore(5)  # Aynı anda maksimum 5 istek
                for page_number in range(total_pages):
                    params_page = params.copy()
                    params_page['page'] = page_number
                    task = fetch_products_page(session, url, headers, params_page, semaphore)
                    tasks.append(task)

                # Asenkron olarak tüm istekleri yapalım
                pages_data = await asyncio.gather(*tasks)

                # Gelen ürünleri birleştirelim
                all_products_data = []
                for products in pages_data:
                    if products:
                        all_products_data.extend(products)

                logger.info(f"Toplam çekilen ürün sayısı: {len(all_products_data)}")

                # Ürünleri işleyelim
                process_all_products(all_products_data)

    except Exception as e:
        logger.error(f"Hata: fetch_trendyol_products_async - {e}")


async def fetch_products_page(session, url, headers, params, semaphore):
    """
    Belirli bir sayfadaki ürünleri çeker
    """
    async with semaphore:
        try:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    logger.error(f"API isteği başarısız oldu: {response.status} - {await response.text()}")
                    return []
                data = await response.json()
                products_data = data.get('content', [])
                return products_data
        except Exception as e:
            logger.error(f"Hata: fetch_products_page - {e}")
            return []


def process_all_products(all_products_data):
    """
    Trendyol'dan çekilen ürünleri veritabanına kaydeder
    """
    try:
        # Mevcut ürünleri al
        existing_products = Product.query.all()
        existing_products_dict = {product.barcode: product for product in existing_products}
        
        # Yeni ürünleri toplu kaydetmek için liste
        new_products = []
        updated_products = []
        
        # Trendyol API'den gelen tüm ürünlerin barkodlarını tutalım
        api_barcodes = set()
        
        for product_data in all_products_data:
            # Temel ürün bilgilerini çıkar
            barcode = product_data.get('barcode', '')
            if not barcode:
                continue
                
            api_barcodes.add(barcode)
            
            # Ürün verilerini hazırla
            product_data_dict = {
                'barcode': barcode,
                'title': product_data.get('title', ''),
                'product_main_id': str(product_data.get('productMainId', '')),
                'category_id': str(product_data.get('categoryId', '')),
                'category_name': product_data.get('categoryName', ''),
                'quantity': product_data.get('quantity', 0),
                'list_price': product_data.get('listPrice', 0),
                'sale_price': product_data.get('salePrice', 0),
                'vat_rate': product_data.get('vatRate', 0),
                'brand': product_data.get('brand', ''),
                'color': product_data.get('color', ''),
                'size': product_data.get('size', ''),
                'stock_code': product_data.get('stockCode', ''),
                'images': product_data.get('images', [''])[0] if product_data.get('images') else '',
                'last_update_date': datetime.now()
            }
            
            if barcode in existing_products_dict:
                # Mevcut ürünü güncelle
                existing_product = existing_products_dict[barcode]
                for key, value in product_data_dict.items():
                    setattr(existing_product, key, value)
                updated_products.append(existing_product)
            else:
                # Yeni ürün oluştur
                new_product = Product(**product_data_dict)
                new_products.append(new_product)
        
        # Yeni ürünleri toplu olarak ekle
        if new_products:
            db.session.bulk_save_objects(new_products)
            logger.info(f"Toplam {len(new_products)} yeni ürün eklendi")
            
        # Güncellenmiş ürünleri kaydet
        if updated_products:
            for product in updated_products:
                db.session.add(product)
            logger.info(f"Toplam {len(updated_products)} ürün güncellendi")
        
        # Veritabanında olup API'de olmayan ürünleri pasife çek
        # Bu kısım opsiyonel, ihtiyaca göre aktifleştirilebilir
        # existing_barcodes = set(existing_products_dict.keys())
        # removed_barcodes = existing_barcodes - api_barcodes
        # if removed_barcodes:
        #     for barcode in removed_barcodes:
        #         product = existing_products_dict[barcode]
        #         product.is_active = False
        #         db.session.add(product)
        #     logger.info(f"Toplam {len(removed_barcodes)} ürün pasife çekildi")
        
        db.session.commit()
        logger.info("Ürün veritabanı güncellendi")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Hata: process_all_products - {e}")


@product_service_bp.route('/api/product-categories', methods=['GET'])
async def get_product_categories():
    """
    Trendyol'daki tüm kategorileri çeker
    """
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}product-categories"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return jsonify({'success': False, 'error': f"API hatası: {response.status}"}), 500
                    
                data = await response.json()
                return jsonify({'success': True, 'categories': data})
                
    except Exception as e:
        logger.error(f"Hata: get_product_categories - {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@product_service_bp.route('/api/brands', methods=['GET'])
async def get_brands():
    """
    Trendyol'daki tüm markaları çeker veya isme göre filtreleyerek arar
    """
    try:
        name = request.args.get('name', '')
        
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        
        if name:
            url = f"{BASE_URL}brands/by-name?name={name}"
        else:
            url = f"{BASE_URL}brands" 
            
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return jsonify({'success': False, 'error': f"API hatası: {response.status}"}), 500
                    
                data = await response.json()
                return jsonify({'success': True, 'brands': data})
                
    except Exception as e:
        logger.error(f"Hata: get_brands - {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@product_service_bp.route('/api/category-attributes/<int:category_id>', methods=['GET'])
async def get_category_attributes(category_id):
    """
    Belirli bir kategorinin özelliklerini çeker
    """
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}product-categories/{category_id}/attributes"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return jsonify({'success': False, 'error': f"API hatası: {response.status}"}), 500
                    
                data = await response.json()
                return jsonify({'success': True, 'attributes': data})
                
    except Exception as e:
        logger.error(f"Hata: get_category_attributes - {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@product_service_bp.route('/update-price-stock', methods=['POST'])
async def update_price_stock():
    """
    Seçilen ürünlerin fiyat ve stok bilgilerini Trendyol'da günceller
    """
    try:
        data = request.json
        if not data or 'items' not in data:
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı'}), 400
            
        items = data['items']
        if not items:
            return jsonify({'success': False, 'error': 'Güncellenecek ürün bulunamadı'}), 400
            
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/products/price-and-inventory"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        # API formatına uygun veri dönüşümü
        api_items = []
        for item in items:
            api_item = {
                "barcode": item.get('barcode'),
                "quantity": item.get('quantity'),
                "salePrice": item.get('salePrice'),
                "listPrice": item.get('listPrice', item.get('salePrice'))
            }
            api_items.append(api_item)
            
        payload = {"items": api_items}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response_data = await response.json()
                
                if response.status != 200:
                    logger.error(f"API Error: {response.status} - {response_data}")
                    return jsonify({'success': False, 'error': f"API hatası: {response_data}"}), 500
                    
                # Veritabanında da aynı güncellemeleri yapalım
                for item in items:
                    barcode = item.get('barcode')
                    product = Product.query.filter_by(barcode=barcode).first()
                    if product:
                        product.quantity = item.get('quantity')
                        product.sale_price = item.get('salePrice')
                        product.list_price = item.get('listPrice', item.get('salePrice'))
                        product.last_update_date = datetime.now()
                        db.session.add(product)
                
                db.session.commit()
                
                return jsonify({
                    'success': True, 
                    'message': 'Ürün fiyat ve stok bilgileri güncellendi',
                    'api_response': response_data
                })
                
    except Exception as e:
        db.session.rollback()
        logger.error(f"Hata: update_price_stock - {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
