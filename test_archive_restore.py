#!/usr/bin/env python3
"""Archive geri yükleme testleri"""

from app import app, db
from models import Archive, OrderCreated
from woocommerce_site.models import WooOrder

with app.app_context():
    print("=" * 60)
    print("ARCHIVE GERİ YÜKLEME TESTİ")
    print("=" * 60)
    
    # 1. Archive'deki siparişleri listele
    archives = db.session.query(Archive).limit(10).all()
    print(f"\nArchive'de {db.session.query(Archive).count()} sipariş var")
    print("\nİlk 10 sipariş:")
    for a in archives:
        source = getattr(a, 'source', 'UNKNOWN')
        print(f"  {a.order_number} - source: {source}")
    
    # 2. WooCommerce siparişlerini say
    woo_count = db.session.query(Archive).filter_by(source='woocommerce').count()
    trendyol_count = db.session.query(Archive).filter_by(source='trendyol').count()
    null_count = db.session.query(Archive).filter(Archive.source.is_(None)).count()
    
    print(f"\nKaynağa göre dağılım:")
    print(f"  WooCommerce: {woo_count}")
    print(f"  Trendyol: {trendyol_count}")
    print(f"  NULL (eski): {null_count}")
    
    # 3. Eski kayıtları güncelle (source=NULL olanlar)
    if null_count > 0:
        print(f"\n⚠️  {null_count} adet source=NULL olan kayıt var")
        print("Bu kayıtlar için fallback mantığı kullanılacak")
        
        for archive in db.session.query(Archive).filter(Archive.source.is_(None)).limit(5).all():
            order_num = str(archive.order_number)
            is_woo = len(order_num) <= 6 and order_num.isdigit() and '-' not in order_num
            detected_source = 'woocommerce' if is_woo else 'trendyol'
            print(f"  {order_num} -> {detected_source}")
    
    # 4. Test: Bir WooCommerce siparişini geri yükle (DRY RUN)
    woo_archive = db.session.query(Archive).filter_by(source='woocommerce').first()
    if woo_archive:
        print(f"\n✅ Test WooCommerce siparişi bulundu: {woo_archive.order_number}")
        print(f"   Bu sipariş geri yüklenirse woo_orders tablosuna 'on-hold' statüsünde eklenecek")
    else:
        print("\n❌ Archive'de WooCommerce siparişi yok")
    
    # 5. Test: Bir Trendyol siparişini geri yükle (DRY RUN)
    trendyol_archive = db.session.query(Archive).filter_by(source='trendyol').first()
    if trendyol_archive:
        print(f"\n✅ Test Trendyol siparişi bulundu: {trendyol_archive.order_number}")
        print(f"   Bu sipariş geri yüklenirse orders_created tablosuna 'Created' statüsünde eklenecek")
    else:
        print("\n❌ Archive'de Trendyol siparişi yok")
    
    print("\n" + "=" * 60)
    print("NOT: Gerçek geri yükleme için web arayüzünü kullanın")
    print("=" * 60)
