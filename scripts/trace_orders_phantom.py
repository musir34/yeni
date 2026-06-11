#!/usr/bin/env python3
"""Belirli siparişler için derin iz sürme — SALT OKUNUR.

Her sipariş için:
  - hangi statü tablosunda (konum)
  - ürün barkod(lar)ı + model/renk/beden
  - StockMovement (ledger) hareketleri
  - OrderAuditLog olayları
  - barkodun ŞU ANKİ raf dağılımı (RafUrun) + central stok

Hiçbir yazma yapmaz.

    DISABLE_JOBS=1 python scripts/trace_orders_phantom.py 11312846987 11312751851 11309996335
"""
from __future__ import annotations

import json
import os
import sys
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
    OrderCreated,
    OrderHazirlaniyor,
    OrderPicking,
    OrderShipped,
    OrderDelivered,
    OrderCancelled,
    RafUrun,
    CentralStock,
    Product,
)

_LOC_TABLES = [
    (OrderCreated, "Created"),
    (OrderHazirlaniyor, "Hazırlanıyor"),
    (OrderPicking, "Picking"),
    (OrderShipped, "Shipped"),
    (OrderDelivered, "Delivered"),
    (OrderCancelled, "Cancelled"),
]


def _locate(on: str):
    rows = []
    for M, name in _LOC_TABLES:
        try:
            r = M.query.filter(M.order_number == on).first()
            if r:
                rows.append((name, r))
        except Exception as e:
            rows.append((name + "(ERR)", None))
    return rows


def _barcodes_for(on: str) -> set[str]:
    bcs: set[str] = set()
    for name, r in _locate(on):
        if r is None:
            continue
        for attr in ("product_barcode", "barcode", "stockCode"):
            v = getattr(r, attr, None)
            if v:
                bcs.add(str(v))
        det = getattr(r, "details", None)
        if det:
            try:
                d = json.loads(det) if isinstance(det, str) else det
                items = d if isinstance(d, list) else d.get("items") or d.get("lines") or []
                for it in items:
                    b = it.get("barcode") or it.get("product_barcode")
                    if b:
                        bcs.add(str(b))
            except Exception:
                pass
    # ledger / audit'ten de topla
    for m in StockMovement.query.filter(StockMovement.order_number == on).all():
        if m.barcode:
            bcs.add(str(m.barcode))
    for a in OrderAuditLog.query.filter(OrderAuditLog.order_number == on).all():
        if a.barcode:
            bcs.add(str(a.barcode))
    return bcs


def _prod_label(bc: str) -> str:
    p = Product.query.filter(Product.barcode == bc).first()
    if not p:
        return "(ürün kaydı yok)"
    model = p.product_main_id or "-"
    parts = [str(model)]
    if p.color:
        parts.append(str(p.color))
    if p.size:
        parts.append(str(p.size))
    return " - ".join(parts)


def main() -> None:
    orders = sys.argv[1:] or ["11312846987", "11312751851", "11309996335"]

    with app.app_context():
        for on in orders:
            print("=" * 84)
            print(f"  SİPARİŞ {on}")
            print("=" * 84)

            locs = _locate(on)
            loc_names = [n for n, r in locs if r is not None]
            print(f"  Konum: {'+'.join(loc_names) or '?? (hiçbir tabloda yok)'}")
            for name, r in locs:
                if r is None:
                    continue
                kargo = getattr(r, "kargo_takip_no", None) or getattr(r, "cargo_tracking_number", None)
                tarih = (getattr(r, "picking_start_time", None) or getattr(r, "toplandi_at", None)
                         or getattr(r, "order_date", None))
                print(f"    - {name}: kargo={kargo} tarih={tarih} "
                      f"toplandi_raf={getattr(r, 'toplandi_raf', None)} "
                      f"atanan_raf={getattr(r, 'atanan_raf', None)}")

            bcs = sorted(_barcodes_for(on))
            print(f"\n  Barkodlar ({len(bcs)}):")
            for bc in bcs:
                print(f"    • {bc}  →  {_prod_label(bc)}")

            print("\n  LEDGER (stock_movement):")
            movs = (StockMovement.query
                    .filter(StockMovement.order_number == on)
                    .order_by(StockMovement.created_at).all())
            if not movs:
                print("    (hiç hareket yok)  ‼ fiziksel düşüm kaydı YOK")
            for m in movs:
                print(f"    {m.created_at} | {m.reason:14s} | bc={m.barcode} | "
                      f"delta={m.delta:+d} | raf={m.shelf_code} | src={m.source} | idem={m.idempotency_key}")

            print("\n  AUDIT (order_audit_logs):")
            auds = (OrderAuditLog.query
                    .filter(OrderAuditLog.order_number == on)
                    .order_by(OrderAuditLog.ts).all())
            if not auds:
                print("    (hiç audit yok)")
            for a in auds:
                print(f"    {a.ts} | {a.event_type:18s} | bc={a.barcode} | raf={a.raf_kodu} "
                      f"| {a.raf_total_before}->{a.raf_total_after} | st {a.status_from}->{a.status_to} "
                      f"| {a.message}")

            print("\n  ŞU ANKİ RAF DAĞILIMI (RafUrun) + central:")
            for bc in bcs:
                rows = RafUrun.query.filter(RafUrun.urun_barkodu == bc).all()
                total = sum(int(x.adet or 0) for x in rows)
                cs = CentralStock.query.filter(CentralStock.barcode == bc).first()
                cq = (getattr(cs, "qty", None) if cs else None)
                shelf_str = ", ".join(f"{x.raf_kodu}:{x.adet}" for x in rows if int(x.adet or 0) != 0) or "(boş)"
                print(f"    • {bc} | raf_toplam={total} | central={cq}")
                print(f"        raflar: {shelf_str}")
            print()


if __name__ == "__main__":
    main()
