"""Shopify'da artık var olmayan ShopifyMapping kayıtlarını siler.

Önce diagnose_stale_shopify_mappings.py çalıştırın.
Bu script, stale (>2 gün sync olmamış) mapping'lerden Shopify GraphQL
nodes(...) sorgusuyla dönmeyenleri (= silinmiş InventoryItem) DB'den siler.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("DISABLE_JOBS", "1")

from app import app
from models import db, ShopifyMapping
from shopify_site.shopify_stock_service import shopify_stock_service

STALE_DAYS = 2
CHUNK = 50

NODES_QUERY = """
query CheckItems($ids: [ID!]!) {
  nodes(ids: $ids) { __typename ... on InventoryItem { id } }
}
"""


def main() -> int:
    with app.app_context():
        cutoff = datetime.utcnow() - timedelta(days=STALE_DAYS)
        stale = ShopifyMapping.query.filter(
            (ShopifyMapping.last_sync_at.is_(None)) | (ShopifyMapping.last_sync_at < cutoff)
        ).all()
        print(f"Stale mapping (>{STALE_DAYS} gün): {len(stale)}")

        inv_ids = [m.shopify_inventory_item_id for m in stale if m.shopify_inventory_item_id]
        alive: set = set()
        for i in range(0, len(inv_ids), CHUNK):
            chunk = inv_ids[i:i + CHUNK]
            try:
                data = shopify_stock_service._graphql(NODES_QUERY, {"ids": chunk})
            except Exception as exc:
                print(f"!! GraphQL hata: {exc} — bu chunk'ı atlıyorum (güvenli taraf)")
                # Hata durumunda silmeyi atla
                for gid in chunk:
                    alive.add(gid)
                continue
            for node in (data.get("nodes") or []):
                if node and node.get("id"):
                    alive.add(node["id"])

        # Shopify'da olmayan = silinmeli
        to_delete = [m for m in stale if m.shopify_inventory_item_id and m.shopify_inventory_item_id not in alive]
        print(f"Silinecek (Shopify'da yok): {len(to_delete)}")

        if not to_delete:
            print("Silinecek bir şey yok.")
            return 0

        print("\nSilinecek barkodlar:")
        for m in to_delete:
            print(f"  {m.barcode}  (last_sync={m.last_sync_at})")

        # SİL
        for m in to_delete:
            db.session.delete(m)
        db.session.commit()
        print(f"\n✅ {len(to_delete)} mapping silindi.")
        print("   Bu barkodlar bir sonraki 'Barkod Eşleştir' işleminde Shopify'da varsa yeniden eşlenecek.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
