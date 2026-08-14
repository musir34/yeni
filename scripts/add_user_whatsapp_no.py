#!/usr/bin/env python3
"""users tablosuna 'whatsapp_no' kolonunu ekler — ADDITIVE, IDEMPOTENT.

Çalışan WhatsApp bildirimleri için: kullanıcı yönetiminden girilen numara
(905xxxxxxxxx biçiminde) bu kolonda tutulur; whatsapp_service alıcıları
buradan çeker. Kolon zaten varsa hiçbir şey yapmaz, başka tabloya/kolona
DOKUNMAZ.

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 python scripts/add_user_whatsapp_no.py
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
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS whatsapp_no VARCHAR(32)"
        ))
        db.session.commit()
        print("OK: users.whatsapp_no kolonu hazır.")


if __name__ == "__main__":
    main()
