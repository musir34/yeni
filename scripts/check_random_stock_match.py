# -*- coding: utf-8 -*-
"""Shopify + Trendyol'dan ortak rastgele barkodları al ve CentralStock ile eşleşiyor mu paralel kontrol et."""
from __future__ import annotations

import os
import sys
import random
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from models import CentralStock
from stock_sync.service import stock_sync_service
from stock_sync.adapters.shopify import shopify_adapter
from stock_sync.adapters.trendyol import trendyol_adapter

SAMPLE_SIZE = 20


async def fetch_trendyol_map() -> dict[str, int]:
    """Trendyol barkod -> quantity (guncel integration endpoint)"""
    supplier_id = trendyol_adapter.supplier_id
    url = f"https://api.trendyol.com/integration/product/sellers/{supplier_id}/products"
    headers = {
        "Authorization": f"Basic {trendyol_adapter._auth_header}",
        "Content-Type": "application/json",
        "User-Agent": f"SellerId={supplier_id} - SelfIntegration",
    }
    result: dict[str, int] = {}
    session = await trendyol_adapter.get_session()
    page = 0
    while True:
        params = {"page": page, "size": 200, "approved": "true"}
        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status != 200:
                print(f"[TRENDYOL] HTTP {resp.status}: {(await resp.text())[:200]}")
                break
            data = await resp.json()
        for p in data.get("content", []):
            bc = str(p.get("barcode", "") or "").strip()
            if bc:
                result[bc] = int(p.get("quantity", 0) or 0)
        total_pages = data.get("totalPages", 1)
        if page >= total_pages - 1:
            break
        page += 1
        await asyncio.sleep(0.1)
    await trendyol_adapter.close_session()
    return result


async def fetch_shopify_map() -> dict[str, int]:
    """Shopify barkod -> aktif lokasyondaki available envanter"""
    location_id = await shopify_adapter._ensure_location_id()
    query = """
    query GetVariants($first: Int!, $after: String, $loc: ID!) {
      productVariants(first: $first, after: $after) {
        edges {
          node {
            barcode
            sku
            inventoryItem {
              inventoryLevel(locationId: $loc) {
                quantities(names: ["available"]) { name quantity }
              }
            }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
    """
    result: dict[str, int] = {}
    after = None
    while True:
        data = await shopify_adapter._graphql(query, {"first": 250, "after": after, "loc": location_id})
        block = data["data"].get("productVariants", {})
        for edge in block.get("edges", []):
            node = edge.get("node", {})
            bc = str(node.get("barcode") or "").strip()
            if not bc:
                continue
            inv = (node.get("inventoryItem") or {}).get("inventoryLevel") or {}
            qty = 0
            for q in inv.get("quantities", []) or []:
                if q.get("name") == "available":
                    qty = int(q.get("quantity", 0) or 0)
            result[bc] = qty
        page = block.get("pageInfo", {})
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
        await asyncio.sleep(0.1)
    await shopify_adapter.close_session()
    return result


async def gather_platforms():
    return await asyncio.gather(fetch_shopify_map(), fetch_trendyol_map())


def main() -> int:
    with app.app_context():
        print("Shopify ve Trendyol ürünleri PARALEL çekiliyor...")
        shopify_map, trendyol_map = asyncio.run(gather_platforms())
        print(f"Shopify: {len(shopify_map)} barkod | Trendyol: {len(trendyol_map)} barkod")

        common = sorted(set(shopify_map) & set(trendyol_map))
        print(f"Her iki platformda ortak barkod: {len(common)}")
        if not common:
            print("Ortak barkod bulunamadi.")
            return 1

        sample = random.sample(common, min(SAMPLE_SIZE, len(common)))

        cs_rows = CentralStock.query.filter(CentralStock.barcode.in_(sample)).all()
        cs_map = {c.barcode: c.qty for c in cs_rows}
        reserved = stock_sync_service.get_reserved_barcodes()

        print(f"\n=== RASTGELE {len(sample)} BARKOD KONTROLU ===\n")
        header = f"{'BARKOD':<16}{'MERKEZ':>8}{'REZERV':>8}{'BEKLNN':>8}{'SHOPIFY':>9}{'TRENDYOL':>10}  DURUM"
        print(header)
        print("-" * len(header))

        mismatch = 0
        for bc in sample:
            central = cs_map.get(bc, 0)
            rez = reserved.get(bc, 0)
            expected = max(0, central - rez)
            sh = shopify_map.get(bc, 0)
            ty = trendyol_map.get(bc, 0)
            ok = (sh == expected) and (ty == expected)
            if not ok:
                mismatch += 1
            durum = "OK" if ok else "UYUMSUZ"
            print(f"{bc:<16}{central:>8}{rez:>8}{expected:>8}{sh:>9}{ty:>10}  {durum}")

        print("-" * len(header))
        print(f"\nSonuc: {len(sample) - mismatch} uyumlu, {mismatch} uyumsuz")
        if mismatch:
            print("UYUMSUZ olanlar: merkez(-rezerv) ile platform stogu farkli. Stok sync gerekebilir.")
        else:
            print("Tum ornek barkodlar Shopify ve Trendyol'da merkez stokla uyumlu.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
