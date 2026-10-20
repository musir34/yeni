#!/usr/bin/env python3
"""Sipariş Hazırla — Telefon Eşlik tablolarını açar — ADDITIVE, IDEMPOTENT.

hazirla_eslesme (QR oturumu) ve hazirla_okutma (telefondan gelen okutmalar) tabloları.
Varsa dokunmaz, başka tabloya DOKUNMAZ.

Çalıştırma (production DB'ye .env üzerinden bağlanır, RESTART ÖNCESİ):
    cd /home/musir/gullupanel/yeni && DISABLE_JOBS=1 ../venv/bin/python scripts/add_hazirla_telefon.py
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
    from models import db, HazirlaEslesme, HazirlaOkutma
    from sqlalchemy import text

    with app.app_context():
        for model in (HazirlaEslesme, HazirlaOkutma):
            model.__table__.create(bind=db.engine, checkfirst=True)
            print(f"OK: {model.__tablename__} tablosu hazır.")
        # Cihaz anahtarı kolonları (tablo daha önce açıldıysa additive ekle)
        for kolon in ("pc_anahtar", "telefon_anahtar"):
            db.session.execute(text(f"ALTER TABLE hazirla_eslesme ADD COLUMN IF NOT EXISTS {kolon} VARCHAR(64)"))
        db.session.commit()
        print("OK: hazirla_eslesme.pc_anahtar / telefon_anahtar kolonları hazır.")


if __name__ == "__main__":
    main()
