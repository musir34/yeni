"""Hatice Göker siparişindeki ürünlerin raf konumlarını kontrol eder."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app  # Flask context for DB
from models import db, Product, RafUrun, ShopifyMapping
from barcode_alias_helper import normalize_barcode
from shopify_site.shopify_service import ShopifyService


def resolve_panel_barcode(variant_barcode: str | None, sku: str | None) -> str | None:
    if variant_barcode:
        p = Product.query.filter_by(barcode=normalize_barcode(variant_barcode)).first()
        if p:
            return p.barcode
    if sku:
        m = ShopifyMapping.query.filter_by(shopify_sku=sku).first()
        if m:
            return m.barcode
    if variant_barcode:
        m = ShopifyMapping.query.filter_by(shopify_barcode=variant_barcode).first()
        if m:
            return m.barcode
    return variant_barcode or None


def shelf_for(barcode: str) -> list[tuple[str, int]]:
    rows = RafUrun.query.filter_by(urun_barkodu=barcode).all()
    return [(r.raf_kodu, r.adet) for r in rows]


def main() -> int:
    svc = ShopifyService()
    if not svc.is_configured():
        print("HATA: Shopify yapılandırılmamış")
        return 1

    queries = [
        "customer:Hatice Göker",
        "customer:'Hatice Göker'",
        "name:Hatice Göker",
        "Hatice Göker",
        "Hatice Goker",
        "last_name:Göker",
        "last_name:Goker",
    ]

    order = None
    for q in queries:
        res = svc.get_orders(limit=10, query_filter=q)
        if not res.get("success"):
            print(f"[{q}] sorgu hata: {res.get('error')}")
            continue
        for o in res.get("orders", []):
            cust = o.get("customer") or {}
            ship = o.get("shippingAddress") or {}
            full = f"{cust.get('firstName','')} {cust.get('lastName','')}".strip().lower()
            ship_name = (ship.get("name") or "").strip().lower()
            if "hatice" in full and ("göker" in full or "goker" in full):
                order = o
                break
            if "hatice" in ship_name and ("göker" in ship_name or "goker" in ship_name):
                order = o
                break
        if order:
            break

    if not order:
        print("Hatice Göker adına sipariş bulunamadı.")
        return 2

    cust = order.get("customer") or {}
    ship = order.get("shippingAddress") or {}
    print(f"Sipariş: {order.get('name')}  (id={order.get('legacyResourceId')})")
    print(f"Müşteri: {cust.get('firstName')} {cust.get('lastName')}  |  Teslim: {ship.get('name')} - {ship.get('city')}")
    print(f"Durum: {order.get('displayFinancialStatus')} / {order.get('displayFulfillmentStatus')}")
    print(f"Oluşturulma: {order.get('createdAt')}")
    print("-" * 80)

    with app.app_context():
        for li in order.get("line_items", []):
            v = li.get("variant") or {}
            vbc = v.get("barcode")
            sku = li.get("sku")
            panel_bc = resolve_panel_barcode(vbc, sku)
            qty = li.get("quantity")
            title = li.get("title")
            shelves = shelf_for(panel_bc) if panel_bc else []
            if shelves:
                loc = ", ".join(f"{k} ({a} adet)" for k, a in shelves)
            else:
                loc = "RAF YOK"
            print(f"• {qty}x {title}")
            print(f"    SKU: {sku}  Shopify barkod: {vbc}  Panel barkod: {panel_bc}")
            print(f"    Raf: {loc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
