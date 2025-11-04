#!/usr/bin/env python3
"""
Stok Birleştirme Test ve Kontrol Aracı
══════════════════════════════════════

Alias ekleme öncesi ve sonrası stok durumunu gösterir.
"""

import sys
from app import app
from models import db, CentralStock, RafUrun, BarcodeAlias, Product
from barcode_alias_helper import add_alias


def show_stock_status(alias_barcode, main_barcode):
    """İki barkodun stok durumunu göster"""
    print("\n" + "="*70)
    print(f"📊 STOK DURUMU")
    print("="*70)
    
    # CentralStock kontrolü
    alias_stock = CentralStock.query.get(alias_barcode)
    main_stock = CentralStock.query.get(main_barcode)
    
    print(f"\n🏢 Merkez Stok (CentralStock):")
    print(f"  📦 Alias ({alias_barcode}): ", end="")
    if alias_stock:
        print(f"{alias_stock.qty} adet ✓")
    else:
        print("YOK ✗")
    
    print(f"  📦 Ana ({main_barcode}): ", end="")
    if main_stock:
        print(f"{main_stock.qty} adet ✓")
    else:
        print("YOK ✗")
    
    # Raf stokları
    alias_raf_items = RafUrun.query.filter_by(urun_barkodu=alias_barcode).all()
    main_raf_items = RafUrun.query.filter_by(urun_barkodu=main_barcode).all()
    
    print(f"\n📦 Raf Stokları:")
    print(f"  Alias ({alias_barcode}):")
    if alias_raf_items:
        total = 0
        for r in alias_raf_items:
            print(f"    └─ Raf {r.raf_kodu}: {r.adet} adet")
            total += r.adet
        print(f"    📊 Toplam: {total} adet")
    else:
        print(f"    └─ Rafta yok ✗")
    
    print(f"  Ana ({main_barcode}):")
    if main_raf_items:
        total = 0
        for r in main_raf_items:
            print(f"    └─ Raf {r.raf_kodu}: {r.adet} adet")
            total += r.adet
        print(f"    📊 Toplam: {total} adet")
    else:
        print(f"    └─ Rafta yok ✗")
    
    # Toplam
    alias_total = (alias_stock.qty if alias_stock else 0) + sum(r.adet for r in alias_raf_items)
    main_total = (main_stock.qty if main_stock else 0) + sum(r.adet for r in main_raf_items)
    
    # Merkez stok = gerçek toplam (raflar sadece dağılım)
    alias_merkez = alias_stock.qty if alias_stock else 0
    main_merkez = main_stock.qty if main_stock else 0
    
    print("\n📈 Genel Toplam:")
    print(f"  🏢 Merkez Stok:")
    print(f"     Alias (008932232669): {alias_merkez} adet")
    print(f"     Ana (Güllüayakkabı048): {main_merkez} adet")
    print(f"  🔢 Gerçek Toplam Stok: {alias_merkez + main_merkez} adet")
    print(f"  ℹ️  Not: Raf stokları merkez stokun raflara dağılımıdır, ayrı sayılmaz")
    print("=" * 70)


def test_merge(alias_barcode, main_barcode=None, do_merge=False):
    """Stok birleştirmeyi test et"""
    from barcode_alias_helper import merge_existing_alias_stocks, add_alias
    from models import BarcodeAlias
    
    # Alias var mı kontrol et
    alias = BarcodeAlias.query.get(alias_barcode)
    
    if alias:
        # Mevcut alias için stok birleştirme
        print(f"\n🔍 {'='*70}")
        print(f"MEVCUT ALİAS İÇİN STOK BİRLEŞTİRME: {alias_barcode} → {alias.main_barcode}")
        print("="*70)
        
        print("\n📸 ÖNCESİ:\n")
        show_stock_status(alias_barcode, alias.main_barcode)
        
        if do_merge:
            print("\n⚙️  Stoklar birleştiriliyor...")
            result = merge_existing_alias_stocks(alias_barcode)
            
            if result['success']:
                print(f"\n✅ {result['message']}")
                print(f"\n📸 SONRASI:\n")
                show_stock_status(alias_barcode, alias.main_barcode)
            else:
                print(f"\n❌ {result['message']}")
        else:
            print("\n⚠️  Bu bir simülasyon. Gerçek birleştirme yapmak için:")
            print(f"   python merge_stocks.py {alias_barcode} --merge")
    
    elif main_barcode:
        # Yeni alias ekleyerek birleştir
        print(f"\n🔍 {'='*70}")
        print(f"STOK BİRLEŞTİRME TESTİ: {alias_barcode} → {main_barcode}")
        print("="*70)
        
        print("\n📸 ÖNCESİ:\n")
        show_stock_status(alias_barcode, main_barcode)
        
        if do_merge:
            print("\n⚙️  Stoklar birleştiriliyor...")
            result = add_alias(alias_barcode, main_barcode, created_by='test', merge_stocks=True)
            
            if result['success']:
                print(f"\n✅ {result['message']}")
                print(f"\n📸 SONRASI:\n")
                show_stock_status(alias_barcode, main_barcode)
            else:
                print(f"\n❌ {result['message']}")
        else:
            print("\n⚠️  Bu bir simülasyon. Gerçek birleştirme yapmak için:")
            print(f"   python merge_stocks.py {alias_barcode} {main_barcode} --merge")
    
    else:
        print(f"\n❌ Alias bulunamadı ve ana barkod belirtilmedi!")
        print(f"   Kullanım: python merge_stocks.py {alias_barcode} [ANA_BARKOD] [--merge]")


def check_existing_alias(alias_barcode):
    """Var olan bir alias'ın stok durumunu göster"""
    alias = BarcodeAlias.query.get(alias_barcode)
    if not alias:
        print(f"\n❌ '{alias_barcode}' için alias kaydı bulunamadı!")
        return
    
    print(f"\n✅ Alias Bulundu: {alias_barcode} → {alias.main_barcode}")
    if alias.note:
        print(f"   Not: {alias.note}")
    if alias.created_by:
        print(f"   Ekleyen: {alias.created_by}")
    
    show_stock_status(alias_barcode, alias.main_barcode)


if __name__ == "__main__":
    with app.app_context():
        print("\n📦 Stok Birleştirme Test Aracı\n")
        
        if len(sys.argv) < 2:
            print("Kullanım:")
            print("  # Mevcut alias'ı kontrol et")
            print("  python merge_stocks.py 008932232669")
            print()
            print("  # Simülasyon (birleştirme yapmadan önce göster)")
            print("  python merge_stocks.py ALIAS_BARKOD ANA_BARKOD")
            print()
            print("  # Gerçek birleştirme")
            print("  python merge_stocks.py ALIAS_BARKOD ANA_BARKOD --merge")
            print()
            
            # Mevcut alias'ları göster
            aliases = BarcodeAlias.query.all()
            if aliases:
                print("Mevcut Alias'lar:")
                for a in aliases:
                    print(f"  • {a.alias_barcode} → {a.main_barcode}")
            
            sys.exit(0)
        
        if len(sys.argv) == 2:
            # Tek barkod verildi - mevcut alias'ı kontrol et veya birleştir
            alias_barcode = sys.argv[1]
            check_existing_alias(alias_barcode)
        
        elif len(sys.argv) >= 3:
            # İki veya daha fazla parametre
            alias_barcode = sys.argv[1]
            
            # --merge parametresi kontrolü
            do_merge = '--merge' in sys.argv or '-m' in sys.argv
            
            # İkinci parametre --merge mi yoksa ana barkod mu?
            if sys.argv[2] in ['--merge', '-m']:
                # Mevcut alias için birleştirme
                test_merge(alias_barcode, do_merge=do_merge)
            else:
                # Yeni alias ekleyerek birleştirme
                main_barcode = sys.argv[2]
                test_merge(alias_barcode, main_barcode, do_merge=do_merge)
