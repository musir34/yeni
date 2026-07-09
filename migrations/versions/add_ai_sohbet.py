"""Add ai_sohbet + ai_mesaj tables (AI asistanı çoklu sohbet)

Revision ID: add_ai_sohbet
Revises: None
Create Date: 2026-07-10

AI asistanı çoklu sohbet + asenkron cevap altyapısı. TAMAMEN ADDITIVE:
sadece iki yeni tablo + indexler oluşturur, mevcut hiçbir tabloya/kolona
dokunmaz. Canlı veri etkilenmez.
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_ai_sohbet'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.create_table(
            'ai_sohbet',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('kullanici', sa.String(length=64), nullable=False),
            sa.Column('baslik', sa.String(length=120), nullable=False),
            sa.Column('claude_session_id', sa.String(length=64), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_ai_sohbet_kullanici', 'ai_sohbet', ['kullanici'])
        op.create_index('ix_ai_sohbet_updated_at', 'ai_sohbet', ['updated_at'])
        print("✅ ai_sohbet tablosu oluşturuldu")
    except Exception as e:
        print(f"⚠️  ai_sohbet tablosu zaten var veya hata: {e}")

    try:
        op.create_table(
            'ai_mesaj',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('sohbet_id', sa.Integer(), nullable=False),
            sa.Column('rol', sa.String(length=16), nullable=False),
            sa.Column('metin', sa.Text(), nullable=False),
            sa.Column('durum', sa.String(length=16), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['sohbet_id'], ['ai_sohbet.id'], ondelete='CASCADE'),
            sa.CheckConstraint("durum IN ('hazir','bekliyor','hata')", name='ck_ai_mesaj_durum'),
        )
        op.create_index('ix_ai_mesaj_sohbet_id', 'ai_mesaj', ['sohbet_id'])
        print("✅ ai_mesaj tablosu oluşturuldu")
    except Exception as e:
        print(f"⚠️  ai_mesaj tablosu zaten var veya hata: {e}")


def downgrade():
    op.drop_table('ai_mesaj')
    op.drop_table('ai_sohbet')
