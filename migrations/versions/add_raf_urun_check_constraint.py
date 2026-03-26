"""Add CHECK constraint to raf_urunleri.adet (non-negative)

Revision ID: add_raf_check
Revises: add_atanan_raf
Create Date: 2026-03-26

"""
from alembic import op

revision = 'add_raf_check'
down_revision = 'add_atanan_raf'
branch_labels = None
depends_on = None


def upgrade():
    # Önce negatif/sıfır kayıtları temizle
    op.execute("DELETE FROM raf_urunleri WHERE adet <= 0")
    # CHECK constraint ekle
    try:
        op.create_check_constraint(
            'ck_raf_urun_adet_non_negative',
            'raf_urunleri',
            'adet >= 0'
        )
        print("✅ raf_urunleri.adet CHECK constraint eklendi (adet >= 0)")
    except Exception as e:
        print(f"⚠️ CHECK constraint zaten mevcut veya eklenemedi: {e}")


def downgrade():
    try:
        op.drop_constraint('ck_raf_urun_adet_non_negative', 'raf_urunleri', type_='check')
    except Exception:
        pass
