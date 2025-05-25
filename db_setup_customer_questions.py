from models import db, CustomerQuestion
from app import app

def create_customer_questions_table():
    """
    Müşteri soruları tablosunu oluşturur
    """
    with app.app_context():
        # Eğer tablo zaten varsa bir şey yapmayacak
        if not db.engine.has_table(CustomerQuestion.__tablename__):
            print(f"Creating table: {CustomerQuestion.__tablename__}")
            db.create_all(tables=[CustomerQuestion.__table__])
            print("CustomerQuestion table created successfully.")
        else:
            print("CustomerQuestion table already exists.")

if __name__ == "__main__":
    create_customer_questions_table()