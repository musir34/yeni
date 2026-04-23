"""Shopify'da artık bulunmayan inventory item'lara ait stale mapping'leri temizle."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from models import db, ShopifyMapping
from shopify_site.shopify_stock_service import shopify_stock_service


STALE_BARCODES = [
    "723008581232669",
    "73073433266",
    "730734502",
    "730734503",
    "730734504",
    "730734505",
    "730734506",
    "7307343129",
    "98523709823037",
]


def main() -> int:
    with app.app_context():
        # Shopify üzerinde gerçekten yok mu doğrula, yoksa sil
        mappings = ShopifyMapping.query.filter(ShopifyMapping.barcode.in_(STALE_BARCODES)).all()
        print(f"Adres: {len(mappings)} mapping kontrol edilecek")

        q = """
        query($id: ID!) {
          inventoryItem(id: $id) { id }
        }
        """
        to_delete = []
        for m in mappings:
            try:
                data = shopify_stock_service._graphql(q, {"id": m.shopify_inventory_item_id})
                if not (data.get("inventoryItem") or {}).get("id"):
                    to_delete.append(m)
                    print(f"  [STALE] {m.barcode}  inv_id={m.shopify_inventory_item_id}")
                else:
                    print(f"  [LIVE]  {m.barcode}  hâlâ Shopify'da — silinmiyor")
            except Exception as exc:
                print(f"  [ERR]   {m.barcode}: {exc}")

        if not to_delete:
            print("Temizlenecek stale mapping yok.")
            return 0

        for m in to_delete:
            db.session.delete(m)
        db.session.commit()
        print(f"\nSilinen stale mapping: {len(to_delete)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
