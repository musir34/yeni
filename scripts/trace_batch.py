# -*- coding: utf-8 -*-
import os, sys, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app import app
import order_audit_routes as oar

ORDERS = ["11236232878","11236810472","11234634837","11235429001","11233041051",
          "11233534939","11235070901","11236886231","11235587834"]
OUT = os.path.join(os.path.dirname(__file__), "trace_batch_result.txt")
L = []
def e(s=""): L.append(str(s))

with app.app_context():
    for needle in ORDERS:
        e("=" * 70)
        e(f"SIPARIS {needle}")
        try:
            recs = oar._find_order_records(needle)
        except Exception as ex:
            recs = []
            e(f"  _find_order_records hata: {ex}")
        if not recs:
            e("  KAYIT YOK (orders_created/archive bulunamadi)")
        for r in recs:
            e(f"  tablo={r.get('table')} status={r.get('status')} atanan_raf={r.get('atanan_raf')} pkg={r.get('package_number')}")
        try:
            bcs = oar._extract_barcodes(recs)
        except Exception as ex:
            bcs = []
        for bc in bcs:
            try:
                snap = oar._barcode_snapshot(bc)
            except Exception as ex:
                e(f"  SNAP {bc} hata: {ex}"); continue
            e(f"  BARKOD {bc}: central={snap.get('central_stock')} raf_total={snap.get('raf_total')} "
              f"raf_dist={snap.get('raf_distribution')} alias={snap.get('alias')}")
        try:
            ev = oar._audit_events(needle, bcs)
        except Exception as ex:
            ev = []
            e(f"  _audit_events hata: {ex}")
        e(f"  EVENTS ({len(ev)}):")
        for x in ev:
            e(f"    {x.get('ts')} {x.get('event_type')} bc={x.get('barcode')} raf={x.get('raf_kodu')} "
              f"cb={x.get('central_qty_before')} ca={x.get('central_qty_after')} "
              f"rb={x.get('raf_total_before')} ra={x.get('raf_total_after')} | "
              f"{str(x.get('message') or x.get('note') or '')[:110]}")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
print("DONE")
