#!/usr/bin/env python3
"""motor_oneri_log tablosunu oluşturur — ADDITIVE, IDEMPOTENT, GÜVENLİ.

scripts/create_stock_movement_table.py ile aynı deseni izler:
`MotorOneriLog.__table__.create(checkfirst=True)` — tablo zaten varsa hiçbir
şey yapmaz, başka hiçbir tabloya/kolona DOKUNMAZ.

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 python scripts/create_motor_oneri_log_table.py
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
    from models import db, MotorOneriLog
    from sqlalchemy import inspect

    with app.app_context():
        insp = inspect(db.engine)
        if insp.has_table("motor_oneri_log"):
            print("ℹ️  motor_oneri_log tablosu ZATEN VAR — değişiklik yapılmadı.")
            return
        MotorOneriLog.__table__.create(bind=db.engine, checkfirst=True)
        # doğrula
        insp = inspect(db.engine)
        if insp.has_table("motor_oneri_log"):
            cols = [c["name"] for c in insp.get_columns("motor_oneri_log")]
            print("✅ motor_oneri_log tablosu oluşturuldu.")
            print(f"   Kolonlar: {', '.join(cols)}")
        else:
            print("❌ Tablo oluşturulamadı — DB bağlantısını kontrol edin.")
            sys.exit(1)


if __name__ == "__main__":
    main()
