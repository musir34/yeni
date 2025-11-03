"""
CentralStock Tablosu - last_push_date Kolonu Eklendi

KOLON DETAYI:
- last_push_date: TIMESTAMPTZ (timezone-aware)
- Nullable: True (henüz gönderilmemiş ürünler için NULL)
- Amaç: Her barkodun en son ne zaman Trendyol'a gönderildiğini takip etmek

GÜNCELLEME MEKANIZMASI:
Her 10 dakikada çalışan push_central_stock_to_trendyol() fonksiyonu:
1. Tüm barkodları Trendyol'a gönderir
2. Başarılı gönderimden sonra her barkod için last_push_date'i günceller
3. Saat bilgisi Europe/Istanbul timezone'unda saklanır

KULLANIM ÖRNEKLERİ:

1. En son gönderilen ürünler:
SELECT barcode, qty, last_push_date 
FROM central_stock 
WHERE last_push_date IS NOT NULL
ORDER BY last_push_date DESC 
LIMIT 10;

2. Hiç gönderilmemiş ürünler:
SELECT barcode, qty 
FROM central_stock 
WHERE last_push_date IS NULL;

3. Son 1 saatte güncellenenler:
SELECT barcode, qty, last_push_date 
FROM central_stock 
WHERE last_push_date >= NOW() - INTERVAL '1 hour'
ORDER BY last_push_date DESC;

4. Python ile sorgu:
from app import app
from models import CentralStock
from datetime import datetime, timedelta

with app.app_context():
    # Son gönderilen 10 ürün
    recent = CentralStock.query.filter(
        CentralStock.last_push_date.isnot(None)
    ).order_by(
        CentralStock.last_push_date.desc()
    ).limit(10).all()
    
    for item in recent:
        print(f"{item.barcode}: {item.qty} adet, "
              f"son gönderim: {item.last_push_date}")

MIGRATION DETAYI:
ALTER TABLE central_stock 
ADD COLUMN IF NOT EXISTS last_push_date TIMESTAMPTZ;

STATUS: ✅ Uygulandı
"""
