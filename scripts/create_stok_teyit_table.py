#!/usr/bin/env python3
"""stok_teyit tablosunu açar — ADDITIVE, IDEMPOTENT.

Tek adet raf teyidi (/tek-adet-teyit). Tablo zaten varsa hiçbir şey yapmaz,
başka tabloya/kolona DOKUNMAZ. Servis yeniden başlatılmadan ÖNCE çalıştırılmalı:
tablo yokken senkron "teyit yok" sayar ve stoğu 1 olan tüm barkodları 0 gönderir.

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 python scripts/create_stok_teyit_table.py
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
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS stok_teyit (
                barcode VARCHAR PRIMARY KEY,
                teyit_at TIMESTAMP NOT NULL,
                teyit_by VARCHAR(150)
            )
        """))
        db.session.commit()
        print("OK: stok_teyit tablosu hazır.")


if __name__ == "__main__":
    main()
