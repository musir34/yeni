from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
# create_engine gerekli değil, db instance'ı kullanılıyor
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float, Boolean, Text, Index # Index import edildi
# declarative_base gerekli değil, db.Model kullanılıyor
from datetime import datetime
import uuid
from sqlalchemy.dialects.postgresql import JSON

# sqlalchemy.dialects.postgresql.UUID zaten PG_UUID olarak import edildi, tekrar gerek yok

# db instance'ı başta tanımlanmalı
db = SQLAlchemy()
# Base = declarative_base() # db.Model kullanıldığı için buna gerek yok

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
class ReturnOrder(db.Model): # <--- db.Model olarak düzeltildi
    __tablename__ = 'return_orders'
    # UUID kullanımı için importlar ve db.Column kullanımı düzeltildi
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number = Column(String)
    return_request_number = Column(String)
    status = Column(String)
    return_date = Column(DateTime)
    process_date = Column(DateTime)  # İşlem tarihi
    customer_first_name = Column(String)
    customer_last_name = Column(String)
    cargo_tracking_number = Column(String)
    cargo_provider_name = Column(String)
    cargo_sender_number = Column(String)
    cargo_tracking_link = Column(String)
    processed_by = Column(String)  # İşlemi yapan kullanıcı
    return_reason = Column(String)  # İade nedeni (Beden/Numara Uyumsuzluğu, vs.)
    customer_explanation = Column(String)  # Müşteri açıklaması
    return_category = Column(String)  # İade kategorisi (Ürün Kaynaklı, Müşteri Kaynaklı, vs.)
    notes = Column(String)  # Ek notlar
    approval_reason = Column(String)  # Onay/red nedeni
    refund_amount = Column(Float)  # İade edilecek tutar

    # İlişki (ReturnProduct'a)
    products = db.relationship('ReturnProduct', backref='return_order', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<ReturnOrder {self.order_number}>'

# İade Edilen Ürünler - db.Model'dan türetilmeli
class ReturnProduct(db.Model): # <--- db.Model olarak düzeltildi, Base kaldırıldı
    __tablename__ = 'return_products'
    # UUID ve ForeignKey kullanımı düzeltildi
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    return_order_id = Column(PG_UUID(as_uuid=True), ForeignKey('return_orders.id'))
    product_id = Column(String)
    barcode = Column(String)
    model_number = Column(String)
    size = Column(String)
    color = Column(String)
    quantity = Column(Integer)
    reason = Column(String)
    claim_line_item_id = Column(String)
    product_condition = Column(String)  # Ürün durumu (Hasarlı, Kullanılmış, Yeni gibi)
    damage_description = Column(String)  # Hasar açıklaması
    inspection_notes = Column(String)  # İnceleme notları
    return_to_stock = Column(Boolean, default=False)  # Stoğa geri alınacak mı?


# Kullanıcı Modeli
class User(db.Model):
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


# Temel sipariş modeli - tüm statüler için ortak alanlar
class OrderBase(db.Model):
    __abstract__ = True # Bu tablo veritabanında oluşturulmaz, sadece kalıtım için kullanılır.

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String, index=True, nullable=False) # Sipariş no boş olmamalı
    order_date = db.Column(db.DateTime, index=True)
    merchant_sku = db.Column(db.String)
    # Sadece orijinal barkodları tutacak alan (virgülle ayrılmış liste)
    product_barcode = db.Column(db.Text) # Virgülle ayrılmış çok sayıda barkod olabileceği için Text daha uygun olabilir
    # original_product_barcode = db.Column(db.String) # --- BU ALAN KALDIRILDI ---
    line_id = db.Column(db.String) # Trendyol satır ID'leri (virgülle ayrılmış?) Text olabilir
    match_status = db.Column(db.String) # Anlamı net değil, kalabilir veya kaldırılabilir
    customer_name = db.Column(db.String)
    customer_surname = db.Column(db.String)
    customer_address = db.Column(db.Text)
    shipping_barcode = db.Column(db.String) # Kargo takip no?
    cargo_tracking_number = db.Column(db.String) # shipping_barcode ile aynı mı? Tekilleştirilebilir.
    product_name = db.Column(db.Text) # Uzun isimler için Text
    product_code = db.Column(db.Text) # Virgülle ayrılmış olabilir, Text
    amount = db.Column(db.Float) # Toplam tutar (KDV dahil?)
    discount = db.Column(db.Float, default=0.0)
    currency_code = db.Column(db.String(10))
    vat_base_amount = db.Column(db.Float)
    package_number = db.Column(db.String, index=True) # Trendyol paket ID
    stockCode = db.Column(db.Text) # merchant_sku ile aynı mı? Virgülle ayrılmış olabilir, Text
    estimated_delivery_start = db.Column(db.DateTime)
    images = db.Column(db.Text) # Virgülle ayrılmış URL listesi? Text
    product_model_code = db.Column(db.Text) # stockCode ile aynı mı? Text
    estimated_delivery_end = db.Column(db.DateTime, index=True) # Index eklendi
    origin_shipment_date = db.Column(db.DateTime)
    product_size = db.Column(db.Text) # Virgülle ayrılmış, Text
    product_main_id = db.Column(db.Text) # Virgülle ayrılmış, Text
    cargo_provider_name = db.Column(db.String)
    agreed_delivery_date = db.Column(db.DateTime)
    product_color = db.Column(db.Text) # Virgülle ayrılmış, Text
    cargo_tracking_link = db.Column(db.String)
    shipment_package_id = db.Column(db.String, index=True) # Trendyol kargo paket ID
    details = db.Column(db.Text) # Ürün detayları JSON string
    quantity = db.Column(db.Integer) # Toplam ürün adedi
    commission = db.Column(db.Float, default=0.0)
    product_cost_total = db.Column(db.Float, default=0.0) # Toplam maliyet (TRY?)
    # Status alanı artık tablo adından belli oluyor, bu alana gerek yok ama eski kod uyumu için kalmış.
    # İleride kaldırılabilir.
    status = db.Column(db.String)
    # Kayıt oluşturulma/güncellenme zamanları eklenebilir
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Yeni sipariş tablosu (Created)
class OrderCreated(OrderBase):
    __tablename__ = 'orders_created'
    # Bu statüye özel alanlar eklenebilir
    # creation_time = db.Column(db.DateTime, default=datetime.utcnow) # Zaten OrderBase'de created_at var

# İşleme alınan sipariş tablosu (Picking)
class OrderPicking(OrderBase):
    __tablename__ = 'orders_picking'
    # Bu statüye özel alanlar
    picking_start_time = db.Column(db.DateTime, default=datetime.utcnow) # İşleme alınma zamanı
    picked_by = db.Column(db.String) # İşleme alan kullanıcı

# Kargodaki sipariş tablosu (Shipped)
class OrderShipped(OrderBase):
    __tablename__ = 'orders_shipped'
    # Bu statüye özel alanlar
    shipping_time = db.Column(db.DateTime, default=datetime.utcnow) # Kargoya verilme zamanı
    tracking_updated = db.Column(db.Boolean, default=False) # Kargo durumu güncellendi mi?

# Teslim edilen sipariş tablosu (Delivered)
class OrderDelivered(OrderBase):
    __tablename__ = 'orders_delivered'
    # Bu statüye özel alanlar
    delivery_date = db.Column(db.DateTime) # Teslim edilme zamanı
    delivery_confirmed = db.Column(db.Boolean, default=False) # Teslimat onayı?

# İptal edilen sipariş tablosu (Cancelled)
class OrderCancelled(OrderBase):
    __tablename__ = 'orders_cancelled'
    # Bu statüye özel alanlar
    cancellation_date = db.Column(db.DateTime, default=datetime.utcnow) # İptal zamanı
    cancellation_reason = db.Column(db.String) # İptal nedeni

# Arşivlenen sipariş tablosu (Archived)
class OrderArchived(OrderBase):
    __tablename__ = 'orders_archived'
    # Bu statüye özel alanlar
    archive_date = db.Column(db.DateTime, default=datetime.utcnow) # Arşivlenme zamanı
    archive_reason = db.Column(db.String) # Arşivlenme nedeni


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


# Ürün Modeli - primary key düzeltildi, original_product_barcode kaldırıldı, __init__ güncellendi
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
    cost_usd = db.Column(db.Float, default=0.0)  # Maliyet (USD cinsinden)
    cost_date = db.Column(db.DateTime)  # Maliyet girişi tarihi
    cost_try = db.Column(db.Float, default=0) #tl karşılığı

    def __init__(self, barcode, title, product_main_id, 
                 quantity, images, variants, size, color, archived, locked, on_sale,
                 reject_reason, sale_price, list_price, currency_type, cost_usd=0.0, cost_try=0.0, cost_date=None):
        self.barcode = barcode
        self.title = title
        self.product_main_id = product_main_id
        self.quantity = quantity
        self.images = images
        self.variants = variants
        self.size = size
        self.color = color
        self.archived = archived
        self.locked = locked
        self.on_sale = on_sale
        self.reject_reason = reject_reason
        self.sale_price = sale_price
        self.list_price = list_price
        self.currency_type = currency_type
        self.cost_usd = cost_usd
        self.cost_date = cost_date
        self.cost_try = cost_try  # <- Doğrusu budur!



# Arşiv Modeli - Bu model de OrderBase gibi görünüyor, OrderArchived ile aynı mı?
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



# Değişim Modeli    
class Degisim(db.Model):
    __tablename__ = 'degisim'

    id = db.Column(db.Integer, primary_key=True)
    degisim_no = db.Column(db.String, primary_key=True)
    siparis_no = db.Column(db.String)
    ad = db.Column(db.String)
    soyad = db.Column(db.String)
    adres = db.Column(db.Text)
    telefon_no = db.Column(db.String)
    urun_barkod = db.Column(db.String)
    urun_model_kodu = db.Column(db.String)
    urun_renk = db.Column(db.String)
    urun_beden = db.Column(db.String)
    degisim_tarihi = db.Column(db.DateTime, default=datetime.utcnow)
    degisim_durumu = db.Column(db.String)
    kargo_kodu = db.Column(db.String)
    degisim_nedeni = db.Column(db.String, nullable=True)

    def __repr__(self):
        return f"<Exchange {self.degisim_no}>"


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