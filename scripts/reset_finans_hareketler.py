#!/usr/bin/env python3
"""Clear finance transaction history and balances; keep accounts and plan setup.

Run from the app directory after confirming a database backup:
    DISABLE_JOBS=1 ../venv/bin/python scripts/reset_finans_hareketler.py            # sayım (silmez)
    DISABLE_JOBS=1 ../venv/bin/python scripts/reset_finans_hareketler.py --confirm  # siler

Only the new /finans module is touched. The legacy /kasa tables are never used.
Employee schedules restart at their next weekly date or next monthly period so
cleared backdated accruals do not immediately appear again.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
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


def _next_employee_period(kalem, today: date) -> tuple[str, date | None]:
    """Advance only the accrual start; keep weekday and existing future starts."""
    from finans_service import donem_kaydir

    next_month = donem_kaydir(today.strftime("%Y-%m"), 1)
    if kalem.siklik == "haftalik":
        first = kalem.ilk_odeme_tarihi
        if first is None:
            raise ValueError(f"Haftalık çalışan planı #{kalem.id} için ilk ödeme tarihi eksik.")
        days = max(0, ((today + timedelta(days=1) - first).days + 6) // 7)
        first = first + timedelta(days=days * 7)
        return max(kalem.baslangic_donem, first.strftime("%Y-%m")), first
    return max(kalem.baslangic_donem, next_month), kalem.ilk_odeme_tarihi


def reset(*, confirm: bool) -> None:
    from app import app
    from models import db, FinansAnaGiderKalem, FinansCari, FinansHesap
    from sqlalchemy import inspect
    from time_utils import to_ist

    with app.app_context():
        engine = db.engine
        if engine.dialect.name != "postgresql":
            raise SystemExit("Sıfırlama yalnızca PostgreSQL finans veritabanında çalışır.")
        present = set(inspect(engine).get_table_names())
        missing = [name for name in TABLES + LOCK_TABLES if name not in present]
        if missing:
            raise SystemExit("Şema eksik; hiçbir kayıt silinmedi. Eksik tablolar: " + ", ".join(sorted(set(missing))))

        today = to_ist(datetime.utcnow()).date()
        if not confirm:
            # Salt okunur sayım: bağlantı ve kapsam doğrulanır, hiçbir kayıt silinmez.
            print("Silinecek kayıtlar (sayım, veri silinmedi):")
            for name in TABLES:
                count = db.session.execute(text(f"SELECT count(*) FROM {name}")).scalar_one()
                print(f"  {name}: {count}")
            plans = (FinansAnaGiderKalem.query
                     .filter(FinansAnaGiderKalem.calisan_cari_id.isnot(None)).count())
            print(f"  ileri alınacak çalışan planı: {plans}")
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

            moved = 0
            for plan in (FinansAnaGiderKalem.query
                         .filter(FinansAnaGiderKalem.calisan_cari_id.isnot(None)).all()):
                plan.baslangic_donem, plan.ilk_odeme_tarihi = _next_employee_period(plan, today)
                moved += 1

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
        print(f"  Çalışan planlarının başlangıcı ileri alındı: {moved}")
        print("Cari hesaplar, hesap/kategori/gider tanımları ve normal ödeme planları korundu.")
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
