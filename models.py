# models.py
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB # JSONB daha iyi olabilir
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float, Boolean, Text, Index 
from datetime import datetime
import uuid

db = SQLAlchemy()

class Shipment(db.Model):
    __tablename__ = 'shipments'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders_delivered.id')) # Veya hangi sipariş tablosuna aitse
    shipping_cost = db.Column(db.Float, nullable=False)
    shipping_provider = db.Column(db.String(100))
    date_shipped = db.Column(db.DateTime, default=datetime.utcnow)

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

class SiparisFisi(db.Model):
    __tablename__ = 'siparis_fisi'
    siparis_id = db.Column(db.Integer, primary_key=True, autoincrement=True) # autoincrement eklendi
    urun_model_kodu = db.Column(db.String(255)) # Bu 255 olmalı, DB'yi güncellemelisin
    renk = db.Column(db.String(100))
    kalemler_json = db.Column(JSONB, default=list) # JSONB daha iyi olabilir
    barkod_35 = db.Column(db.String(100), nullable=True)
    barkod_36 = db.Column(db.String(100), nullable=True)
    barkod_37 = db.Column(db.String(100), nullable=True)
    barkod_38 = db.Column(db.String(100), nullable=True)
    barkod_39 = db.Column(db.String(100), nullable=True)
    barkod_40 = db.Column(db.String(100), nullable=True)
    barkod_41 = db.Column(db.String(100), nullable=True)
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
    created_date = db.Column(db.DateTime, default=datetime.utcnow) # default olarak utcnow
    print_date = db.Column(db.DateTime, nullable=True)
    teslim_kayitlari = db.Column(JSONB, nullable=True) # JSONB
    kalan_adet = db.Column(db.Integer, default=0)
    is_printed = db.Column(db.Boolean, default=False, nullable=False)
    printed_barcodes = db.Column(JSONB, default=list, nullable=False) # JSONB
    image_url = db.Column(db.String, nullable=True)


class ReturnOrder(db.Model): 
    __tablename__ = 'return_orders'
    id = db.Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4) 
    order_number = db.Column(db.String(100), index=True) # Uzunluk eklendi
    return_request_number = db.Column(db.String(100), unique=True, nullable=True, index=True) 
    status = db.Column(db.String(50), index=True) 
    return_date = db.Column(db.DateTime, default=datetime.utcnow) 
    process_date = db.Column(db.DateTime, nullable=True)
    customer_first_name = db.Column(db.String(150), nullable=True)
    customer_last_name = db.Column(db.String(150), nullable=True)
    cargo_tracking_number = db.Column(db.String(100), nullable=True)
    cargo_provider_name = db.Column(db.String(100), nullable=True)
    cargo_sender_number = db.Column(db.String(100), nullable=True) 
    cargo_tracking_link = db.Column(db.String(255), nullable=True)
    processed_by = db.Column(db.String(150), nullable=True) 
    return_reason = db.Column(db.String(255), nullable=True)
    customer_explanation = db.Column(db.Text, nullable=True) 
    return_category = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True) 
    approval_reason = db.Column(db.Text, nullable=True) 
    refund_amount = db.Column(db.Float, nullable=True)
    products = db.relationship('ReturnProduct', backref='return_order', lazy='dynamic', cascade="all, delete-orphan") 

class ReturnProduct(db.Model):
    __tablename__ = 'return_products'
    id = db.Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    return_order_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey('return_orders.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.String(100), nullable=True) # Trendyol Product ID (claim_line_item_id ile aynı olabilir mi?)
    barcode = db.Column(db.String(100), db.ForeignKey('products.barcode', ondelete='SET NULL'), index=True, nullable=True) # products tablosuna FK
    model_number = db.Column(db.String(100), nullable=True) # merchantSku için
    product_name = db.Column(db.String(255), nullable=True) 
    size = db.Column(db.String(50), nullable=True)
    color = db.Column(db.String(50), nullable=True)
    quantity = db.Column(db.Integer, nullable=False, default=1) 
    reason = db.Column(db.String(255), nullable=True) 
    claim_line_item_id = db.Column(db.String(100), index=True, nullable=True) 
    product_condition = db.Column(db.String(100), nullable=True)
    damage_description = db.Column(db.Text, nullable=True)
    inspection_notes = db.Column(db.Text, nullable=True)
    return_to_stock = db.Column(db.Boolean, default=False, nullable=False)
    # Product ile ilişki (opsiyonel, eğer barcode FK ise)
    # product_ref = db.relationship('Product', backref=db.backref('returned_items', lazy='dynamic'))


class User(db.Model): # flask_login.UserMixin ekleyebilirsin
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(150), nullable=False)
    last_name = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(150), unique=True, nullable=False, index=True)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password = db.Column(db.String(256), nullable=False) 
    role = db.Column(db.String(50), default='worker', index=True) 
    status = db.Column(db.String(50), default='pending', index=True) 
    totp_secret = db.Column(db.String(32)) # Genelde 16 veya 32 karakter olur Base32
    totp_confirmed = db.Column(db.Boolean, default=False)
    # UserLog ilişkisi backref ile UserLog modelinde tanımlanacak

    # Flask-Login için gerekli metodlar (UserMixin eklenirse otomatik gelir bir kısmı)
    @property
    def is_active(self):
        return self.status == 'active'

    @property
    def is_authenticated(self):
        return True # Oturumda user_id varsa authenticated sayılır

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)


class OrderItem(db.Model):
    __tablename__ = 'order_items' # Bu tablo artık kullanılmıyor gibi, yeni sipariş yapısı var
    id = db.Column(db.Integer, primary_key=True)
    # order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False) # 'orders' tablosu eski
    # Bu ForeignKey'ler OrderCreated, OrderPicking vb. tablolardan birine bağlanmalı veya bu model kaldırılmalı.
    # Şimdilik ForeignKey'leri yorum satırı yapıyorum, hangi tabloya bağlanacağı belirsiz.
    # order_id = db.Column(db.Integer, nullable=False) 
    product_barcode = db.Column(db.String(100), db.ForeignKey('products.barcode', ondelete='SET NULL'), nullable=True) 
    product_name = db.Column(db.String(255))
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float) 
    unit_cost = db.Column(db.Float) 
    commission = db.Column(db.Float) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # order = db.relationship('Order', backref=db.backref('items', lazy=True, cascade="all, delete-orphan"))
    product = db.relationship('Product', backref=db.backref('order_items', lazy='dynamic'))


class OrderBase(db.Model):
    __abstract__ = True
    id = db.Column(db.Integer, primary_key=True, autoincrement=True) 
    order_number = db.Column(db.String(100), index=True, nullable=False) 
    order_date = db.Column(db.DateTime, index=True, nullable=True) 
    status = db.Column(db.String(50), nullable=True) 
    customer_id = db.Column(db.String(100), index=True, nullable=True) 
    customer_name = db.Column(db.String(150), nullable=True)
    customer_surname = db.Column(db.String(150), nullable=True)
    customer_address = db.Column(db.Text, nullable=True)
    merchant_sku = db.Column(db.Text, nullable=True) 
    product_barcode = db.Column(db.Text, nullable=True) 
    product_name = db.Column(db.Text, nullable=True) 
    product_code = db.Column(db.Text, nullable=True) 
    product_size = db.Column(db.Text, nullable=True) 
    product_color = db.Column(db.Text, nullable=True) 
    product_main_id = db.Column(db.Text, nullable=True) 
    stockCode = db.Column(db.Text, nullable=True) 
    line_id = db.Column(db.Text, nullable=True) 
    details = db.Column(JSONB, nullable=True) # JSONB daha iyi
    quantity = db.Column(db.Integer, nullable=True) 
    amount = db.Column(db.Float, nullable=True) 
    discount = db.Column(db.Float, default=0.0, nullable=True)
    gross_amount = db.Column(db.Float, nullable=True) 
    tax_amount = db.Column(db.Float, nullable=True) 
    vat_base_amount = db.Column(db.Float, nullable=True) 
    commission = db.Column(db.Float, default=0.0, nullable=True) 
    currency_code = db.Column(db.String(10), nullable=True)
    product_cost_total = db.Column(db.Float, default=0.0, nullable=True)
    package_number = db.Column(db.String(100), index=True, nullable=True) 
    shipment_package_id = db.Column(db.String(100), index=True, nullable=True) 
    shipping_barcode = db.Column(db.String(100), nullable=True) 
    cargo_tracking_number = db.Column(db.String(100), index=True, nullable=True) 
    cargo_provider_name = db.Column(db.String(100), nullable=True)
    cargo_tracking_link = db.Column(db.String(255), nullable=True)
    shipment_package_status = db.Column(db.String(50), nullable=True) 
    origin_shipment_date = db.Column(db.DateTime, nullable=True) 
    estimated_delivery_start = db.Column(db.DateTime, nullable=True)
    estimated_delivery_end = db.Column(db.DateTime, index=True, nullable=True)
    agreed_delivery_date = db.Column(db.DateTime, nullable=True)
    last_modified_date = db.Column(db.DateTime, index=True, nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)
    match_status = db.Column(db.String(50), nullable=True) 
    images = db.Column(db.Text, nullable=True) 
    product_model_code = db.Column(db.Text, nullable=True) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class OrderCreated(OrderBase):
    __tablename__ = 'orders_created'
class OrderPicking(OrderBase):
    __tablename__ = 'orders_picking'
    picking_start_time = db.Column(db.DateTime, default=datetime.utcnow) 
    picked_by = db.Column(db.String(150)) 
class OrderShipped(OrderBase):
    __tablename__ = 'orders_shipped'
    shipping_time = db.Column(db.DateTime, default=datetime.utcnow) 
    tracking_updated = db.Column(db.Boolean, default=False) 
class OrderDelivered(OrderBase):
    __tablename__ = 'orders_delivered'
    delivery_date = db.Column(db.DateTime, nullable=True) # Teslim tarihi nullable olabilir
    delivery_confirmed = db.Column(db.Boolean, default=False) 
class OrderCancelled(OrderBase):
    __tablename__ = 'orders_cancelled'
    cancellation_date = db.Column(db.DateTime, default=datetime.utcnow) 
    cancellation_reason = db.Column(db.String(255)) 
class OrderArchived(OrderBase): # Bu Archive modeli yerine geçebilir
    __tablename__ = 'orders_archived'
    archive_date = db.Column(db.DateTime, default=datetime.utcnow) 
    archive_reason = db.Column(db.String(255)) 


class Order(db.Model): # Eski Order modeli, artık kullanılmıyor olmalı
    __tablename__ = 'orders' # Bu tablo adı diğerleriyle çakışmamalı, belki orders_legacy?
    __table_args__ = (
        db.Index('idx_legacy_orders_order_number', 'order_number'), 
        db.Index('idx_legacy_orders_status', 'status'),
        db.Index('idx_legacy_orders_order_date', 'order_date'),
    )
    id = db.Column(db.Integer, primary_key=True)
    # ... (Diğer kolonlar OrderBase'deki gibi, ama ForeignKey'ler ve ilişkiler gözden geçirilmeli)
    # Şimdilik bu modeli küçültüyorum, OrderBase ve türevleri ana odak olmalı.
    order_number = db.Column(db.String(100))
    status = db.Column(db.String(50))
    order_date = db.Column(db.DateTime)
    # ... (Eski modelin geri kalanını eklemeye gerek yok eğer kullanılmıyorsa)


class ProductArchive(db.Model):
    __tablename__ = 'product_archive' # Tablo adı 'product_archives' olabilir (çoğul)
    barcode = db.Column(db.String(100), primary_key=True) # Uzunluk eklendi
    title = db.Column(db.String(255))
    product_main_id = db.Column(db.String(100), index=True)
    quantity = db.Column(db.Integer)
    images = db.Column(db.Text) # String yerine Text daha uygun olabilir
    variants = db.Column(JSONB) # JSONB
    size = db.Column(db.String(50))
    color = db.Column(db.String(50))
    archived = db.Column(db.Boolean, default=True) # Arşivdeyse True olmalı
    locked = db.Column(db.Boolean, default=False)
    on_sale = db.Column(db.Boolean, default=False)
    reject_reason = db.Column(db.String(255), nullable=True)
    sale_price = db.Column(db.Float)
    list_price = db.Column(db.Float)
    currency_type = db.Column(db.String(10))
    archive_date = db.Column(db.DateTime, default=datetime.utcnow)


class Product(db.Model):
    __tablename__ = 'products'
    barcode = db.Column(db.String(100), primary_key=True) # Uzunluk eklendi
    title = db.Column(db.String(255), nullable=True) # Trendyol'dan gelen başlık
    hidden = db.Column(db.Boolean, default=False, nullable=False) # DB'de BOOLEAN olmalı
    product_main_id = db.Column(db.String(100), index=True, nullable=True) # Model kodu
    quantity = db.Column(db.Integer, default=0, nullable=True)
    images = db.Column(db.Text, nullable=True) # Virgülle ayrılmış URL listesi veya JSON string
    variants = db.Column(JSONB, nullable=True) # Varyant detayları JSONB
    size = db.Column(db.String(50), nullable=True)
    color = db.Column(db.String(50), nullable=True)
    archived = db.Column(db.Boolean, default=False, nullable=False) # Arşivlenmiş mi?
    locked = db.Column(db.Boolean, default=False, nullable=False) # Satışa kilitli mi?
    on_sale = db.Column(db.Boolean, default=True, nullable=False) # Trendyol'da satışta mı?
    reject_reason = db.Column(db.Text, nullable=True) # Reddedilme nedeni (uzun olabilir)
    sale_price = db.Column(db.Float, nullable=True) # Satış fiyatı
    list_price = db.Column(db.Float, nullable=True) # Liste fiyatı
    currency_type = db.Column(db.String(10), default='TRY')
    cost_usd = db.Column(db.Float, default=0.0, nullable=True)
    cost_date = db.Column(db.DateTime, nullable=True)
    cost_try = db.Column(db.Float, default=0.0, nullable=True)

    # __init__ metodunu kaldırıyorum, SQLAlchemy varsayılan constructor'ı kullanır.
    # Gerekirse özel bir __init__ eklenebilir ama alanları direkt atamak daha yaygın.


class Archive(db.Model): # Bu model OrderArchived ile aynı amaçlı mı?
    __tablename__ = 'archive' # Eğer orders_archived kullanılacaksa bu tabloya gerek yok.
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_number = db.Column(db.String(100))
    order_date = db.Column(db.DateTime)
    merchant_sku = db.Column(db.String(255))
    product_barcode = db.Column(db.Text)
    status = db.Column(db.String(50))
    line_id = db.Column(db.Text) # String yerine Text
    match_status = db.Column(db.String(50))
    customer_name = db.Column(db.String(150))
    customer_surname = db.Column(db.String(150))
    customer_address = db.Column(db.Text)
    shipping_barcode = db.Column(db.String(100))
    product_name = db.Column(db.Text)
    product_code = db.Column(db.Text)
    amount = db.Column(db.Float)
    discount = db.Column(db.Float)
    currency_code = db.Column(db.String(10))
    vat_base_amount = db.Column(db.Float)
    package_number = db.Column(db.String(100))
    stockCode = db.Column(db.Text)
    estimated_delivery_start = db.Column(db.DateTime)
    images = db.Column(db.Text)
    product_model_code = db.Column(db.Text)
    estimated_delivery_end = db.Column(db.DateTime)
    origin_shipment_date = db.Column(db.DateTime)
    product_size = db.Column(db.Text)
    product_main_id = db.Column(db.Text)
    cargo_provider_name = db.Column(db.String(100))
    agreed_delivery_date = db.Column(db.DateTime)
    product_color = db.Column(db.Text)
    cargo_tracking_link = db.Column(db.String(255))
    shipment_package_id = db.Column(db.String(100))
    details = db.Column(JSONB) # JSONB
    archive_date = db.Column(db.DateTime, default=datetime.utcnow)
    archive_reason = db.Column(db.String(255))
    def __repr__(self):
        return f"<Archive {self.order_number}>"

class YeniSiparis(db.Model):
    __tablename__ = 'yeni_siparisler' 
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    siparis_no = db.Column(db.String(100), unique=True, nullable=False, index=True) 
    musteri_adi = db.Column(db.String(150))
    musteri_soyadi = db.Column(db.String(150))
    musteri_adres = db.Column(db.Text)
    musteri_telefon = db.Column(db.String(20)) # Uzunluk eklendi
    siparis_tarihi = db.Column(db.DateTime, default=datetime.utcnow)
    toplam_tutar = db.Column(db.Float)
    durum = db.Column(db.String(50), default='Yeni', index=True) 
    notlar = db.Column(db.Text, nullable=True)
    urunler = db.relationship('SiparisUrun', backref='yeni_siparis', lazy=True, cascade="all, delete-orphan")

class SiparisUrun(db.Model):
    __tablename__ = 'siparis_urunler' 
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    siparis_id = db.Column(db.Integer, db.ForeignKey('yeni_siparisler.id', ondelete='CASCADE')) # onDelete eklendi
    urun_barkod = db.Column(db.String(100), db.ForeignKey('products.barcode', ondelete='SET NULL'), nullable=True) # FK
    urun_adi = db.Column(db.String(255))
    adet = db.Column(db.Integer)
    birim_fiyat = db.Column(db.Float)
    toplam_fiyat = db.Column(db.Float)
    renk = db.Column(db.String(50))
    beden = db.Column(db.String(50))
    urun_gorseli = db.Column(db.String(255), nullable=True)
    # Product ile ilişki (opsiyonel)
    # product_ref = db.relationship('Product', foreign_keys=[urun_barkod])


class Degisim(db.Model):
    __tablename__ = 'degisim'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True) # Otomatik artan id
    degisim_no = db.Column(db.String(100), unique=True, default=lambda: str(uuid.uuid4()), index=True) # UUID default
    siparis_no = db.Column(db.String(100), index=True) # Hangi siparişe istinaden?
    ad = db.Column(db.String(150))
    soyad = db.Column(db.String(150))
    adres = db.Column(db.Text)
    telefon_no = db.Column(db.String(20))
    urun_barkod = db.Column(db.String(100)) # Geri gönderilen ürünün barkodu
    urun_model_kodu = db.Column(db.String(100))
    urun_renk = db.Column(db.String(50))
    urun_beden = db.Column(db.String(50))
    degisim_tarihi = db.Column(db.DateTime, default=datetime.utcnow)
    degisim_durumu = db.Column(db.String(50), default='Beklemede', index=True) # (Beklemede, Onaylandı, Kargoda, Tamamlandı, İptal)
    kargo_kodu = db.Column(db.String(100), nullable=True) # Müşteriye verilen iade/değişim kargo kodu
    degisim_nedeni = db.Column(db.String(255), nullable=True)
    # İstenen yeni ürün bilgileri (opsiyonel, not olarak da tutulabilir)
    istenen_urun_barkod = db.Column(db.String(100), nullable=True)
    istenen_urun_model_kodu = db.Column(db.String(100), nullable=True)
    istenen_urun_renk = db.Column(db.String(50), nullable=True)
    istenen_urun_beden = db.Column(db.String(50), nullable=True)
    notlar = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<Degisim {self.degisim_no}>"


class Return(db.Model): # Bu model ReturnOrder/ReturnProduct ile çakışıyor. Birini seçmelisin.
    __tablename__ = 'returns' # Eğer ReturnOrder/ReturnProduct kullanılacaksa bu tabloya gerek yok.
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    claim_id = db.Column(db.String(50), unique=True, nullable=False, index=True) 
    order_number = db.Column(db.String(50), index=True)
    order_line_id = db.Column(db.String(50), index=True) 
    status = db.Column(db.String(50), index=True) 
    reason = db.Column(db.String(255)) 
    barcode = db.Column(db.String(100)) 
    product_name = db.Column(db.String(255))
    product_color = db.Column(db.String(50))
    product_size = db.Column(db.String(50))
    quantity = db.Column(db.Integer, default=1) 
    customer_name = db.Column(db.String(100)) 
    address = db.Column(db.Text) 
    create_date = db.Column(db.DateTime) 
    last_modified_date = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow) 
    notes = db.Column(db.Text, nullable=True) 
    details = db.Column(JSONB, nullable=True) # JSONB

    def __repr__(self):
        return f"<Return {self.claim_id}>"

class UserLog(db.Model):
    __tablename__ = 'user_logs'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True) # onDelete eklendi
    action = db.Column(db.String(255), nullable=False, index=True)
    details = db.Column(JSONB) # JSONB
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    ip_address = db.Column(db.String(45)) 
    page_url = db.Column(db.String(512)) # URL'ler uzun olabilir
    status_code = db.Column(db.Integer, nullable=True) 
    # Loglanan SQL sorgusunda 'browser', 'platform', 'session_id', 'session_duration', 'referrer' alanları vardı.
    # Bunlar `details` JSON'ı içinde saklanıyor. Eğer ayrı kolon isteniyorsa eklenmeli:
    browser = db.Column(db.String(255), nullable=True)
    platform = db.Column(db.String(255), nullable=True)
    session_id = db.Column(db.String(255), nullable=True, index=True)
    # session_duration = db.Column(db.Integer, nullable=True) # Saniye cinsinden tutulabilir
    referrer = db.Column(db.String(512), nullable=True)

    user = db.relationship('User', backref=db.backref('logs', lazy='dynamic')) 


class StockAnalysisRecord(db.Model):
    __tablename__ = 'stock_analysis_records'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True) # onDelete eklendi
    analysis_name = db.Column(db.String(100), nullable=False)
    analysis_parameters = db.Column(JSONB, nullable=True)  
    analysis_results = db.Column(JSONB, nullable=True)  
    user = db.relationship('User', backref=db.backref('stock_analyses', lazy='dynamic')) # lazy='dynamic'

    def __init__(self, user_id=None, analysis_name=None, analysis_parameters=None, analysis_results=None):
        self.user_id = user_id
        self.analysis_name = analysis_name
        self.analysis_parameters = analysis_parameters
        self.analysis_results = analysis_results

    def __repr__(self):
        return f"<StockAnalysisRecord {self.id}: {self.analysis_name}>"

# ProductQuestion modeli product_questions.py dosyasından buraya taşındı (veya oradan import edilmeli)
# Şimdilik buraya ekliyorum, db_setup.py'nin çalışması için.
# from product_questions import ProductQuestion # Eğer ayrı dosyada kalacaksa ve app context'i doğru yönetiliyorsa

class ProductQuestion(db.Model):
    __tablename__ = 'product_questions'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    question_id = db.Column(db.String(100), unique=True, index=True) 
    product_id = db.Column(db.String(100), index=True) 
    barcode = db.Column(db.String(100), db.ForeignKey('products.barcode', ondelete='SET NULL'), index=True, nullable=True) 
    product_name = db.Column(db.String(255)) 
    question_text = db.Column(db.Text) 
    asker_name = db.Column(db.String(150)) 
    question_date = db.Column(db.DateTime) 
    status = db.Column(db.String(50), index=True) 
    answer_text = db.Column(db.Text, nullable=True) 
    answer_date = db.Column(db.DateTime, nullable=True) 
    is_approved = db.Column(db.Boolean, default=False) 
    last_sync = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Product ile ilişki (opsiyonel)
    product_ref = db.relationship('Product', backref=db.backref('questions', lazy='dynamic'))


    def __repr__(self):
        return f"<ProductQuestion {self.question_id}: {self.question_text[:30]}...>"