#!/usr/bin/env python3
"""siparis_notu tablosunu açar — ADDITIVE, IDEMPOTENT.

Siparişe özel serbest metin notlar (sipariş listesi + sipariş hazırla ekranı).
Tablo zaten varsa hiçbir şey yapmaz, başka tabloya/kolona DOKUNMAZ.

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 python scripts/create_siparis_notu_table.py
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
            CREATE TABLE IF NOT EXISTS siparis_notu (
                id SERIAL PRIMARY KEY,
                order_number VARCHAR(50) NOT NULL UNIQUE,
                note TEXT NOT NULL,
                updated_by VARCHAR(150),
                updated_at TIMESTAMP
            )
        """))
        db.session.commit()
        print("OK: siparis_notu tablosu hazır.")


if __name__ == "__main__":
    main()
