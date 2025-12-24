#!/usr/bin/env python
"""
Merkezi Stok Gönderim - Canlı Test
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Env değişkenlerini yükle
from dotenv import load_dotenv
load_dotenv()

# Minimal import - Amazon'u atla
os.environ['SKIP_AMAZON'] = '1'

from flask import Flask
from models import db, Product, CentralStock, OrderCreated
from central_stock_pusher import stock_pusher, push_stocks_sync
import asyncio

# Minimal Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

def analyze_platforms():
    """Platform analizini göster"""
    with app.app_context():
        print("=" * 70)
        print("🔍 PLATFORM STOK ANALİZİ")
        print("=" * 70)
        
        for platform in ['trendyol', 'idefix']:
            print(f"\n📦 {platform.upper()}")
            print("-" * 70)
            
            try:
                items = stock_pusher.get_platform_products(platform)
                
                if not items:
                    print("  ⚠️  Bu platformda ürün bulunamadı!")
                    continue
                
                positive_stock = [item for item in items if item['quantity'] > 0]
                zero_stock = [item for item in items if item['quantity'] == 0]
                total_qty = sum(item['quantity'] for item in items)
                
                print(f"  • Toplam ürün:       {len(items):6,}")
                print(f"  • Pozitif stoklu:    {len(positive_stock):6,}")
                print(f"  • Sıfır stoklu:      {len(zero_stock):6,}")
                print(f"  • Toplam miktar:     {total_qty:6,}")
                
                # İlk 5 pozitif stoklu ürün
                if positive_stock:
                    print(f"\n  📋 Örnek Ürünler (ilk 5):")
                    for i, item in enumerate(positive_stock[:5], 1):
                        print(f"     {i}. Barkod: {item['barcode'][:20]:20} → Stok: {item['quantity']:4}")
                
            except Exception as e:
                print(f"  ❌ HATA: {e}")
        
        print("\n" + "=" * 70)
        print("✅ Analiz tamamlandı!\n")

def test_push(platforms=None, dry_run=False):
    """Gerçek stok gönderimi"""
    with app.app_context():
        print("=" * 70)
        print("🚀 STOK GÖNDERİM TESTİ")
        print("=" * 70)
        
        if dry_run:
            print("⚠️  DRY RUN MODU - Gerçek gönderim yapılmayacak!\n")
            analyze_platforms()
            return
        
        print(f"📤 Hedef Platformlar: {', '.join(platforms) if platforms else 'Tümü (Hepsiburada hariç)'}")
        print(f"⏰ Başlangıç: {__import__('datetime').datetime.now().strftime('%H:%M:%S')}\n")
        
        # Onay al
        confirm = input("⚠️  Gerçek stok gönderimi yapılacak! Devam edilsin mi? (yes/no): ")
        if confirm.lower() != 'yes':
            print("❌ İşlem iptal edildi.")
            return
        
        print("\n🔄 Gönderim başlatılıyor...\n")
        
        # Gerçek gönderim
        result = push_stocks_sync(platforms)
        
        # Sonuçları göster
        print("\n" + "=" * 70)
        print("📊 SONUÇLAR")
        print("=" * 70)
        
        summary = result.get('summary', {})
        print(f"\n✨ Genel Özet:")
        print(f"  • Toplam platform:      {summary.get('total_platforms', 0)}")
        print(f"  • Başarılı platform:    {summary.get('successful_platforms', 0)}")
        print(f"  • Başarısız platform:   {summary.get('failed_platforms', 0)}")
        print(f"  • Toplam ürün:          {summary.get('total_items', 0):,}")
        print(f"  • Başarılı gönderim:    {summary.get('success_count', 0):,}")
        print(f"  • Hatalı gönderim:      {summary.get('error_count', 0):,}")
        print(f"  • Başarı oranı:         {summary.get('success_rate', 'N/A')}")
        print(f"  • Toplam süre:          {summary.get('duration', 'N/A')}")
        
        # Platform detayları
        platforms_data = result.get('platforms', {})
        if platforms_data:
            print(f"\n📦 Platform Detayları:")
            for platform, pdata in platforms_data.items():
                status = "✅" if pdata.get('success') else "❌"
                print(f"\n  {status} {platform.upper()}:")
                print(f"     Ürün: {pdata.get('total_items', 0):,} | "
                      f"Başarılı: {pdata.get('success_count', 0):,} | "
                      f"Hata: {pdata.get('error_count', 0):,} | "
                      f"Süre: {pdata.get('duration', 'N/A')}")
                
                # Hatalar varsa göster
                errors = pdata.get('errors', [])
                if errors:
                    print(f"     ⚠️  Hatalar ({len(errors)}):")
                    for error in errors[:3]:
                        print(f"        - {error[:60]}")
        
        print("\n" + "=" * 70)
        
        if result.get('success'):
            print("🎉 İşlem BAŞARILI!")
        else:
            print("⚠️  İşlem kısmen başarılı - Bazı hatalar oluştu")
        
        print("=" * 70 + "\n")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Merkezi Stok Gönderim - Canlı Test")
    parser.add_argument('--analyze', action='store_true', help='Sadece analiz yap (gönderim yok)')
    parser.add_argument('--platform', type=str, help='Belirli platform (trendyol, idefix)')
    parser.add_argument('--dry-run', action='store_true', help='Dry run - gerçek gönderim yok')
    
    args = parser.parse_args()
    
    if args.analyze or args.dry_run:
        analyze_platforms()
    else:
        platforms = [args.platform] if args.platform else None
        test_push(platforms, dry_run=args.dry_run)
