#!/usr/bin/env python3
"""/soru-cevap arşivi için 'archived_at' + 'archived_by' kolonlarını ekler — ADDITIVE, IDEMPOTENT.

Dört soru tablosuna (trendyol_questions, shopify_questions, instagram_conversations,
instagram_comments) panel içi arşiv damgası. Kolon zaten varsa hiçbir şey yapmaz,
başka tabloya/kolona DOKUNMAZ. Pazaryeri statüsü (status) ayrı kalır; senkron
bu kolonlara yazmaz.

ÖNEMLİ: Modeller bu kolonları okuduğu için kod güncellendikten (git pull) SONRA,
servis yeniden başlatılmadan ÖNCE çalıştırılmalı.

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 /home/musir/gullupanel/venv/bin/python scripts/add_soru_arsiv.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")

TABLOLAR = ("trendyol_questions", "shopify_questions", "instagram_conversations", "instagram_comments")


def main():
    from app import app
    from models import db
    from sqlalchemy import text

    with app.app_context():
        for tablo in TABLOLAR:
            db.session.execute(text(
                f"ALTER TABLE {tablo} ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITH TIME ZONE"
            ))
            db.session.execute(text(
                f"ALTER TABLE {tablo} ADD COLUMN IF NOT EXISTS archived_by VARCHAR(120)"
            ))
        db.session.commit()
        print("OK: " + ", ".join(f"{t}.archived_at/archived_by" for t in TABLOLAR) + " kolonları hazır.")


if __name__ == "__main__":
    main()
