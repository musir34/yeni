#!/usr/bin/env python3
"""
Test siparişlerini temizle
"""
from app import app
from models import db, OrderCreated

with app.app_context():
    # WOO-TEST ile başlayan veya "Test" içeren siparişleri bul
    test_orders = OrderCreated.query.filter(
        (OrderCreated.order_number.like('WOO-TEST%')) |
        (OrderCreated.customer_name == 'Test') |
        (OrderCreated.customer_surname == 'Test') |
        (OrderCreated.customer_name == 'Test 2')
    ).all()
    
    print(f"\n🔍 Bulunan test siparişleri: {len(test_orders)}")
    
    if test_orders:
        for order in test_orders:
            print(f"  🗑️  Siliniyor: #{order.order_number} - {order.customer_name} {order.customer_surname}")
            db.session.delete(order)
        
        db.session.commit()
        print(f"\n✅ {len(test_orders)} adet test siparişi silindi!\n")
    else:
        print("\n✅ Test siparişi bulunamadı.\n")
