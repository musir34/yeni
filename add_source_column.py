#!/usr/bin/env python3
"""
OrderCreated ve diğer sipariş tablolarına 'source' kolonu ekler
KULLANIM: Sunucuyu kapatın, bu scripti çalıştırın, sonra tekrar başlatın
"""
import sys
import os

# Flask app'i import etmeden önce environment değişkenlerini yükle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# Veritabanı bağlantısı
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL bulunamadı!")
    sys.exit(1)

engine = create_engine(DATABASE_URL)

tables = [
    'orders_created',
    'orders_picking',
    'orders_shipped',
    'orders_delivered',
    'orders_cancelled',
    'orders_archived',
    'orders_ready_to_ship'
]

print("\n🔧 OrderCreated ve diğer tablolara 'source' kolonu ekleniyor...\n")

with engine.connect() as conn:
    for table in tables:
        try:
            # Kolon var mı kontrol et
            check_query = text(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='{table}' AND column_name='source'
            """)
            result = conn.execute(check_query).fetchone()
            
            if result:
                print(f"✅ {table} - 'source' kolonu zaten mevcut")
            else:
                # Kolon ekle
                add_query = text(f"""
                    ALTER TABLE {table} 
                    ADD COLUMN source VARCHAR(20) DEFAULT 'TRENDYOL' NOT NULL
                """)
                conn.execute(add_query)
                conn.commit()
                print(f"✅ {table} - 'source' kolonu eklendi")
                
        except Exception as e:
            print(f"❌ {table} - Hata: {e}")
            conn.rollback()

print("\n✅ Migration tamamlandı! Şimdi sunucuyu başlatabilirsiniz.\n")
