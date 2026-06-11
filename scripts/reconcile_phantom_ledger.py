#!/usr/bin/env python3
"""HAYALET STOK RECONCILE — ledger sonrası kargolanıp düşülmemiş siparişleri düzeltir.

`verify_no_phantom_ledger.py` ile AYNI bağımsız kriterle hayaletleri taze tespit
eder (sabit liste YOK): ledger başlangıcından sonra Shipped/Delivered olmuş ama
ledger'da fiziksel çıkışı (pack_out/ship_out, delta<0) OLMAYAN siparişler.

Her hayalet sipariş için details'teki barkod×adet kadar `ship_out` hareketi yazar
(mutate_shelf=True → rafı ve central'ı gerçekten düşürür, kanıtlanmış
allocate_from_shelf_and_decrement yoluyla). reason=ship_out seçilir ki hem
semantik doğru (mal kargolandı) hem de watchdog sonradan PASS versin.

GÜVENLİK:
  - VARSAYILAN --dry-run: hiçbir yazma yapmaz, ne olacağını gösterir.
  - --confirm: gerçek yazma.
  - idempotency_key = "{order}:reconcile:{barcode}:ship_out" → İKİ KEZ çalışsa bile
    raf bir kez düşer (çift düşüm imkânsız).

    DISABLE_JOBS=1 python scripts/reconcile_phantom_ledger.py            # dry-run
    DISABLE_JOBS=1 python scripts/reconcile_phantom_ledger.py --confirm  # uygula
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")


def _parse_details(details) -> list[dict]:
    if not details:
        return []
    try:
        det = json.loads(details) if isinstance(details, str) else details
    except (ValueError, TypeError):
        return []
    return det if isinstance(det, list) else []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", help="Gerçek yazma (yoksa dry-run).")
    ap.add_argument("--since", help="Ledger başlangıcını elle ver (YYYY-MM-DD).")
    args = ap.parse_args()

    from app import app
    from models import db, OrderShipped, OrderDelivered, StockMovement, CentralStock
    from stock_ledger import record_movement, REASON_SHIP_OUT

    with app.app_context():
        # Ledger başlangıcı (self-calibrating)
        if args.since:
            ledger_start = datetime.strptime(args.since, "%Y-%m-%d")
        else:
            first = (db.session.query(StockMovement.created_at)
                     .order_by(StockMovement.created_at.asc()).first())
            if not first or not first[0]:
                print("Ledger boş — reconcile yapılamıyor."); sys.exit(2)
            ledger_start = datetime(first[0].year, first[0].month, first[0].day)

        out_orders = set(
            on for (on,) in db.session.query(StockMovement.order_number)
            .filter(StockMovement.reason.in_(("pack_out", "ship_out")),
                    StockMovement.delta < 0).distinct().all() if on
        )

        # Hayalet siparişleri taze tespit et
        targets: list[tuple[str, str, list[dict]]] = []  # (order, label, items)
        for model, label in ((OrderShipped, "Shipped"), (OrderDelivered, "Delivered")):
            for o in model.query.all():
                od = getattr(o, "order_date", None)
                if od and od < ledger_start:
                    continue
                on = str(o.order_number)
                if on in out_orders:
                    continue
                items = _parse_details(getattr(o, "details", None))
                if not items:
                    bc = getattr(o, "product_barcode", None)
                    if bc:
                        items = [{"barcode": bc, "quantity": 1}]
                if items:
                    targets.append((on, label, items))

        mode = "UYGULA (--confirm)" if args.confirm else "DRY-RUN (yazma yok)"
        print("=" * 76)
        print(f"  HAYALET RECONCILE — {mode}")
        print(f"  Ledger başlangıcı: {ledger_start.date()} | Hedef sipariş: {len(targets)}")
        print("=" * 76)

        if not targets:
            print("  ✅ Düzeltilecek hayalet yok.")
            return

        planned = 0
        applied = 0
        for on, label, items in targets:
            print(f"\n  {on} [{label}]")
            for it in items:
                bc = it.get("barcode")
                qty = int(it.get("quantity") or 1)
                if not bc or qty <= 0:
                    continue
                cs = db.session.get(CentralStock, bc)
                central = getattr(cs, "qty", 0) if cs else 0
                idem = f"{on}:reconcile:{bc}:ship_out"
                exists = db.session.query(StockMovement.id).filter(
                    StockMovement.idempotency_key == idem).first() is not None
                tag = " (zaten yapılmış, atlanır)" if exists else ""
                print(f"     - {bc} ×{qty} | central {central} → {max(0, central - qty)}{tag}")
                planned += qty

                if args.confirm and not exists:
                    res = record_movement(
                        barcode=bc, delta=-qty, reason=REASON_SHIP_OUT,
                        order_number=on, idempotency_key=idem,
                        source="RECONCILE",
                        note=f"2026-06-11 hayalet düzeltme ({label}, kargolandı düşülmedi)",
                        mutate_shelf=True, commit=True,
                    )
                    if res.applied:
                        applied += -res.delta
                        if -res.delta < qty:
                            print(f"       ⚠ kısmi: rafta yeterli yok, {-res.delta} düşüldü")
                    else:
                        print("       ⚠ uygulanmadı (idempotent/yetersiz)")

        print("\n" + "=" * 76)
        if args.confirm:
            print(f"  ✅ UYGULANDI — toplam {applied} adet düşüldü.")
            print("  Doğrulama: scripts/verify_no_phantom_ledger.py (PASS bekleniyor)")
        else:
            print(f"  DRY-RUN — {planned} adet düşülecek. Uygulamak için: --confirm")
        print("=" * 76)


if __name__ == "__main__":
    main()
