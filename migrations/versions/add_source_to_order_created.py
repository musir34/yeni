"""Add source column to order tables

Revision ID: add_source_column
Revises: 
Create Date: 2025-11-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_source_column'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # OrderCreated ve diğer order tablolarına source kolonu ekle
    tables = [
        'orders_created',
        'orders_picking',
        'orders_shipped',
        'orders_delivered',
        'orders_cancelled',
        'orders_archived',
        'orders_ready_to_ship'
    ]
    
    for table in tables:
        try:
            op.add_column(table, sa.Column('source', sa.String(20), server_default='TRENDYOL', nullable=False))
            print(f"✅ {table} tablosuna 'source' kolonu eklendi")
        except Exception as e:
            print(f"⚠️  {table} - source kolonu zaten var veya hata: {e}")


def downgrade():
    # Geri alma: source kolonunu kaldır
    tables = [
        'orders_created',
        'orders_picking',
        'orders_shipped',
        'orders_delivered',
        'orders_cancelled',
        'orders_archived',
        'orders_ready_to_ship'
    ]
    
    for table in tables:
        try:
            op.drop_column(table, 'source')
        except Exception as e:
            print(f"⚠️  {table} - source kolonu kaldırılamadı: {e}")
