#!/usr/bin/env python3
"""BAĞIMSIZ HAYALET-STOK TEYİT/WATCHDOG — SALT OKUNUR (hiçbir yazma yapmaz).

`measure_phantom_stock.py`'den BAĞIMSIZ bir ikinci doğrulama. O script sinyal
olarak AUDIT eventlerini (order_picked/stock_decremented) kullanır; bu script ise
STOK HAREKET DEFTERİNİ (StockMovement pack_out/ship_out) kullanır. İki ayrı veri
kaynağı aynı invariant'ı doğruladığında güven yükselir.

İNVARİANT (güvenlik ağı fix'inin garantisi):
    Ledger devreye girdikten SONRA kargolanan/teslim olan HER sipariş için
    ledger'da en az bir fiziksel çıkış (pack_out veya ship_out, delta<0) olmalı.
    Yoksa = sipariş fiziksel düşülmeden gitmiş = HAYALET STOK.

SELF-CALIBRATING: Ledger başlangıç tarihini otomatik tespit eder
(min(StockMovement.created_at)); öncesinde kargolanmış siparişlerde ledger kaydı
beklenmez, yanlış-pozitif olmaması için onlar değerlendirme dışı bırakılır.
`--since YYYY-MM-DD` ile elle geçersiz kılınabilir.

ÇIKTI: PASS/FAIL + sipariş/barkod kırılımı. Hayalet varsa exit code 1 (cron/
watchdog için). `--out dosya.txt` ile rapor dosyaya da yazılır.

    DISABLE_JOBS=1 python scripts/verify_no_phantom_ledger.py
    DISABLE_JOBS=1 python scripts/verify_no_phantom_ledger.py --since 2026-06-09
    DISABLE_JOBS=1 python scripts/verify_no_phantom_ledger.py --out /tmp/phantom_rapor.txt
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
    ap.add_argument("--since", help="Bu tarihten (YYYY-MM-DD) sonraki siparişler. "
                                    "Verilmezse ledger başlangıcı otomatik bulunur.")
    ap.add_argument("--out", help="Raporu bu dosyaya da yaz (UTF-8).")
    args = ap.parse_args()

    from app import app
    from models import (
        db, OrderShipped, OrderDelivered, OrderAuditLog, StockMovement, CentralStock,
    )

    lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    with app.app_context():
        # 1) Ledger başlangıcını tespit et (self-calibrating)
        if args.since:
            try:
                ledger_start = datetime.strptime(args.since, "%Y-%m-%d")
            except ValueError:
                print(f"Geçersiz --since: {args.since} (YYYY-MM-DD)")
                sys.exit(2)
            src = "elle (--since)"
        else:
            first = (db.session.query(StockMovement.created_at)
                     .order_by(StockMovement.created_at.asc()).first())
            if not first or not first[0]:
                print("Ledger'da hiç hareket yok — doğrulama yapılamıyor.")
                sys.exit(2)
            ledger_start = datetime(first[0].year, first[0].month, first[0].day)
            src = f"otomatik (ilk ledger hareketi: {first[0]})"

        # 2) Ledger'da fiziksel çıkışı (pack_out/ship_out, delta<0) olan sipariş no'ları
        out_orders = set(
            on for (on,) in db.session.query(StockMovement.order_number)
            .filter(StockMovement.reason.in_(("pack_out", "ship_out")),
                    StockMovement.delta < 0)
            .distinct().all()
            if on
        )

        # 3) Çapraz kontrol için: audit'te pick event'i olan sipariş no'ları
        picked_audit = set(
            on for (on,) in db.session.query(OrderAuditLog.order_number)
            .filter(OrderAuditLog.event_type.in_(("order_picked", "stock_decremented")))
            .distinct().all()
            if on
        )

        # 4) Shipped + Delivered tara
        phantom_units = defaultdict(int)
        phantom_orders: list[tuple[str, str, int, bool]] = []  # (order, barkodlar, adet, audit_var)
        evaluated = 0
        skipped_old = 0

        for model, label in ((OrderShipped, "Shipped"), (OrderDelivered, "Delivered")):
            for o in model.query.all():
                od = getattr(o, "order_date", None)
                if od and od < ledger_start:
                    skipped_old += 1
                    continue
                on = str(o.order_number)
                evaluated += 1
                if on in out_orders:
                    continue  # ledger çıkışı var → sağlam
                # Ledger çıkışı YOK → hayalet şüphesi
                items = _parse_details(getattr(o, "details", None))
                bcs = []
                qty_sum = 0
                if items:
                    for it in items:
                        bc = it.get("barcode")
                        q = int(it.get("quantity") or 1)
                        if bc and q > 0:
                            phantom_units[bc] += q
                            bcs.append(f"{bc}×{q}")
                            qty_sum += q
                else:
                    bc = getattr(o, "product_barcode", None)
                    if bc:
                        phantom_units[bc] += 1
                        bcs.append(f"{bc}×1")
                        qty_sum += 1
                phantom_orders.append((f"{on}[{label}]", ", ".join(bcs) or "-",
                                       qty_sum, on in picked_audit))

        # 5) Rapor
        emit("=" * 76)
        emit("  BAĞIMSIZ HAYALET-STOK TEYİDİ (ledger tabanlı, salt okunur)")
        emit(f"  Çalışma zamanı       : {datetime.utcnow()} UTC")
        emit(f"  Ledger başlangıcı    : {ledger_start.date()}  [{src}]")
        emit(f"  Değerlendirilen sipariş (Shipped+Delivered, >= başlangıç): {evaluated}")
        emit(f"  Değerlendirme dışı (ledger öncesi eski): {skipped_old}")
        emit("=" * 76)

        if not phantom_orders:
            emit("")
            emit("  ✅ PASS — Ledger sonrası kargolanan TÜM siparişlerin fiziksel")
            emit("           çıkışı (pack_out/ship_out) var. Hayalet stok YOK.")
            emit("")
            _maybe_write(args.out, lines)
            sys.exit(0)

        emit("")
        emit(f"  ❌ FAIL — {len(phantom_orders)} sipariş ledger çıkışı OLMADAN kargolanmış:")
        emit("")
        emit(f"  {'SİPARİŞ':<22} {'BARKOD×ADET':<34} {'ADET':>5} {'AUDIT':>6}")
        emit("  " + "-" * 72)
        for on, bcs, q, aud in phantom_orders:
            emit(f"  {on:<22} {bcs:<34} {q:>5} {'pick✓' if aud else 'YOK':>6}")

        emit("")
        emit("  BARKOD BAZLI HAYALET ADET vs CENTRAL:")
        emit("  " + "-" * 72)
        emit(f"  {'BARKOD':<28} {'HAYALET':>8} {'CENTRAL':>8}")
        total = 0
        for bc, q in sorted(phantom_units.items(), key=lambda kv: kv[1], reverse=True):
            cs = db.session.get(CentralStock, bc)
            central = getattr(cs, "qty", 0) if cs else 0
            emit(f"  {bc:<28} {q:>8} {central:>8}")
            total += q
        emit("  " + "-" * 72)
        emit(f"  TOPLAM hayalet adet: {total}  ({len(phantom_units)} barkod)")
        emit("")
        emit("  NOT: 'AUDIT=pick✓' → audit'te toplama izi var ama ledger çıkışı yok")
        emit("       (loglama/ledger uyumsuzluğu). 'AUDIT=YOK' → hiç düşülmemiş = tam hayalet.")
        emit("  Düzeltme: fiziksel sayım + reconcile (bu script SALT OKUNUR, yazmaz).")
        emit("")
        _maybe_write(args.out, lines)
        sys.exit(1)


def _maybe_write(out_path: str | None, lines: list[str]) -> None:
    if out_path:
        Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n[rapor yazıldı: {out_path}]")


if __name__ == "__main__":
    main()
