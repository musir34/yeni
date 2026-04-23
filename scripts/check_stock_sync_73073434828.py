"""73073434828 barkodu için panel stoğu, raf, mapping ve Shopify envanterini karşılaştır."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from models import db, Product, CentralStock, RafUrun, ShopifyMapping
from stock_sync.service import stock_sync_service
from shopify_site.shopify_stock_service import shopify_stock_service


BARCODE = "73073434828"


def main() -> int:
    with app.app_context():
        print(f"=== PANEL TARAFI ({BARCODE}) ===")
        p = Product.query.filter_by(barcode=BARCODE).first()
        print(f"Product.quantity: {p.quantity if p else 'YOK'}")

        cs = CentralStock.query.filter_by(barcode=BARCODE).first()
        print(f"CentralStock.qty: {cs.qty if cs else 'YOK'}")

        rafs = RafUrun.query.filter_by(urun_barkodu=BARCODE).all()
        print(f"Raf kayıtları: {[(r.raf_kodu, r.adet) for r in rafs] or 'YOK'}")

        reserved = stock_sync_service.get_reserved_barcodes()
        print(f"Bekleyen siparişlerde rezerv: {reserved.get(BARCODE, 0)}")

        m = ShopifyMapping.query.filter_by(barcode=BARCODE).first()
        if m:
            print(f"\n=== SHOPIFY MAPPING ===")
            print(f"variant_id: {m.shopify_variant_id}")
            print(f"inventory_item_id: {m.shopify_inventory_item_id}")
            print(f"sku: {m.shopify_sku}  |  shopify_barcode: {m.shopify_barcode}")
            print(f"last_stock_sent: {m.last_stock_sent}")
            print(f"last_sync_at: {m.last_sync_at}")
        else:
            print("\n[!] Shopify mapping bulunamadı.")
            return 2

        print("\n=== CANLI SHOPIFY ENVANTERİ ===")
        q = """
        query($id: ID!) {
          inventoryItem(id: $id) {
            id
            tracked
            variant { id sku barcode product { title } }
            inventoryLevels(first: 10) {
              edges { node { location { id name } quantities(names: ["available","on_hand","committed","reserved"]) { name quantity } } }
            }
          }
        }
        """
        data = shopify_stock_service._graphql(q, {"id": m.shopify_inventory_item_id})
        inv = data.get("inventoryItem") or {}
        print(f"tracked: {inv.get('tracked')}")
        v = inv.get("variant") or {}
        print(f"variant SKU: {v.get('sku')} | barcode: {v.get('barcode')} | product: {(v.get('product') or {}).get('title')}")
        for edge in (inv.get("inventoryLevels") or {}).get("edges", []):
            node = edge["node"]
            loc = node["location"]["name"]
            qs = {q["name"]: q["quantity"] for q in node["quantities"]}
            print(f"Lokasyon {loc}: {qs}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
