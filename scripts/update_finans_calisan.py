#!/usr/bin/env python3
"""Çalışan carisi/hak ediş desteğini ekler. Mevcut kasa kayıtlarını değiştirmez.

DISABLE_JOBS=1 python scripts/update_finans_calisan.py
Haftalık ödeme ve cari önkoşullarını da tamamlar. Tekrar çalıştırılabilir.
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DISABLE_JOBS', '1')
os.environ.setdefault('WERKZEUG_RUN_MAIN', 'false')
from scripts.create_finans_tables import DDL as FINANS_DDL
from scripts.create_finans_cari_tables import DDL as CARI_DDL

DDL = FINANS_DDL + CARI_DDL + [
    'ALTER TABLE finans_ana_gider_kalem ADD COLUMN IF NOT EXISTS calisan_cari_id INTEGER REFERENCES finans_cari(id)',
    '''CREATE TABLE IF NOT EXISTS finans_calisan_hakedis (
        id SERIAL PRIMARY KEY,
        kalem_id INTEGER NOT NULL REFERENCES finans_ana_gider_kalem(id),
        donem VARCHAR(10) NOT NULL,
        tutar NUMERIC(12,2) CHECK (tutar >= 0),
        CONSTRAINT uq_finans_calisan_hakedis UNIQUE(kalem_id, donem)
    )''',
    'ALTER TABLE finans_cari_hareket ADD COLUMN IF NOT EXISTS hakedis_id INTEGER REFERENCES finans_calisan_hakedis(id)',
    'ALTER TABLE finans_cari_hareket ADD COLUMN IF NOT EXISTS odeme_anahtari VARCHAR(36)',
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_finans_cari_odeme_anahtari ON finans_cari_hareket(odeme_anahtari)',
    'CREATE INDEX IF NOT EXISTS ix_finans_cari_hakedis ON finans_cari_hareket(hakedis_id)',
    'CREATE INDEX IF NOT EXISTS ix_finans_kalem_calisan ON finans_ana_gider_kalem(calisan_cari_id)',
]


def main():
    from app import app
    from models import db
    from sqlalchemy import text
    with app.app_context():
        try:
            for stmt in DDL:
                db.session.execute(text(stmt))
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        print('Çalışan carisi, hak ediş ve kısmi ödeme alanları hazır.')


if __name__ == '__main__':
    main()
