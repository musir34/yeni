#!/usr/bin/env python3
"""alissa_* tablolarını oluşturur — ADDITIVE, IDEMPOTENT, GÜVENLİ.

scripts/create_ai_sohbet_tables.py ile aynı desen: tablo zaten varsa hiçbir şey
yapmaz, başka hiçbir tabloya/kolona DOKUNMAZ. Prod'da alembic koşulmadığı için
tablolar bu script ile açılır.

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 python -m alissa.kur             # yalnız tablolar
    DISABLE_JOBS=1 python -m alissa.kur --senkron   # tablolar + ilk veri çekimi (birkaç dakika)
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
    from sqlalchemy import inspect
    from alissa.models import TABLOLAR

    with app.app_context():
        insp = inspect(db.engine)
        for model in TABLOLAR:
            tablo = model.__tablename__
            if insp.has_table(tablo):
                print(f"ℹ️  {tablo} tablosu ZATEN VAR — değişiklik yapılmadı.")
                continue
            model.__table__.create(bind=db.engine, checkfirst=True)
            insp = inspect(db.engine)  # doğrulama için tazele
            if insp.has_table(tablo):
                print(f"✅ {tablo} tablosu oluşturuldu.")
            else:
                print(f"❌ {tablo} oluşturulamadı — DB bağlantısını kontrol edin.")
                sys.exit(1)

        if "--senkron" in sys.argv:
            from alissa.senkron import senkronla
            print("⏳ Trendyol'dan ilk veri çekiliyor (birkaç dakika sürer)...")
            print(f"✅ Senkron tamam: {senkronla()}")


if __name__ == "__main__":
    main()
