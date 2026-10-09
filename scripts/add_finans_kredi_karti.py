#!/usr/bin/env python3
"""finans_hesap tablosuna 'kredi_karti' hesabını ekler — ADDITIVE, IDEMPOTENT.

Kredi kartı borç hesabıdır: bakiyesi eksi olması normaldir (kart borcu), "emin misin?"
sorulmaz. Satır zaten varsa hiçbir şey yapmaz, başka tabloya/satıra DOKUNMAZ.

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 /home/musir/gullupanel/venv/bin/python scripts/add_finans_kredi_karti.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")


def main():
    from app import app
    from models import db
    from sqlalchemy import text

    with app.app_context():
        db.session.execute(text(
            "INSERT INTO finans_hesap (kod, ad, bakiye, sira) VALUES ('kredi_karti', 'Kredi Kartı (5503)', 0, 4) "
            "ON CONFLICT (kod) DO NOTHING"
        ))
        db.session.commit()
        n = db.session.execute(text("SELECT count(*) FROM finans_hesap WHERE kod='kredi_karti'")).scalar()
        print(f"OK: kredi_karti hesabı hazır ({n} satır).")


if __name__ == "__main__":
    main()
