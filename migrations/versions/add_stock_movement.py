"""Add stock_movement table (append-only stok hareket defteri)

Revision ID: add_stock_movement
Revises: add_stok_yok_mail_at
Create Date: 2026-06-10

Stok katmanı yeniden tasarımı (ledger modeli). TAMAMEN ADDITIVE:
sadece yeni tablo + index oluşturur, mevcut hiçbir tabloya/kolona dokunmaz.
Canlı veri etkilenmez.
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_stock_movement'
down_revision = 'add_stok_yok_mail_at'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.create_table(
            'stock_movement',
            sa.Column('id', sa.BigInteger(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('barcode', sa.String(length=64), nullable=False),
            sa.Column('shelf_code', sa.String(length=64), nullable=True),
            sa.Column('delta', sa.Integer(), nullable=False),
            sa.Column('reason', sa.String(length=32), nullable=False),
            sa.Column('order_number', sa.String(length=64), nullable=True),
            sa.Column('idempotency_key', sa.String(length=128), nullable=True),
            sa.Column('source', sa.String(length=32), nullable=True),
            sa.Column('note', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('idempotency_key', name='uq_stock_movement_idem'),
            sa.CheckConstraint(
                "reason IN ('goods_in','pack_out','ship_out','cancel_return',"
                "'manual_adjust','opening_balance','exchange','reconcile')",
                name='ck_stock_movement_reason',
            ),
        )
        op.create_index('ix_stock_movement_created_at', 'stock_movement', ['created_at'])
        op.create_index('ix_stock_movement_barcode', 'stock_movement', ['barcode'])
        op.create_index('ix_stock_movement_reason', 'stock_movement', ['reason'])
        op.create_index('ix_stock_movement_order_number', 'stock_movement', ['order_number'])
        op.create_index('ix_stock_movement_barcode_created', 'stock_movement', ['barcode', 'created_at'])
        print("✅ stock_movement tablosu ve indexleri oluşturuldu")
    except Exception as e:
        print(f"⚠️  stock_movement tablosu zaten var veya hata: {e}")


def downgrade():
    try:
        op.drop_table('stock_movement')  # indexler tabloyla birlikte düşer
    except Exception as e:
        print(f"⚠️  stock_movement tablosu kaldırılamadı: {e}")
