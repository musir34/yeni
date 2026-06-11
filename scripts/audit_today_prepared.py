#!/usr/bin/env python3
"""BUGÜN HAZIRLANAN (toplanan) TÜM siparişlerde raf düşümü denetimi — SALT OKUNUR.

İlk versiyondan farkı: yalnızca orders_picking'e değil, statü ne olursa olsun
(Picking / Shipped / Delivered / Cancelled / hâlâ Hazırlanıyor) BUGÜN bir toplama/
düşüm izi olan HER siparişe bakar.

Aday sipariş kaynakları (bugün):
  - OrderAuditLog.event_type in (order_picked, stock_decremented)
  - StockMovement.reason == pack_out
  - OrderHazirlaniyor.toplandi_at (bugün)

Her sipariş için raftan düşüm gerçekleşmiş mi (ledger pack_out + audit stock_decremented)
tek tek doğrular ve uyumsuzları işaretler. Hiçbir yazma yapmaz.

    DISABLE_JOBS=1 python scripts/audit_today_prepared.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")

from app import app  # noqa: E402
from models import (  # noqa: E402
    db,
    OrderAuditLog,
    StockMovement,
    OrderHazirlaniyor,
    OrderCreated,
    OrderPicking,
    OrderShipped,
    OrderDelivered,
    OrderCancelled,
)

_LOC_TABLES = [
    (OrderCreated, "Created"),
    (OrderHazirlaniyor, "Hazırlanıyor"),
    (OrderPicking, "Picking"),
    (OrderShipped, "Shipped"),
    (OrderDelivered, "Delivered"),
    (OrderCancelled, "Cancelled"),
]


def _locate(on: str) -> str:
    locs = []
    for M, name in _LOC_TABLES:
        try:
            if db.session.query(M.id).filter(M.order_number == on).first():
                locs.append(name)
        except Exception:
            pass
    return "+".join(locs) if locs else "?"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (varsayılan: bugün, UTC)")
    args = ap.parse_args()

    with app.app_context():
        if args.date:
            day_start = datetime.strptime(args.date, "%Y-%m-%d")
        else:
            now = datetime.utcnow()
            day_start = datetime(now.year, now.month, now.day)
        day_end = day_start + timedelta(days=1)

        # 1) Aday sipariş numaralarını topla
        cand: set[str] = set()

        picked = (OrderAuditLog.query
                  .filter(OrderAuditLog.ts >= day_start, OrderAuditLog.ts < day_end)
                  .filter(OrderAuditLog.event_type.in_(("order_picked", "stock_decremented")))
                  .all())
        for a in picked:
            if a.order_number:
                cand.add(str(a.order_number))

        movements = (StockMovement.query
                     .filter(StockMovement.created_at >= day_start, StockMovement.created_at < day_end)
                     .filter(StockMovement.reason == "pack_out")
                     .all())
        for m in movements:
            if m.order_number:
                cand.add(str(m.order_number))

        toplananlar = (OrderHazirlaniyor.query
                       .filter(OrderHazirlaniyor.toplandi_at >= day_start,
                               OrderHazirlaniyor.toplandi_at < day_end)
                       .all())
        for o in toplananlar:
            cand.add(str(o.order_number))

        orders = sorted(cand)

        print("=" * 80)
        print(f"  BUGÜN HAZIRLANAN TÜM SİPARİŞLER — RAF DÜŞÜM DENETİMİ — {day_start.date()} (UTC)")
        print(f"  Aday sipariş sayısı: {len(orders)}")
        print(f"  (kaynak: order_picked/stock_decremented audit={len({a.order_number for a in picked})}, "
              f"pack_out ledger={len({m.order_number for m in movements})}, "
              f"toplandi_at={len(toplananlar)})")
        print("=" * 80)

        ok = 0
        problems: list[tuple[str, str]] = []

        for idx, on in enumerate(orders, 1):
            loc = _locate(on)

            packouts = (StockMovement.query
                        .filter(StockMovement.order_number == on,
                                StockMovement.reason.in_(("pack_out", "ship_out")),
                                StockMovement.delta < 0)
                        .all())
            decr_audits = (OrderAuditLog.query
                           .filter(OrderAuditLog.order_number == on,
                                   OrderAuditLog.event_type == "stock_decremented")
                           .all())
            picked_audit = (OrderAuditLog.query
                            .filter(OrderAuditLog.order_number == on,
                                    OrderAuditLog.event_type == "order_picked")
                            .count())

            ledger_qty = sum(-m.delta for m in packouts)
            shelves = ", ".join(sorted({(m.shelf_code or "?") for m in packouts})) or "-"
            audit_shelves = ", ".join(
                f"{a.raf_kodu}({a.raf_total_before}->{a.raf_total_after})"
                for a in decr_audits if a.raf_kodu
            ) or "-"

            status = "OK"
            reason = ""
            if ledger_qty == 0 and not decr_audits:
                status = "‼ DÜŞÜM YOK"
                reason = "ne ledger pack_out ne stock_decremented audit var"
            elif ledger_qty == 0 and decr_audits:
                status = "⚠ LEDGER EKSİK"
                reason = "audit düşmüş ama ledger pack_out yok"
            elif ledger_qty > 0 and not decr_audits:
                status = "⚠ AUDIT EKSİK"
                reason = "ledger pack_out var ama stock_decremented audit yok"

            mark = "✅" if status == "OK" else "❌"
            print(f"\n[{idx}/{len(orders)}] {on}  | konum={loc} | order_picked={picked_audit} {mark}")
            print(f"      ledger pack_out: -{ledger_qty} | raf(ledger): {shelves}")
            print(f"      audit stock_decremented: {len(decr_audits)} | raf(audit): {audit_shelves}")
            if status != "OK":
                print(f"      → {status}: {reason}")
                problems.append((on, status))
            else:
                ok += 1

        print("\n" + "=" * 80)
        print("  ÖZET")
        print("-" * 80)
        print(f"  Toplam hazırlanan sipariş : {len(orders)}")
        print(f"  ✅ Düşümü sağlam          : {ok}")
        print(f"  ❌ Sorunlu                : {len(problems)}")
        for on, st in problems:
            print(f"       - {on}  ({st})")
        if not problems:
            print("  ✅ Bugün hazırlanan TÜM siparişlerde raf düşümü sağlam.")
        print("=" * 80)


if __name__ == "__main__":
    main()
