# db_setup.py
from models import db, ProductArchive
from sqlalchemy import text, inspect
from app import app

def run_setup():
    with app.app_context():
        db.create_all()
        db.session.execute(text(
            'ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_date TIMESTAMP'
        ))
        inspector = inspect(db.engine)
        if not inspector.has_table('product_archives'):
            ProductArchive.__table__.create(db.engine)
        db.session.commit()
        print("✅ Veritabanı kurulumu tamamlandı.")
