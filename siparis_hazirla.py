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

# Hava Durumu Servisi
from weather_service import get_weather_info, get_istanbul_time

# 🔥 BARKOD ALIAS DESTEĞİ
from barcode_alias_helper import normalize_barcode

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


def convert_woo_to_order_format(woo_order):
    """
    WooOrder modelini OrderCreated formatına çevir
    (sipariş hazırla sayfası için uyumlu hale getir)
    """
    import json
    
    # Müşteri adres bilgisi
    address_parts = [
        woo_order.shipping_address_1 or woo_order.billing_address_1,
        woo_order.shipping_address_2 or woo_order.billing_address_2,
        woo_order.shipping_city or woo_order.billing_city,
        woo_order.shipping_state or woo_order.billing_state,
        woo_order.shipping_postcode or woo_order.billing_postcode,
    ]
    full_address = ' '.join([p for p in address_parts if p])
    
    # Details JSON oluştur (sipariş hazırla sayfası için)
    details_list = []
    total_qty = 0
    
    for item in woo_order.line_items or []:
        product_id = item.get('product_id')
        variation_id = item.get('variation_id')
        woo_id = variation_id if variation_id else product_id
        qty = int(item.get('quantity', 1))
        total_qty += qty
        
        details_list.append({
            'woo_product_id': product_id,
            'woo_variation_id': variation_id,
            'woo_id': woo_id,
            'quantity': qty,
            'price': float(item.get('price', 0)),
            'line_total_price': float(item.get('total', 0)),
            'product_name': item.get('name', ''),
            'sku': item.get('sku', '')
        })
    
    # OrderCreated benzeri obje oluştur (dict olarak)
    class WooOrderAdapter:
        def __init__(self, woo_order, details_list, total_qty, full_address):
            self.order_number = woo_order.order_number
            self.order_date = woo_order.date_created
            self.status = woo_order.status
            self.customer_name = woo_order.customer_first_name or ''
            self.customer_surname = woo_order.customer_last_name or ''
            self.customer_address = full_address
            self.customer_id = woo_order.customer_email or ''
            self.amount = float(woo_order.total)
            self.currency_code = woo_order.currency
            self.quantity = total_qty
            self.details = json.dumps(details_list, ensure_ascii=False)
            self.source = 'WOOCOMMERCE'
            self.agreed_delivery_date = None  # WooCommerce'de yok
            self.cargo_provider_name = 'MNG'  # Varsayılan
            self.products = []  # Ürün listesi (sonradan doldurulacak)
            self.from_woo_table = True  # 🔥 woo_orders tablosundan geldiğini işaretle
            self.woo_order_id = woo_order.order_id  # 🔥 WooCommerce order ID
            
            # Ürün adı (ilk 3 ürün)
            self.product_name = ', '.join([
                item.get('name', '')[:30] 
                for item in (woo_order.line_items or [])[:3]
            ])
    
    return WooOrderAdapter(woo_order, details_list, total_qty, full_address)


# 🔔 Arşivde bekleyen siparişlerden uyarılar üret
def get_archive_warnings():
    now = get_istanbul_time()  # <-- IST (Türkiye saati)
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
        now = get_istanbul_time()  # <-- IST (Türkiye saati)
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
    
    ÖNCELİK SIRASI:
    1. woo_orders tablosu (status='processing' veya 'on-hold')
    2. orders_created tablosu (Trendyol siparişleri)
    
    Ayrıca arşiv ve değişim (İşleme Alındı) uyarılarını template'e gönderir.
    """
    try:
        from woocommerce_site.models import WooOrder
        
        # 🛒 ÖNCELİK 1: woo_orders tablosundan hazırlanacak sipariş var mı?
        # Sadece 'on-hold' (Beklemede) siparişler sipariş hazırla ekranına gelir
        woo_order_db = (WooOrder.query
                       .filter(WooOrder.status == 'on-hold')
                       .order_by(WooOrder.date_created)
                       .first())
        
        if woo_order_db:
            # WooOrder'dan OrderCreated formatına çevir
            oldest_order = convert_woo_to_order_format(woo_order_db)
            is_from_woo_table = True
        else:
            # 🛒 ÖNCELİK 2: orders_created tablosundan al (Trendyol)
            # Sadece 'Created' durumundaki siparişler
            oldest_order = (OrderCreated.query
                          .filter(OrderCreated.status == 'Created')
                          .order_by(OrderCreated.order_date)
                          .first())
            is_from_woo_table = False

        # Hava durumu bilgisi
        weather_info = get_weather_info()
        current_time = get_istanbul_time()

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
                "weather": weather_info,
                "current_time": current_time
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

        # 🔥 WooCommerce kontrolü (tire içermeyen sipariş numarası)
        is_woocommerce = oldest_order.source == 'WOOCOMMERCE' or (
            oldest_order.order_number and '-' not in str(oldest_order.order_number)
        )
        
        # Ürün kartları
        products = []
        for d in details_list:
            # 🔥 WooCommerce siparişi için product_id kullan
            if is_woocommerce:
                woo_id = d.get("woo_id") or d.get("woo_product_id")
                
                if woo_id:
                    # Product tablosundan woo_product_id ile ara
                    product_db = Product.query.filter_by(woo_product_id=int(woo_id)).first()
                    
                    if product_db:
                        bc = product_db.barcode  # Gerçek barkod
                        normalized_bc = normalize_barcode(bc)
                        product_name = product_db.title or "Bilinmeyen Ürün"
                        image_url = product_db.images or get_product_image(normalized_bc)
                    else:
                        # WooCommerce'den gelen bilgiler (fallback)
                        bc = str(woo_id)  # ID'yi barkod olarak kullan
                        normalized_bc = bc
                        product_name = d.get("product_name", "Bilinmeyen Ürün")
                        image_url = get_product_image(bc)
                        logging.warning(f"⚠️ WooCommerce ürün #{woo_id} Product tablosunda bulunamadı!")
                else:
                    # Hiç ID yok (çok eski veri)
                    bc = d.get("barcode", "")
                    normalized_bc = normalize_barcode(bc)
                    product_name = d.get("product_name", "Bilinmeyen Ürün")
                    image_url = get_product_image(normalized_bc)
            else:
                # 🔥 Trendyol siparişi - klasik mantık
                bc = d.get("barcode", "")
                normalized_bc = normalize_barcode(bc)
                
                # Product tablosundan barkod ile ara
                product_db = Product.query.filter_by(barcode=normalized_bc).first()
                
                if product_db:
                    product_name = product_db.title or "Bilinmeyen Ürün"
                    image_url = product_db.images or get_product_image(normalized_bc)
                else:
                    product_name = d.get("product_name") or d.get("productName", "Bilinmeyen Ürün")
                    image_url = d.get("image_url") or get_product_image(normalized_bc)

            # Aktif tüm raflar (adet > 0)
            raf_kayitlari = (
                RafUrun.query
                .filter(RafUrun.urun_barkodu == normalized_bc, RafUrun.adet > 0)
                .order_by(desc(RafUrun.adet))
                .all()
            )
            raflar = [{"kod": r.raf_kodu, "adet": r.adet} for r in raf_kayitlari]

            products.append({
                "sku": d.get("sku", bc),  # SKU veya barkod
                "barcode": bc,  # Orijinal (API'den gelen veya gerçek barkod)
                "normalized_barcode": normalized_bc,  # 🔥 Ana barkod
                "product_name": product_name,  # 🔥 Product tablosundan
                "quantity": d.get("quantity", 1),
                "image_url": image_url,  # 🔥 Product tablosundan
                "raflar": raflar,
                "woo_id": d.get("woo_id") if is_woocommerce else None  # WooCommerce ID (debug için)
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
            "weather": weather_info,
            "current_time": current_time
        }

    except Exception as e:
        logging.error(f"Bir hata oluştu: {e}")
        traceback.print_exc()

        # Hata olsa da uyarıları ve hava durumunu gönder
        warnings, archive_count = get_archive_warnings()
        degisim_msgs, _degisim_count, degisim_max_h = get_exchange_warnings()
        weather_info = get_weather_info()
        current_time = get_istanbul_time()

        base = default_order_data()
        base.update({
            "archive_warnings": warnings,
            "archive_count": archive_count,
            "degisim_warnings": degisim_msgs,
            "degisim_meta": {"max_delay_hours": degisim_max_h},
            "weather": weather_info,
            "current_time": current_time
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
            now = get_istanbul_time()       # <-- IST (Türkiye saati)
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
