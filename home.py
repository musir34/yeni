import logging
from datetime import datetime
from flask import Blueprint, render_template
import json
import os
import traceback

# Yeni tablolarınız:
from models import (
    OrderCreated,
    Product,
    # ... eğer diğer tabloları da kullanacaksanız, buraya ekleyin
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

home_bp = Blueprint('home', __name__)

@home_bp.route('/')
def home():
    order_data = get_home()
    return render_template('home.html', **order_data)

def get_home():
    """
    Ana sayfa için gerekli sipariş verilerini hazırlar.
    Artık eski 'Order' tablosu yerine 'OrderCreated' tablosunu kullanıyoruz.
    """
    try:
        # En eski 'Created' siparişi OrderCreated tablosundan çekelim
        oldest_order = OrderCreated.query.order_by(OrderCreated.order_date).first()

        if oldest_order:
            logging.info(f"En eski 'Created' statüsündeki sipariş işleniyor: {oldest_order.order_number}")

            shipping_barcode = oldest_order.shipping_barcode or 'Kargo Kodu Yok'
            remaining_time = calculate_remaining_time(oldest_order.agreed_delivery_date)

            # Sipariş detaylarını alalım - boş string veya None kontrolü
            details_json = oldest_order.details
            products = []
            
            if details_json and details_json.strip() != '':
                logging.info(f"Sipariş detayları mevcut: {details_json[:100]}...")
                # JSON details varsa parse et
                try:
                    if isinstance(details_json, str):
                        details_list = json.loads(details_json)
                    elif isinstance(details_json, list):
                        details_list = details_json
                    else:
                        details_list = []
                    
                    # JSON'dan ürün bilgilerini çıkar
                    for detail in details_list:
                        if isinstance(detail, dict):
                            product_barcode = detail.get('barcode', '')
                            image_url = get_product_image(product_barcode)
                            products.append({
                                'sku': detail.get('sku', 'Bilinmeyen SKU'),
                                'barcode': product_barcode,
                                'product_name': detail.get('productName', 'Ürün Adı Yok'),
                                'size': detail.get('size', ''),
                                'color': detail.get('color', ''),
                                'quantity': detail.get('quantity', 1),
                                'unit_price': detail.get('unit_price', 0),
                                'image_url': image_url
                            })
                            
                except json.JSONDecodeError as e:
                    logging.error(f"JSON çözümleme hatası: {e}")
                    # JSON parse edilemezse, tek ürün olarak işle
                    if oldest_order.product_barcode:
                        product_barcode = oldest_order.product_barcode.split(',')[0].strip()
                        image_url = get_product_image(product_barcode)
                        products.append({
                            'sku': oldest_order.merchant_sku or 'Bilinmeyen SKU',
                            'barcode': product_barcode,
                            'product_name': oldest_order.product_name or 'Ürün Adı Yok',
                            'size': '',
                            'color': '',
                            'quantity': 1,
                            'unit_price': oldest_order.amount or 0,
                            'image_url': image_url
                        })
            else:
                logging.info("Sipariş detayları boş, temel alanlardan ürün bilgisi alınacak.")
                # Details boşsa, temel alanlardan ürün bilgisini oluştur
                if oldest_order.product_barcode:
                    # Virgülle ayrılmış barkodları işle
                    barcodes = [b.strip() for b in oldest_order.product_barcode.split(',') if b.strip()]
                    for barcode in barcodes:
                        image_url = get_product_image(barcode)
                        products.append({
                            'sku': oldest_order.merchant_sku or 'Bilinmeyen SKU',
                            'barcode': barcode,
                            'product_name': oldest_order.product_name or 'Ürün Adı Yok',
                            'size': '',
                            'color': '',
                            'quantity': 1,
                            'unit_price': oldest_order.amount or 0,
                            'image_url': image_url
                        })

            # Şablonda kolay erişim için sipariş nesnesine ekliyoruz (opsiyonel)
            oldest_order.products = products

            return {
                'order': oldest_order,
                'order_number': oldest_order.order_number or 'Sipariş Yok',
                'products': products,
                'merchant_sku': oldest_order.merchant_sku or 'Bilgi Yok',
                'shipping_barcode': shipping_barcode,
                'cargo_provider_name': oldest_order.cargo_provider_name or 'Kargo Firması Yok',
                'customer_name': oldest_order.customer_name or 'Alıcı Yok',
                'customer_surname': oldest_order.customer_surname or 'Soyad Yok',
                'customer_address': oldest_order.customer_address or 'Adres Yok',
                'remaining_time': remaining_time
            }
        else:
            logging.info("İşlenecek 'Created' statüsünde sipariş yok.")
            return default_order_data()

    except Exception as e:
        logging.error(f"Bir hata oluştu: {e}")
        traceback.print_exc()
        return default_order_data()


def default_order_data():
    """
    Varsayılan boş sipariş verilerini döndürür.
    """
    return {
        'order': None,
        'order_number': 'Sipariş Yok',
        'products': [],
        'merchant_sku': 'Bilgi Yok',
        'shipping_barcode': 'Kargo Kodu Yok',
        'cargo_provider_name': 'Kargo Firması Yok',
        'customer_name': 'Alıcı Yok',
        'customer_surname': 'Soyad Yok',
        'customer_address': 'Adres Yok',
        'remaining_time': 'Kalan Süre Yok'
    }

def calculate_remaining_time(delivery_date):
    """
    Teslimat süresini hesaplar.
    """
    if delivery_date:
        try:
            now = datetime.now()
            time_difference = delivery_date - now

            if time_difference.total_seconds() > 0:
                days, seconds = divmod(time_difference.total_seconds(), 86400)
                hours, seconds = divmod(seconds, 3600)
                minutes = seconds // 60
                return f"{int(days)} gün {int(hours)} saat {int(minutes)} dakika"
            else:
                return "0 dakika"
        except Exception as ve:
            logging.error(f"Tarih hesaplama hatası: {ve}")
            return "Kalan Süre Yok"
    else:
        return "Kalan Süre Yok"

def get_product_image(barcode):
    """
    Ürün görselinin yolunu döndürür.
    """
    images_folder = os.path.join('static', 'images')
    extensions = ['.jpg', '.jpeg', '.png', '.gif']
    for ext in extensions:
        image_filename = f"{barcode}{ext}"
        image_path = os.path.join(images_folder, image_filename)
        if os.path.exists(image_path):
            return f"/static/images/{image_filename}"
    return "/static/images/default.jpg"
