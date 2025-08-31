import logging
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for
import json
import os
import traceback
from sqlalchemy import desc



# Yeni tablolarınız:
from models import (
    OrderCreated,
    RafUrun,
    Product,
    # ... eğer diğer tabloları da kullanacaksanız, buraya ekleyin
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

siparis_hazirla_bp = Blueprint("siparis_hazirla", __name__)



@siparis_hazirla_bp.route("/siparis-hazirla", endpoint="index")
@siparis_hazirla_bp.route("/hazirla")
def index():
    data = get_home()  # en eski Created siparişi ve ürünleri toplar
    return render_template("siparis_hazirla.html", **data)



def get_home():
    """
    Ana sayfa: en eski 'Created' siparişi ve ürünlerinin (aktif ilk 3 rafla) hazırlanması.
    """
    try:
        oldest_order = OrderCreated.query.order_by(OrderCreated.order_date).first()
        if not oldest_order:
            logging.info("İşlenecek 'Created' sipariş yok.")
            return default_order_data()

        remaining_time = calculate_remaining_time(oldest_order.agreed_delivery_date)

        # details parse
        details_json = oldest_order.details or '[]'
        if isinstance(details_json, str):
            try:
                details_list = json.loads(details_json)
            except json.JSONDecodeError as e:
                logging.error(f"JSON çözümleme hatası: {e}")
                details_list = []
        elif isinstance(details_json, list):
            details_list = details_json
        else:
            details_list = []

        # ürün kartları
        products = []
        for d in details_list:
            bc = d.get('barcode', '')
            image_url = get_product_image(bc)

            # SADECE AKTİF (adet>0) İLK 3 RAF
            raf_kayitlari = (
                RafUrun.query
                .filter(RafUrun.urun_barkodu == bc, RafUrun.adet > 0)
                .order_by(desc(RafUrun.adet))
                .limit(3)
                .all()
            )
            raflar = [{"kod": r.raf_kodu, "adet": r.adet} for r in raf_kayitlari]

            products.append({
                "sku": d.get("sku", "Bilinmeyen SKU"),
                "barcode": bc,
                "quantity": d.get("quantity", 1),
                "image_url": image_url,
                "raflar": raflar,  # sadece aktif ilk 3
            })

        # sipariş objesine iliştir
        oldest_order.products = products

        return {
            "order": oldest_order,
            "remaining_time": remaining_time
        }

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

# alias düğmeleri yerine doğrudan /index yönlendirmesi kullanılıyor