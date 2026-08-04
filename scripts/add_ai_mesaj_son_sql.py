#!/usr/bin/env python3
"""ai_mesaj tablosuna 'son_sql' kolonunu ekler — ADDITIVE, IDEMPOTENT, GÜVENLİ.

scripts/create_ai_sohbet_tables.py ile aynı deseni izler: kolon zaten varsa
hiçbir şey yapmaz, başka hiçbir tabloya/kolona DOKUNMAZ.

Ne işe yarar: Codex motoru bir cevabı üretirken çalıştırdığı SON SELECT'i bu
kolona yazar; panelde cevabın altında "Excel indir" çıkar ve sorgu indirme
anında ai_readonly ile yeniden çalıştırılıp tam veri .xlsx olarak verilir.
(Prod'da alembic koşulmadığı için migrations/versions/add_ai_mesaj_son_sql.py
yerine bu script kullanılır.)

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 /home/musir/gullupanel/venv/bin/python scripts/add_ai_mesaj_son_sql.py
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
    from sqlalchemy import inspect, text

    with app.app_context():
        insp = inspect(db.engine)
        if not insp.has_table("ai_mesaj"):
            print("❌ ai_mesaj tablosu yok — önce scripts/create_ai_sohbet_tables.py çalıştırın.")
            sys.exit(1)

        kolonlar = [c["name"] for c in insp.get_columns("ai_mesaj")]
        if "son_sql" in kolonlar:
            print("ℹ️  son_sql kolonu ZATEN VAR — değişiklik yapılmadı.")
            return

        with db.engine.begin() as baglanti:
            baglanti.execute(text("ALTER TABLE ai_mesaj ADD COLUMN son_sql TEXT"))

        kolonlar = [c["name"] for c in inspect(db.engine).get_columns("ai_mesaj")]
        if "son_sql" in kolonlar:
            print("✅ ai_mesaj tablosuna 'son_sql' kolonu eklendi.")
            print(f"   Kolonlar: {', '.join(kolonlar)}")
        else:
            print("❌ Kolon eklenemedi — DB bağlantısını kontrol edin.")
            sys.exit(1)


if __name__ == "__main__":
    main()
