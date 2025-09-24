from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
# create_engine gerekli değil, db instance'ı kullanılıyor
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float, Boolean, Text, Index, UniqueConstraint
# declarative_base gerekli değil, db.Model kullanılıyor
from datetime import datetime
import uuid
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from datetime import date
from sqlalchemy.dialects.postgresql import JSONB # Eğer PostgreSQL kullanıyorsan bu daha verimli
from sqlalchemy import JSON
from flask_login import UserMixin
from sqlalchemy import func


db = SQLAlchemy()



# --- Varsayılan seçimler (tek kayıt yeter)
class UretimOneriDefaults(db.Model):
    __tablename__ = "uretim_oneri_defaults"
    id = db.Column(db.Integer, primary_key=True)
    models_json = db.Column(db.Text, nullable=False, default="[]")       # ["gll012","gll088",...]
    days = db.Column(db.Integer, nullable=False, default=7)
    min_cover_days = db.Column(db.Float, nullable=False, default=14.0)
    safety_factor = db.Column(db.Float, nullable=False, default=0.10)
    only_positive = db.Column(db.Boolean, nullable=False, default=True)
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())

# --- Haftalık üretim planı kaydı (snapshot)
class UretimPlan(db.Model):
    __tablename__ = "uretim_plan"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)                    # örn: "Haftalık Plan 2025-09-24"
    models_json = db.Column(db.Text, nullable=False)                      # ["gll012","gll088"]
    params_json = db.Column(db.Text, nullable=False)                      # {"days":7,"min_cover_days":14,...}
    snapshot_json = db.Column(db.Text, nullable=False)                    # API çıktısı (groups vb.)
    total_suggest = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(24), nullable=False, default="calisacak")# calisacak|tamamlandi|iptal
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)



class UretimOneriWatch(db.Model):
    __tablename__ = "uretim_oneri_watchlist"
    id = db.Column(db.Integer, primary_key=True)
    product_barcode = db.Column(db.String(64), unique=True, index=True, nullable=False)
    product_main_id = db.Column(db.String, index=True)     # grup için
    note = db.Column(db.String(255))
    min_cover_days = db.Column(db.Integer, default=10)
    safety_factor = db.Column(db.Float, default=0.20)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class CentralStock(db.Model):
    __tablename__ = "central_stock"

    barcode = db.Column(db.String, primary_key=True)   # Ürün barkodu
    qty = db.Column(db.Integer, nullable=False, default=0)  # Merkezdeki toplam adet
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


### --- YENİ EKLENEN GÜNLÜK RAPOR MODELİ --- ###
class Rapor(db.Model):
    __tablename__ = 'raporlar'

    id = db.Column(db.Integer, primary_key=True)
    icerik = db.Column(db.Text, nullable=True)
    zaman_damgasi = db.Column(DateTime, nullable=False, default=datetime.utcnow)
    kullanici_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    kullanici = db.relationship('User', backref=db.backref('raporlar', lazy=True))
    kategori = db.Column(db.String(100), nullable=False)
    aciklama = db.Column(db.Text, nullable=True)
    veri = db.Column(JSON, nullable=True)

    def __repr__(self):
        kullanici_adi = self.kullanici.username if self.kullanici else 'Bilinmeyen'
        return f'<Rapor ID: {self.id} - Kullanıcı: {kullanici_adi} - Zaman: {self.zaman_damgasi.strftime("%Y-%m-%d %H:%M")}>'

class Raf(db.Model):
    __tablename__ = 'raflar'

    id = db.Column(db.Integer, primary_key=True)
    kod = db.Column(db.String, unique=True, nullable=False)
    ana = db.Column(db.String, nullable=False)
    ikincil = db.Column(db.String, nullable=False)
    kat = db.Column(db.String, nullable=False)
    barcode_path = db.Column(db.String)
    qr_path = db.Column(db.String)

class RafUrun(db.Model):
    __tablename__ = "raf_urunleri"

    id = db.Column(db.Integer, primary_key=True)
    raf_kodu = db.Column(db.String, db.ForeignKey("raflar.kod"), nullable=False)
    urun_barkodu = db.Column(db.String, nullable=False)
    adet = db.Column(db.Integer, default=1)

    __table_args__ = (db.UniqueConstraint("raf_kodu", "urun_barkodu", name="u_raf_urun"),)


# Bu modeller db.Model'dan türetilmeli
class Shipment(db.Model):
    __tablename__ = 'shipments'
    id = db.Column(db.Integer, primary_key=True)
    # order_id ForeignKey tanımlaması düzeltildi (önceki kodda 'orders.id' string idi)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id')) # 'orders' tablosu var mı kontrol et, yoksa ilgili tablo adı yazılmalı
    shipping_cost = db.Column(db.Float, nullable=False)
    shipping_provider = db.Column(db.String(100))
    date_shipped = db.Column(db.DateTime, default=datetime.utcnow)
    # Order ilişkisi (isteğe bağlı)
    # order = db.relationship('Order', backref=db.backref('shipments', lazy=True)) # Eğer Order modeli varsa

class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    expense_type = db.Column(db.String(100))
    description = db.Column(db.String(255))
    amount = db.Column(db.Float, nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

class ExcelUpload(db.Model):
    __tablename__ = 'excel_uploads'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ExcelUpload filename={self.filename}, upload_time={self.upload_time}>"

# Sipariş Fişi - Bu model diğer sipariş yapısıyla pek uyumlu görünmüyor.
# Belki ayrı bir işlev için kullanılıyor. Şimdilik dokunmuyoruz.
class SiparisFisi(db.Model):
    __tablename__ = 'siparis_fisi'
    siparis_id = db.Column(db.Integer, primary_key=True)
    urun_model_kodu = db.Column(db.String(255))
    renk = db.Column(db.String(100))
    kalemler_json = db.Column(db.Text, default='[]')
    barkod_35 = db.Column(db.String(100))
    barkod_36 = db.Column(db.String(100))
    barkod_37 = db.Column(db.String(100))
    barkod_38 = db.Column(db.String(100))
    barkod_39 = db.Column(db.String(100))
    barkod_40 = db.Column(db.String(100))
    barkod_41 = db.Column(db.String(100))
    beden_35 = db.Column(db.Integer, default=0)
    beden_36 = db.Column(db.Integer, default=0)
    beden_37 = db.Column(db.Integer, default=0)
    beden_38 = db.Column(db.Integer, default=0)
    beden_39 = db.Column(db.Integer, default=0)
    beden_40 = db.Column(db.Integer, default=0)
    beden_41 = db.Column(db.Integer, default=0)
    cift_basi_fiyat = db.Column(db.Float, default=0)
    toplam_adet = db.Column(db.Integer, default=0)
    toplam_fiyat = db.Column(db.Float, default=0)
    created_date = db.Column(db.DateTime, default=None)
    print_date = db.Column(db.DateTime, default=None)
    teslim_kayitlari = db.Column(db.Text, default=None)
    kalan_adet = db.Column(db.Integer, default=0)
    is_printed = db.Column(db.Boolean, default=False, nullable=False)
    printed_barcodes = db.Column(JSON, default=list, nullable=False)
    image_url = db.Column(db.String)


# İade Siparişleri - db.Model'dan türetilmeli
class ReturnOrder(db.Model): # db.Model'dan türedi
    __tablename__ = 'return_orders'
    id = db.Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4) # db.Column kullanıldı
    order_number = db.Column(db.String) # db.String
    return_request_number = db.Column(db.String, unique=True, nullable=True, index=True) # unique ve index eklenebilir
    status = db.Column(db.String, index=True) # db.String
    return_date = db.Column(db.DateTime, default=datetime.utcnow) # db.DateTime
    process_date = db.Column(db.DateTime, nullable=True)
    customer_first_name = db.Column(db.String, nullable=True)
    customer_last_name = db.Column(db.String, nullable=True)
    cargo_tracking_number = db.Column(db.String, nullable=True)
    cargo_provider_name = db.Column(db.String, nullable=True)
    cargo_sender_number = db.Column(db.String, nullable=True) # Trendyol'un iade için verdiği kod olabilir
    cargo_tracking_link = db.Column(db.String, nullable=True)
    processed_by = db.Column(db.String, nullable=True) # User.id ile ForeignKey olabilir
    return_reason = db.Column(db.String, nullable=True)
    customer_explanation = db.Column(db.Text, nullable=True) # Text daha uygun olabilir
    return_category = db.Column(db.String, nullable=True)
    notes = db.Column(db.Text, nullable=True) # Text daha uygun olabilir
    approval_reason = db.Column(db.Text, nullable=True) # Text daha uygun olabilir
    refund_amount = db.Column(db.Float, nullable=True)
    products = db.relationship('ReturnProduct', backref='return_order', lazy='dynamic', cascade="all, delete-orphan") # lazy='dynamic' çok ürün varsa iyi


# İade Edilen Ürünler - db.Model'dan türetilmeli
class ReturnProduct(db.Model):
    __tablename__ = 'return_products'
    id = db.Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    return_order_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey('return_orders.id'), nullable=False) # nullable=False olmalı
    # product_id = db.Column(db.String) # Bu bizim sistemimizdeki ürün ID'si mi? Product.barcode ile FK olabilir.
    barcode = db.Column(db.String, index=True) # db.String
    # model_number = db.Column(db.String) # product_code veya merchant_sku olabilir
    product_name = db.Column(db.String, nullable=True) # İade anındaki ürün adı
    size = db.Column(db.String, nullable=True)
    color = db.Column(db.String, nullable=True)
    quantity = db.Column(db.Integer, nullable=False, default=1) # Genelde 1 olur ama API farklı verebilir
    reason = db.Column(db.String, nullable=True) # Satır bazlı iade nedeni
    claim_line_item_id = db.Column(db.String, index=True, nullable=True) # Trendyol iade satır ID'si
    product_condition = db.Column(db.String, nullable=True)
    damage_description = db.Column(db.Text, nullable=True)
    inspection_notes = db.Column(db.Text, nullable=True)
    return_to_stock = db.Column(db.Boolean, default=False, nullable=False)


# Kullanıcı Modeli
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(150), nullable=False)
    last_name = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False) # Hashlenmiş şifre saklanmalı
    role = db.Column(db.String(50), default='worker') # Varsayılan rol
    status = db.Column(db.String(50), default='pending') # Onay bekliyor durumu
    totp_secret = db.Column(db.String(16))
    totp_confirmed = db.Column(db.Boolean, default=False)
    # backref ile UserLog ilişkisi UserLog modelinde tanımlandı

# Analiz ve hesaplar için kullanılacak OrderItem (Bu muhtemelen eski Order modeliyle ilişkili)
# Eğer yeni sipariş yapısıyla (OrderBase) kullanılacaksa ilişkiler güncellenmeli.
class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False) # Eski 'orders' tablosuna bağlı
    product_barcode = db.Column(db.String, db.ForeignKey('products.barcode')) # products.barcode'a bağlı
    product_name = db.Column(db.String)
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float) # Satış fiyatı (KDV dahil?)
    unit_cost = db.Column(db.Float) # Maliyet (USD mi TRY mi?)
    commission = db.Column(db.Float) # Komisyon
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler (Eski Order ve Product modeliyle)
    order = db.relationship('Order', backref=db.backref('items', lazy=True, cascade="all, delete-orphan")) # cascade eklendi
    product = db.relationship('Product', backref=db.backref('order_items', lazy=True)) # backref eklendi


# ──────────────────────────────────────────────────────────────────────────────
# Temel sipariş modeli - tüm statüler için ortak alanlar
# ──────────────────────────────────────────────────────────────────────────────
class OrderBase(db.Model):
    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True)  # Her tabloya ayrı sequence
    order_number = db.Column(db.String, index=True, nullable=False)
    order_date = db.Column(db.DateTime, index=True, nullable=True)

    # API'den gelen orijinal statü (bilgi amaçlı)
    status = db.Column(db.String, nullable=True)

    # Müşteri Bilgileri
    customer_id = db.Column(db.String, index=True, nullable=True)
    customer_name = db.Column(db.String, nullable=True)
    customer_surname = db.Column(db.String, nullable=True)
    customer_address = db.Column(db.Text, nullable=True)

    # Ürün ve Sipariş Detayları
    merchant_sku = db.Column(db.Text, nullable=True)
    product_barcode = db.Column(db.Text, nullable=True)
    product_name = db.Column(db.Text, nullable=True)
    product_code = db.Column(db.Text, nullable=True)
    product_size = db.Column(db.Text, nullable=True)
    product_color = db.Column(db.Text, nullable=True)
    product_main_id = db.Column(db.Text, nullable=True)
    stockCode = db.Column(db.Text, nullable=True)
    line_id = db.Column(db.Text, nullable=True)
    details = db.Column(db.Text, nullable=True)  # JSON string
    quantity = db.Column(db.Integer, nullable=True)

    # Fiyat ve Finansal Bilgiler
    amount = db.Column(db.Float, nullable=True)
    discount = db.Column(db.Float, default=0.0, nullable=True)
    gross_amount = db.Column(db.Float, nullable=True)
    tax_amount = db.Column(db.Float, nullable=True)
    vat_base_amount = db.Column(db.Float, nullable=True)
    commission = db.Column(db.Float, default=0.0, nullable=True)
    currency_code = db.Column(db.String(10), nullable=True)
    product_cost_total = db.Column(db.Float, default=0.0, nullable=True)

    # Kargo ve Paket Bilgileri
    package_number = db.Column(db.String, index=True, nullable=True)
    shipment_package_id = db.Column(db.String, index=True, nullable=True)
    shipping_barcode = db.Column(db.String, nullable=True)
    cargo_tracking_number = db.Column(db.String, index=True, nullable=True)
    cargo_provider_name = db.Column(db.String, nullable=True)
    cargo_tracking_link = db.Column(db.String, nullable=True)
    shipment_package_status = db.Column(db.String, nullable=True)

    # Tarihler
    origin_shipment_date = db.Column(db.DateTime, nullable=True)
    estimated_delivery_start = db.Column(db.DateTime, nullable=True)
    estimated_delivery_end = db.Column(db.DateTime, index=True, nullable=True)
    agreed_delivery_date = db.Column(db.DateTime, nullable=True)
    last_modified_date = db.Column(db.DateTime, index=True, nullable=True)

    # Diğer Alanlar
    match_status = db.Column(db.String, nullable=True)
    images = db.Column(db.Text, nullable=True)
    product_model_code = db.Column(db.Text, nullable=True)

    # Kayıt Zaman Damgaları
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ──────────────────────────────────────────────────────────────────────────────
# Statü tabloları
# ──────────────────────────────────────────────────────────────────────────────

# Yeni sipariş (Created)
class OrderCreated(OrderBase):
    __tablename__ = 'orders_created'
    # statüye özel alan gerekirse eklenir


# İşleme alınan (Picking)
class OrderPicking(OrderBase):
    __tablename__ = 'orders_picking'
    picking_start_time = db.Column(db.DateTime, default=datetime.utcnow)
    picked_by = db.Column(db.String)


# Kargoda (Shipped)
class OrderShipped(OrderBase):
    __tablename__ = 'orders_shipped'
    shipping_time = db.Column(db.DateTime, default=datetime.utcnow)
    tracking_updated = db.Column(db.Boolean, default=False)


# Teslim (Delivered)
class OrderDelivered(OrderBase):
    __tablename__ = 'orders_delivered'
    delivery_date = db.Column(db.DateTime)
    delivery_confirmed = db.Column(db.Boolean, default=False)


# İptal (Cancelled)
class OrderCancelled(OrderBase):
    __tablename__ = 'orders_cancelled'
    cancellation_date = db.Column(db.DateTime, default=datetime.utcnow)
    cancellation_reason = db.Column(db.String)


# Arşiv (Archived)
class OrderArchived(OrderBase):
    __tablename__ = 'orders_archived'
    archive_date = db.Column(db.DateTime, default=datetime.utcnow)
    archive_reason = db.Column(db.String)


# 🔥 YENİ: Hazır Gönderim (ReadyToShip)
class OrderReadyToShip(OrderBase):
    __tablename__ = 'orders_ready_to_ship'
    # İstersen bu statüye özgü küçük alanlar:
    ready_since = db.Column(db.DateTime, default=datetime.utcnow)   # “hazır”a geçtiği an
    label_printed = db.Column(db.Boolean, default=False)            # etiketi basıldı mı


# Geriye dönük uyumluluk için mevcut sipariş tablosu ('orders')
# Bu tablodan da original_product_barcode kaldırılıyor.
# Eğer bu tablo artık kullanılmıyorsa tamamen kaldırılabilir.
class Order(db.Model):
    __tablename__ = 'orders'
    __table_args__ = (
        db.Index('idx_orders_order_number', 'order_number'), # Index isimleri düzeltildi
        db.Index('idx_orders_status', 'status'),
        db.Index('idx_orders_order_date', 'order_date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String)
    order_date = db.Column(db.DateTime)
    merchant_sku = db.Column(db.String)
    product_barcode = db.Column(db.Text) # Virgülle ayrılmış orijinal barkodlar
    # original_product_barcode = db.Column(db.String) # --- BU ALAN KALDIRILDI ---
    status = db.Column(db.String)
    line_id = db.Column(db.String) # Text olabilir
    match_status = db.Column(db.String)
    customer_name = db.Column(db.String)
    customer_surname = db.Column(db.String)
    customer_address = db.Column(db.Text)
    shipping_barcode = db.Column(db.String)
    cargo_tracking_number = db.Column(db.String) # Tekrarlı alan?
    product_name = db.Column(db.Text)
    product_code = db.Column(db.Text)
    amount = db.Column(db.Float)
    discount = db.Column(db.Float, default=0.0)
    currency_code = db.Column(db.String(10))
    vat_base_amount = db.Column(db.Float)
    package_number = db.Column(db.String)
    stockCode = db.Column(db.Text)
    estimated_delivery_start = db.Column(db.DateTime)
    images = db.Column(db.Text)
    product_model_code = db.Column(db.Text)
    estimated_delivery_end = db.Column(db.DateTime)
    origin_shipment_date = db.Column(db.DateTime)
    product_size = db.Column(db.Text)
    product_main_id = db.Column(db.Text)
    cargo_provider_name = db.Column(db.String)
    agreed_delivery_date = db.Column(db.DateTime)
    product_color = db.Column(db.Text)
    cargo_tracking_link = db.Column(db.String)
    shipment_package_id = db.Column(db.String)
    details = db.Column(db.Text)
    # archive_date = db.Column(db.DateTime) # Bu alan OrderArchived tablosunda
    # archive_reason = db.Column(db.String) # Bu alan OrderArchived tablosunda
    quantity = db.Column(db.Integer)
    # delivery_date = db.Column(db.DateTime) # Bu alan OrderDelivered tablosunda
    commission = db.Column(db.Float, default=0.0)
    product_cost_total = db.Column(db.Float, default=0.0)
    # İlişkiler (OrderItem'a) - Zaten OrderItem modelinde tanımlı

class ProductArchive(db.Model):
    __tablename__ = 'product_archive'

    # --- Önceki tüm alanlar burada yer alıyor ---
    # ... (barcode, title, brand, category_name, vs.)
    barcode = db.Column(db.String, primary_key=True)
    title = db.Column(db.String)
    product_main_id = db.Column(db.String)
    quantity = db.Column(db.Integer)
    images = db.Column(db.String)
    variants = db.Column(db.String)
    size = db.Column(db.String)
    color = db.Column(db.String)
    archived = db.Column(db.Boolean)
    locked = db.Column(db.Boolean)
    on_sale = db.Column(db.Boolean)
    reject_reason = db.Column(db.String)
    sale_price = db.Column(db.Float)
    list_price = db.Column(db.Float)
    currency_type = db.Column(db.String)
    archive_date = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.Text, nullable=True)
    attributes = db.Column(db.Text, nullable=True)
    brand = db.Column(db.String(255), nullable=True)
    category_name = db.Column(db.String(255), nullable=True)
    category_id = db.Column(db.Integer, nullable=True)
    stock_code = db.Column(db.String(255), nullable=True)
    shipment_address_id = db.Column(db.Integer, nullable=True)
    delivery_duration = db.Column(db.Integer, nullable=True)
    cargo_company_id = db.Column(db.Integer, nullable=True)
    dimensional_weight = db.Column(db.Float, nullable=True)
    vat_rate = db.Column(db.Integer, nullable=True)

    # --- YENİ EKLENEN ALANLAR (07.07.2025) ---
    status = db.Column(db.String(50), nullable=True)
    gtin = db.Column(db.String(255), nullable=True)
    last_update_date = db.Column(db.DateTime, nullable=True)
    brand_id = db.Column(db.Integer, nullable=True)
    create_date_time = db.Column(db.DateTime, nullable=True)
    gender = db.Column(db.String(50), nullable=True)
    has_active_campaign = db.Column(db.Boolean, nullable=True)
    trendyol_id = db.Column(db.String(255), nullable=True)
    pim_category_id = db.Column(db.Integer, nullable=True)
    platform_listing_id = db.Column(db.String(255), nullable=True)
    product_code = db.Column(db.String(255), nullable=True)
    product_content_id = db.Column(db.Integer, nullable=True)
    stock_unit_type = db.Column(db.String(50), nullable=True)
    supplier_id = db.Column(db.Integer, nullable=True)
    is_rejected = db.Column(db.Boolean, nullable=True)
    is_blacklisted = db.Column(db.Boolean, nullable=True)
    has_html_content = db.Column(db.Boolean, nullable=True)
    product_url = db.Column(db.Text, nullable=True)
    is_approved = db.Column(db.Boolean, nullable=True)

    def __init__(self, **kwargs):
        super(ProductArchive, self).__init__(**kwargs)


class Product(db.Model):
    __tablename__ = 'products'

    barcode = db.Column(db.String, primary_key=True)
    title = db.Column(db.String)
    hidden = db.Column(db.Boolean, default=False)
    product_main_id = db.Column(db.String)
    quantity = db.Column(db.Integer)
    images = db.Column(db.String)
    variants = db.Column(db.String)
    size = db.Column(db.String)
    color = db.Column(db.String)
    archived = db.Column(db.Boolean)
    locked = db.Column(db.Boolean)
    on_sale = db.Column(db.Boolean)
    reject_reason = db.Column(db.String)
    sale_price = db.Column(db.Float)
    list_price = db.Column(db.Float)
    currency_type = db.Column(db.String)
    cost_usd = db.Column(db.Float, default=0.0)
    cost_date = db.Column(db.DateTime)
    cost_try = db.Column(db.Float, default=0)
    description = db.Column(db.Text, nullable=True)
    attributes = db.Column(db.Text, nullable=True)
    brand = db.Column(db.String(255), nullable=True)
    category_name = db.Column(db.String(255), nullable=True)
    category_id = db.Column(db.Integer, nullable=True)
    stock_code = db.Column(db.String(255), nullable=True)
    shipment_address_id = db.Column(db.Integer, nullable=True)
    delivery_duration = db.Column(db.Integer, nullable=True)
    cargo_company_id = db.Column(db.Integer, nullable=True)
    dimensional_weight = db.Column(db.Float, nullable=True)
    vat_rate = db.Column(db.Integer, nullable=True)

    # --- YENİ EKLENEN ALANLAR (TÜM VERİLER) ---
    brand_id = db.Column(db.Integer, nullable=True)
    create_date_time = db.Column(db.DateTime, nullable=True)
    gender = db.Column(db.String(50), nullable=True)
    has_active_campaign = db.Column(db.Boolean, nullable=True)
    trendyol_id = db.Column(db.String(255), nullable=True) # Trendyol'un kendi ürün ID'si
    pim_category_id = db.Column(db.Integer, nullable=True)
    platform_listing_id = db.Column(db.String(255), nullable=True)
    product_code = db.Column(db.String(255), nullable=True)
    product_content_id = db.Column(db.Integer, nullable=True)
    stock_unit_type = db.Column(db.String(50), nullable=True)
    supplier_id = db.Column(db.Integer, nullable=True)
    is_rejected = db.Column(db.Boolean, nullable=True)
    is_blacklisted = db.Column(db.Boolean, nullable=True)
    has_html_content = db.Column(db.Boolean, nullable=True)
    product_url = db.Column(db.Text, nullable=True)
    is_approved = db.Column(db.Boolean, nullable=True)
    status = db.Column(db.String(50), nullable=True)
    gtin = db.Column(db.String(255), nullable=True)
    last_update_date = db.Column(db.DateTime, nullable=True)


# Eğer farklıysa, buradan da original_product_barcode'u kaldıralım.
class Archive(db.Model):
    __tablename__ = 'archive' # Bu tablo adı OrderArchived ile çakışıyor mu? Dikkat!

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String)
    order_date = db.Column(db.DateTime)
    merchant_sku = db.Column(db.String)
    product_barcode = db.Column(db.Text) # Orijinal barkodlar
    # original_product_barcode = db.Column(db.String) # --- BU ALAN KALDIRILDI ---
    status = db.Column(db.String) # Arşivlendiğindeki statü?
    line_id = db.Column(db.String) # Text olabilir
    match_status = db.Column(db.String)
    customer_name = db.Column(db.String)
    customer_surname = db.Column(db.String)
    customer_address = db.Column(db.Text)
    shipping_barcode = db.Column(db.String)
    product_name = db.Column(db.Text)
    product_code = db.Column(db.Text)
    amount = db.Column(db.Float)
    discount = db.Column(db.Float)
    currency_code = db.Column(db.String(10))
    vat_base_amount = db.Column(db.Float)
    package_number = db.Column(db.String)
    stockCode = db.Column(db.Text)
    estimated_delivery_start = db.Column(db.DateTime)
    images = db.Column(db.Text)
    product_model_code = db.Column(db.Text)
    estimated_delivery_end = db.Column(db.DateTime)
    origin_shipment_date = db.Column(db.DateTime)
    product_size = db.Column(db.Text)
    product_main_id = db.Column(db.Text)
    cargo_provider_name = db.Column(db.String)
    agreed_delivery_date = db.Column(db.DateTime)
    product_color = db.Column(db.Text)
    cargo_tracking_link = db.Column(db.String)
    shipment_package_id = db.Column(db.String)
    details = db.Column(db.Text)
    archive_date = db.Column(db.DateTime, default=datetime.utcnow)
    archive_reason = db.Column(db.String)
    # quantity, commission gibi alanlar eksikse OrderArchived'dan eklenebilir.

    def __repr__(self):
        return f"<Archive {self.order_number}>"

# Değişim Modeli ('yeni_siparisler' ve 'siparis_urunler' ile ilişkili mi?)
class YeniSiparis(db.Model):
    __tablename__ = 'yeni_siparisler' # Değişim talepleri için ayrı tablo daha iyi olabilir
    id = db.Column(db.Integer, primary_key=True)
    siparis_no = db.Column(db.String, unique=True, nullable=False) # Boş olmamalı
    musteri_adi = db.Column(db.String)
    musteri_soyadi = db.Column(db.String)
    musteri_adres = db.Column(db.Text)
    musteri_telefon = db.Column(db.String)
    siparis_tarihi = db.Column(db.DateTime, default=datetime.utcnow)
    toplam_tutar = db.Column(db.Float)
    durum = db.Column(db.String, default='Yeni') # Değişim durumu? (Bekliyor, Onaylandı, Kargoda...)
    notlar = db.Column(db.Text)
    # İlişki
    urunler = db.relationship('SiparisUrun', backref='yeni_siparis', lazy=True, cascade="all, delete-orphan")

class SiparisUrun(db.Model):
    __tablename__ = 'siparis_urunler' # Değişim ürünleri tablosu?
    id = db.Column(db.Integer, primary_key=True)
    siparis_id = db.Column(db.Integer, db.ForeignKey('yeni_siparisler.id'))
    urun_barkod = db.Column(db.String) # Gelen/Giden ürün barkodu?
    urun_adi = db.Column(db.String)
    adet = db.Column(db.Integer)
    birim_fiyat = db.Column(db.Float)
    toplam_fiyat = db.Column(db.Float)
    renk = db.Column(db.String)
    beden = db.Column(db.String)
    urun_gorseli = db.Column(db.String)



### ----> İSTEDİĞİN GÜNCELLEME BURADA <---- ###
class Degisim(db.Model):
    __tablename__ = 'degisim'
    id = db.Column(db.Integer, primary_key=True)
    degisim_no = db.Column(db.String, unique=True, nullable=False, index=True)
    siparis_no = db.Column(db.String, index=True)
    ad = db.Column(db.String)
    soyad = db.Column(db.String)
    adres = db.Column(db.Text)
    telefon_no = db.Column(db.String)
    degisim_tarihi = db.Column(db.DateTime, default=datetime.utcnow)
    degisim_durumu = db.Column(db.String, index=True)
    kargo_kodu = db.Column(db.String)
    degisim_nedeni = db.Column(db.Text)
    # GÜNCELLENDİ: Tekil ürün alanları kaldırıldı, yerine JSON alanı eklendi.
    urunler_json = db.Column(db.Text, nullable=False)
    musteri_kargo_takip = db.Column(db.String(64), nullable=True)


    def __repr__(self):
        return f"<Degisim {self.degisim_no}>"

# İade Modeli (Bu model ReturnOrder/ReturnProduct ile çakışıyor gibi?)
# Eğer bu kullanılacaksa, ReturnOrder/ReturnProduct kaldırılabilir.
class Return(db.Model):
    """İade bilgilerini tutan tablo"""
    __tablename__ = 'returns'
    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.String(50), unique=True, nullable=False, index=True) # Trendyol iade ID
    order_number = db.Column(db.String(50), index=True)
    order_line_id = db.Column(db.String(50), index=True) # İade edilen ürün satır ID
    status = db.Column(db.String(50), index=True) # İade durumu (Created, Accepted, Rejected, Refunded...)
    reason = db.Column(db.String(255)) # İade nedeni
    barcode = db.Column(db.String(100)) # İade edilen ürün barkodu
    product_name = db.Column(db.String(255))
    product_color = db.Column(db.String(50))
    product_size = db.Column(db.String(50))
    quantity = db.Column(db.Integer, default=1) # Genelde 1 olur
    customer_name = db.Column(db.String(100)) # API'den geliyorsa
    address = db.Column(db.Text) # API'den geliyorsa
    create_date = db.Column(db.DateTime) # İade talebi oluşturulma tarihi
    last_modified_date = db.Column(db.DateTime, onupdate=datetime.utcnow) # Son güncelleme
    notes = db.Column(db.Text) # Manuel notlar
    details = db.Column(db.Text) # API'den gelen tüm JSON detayları

    def __repr__(self):
        return f"<Return {self.claim_id}>"

# Kullanıcı Log Modeli
class UserLog(db.Model):
    __tablename__ = 'user_logs'
    id = db.Column(db.Integer, primary_key=True)
    # user_id null olabilir (örn: sistem logları için)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    action = db.Column(db.String(255), nullable=False, index=True)
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    ip_address = db.Column(db.String(45)) # IPv6 desteği için 45 karakter
    page_url = db.Column(db.String(255)) # Logun oluştuğu sayfa URL'si
    status_code = db.Column(db.Integer, nullable=True) # İşlem sonucu (örn: HTTP status)
    # İlişki
    user = db.relationship('User', backref=db.backref('logs', lazy='dynamic')) # lazy='dynamic' çok sayıda log varsa performansı artırır

# Kasa modeli - Gelir ve gider kayıtları
class Kasa(db.Model):
    __tablename__ = 'kasa'
    id = db.Column(db.Integer, primary_key=True)
    tip = db.Column(db.String(50), nullable=False)  # 'gelir' veya 'gider'
    aciklama = db.Column(db.Text, nullable=False)
    tutar = db.Column(db.Float, nullable=False)
    tarih = db.Column(db.DateTime, default=datetime.utcnow)
    kullanici_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    kategori = db.Column(db.String(100), nullable=True)  # Kategori (opsiyonel)
    
    # Relationship to User model
    kullanici = db.relationship('User', backref='kasa_kayitlari')
    
    def __repr__(self):
        return f"<Kasa {self.tip}: {self.tutar} TL>"

# Kasa Kategori modeli - Kategori yönetimi
class KasaKategori(db.Model):
    __tablename__ = 'kasa_kategoriler'
    id = db.Column(db.Integer, primary_key=True)
    kategori_adi = db.Column(db.String(100), nullable=False, unique=True)
    aciklama = db.Column(db.Text, nullable=True)
    renk = db.Column(db.String(7), default='#007bff')  # Hex renk kodu
    aktif = db.Column(db.Boolean, default=True)
    olusturma_tarihi = db.Column(db.DateTime, default=datetime.utcnow)
    olusturan_kullanici_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Relationship to User model
    olusturan_kullanici = db.relationship('User', backref='olusturulan_kategoriler')
    
    def __repr__(self):
        return f"<KasaKategori {self.kategori_adi}>"
        


        # --- GÖREV MODELLERİ (temiz) ---

class TaskTemplate(db.Model):
    __tablename__ = "task_templates"
    id             = db.Column(db.Integer, primary_key=True)
    assignee       = db.Column(db.String(80),  nullable=False)
    assignee_email = db.Column(db.String(120))
    title          = db.Column(db.String(120), nullable=False)
    due_h          = db.Column(db.Integer,      nullable=False, default=11)
    due_m          = db.Column(db.Integer,      nullable=False, default=0)
    weekdays       = db.Column(db.String(20),   nullable=False, default="0,1,2,3,4")
    priority       = db.Column(db.Integer,      nullable=False, default=2)
    proof_required = db.Column(db.Boolean,      nullable=False, default=False)
    active         = db.Column(db.Boolean,      nullable=False, default=True)

    __table_args__ = (
        db.UniqueConstraint("assignee", "title", name="uq_ttpl_assignee_title"),
    )


class Task(db.Model):
    __tablename__ = "tasks"

    id              = db.Column(db.Integer, primary_key=True)
    assignee        = db.Column(db.String(80),  nullable=False)
    assignee_email  = db.Column(db.String(120))
    title           = db.Column(db.String(120), nullable=False)
    date_           = db.Column(db.Date,        nullable=False, index=True)
    due             = db.Column(db.DateTime(timezone=True), nullable=False, index=True)  # klasik due (esnekte yedek)
    priority        = db.Column(db.Integer,     nullable=False, default=2)
    status          = db.Column(db.String(16),  nullable=False, default="bekliyor")
    proof_required  = db.Column(db.Boolean,     nullable=False, default=False)
    proof_url       = db.Column(db.String(300))
    reminded_30     = db.Column(db.Boolean,     nullable=False, default=False)
    reminded_10     = db.Column(db.Boolean,     nullable=False, default=False)

    # --- ESNEK GÖREV alanları ---
    flexible        = db.Column(db.Boolean,     nullable=False, default=True)          # çalışan planlar mı?
    expected_window = db.Column(db.String(12),  nullable=False, default="this_week")   # today|this_week|custom
    sla_latest      = db.Column(db.Date)                                               # en geç gün (opsiyonel)
    acceptance      = db.Column(db.Text)                                               # kabul kriteri (opsiyonel)
    effort          = db.Column(db.Integer,     default=1)                              # iş yükü puanı
    commit_due      = db.Column(db.DateTime(timezone=True), index=True)                 # çalışanın taahhüt ettiği teslim
    commit_at       = db.Column(db.DateTime(timezone=True))                             # taahhüt zamanı

    __table_args__ = (
        db.UniqueConstraint("assignee", "title", "date_", name="uq_tasks_assignee_title_date"),
        db.Index("ix_tasks_assignee_date", "assignee", "date_"),
        db.Index("ix_tasks_commit_due", "commit_due"),
    )




class MasterTask(db.Model):
    __tablename__ = "master_tasks"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text)
    default_due_h = db.Column(db.Integer, default=11, nullable=False)
    default_due_m = db.Column(db.Integer, default=0,  nullable=False)
    default_weekdays = db.Column(db.String(20), default="0,1,2,3,4", nullable=False)
    default_priority = db.Column(db.Integer, default=2, nullable=False)
    proof_required = db.Column(db.Boolean, default=False, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

        
