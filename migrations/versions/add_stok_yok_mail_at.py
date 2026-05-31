"""Add stok_yok_mail_at column to orders_created

Revision ID: add_stok_yok_mail_at
Revises: add_orders_hazirlaniyor
Create Date: 2026-06-01

Stoksuz sipariş için anlık mail gönderildiğinde işaretlenir (tekrar gönderimi önler).
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_stok_yok_mail_at'
down_revision = 'add_orders_hazirlaniyor'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.add_column('orders_created', sa.Column('stok_yok_mail_at', sa.DateTime(), nullable=True))
        print("✅ orders_created tablosuna 'stok_yok_mail_at' kolonu eklendi")
    except Exception as e:
        print(f"⚠️  stok_yok_mail_at kolonu zaten var veya hata: {e}")


def downgrade():
    try:
        op.drop_column('orders_created', 'stok_yok_mail_at')
    except Exception as e:
        print(f"⚠️  stok_yok_mail_at kolonu kaldırılamadı: {e}")
