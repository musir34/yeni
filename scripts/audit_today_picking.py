#!/usr/bin/env python3
"""BUGÜN Hazırlanıyor → İşleme Alındı (Picking) geçen siparişlerin DENETİMİ — SALT OKUNUR.

Her sipariş için:
  - Ürün satırları (barkod + adet)
  - Hangi raftan düşülmesi gerekti / düşüldü (StockMovement pack_out)
  - Raf stoğu fiilen düştü mü? (ledger + RafUrun anlık adet)
  - OrderAuditLog order_picked / raf_changed izleri

Hiçbir yazma yapmaz.

Çalıştırma:
    DISABLE_JOBS=1 python scripts/audit_today_picking.py
    DISABLE_JOBS=1 python scripts/audit_today_picking.py --date 2026-06-10
"""
from __future__ import annotations

import argparse
import json
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
    OrderPicking,
    OrderAuditLog,
    StockMovement,
    RafUrun,
    CentralStock,
)

try:
    from barcode_utils import normalize_barcode  # type: ignore
except Exception:  # pragma: no cover
    def normalize_barcode(b):
        return (b or "").strip()


def _parse_barcodes(order) -> list[str]:
    """Sipariş satırındaki ürün barkodlarını çıkar (details JSON → fallback product_barcode)."""
    out: list[str] = []
    raw = getattr(order, "details", None)
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                for it in data:
                    bc = it.get("barcode") or it.get("product_barcode") or it.get("urun_barkodu")
                    qty = int(it.get("quantity") or it.get("adet") or 1)
                    if bc:
                        for _ in range(max(1, qty)):
                            out.append(normalize_barcode(str(bc)))
        except Exception:
            pass
    if not out and getattr(order, "product_barcode", None):
        for seg in str(order.product_barcode).split(","):
            seg = seg.strip()
            if seg:
                out.append(normalize_barcode(seg))
    return out


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

        q = (
            OrderPicking.query
            .filter(OrderPicking.picking_start_time >= day_start)
            .filter(OrderPicking.picking_start_time < day_end)
            .order_by(OrderPicking.picking_start_time.asc())
        )
        orders = q.all()

        print("=" * 78)
        print(f"  BUGÜN İŞLEME ALINAN (Picking) SİPARİŞ DENETİMİ — {day_start.date()} (UTC)")
        print(f"  Toplam sipariş: {len(orders)}")
        print("=" * 78)

        tot_lines = 0
        tot_dropped = 0      # ledger'da pack_out/ship_out hareketi olan satır
        tot_missing = 0      # düşüm hareketi BULUNMAYAN satır (HAYALET RİSKİ)
        problem_orders: list[str] = []

        for idx, o in enumerate(orders, 1):
            on = o.order_number
            barcodes = _parse_barcodes(o)
            src = getattr(o, "source", "?")
            pst = o.picking_start_time

            # Bu siparişe ait stok hareketleri (çıkış: pack_out / ship_out)
            movements = (
                StockMovement.query
                .filter(StockMovement.order_number == on)
                .order_by(StockMovement.created_at.asc())
                .all()
            )
            out_by_bc: dict[str, list] = {}
            for m in movements:
                if m.reason in ("pack_out", "ship_out") and m.delta < 0:
                    out_by_bc.setdefault(m.barcode, []).append(m)

            # order_picked audit izi
            picked_events = (
                OrderAuditLog.query
                .filter(OrderAuditLog.order_number == on)
                .filter(OrderAuditLog.event_type == "order_picked")
                .count()
            )

            print(f"\n[{idx}/{len(orders)}] Sipariş {on}  | kaynak={src} | picking={pst}")
            print(f"      ürün satırı: {len(barcodes)} | order_picked audit: {picked_events}")

            order_has_problem = False
            # Barkod bazında say (aynı barkod x adet için tüketim eşle)
            consumed: dict[str, int] = {}
            for bc in barcodes:
                tot_lines += 1
                outs = out_by_bc.get(bc, [])
                used = consumed.get(bc, 0)
                if used < len(outs):
                    m = outs[used]
                    consumed[bc] = used + 1
                    tot_dropped += 1
                    shelf = m.shelf_code or "(raf yok)"
                    print(f"        ✔ {bc}  →  {m.reason} {m.delta} | raf={shelf} | {m.created_at}")
                else:
                    tot_missing += 1
                    order_has_problem = True
                    # anlık raf durumu (nerede duruyor)
                    rafs = (
                        RafUrun.query
                        .filter(RafUrun.urun_barkodu == bc)
                        .filter(RafUrun.adet > 0)
                        .all()
                    )
                    raf_str = ", ".join(f"{r.raf_kodu}:{r.adet}" for r in rafs) or "HİÇBİR RAFTA YOK"
                    cs = CentralStock.query.filter_by(barcode=bc).first()
                    cs_qty = cs.qty if cs else 0
                    print(f"        �‼ {bc}  →  DÜŞÜM HAREKETİ YOK (hayalet riski) "
                          f"| central={cs_qty} | mevcut raflar: {raf_str}")

            if order_has_problem:
                problem_orders.append(on)

        print("\n" + "=" * 78)
        print("  ÖZET")
        print("-" * 78)
        print(f"  Sipariş sayısı            : {len(orders)}")
        print(f"  Toplam ürün satırı        : {tot_lines}")
        print(f"  Düşümü yapılmış satır     : {tot_dropped}")
        print(f"  Düşümü EKSİK satır        : {tot_missing}")
        if problem_orders:
            print(f"  ⚠ Sorunlu sipariş ({len(problem_orders)}): {', '.join(problem_orders)}")
        else:
            print("  ✅ Tüm satırların stok düşümü deftere işlenmiş — eksik yok.")
        print("=" * 78)


if __name__ == "__main__":
    main()
