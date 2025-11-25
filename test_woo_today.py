#!/usr/bin/env python3
"""WooCommerce siparişlerini bugün için test et"""

from datetime import datetime
from zoneinfo import ZoneInfo
from app import app
from models import db
from woocommerce_site.models import WooOrder

IST = ZoneInfo("Europe/Istanbul")

with app.app_context():
    # Bugünün başlangıcı ve bitişi
    today = datetime.now(IST).date()
    start_ist = datetime.combine(today, datetime.min.time()).replace(tzinfo=IST)
    end_ist = datetime.combine(today, datetime.max.time()).replace(tzinfo=IST)
    
    print(f"Tarih aralığı: {start_ist} - {end_ist}")
    
    # WooCommerce siparişlerini say
    total_woo = db.session.query(WooOrder).count()
    print(f"\nToplam WooCommerce siparişi: {total_woo}")
    
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
    print(f"Bugünkü WooCommerce siparişleri: {len(today_orders)}")
    
    if today_orders:
        print("\nBugünkü siparişler:")
        for o in today_orders[:5]:  # İlk 5'ini göster
            print(f"  - Order #{o.order_number}, Tarih: {o.date_created}, Status: {o.status}")
    
    # Son 7 günkü siparişler
    from datetime import timedelta
    week_ago = start_ist - timedelta(days=7)
    q_week = db.session.query(WooOrder).filter(
        or_(
            and_(func.timezone('Europe/Istanbul', WooOrder.date_created) >= week_ago,
                 func.timezone('Europe/Istanbul', WooOrder.date_created) <  end_ist),
            and_(WooOrder.date_created >= week_ago, WooOrder.date_created < end_ist)
        )
    )
    week_orders = q_week.all()
    print(f"\nSon 7 gündeki WooCommerce siparişleri: {len(week_orders)}")
