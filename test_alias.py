#!/usr/bin/env python3
"""
Barkod Alias Test Aracı
═══════════════════════

Hızlıca bir barkodun alias olup olmadığını ve hangi ana barkoda bağlı olduğunu kontrol eder.

Kullanım:
    python test_alias.py ABC123
    python test_alias.py XYZ789
"""

import sys
from app import app
from barcode_alias_helper import normalize_barcode, get_alias_info, get_all_aliases
from models import BarcodeAlias


def test_barcode(barcode):
    """Bir barkodu test et ve detaylı bilgi göster"""
    
    with app.app_context():
        print("\n" + "="*60)
        print(f"🔍 BARKOD TEST: {barcode}")
        print("="*60)
        
        # 1. Normalize edilmiş hali
        normalized = normalize_barcode(barcode)
        print(f"\n✅ Normalize Edilmiş Barkod: {normalized}")
        
        if normalized != barcode:
            print(f"   → Bu bir ALIAS! Ana barkod: {normalized}")
        else:
            print(f"   → Bu bir ANA BARKOD (veya tanımsız alias)")
        
        # 2. Detaylı bilgi
        info = get_alias_info(barcode)
        print(f"\n📊 Detaylı Bilgi:")
        print(f"   - Alias mi?: {'EVET ✓' if info['is_alias'] else 'HAYIR ✗'}")
        print(f"   - Ana Barkod: {info['main_barcode']}")
        
        if info['aliases']:
            print(f"   - Bu ana barkoda bağlı {len(info['aliases'])} alias var:")
            for alias in info['aliases']:
                print(f"      • {alias}")
        
        if info['note']:
            print(f"   - Not: {info['note']}")
        
        # 3. Veritabanından direkt kontrol
        print(f"\n🗄️  Veritabanı Kontrolü:")
        alias_record = BarcodeAlias.query.get(barcode)
        if alias_record:
            print(f"   ✓ Alias kaydı bulundu!")
            print(f"   - Alias: {alias_record.alias_barcode}")
            print(f"   - Ana Barkod: {alias_record.main_barcode}")
            if alias_record.created_by:
                print(f"   - Ekleyen: {alias_record.created_by}")
            if alias_record.note:
                print(f"   - Not: {alias_record.note}")
            print(f"   - Oluşturulma: {alias_record.created_at}")
        else:
            print(f"   ✗ Bu barkod için alias kaydı yok")
            
            # Belki bu bir ana barkod, onun alias'larına bakalım
            related = BarcodeAlias.query.filter_by(main_barcode=barcode).all()
            if related:
                print(f"\n   ℹ️  Ancak bu barkoda bağlı {len(related)} alias bulundu:")
                for r in related:
                    print(f"      • {r.alias_barcode} → {r.main_barcode}")
        
        # 4. Tüm alias'ları göster (opsiyonel)
        all_aliases = BarcodeAlias.query.all()
        if all_aliases:
            print(f"\n📋 Sistemdeki Tüm Alias'lar ({len(all_aliases)} adet):")
            for a in all_aliases[:10]:  # İlk 10 tanesini göster
                print(f"   {a.alias_barcode} → {a.main_barcode}")
            if len(all_aliases) > 10:
                print(f"   ... ve {len(all_aliases) - 10} tane daha")
        
        print("\n" + "="*60)
        print("✨ Test Tamamlandı!")
        print("="*60 + "\n")


def list_all_aliases():
    """Tüm alias'ları listele"""
    with app.app_context():
        aliases = BarcodeAlias.query.order_by(BarcodeAlias.main_barcode).all()
        
        if not aliases:
            print("\n❌ Sistemde hiç alias yok!")
            print("   Yeni alias eklemek için: /barcode-alias/ sayfasına git\n")
            return
        
        print("\n" + "="*60)
        print(f"📋 SİSTEMDEKİ TÜM ALIAS'LAR ({len(aliases)} adet)")
        print("="*60 + "\n")
        
        # Ana barkoda göre grupla
        grouped = {}
        for alias in aliases:
            if alias.main_barcode not in grouped:
                grouped[alias.main_barcode] = []
            grouped[alias.main_barcode].append(alias)
        
        for main_barcode, alias_list in grouped.items():
            print(f"🔖 Ana Barkod: {main_barcode}")
            for alias in alias_list:
                note = f" ({alias.note})" if alias.note else ""
                creator = f" - {alias.created_by}" if alias.created_by else ""
                print(f"   ├─ {alias.alias_barcode}{note}{creator}")
            print()
        
        print("="*60 + "\n")


if __name__ == "__main__":
    print("\n🔖 Barkod Alias Test Aracı\n")
    
    if len(sys.argv) < 2:
        print("Kullanım:")
        print("  python test_alias.py ABC123          # Belirli bir barkodu test et")
        print("  python test_alias.py --list          # Tüm alias'ları listele")
        print("  python test_alias.py --all           # Tüm alias'ları listele")
        print()
        
        # Varsayılan: Tüm alias'ları göster
        list_all_aliases()
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command in ['--list', '--all', '-l', '-a']:
        list_all_aliases()
    else:
        # Barkod testi
        test_barcode(command)
