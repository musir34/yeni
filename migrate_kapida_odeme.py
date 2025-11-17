"""
KAPIDA ÖDEME MIGRATION SCRIPT
Bu script yeni_siparisler tablosuna kapida_odeme ve kapida_odeme_tutari sütunlarını ekler.
Kullanım: python migrate_kapida_odeme.py
"""

from app import app, db
from sqlalchemy import text

def add_kapida_odeme_columns():
    with app.app_context():
        try:
            # Önce sütunların var olup olmadığını kontrol et
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='yeni_siparisler' AND column_name IN ('kapida_odeme', 'kapida_odeme_tutari')
            """))
            
            existing_columns = [row[0] for row in result.fetchall()]
            
            if 'kapida_odeme' in existing_columns and 'kapida_odeme_tutari' in existing_columns:
                print("⚠️  kapida_odeme ve kapida_odeme_tutari sütunları zaten mevcut.")
                return
            
            # kapida_odeme sütunu yoksa ekle
            if 'kapida_odeme' not in existing_columns:
                db.session.execute(text(
                    "ALTER TABLE yeni_siparisler ADD COLUMN kapida_odeme BOOLEAN DEFAULT FALSE"
                ))
                print("✅ kapida_odeme sütunu eklendi.")
            else:
                print("⚠️  kapida_odeme sütunu zaten mevcut.")
            
            # kapida_odeme_tutari sütunu yoksa ekle
            if 'kapida_odeme_tutari' not in existing_columns:
                db.session.execute(text(
                    "ALTER TABLE yeni_siparisler ADD COLUMN kapida_odeme_tutari NUMERIC(10, 2)"
                ))
                print("✅ kapida_odeme_tutari sütunu eklendi.")
            else:
                print("⚠️  kapida_odeme_tutari sütunu zaten mevcut.")
            
            db.session.commit()
            print("✅ Migration başarılı! Tüm sütunlar eklendi.")
            
        except Exception as e:
            print(f"❌ Hata: {e}")
            db.session.rollback()

if __name__ == "__main__":
    add_kapida_odeme_columns()
