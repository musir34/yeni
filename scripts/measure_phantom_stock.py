#!/usr/bin/env python3
"""Hayalet stok ÖLÇÜM scripti — SALT OKUNUR (hiçbir yazma yapmaz).

Amaç
----
Kronik hayalet stoğun kaynağını sayısallaştırmak: paketlemeden (Picking) geçmeden
Shipped/Delivered olmuş — yani fiziksel stok düşümü HİÇ yapılmamış — siparişleri
bulur ve bunların barkod×adet toplamını "tahmini hayalet stok" olarak raporlar.

Yöntem
------
OrderShipped + OrderDelivered tablolarındaki her sipariş için OrderAuditLog'a bakar:
eğer o sipariş için bir `order_picked` veya `stock_decremented` (paketleme) event'i
YOKSA → o sipariş bizim paketleme akışımızdan geçmeden kargolanmış → fiziksel stoğu
hiç düşülmemiş → details'teki barkod×adet hayalet stoğa katkıdır.

ÖNEMLİ kısıt: barkod-bazlı audit izlemesi 2026-05-08'de başladı. Öncesi için pick
event'i bulunamayacağından yanlış-pozitif olur. Bu yüzden varsayılan olarak yalnızca
`--since` (varsayılan 2026-05-08) tarihinden sonraki siparişler değerlendirilir.

Çalıştırma
----------
    DISABLE_JOBS=1 python scripts/measure_phantom_stock.py
    DISABLE_JOBS=1 python scripts/measure_phantom_stock.py --since 2026-05-08
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")

AUDIT_START = "2026-05-08"  # barkod-bazlı audit izleme başlangıcı


def _parse_details(details):
    if not details:
        return []
    try:
        det = json.loads(details) if isinstance(details, str) else details
    except (ValueError, TypeError):
        return []
    return det if isinstance(det, list) else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=AUDIT_START,
                    help=f"Bu tarihten (YYYY-MM-DD) sonraki siparişler (varsayılan {AUDIT_START})")
    args = ap.parse_args()
    try:
        since = datetime.strptime(args.since, "%Y-%m-%d")
    except ValueError:
        print(f"Geçersiz --since: {args.since} (YYYY-MM-DD bekleniyor)")
        sys.exit(1)

    from app import app  # gerçek app + DATABASE_URL
    from models import OrderShipped, OrderDelivered, OrderAuditLog, CentralStock

    with app.app_context():
        # Paketleme (pick/decrement) event'i olan sipariş numaraları
        picked = set(
            on for (on,) in OrderAuditLog.query
            .with_entities(OrderAuditLog.order_number)
            .filter(OrderAuditLog.event_type.in_(("order_picked", "stock_decremented")))
            .distinct().all()
            if on
        )

        phantom = defaultdict(int)
        affected_orders = defaultdict(set)
        total_orders = 0
        skipped_old = 0

        for model in (OrderShipped, OrderDelivered):
            for o in model.query.all():
                od = getattr(o, "order_date", None)
                if od and od < since:
                    skipped_old += 1
                    continue
                on = o.order_number
                if on in picked:
                    continue  # düzgün paketlenmiş → hayalet değil
                total_orders += 1
                for it in _parse_details(getattr(o, "details", None)):
                    bc = it.get("barcode")
                    qty = int(it.get("quantity") or 1)
                    if bc and qty > 0:
                        phantom[bc] += qty
                        affected_orders[bc].add(on)

        # Rapor
        print("=" * 72)
        print("HAYALET STOK ÖLÇÜM RAPORU (salt okunur)")
        print(f"Değerlendirilen sipariş tarihi >= {args.since}")
        print(f"Paketlemesiz Shipped/Delivered sipariş sayısı: {total_orders}")
        print(f"(audit öncesi atlanan eski sipariş: {skipped_old})")
        print("=" * 72)
        if not phantom:
            print("Tahmini hayalet stok bulunamadı. ✅")
            return

        rows = sorted(phantom.items(), key=lambda kv: kv[1], reverse=True)
        print(f"{'BARKOD':<28} {'HAYALET':>8} {'CENTRAL':>8} {'SİPARİŞ':>8}")
        print("-" * 72)
        total_phantom = 0
        for bc, qty in rows:
            cs = CentralStock.query.get(bc)
            central = cs.qty if cs else 0
            print(f"{bc:<28} {qty:>8} {central:>8} {len(affected_orders[bc]):>8}")
            total_phantom += qty
        print("-" * 72)
        print(f"TOPLAM tahmini hayalet adet: {total_phantom} "
              f"({len(phantom)} barkod)")
        print("\nNOT: Bu bir TAHMİNDİR. Kesin düzeltme için backfill scriptini "
              "--dry-run ile çalıştırıp fiziksel sayımla karşılaştırın.")


if __name__ == "__main__":
    main()
