from app import app, db
from models import CustomerQuestion

if __name__ == "__main__":
    with app.app_context():
        # Eksik tabloları oluştur
        print("Veritabanı tabloları oluşturuluyor...")
        db.create_all()
        print("Veritabanı tabloları başarıyla oluşturuldu!")