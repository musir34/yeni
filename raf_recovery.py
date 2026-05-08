"""atanan_raf=NULL olan Created siparişleri için raf ataması yapan helper.

Üç yerden çağrılır:
- ``order_audit_routes.backfill``  → kullanıcı "Bunu Onar / Geçmişi Tara" butonu (source=BACKFILL)
- ``order_service`` her sync turu sonunda                    (source=AUTO_HEAL)
- CLI / scheduler ile manuel                                  (source=MANUAL)

Yan etki olarak gereken eventleri ``OrderAuditLog``'a yazar.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import or_

from models import OrderCreated, RafUrun, db

logger = logging.getLogger(__name__)


def recover_missing_raf(
    order_number: str | None = None,
    *,
    source: str = "AUTO_HEAL",
    limit: int = 500,
) -> dict:
    """``atanan_raf=NULL`` olan Created siparişleri için raf atar + event yazar.

    Args:
        order_number: Tek bir sipariş için çalıştır; None ise tüm null'ları işler.
        source: Audit log'a yazılacak kaynak etiketi.
        limit: Tek seferde işlenecek max sipariş sayısı.

    Returns:
        Sayaç sözlüğü.
    """
    # Geç import: dairesel bağımlılığı önle.
    from barcode_alias_helper import normalize_barcode
    from order_audit import log_many

    q = db.session.query(OrderCreated).filter(
        or_(OrderCreated.atanan_raf.is_(None), OrderCreated.atanan_raf == "")
    )
    if order_number:
        q = q.filter(OrderCreated.order_number == order_number)

    orders = q.limit(limit).all()
    if not orders:
        return {
            "scanned": 0,
            "fixed_atanan_raf": 0,
            "raf_assigned_events": 0,
            "warnings": 0,
            "skipped_no_details": 0,
        }

    fixed = 0
    raf_total = 0
    warnings_total = 0
    skipped = 0
    evs: list[dict] = []

    for o in orders:
        if not o.details:
            skipped += 1
            continue
        try:
            det = json.loads(o.details) if isinstance(o.details, str) else o.details
        except Exception:
            skipped += 1
            continue
        if not isinstance(det, list):
            skipped += 1
            continue

        atanan_first = None
        for item in det:
            bc = normalize_barcode(str(item.get("barcode") or "").strip())
            if not bc:
                continue
            qty = int(item.get("quantity") or 1)
            raf = (
                db.session.query(RafUrun)
                .filter(RafUrun.urun_barkodu == bc, RafUrun.adet > 0)
                .order_by(RafUrun.adet.desc())
                .first()
            )
            raf_kodu = raf.raf_kodu if raf else None
            raf_mevcut = int(raf.adet) if raf else 0

            if not atanan_first and raf_kodu:
                atanan_first = raf_kodu

            evs.append({
                "event_type": "order_received",
                "order_number": o.order_number,
                "package_number": getattr(o, "package_number", None),
                "barcode": bc,
                "quantity": qty,
                "raf_kodu": raf_kodu,
                "status_to": "Created",
                "source": source,
                "severity": "info" if raf_kodu else "warning",
                "message": (
                    f"[{source}] Raf ataması yapıldı: {raf_kodu}"
                    if raf_kodu
                    else f"[{source}] Raf bulunamadı (rafta stok yok)"
                ),
                "details": {
                    "order_date": str(o.order_date or ""),
                    "raf_mevcut_stok": raf_mevcut,
                    "auto_recovery": True,
                },
                "snapshot": True,
            })
            if raf_kodu:
                raf_total += 1
                evs.append({
                    "event_type": "raf_assigned",
                    "order_number": o.order_number,
                    "package_number": getattr(o, "package_number", None),
                    "barcode": bc,
                    "raf_kodu": raf_kodu,
                    "quantity": qty,
                    "source": source,
                    "severity": "info",
                    "message": f"[{source}] Otomatik raf ataması: {raf_kodu}",
                    "snapshot": False,
                })
            else:
                warnings_total += 1
                evs.append({
                    "event_type": "warning",
                    "order_number": o.order_number,
                    "package_number": getattr(o, "package_number", None),
                    "barcode": bc,
                    "quantity": qty,
                    "source": source,
                    "severity": "critical",
                    "message": f"[{source}] Raf yok — bu barkodun stoğu rafta görünmüyor",
                    "snapshot": True,
                })

        if atanan_first:
            o.atanan_raf = atanan_first
            fixed += 1

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("[RAF_RECOVERY] commit hatası")
        return {
            "scanned": len(orders),
            "fixed_atanan_raf": 0,
            "raf_assigned_events": 0,
            "warnings": 0,
            "skipped_no_details": skipped,
            "error": "commit_failed",
        }

    if evs:
        log_many(evs)

    if fixed or warnings_total:
        logger.info(
            "[RAF_RECOVERY][%s] taranan=%d düzelen=%d raf_atandı=%d uyarı=%d atlanan=%d",
            source, len(orders), fixed, raf_total, warnings_total, skipped,
        )

    return {
        "scanned": len(orders),
        "fixed_atanan_raf": fixed,
        "raf_assigned_events": raf_total,
        "warnings": warnings_total,
        "skipped_no_details": skipped,
    }
