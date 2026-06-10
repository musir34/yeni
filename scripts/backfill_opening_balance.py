#!/usr/bin/env python3
"""Stok defteri başlangıç bakiyesi + hayalet stok mutabakatı.

İki aşama:
  1) opening_balance — Mevcut her RafUrun satırı için deftere bir başlangıç
     hareketi yazar (mutate_shelf=False: rafa DOKUNMAZ, sadece ledger'a baz
     nokta koyar). İdempotenttir; tekrar çalışırsa atlar. GÜVENLİ.
  2) reconcile — Hayalet stoğu fiziksel gerçeğe indirir: verilen barkod×adet
     kadar raf stoğunu DÜŞER (reason='reconcile'). YALNIZCA --confirm ile.

Hayalet listesi iki kaynaktan gelebilir:
  - measure_phantom_stock.py tahmini (otomatik, --auto-phantom ile)
  - Operatörün fiziksel sayımından CSV (barkod,düsulecek_adet) (--csv ile) — ÖNERİLEN

GÜVENLİK: Varsayılan --dry-run. Hiçbir şey yazılmaz, yalnızca ne yapılacağı
gösterilir. --confirm vermeden raf stoğu DEĞİŞMEZ. reconcile'ı çalıştırmadan
önce dry-run çıktısını fiziksel sayımla doğrulayın ve DB yedeği alın.

Çalıştırma
----------
    # 1) Sadece başlangıç bakiyesi (güvenli):
    DISABLE_JOBS=1 python scripts/backfill_opening_balance.py --opening --confirm

    # 2) Mutabakat önizleme (yazma yok):
    DISABLE_JOBS=1 python scripts/backfill_opening_balance.py --reconcile --csv duzeltme.csv --dry-run

    # 3) Mutabakatı uygula (fiziksel sayım doğrulandıktan SONRA):
    DISABLE_JOBS=1 python scripts/backfill_opening_balance.py --reconcile --csv duzeltme.csv --confirm
"""
from __future__ import annotations

import argparse
import csv as csvmod
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")


def _load_csv(path):
    """barkod,adet biçimindeki CSV'yi {barcode: qty} olarak yükler."""
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv_rows(f):
            if len(row) < 2:
                continue
            bc = row[0].strip()
            try:
                qty = int(row[1])
            except ValueError:
                continue
            if bc and qty > 0:
                out[bc] = out.get(bc, 0) + qty
    return out


def csv_rows(f):
    reader = csvmod.reader(f)
    for i, row in enumerate(reader):
        if i == 0 and row and not row[1:2] == []:
            # başlık satırını atla (ilk hücre sayı değilse)
            try:
                int(row[1])
            except (ValueError, IndexError):
                continue
        yield row


def run_opening(confirm):
    from models import db, RafUrun
    from stock_ledger import record_movement, REASON_OPENING

    rows = RafUrun.query.filter(RafUrun.adet > 0).all()
    print(f"[OPENING] {len(rows)} RafUrun satırı için başlangıç bakiyesi "
          f"({'UYGULANACAK' if confirm else 'DRY-RUN'})")
    written = 0
    for r in rows:
        if not confirm:
            continue
        res = record_movement(
            barcode=r.urun_barkodu, delta=int(r.adet or 0), reason=REASON_OPENING,
            shelf_code=r.raf_kodu, idempotency_key=f"opening:{r.raf_kodu}:{r.urun_barkodu}",
            source="SYSTEM", note="ledger devreye alma başlangıç bakiyesi",
            mutate_shelf=False, commit=False,
        )
        if res.applied:
            written += 1
    if confirm:
        db.session.commit()
        print(f"[OPENING] {written} başlangıç hareketi yazıldı.")
    else:
        print("[OPENING] --confirm verilmedi, yazma yapılmadı.")


def run_reconcile(phantom, confirm):
    from models import db, RafUrun, CentralStock
    from stock_ledger import record_movement, REASON_RECONCILE

    stamp = datetime.utcnow().strftime("%Y%m%d")
    print(f"[RECONCILE] {len(phantom)} barkod ({'UYGULANACAK' if confirm else 'DRY-RUN'})")
    print(f"{'BARKOD':<28} {'MEVCUT':>8} {'DÜŞ':>6} {'SONRA':>8}")
    print("-" * 60)
    total = 0
    for bc, qty in sorted(phantom.items(), key=lambda kv: kv[1], reverse=True):
        cs = CentralStock.query.get(bc)
        cur = cs.qty if cs else 0
        after = max(0, cur - qty)
        print(f"{bc:<28} {cur:>8} {qty:>6} {after:>8}")
        total += qty
        if confirm:
            record_movement(
                barcode=bc, delta=-qty, reason=REASON_RECONCILE,
                idempotency_key=f"reconcile:{bc}:{stamp}",
                source="SYSTEM", note="hayalet stok mutabakatı",
                mutate_shelf=True, commit=False,
            )
    print("-" * 60)
    print(f"TOPLAM düşülecek: {total} adet")
    if confirm:
        db.session.commit()
        print("[RECONCILE] Uygulandı ve commit edildi.")
    else:
        print("[RECONCILE] DRY-RUN — hiçbir şey yazılmadı. Fiziksel sayımla "
              "doğruladıktan sonra --confirm ile çalıştırın.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--opening", action="store_true", help="Başlangıç bakiyesi yaz")
    ap.add_argument("--reconcile", action="store_true", help="Hayalet stok mutabakatı")
    ap.add_argument("--csv", help="Mutabakat için barkod,adet CSV dosyası")
    ap.add_argument("--auto-phantom", action="store_true",
                    help="Mutabakat miktarını measure_phantom_stock tahmininden al (DİKKAT: tahmin)")
    ap.add_argument("--confirm", action="store_true", help="Gerçekten uygula (yoksa dry-run)")
    args = ap.parse_args()

    if not (args.opening or args.reconcile):
        ap.error("--opening veya --reconcile gerekli")

    from app import app
    with app.app_context():
        if args.opening:
            run_opening(args.confirm)

        if args.reconcile:
            if args.csv:
                phantom = _load_csv(args.csv)
            elif args.auto_phantom:
                print("⚠️  --auto-phantom: measure_phantom_stock tahmini kullanılıyor "
                      "(fiziksel sayım ÖNERİLİR).")
                from scripts.measure_phantom_stock import _parse_details  # noqa
                from models import OrderShipped, OrderDelivered, OrderAuditLog
                picked = set(
                    on for (on,) in OrderAuditLog.query
                    .with_entities(OrderAuditLog.order_number)
                    .filter(OrderAuditLog.event_type.in_(("order_picked", "stock_decremented")))
                    .distinct().all() if on
                )
                from collections import defaultdict
                phantom = defaultdict(int)
                for model in (OrderShipped, OrderDelivered):
                    for o in model.query.all():
                        if o.order_number in picked:
                            continue
                        for it in _parse_details(getattr(o, "details", None)):
                            bc = it.get("barcode"); q = int(it.get("quantity") or 1)
                            if bc and q > 0:
                                phantom[bc] += q
                phantom = dict(phantom)
            else:
                ap.error("--reconcile için --csv veya --auto-phantom gerekli")
            run_reconcile(phantom, args.confirm)


if __name__ == "__main__":
    main()
