from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
import base64
import aiohttp
import asyncio
import json
from datetime import datetime
from models import db, Product
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID
import logging

# Loglama ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('product_service.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Trendyol ürünler için API temel URL
BASE_URL = "https://api.trendyol.com/"

product_service_bp = Blueprint('product_service', __name__)

@product_service_bp.route('/fetch-trendyol-products', methods=['POST'])
async def fetch_trendyol_products_route():
    try:
        await fetch_trendyol_products_async()
        flash('Ürün kataloğu başarıyla güncellendi!', 'success')
    except Exception as e:
        logger.error(f"Hata: fetch_trendyol_products_route - {e}")
        flash('Ürün kataloğu güncellenirken bir hata oluştu.', 'danger')

    return redirect(url_for('get_products.product_list'))


async def fetch_trendyol_products_async():
    """
    Trendyol API'den tüm ürünleri asenkron olarak çeker
    """
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')

        # Bu endpoint doğru ve teyit edildi.
        url = f"{BASE_URL}integration/product/sellers/{SUPPLIER_ID}/products"

        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json",
            "User-Agent": f"SellerId={SUPPLIER_ID} - SelfIntegration"
        }

        params = { "page": 0, "size": 200, "approved": "true" }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    response_data = await response.text()
                    logger.error(f"API Error: {response.status} - {response_data}")
                    return

                response_data = await response.json()
                total_elements = response_data.get('totalElements', 0)
                total_pages = response_data.get('totalPages', 1)
                logger.info(f"Toplam ürün sayısı: {total_elements}, Toplam sayfa sayısı: {total_pages}")

                tasks = []
                semaphore = asyncio.Semaphore(5)
                for page_number in range(total_pages):
                    params_page = params.copy()
                    params_page['page'] = page_number
                    task = fetch_products_page(session, url, headers, params_page, semaphore)
                    tasks.append(task)

                pages_data = await asyncio.gather(*tasks)

                all_products_data = []
                for products in pages_data:
                    if products:
                        all_products_data.extend(products)

                logger.info(f"Toplam çekilen ürün sayısı: {len(all_products_data)}")
                process_all_products(all_products_data)

    except Exception as e:
        logger.error(f"Hata: fetch_trendyol_products_async - {e}", exc_info=True)


async def fetch_products_page(session, url, headers, params, semaphore):
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
            logger.error(f"Hata: fetch_products_page - {e}", exc_info=True)
            return []


def process_all_products(all_products_data):
    try:
        existing_products = Product.query.all()
        existing_products_dict = {product.barcode: product for product in existing_products}

        new_products = []
        updated_products = []
        api_barcodes = set()

        for product_data in all_products_data:
            barcode = product_data.get('barcode', '').strip().lower()  # 🔧 Küçük harfe normalize et
            if not barcode: continue

            api_barcodes.add(barcode)

            attributes = product_data.get('attributes', [])
            color = next((attr.get('attributeValue', '') for attr in attributes if attr.get('attributeName') == 'Renk'), '')
            size = next((attr.get('attributeValue', '') for attr in attributes if attr.get('attributeName') == 'Beden'), '')

            product_data_dict = {
                'barcode': barcode, 'title': product_data.get('title', ''),  # Küçük harfli barkod
                'product_main_id': str(product_data.get('productMainId', '')),
                'category_name': product_data.get('categoryName', ''),
                'quantity': product_data.get('quantity', 0),
                'list_price': product_data.get('listPrice', 0),
                'sale_price': product_data.get('salePrice', 0),
                'vat_rate': product_data.get('vatRate', 0),
                'brand': product_data.get('brand', ''),
                'stock_code': product_data.get('stockCode', ''),
                'images': product_data.get('images', [{}])[0].get('url', '') if product_data.get('images') else '',
                'last_update_date': datetime.now(),
                'color': color, 'size': size,
            }

            if barcode in existing_products_dict:
                existing_product = existing_products_dict[barcode]
                for key, value in product_data_dict.items():
                    setattr(existing_product, key, value)
                updated_products.append(existing_product)
            else:
                new_product = Product(**product_data_dict)
                new_products.append(new_product)

        if new_products:
            db.session.bulk_save_objects(new_products)
            logger.info(f"Toplam {len(new_products)} yeni ürün eklendi")

        if updated_products:
            db.session.commit()
            logger.info(f"Toplam {len(updated_products)} ürün güncellendi")
        elif new_products:
            db.session.commit()

        logger.info("Ürün veritabanı güncellendi")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Hata: process_all_products - {e}", exc_info=True)


@product_service_bp.route('/api/product-categories', methods=['GET'])
async def get_product_categories():
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')

        # DÜZELTİLDİ: Gönderdiğin tabloya göre doğru endpoint.
        url = f"{BASE_URL}integration/product/product-categories"

        headers = { "Authorization": f"Basic {b64_auth_str}", "User-Agent": f"SellerId={SUPPLIER_ID} - SelfIntegration" }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return jsonify({'success': False, 'error': f"API hatası: {response.status}"}), 500
                data = await response.json()
                return jsonify({'success': True, 'categories': data.get('categories', [])})

    except Exception as e:
        logger.error(f"Hata: get_product_categories - {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@product_service_bp.route('/api/brands', methods=['GET'])
async def get_brands():
    try:
        name = request.args.get('name', '')
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')

        # DÜZELTİLDİ: Gönderdiğin tabloya göre doğru endpoint.
        # İsimle arama için endpoint farklı olabilir, şimdilik ana listeyi alacak şekilde ayarlandı.
        # Dokümantasyonda by-name araması yoksa bu şekilde kalmalı.
        url = f"{BASE_URL}integration/product/brands"

        headers = { "Authorization": f"Basic {b64_auth_str}", "User-Agent": f"SellerId={SUPPLIER_ID} - SelfIntegration" }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return jsonify({'success': False, 'error': f"API hatası: {response.status}"}), 500
                data = await response.json()
                return jsonify({'success': True, 'brands': data})

    except Exception as e:
        logger.error(f"Hata: get_brands - {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@product_service_bp.route('/api/category-attributes/<int:category_id>', methods=['GET'])
async def get_category_attributes(category_id):
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')

        # DÜZELTİLDİ: Gönderdiğin tabloya göre doğru endpoint.
        url = f"{BASE_URL}integration/product/product-categories/{category_id}/attributes"

        headers = { "Authorization": f"Basic {b64_auth_str}", "User-Agent": f"SellerId={SUPPLIER_ID} - SelfIntegration" }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return jsonify({'success': False, 'error': f"API hatası: {response.status}"}), 500
                data = await response.json()
                return jsonify({'success': True, 'attributes': data})

    except Exception as e:
        logger.error(f"Hata: get_category_attributes - {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@product_service_bp.route('/update-price-stock', methods=['POST'])
async def update_price_stock():
    try:
        data = request.json
        if not data or 'items' not in data:
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı'}), 400

        items = data['items']
        if not items:
            return jsonify({'success': False, 'error': 'Güncellenecek ürün bulunamadı'}), 400

        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')

        # Bu endpoint doğru ve teyit edildi.
        url = f"{BASE_URL}integration/inventory/sellers/{SUPPLIER_ID}/products/price-and-inventory"

        headers = {
            "Authorization": f"Basic {b64_auth_str}", "Content-Type": "application/json",
            "User-Agent": f"SellerId={SUPPLIER_ID} - SelfIntegration"
        }

        payload = {"items": items}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status not in [200, 202]:
                    response_text = await response.text()
                    logger.error(f"API Error: {response.status} - {response_text}")
                    return jsonify({'success': False, 'error': f"API hatası: {response_text}"}), 500

                for item in items:
                    barcode = item.get('barcode')
                    product = Product.query.filter_by(barcode=barcode).first()
                    if product:
                        if 'quantity' in item: product.quantity = item['quantity']
                        if 'salePrice' in item: product.sale_price = item['salePrice']
                        if 'listPrice' in item: product.list_price = item['listPrice']
                        product.last_update_date = datetime.now()
                        db.session.add(product)

                db.session.commit()

                return jsonify({ 'success': True, 'message': 'Ürün fiyat ve stok bilgileri başarıyla güncellendi' })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Hata: update_price_stock - {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500