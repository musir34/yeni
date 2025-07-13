#!/usr/bin/env python3
"""
Raf stok düşürme işlemini doğrudan test eden script
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import db, RafUrun, OrderCreated
from app import app
import json
from sqlalchemy import asc

def test_raf_stock_reduction():
    """Test raf stok düşürme"""
    with app.app_context():
        # 1. Test öncesi stok durumu
        print("=== Test Öncesi Stok Durumu ===")
        raf_5555 = RafUrun.query.filter_by(urun_barkodu='5555555555555').first()
        if raf_5555:
            print(f"5555555555555 - Raf: {raf_5555.raf_kodu}, Adet: {raf_5555.adet}")
            original_stock = raf_5555.adet
        else:
            print("5555555555555 barkodu için raf kaydı bulunamadı")
            return False
        
        # 2. Test siparişi bul
        order = OrderCreated.query.filter_by(order_number='TEST_RAF_001').first()
        if not order:
            print("TEST_RAF_001 siparişi bulunamadı")
            return False
        
        # 3. Sipariş detaylarını parse et
        details = json.loads(order.details)
        print(f"Sipariş detayları: {details}")
        
        # 4. Raf stok düşürme kodu (update_service.py'den aynı mantık)
        print("\n=== Raf Stok Düşürme Başlıyor ===")
        all_stock_sufficient = True
        insufficient_stock_items = []
        
        for detail in details:
            barkod = detail.get("barcode")
            adet = int(detail.get("quantity", 1))
            
            if not barkod or adet <= 0:
                continue
            
            # Raf kayıtlarını bul
            raf_kayitlari = RafUrun.query.filter(
                RafUrun.urun_barkodu == barkod,
                RafUrun.adet > 0
            ).order_by(asc(RafUrun.raf_kodu)).all()
            
            print(f"➡️ {adet} adet {barkod} raftan düşülecek")
            print(f"Müsait raflar: {[(r.raf_kodu, r.adet) for r in raf_kayitlari]}")
            
            kalan_adet = adet
            for raf in raf_kayitlari:
                if kalan_adet == 0:
                    break
                
                dusulecek = min(raf.adet, kalan_adet)
                raf.adet -= dusulecek
                kalan_adet -= dusulecek
                print(f"✅ {barkod} → {raf.raf_kodu} rafından {dusulecek} adet düşüldü (kalan: {raf.adet})")
            
            if kalan_adet > 0:
                all_stock_sufficient = False
                print(f"❌ YETERSİZ STOK: {barkod} için {kalan_adet} adet daha bulunamadı!")
                insufficient_stock_items.append(f"{barkod} ({kalan_adet} adet eksik)")
        
        # 5. Sonuç
        if not all_stock_sufficient:
            db.session.rollback()
            print(f"❌ STOK YETERSİZ: {', '.join(insufficient_stock_items)}")
            return False
        else:
            db.session.commit()
            print("✅ Tüm stoklar başarıyla düşürüldü")
            
            # Test sonrası stok durumu
            print("\n=== Test Sonrası Stok Durumu ===")
            raf_5555_after = RafUrun.query.filter_by(urun_barkodu='5555555555555').first()
            if raf_5555_after:
                print(f"5555555555555 - Raf: {raf_5555_after.raf_kodu}, Adet: {raf_5555_after.adet}")
                print(f"Fark: {original_stock - raf_5555_after.adet} adet düşürüldü")
            
            return True

if __name__ == "__main__":
    success = test_raf_stock_reduction()
    if success:
        print("\n🎉 TEST BAŞARILI - Raf stok düşürme işlemi çalışıyor!")
    else:
        print("\n❌ TEST BAŞARISIZ - Raf stok düşürme işlemi çalışmıyor!")