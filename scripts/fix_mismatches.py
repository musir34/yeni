"""Panel ≠ Shopify son gönderilen olan mapping'leri tespit edip zorla gönderir."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from models import db, ShopifyMapping, CentralStock
from shopify_site.shopify_stock_service import shopify_stock_service


def main() -> int:
    with app.app_context():
        rows = db.session.query(ShopifyMapping, CentralStock).outerjoin(
            CentralStock, CentralStock.barcode == ShopifyMapping.barcode
        ).all()
        mismatches: list[str] = []
        for m, cs in rows:
            panel = cs.qty if cs else 0
            sent = m.last_stock_sent if m.last_stock_sent is not None else -1
            if panel != sent:
                mismatches.append(m.barcode)

        print(f"Tutarsız mapping sayısı: {len(mismatches)}")
        if not mismatches:
            return 0

        result = shopify_stock_service.push_stock(barcodes=mismatches)
        print(f"push_stock sonucu: total={result.get('total')} "
              f"success={result.get('success_count')} error={result.get('error_count')} "
              f"skipped={result.get('skipped_count')}")
        for err in (result.get("errors") or [])[:20]:
            print(f"  ERR: {err}")

        # Tekrar tutarsızlık sayımı
        db.session.expire_all()
        remaining = 0
        rows = db.session.query(ShopifyMapping, CentralStock).outerjoin(
            CentralStock, CentralStock.barcode == ShopifyMapping.barcode
        ).filter(ShopifyMapping.barcode.in_(mismatches)).all()
        still = []
        for m, cs in rows:
            panel = cs.qty if cs else 0
            sent = m.last_stock_sent if m.last_stock_sent is not None else -1
            if panel != sent:
                still.append((m.barcode, panel, sent))
        print(f"\nPush sonrası hâlâ tutarsız: {len(still)}")
        for s in still[:20]:
            print(f"  {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
