"""
RAF KODU MIGRATION SCRIPT
Bu script siparis_urunler tablosuna raf_kodu sütununu ekler.
Kullanım: python migrate_raf_kodu.py
"""

from app import app, db
from sqlalchemy import text

def add_raf_kodu_column():
    with app.app_context():
        try:
            # Önce sütunun var olup olmadığını kontrol et
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='siparis_urunler' AND column_name='raf_kodu'
            """))
            
            if result.fetchone():
                print("⚠️  raf_kodu sütunu zaten mevcut.")
                return
            
            # Sütun yoksa ekle
            db.session.execute(text("ALTER TABLE siparis_urunler ADD COLUMN raf_kodu VARCHAR"))
            db.session.commit()
            print("✅ Migration başarılı! raf_kodu sütunu eklendi.")
            
        except Exception as e:
            print(f"❌ Hata: {e}")
            db.session.rollback()

if __name__ == "__main__":
    add_raf_kodu_column()
