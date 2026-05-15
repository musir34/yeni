# -*- coding: utf-8 -*-
"""Urun listesinde OLAN, central etkin stok 0, ama Shopify'da hala >0 olan barkodlar."""
from __future__ import annotations

import os
import sys
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from models import CentralStock, Product
from stock_sync.service import stock_sync_service
from barcode_alias_helper import normalize_barcode
from check_random_stock_match import gather_platforms

OUT = os.path.join(os.path.dirname(__file__), "real_product_zero_result.txt")
_l: list[str] = []


def e(s=""):
    _l.append(str(s))


def main():
    with app.app_context():
        print("Shopify + Trendyol PARALEL cekiliyor...")
        shopify_map, trendyol_map = asyncio.run(gather_platforms())

        # Panel urun listesi (Product) barkodlari
        prod_barcodes = {p.barcode for p in Product.query.with_entities(Product.barcode).all()}

        reserved = stock_sync_service.get_reserved_barcodes()

        # Sadece Shopify'da gozuken barkodlar uzerinde calis
        hits = []
        for bc, sh_qty in shopify_map.items():
            if sh_qty <= 0:
                continue
            canon = normalize_barcode(bc)
            # Urun listesinde olmali (bc veya canonical Product'ta)
            if bc not in prod_barcodes and canon not in prod_barcodes:
                continue  # orphan, salla
            cs = CentralStock.query.filter_by(barcode=canon).first()
            central = cs.qty if cs else 0
            rez = reserved.get(canon, 0) or reserved.get(bc, 0)
            effective = max(0, central - rez)
            if effective == 0:
                hits.append((bc, canon, central, rez, sh_qty, trendyol_map.get(bc, 0)))

        e("=== URUN LISTESINDE OLAN + CENTRAL 0 + SHOPIFY >0 ===")
        e(f"Toplam: {len(hits)} barkod, Shopify'da asili {sum(h[4] for h in hits)} adet")
        e("")
        e(f"{'BARKOD':<22}{'CANONICAL':<22}{'CENTRAL':>8}{'REZERV':>7}{'SHOPIFY':>8}{'TRNDYL':>8}")
        e("-" * 75)
        for h in sorted(hits, key=lambda x: -x[4]):
            e(f"{h[0]:<22}{h[1]:<22}{h[2]:>8}{h[3]:>7}{h[4]:>8}{h[5]:>8}")

        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_l))
        print("RESULT_WRITTEN " + str(len(hits)))


if __name__ == "__main__":
    main()
