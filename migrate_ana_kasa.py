"""
Ana Kasa Sistemi Migration Script
----------------------------------
Bu script Ana Kasa sistemini ekler:
1. ana_kasa tablosunu oluşturur
2. ana_kasa_islemler tablosunu oluşturur
3. kasa tablosuna ana_kasadan boolean alanını ekler
"""

from models import db, AnaKasa, AnaKasaIslem
from app import app
from sqlalchemy import text

def migrate():
    with app.app_context():
        try:
            # 1. Ana Kasa tablosunu oluştur
            print("Ana Kasa tablosu oluşturuluyor...")
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS ana_kasa (
                    id SERIAL PRIMARY KEY,
                    bakiye NUMERIC(12, 2) NOT NULL DEFAULT 0,
                    guncelleme_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            
            # 2. Ana Kasa İşlemler tablosunu oluştur
            print("Ana Kasa İşlemler tablosu oluşturuluyor...")
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS ana_kasa_islemler (
                    id SERIAL PRIMARY KEY,
                    islem_tipi VARCHAR(20) NOT NULL,
                    tutar NUMERIC(12, 2) NOT NULL,
                    aciklama VARCHAR(500) NOT NULL,
                    onceki_bakiye NUMERIC(12, 2) NOT NULL,
                    yeni_bakiye NUMERIC(12, 2) NOT NULL,
                    tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    kullanici_id INTEGER NOT NULL REFERENCES users(id),
                    kasa_id INTEGER REFERENCES kasa(id)
                );
            """))
            
            # 3. Kasa tablosuna ana_kasadan alanını ekle
            print("Kasa tablosuna ana_kasadan alanı ekleniyor...")
            db.session.execute(text("""
                ALTER TABLE kasa 
                ADD COLUMN IF NOT EXISTS ana_kasadan BOOLEAN NOT NULL DEFAULT FALSE;
            """))
            
            # 4. İlk Ana Kasa kaydını oluştur
            print("İlk Ana Kasa kaydı oluşturuluyor...")
            ana_kasa_var = db.session.query(AnaKasa).first()
            if not ana_kasa_var:
                yeni_ana_kasa = AnaKasa(bakiye=0)
                db.session.add(yeni_ana_kasa)
            
            db.session.commit()
            print("✅ Migration başarıyla tamamlandı!")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Migration hatası: {e}")
            raise

if __name__ == '__main__':
    migrate()
