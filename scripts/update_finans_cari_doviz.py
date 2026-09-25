#!/usr/bin/env python3
"""Cari hesaplara para birimi (TRY/USD) ve kasa bağlı hareketlere kur alanı ekler.

Additive; mevcut kayıtlar TRY kalır. Tekrar çalıştırılabilir.
Uygulamayı yeniden başlatmadan önce sunucuda:
    DISABLE_JOBS=1 ../venv/bin/python scripts/update_finans_cari_doviz.py
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DISABLE_JOBS', '1')
os.environ.setdefault('WERKZEUG_RUN_MAIN', 'false')

DDL = [
    "ALTER TABLE finans_cari ADD COLUMN IF NOT EXISTS para_birimi VARCHAR(3) NOT NULL DEFAULT 'TRY'",
    "ALTER TABLE finans_cari_hareket ADD COLUMN IF NOT EXISTS kur NUMERIC(12,4)",
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
        print('Cari para birimi (TRY/USD) ve kur alanları hazır.')


if __name__ == '__main__':
    main()
