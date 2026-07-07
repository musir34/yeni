"""Add stock_listing_policy table (iptal-eğilimli ürünler için ekstra listeleme tamponu)

Revision ID: add_stock_listing_policy
Revises:
Create Date: 2026-07-07

Additive — mevcut tablolara dokunmaz. Yeni tablo yoksa senkron eski davranışıyla
(yalnız global SAFETY_STOCK_BUFFER) çalışmaya devam eder; bu migration ekstra
barkod-bazlı tamponu etkinleştirir.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_stock_listing_policy'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'stock_listing_policy' in insp.get_table_names():
        return
    op.create_table(
        'stock_listing_policy',
        sa.Column('barcode', sa.String(), nullable=False),
        sa.Column('extra_buffer', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cancel_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reason', sa.String(length=200), nullable=True),
        sa.Column('auto', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('barcode'),
    )


def downgrade():
    op.drop_table('stock_listing_policy')
