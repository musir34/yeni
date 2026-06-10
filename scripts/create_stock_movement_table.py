#!/usr/bin/env python3
"""stock_movement tablosunu oluşturur — ADDITIVE, IDEMPOTENT, GÜVENLİ.

Kod tabanındaki mevcut `order_audit.ensure_table_exists()` desenini izler:
`StockMovement.__table__.create(checkfirst=True)` — tablo zaten varsa hiçbir şey
yapmaz, başka hiçbir tabloya/kolona DOKUNMAZ. Alembic multi-head karmaşasına
girmeden tek tabloyu güvenle ekler.

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 python scripts/create_stock_movement_table.py
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
    from models import db, StockMovement
    from sqlalchemy import inspect

    with app.app_context():
        insp = inspect(db.engine)
        if insp.has_table("stock_movement"):
            print("ℹ️  stock_movement tablosu ZATEN VAR — değişiklik yapılmadı.")
            return
        StockMovement.__table__.create(bind=db.engine, checkfirst=True)
        # doğrula
        insp = inspect(db.engine)
        if insp.has_table("stock_movement"):
            cols = [c["name"] for c in insp.get_columns("stock_movement")]
            print("✅ stock_movement tablosu oluşturuldu.")
            print(f"   Kolonlar: {', '.join(cols)}")
        else:
            print("❌ Tablo oluşturulamadı (beklenmedik).")
            sys.exit(1)


if __name__ == "__main__":
    main()
