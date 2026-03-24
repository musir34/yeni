"""Add atanan_raf column to orders_created

Revision ID: add_atanan_raf
Revises: add_source_column
Create Date: 2026-03-24

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_atanan_raf'
down_revision = 'add_source_column'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.add_column('orders_created', sa.Column('atanan_raf', sa.String(), nullable=True))
        print("✅ orders_created tablosuna 'atanan_raf' kolonu eklendi")
    except Exception as e:
        print(f"⚠️  atanan_raf kolonu zaten var veya hata: {e}")


def downgrade():
    try:
        op.drop_column('orders_created', 'atanan_raf')
    except Exception as e:
        print(f"⚠️  atanan_raf kolonu kaldırılamadı: {e}")
