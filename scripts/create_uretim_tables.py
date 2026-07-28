#!/usr/bin/env python3
"""uretim_siparis tablosunu oluşturur — ADDITIVE, IDEMPOTENT, GÜVENLİ.

scripts/create_ai_sohbet_tables.py ile aynı deseni izler:
`Model.__table__.create(checkfirst=True)` — tablo zaten varsa hiçbir
şey yapmaz, başka hiçbir tabloya/kolona DOKUNMAZ.

Üretim Modu özelliği (migrations/versions/add_uretim_siparis.py ile aynı şema).
Prod'da alembic koşulmadığı için tablo bu script ile açılır. Ayarlar
(model listesi + mail adresi) PlatformConfig 'uretim_ayar' satırında tutulur,
onun için migration/script GEREKMEZ.

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 python scripts/create_uretim_tables.py
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
    from models import db, UretimSiparis
    from sqlalchemy import inspect

    with app.app_context():
        insp = inspect(db.engine)
        tablo = "uretim_siparis"
        if insp.has_table(tablo):
            print(f"ℹ️  {tablo} tablosu ZATEN VAR — değişiklik yapılmadı.")
            return
        UretimSiparis.__table__.create(bind=db.engine, checkfirst=True)
        insp = inspect(db.engine)  # doğrulama için tazele
        if insp.has_table(tablo):
            cols = [c["name"] for c in insp.get_columns(tablo)]
            print(f"✅ {tablo} tablosu oluşturuldu.")
            print(f"   Kolonlar: {', '.join(cols)}")
        else:
            print(f"❌ {tablo} oluşturulamadı — DB bağlantısını kontrol edin.")
            sys.exit(1)


if __name__ == "__main__":
    main()
