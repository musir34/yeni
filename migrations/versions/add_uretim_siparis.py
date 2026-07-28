"""Add uretim_siparis table (Üretim Modu — ön sipariş takibi)

Revision ID: add_uretim_siparis
Revises:
Create Date: 2026-07-28

Additive — mevcut tablolara dokunmaz. Tablo yoksa üretim modu kancaları
(sipariş ingest, terfi hariç tutma) sessizce devre dışı kalır ve mevcut
davranış korunur; bu migration özelliği etkinleştirir. Prod'da alembic
koşulmadığı için tablo scripts/create_uretim_tables.py ile açılır.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_uretim_siparis'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'uretim_siparis' in insp.get_table_names():
        return
    op.create_table(
        'uretim_siparis',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_number', sa.String(length=50), nullable=False),
        sa.Column('package_number', sa.String(length=50), nullable=True),
        sa.Column('product_main_id', sa.String(length=255), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('customer_name', sa.String(length=255), nullable=True),
        sa.Column('order_date', sa.DateTime(), nullable=True),
        sa.Column('uretildi', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('uretildi_at', sa.DateTime(), nullable=True),
        sa.Column('mail_sent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_number', name='uq_uretim_siparis_order'),
    )
    op.create_index('ix_uretim_siparis_order_number', 'uretim_siparis', ['order_number'])
    op.create_index('ix_uretim_siparis_uretildi', 'uretim_siparis', ['uretildi'])


def downgrade():
    op.drop_table('uretim_siparis')
