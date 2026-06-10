#!/usr/bin/env python3
"""Sipariş / Barkod İZLEME ARACI — SALT OKUNUR (hiçbir yazma yapmaz).

Bir siparişin veya barkodun tüm stok serüvenini, iki izi birleştirerek
kronolojik tek bir zaman çizelgesinde gösterir:
  - OrderAuditLog  (olay izi: status_changed, order_picked, raf_changed, ...)
  - StockMovement  (hareket defteri: pack_out, ship_out, cancel_return, ...)

Ayrıca siparişin ANLIK konumunu (hangi sipariş tablosunda) ve barkodun
güncel raf/merkez stok durumunu özetler.

Çalıştırma
----------
    DISABLE_JOBS=1 python scripts/trace_order.py 1234567890        # otomatik algıla
    DISABLE_JOBS=1 python scripts/trace_order.py --order 1234567890
    DISABLE_JOBS=1 python scripts/trace_order.py --barcode 9852370982310
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")

# Sipariş statü tabloları (anlık konum tespiti için)
_ORDER_TABLES = [
    ("orders_created", "Yeni (Created)"),
    ("orders_hazirlaniyor", "Hazırlanıyor"),
    ("orders_picking", "İşleme Alındı (Picking)"),
    ("orders_shipped", "Kargolandı (Shipped)"),
    ("orders_delivered", "Teslim Edildi (Delivered)"),
    ("orders_cancelled", "İptal (Cancelled)"),
]


def _fmt_ts(ts):
    try:
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def _safe_movements_query(model_filter):
    """StockMovement tablosu yoksa (deploy öncesi) sessizce boş döner."""
    try:
        from models import StockMovement
        return model_filter(StockMovement).all()
    except Exception as e:
        print(f"  (StockMovement defteri okunamadı — muhtemelen henüz deploy edilmedi: {e})")
        return []


# ──────────────────────────────────────────────────────────────────────
# Çekirdek: birleşik zaman çizelgesi olayları
# ──────────────────────────────────────────────────────────────────────
def _audit_events(filter_fn):
    from models import OrderAuditLog
    rows = filter_fn(OrderAuditLog.query).order_by(OrderAuditLog.ts).all()
    out = []
    for r in rows:
        out.append({
            "ts": r.ts,
            "kind": "AUDIT",
            "tag": r.event_type,
            "severity": r.severity or "info",
            "detail": _audit_detail(r),
            "source": r.source or "",
        })
    return out


def _audit_detail(r):
    parts = []
    if r.status_from or r.status_to:
        parts.append(f"{r.status_from or '—'}→{r.status_to or '—'}")
    if r.barcode:
        parts.append(f"bc={r.barcode}")
    if r.quantity is not None:
        parts.append(f"qty={r.quantity}")
    if r.raf_total_before is not None or r.raf_total_after is not None:
        parts.append(f"raf {r.raf_total_before}→{r.raf_total_after}")
    if r.message:
        parts.append(r.message)
    return " · ".join(str(p) for p in parts)


def _movement_events(filter_fn):
    rows = _safe_movements_query(lambda M: filter_fn(M.query).order_by(M.created_at))
    out = []
    for r in rows:
        sign = "+" if r.delta >= 0 else ""
        out.append({
            "ts": r.created_at,
            "kind": "LEDGER",
            "tag": r.reason,
            "severity": "info",
            "detail": f"{sign}{r.delta} adet"
                      + (f" · raf={r.shelf_code}" if r.shelf_code else "")
                      + (f" · {r.note}" if r.note else ""),
            "source": r.source or "",
        })
    return out


def _print_timeline(events):
    if not events:
        print("  (kayıt yok)")
        return
    events.sort(key=lambda e: (e["ts"] or __import__("datetime").datetime.min))
    icon = {"AUDIT": "📋", "LEDGER": "📦"}
    for e in events:
        sev = "🔴 " if e["severity"] == "critical" else ("⚠️  " if e["severity"] == "warning" else "")
        src = f"  [{e['source']}]" if e["source"] else ""
        print(f"  {_fmt_ts(e['ts'])}  {icon.get(e['kind'],'•')} {sev}{e['tag']:<18} {e['detail']}{src}")


# ──────────────────────────────────────────────────────────────────────
# Sipariş modu
# ──────────────────────────────────────────────────────────────────────
def trace_order(order_number):
    from sqlalchemy import text
    from models import db, Archive

    print("=" * 78)
    print(f"SİPARİŞ İZLEME · {order_number}")
    print("=" * 78)

    # Anlık konum
    print("\n▸ ANLIK KONUM")
    found = False
    for tbl, label in _ORDER_TABLES:
        try:
            n = db.session.execute(
                text(f"SELECT COUNT(*) FROM {tbl} WHERE order_number = :o"),
                {"o": str(order_number)},
            ).scalar()
        except Exception:
            n = 0
        if n:
            print(f"  • {label}  ({tbl}, {n} kayıt)")
            found = True
    try:
        if Archive.query.filter_by(order_number=str(order_number)).count():
            print("  • Arşivde")
            found = True
    except Exception:
        pass
    if not found:
        print("  • Aktif sipariş tablolarında bulunamadı (Shopify olabilir veya hiç görülmemiş)")

    # Zaman çizelgesi
    print("\n▸ ZAMAN ÇİZELGESİ (📋 audit · 📦 stok defteri)")
    events = (
        _audit_events(lambda q: q.filter_by(order_number=str(order_number)))
        + _movement_events(lambda q: q.filter_by(order_number=str(order_number)))
    )
    _print_timeline(events)

    # Stok özeti
    movs = [e for e in events if e["kind"] == "LEDGER"]
    if movs:
        print(f"\n▸ ÖZET: {len(movs)} stok hareketi kayıtlı")
    crit = [e for e in events if e["severity"] == "critical"]
    if crit:
        print(f"  🔴 {len(crit)} KRİTİK uyarı var (hayalet stok riski) — yukarıya bak")


# ──────────────────────────────────────────────────────────────────────
# Barkod modu
# ──────────────────────────────────────────────────────────────────────
def trace_barcode(barcode):
    from models import RafUrun, CentralStock
    from barcode_alias_helper import normalize_barcode

    norm = normalize_barcode(barcode)
    print("=" * 78)
    print(f"BARKOD İZLEME · {barcode}" + (f"  (normalize: {norm})" if norm != barcode else ""))
    print("=" * 78)

    # Güncel durum
    print("\n▸ GÜNCEL STOK")
    raf_rows = RafUrun.query.filter_by(urun_barkodu=norm).all()
    raf_total = sum((r.adet or 0) for r in raf_rows)
    for r in raf_rows:
        print(f"  • {r.raf_kodu}: {r.adet} adet")
    cs = CentralStock.query.get(norm)
    print(f"  → Raf toplam: {raf_total} | CentralStock: {cs.qty if cs else 0}")

    # Zaman çizelgesi
    print("\n▸ ZAMAN ÇİZELGESİ (📋 audit · 📦 stok defteri)")
    events = (
        _audit_events(lambda q: q.filter_by(barcode=norm))
        + _movement_events(lambda q: q.filter_by(barcode=norm))
    )
    _print_timeline(events)

    # Defterden net hareket
    movs = _safe_movements_query(
        lambda M: M.query.filter_by(barcode=norm)
    )
    if movs:
        net = sum(m.delta for m in movs)
        print(f"\n▸ ÖZET: defterde net {net:+d} adet ({len(movs)} hareket). "
              f"Güncel raf toplamı: {raf_total}")


# ──────────────────────────────────────────────────────────────────────
def _auto_detect(app, value):
    """Değerin sipariş mi barkod mu olduğunu kabaca tahmin et."""
    from sqlalchemy import text
    from models import db, RafUrun
    with app.app_context():
        for tbl, _ in _ORDER_TABLES:
            try:
                if db.session.execute(
                    text(f"SELECT 1 FROM {tbl} WHERE order_number = :o LIMIT 1"),
                    {"o": str(value)},
                ).first():
                    return "order"
            except Exception:
                continue
        if RafUrun.query.filter_by(urun_barkodu=value).first():
            return "barcode"
    return None


def main():
    ap = argparse.ArgumentParser(description="Sipariş/Barkod stok izleme (salt okunur)")
    ap.add_argument("value", nargs="?", help="Sipariş numarası veya barkod")
    ap.add_argument("--order", help="Sipariş numarasıyla izle")
    ap.add_argument("--barcode", help="Barkodla izle")
    args = ap.parse_args()

    from app import app

    if args.order:
        with app.app_context():
            trace_order(args.order)
        return
    if args.barcode:
        with app.app_context():
            trace_barcode(args.barcode)
        return
    if not args.value:
        ap.error("Bir sipariş numarası veya barkod ver (ya da --order/--barcode)")

    mode = _auto_detect(app, args.value)
    with app.app_context():
        if mode == "barcode":
            trace_barcode(args.value)
        elif mode == "order":
            trace_order(args.value)
        else:
            print(f"'{args.value}' otomatik algılanamadı — her iki mod da deneniyor:\n")
            trace_order(args.value)
            print()
            trace_barcode(args.value)


if __name__ == "__main__":
    main()
