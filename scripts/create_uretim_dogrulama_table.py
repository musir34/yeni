#!/usr/bin/env python3
"""uretim_dogrulama tablosunu oluşturur — ADDITIVE, IDEMPOTENT, GÜVENLİ.

scripts/create_ai_sohbet_tables.py ile aynı desen: `__table__.create(checkfirst=True)`
— tablo zaten varsa hiçbir şey yapmaz, başka tabloya/kolona DOKUNMAZ.

Üretim ekranı 'yanlış ürün asla gitmesin' sistemi: üretilen kalemler paketlemede
adet adet okutulur, izi bu tabloya düşer; tüm kalemler okutulmadan etiket verilmez.

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 python scripts/create_uretim_dogrulama_table.py
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
    from models import db, UretimDogrulama

    with app.app_context():
        UretimDogrulama.__table__.create(db.engine, checkfirst=True)
        print("OK: uretim_dogrulama tablosu hazır.")


if __name__ == "__main__":
    main()
