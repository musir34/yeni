import logging
import os
import json
import traceback
from datetime import datetime
from flask import Blueprint, render_template
from sqlalchemy import desc

# Modeller
from models import OrderCreated, RafUrun, Product, Archive

# Blueprint
siparis_hazirla_bp = Blueprint("siparis_hazirla", __name__)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")


# 🔔 Arşivde bekleyen siparişlerden uyarılar üret
def get_archive_warnings():
    now = datetime.utcnow()
    archived_orders = Archive.query.all()
    warnings = []

    for a in archived_orders:
        if not a.archive_date:
            continue

        diff = now - a.archive_date
        minutes = diff.total_seconds() // 60
        hours = diff.total_seconds() // 3600

        if hours >= 1:
            warnings.append(f"Sipariş {a.order_number} {int(hours)} saattir arşivde bekliyor.")
        elif minutes >= 30:
            warnings.append(f"Sipariş {a.order_number} 30 dakikadan fazla arşivde.")

    return warnings, len(archived_orders)


@siparis_hazirla_bp.route("/siparis-hazirla", endpoint="index")
@siparis_hazirla_bp.route("/hazirla")
def index():
    data = get_home()
    return render_template("siparis_hazirla.html", **data)


def get_home():
    """
    En eski 'Created' sipariş ve ürünlerini hazırla.
    """
    try:
        # En eski Created sipariş
        oldest_order = OrderCreated.query.order_by(OrderCreated.order_date).first()
        if not oldest_order:
            logging.info("İşlenecek 'Created' sipariş yok.")
            return default_order_data()

        remaining_time = calculate_remaining_time(oldest_order.agreed_delivery_date)

        # Details parse
        details_json = oldest_order.details or "[]"
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

        # Ürün kartları
        products = []
        for d in details_list:
            bc = d.get("barcode", "")
            image_url = get_product_image(bc)

            # Aktif tüm raflar (adet > 0)
            raf_kayitlari = (
                RafUrun.query
                .filter(RafUrun.urun_barkodu == bc, RafUrun.adet > 0)
                .order_by(desc(RafUrun.adet))
                .all()
            )
            raflar = [{"kod": r.raf_kodu, "adet": r.adet} for r in raf_kayitlari]

            products.append({
                "sku": d.get("sku", "Bilinmeyen SKU"),
                "barcode": bc,
                "quantity": d.get("quantity", 1),
                "image_url": image_url,
                "raflar": raflar
            })

        # Sipariş objesine iliştir
        oldest_order.products = products

        # Arşiv uyarılarını ekle
        warnings, archive_count = get_archive_warnings()

        return {
            "order": oldest_order,
            "remaining_time": remaining_time,
            "archive_warnings": warnings,
            "archive_count": archive_count
        }

    except Exception as e:
        logging.error(f"Bir hata oluştu: {e}")
        traceback.print_exc()
        return default_order_data()


def default_order_data():
    return {
        "order": None,
        "order_number": "Sipariş Yok",
        "products": [],
        "merchant_sku": "Bilgi Yok",
        "shipping_barcode": "Kargo Kodu Yok",
        "cargo_provider_name": "Kargo Firması Yok",
        "customer_name": "Alıcı Yok",
        "customer_surname": "Soyad Yok",
        "customer_address": "Adres Yok",
        "remaining_time": "Kalan Süre Yok",
        "archive_warnings": [],
        "archive_count": 0
    }


def calculate_remaining_time(delivery_date):
    if delivery_date:
        try:
            now = datetime.now()
            diff = delivery_date - now
            if diff.total_seconds() > 0:
                days, seconds = divmod(diff.total_seconds(), 86400)
                hours, seconds = divmod(seconds, 3600)
                minutes = seconds // 60
                return f"{int(days)} gün {int(hours)} saat {int(minutes)} dakika"
            else:
                return "0 dakika"
        except Exception as ve:
            logging.error(f"Tarih hesaplama hatası: {ve}")
            return "Kalan Süre Yok"
    return "Kalan Süre Yok"


def get_product_image(barcode):
    images_folder = os.path.join("static", "images")
    extensions = [".jpg", ".jpeg", ".png", ".gif"]
    for ext in extensions:
        image_filename = f"{barcode}{ext}"
        image_path = os.path.join(images_folder, image_filename)
        if os.path.exists(image_path):
            return f"/static/images/{image_filename}"
    return "/static/images/default.jpg"
