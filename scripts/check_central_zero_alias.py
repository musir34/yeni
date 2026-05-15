# -*- coding: utf-8 -*-
"""Alias-normalizasyonlu: Central'da gercekten 0 olup Shopify/Trendyol'da >0 olan barkodlar.

Sonuc scripts/alias_zero_result.txt dosyasina yazilir (app scheduler loglarindan ayri).
"""
from __future__ import annotations

import os
import sys
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from models import CentralStock
from stock_sync.service import stock_sync_service
from barcode_alias_helper import normalize_barcode
from check_random_stock_match import gather_platforms

OUT = os.path.join(os.path.dirname(__file__), "alias_zero_result.txt")
_lines: list[str] = []


def emit(s: str = "") -> None:
    _lines.append(s)


def main() -> int:
    with app.app_context():
        print("Shopify ve Trendyol urunleri PARALEL cekiliyor...")
        shopify_map, trendyol_map = asyncio.run(gather_platforms())
        common = sorted(set(shopify_map) & set(trendyol_map))

        canon_of = {bc: normalize_barcode(bc) for bc in common}
        canons = set(canon_of.values())
        cs_rows = CentralStock.query.filter(CentralStock.barcode.in_(list(canons))).all()
        cs_map = {c.barcode: c.qty for c in cs_rows}
        reserved = stock_sync_service.get_reserved_barcodes()

        sh_hits = []
        ty_hits = []
        for bc in common:
            canon = canon_of[bc]
            central = cs_map.get(canon, 0)
            rez = reserved.get(canon, 0) or reserved.get(bc, 0)
            effective = max(0, central - rez)
            if effective != 0:
                continue
            sh = shopify_map.get(bc, 0)
            ty = trendyol_map.get(bc, 0)
            if sh > 0:
                sh_hits.append((bc, canon, sh))
            if ty > 0:
                ty_hits.append((bc, canon, ty))

        emit("=== ALIAS-NORMALIZE: CENTRAL 0 AMA PLATFORMDA >0 ===")
        emit(f"Ortak barkod: {len(common)}")
        emit(f"Shopify'da sapma : {len(sh_hits)} barkod, toplam {sum(x[2] for x in sh_hits)} adet")
        emit(f"Trendyol'da sapma: {len(ty_hits)} barkod, toplam {sum(x[2] for x in ty_hits)} adet")

        def dump(title, hits):
            if not hits:
                emit(f"\n{title}: YOK - tam uyumlu")
                return
            emit(f"\n--- {title} ({len(hits)}) ---")
            emit(f"{'BARKOD':<24}{'CANONICAL':<22}{'ADET':>6}")
            for bc, canon, q in sorted(hits, key=lambda x: -x[2])[:120]:
                emit(f"{bc:<24}{canon:<22}{q:>6}")
            if len(hits) > 120:
                emit(f"... ve {len(hits) - 120} barkod daha")

        dump("SHOPIFY central 0 ama >0", sh_hits)
        dump("TRENDYOL central 0 ama >0", ty_hits)

        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
        print("RESULT_WRITTEN:" + OUT)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
