#!/usr/bin/env python3
"""uretim_siparis tablosuna 'paketlendi' + 'paketlendi_at' kolonlarını ekler — ADDITIVE, IDEMPOTENT.

Üretim sayfası 6 statülü akışa geçti (Bekleyen → Üretiliyor → Üretilen →
Paketlenen → Kargoya Verilen → Teslim Edilen); 'Paketlenen' statüsü bu
kolonlarla damgalanır. Kolonlar zaten varsa hiçbir şey yapmaz.

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 python scripts/add_uretim_paketlendi.py
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
            "ALTER TABLE uretim_siparis ADD COLUMN IF NOT EXISTS paketlendi BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        db.session.execute(text(
            "ALTER TABLE uretim_siparis ADD COLUMN IF NOT EXISTS paketlendi_at TIMESTAMP"
        ))
        db.session.commit()
        print("OK: uretim_siparis.paketlendi + paketlendi_at kolonları hazır.")


if __name__ == "__main__":
    main()
