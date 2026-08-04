"""Add son_sql column to ai_mesaj (asistan cevabından Excel indirme)

Revision ID: add_ai_mesaj_son_sql
Revises: add_ai_sohbet
Create Date: 2026-08-04

Codex motoru cevabı üretirken çalıştırdığı SON SELECT'i burada saklar; panel
"Excel indir" butonunda bu sorguyu ai_readonly ile yeniden çalıştırıp tam
veriyi .xlsx olarak verir. TAMAMEN ADDITIVE: tek nullable kolon.
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_ai_mesaj_son_sql'
down_revision = 'add_ai_sohbet'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.add_column('ai_mesaj', sa.Column('son_sql', sa.Text(), nullable=True))
        print("✅ ai_mesaj tablosuna 'son_sql' kolonu eklendi")
    except Exception as e:
        print(f"⚠️  son_sql kolonu zaten var veya hata: {e}")


def downgrade():
    try:
        op.drop_column('ai_mesaj', 'son_sql')
    except Exception as e:
        print(f"⚠️  son_sql kolonu kaldırılamadı: {e}")
