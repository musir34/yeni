"""Create orders_hazirlaniyor table (Yeni ile Picking arasi ara statu)

Revision ID: add_orders_hazirlaniyor
Revises: add_raf_check
Create Date: 2026-06-01

Stogu teyit edilip Trendyol'da Picking'e cekilmis, fiziksel toplanmayi bekleyen
siparisler bu tabloda tutulur. Stok rezervi bu statude tutulur.
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_orders_hazirlaniyor'
down_revision = 'add_raf_check'
branch_labels = None
depends_on = None


def upgrade():
    try:
        # Tabloyu modelden olustur (kolonlar OrderBase + OrderHazirlaniyor ile senkron kalir).
        from models import OrderHazirlaniyor
        OrderHazirlaniyor.__table__.create(bind=op.get_bind(), checkfirst=True)
        print("✅ orders_hazirlaniyor tablosu oluşturuldu")
    except Exception as e:
        print(f"⚠️  orders_hazirlaniyor oluşturulamadı veya zaten var: {e}")


def downgrade():
    try:
        op.drop_table('orders_hazirlaniyor')
    except Exception as e:
        print(f"⚠️  orders_hazirlaniyor kaldırılamadı: {e}")
