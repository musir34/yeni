# -*- coding: utf-8 -*-
"""Belirtilen sipariş→raf çiftleri için ürünü o raftan SİL (RafUrun satırı) + CentralStock güncelle."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app import app
from models import db, RafUrun, CentralStock
from barcode_alias_helper import normalize_barcode
from stock_management import sync_central_stock
import order_audit_routes as oar

# (sipariş_no, raf_kodu)
PAIRS = [
    ("11236232878", "F-A-01"),
    ("11236810472", "F-A-02"),
    ("11234634837", "E-E-01"),
    ("11235429001", "F-G-02"),
    ("11233041051", "C-E-02"),
    ("11233534939", "C-G-02"),
    ("11235070901", "G-E-02"),
    ("11236886231", "G-F-02"),
    ("11235587834", "G-E-02"),
]

APPLY = os.getenv("APPLY", "0") == "1"

with app.app_context():
    print(f"{'SIPARIS':<14}{'RAF':<8}{'BARKOD':<22}{'CANON':<22}{'ADET':>5}  AKSIYON")
    print("-" * 85)
    deleted, central_changed = 0, []
    for order_no, shelf in PAIRS:
        recs = oar._find_order_records(order_no)
        bcs = oar._extract_barcodes(recs)
        if not bcs:
            print(f"{order_no:<14}{shelf:<8}{'(barkod yok)':<22}{'':<22}{'-':>5}  ATLANDI")
            continue
        for bc in bcs:
            canon = normalize_barcode(bc)
            row = (RafUrun.query
                   .filter_by(urun_barkodu=canon, raf_kodu=shelf)
                   .first())
            if not row:
                print(f"{order_no:<14}{shelf:<8}{bc:<22}{canon:<22}{'-':>5}  RAF SATIRI YOK")
                continue
            adet = row.adet
            if APPLY:
                db.session.delete(row)
                db.session.flush()
                sync_central_stock(canon, commit=False)
                cs = CentralStock.query.get(canon)
                central_changed.append((canon, cs.qty if cs else 0))
                deleted += 1
                print(f"{order_no:<14}{shelf:<8}{bc:<22}{canon:<22}{adet:>5}  SİLİNDİ → central={cs.qty if cs else 0}")
            else:
                print(f"{order_no:<14}{shelf:<8}{bc:<22}{canon:<22}{adet:>5}  [DRY-RUN] silinecek")

    if APPLY:
        db.session.commit()
        print("-" * 85)
        print(f"COMMIT: {deleted} raf satırı silindi.")
    else:
        print("-" * 85)
        print("DRY-RUN (APPLY=0). Uygulamak için APPLY=1 ile çalıştır.")
