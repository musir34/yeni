# -*- coding: utf-8 -*-
"""
Trendyol'dan Orijinal Barkodları Çekip Veritabanını Güncelleme
===============================================================
Bu script Trendyol API'den tüm ürünleri çeker ve veritabanındaki
barkodları orijinal haliyle günceller.

Kullanım:
    python scripts/sync_original_barcodes.py
"""

import sys
import os
import asyncio
import aiohttp
import base64

# Ana dizini path'e ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from trendyol_v2 import flatten_v2_page, V2_MAX_PAGE_SIZE

# Trendyol API bilgileri
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SUPPLIER_ID = os.getenv("SUPPLIER_ID")
BASE_URL = "https://apigw.trendyol.com/integration/"


async def fetch_all_trendyol_barcodes():
    """Trendyol'dan tüm ürün barkodlarını çeker (orijinal haliyle)"""
    all_products = []
    page_size = V2_MAX_PAGE_SIZE  # V2'de sayfa boyutu en fazla 100
    url = f"{BASE_URL}product/sellers/{SUPPLIER_ID}/products/approved"
    credentials = f"{API_KEY}:{API_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    headers = {"Authorization": f"Basic {encoded_credentials}"}

    base_params = {
        "size": page_size
    }

    async with aiohttp.ClientSession() as session:
        timeout = aiohttp.ClientTimeout(total=60)
        
        # İlk sayfa
        params = {"page": 0, **base_params}
        async with session.get(url, headers=headers, params=params, timeout=timeout) as response:
            response.raise_for_status()
            data = await response.json()
            total_pages = data.get('totalPages', 1)
            total_elements = data.get('totalElements', 0)
            print(f"📦 Toplam ürün: {total_elements}, Sayfa: {total_pages}")
            
            if 'content' in data and isinstance(data['content'], list):
                all_products.extend(flatten_v2_page(data))

            # Diğer sayfaları çek
            for page_num in range(1, total_pages):
                print(f"   Sayfa {page_num + 1}/{total_pages} çekiliyor...")
                params = {"page": page_num, **base_params}
                async with session.get(url, headers=headers, params=params, timeout=timeout) as resp:
                    if resp.status == 200:
                        page_data = await resp.json()
                        if 'content' in page_data:
                            all_products.extend(flatten_v2_page(page_data))

    # v1'deki archived=false filtresinin V2 karşılığı
    return [p for p in all_products if not p.get('archived')]


def update_database_barcodes(trendyol_products):
    """Veritabanındaki barkodları Trendyol'dan gelen orijinal hallerine güncelle"""
    from app import app
    from models import db, Product, CentralStock, RafUrun
    
    with app.app_context():
        # Trendyol'dan gelen barkodları map'e al (küçük harf -> orijinal)
        barcode_map = {}
        for p in trendyol_products:
            original_barcode = p.get('barcode', '').strip()
            if original_barcode:
                barcode_map[original_barcode.lower()] = original_barcode
        
        print(f"\n📊 Trendyol'dan {len(barcode_map)} benzersiz barkod alındı")
        
        # Örnek barkodları göster
        print("\n🔍 Örnek orijinal barkodlar (ilk 20):")
        for i, (lower, original) in enumerate(list(barcode_map.items())[:20]):
            if lower != original:
                print(f"   {lower} → {original} (farklı)")
            else:
                print(f"   {original}")
        
        # 1. Product tablosunu güncelle
        print("\n📝 Product tablosu güncelleniyor...")
        products = Product.query.all()
        product_updated = 0
        for p in products:
            if p.barcode:
                original = barcode_map.get(p.barcode.lower())
                if original and p.barcode != original:
                    print(f"   Product: {p.barcode} → {original}")
                    p.barcode = original
                    product_updated += 1
        db.session.commit()
        print(f"   ✅ {product_updated} ürün güncellendi")
        
        # 2. CentralStock tablosunu güncelle
        print("\n📝 CentralStock tablosu güncelleniyor...")
        stocks = CentralStock.query.all()
        stock_updated = 0
        for s in stocks:
            if s.barcode:
                original = barcode_map.get(s.barcode.lower())
                if original and s.barcode != original:
                    print(f"   CentralStock: {s.barcode} → {original}")
                    # Primary key değişikliği için yeni kayıt oluştur ve eskiyi sil
                    new_stock = CentralStock(barcode=original, qty=s.qty)
                    db.session.delete(s)
                    db.session.add(new_stock)
                    stock_updated += 1
        db.session.commit()
        print(f"   ✅ {stock_updated} stok kaydı güncellendi")
        
        # 3. RafUrun tablosunu güncelle
        print("\n📝 RafUrun tablosu güncelleniyor...")
        raf_urunler = RafUrun.query.all()
        raf_updated = 0
        for r in raf_urunler:
            if r.urun_barkodu:
                original = barcode_map.get(r.urun_barkodu.lower())
                if original and r.urun_barkodu != original:
                    r.urun_barkodu = original
                    raf_updated += 1
        db.session.commit()
        print(f"   ✅ {raf_updated} raf ürünü güncellendi")
        
        print("\n" + "=" * 60)
        print("✅ TÜM BARKODLAR ORİJİNAL HALİNE GÜNCELLENDİ!")
        print("=" * 60)


async def main():
    print("=" * 60)
    print("🔄 TRENDYOL ORİJİNAL BARKOD SENKRONIZASYONU")
    print("=" * 60)
    
    print("\n📥 Trendyol'dan ürünler çekiliyor...")
    products = await fetch_all_trendyol_barcodes()
    
    if not products:
        print("❌ Ürün çekilemedi!")
        return
    
    print(f"✅ {len(products)} ürün çekildi")
    
    update_database_barcodes(products)


if __name__ == "__main__":
    asyncio.run(main())
