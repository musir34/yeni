"""
Idefix Platform Entegrasyonu - Migration Script
Product tablosuna platforms ve idefix alanları ekleme
"""

import os
import sys

# Proje kök dizinini path'e ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import db

def migrate():
    """Product tablosuna yeni sütunları ekle"""
    with app.app_context():
        # Bağlantıyı kontrol et
        try:
            db.session.execute(db.text("SELECT 1"))
            print("✓ Veritabanı bağlantısı başarılı")
        except Exception as e:
            print(f"✗ Veritabanı bağlantı hatası: {e}")
            return False
        
        # Sütunları ekle
        columns_to_add = [
            ("platforms", "TEXT DEFAULT '[\"trendyol\"]'"),
            ("idefix_product_id", "VARCHAR(255)"),
            ("idefix_status", "VARCHAR(50)"),
            ("idefix_last_sync", "TIMESTAMP"),
        ]
        
        for column_name, column_type in columns_to_add:
            try:
                # Sütun var mı kontrol et
                check_sql = f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'products' AND column_name = '{column_name}'
                """
                result = db.session.execute(db.text(check_sql)).fetchone()
                
                if result:
                    print(f"⚠ '{column_name}' sütunu zaten mevcut, atlanıyor...")
                else:
                    # Sütunu ekle
                    alter_sql = f"ALTER TABLE products ADD COLUMN {column_name} {column_type}"
                    db.session.execute(db.text(alter_sql))
                    db.session.commit()
                    print(f"✓ '{column_name}' sütunu eklendi")
                    
            except Exception as e:
                db.session.rollback()
                print(f"✗ '{column_name}' eklenirken hata: {e}")
        
        # Mevcut Trendyol ürünlerinin platforms alanını güncelle
        try:
            update_sql = """
                UPDATE products 
                SET platforms = '["trendyol"]' 
                WHERE platforms IS NULL
            """
            result = db.session.execute(db.text(update_sql))
            db.session.commit()
            print(f"✓ {result.rowcount} ürünün platforms alanı güncellendi")
        except Exception as e:
            db.session.rollback()
            print(f"✗ platforms güncelleme hatası: {e}")
        
        print("\n✓ Migration tamamlandı!")
        return True


if __name__ == "__main__":
    migrate()
