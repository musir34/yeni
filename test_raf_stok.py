#!/usr/bin/env python3
"""
Raf stok düşürme işlemini test etmek için basit script
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import db, RafUrun, OrderCreated
from app import app
import json

def test_raf_stok():
    with app.app_context():
        # Test öncesi mevcut stok durumu
        print("=== Test Öncesi Raf Stok Durumu ===")
        raf_kayitlari = RafUrun.query.filter_by(urun_barkodu='2222222222222').all()
        for raf in raf_kayitlari:
            print(f"Raf: {raf.raf_kodu} - Barkod: {raf.urun_barkodu} - Adet: {raf.adet}")
        
        # Test siparişi bul
        order = OrderCreated.query.filter_by(order_number='TEST123456').first()
        if not order:
            print("Test siparişi bulunamadı!")
            return
        
        # Sipariş detaylarını parse et
        details = json.loads(order.details)
        print(f"\n=== Sipariş Detayları ===")
        print(f"Order: {order.order_number}")
        print(f"Details: {details}")
        
        # Raf stok düşürme simülasyonu
        print(f"\n=== Raf Stok Düşürme Simülasyonu ===")
        for detail in details:
            barkod = detail.get("barcode")
            adet = int(detail.get("quantity", 1))
            
            print(f"İşlenecek: {barkod} - {adet} adet")
            
            # Raf stokları bul
            raf_kayitlari = RafUrun.query.filter(
                RafUrun.urun_barkodu == barkod,
                RafUrun.adet > 0
            ).order_by(RafUrun.raf_kodu.asc()).all()
            
            print(f"Müsait raflar: {[(r.raf_kodu, r.adet) for r in raf_kayitlari]}")
            
            # Stok düşürme
            kalan_adet = adet
            for raf in raf_kayitlari:
                if kalan_adet == 0:
                    break
                    
                dusulecek = min(raf.adet, kalan_adet)
                raf.adet -= dusulecek
                kalan_adet -= dusulecek
                print(f"✅ {barkod} → {raf.raf_kodu} rafından {dusulecek} adet düşüldü (kalan: {raf.adet})")
            
            if kalan_adet > 0:
                print(f"❌ YETERSİZ STOK: {barkod} için {kalan_adet} adet daha bulunamadı!")
                return False
        
        # Değişiklikleri kaydet
        db.session.commit()
        print("\n=== Stok değişiklikleri kaydedildi ===")
        
        # Test sonrası durum
        print("\n=== Test Sonrası Raf Stok Durumu ===")
        raf_kayitlari = RafUrun.query.filter_by(urun_barkodu='2222222222222').all()
        for raf in raf_kayitlari:
            print(f"Raf: {raf.raf_kodu} - Barkod: {raf.urun_barkodu} - Adet: {raf.adet}")
        
        return True

if __name__ == "__main__":
    success = test_raf_stok()
    if success:
        print("\n✅ Test başarılı!")
    else:
        print("\n❌ Test başarısız!")