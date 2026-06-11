#!/usr/bin/env python3
"""BUGÜN düşen sipariş–ürün–raf listesini PDF olarak üretir — SALT OKUNUR.

Kaynak: StockMovement (reason=pack_out, bugün). Her satır = bir düşüm hareketi:
sipariş no, barkod, ürün adı, raf, adet, saat. Ürün adı Product tablosundan.

    DISABLE_JOBS=1 python scripts/today_picking_pdf.py [--date YYYY-MM-DD] [--out PATH]
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")

from app import app  # noqa: E402
from models import db, StockMovement, Product  # noqa: E402

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
)

# Türkçe karakter destekli font
_FONT = "Helvetica"
_FONT_B = "Helvetica-Bold"
for cand in (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
):
    if Path(cand).exists():
        try:
            pdfmetrics.registerFont(TTFont("TR", cand))
            pdfmetrics.registerFont(TTFont("TR-B", cand))
            _FONT = "TR"
            _FONT_B = "TR-B"
            break
        except Exception:
            pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (varsayılan: bugün, UTC)")
    ap.add_argument("--out", help="çıktı PDF yolu")
    args = ap.parse_args()

    with app.app_context():
        if args.date:
            day_start = datetime.strptime(args.date, "%Y-%m-%d")
        else:
            now = datetime.utcnow()
            day_start = datetime(now.year, now.month, now.day)
        day_end = day_start + timedelta(days=1)
        dstr = day_start.strftime("%Y-%m-%d")

        out = args.out or str(PROJECT_ROOT / f"bugun_dusum_{dstr}.pdf")

        movements = (
            StockMovement.query
            .filter(StockMovement.created_at >= day_start,
                    StockMovement.created_at < day_end)
            .filter(StockMovement.reason.in_(("pack_out", "ship_out")))
            .filter(StockMovement.delta < 0)
            .order_by(StockMovement.order_number.asc(),
                      StockMovement.created_at.asc())
            .all()
        )

        # ürün: model kodu - renk - beden
        bcs = {m.barcode for m in movements}
        prod = {}
        if bcs:
            for p in Product.query.filter(Product.barcode.in_(bcs)).all():
                model = p.product_main_id or getattr(p, "product_code", None) or "-"
                parts = [str(model)]
                if p.color:
                    parts.append(str(p.color))
                if p.size:
                    parts.append(str(p.size))
                prod[p.barcode] = " - ".join(parts)

        styles = getSampleStyleSheet()
        cell = ParagraphStyle("cell", parent=styles["Normal"], fontName=_FONT,
                              fontSize=8, leading=10)
        cell_b = ParagraphStyle("cellb", parent=styles["Normal"], fontName=_FONT_B,
                                fontSize=8, leading=10)
        title = ParagraphStyle("title", parent=styles["Title"], fontName=_FONT_B,
                               fontSize=15, leading=18)
        sub = ParagraphStyle("sub", parent=styles["Normal"], fontName=_FONT,
                             fontSize=9, leading=12, textColor=colors.grey)

        rows = [[
            Paragraph("<b>#</b>", cell_b),
            Paragraph("<b>Sipariş No</b>", cell_b),
            Paragraph("<b>Barkod</b>", cell_b),
            Paragraph("<b>Model - Renk - Beden</b>", cell_b),
            Paragraph("<b>Raf</b>", cell_b),
            Paragraph("<b>Adet</b>", cell_b),
            Paragraph("<b>Saat</b>", cell_b),
        ]]
        total_qty = 0
        for i, m in enumerate(movements, 1):
            qty = -m.delta
            total_qty += qty
            rows.append([
                Paragraph(str(i), cell),
                Paragraph(str(m.order_number or "-"), cell),
                Paragraph(str(m.barcode), cell),
                Paragraph(prod.get(m.barcode, "-"), cell),
                Paragraph(f"<b>{m.shelf_code or '-'}</b>", cell_b),
                Paragraph(str(qty), cell),
                Paragraph(m.created_at.strftime("%H:%M"), cell),
            ])

        doc = SimpleDocTemplate(
            out, pagesize=A4,
            leftMargin=12 * mm, rightMargin=12 * mm,
            topMargin=14 * mm, bottomMargin=14 * mm,
            title=f"Bugün Düşen Stok Listesi {dstr}",
        )
        elems = [
            Paragraph("Bugün Düşen Stok Listesi (Sipariş · Ürün · Raf)", title),
            Paragraph(f"Tarih: {dstr} (UTC) &nbsp;|&nbsp; Toplam hareket: {len(movements)} "
                     f"&nbsp;|&nbsp; Toplam adet: {total_qty} &nbsp;|&nbsp; "
                     f"Üretim: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC", sub),
            Spacer(1, 6 * mm),
        ]

        col_w = [9 * mm, 30 * mm, 32 * mm, 62 * mm, 18 * mm, 13 * mm, 16 * mm]
        tbl = Table(rows, colWidths=col_w, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), _FONT_B),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f3f3")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (4, 0), (6, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elems.append(tbl)
        doc.build(elems)

        print(f"PDF üretildi: {out}")
        print(f"Satır: {len(movements)} | Toplam adet: {total_qty}")


if __name__ == "__main__":
    main()
