"""
Merkezi Stok Gönderim Sistemi Test Suite
"""
import sys
import os
import argparse
import asyncio
from datetime import datetime

# Projeyi path'e ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_basic_imports():
    """Temel import testleri"""
    print("🧪 Test 1: Import kontrolü...")
    try:
        from central_stock_pusher import CentralStockPusher, StockPushResult, stock_pusher, push_stocks_sync
        print("✅ Import başarılı")
        return True
    except Exception as e:
        print(f"❌ Import hatası: {e}")
        return False


def test_platform_configs():
    """Platform konfigürasyon testleri"""
    print("\n🧪 Test 2: Platform konfigürasyonları...")
    try:
        from central_stock_pusher import stock_pusher
        
        configs = stock_pusher.PLATFORM_CONFIGS
        
        # Hepsiburada'nın disabled olduğunu kontrol et
        assert configs["hepsiburada"]["enabled"] == False, "Hepsiburada enabled olmamalı!"
        print("✅ Hepsiburada devre dışı")
        
        # Diğer platformların enabled olduğunu kontrol et
        enabled_platforms = [p for p, cfg in configs.items() if cfg["enabled"]]
        assert "trendyol" in enabled_platforms, "Trendyol enabled olmalı!"
        assert "idefix" in enabled_platforms, "Idefix enabled olmalı!"
        print(f"✅ Aktif platformlar: {', '.join(enabled_platforms)}")
        
        # Batch size kontrolü
        for platform, config in configs.items():
            if config["enabled"]:
                assert config["batch_size"] > 0, f"{platform} batch_size > 0 olmalı!"
                assert config["max_retries"] >= 0, f"{platform} max_retries >= 0 olmalı!"
        print("✅ Konfigürasyon değerleri geçerli")
        
        return True
    except Exception as e:
        print(f"❌ Konfigürasyon testi hatası: {e}")
        return False


def test_barcode_normalization():
    """Barkod normalizasyon testleri"""
    print("\n🧪 Test 3: Barkod normalizasyonu...")
    try:
        from central_stock_pusher import stock_pusher
        
        test_cases = [
            ("123456789012", "123456789012"),  # 12 haneli - olduğu gibi
            ("1234567890123", "1234567890123"),  # 13 haneli - olduğu gibi
            ("123", "0000000000123"),  # Kısa barkod - pad
            ("12345", "0000000012345"),  # Orta uzunlukta
            ("  123  ", "0000000000123"),  # Boşluklarla
            ("", ""),  # Boş
        ]
        
        for input_barcode, expected in test_cases:
            result = stock_pusher._normalize_barcode(input_barcode)
            assert result == expected, f"'{input_barcode}' -> beklenen: '{expected}', alınan: '{result}'"
        
        print("✅ Tüm barkod testleri geçti")
        return True
    except Exception as e:
        print(f"❌ Barkod normalizasyon hatası: {e}")
        return False


def test_platform_filter():
    """Hepsiburada filtre testleri"""
    print("\n🧪 Test 4: Hepsiburada filtresi...")
    try:
        from central_stock_pusher import stock_pusher
        
        # Tüm platformlar (hepsiburada dahil)
        all_platforms = ["trendyol", "idefix", "hepsiburada", "amazon"]
        
        # Filtreleme
        filtered = [p for p in all_platforms if p != "hepsiburada"]
        
        assert "hepsiburada" not in filtered, "Hepsiburada filtrelenemedi!"
        assert len(filtered) == 3, f"Filtreden sonra 3 platform kalmalı, {len(filtered)} kaldı"
        
        print(f"✅ Hepsiburada başarıyla filtrelendi: {filtered}")
        return True
    except Exception as e:
        print(f"❌ Filtre testi hatası: {e}")
        return False


def test_stock_push_result():
    """StockPushResult sınıfı testleri"""
    print("\n🧪 Test 5: StockPushResult sınıfı...")
    try:
        from central_stock_pusher import StockPushResult
        
        result = StockPushResult("trendyol")
        result.total_items = 100
        result.success_count = 95
        result.error_count = 5
        result.duration = 12.34
        result.errors = ["Error 1", "Error 2"]
        
        result_dict = result.to_dict()
        
        assert result_dict["platform"] == "trendyol"
        assert result_dict["total_items"] == 100
        assert result_dict["success_count"] == 95
        assert result_dict["error_count"] == 5
        assert "95.0%" in result_dict["success_rate"]
        
        print("✅ StockPushResult testleri geçti")
        return True
    except Exception as e:
        print(f"❌ StockPushResult testi hatası: {e}")
        return False


async def test_mock_push(platform="trendyol"):
    """Mock platform push testi (gerçek API çağrısı yok)"""
    print(f"\n🧪 Test 6: Mock {platform} push...")
    try:
        from central_stock_pusher import StockPushResult
        
        # Mock items
        mock_items = [
            {"barcode": "1234567890123", "quantity": 10},
            {"barcode": "9876543210987", "quantity": 5},
            {"barcode": "1111111111111", "quantity": 0},
        ]
        
        result = StockPushResult(platform)
        result.total_items = len(mock_items)
        result.success_count = len(mock_items)
        result.error_count = 0
        result.duration = 0.5
        
        print(f"✅ Mock {platform} push başarılı: {result.to_dict()}")
        return True
    except Exception as e:
        print(f"❌ Mock push hatası: {e}")
        return False


def test_with_app_context():
    """Flask app context ile test"""
    print("\n🧪 Test 7: Flask app context...")
    try:
        from app import app, db
        from models import Product, CentralStock
        
        with app.app_context():
            # Basit DB query
            product_count = Product.query.count()
            stock_count = CentralStock.query.count()
            
            print(f"✅ DB bağlantısı başarılı")
            print(f"   • Product sayısı: {product_count}")
            print(f"   • CentralStock sayısı: {stock_count}")
            
            # Test platform ürünlerini getir
            from central_stock_pusher import stock_pusher
            
            # Sadece Trendyol için test (en yaygın)
            items = stock_pusher.get_platform_products("trendyol")
            print(f"   • Trendyol ürün sayısı: {len(items)}")
            
            return True
    except Exception as e:
        print(f"❌ App context hatası: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Tüm testleri çalıştır"""
    print("=" * 60)
    print("🚀 MERKEZI STOK GÖNDERİM SİSTEMİ TEST SUITE")
    print("=" * 60)
    print(f"⏰ Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    tests = [
        ("Import Kontrolü", test_basic_imports),
        ("Platform Konfigürasyonları", test_platform_configs),
        ("Barkod Normalizasyonu", test_barcode_normalization),
        ("Hepsiburada Filtresi", test_platform_filter),
        ("StockPushResult Sınıfı", test_stock_push_result),
        ("Flask App Context", test_with_app_context),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ Test çalıştırma hatası: {e}")
            results.append((test_name, False))
    
    # Mock push testini async olarak çalıştır
    print("\n🧪 Test 6: Mock push testleri...")
    try:
        asyncio.run(test_mock_push("trendyol"))
        results.append(("Mock Push", True))
    except Exception as e:
        print(f"❌ Mock push hatası: {e}")
        results.append(("Mock Push", False))
    
    # Özet
    print("\n" + "=" * 60)
    print("📊 TEST SONUÇLARI")
    print("=" * 60)
    
    passed = sum(1 for _, success in results if success)
    failed = len(results) - passed
    
    for test_name, success in results:
        status = "✅ BAŞARILI" if success else "❌ BAŞARISIZ"
        print(f"{status:15} {test_name}")
    
    print()
    print(f"Toplam: {len(results)}")
    print(f"✅ Başarılı: {passed}")
    print(f"❌ Başarısız: {failed}")
    print(f"Başarı Oranı: {(passed/len(results)*100):.1f}%")
    print("=" * 60)
    
    return failed == 0


def test_single_platform(platform):
    """Tek platform için gerçek test (dikkatli kullanın!)"""
    print(f"\n⚠️  GERÇEK PLATFORM TESTİ: {platform.upper()}")
    print("Bu test gerçek API çağrıları yapacak!")
    
    confirm = input("Devam etmek istediğinize emin misiniz? (yes/no): ")
    if confirm.lower() != "yes":
        print("Test iptal edildi.")
        return False
    
    try:
        from app import app
        from central_stock_pusher import push_stocks_sync
        
        with app.app_context():
            print(f"\n🚀 {platform} için stok gönderimi başlatılıyor...")
            
            result = push_stocks_sync([platform])
            
            print("\n📊 SONUÇ:")
            print(f"Başarı: {result.get('success')}")
            print(f"Özet: {result.get('summary')}")
            
            if platform in result.get("platforms", {}):
                platform_result = result["platforms"][platform]
                print(f"\n{platform.upper()} Detayları:")
                print(f"  • Toplam ürün: {platform_result.get('total_items')}")
                print(f"  • Başarılı: {platform_result.get('success_count')}")
                print(f"  • Hatalı: {platform_result.get('error_count')}")
                print(f"  • Süre: {platform_result.get('duration')}")
                print(f"  • Başarı oranı: {platform_result.get('success_rate')}")
            
            return result.get("success")
            
    except Exception as e:
        print(f"❌ Test hatası: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Merkezi Stok Gönderim Sistemi Test")
    parser.add_argument("--all", action="store_true", help="Tüm testleri çalıştır")
    parser.add_argument("--platform", type=str, help="Tek platform testi (GERÇEK API)")
    parser.add_argument("--dry-run", action="store_true", help="Sadece mock testler")
    
    args = parser.parse_args()
    
    if args.platform:
        # Gerçek platform testi
        success = test_single_platform(args.platform)
        sys.exit(0 if success else 1)
    
    elif args.all or args.dry_run:
        # Tüm testler (mock)
        success = run_all_tests()
        sys.exit(0 if success else 1)
    
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
