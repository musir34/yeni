"""730734501 için neden sync düzeltmiyor — tam tanı."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from models import db, Product, CentralStock, RafUrun, ShopifyMapping
from shopify_site.shopify_stock_service import shopify_stock_service

BC = "730734501"


def main() -> int:
    with app.app_context():
        print(f"=== PANEL ({BC}) ===")
        p = Product.query.filter_by(barcode=BC).first()
        cs = CentralStock.query.filter_by(barcode=BC).first()
        rafs = RafUrun.query.filter_by(urun_barkodu=BC).all()
        print(f"Product.quantity: {p.quantity if p else 'YOK'}")
        print(f"CentralStock.qty: {cs.qty if cs else 'YOK'}")
        print(f"Raf: {[(r.raf_kodu, r.adet) for r in rafs] or 'YOK'}")

        ms = ShopifyMapping.query.filter_by(barcode=BC).all()
        print(f"\n=== MAPPING ({len(ms)} kayıt) ===")
        for m in ms:
            print(f"  variant_id={m.shopify_variant_id}")
            print(f"  inventory_item_id={m.shopify_inventory_item_id}")
            print(f"  last_stock_sent={m.last_stock_sent}  last_sync_at={m.last_sync_at}")
            print(f"  shopify_sku={m.shopify_sku}  shopify_barcode={m.shopify_barcode}")

        for m in ms:
            print(f"\n=== CANLI SHOPIFY ({m.shopify_inventory_item_id}) ===")
            q = """
            query($id: ID!) {
              inventoryItem(id: $id) {
                id tracked
                variant { id sku barcode title product { title id status } }
                inventoryLevels(first: 10) {
                  edges { node {
                    location { id name isActive }
                    quantities(names:["available","on_hand","committed","reserved","incoming"]){name quantity}
                  } }
                }
              }
            }"""
            try:
                data = shopify_stock_service._graphql(q, {"id": m.shopify_inventory_item_id})
                inv = data.get("inventoryItem")
                if not inv:
                    print("  [!] Inventory item Shopify'da yok (silinmiş)")
                    continue
                print(f"  tracked: {inv.get('tracked')}")
                v = inv.get("variant") or {}
                p2 = v.get("product") or {}
                print(f"  variant: sku={v.get('sku')}  barcode={v.get('barcode')}  title={v.get('title')}")
                print(f"  product: {p2.get('title')}  status={p2.get('status')}")
                for edge in (inv.get("inventoryLevels") or {}).get("edges", []):
                    node = edge["node"]
                    loc = node["location"]
                    qs = {q["name"]: q["quantity"] for q in node["quantities"]}
                    print(f"  Lokasyon {loc['name']} (active={loc.get('isActive')}): {qs}")
            except Exception as exc:
                print(f"  [HATA] {exc}")

        # Mapping'i kullanan tek barcode push deneyelim
        print(f"\n=== TEK BARCODE PUSH DENEMESİ ===")
        result = shopify_stock_service.push_stock(barcodes=[BC])
        print(f"  result: {result}")

        db.session.expire_all()
        for m in ShopifyMapping.query.filter_by(barcode=BC).all():
            print(f"  PUSH SONRASI last_stock_sent={m.last_stock_sent}  last_sync_at={m.last_sync_at}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
