from models import db, CustomerQuestion
from app import app
from sqlalchemy import inspect

def create_customer_questions_table():
    """
    Müşteri soruları tablosunu oluşturur
    """
    with app.app_context():
        # Eğer tablo zaten varsa bir şey yapmayacak
        inspector = inspect(db.engine)
        if not inspector.has_table(CustomerQuestion.__tablename__):
            print(f"Creating table: {CustomerQuestion.__tablename__}")
            db.create_all()  # Tüm tabloları oluşturacak ama sadece olmayanlar eklenecek
            print("CustomerQuestion table created successfully.")
        else:
            print("CustomerQuestion table already exists.")

if __name__ == "__main__":
    create_customer_questions_table()