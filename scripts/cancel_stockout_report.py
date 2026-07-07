"""Stoksuzluk kaynaklı iptal raporu (salt okunur).

Son N günde en çok iptal edilen ürünleri, güncel stok/raf durumuyla birlikte
listeler. Amaç: hangi modelleri ACİL basman/tedarik etmen gerektiğini görmek ve
listeleme-tamponu politikasını beslemek.

Kullanım (sunucuda):
    python -m scripts.cancel_stockout_report                  # 30 gün, tümü
    python -m scripts.cancel_stockout_report --days 30 --min-cancels 1 --limit 40
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Stoksuzluk iptal raporu (salt okunur)")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--min-cancels", type=int, default=1)
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()

    from app import app
    from sqlalchemy import func
    from models import db, OrderCancelled, Product, CentralStock, RafUrun

    cutoff = datetime.utcnow() - timedelta(days=args.days)

    with app.app_context():
        rows = (
            db.session.query(
                OrderCancelled.product_barcode,
                func.count().label("iptal"),
                func.max(OrderCancelled.order_date).label("son"),
            )
            .filter(
                OrderCancelled.order_date >= cutoff,
                OrderCancelled.product_barcode.isnot(None),
                OrderCancelled.product_barcode != "",
            )
            .group_by(OrderCancelled.product_barcode)
            .having(func.count() >= args.min_cancels)
            .order_by(func.count().desc(), func.max(OrderCancelled.order_date).desc())
            .limit(args.limit)
            .all()
        )

        print(f"=== Son {args.days} gün — en çok iptal edilen ürünler ===")
        print(f"{'barkod':20s} {'iptal':>5s} {'stok':>5s} {'raf':>4s}  {'son':10s}  ürün")
        print("-" * 90)
        for barcode, iptal, son in rows:
            p = Product.query.filter_by(barcode=barcode).first()
            cs = CentralStock.query.get(barcode)
            stok = cs.qty if cs else 0
            rafta = (
                RafUrun.query.filter(
                    RafUrun.urun_barkodu == barcode, RafUrun.adet > 0
                ).first() is not None
            )
            title = ""
            if p:
                title = f"{p.product_main_id or ''} {p.size or ''} {p.color or (p.title or '')[:20]}".strip()
            son_s = son.strftime("%Y-%m-%d") if son else ""
            flag = " ⚠" if stok == 0 else ""
            print(f"{barcode:20s} {iptal:5d} {stok:5d} {'var' if rafta else 'YOK':>4s}  {son_s:10s}  {title}{flag}")

        print(f"\nToplam {len(rows)} ürün listelendi. ⚠ = güncel stok 0 (kronik stoksuz).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
