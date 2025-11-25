#!/usr/bin/env python3
"""WooCommerce siparişlerindeki ürünleri kontrol et"""

from datetime import datetime
from zoneinfo import ZoneInfo
from app import app
from models import db, Product
from woocommerce_site.models import WooOrder
import json

IST = ZoneInfo("Europe/Istanbul")

with app.app_context():
    # Bugünün başlangıcı ve bitişi
    today = datetime.now(IST).date()
    start_ist = datetime.combine(today, datetime.min.time()).replace(tzinfo=IST)
    end_ist = datetime.combine(today, datetime.max.time()).replace(tzinfo=IST)
    
    # Bugünkü siparişler
    from sqlalchemy import or_, and_, func
    q = db.session.query(WooOrder).filter(
        or_(
            and_(func.timezone('Europe/Istanbul', WooOrder.date_created) >= start_ist,
                 func.timezone('Europe/Istanbul', WooOrder.date_created) <  end_ist),
            and_(WooOrder.date_created >= start_ist, WooOrder.date_created < end_ist)
        )
    )
    
    today_orders = q.all()
    print(f"Bugünkü WooCommerce siparişleri: {len(today_orders)}\n")
    
    for order in today_orders:
        print(f"📦 Order #{order.order_number}")
        print(f"   Status: {order.status}")
        print(f"   Total: {order.total}")
        
        if order.line_items:
            try:
                items = json.loads(order.line_items) if isinstance(order.line_items, str) else order.line_items
                print(f"   Line Items: {len(items)} adet ürün")
                
                for item in items:
                    product_id = item.get('product_id')
                    sku = item.get('sku', '')
                    name = item.get('name', 'Bilinmiyor')
                    quantity = item.get('quantity', 0)
                    subtotal = item.get('subtotal', 0)
                    
                    print(f"\n   🛍️  {name}")
                    print(f"      Product ID: {product_id}")
                    print(f"      SKU: {sku}")
                    print(f"      Quantity: {quantity}")
                    print(f"      Subtotal: {subtotal}")
                    
                    # Product tablosunda ara
                    product = None
                    if product_id:
                        product = db.session.query(Product).filter_by(woo_product_id=str(product_id)).first()
                        if product:
                            print(f"      ✅ Product bulundu (woo_product_id ile): {product.barcode}")
                        else:
                            print(f"      ❌ woo_product_id={product_id} ile Product bulunamadı")
                    
                    if not product and sku:
                        product = db.session.query(Product).filter_by(barcode=sku).first()
                        if product:
                            print(f"      ✅ Product bulundu (SKU/barcode ile): {product.barcode}")
                        else:
                            print(f"      ❌ SKU={sku} ile Product bulunamadı")
                    
                    if not product:
                        print(f"      ⚠️  BU ÜRÜN CANLI PANELDE GÖRÜNMEYECEK!")
                        
            except Exception as e:
                print(f"   ❌ Line items parse hatası: {e}")
        else:
            print(f"   ⚠️  Line items boş!")
        
        print("\n" + "="*60 + "\n")
