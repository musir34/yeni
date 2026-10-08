#!/usr/bin/env python3
"""uretim_siparis tablosuna 'arsivlendi_at' kolonunu ekler — ADDITIVE, IDEMPOTENT.

Üretim sayfasındaki Paketlenen sekmesinde takılı kalan eski siparişler için
"Arşivle" düğmesi bu kolona damga vurur. Kolon zaten varsa hiçbir şey yapmaz,
başka tabloya/kolona DOKUNMAZ.

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 /home/musir/gullupanel/venv/bin/python scripts/add_uretim_arsiv.py
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
            "ALTER TABLE uretim_siparis ADD COLUMN IF NOT EXISTS arsivlendi_at TIMESTAMP"
        ))
        db.session.commit()
        print("OK: uretim_siparis.arsivlendi_at kolonu hazır.")


if __name__ == "__main__":
    main()
