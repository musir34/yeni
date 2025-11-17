"""
Kapıda ödeme verilerini kontrol et
"""
from app import app, db
from models import YeniSiparis

with app.app_context():
    siparisler = YeniSiparis.query.order_by(YeniSiparis.siparis_tarihi.desc()).limit(5).all()
    
    print("\n" + "="*80)
    print("SON 5 SİPARİŞ - KAPIDA ÖDEME KONTROLÜ")
    print("="*80)
    
    for sip in siparisler:
        print(f"\nSipariş No: {sip.siparis_no}")
        print(f"Müşteri: {sip.musteri_adi} {sip.musteri_soyadi}")
        print(f"Kapıda Ödeme: {sip.kapida_odeme}")
        print(f"Kapıda Ödeme Tutarı: {sip.kapida_odeme_tutari}")
        print("-" * 80)
