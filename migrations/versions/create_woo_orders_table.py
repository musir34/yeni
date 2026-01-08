"""create woo_orders table

Revision ID: woo_orders_001
Revises: 
Create Date: 2025-11-21 17:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'woo_orders_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('woo_orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('order_number', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('date_created', sa.DateTime(), nullable=True),
    sa.Column('date_modified', sa.DateTime(), nullable=True),
    sa.Column('last_synced', sa.DateTime(), nullable=True),
    sa.Column('customer_first_name', sa.String(length=100), nullable=True),
    sa.Column('customer_last_name', sa.String(length=100), nullable=True),
    sa.Column('customer_email', sa.String(length=200), nullable=True),
    sa.Column('customer_phone', sa.String(length=50), nullable=True),
    sa.Column('billing_address_1', sa.String(length=255), nullable=True),
    sa.Column('billing_address_2', sa.String(length=255), nullable=True),
    sa.Column('billing_city', sa.String(length=100), nullable=True),
    sa.Column('billing_state', sa.String(length=100), nullable=True),
    sa.Column('billing_postcode', sa.String(length=20), nullable=True),
    sa.Column('billing_country', sa.String(length=2), nullable=True),
    sa.Column('shipping_address_1', sa.String(length=255), nullable=True),
    sa.Column('shipping_address_2', sa.String(length=255), nullable=True),
    sa.Column('shipping_city', sa.String(length=100), nullable=True),
    sa.Column('shipping_state', sa.String(length=100), nullable=True),
    sa.Column('shipping_postcode', sa.String(length=20), nullable=True),
    sa.Column('shipping_country', sa.String(length=2), nullable=True),
    sa.Column('total', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('shipping_total', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('tax_total', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('discount_total', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('payment_method', sa.String(length=100), nullable=True),
    sa.Column('payment_method_title', sa.String(length=200), nullable=True),
    sa.Column('transaction_id', sa.String(length=200), nullable=True),
    sa.Column('customer_note', sa.Text(), nullable=True),
    sa.Column('line_items', sa.JSON(), nullable=True),
    sa.Column('raw_data', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_woo_orders_order_id'), 'woo_orders', ['order_id'], unique=True)
    op.create_index(op.f('ix_woo_orders_status'), 'woo_orders', ['status'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_woo_orders_status'), table_name='woo_orders')
    op.drop_index(op.f('ix_woo_orders_order_id'), table_name='woo_orders')
    op.drop_table('woo_orders')
