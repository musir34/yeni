# -*- coding: utf-8 -*-
"""
Büyük/Küçük Harf Farklılığından Kaynaklanan Çift Barkod Kayıtlarını Düzeltme
===========================================================================
Bu script:
1. CentralStock tablosundaki çift kayıtları birleştirir (küçük harfe normalize)
2. SyncDetail tablosundaki çift kayıtları düzeltir
3. RafUrun tablosundaki çift kayıtları birleştirir

Kullanım:
    python scripts/fix_duplicate_barcodes.py
"""

import sys
import os

# Ana dizini path'e ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ana uygulamayı import et
from app import app
from models import db, CentralStock, Product, RafUrun
from stock_sync.models import SyncDetail
from sqlalchemy import func


def fix_central_stock_duplicates():
    """CentralStock tablosundaki çift kayıtları düzelt"""
    print("\n📊 CentralStock tablosu analiz ediliyor...")
    
    # Tüm kayıtları al
    all_stocks = CentralStock.query.all()
    print(f"   Toplam kayıt: {len(all_stocks)}")
    
    # Barkodları grupla (küçük harfe göre)
    barcode_groups = {}
    for stock in all_stocks:
        key = stock.barcode.lower() if stock.barcode else ''
        if key not in barcode_groups:
            barcode_groups[key] = []
        barcode_groups[key].append(stock)
    
    # Çift kayıtları bul
    duplicates = {k: v for k, v in barcode_groups.items() if len(v) > 1}
    
    if not duplicates:
        print("   ✅ Çift kayıt bulunamadı!")
        return
    
    print(f"   ⚠️  {len(duplicates)} adet çift kayıt bulundu!")
    
    fixed_count = 0
    for barcode, stocks in duplicates.items():
        print(f"\n   🔧 Düzeltiliyor: '{barcode}'")
        
        # En yüksek stok değerini al
        max_qty = max(s.qty or 0 for s in stocks)
        print(f"      Kayıtlar: {[(s.barcode, s.qty) for s in stocks]}")
        print(f"      Seçilen stok: {max_qty}")
        
        # Küçük harfli olanı tut, diğerlerini sil
        kept = None
        for stock in stocks:
            if stock.barcode == barcode:  # Zaten küçük harfli
                kept = stock
                break
        
        if not kept:
            kept = stocks[0]
        
        # Stok değerini güncelle
        kept.barcode = barcode  # Küçük harfe normalize et
        kept.qty = max_qty
        
        # Diğerlerini sil
        for stock in stocks:
            if stock != kept:
                print(f"      ❌ Siliniyor: '{stock.barcode}'")
                db.session.delete(stock)
        
        fixed_count += 1
    
    db.session.commit()
    print(f"\n✅ {fixed_count} çift kayıt düzeltildi!")


def fix_sync_detail_duplicates():
    """SyncDetail tablosundaki çift kayıtları düzelt"""
    print("\n📊 SyncDetail tablosu analiz ediliyor...")
    
    # Son session'daki kayıtları al
    all_details = SyncDetail.query.order_by(SyncDetail.id.desc()).limit(10000).all()
    print(f"   Son 10000 kayıt kontrol ediliyor...")
    
    # Session bazında grupla
    session_groups = {}
    for detail in all_details:
        key = (detail.session_id, detail.barcode.lower() if detail.barcode else '')
        if key not in session_groups:
            session_groups[key] = []
        session_groups[key].append(detail)
    
    # Çift kayıtları bul
    duplicates = {k: v for k, v in session_groups.items() if len(v) > 1}
    
    if not duplicates:
        print("   ✅ Çift kayıt bulunamadı!")
        return
    
    print(f"   ⚠️  {len(duplicates)} adet çift kayıt bulundu!")
    
    fixed_count = 0
    for (session_id, barcode), details in duplicates.items():
        # İlkini tut, diğerlerini sil
        kept = details[0]
        for detail in details[1:]:
            db.session.delete(detail)
            fixed_count += 1
    
    db.session.commit()
    print(f"   ✅ {fixed_count} çift kayıt silindi!")


def fix_raf_urun_duplicates():
    """RafUrun tablosundaki çift kayıtları düzelt"""
    print("\n📊 RafUrun tablosu analiz ediliyor...")
    
    # Tüm raf ürünlerini al
    all_raf_urun = RafUrun.query.all()
    print(f"   Toplam kayıt: {len(all_raf_urun)}")
    
    # Raf kodu + barkod (küçük harf) bazında grupla
    groups = {}
    for ru in all_raf_urun:
        key = (ru.raf_kodu, ru.urun_barkodu.lower() if ru.urun_barkodu else '')
        if key not in groups:
            groups[key] = []
        groups[key].append(ru)
    
    # Çift kayıtları bul
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}
    
    if not duplicates:
        print("   ✅ Çift kayıt bulunamadı!")
        return
    
    print(f"   ⚠️  {len(duplicates)} adet çift kayıt bulundu!")
    
    fixed_count = 0
    for (raf_kodu, barcode), items in duplicates.items():
        print(f"\n   🔧 Düzeltiliyor: Raf={raf_kodu}, Barkod='{barcode}'")
        
        # Toplam adedi hesapla
        total_adet = sum(item.adet or 0 for item in items)
        print(f"      Kayıtlar: {[(item.urun_barkodu, item.adet) for item in items]}")
        print(f"      Toplam adet: {total_adet}")
        
        # İlkini tut, diğerlerini sil
        kept = items[0]
        kept.urun_barkodu = barcode  # Küçük harfe normalize et
        kept.adet = total_adet
        
        for item in items[1:]:
            print(f"      ❌ Siliniyor: '{item.urun_barkodu}'")
            db.session.delete(item)
        
        fixed_count += 1
    
    db.session.commit()
    print(f"\n✅ {fixed_count} çift kayıt düzeltildi!")


def main():
    print("=" * 60)
    print("🔧 BARKOD NORMALİZASYON SCRIPTİ")
    print("=" * 60)
    
    with app.app_context():
        fix_central_stock_duplicates()
        fix_raf_urun_duplicates()
        fix_sync_detail_duplicates()
    
    print("\n" + "=" * 60)
    print("✅ İŞLEM TAMAMLANDI!")
    print("=" * 60)


if __name__ == "__main__":
    main()
