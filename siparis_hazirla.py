import logging
import os
import json
import traceback
from datetime import datetime
from flask import Blueprint, render_template
from sqlalchemy import desc
from zoneinfo import ZoneInfo



# Modeller
from models import OrderCreated, RafUrun, Product, Archive, Degisim

# Blueprint
siparis_hazirla_bp = Blueprint("siparis_hazirla", __name__)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")


IST = ZoneInfo("Europe/Istanbul")

def to_ist(dt):
    """Naive ise IST varsay, aware ise IST'ye çevir."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


# 🔔 Arşivde bekleyen siparişlerden uyarılar üret
def get_archive_warnings():
    now = datetime.now(IST)  # <-- IST
    archived_orders = Archive.query.all()
    warnings = []

    for a in archived_orders:
        if not a.archive_date:
            continue

        a_dt = to_ist(a.archive_date)       # <-- normalize
        diff = now - a_dt
        minutes = diff.total_seconds() // 60
        hours = diff.total_seconds() // 3600

        if hours >= 1:
            warnings.append(f"Sipariş {a.order_number} {int(hours)} saattir arşivde bekliyor.")
        elif minutes >= 30:
            warnings.append(f"Sipariş {a.order_number} 30 dakikadan fazla arşivde.")

    return warnings, len(archived_orders)

# 🔔 Değişim bekleyen siparişlerden uyarılar üret
def get_exchange_warnings():
    """
    'İşleme Alındı' statüsündeki değişimler için mesaj + max saat.
    Dönüş: (messages:list[str], count:int, max_delay_hours:int)
    """
    try:
        items = (Degisim.query
                 .filter(Degisim.degisim_durumu == 'İşleme Alındı')
                 .order_by(Degisim.degisim_tarihi.desc())
                 .all())
        now = datetime.now(IST)  # <-- IST
        msgs, max_h = [], 0
        for d in items:
            started = to_ist(getattr(d, 'degisim_tarihi', None))  # <-- normalize
            if started:
                diff_h = int((now - started).total_seconds() // 3600)
                max_h = max(max_h, diff_h)
                msgs.append(f"#{d.siparis_no} — {d.ad} {d.soyad} ({diff_h} saattir işleme alındı.)")
            else:
                msgs.append(f"#{d.siparis_no} — {d.ad} {d.soyad}")
        return msgs, len(items), max_h
    except Exception as e:
        logging.error(f"Değişim uyarıları alınamadı: {e}")
        return [], 0, 0





@siparis_hazirla_bp.route("/siparis-hazirla", endpoint="index")
@siparis_hazirla_bp.route("/hazirla")
def index():
    data = get_home()
    return render_template("siparis_hazirla.html", **data)


def get_home():
    """
    En eski 'Created' sipariş ve ürünlerini hazırla.
    Ayrıca arşiv ve değişim (İşleme Alındı) uyarılarını template'e gönderir.
    """
    try:
        # En eski Created sipariş
        oldest_order = OrderCreated.query.order_by(OrderCreated.order_date).first()

        # Uyarıları (her durumda) hazırla
        warnings, archive_count = get_archive_warnings()
        # get_exchange_warnings() => (messages, count, max_delay_hours)
        degisim_msgs, _degisim_count, degisim_max_h = get_exchange_warnings()

        if not oldest_order:
            logging.info("İşlenecek 'Created' sipariş yok.")
            base = default_order_data()
            base.update({
                "archive_warnings": warnings,
                "archive_count": archive_count,
                "degisim_warnings": degisim_msgs,
                "degisim_meta": {"max_delay_hours": degisim_max_h},  # ⬅️ sıklaşma için
            })
            return base

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

        # Dönüş
        return {
            "order": oldest_order,
            "remaining_time": remaining_time,
            "archive_warnings": warnings,
            "archive_count": archive_count,
            "degisim_warnings": degisim_msgs,
            "degisim_meta": {"max_delay_hours": degisim_max_h},  # ⬅️ ARŞİVLE AYNI MANTIK
        }

    except Exception as e:
        logging.error(f"Bir hata oluştu: {e}")
        traceback.print_exc()

        # Hata olsa da uyarıları gönder
        warnings, archive_count = get_archive_warnings()
        degisim_msgs, _degisim_count, degisim_max_h = get_exchange_warnings()

        base = default_order_data()
        base.update({
            "archive_warnings": warnings,
            "archive_count": archive_count,
            "degisim_warnings": degisim_msgs,
            "degisim_meta": {"max_delay_hours": degisim_max_h},
        })
        return base




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
            now = datetime.now(IST)         # <-- IST
            dd  = to_ist(delivery_date)     # <-- normalize
            diff = dd - now
            if diff.total_seconds() > 0:
                total = int(diff.total_seconds())
                days, rem = divmod(total, 86400)
                hours, rem = divmod(rem, 3600)
                minutes = rem // 60
                return f"{days} gün {hours} saat {minutes} dakika"
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
