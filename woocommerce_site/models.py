"""
WooCommerce Sipariş Modelleri
"""
from models import db
from datetime import datetime


class WooOrder(db.Model):
    """WooCommerce Siparişleri"""
    __tablename__ = 'woo_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, unique=True, nullable=False, index=True)  # WooCommerce order ID
    order_number = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), nullable=False, index=True)
    
    # Tarihler
    date_created = db.Column(db.DateTime, nullable=True)
    date_modified = db.Column(db.DateTime, nullable=True)
    last_synced = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Müşteri Bilgileri
    customer_first_name = db.Column(db.String(100))
    customer_last_name = db.Column(db.String(100))
    customer_email = db.Column(db.String(200))
    customer_phone = db.Column(db.String(50))
    
    # Fatura Adresi
    billing_address_1 = db.Column(db.String(255))
    billing_address_2 = db.Column(db.String(255))
    billing_city = db.Column(db.String(100))
    billing_state = db.Column(db.String(100))
    billing_postcode = db.Column(db.String(20))
    billing_country = db.Column(db.String(2))
    
    # Teslimat Adresi
    shipping_address_1 = db.Column(db.String(255))
    shipping_address_2 = db.Column(db.String(255))
    shipping_city = db.Column(db.String(100))
    shipping_state = db.Column(db.String(100))
    shipping_postcode = db.Column(db.String(20))
    shipping_country = db.Column(db.String(2))
    
    # Finansal Bilgiler
    total = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2))
    shipping_total = db.Column(db.Numeric(10, 2))
    tax_total = db.Column(db.Numeric(10, 2))
    discount_total = db.Column(db.Numeric(10, 2))
    currency = db.Column(db.String(3), default='TRY')
    
    # Ödeme Bilgileri
    payment_method = db.Column(db.String(100))
    payment_method_title = db.Column(db.String(200))
    transaction_id = db.Column(db.String(200))
    
    # Notlar
    customer_note = db.Column(db.Text)
    
    # Ürünler (JSON olarak saklanır)
    line_items = db.Column(db.JSON)
    
    # Ham veri (yedek)
    raw_data = db.Column(db.JSON)
    
    def __repr__(self):
        return f'<WooOrder {self.order_number} - {self.status}>'
    
    @classmethod
    def from_woo_data(cls, data):
        """WooCommerce API verisinden model instance oluştur"""
        try:
            # Tarih parse
            date_created = None
            if data.get('date_created'):
                try:
                    date_created = datetime.fromisoformat(data['date_created'].replace('Z', '+00:00'))
                except:
                    pass
            
            date_modified = None
            if data.get('date_modified'):
                try:
                    date_modified = datetime.fromisoformat(data['date_modified'].replace('Z', '+00:00'))
                except:
                    pass
            
            billing = data.get('billing', {})
            shipping = data.get('shipping', {})
            
            return cls(
                order_id=data.get('id'),
                order_number=str(data.get('number', data.get('id'))),
                status=data.get('status'),
                date_created=date_created,
                date_modified=date_modified,
                
                # Müşteri
                customer_first_name=billing.get('first_name'),
                customer_last_name=billing.get('last_name'),
                customer_email=billing.get('email'),
                customer_phone=billing.get('phone'),
                
                # Fatura
                billing_address_1=billing.get('address_1'),
                billing_address_2=billing.get('address_2'),
                billing_city=billing.get('city'),
                billing_state=billing.get('state'),
                billing_postcode=billing.get('postcode'),
                billing_country=billing.get('country'),
                
                # Teslimat
                shipping_address_1=shipping.get('address_1'),
                shipping_address_2=shipping.get('address_2'),
                shipping_city=shipping.get('city'),
                shipping_state=shipping.get('state'),
                shipping_postcode=shipping.get('postcode'),
                shipping_country=shipping.get('country'),
                
                # Finansal
                total=float(data.get('total', 0)),
                subtotal=float(data.get('total', 0)) - float(data.get('shipping_total', 0)),
                shipping_total=float(data.get('shipping_total', 0)),
                tax_total=float(data.get('total_tax', 0)),
                discount_total=float(data.get('discount_total', 0)),
                currency=data.get('currency', 'TRY'),
                
                # Ödeme
                payment_method=data.get('payment_method'),
                payment_method_title=data.get('payment_method_title'),
                transaction_id=data.get('transaction_id'),
                
                # Notlar
                customer_note=data.get('customer_note'),
                
                # Ürünler
                line_items=[
                    {
                        'name': item.get('name'),
                        'product_id': item.get('product_id'),
                        'variation_id': item.get('variation_id'),
                        'quantity': item.get('quantity'),
                        'subtotal': item.get('subtotal'),
                        'total': item.get('total'),
                        'sku': item.get('sku'),
                        'price': item.get('price'),
                    }
                    for item in data.get('line_items', [])
                ],
                
                # Ham veri
                raw_data=data
            )
        except Exception as e:
            print(f"WooOrder.from_woo_data hatası: {e}")
            return None
    
    def update_from_woo_data(self, data):
        """Mevcut kaydı güncelle - Tüm müşteri bilgileri dahil"""
        try:
            self.status = data.get('status', self.status)
            
            if data.get('date_modified'):
                try:
                    self.date_modified = datetime.fromisoformat(data['date_modified'].replace('Z', '+00:00'))
                except:
                    pass
            
            self.total = float(data.get('total', self.total))
            self.payment_method = data.get('payment_method', self.payment_method)
            self.payment_method_title = data.get('payment_method_title', self.payment_method_title)
            self.transaction_id = data.get('transaction_id', self.transaction_id)
            
            # 🔥 Müşteri bilgilerini güncelle (Hızlı sipariş için kritik!)
            billing = data.get('billing', {})
            shipping = data.get('shipping', {})
            
            # Müşteri bilgileri - billing'den al
            if billing.get('first_name'):
                self.customer_first_name = billing.get('first_name')
            if billing.get('last_name'):
                self.customer_last_name = billing.get('last_name')
            if billing.get('email'):
                self.customer_email = billing.get('email')
            if billing.get('phone'):
                self.customer_phone = billing.get('phone')
            
            # Fatura adresi
            if billing.get('address_1'):
                self.billing_address_1 = billing.get('address_1')
            if billing.get('address_2'):
                self.billing_address_2 = billing.get('address_2')
            if billing.get('city'):
                self.billing_city = billing.get('city')
            if billing.get('state'):
                self.billing_state = billing.get('state')
            if billing.get('postcode'):
                self.billing_postcode = billing.get('postcode')
            if billing.get('country'):
                self.billing_country = billing.get('country')
            
            # Teslimat adresi
            if shipping.get('address_1'):
                self.shipping_address_1 = shipping.get('address_1')
            if shipping.get('address_2'):
                self.shipping_address_2 = shipping.get('address_2')
            if shipping.get('city'):
                self.shipping_city = shipping.get('city')
            if shipping.get('state'):
                self.shipping_state = shipping.get('state')
            if shipping.get('postcode'):
                self.shipping_postcode = shipping.get('postcode')
            if shipping.get('country'):
                self.shipping_country = shipping.get('country')
            
            # Ürünleri güncelle
            if data.get('line_items'):
                self.line_items = [
                    {
                        'name': item.get('name'),
                        'product_id': item.get('product_id'),
                        'variation_id': item.get('variation_id'),
                        'quantity': item.get('quantity'),
                        'subtotal': item.get('subtotal'),
                        'total': item.get('total'),
                        'sku': item.get('sku'),
                        'price': item.get('price'),
                    }
                    for item in data.get('line_items', [])
                ]
            
            self.raw_data = data
            self.last_synced = datetime.utcnow()
            
        except Exception as e:
            print(f"WooOrder.update_from_woo_data hatası: {e}")
