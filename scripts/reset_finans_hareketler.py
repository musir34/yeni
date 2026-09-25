#!/usr/bin/env python3
"""Clear finance transaction history, balances and recurring payment plans.

Run from the app directory after confirming a database backup:
    DISABLE_JOBS=1 ../venv/bin/python scripts/reset_finans_hareketler.py            # sayım (silmez)
    DISABLE_JOBS=1 ../venv/bin/python scripts/reset_finans_hareketler.py --confirm  # siler

Only the new /finans module is touched. The legacy /kasa tables are never used.
Recurring payment plans (Düzenli Ödemeler → Kalem Tanımları) are deleted too;
accounts, categories, expense names and cari/employee records are kept.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")

from sqlalchemy import text


TABLES = (
    "finans_cari_kalem",
    "finans_cari_hareket",
    "finans_calisan_hakedis",
    "finans_islem",
    "finans_ana_gider_kalem",
)
LOCK_TABLES = (
    "finans_ana_gider_kalem",
    "finans_hesap",
    "finans_cari",
    "finans_islem",
    "finans_cari_hareket",
    "finans_cari_kalem",
    "finans_calisan_hakedis",
)



def reset(*, confirm: bool) -> None:
    from app import app
    from models import db, FinansCari, FinansHesap
    from sqlalchemy import inspect

    with app.app_context():
        engine = db.engine
        if engine.dialect.name != "postgresql":
            raise SystemExit("Sıfırlama yalnızca PostgreSQL finans veritabanında çalışır.")
        present = set(inspect(engine).get_table_names())
        missing = [name for name in TABLES + LOCK_TABLES if name not in present]
        if missing:
            raise SystemExit("Şema eksik; hiçbir kayıt silinmedi. Eksik tablolar: " + ", ".join(sorted(set(missing))))

        if not confirm:
            # Salt okunur sayım: bağlantı ve kapsam doğrulanır, hiçbir kayıt silinmez.
            print("Silinecek kayıtlar (sayım, veri silinmedi):")
            for name in TABLES:
                count = db.session.execute(text(f"SELECT count(*) FROM {name}")).scalar_one()
                print(f"  {name}: {count}")
            db.session.rollback()
            raise SystemExit("Veri silinmedi. Yedek sonrası --confirm ile tekrar çalıştırın.")

        try:
            # Block concurrent finance requests until all ledger/balance changes commit.
            db.session.execute(text(
                "LOCK TABLE " + ", ".join(LOCK_TABLES) + " IN ACCESS EXCLUSIVE MODE"
            ))
            counts = {
                name: db.session.execute(text(f"SELECT count(*) FROM {name}")).scalar_one()
                for name in TABLES
            }

            for name in TABLES:
                db.session.execute(text(f"DELETE FROM {name}"))
            db.session.query(FinansHesap).update(
                {FinansHesap.bakiye: 0}, synchronize_session=False
            )
            db.session.query(FinansCari).update(
                {FinansCari.bakiye: 0}, synchronize_session=False
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        print("Finans hareketleri temizlendi.")
        for name, count in counts.items():
            print(f"  {name}: {count} kayıt silindi")
        print("  finans_hesap ve finans_cari bakiyeleri: 0")
        print("Cari hesaplar ile hesap/kategori/gider tanımları korundu.")
        print("Eski kasa (/kasa) tablolarına dokunulmadı.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm", action="store_true",
        help="Finans hareketlerini kalıcı olarak silmeyi onaylar (önce yedek alın)."
    )
    args = parser.parse_args()
    reset(confirm=args.confirm)


if __name__ == "__main__":
    main()
