# -*- coding: utf-8 -*-
"""Gercek sapma barkodlari neden central 0 ama Shopify'da satista? Tani."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from models import CentralStock, RafUrun, Product, ShopifyMapping
from stock_sync.service import stock_sync_service
from barcode_alias_helper import normalize_barcode, get_alias_info

BARCODES = [
    "73008433001", "73008433002", "73008433003", "73008433004",
    "73008433005", "73008433006", "73008433007",
    "0198523701411", "0198523701412", "0198523701428", "0198523714210",
]

OUT = os.path.join(os.path.dirname(__file__), "diag_result.txt")
_l: list[str] = []


def e(s=""):
    _l.append(str(s))


def main():
    with app.app_context():
        reserved = stock_sync_service.get_reserved_barcodes()
        for bc in BARCODES:
            canon = normalize_barcode(bc)
            ai = get_alias_info(bc)
            cs = CentralStock.query.filter_by(barcode=canon).first()
            cs_raw = CentralStock.query.filter_by(barcode=bc).first()
            rafs = RafUrun.query.filter_by(urun_barkodu=canon).all()
            raf_tot = sum(r.adet for r in rafs)
            p = Product.query.filter_by(barcode=canon).first()
            maps = ShopifyMapping.query.filter_by(barcode=bc).all()
            e(f"=== {bc}  (canonical={canon}) ===")
            e(f"  alias_info       : {ai}")
            e(f"  CentralStock[{canon}] : {cs.qty if cs else 'KAYIT YOK'}"
              + (f"  | CentralStock[{bc}](raw)={cs_raw.qty}" if cs_raw else ""))
            e(f"  Raf kayitlari    : {[(r.raf_kodu, r.adet) for r in rafs] or 'YOK'} (toplam {raf_tot})")
            e(f"  Product.quantity : {p.quantity if p else 'PRODUCT YOK'}"
              + (f" | satista_mi={getattr(p,'is_active',None)}" if p else ""))
            e(f"  Rezerv(bekleyen) : canon={reserved.get(canon,0)} raw={reserved.get(bc,0)}")
            if maps:
                for m in maps:
                    e(f"  ShopifyMapping   : variant={m.shopify_variant_id} "
                      f"last_stock_sent={m.last_stock_sent} last_sync_at={m.last_sync_at} "
                      f"sh_barcode={m.shopify_barcode} sku={m.shopify_sku}")
            else:
                e("  ShopifyMapping   : YOK (panel bu barkodu Shopify'a mapli bilmiyor!)")
            e("")
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_l))
        print("RESULT_WRITTEN")


if __name__ == "__main__":
    main()
