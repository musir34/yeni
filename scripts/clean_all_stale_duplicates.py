"""Aynı barkodda birden çok mapping varsa, Shopify'da bulunmayan inventory item'lara
ait stale kayıtları topluca sil. Live olanı bırak."""
from __future__ import annotations

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from models import db, ShopifyMapping
from shopify_site.shopify_stock_service import shopify_stock_service


def main() -> int:
    with app.app_context():
        # Aynı barkod için >1 mapping olanları topla
        groups: dict[str, list[ShopifyMapping]] = defaultdict(list)
        for m in ShopifyMapping.query.all():
            groups[m.barcode].append(m)

        dups = {bc: ms for bc, ms in groups.items() if len(ms) > 1}
        print(f"Duplicate barkod sayısı: {len(dups)}")
        if not dups:
            return 0

        check_q = "query($id: ID!) { inventoryItem(id: $id) { id } }"
        deleted = 0
        kept_all_live = 0

        for bc, ms in dups.items():
            statuses = []  # [(mapping, is_live)]
            for m in ms:
                try:
                    data = shopify_stock_service._graphql(check_q, {"id": m.shopify_inventory_item_id})
                    is_live = bool((data.get("inventoryItem") or {}).get("id"))
                except Exception:
                    is_live = True  # API hatasında temkinli ol — silme
                statuses.append((m, is_live))

            live = [m for m, ok in statuses if ok]
            stale = [m for m, ok in statuses if not ok]

            if not live:
                # Hepsi stale — hiçbirini silme (tek live yok, biri zorunlu lazım)
                continue
            if not stale:
                kept_all_live += 1
                continue

            for m in stale:
                print(f"  [SİL] {bc}  inv_id={m.shopify_inventory_item_id}  last_sync={m.last_sync_at}")
                db.session.delete(m)
                deleted += 1

        db.session.commit()
        print(f"\nToplam silinen stale duplicate: {deleted}")
        print(f"Hepsi live olan duplicate (dokunulmadı): {kept_all_live}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
