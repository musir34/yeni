"""Genel Shopify stok sync sağlığını kontrol eder."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from models import db, ShopifyMapping, CentralStock
from sqlalchemy import func


def main() -> int:
    with app.app_context():
        total = ShopifyMapping.query.count()
        synced = ShopifyMapping.query.filter(ShopifyMapping.last_sync_at.isnot(None)).count()
        never = total - synced

        latest = ShopifyMapping.query.order_by(ShopifyMapping.last_sync_at.desc().nullslast()).first()
        oldest = ShopifyMapping.query.filter(ShopifyMapping.last_sync_at.isnot(None)).order_by(ShopifyMapping.last_sync_at.asc()).first()

        print(f"Toplam mapping: {total}")
        print(f"Hiç sync edilmemiş: {never}")
        print(f"En son sync: {latest.last_sync_at if latest else 'N/A'}")
        print(f"En eski sync: {oldest.last_sync_at if oldest else 'N/A'}")

        # Dağılım: son 1 gün, 3 gün, 7 gün, daha eski
        now = datetime.utcnow()
        buckets = [("<1 gün", 1), ("<3 gün", 3), ("<7 gün", 7), ("<14 gün", 14), ("<30 gün", 30)]
        for label, days in buckets:
            cutoff = now - timedelta(days=days)
            n = ShopifyMapping.query.filter(ShopifyMapping.last_sync_at >= cutoff).count()
            print(f"  {label}: {n}")

        # Stok tutarsızlıkları: CentralStock.qty != last_stock_sent
        print("\n=== Tutarsızlıklar (panel stok ≠ Shopify'a son gönderilen) ===")
        q = db.session.query(ShopifyMapping, CentralStock).outerjoin(
            CentralStock, CentralStock.barcode == ShopifyMapping.barcode
        ).all()
        mismatches = []
        for m, cs in q:
            panel_qty = cs.qty if cs else 0
            sent = m.last_stock_sent if m.last_stock_sent is not None else -1
            if panel_qty != sent:
                mismatches.append((m.barcode, panel_qty, sent, m.last_sync_at))
        print(f"Tutarsız sayısı: {len(mismatches)} / {total}")
        print("İlk 20 örnek (barcode, panel_qty, last_sent, last_sync_at):")
        for row in mismatches[:20]:
            print(f"  {row}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
