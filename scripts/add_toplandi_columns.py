#!/usr/bin/env python3
"""orders_hazirlaniyor'a toplandi_at + toplandi_raf kolonlarını ekler.

ADDITIVE, IDEMPOTENT: ALTER TABLE ... ADD COLUMN IF NOT EXISTS (Postgres).
Mevcut hiçbir kolona/tabloya dokunmaz; canlı veri güvende.

Çalıştırma (prod DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 python scripts/add_toplandi_columns.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")


def main():
    from app import app
    from models import db
    from sqlalchemy import text

    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE orders_hazirlaniyor ADD COLUMN IF NOT EXISTS toplandi_at TIMESTAMP"
            ))
            conn.execute(text(
                "ALTER TABLE orders_hazirlaniyor ADD COLUMN IF NOT EXISTS toplandi_raf VARCHAR"
            ))
        print("✅ orders_hazirlaniyor: toplandi_at + toplandi_raf eklendi (veya zaten vardı).")


if __name__ == "__main__":
    main()
