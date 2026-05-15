"""Sipariş iz sürme paneli."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import func, or_, text

from models import (
    Archive,
    BarcodeAlias,
    CentralStock,
    Order,
    OrderArchived,
    OrderAuditLog,
    OrderCancelled,
    OrderCreated,
    OrderDelivered,
    OrderPicking,
    OrderReadyToShip,
    OrderShipped,
    Product,
    RafUrun,
    ShopifyMapping,
    UserLog,
    db,
)

logger = logging.getLogger(__name__)
order_audit_bp = Blueprint("order_audit", __name__)


ORDER_TABLES: list[tuple[type, str]] = [
    (OrderCreated, "Created"),
    (OrderPicking, "Picking"),
    (OrderReadyToShip, "ReadyToShip"),
    (OrderShipped, "Shipped"),
    (OrderDelivered, "Delivered"),
    (OrderCancelled, "Cancelled"),
    (OrderArchived, "Archived"),
]


def _safe_get(obj, *names, default=None):
    for n in names:
        if hasattr(obj, n):
            v = getattr(obj, n)
            if v is not None:
                return v
    return default


def _serialize_order_row(row, table_label: str) -> dict:
    return {
        "table": table_label,
        "id": getattr(row, "id", None),
        "order_number": _safe_get(row, "order_number"),
        "package_number": _safe_get(row, "package_number"),
        "status": _safe_get(row, "status"),
        "order_date": str(_safe_get(row, "order_date") or ""),
        "created_at": str(_safe_get(row, "created_at") or ""),
        "updated_at": str(_safe_get(row, "updated_at") or ""),
        "product_barcode": _safe_get(row, "product_barcode"),
        "merchant_sku": _safe_get(row, "merchant_sku"),
        "product_name": _safe_get(row, "product_name"),
        "quantity": _safe_get(row, "quantity"),
        "amount": _safe_get(row, "amount"),
        "atanan_raf": _safe_get(row, "atanan_raf"),
        "picking_start_time": str(_safe_get(row, "picking_start_time") or "") or None,
        "picked_by": _safe_get(row, "picked_by"),
        "cargo_provider_name": _safe_get(row, "cargo_provider_name"),
        "cargo_tracking_number": _safe_get(row, "cargo_tracking_number"),
        "customer": f"{_safe_get(row, 'customer_name') or ''} {_safe_get(row, 'customer_surname') or ''}".strip(),
        "details": _parse_details(_safe_get(row, "details")),
    }


def _parse_details(raw):
    if raw is None:
        return None
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return str(raw)[:500]


def _find_order_records(needle: str) -> list[dict]:
    out: list[dict] = []
    for model, label in ORDER_TABLES:
        try:
            rows = (
                db.session.query(model)
                .filter(
                    or_(
                        model.order_number == needle,
                        model.package_number == needle,
                        model.shipment_package_id == needle,
                    )
                )
                .limit(20)
                .all()
            )
            for r in rows:
                out.append(_serialize_order_row(r, label))
        except Exception as e:
            # Şema farklılığı olan tablolarda raw SQL fallback.
            logger.warning("Order arama hatası %s: %s", label, e)
            db.session.rollback()
            try:
                tbl = model.__tablename__
                with db.engine.connect() as c:
                    raw_rows = c.execute(
                        text(
                            f"SELECT order_number, package_number, status, order_date, "
                            f"product_barcode, quantity, details "
                            f"FROM {tbl} WHERE order_number = :n OR package_number = :n LIMIT 20"
                        ),
                        {"n": needle},
                    ).fetchall()
                for r in raw_rows:
                    d = dict(r._mapping)
                    out.append(
                        {
                            "table": label,
                            "order_number": d.get("order_number"),
                            "package_number": d.get("package_number"),
                            "status": d.get("status"),
                            "order_date": str(d.get("order_date") or ""),
                            "product_barcode": d.get("product_barcode"),
                            "quantity": d.get("quantity"),
                            "details": _parse_details(d.get("details")),
                        }
                    )
            except Exception:
                logger.exception("raw fallback hatası: %s", label)

    # Archive (paket iptali sonrası buraya düşer)
    try:
        rows = (
            db.session.query(Archive)
            .filter(
                or_(
                    Archive.order_number == needle,
                    Archive.package_number == needle,
                )
            )
            .all()
        )
        for r in rows:
            out.append(_serialize_order_row(r, "Archive(paket iptal)"))
    except Exception:
        logger.exception("Archive arama hatası")

    return out


def _extract_barcodes(order_records: list[dict]) -> list[str]:
    seen: set[str] = set()
    for rec in order_records:
        pb = rec.get("product_barcode")
        if pb:
            for b in str(pb).split(","):
                b = b.strip()
                if b:
                    seen.add(b)
        det = rec.get("details")
        if isinstance(det, list):
            for it in det:
                if isinstance(it, dict):
                    bc = it.get("barcode") or it.get("Barcode") or it.get("sku")
                    if bc:
                        seen.add(str(bc).strip())
    return sorted(seen)


def _barcode_snapshot(barcode: str) -> dict:
    cs = db.session.get(CentralStock, barcode)
    p = db.session.get(Product, barcode)
    rafs = (
        db.session.query(RafUrun)
        .filter(RafUrun.urun_barkodu == barcode)
        .all()
    )
    raf_total = sum(int(r.adet or 0) for r in rafs)
    raf_dist = [{"raf_kodu": r.raf_kodu, "adet": int(r.adet or 0)} for r in rafs]

    sm = (
        db.session.query(ShopifyMapping)
        .filter(ShopifyMapping.barcode == barcode)
        .all()
    )

    aliases_as_alias = (
        db.session.query(BarcodeAlias)
        .filter(BarcodeAlias.alias_barcode == barcode)
        .first()
    )
    aliases_as_main = (
        db.session.query(BarcodeAlias)
        .filter(BarcodeAlias.main_barcode == barcode)
        .all()
    )

    return {
        "barcode": barcode,
        "product": (
            {
                "title": p.title if p else None,
                "product_main_id": getattr(p, "product_main_id", None) if p else None,
                "size": getattr(p, "size", None) if p else None,
                "color": getattr(p, "color", None) if p else None,
                "quantity": getattr(p, "quantity", None) if p else None,
            }
            if p
            else None
        ),
        "central_stock": (
            {
                "qty": cs.qty,
                "updated_at": str(cs.updated_at) if cs.updated_at else None,
            }
            if cs
            else None
        ),
        "raf_total": raf_total,
        "raf_distribution": raf_dist,
        "shopify_mappings": [
            {
                "variant_id": m.shopify_variant_id,
                "last_stock_sent": m.last_stock_sent,
                "last_sync_at": str(m.last_sync_at) if m.last_sync_at else None,
            }
            for m in sm
        ],
        "alias": (
            {"alias_of": aliases_as_alias.main_barcode}
            if aliases_as_alias
            else None
        ),
        "is_main_for": [a.alias_barcode for a in aliases_as_main],
    }


def _audit_events(needle: str, barcodes: list[str], limit: int = 500) -> list[dict]:
    q = db.session.query(OrderAuditLog).filter(
        or_(
            OrderAuditLog.order_number == needle,
            OrderAuditLog.package_number == needle,
            OrderAuditLog.barcode.in_(barcodes) if barcodes else False,
        )
    )
    rows = q.order_by(OrderAuditLog.ts.asc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "ts": r.ts.strftime("%Y-%m-%d %H:%M:%S") if r.ts else "",
            "event_type": r.event_type,
            "severity": r.severity,
            "order_number": r.order_number,
            "package_number": r.package_number,
            "barcode": r.barcode,
            "quantity": r.quantity,
            "central_qty_before": r.central_qty_before,
            "central_qty_after": r.central_qty_after,
            "raf_total_before": r.raf_total_before,
            "raf_total_after": r.raf_total_after,
            "raf_kodu": r.raf_kodu,
            "status_from": r.status_from,
            "status_to": r.status_to,
            "source": r.source,
            "user_id": r.user_id,
            "message": r.message,
            "details": r.details,
        }
        for r in rows
    ]


def _user_logs(needle: str, limit: int = 50) -> list[dict]:
    rows = (
        db.session.query(UserLog)
        .filter(UserLog.details.like(f"%{needle}%"))
        .order_by(UserLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "ts": u.timestamp.strftime("%Y-%m-%d %H:%M:%S") if u.timestamp else "",
            "user_id": u.user_id,
            "action": u.action,
            "details": (u.details or "")[:1000],
        }
        for u in rows
    ]


@order_audit_bp.route("/siparis-iz", endpoint="page")
def page():
    return render_template("order_audit.html")


# ════════════════════════════════════════════════════════════════════
# Stok Kaynak Analizi — RafUrun/CentralStock'u kim/ne değiştiriyor?
# ════════════════════════════════════════════════════════════════════

def _stock_source_breakdown(hours: int) -> dict:
    since = datetime.utcnow() - timedelta(hours=hours)
    base = db.session.query(OrderAuditLog).filter(
        OrderAuditLog.ts >= since,
        OrderAuditLog.event_type.in_(["stock_changed", "raf_changed"]),
    )

    # Kaynak x olay tipi kırılımı
    rows = (
        db.session.query(
            OrderAuditLog.event_type,
            OrderAuditLog.source,
            func.count(),
        )
        .filter(
            OrderAuditLog.ts >= since,
            OrderAuditLog.event_type.in_(["stock_changed", "raf_changed"]),
        )
        .group_by(OrderAuditLog.event_type, OrderAuditLog.source)
        .order_by(func.count().desc())
        .all()
    )
    breakdown = [
        {"event_type": et, "source": src or "?", "count": int(c)}
        for et, src, c in rows
    ]

    # Fiziksel olmayan ŞİŞME: central artışı (cb < ca), kaynağa göre
    inc_rows = (
        db.session.query(OrderAuditLog.source, func.count())
        .filter(
            OrderAuditLog.ts >= since,
            OrderAuditLog.event_type == "stock_changed",
            OrderAuditLog.central_qty_after > OrderAuditLog.central_qty_before,
        )
        .group_by(OrderAuditLog.source)
        .order_by(func.count().desc())
        .all()
    )
    inflate = [{"source": s or "?", "count": int(c)} for s, c in inc_rows]

    # Şüpheli örnekler: JOB/SYSTEM dışı kaynaklı son central artışları
    ex = (
        db.session.query(OrderAuditLog)
        .filter(
            OrderAuditLog.ts >= since,
            OrderAuditLog.event_type == "stock_changed",
            OrderAuditLog.central_qty_after > OrderAuditLog.central_qty_before,
        )
        .order_by(OrderAuditLog.ts.desc())
        .limit(60)
        .all()
    )
    samples = []
    for r in ex:
        origin = None
        if isinstance(r.details, dict):
            origin = r.details.get("origin")
        samples.append({
            "ts": r.ts.isoformat() if r.ts else None,
            "barcode": r.barcode,
            "before": r.central_qty_before,
            "after": r.central_qty_after,
            "source": r.source,
            "order_number": r.order_number,
            "origin": origin,
        })

    return {
        "hours": hours,
        "since": since.isoformat(),
        "total": base.count(),
        "breakdown": breakdown,
        "inflate": inflate,
        "samples": samples,
    }


@order_audit_bp.route("/stok-kaynak", endpoint="stock_source_page")
def stock_source_page():
    return render_template("stock_source.html")


@order_audit_bp.route("/stok-kaynak/data", endpoint="stock_source_data")
def stock_source_data():
    try:
        hours = int(request.args.get("hours", "6"))
    except (TypeError, ValueError):
        hours = 6
    hours = max(1, min(hours, 168))
    try:
        return jsonify({"success": True, **_stock_source_breakdown(hours)})
    except Exception as exc:
        logger.exception("stok-kaynak data hatası")
        return jsonify({"success": False, "error": str(exc)}), 500


@order_audit_bp.route("/siparis-iz/lookup", endpoint="lookup")
def lookup():
    needle = (request.args.get("q") or "").strip()
    if not needle:
        return jsonify({"success": False, "error": "Sipariş numarası gir."}), 400

    try:
        order_records = _find_order_records(needle)
        barcodes = _extract_barcodes(order_records)
        snapshots = [_barcode_snapshot(b) for b in barcodes]
        events = _audit_events(needle, barcodes)
        ulogs = _user_logs(needle)

        return jsonify(
            {
                "success": True,
                "query": needle,
                "order_records": order_records,
                "barcodes": barcodes,
                "snapshots": snapshots,
                "events": events,
                "user_logs": ulogs,
            }
        )
    except Exception as exc:
        logger.exception("siparis-iz lookup hatası")
        return jsonify({"success": False, "error": str(exc)}), 500


@order_audit_bp.route("/siparis-iz/backfill", methods=["POST"], endpoint="backfill")
def backfill():
    """atanan_raf=NULL olan Created siparişleri için raf ataması + retro event yazar."""
    from raf_recovery import recover_missing_raf

    target_order = (request.json or {}).get("order_number") if request.is_json else request.args.get("order_number")
    target_order = (target_order or "").strip() or None

    try:
        result = recover_missing_raf(order_number=target_order, source="BACKFILL")
    except Exception as exc:
        logger.exception("backfill hatası")
        return jsonify({"success": False, "error": str(exc)}), 500

    return jsonify({
        "success": True,
        **result,
        "filter": {"order_number": target_order} if target_order else "all_null",
    })


@order_audit_bp.route("/siparis-iz/note", methods=["POST"], endpoint="add_note")
def add_note():
    """Operatörün manuel notu ekler (post-mortem için)."""
    from order_audit import log_event

    data = request.get_json(silent=True) or {}
    needle = (data.get("order_number") or "").strip()
    msg = (data.get("message") or "").strip()
    if not needle or not msg:
        return jsonify({"success": False, "error": "order_number ve message gerek."}), 400
    log_event(
        "manual_note",
        order_number=needle,
        package_number=data.get("package_number") or None,
        barcode=data.get("barcode") or None,
        message=msg,
        source="USER",
        severity="info",
    )
    return jsonify({"success": True})
