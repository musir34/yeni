# -*- coding: utf-8 -*-
"""Central'da 0 gorunen barkodlar Shopify ve Trendyol'da kac adet duruyor?"""
from __future__ import annotations

import os
import sys
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from models import CentralStock
from stock_sync.service import stock_sync_service

# fetch_shopify_map / fetch_trendyol_map / gather_platforms ayni mantik
from check_random_stock_match import gather_platforms


def main() -> int:
    with app.app_context():
        print("Shopify ve Trendyol urunleri PARALEL cekiliyor...")
        shopify_map, trendyol_map = asyncio.run(gather_platforms())
        print(f"Shopify: {len(shopify_map)} | Trendyol: {len(trendyol_map)}")

        common = sorted(set(shopify_map) & set(trendyol_map))
        cs_rows = CentralStock.query.filter(CentralStock.barcode.in_(common)).all()
        cs_map = {c.barcode: c.qty for c in cs_rows}
        reserved = stock_sync_service.get_reserved_barcodes()

        # Central'da etkin stok 0 olan barkodlar (qty - rezerv <= 0, kayit yoksa da 0)
        zero_barcodes = []
        for bc in common:
            central = cs_map.get(bc, 0)
            effective = max(0, central - reserved.get(bc, 0))
            if effective == 0:
                zero_barcodes.append(bc)

        sh_pos = [bc for bc in zero_barcodes if shopify_map.get(bc, 0) > 0]
        ty_pos = [bc for bc in zero_barcodes if trendyol_map.get(bc, 0) > 0]
        both_pos = [bc for bc in zero_barcodes if shopify_map.get(bc, 0) > 0 and trendyol_map.get(bc, 0) > 0]

        print(f"\n=== CENTRAL'DA 0 OLAN BARKODLAR ===")
        print(f"Ortak barkod                : {len(common)}")
        print(f"Central'da etkin stok 0     : {len(zero_barcodes)}")
        print(f"  -> Shopify'da > 0 (sapma) : {len(sh_pos)}")
        print(f"  -> Trendyol'da > 0 (sapma): {len(ty_pos)}")
        print(f"  -> Her ikisinde de > 0    : {len(both_pos)}")
        print(f"  -> Her ikisinde de 0 (OK) : {len(zero_barcodes) - len(set(sh_pos) | set(ty_pos))}")

        sapma = sorted(set(sh_pos) | set(ty_pos), key=lambda b: -(shopify_map.get(b, 0) + trendyol_map.get(b, 0)))
        if sapma:
            print(f"\n=== SAPMA OLAN {len(sapma)} BARKOD (central 0 ama platformda var) ===")
            print(f"{'BARKOD':<24}{'SHOPIFY':>9}{'TRENDYOL':>10}")
            print("-" * 43)
            for bc in sapma[:60]:
                print(f"{bc:<24}{shopify_map.get(bc,0):>9}{trendyol_map.get(bc,0):>10}")
            if len(sapma) > 60:
                print(f"... ve {len(sapma) - 60} barkod daha")
            tot_sh = sum(shopify_map.get(b, 0) for b in sapma)
            tot_ty = sum(trendyol_map.get(b, 0) for b in sapma)
            print(f"\nToplam yanlis asili adet -> Shopify: {tot_sh} | Trendyol: {tot_ty}")
        else:
            print("\nCentral'da 0 olan tum barkodlar platformlarda da 0. Tam uyumlu.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
