import logging
import os
import json
import traceback
from datetime import datetime
from flask import Blueprint, render_template, request
from sqlalchemy import desc
from zoneinfo import ZoneInfo

# Modeller
from models import db, OrderCreated, RafUrun, Product, Archive, Degisim, ShopifyMapping

# Hava Durumu Servisi
from weather_service import get_weather_info, get_istanbul_time

# 🔥 BARKOD ALIAS DESTEĞİ
from barcode_alias_helper import normalize_barcode

# 🛍️ SHOPIFY DESTEĞİ
from shopify_site.shopify_service import shopify_service
from shopify_site.shopify_config import ShopifyConfig

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





# ════════════════════════════════════════════════════════════════
# 🛍️ SHOPIFY SİPARİŞ HELPER'LARI
# ════════════════════════════════════════════════════════════════

def _resolve_shopify_barcode(variant_barcode, sku):
    """Shopify variant barkodu veya SKU'dan panel barkodunu bul.
    ShopifyMapping tablosu üzerinden eşleştirme yapar.
    Dönüş: (panel_barkod, kaynak) veya (None, None)"""
    # 1) variant.barcode doluysa direkt Product tablosunda ara
    if variant_barcode:
        nbc = normalize_barcode(variant_barcode)
        p = Product.query.filter_by(barcode=nbc).first()
        if p:
            return p.barcode, "variant_barcode"

    # 2) ShopifyMapping üzerinden SKU ile panel barkodunu bul
    if sku:
        mapping = ShopifyMapping.query.filter_by(shopify_sku=sku).first()
        if mapping and mapping.barcode:
            return mapping.barcode, "shopify_mapping_sku"

    # 3) ShopifyMapping üzerinden variant barcode ile panel barkodunu bul
    if variant_barcode:
        mapping = ShopifyMapping.query.filter_by(shopify_barcode=variant_barcode).first()
        if mapping and mapping.barcode:
            return mapping.barcode, "shopify_mapping_barcode"

    # 4) SKU ile direkt Product tablosunda ara
    if sku:
        nsku = normalize_barcode(sku)
        p = Product.query.filter_by(barcode=nsku).first()
        if p:
            return p.barcode, "sku_direct"

    return None, None


def _is_cod_order(order):
    """Kapıda ödeme siparişi mi kontrol et."""
    gateways = order.get("paymentGatewayNames") or []
    cod_keywords = ["cash on delivery", "kapida", "cod", "manual"]
    return any(any(kw in gw.lower() for kw in cod_keywords) for gw in gateways)


def _fetch_shopify_beklemede_orders(limit=20):
    """Shopify'dan beklemedeki siparişleri çek.
    - Ödemesi onaylanmış (PAID) siparişler → hazırlamaya düşer
    - Kapıda ödemeli (COD/PENDING) siparişler → hazırlamaya düşer
    - Havale bekleyen (PENDING, COD değil) → hazırlamaya DÜŞMEZ
    """
    if not ShopifyConfig.is_configured():
        return []
    try:
        # Genel filtre: hazırlanan/kargoda/teslim/iptal/iade hariç
        base_filter = "-tag:Hazirlaniyor -tag:Kargoda -tag:\"Teslim Edildi\" -tag:Arsivlendi -status:cancelled -financial_status:refunded -financial_status:partially_refunded"

        # 1) Ödemesi onaylanmış siparişler
        result_paid = shopify_service.get_orders(
            limit=limit,
            query_filter=base_filter + " financial_status:paid",
            oldest_first=True,
        )
        paid_orders = result_paid.get("orders", []) if result_paid.get("success") else []

        # 2) Pending siparişler (kapıda ödeme olanları ayıkla)
        result_pending = shopify_service.get_orders(
            limit=limit,
            query_filter=base_filter + " financial_status:pending",
            oldest_first=True,
        )
        pending_orders = result_pending.get("orders", []) if result_pending.get("success") else []
        # Her pending siparişin gateway'ini logla
        for po in pending_orders:
            gw = po.get("paymentGatewayNames") or []
            logging.info(f"[SHOPIFY][PENDING] order={po.get('name')} gateways={gw} is_cod={_is_cod_order(po)}")
        cod_orders = [o for o in pending_orders if _is_cod_order(o)]

        # Birleştir ve tarihe göre sırala
        all_orders = paid_orders + cod_orders
        all_orders.sort(key=lambda o: o.get("createdAt", ""))

        logging.info(f"[SHOPIFY] Hazırlamaya düşen: {len(all_orders)} (paid={len(paid_orders)}, cod={len(cod_orders)})")
        return all_orders[:limit]
    except Exception as e:
        logging.error(f"[SHOPIFY] Beklemede siparişleri çekilirken hata: {e}")
        return []


def _shopify_order_to_hazirla_format(shopify_order):
    """Shopify sipariş verisini siparis_hazirla ekranının beklediği formata dönüştürür.
    Sahte bir OrderCreated benzeri obje döner."""

    order_id = shopify_order.get("legacyResourceId") or shopify_order.get("id", "").split("/")[-1]
    customer = shopify_order.get("customer") or {}
    shipping = shopify_order.get("shippingAddress") or {}
    line_items = shopify_order.get("line_items") or []
    price_set = shopify_order.get("currentTotalPriceSet", {}).get("shopMoney", {})

    # Kapıda ödeme tespiti
    gateways = shopify_order.get("paymentGatewayNames") or []
    cod_keywords = ["cash on delivery", "kapida", "cod", "manual"]
    is_cod = any(any(kw in gw.lower() for kw in cod_keywords) for gw in gateways)
    total_amount = float(price_set.get("amount", 0))

    # Ürün detaylarını details formatına çevir
    details_list = []
    for li in line_items:
        # Variant bilgileri güvenli çıkarma
        variant = li.get("variant") or {}
        variant_barcode = variant.get("barcode") or ""
        sku = li.get("sku") or ""
        variant_image = (variant.get("image") or {}).get("url") if isinstance(variant.get("image"), dict) else None

        # Panel barkodunu bul (ShopifyMapping üzerinden)
        panel_barcode, resolve_source = _resolve_shopify_barcode(variant_barcode, sku)
        real_barcode = panel_barcode or variant_barcode or sku
        logging.info(f"[SHOPIFY][RESOLVE] sku={sku} variant_bc={variant_barcode} -> panel_bc={panel_barcode} source={resolve_source}")

        details_list.append({
            "barcode": real_barcode,
            "sku": sku,
            "product_name": li.get("title") or "Shopify Ürün",
            "quantity": li.get("quantity", 1),
            "image_url": variant_image,
        })

    # Sahte OrderCreated benzeri obje (SimpleNamespace ile)
    from types import SimpleNamespace
    fake_order = SimpleNamespace(
        order_number=f"SH-{order_id}",
        shopify_gid=shopify_order.get("id"),
        shopify_order_name=shopify_order.get("name", f"#{order_id}"),
        status="Created",
        source="SHOPIFY",
        order_date=datetime.fromisoformat(shopify_order["createdAt"].replace("Z", "+00:00")) if shopify_order.get("createdAt") else datetime.utcnow(),
        customer_name=(customer.get("firstName") or shipping.get("name", "").split(" ")[0] if shipping.get("name") else "Misafir"),
        customer_surname=(customer.get("lastName") or (" ".join(shipping.get("name", "").split(" ")[1:]) if shipping.get("name") else "")),
        customer_address=f"{shipping.get('address1', '')} {shipping.get('address2', '')} {shipping.get('city', '')} {shipping.get('province', '')} {shipping.get('country', '')}".strip(),
        merchant_sku=", ".join(li.get("sku", "") for li in line_items),
        shipping_barcode="",
        cargo_provider_name="",
        cargo_tracking_number="",
        agreed_delivery_date=None,
        amount=total_amount,
        details=json.dumps(details_list),
        atanan_raf=None,
        products=[],  # get_home'da doldurulacak
        # Kapıda ödeme
        kapida_odeme=is_cod,
        kapida_odeme_tutari=total_amount if is_cod else 0,
        # Shopify özgü alanlar
        _is_shopify=True,
        _shopify_tags=shopify_order.get("tags", []),
        _shopify_payment_gateways=shopify_order.get("paymentGatewayNames", []),
        _shopify_financial_status=shopify_order.get("displayFinancialStatus", ""),
    )
    return fake_order, details_list


@siparis_hazirla_bp.route("/siparis-hazirla", endpoint="index")
@siparis_hazirla_bp.route("/hazirla")
def index():
    order_number = request.args.get("order_number", "").strip()
    manuel       = request.args.get("manuel", "0") == "1"
    if manuel and not order_number:
        # Manuel mod — sipariş yok, boş ekran
        data = get_home(order_number="__empty__")
    else:
        data = get_home(order_number=order_number or None)
    data["manuel_mod"] = manuel
    return render_template("siparis_hazirla.html", **data)


def get_home(order_number=None):
    """
    order_number verilirse o siparişi yükler (manuel mod).
    Verilmezse en eski 'Created' siparişi yükler (sıralı mod).
    """
    try:
        if order_number == "__empty__":
            oldest_order = None
        elif order_number and order_number.startswith("SH-"):
            # 🛍️ Shopify siparişi — API'den çek
            shopify_id = order_number.replace("SH-", "")
            shopify_result = shopify_service.get_order(shopify_id)
            if shopify_result.get("success") and shopify_result.get("order"):
                raw = shopify_result["order"]
                # line_items formatla
                raw["line_items"] = raw.get("line_items") or []
                oldest_order, _ = _shopify_order_to_hazirla_format(raw)
            else:
                oldest_order = None
        elif order_number:
            oldest_order = (OrderCreated.query
                          .filter(OrderCreated.order_number == order_number)
                          .first())
        else:
            # 🛍️ Öncelik: Shopify Beklemede siparişleri, sonra Trendyol
            # Arşivdekileri atla (Shopify tag filtresi + yerel kontrol)
            archived_numbers = {r[0] for r in db.session.query(Archive.order_number).all()}
            shopify_orders = _fetch_shopify_beklemede_orders(limit=5)
            shopify_match = None
            for so in shopify_orders:
                so_id = so.get("legacyResourceId") or so.get("id", "").split("/")[-1]
                if f"SH-{so_id}" not in archived_numbers:
                    shopify_match = so
                    break
            if shopify_match:
                oldest_order, _ = _shopify_order_to_hazirla_format(shopify_match)
            else:
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

        # 🔥 Platform kontrolü
        is_shopify = getattr(oldest_order, 'source', '') == 'SHOPIFY'
        is_woocommerce = (not is_shopify) and (
            oldest_order.source == 'WOOCOMMERCE' or (
                oldest_order.order_number and '-' not in str(oldest_order.order_number)
            )
        )

        # Ürün kartları
        products = []
        for d in details_list:
            # 🛍️ Shopify siparişi
            if is_shopify:
                sku_raw = d.get("sku") or ""
                # d["barcode"] zaten _shopify_order_to_hazirla_format'ta resolve edilmiş panel barkodu
                bc = d.get("barcode") or sku_raw
                normalized_bc = normalize_barcode(bc)
                shopify_image = d.get("image_url") or None

                # Product tablosundan barkod ile ara
                product_db = Product.query.filter_by(barcode=normalized_bc).first()

                if product_db:
                    product_name = product_db.title or d.get("product_name", "Shopify Ürün")
                    image_url = product_db.images or get_product_image(product_db.barcode)
                    if image_url == "/static/images/default.jpg" and shopify_image:
                        image_url = shopify_image
                else:
                    product_name = d.get("product_name", "Shopify Ürün")
                    image_url = get_product_image(normalized_bc)
                    if image_url == "/static/images/default.jpg" and shopify_image:
                        image_url = shopify_image

                logging.info(f"[SHOPIFY][IMG] barcode={bc} sku={sku_raw} normalized={normalized_bc} image={image_url}")

                # Raf bilgisi (barkod ile ara)
                raf_kayitlari = (
                    RafUrun.query
                    .filter(RafUrun.urun_barkodu == normalized_bc, RafUrun.adet > 0)
                    .order_by(desc(RafUrun.adet))
                    .all()
                )
                raflar = [{"kod": r.raf_kodu, "adet": r.adet} for r in raf_kayitlari]

                products.append({
                    "sku": sku_raw,
                    "barcode": bc,
                    "display_barcode": bc,
                    "normalized_barcode": normalized_bc,
                    "product_name": product_name,
                    "quantity": d.get("quantity", 1),
                    "image_url": image_url,
                    "raflar": raflar,
                    "woo_id": None
                })
                continue

            # 🔥 WooCommerce siparişi için woo_product_id kullan
            if is_woocommerce:
                woo_id = d.get("woo_id") or d.get("woo_product_id")
                
                if woo_id:
                    # Product tablosundan woo_product_id ile ürün bilgilerini al
                    product_db = Product.query.filter_by(woo_product_id=int(woo_id)).first()
                    
                    if product_db:
                        # 🔥 Görüntüde gerçek barkod gösterilir
                        display_barcode = product_db.barcode
                        normalized_bc = normalize_barcode(display_barcode)
                        product_name = product_db.title or d.get("product_name", "Bilinmeyen Ürün")
                        image_url = product_db.images or get_product_image(normalized_bc)
                    else:
                        # Product bulunamadı - WooCommerce'den gelen bilgileri kullan
                        display_barcode = d.get("sku", "") or str(woo_id)
                        normalized_bc = display_barcode
                        product_name = d.get("product_name", "Bilinmeyen Ürün")
                        image_url = get_product_image(normalized_bc)
                        logging.warning(f"⚠️ WooCommerce ürün #{woo_id} Product tablosunda bulunamadı!")
                    
                    # 🔥 ARKA PLANDA woo_id kullanılır (barkod doğrulama için)
                    bc = str(woo_id)  # Arka planda woo_id
                else:
                    # Hiç ID yok (çok eski veri)
                    bc = d.get("barcode", "")
                    display_barcode = bc
                    normalized_bc = normalize_barcode(bc)
                    product_name = d.get("product_name", "Bilinmeyen Ürün")
                    image_url = get_product_image(normalized_bc)
            else:
                # 🔥 Trendyol siparişi - klasik mantık
                bc = d.get("barcode", "")
                display_barcode = bc
                normalized_bc = normalize_barcode(bc)
                
                # Product tablosundan barkod ile ara
                product_db = Product.query.filter_by(barcode=normalized_bc).first()
                
                if product_db:
                    product_name = product_db.title or "Bilinmeyen Ürün"
                    image_url = product_db.images or get_product_image(normalized_bc)
                else:
                    product_name = d.get("product_name") or d.get("productName", "Bilinmeyen Ürün")
                    image_url = d.get("image_url") or get_product_image(normalized_bc)

            # Aktif tüm raflar (adet > 0) - Her iki platform için de barkod bazlı raf kontrolü
            # WooCommerce için display_barcode (gerçek barkod), Trendyol için normalized_bc kullanılır
            raf_barkod = display_barcode if is_woocommerce else normalized_bc
            
            raf_kayitlari = (
                RafUrun.query
                .filter(RafUrun.urun_barkodu == raf_barkod, RafUrun.adet > 0)
                .order_by(desc(RafUrun.adet))
                .all()
            )
            raflar = [{"kod": r.raf_kodu, "adet": r.adet} for r in raf_kayitlari]
            
            # Eğer bulunamazsa normalized_bc ile de dene (alias durumu için)
            if not raflar and is_woocommerce and display_barcode != normalized_bc:
                raf_kayitlari = (
                    RafUrun.query
                    .filter(RafUrun.urun_barkodu == normalized_bc, RafUrun.adet > 0)
                    .order_by(desc(RafUrun.adet))
                    .all()
                )
                raflar = [{"kod": r.raf_kodu, "adet": r.adet} for r in raf_kayitlari]

            products.append({
                "sku": d.get("sku", display_barcode if is_woocommerce else bc),  # SKU veya görüntü barkodu
                "barcode": bc,  # 🔥 Arka planda kullanılan (WooCommerce için woo_id)
                "display_barcode": display_barcode if is_woocommerce else bc,  # 🔥 Görüntüde gösterilen
                "normalized_barcode": normalized_bc,  # 🔥 Normalize edilmiş
                "product_name": product_name,  # 🔥 Product tablosundan
                "quantity": d.get("quantity", 1),
                "image_url": image_url,  # 🔥 Product tablosundan
                "raflar": raflar,
                "woo_id": d.get("woo_id") or d.get("woo_product_id") if is_woocommerce else None  # WooCommerce ID
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


# 🔥 Sıradaki siparişleri getiren API endpoint
@siparis_hazirla_bp.route("/api/siradaki-siparisler")
def get_queue_orders():
    """
    Sıradaki siparişlerin özet bilgilerini döndürür.
    Aktif sipariş hariç, en fazla 10 sipariş döndürülür.
    Raf bilgisi de dahil edilir.
    """
    from flask import jsonify, request
    from sqlalchemy import desc

    try:
        queue_orders = []

        # Aktif sipariş numarasını al (kuyrukta gösterilmeyecek)
        active_order_number = request.args.get('active', '')

        # Arşivdeki sipariş numaralarını al
        archived_order_numbers = db.session.query(Archive.order_number).all()
        archived_order_numbers = [num[0] for num in archived_order_numbers]

        remaining_slots = 10

        # 🛍️ ÖNCELİK 1: Shopify Beklemede siparişleri
        shopify_orders_raw = _fetch_shopify_beklemede_orders(limit=remaining_slots)
        for s_order in shopify_orders_raw:
            s_id = s_order.get("legacyResourceId") or s_order.get("id", "").split("/")[-1]
            s_order_number = f"SH-{s_id}"

            if s_order_number == active_order_number or s_order_number in archived_order_numbers:
                continue

            customer = s_order.get("customer") or {}
            shipping = s_order.get("shippingAddress") or {}
            line_items = s_order.get("line_items") or []
            price_set = s_order.get("currentTotalPriceSet", {}).get("shopMoney", {})

            cust_name = ((customer.get("firstName") or "") + " " + (customer.get("lastName") or "")).strip()
            if not cust_name:
                cust_name = shipping.get("name") or "Misafir"

            first_image = "/static/images/default.jpg"
            first_sku = ""
            first_raf = None
            first_product_name = "Shopify Ürün"

            if line_items:
                first_li = line_items[0]
                first_sku = first_li.get("sku") or ""
                first_product_name = (first_li.get("title") or "Shopify Ürün")[:30]
                _variant = first_li.get("variant") or {}
                _variant_barcode = _variant.get("barcode") or ""
                _vimg = _variant.get("image")
                img = _vimg.get("url") if isinstance(_vimg, dict) else None

                # ShopifyMapping ile panel barkodunu bul
                panel_bc, _ = _resolve_shopify_barcode(_variant_barcode, first_sku)
                lookup_bc = panel_bc or _variant_barcode or first_sku
                if lookup_bc:
                    nbc = normalize_barcode(lookup_bc)
                    product_db = Product.query.filter_by(barcode=nbc).first()
                    if product_db:
                        first_image = product_db.images or get_product_image(product_db.barcode)
                    else:
                        first_image = get_product_image(nbc)
                    if first_image == "/static/images/default.jpg" and img:
                        first_image = img

                    # Raf
                    raf_kayit = (RafUrun.query
                                .filter(RafUrun.urun_barkodu == nbc, RafUrun.adet > 0)
                                .order_by(desc(RafUrun.adet))
                                .first())
                    if raf_kayit:
                        first_raf = {"kod": raf_kayit.raf_kodu, "adet": raf_kayit.adet}
                elif img:
                    first_image = img

            # Kapida odeme tespiti
            s_gateways = s_order.get("paymentGatewayNames") or []
            s_cod_keywords = ["cash on delivery", "kapida", "cod", "manual"]
            s_is_cod = any(any(kw in gw.lower() for kw in s_cod_keywords) for gw in s_gateways)

            queue_orders.append({
                "order_number": s_order_number,
                "source": "SHOPIFY",
                "customer_name": cust_name,
                "product_count": len(line_items),
                "first_product_name": first_product_name,
                "first_sku": first_sku,
                "first_image": first_image,
                "first_raf": first_raf,
                "order_date": s_order.get("createdAt"),
                "total": float(price_set.get("amount", 0)),
                "kapida_odeme": s_is_cod,
            })
            remaining_slots -= 1
            if remaining_slots <= 0:
                break

        # ÖNCELİK 2: Trendyol siparişleri (Created)
        if remaining_slots > 0:
            trendyol_query = (OrderCreated.query
                              .filter(OrderCreated.status == 'Created'))

            # Aktif siparişi hariç tut
            if active_order_number:
                trendyol_query = trendyol_query.filter(OrderCreated.order_number != active_order_number)

            trendyol_orders = trendyol_query.order_by(OrderCreated.order_date).limit(remaining_slots).all()

            for order in trendyol_orders:
                first_image = "/static/images/default.jpg"
                product_count = 0
                first_product_name = "Ürün"
                first_sku = ""
                first_raf = None

                # Details parse
                details_json = order.details or "[]"
                if isinstance(details_json, str):
                    try:
                        details_list = json.loads(details_json)
                    except json.JSONDecodeError:
                        details_list = []
                elif isinstance(details_json, list):
                    details_list = details_json
                else:
                    details_list = []

                if details_list:
                    product_count = len(details_list)
                    first_item = details_list[0]
                    bc = first_item.get("barcode", "")
                    normalized_bc = normalize_barcode(bc)
                    first_product_name = first_item.get("product_name", first_item.get("productName", "Ürün"))[:30]
                    first_sku = first_item.get("sku", bc)

                    product_db = Product.query.filter_by(barcode=normalized_bc).first()
                    if product_db and product_db.images:
                        first_image = product_db.images
                    else:
                        first_image = get_product_image(normalized_bc)

                    raf_kayit = (RafUrun.query
                                .filter(RafUrun.urun_barkodu == normalized_bc, RafUrun.adet > 0)
                                .order_by(desc(RafUrun.adet))
                                .first())
                    if raf_kayit:
                        first_raf = {"kod": raf_kayit.raf_kodu, "adet": raf_kayit.adet}

                queue_orders.append({
                    "order_number": order.order_number,
                    "source": "TRENDYOL",
                    "customer_name": f"{order.customer_name or ''} {order.customer_surname or ''}".strip(),
                    "product_count": product_count,
                    "first_product_name": first_product_name,
                    "first_sku": first_sku,
                    "first_image": first_image,
                    "first_raf": first_raf,
                    "order_date": order.order_date.isoformat() if order.order_date else None,
                    "total": float(order.amount) if order.amount else 0
                })

        return jsonify({
            "success": True,
            "orders": queue_orders,
            "total_count": len(queue_orders)
        })
    
    except Exception as e:
        logging.error(f"Sıradaki siparişler alınamadı: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "orders": []
        }), 500
