"""Sipariş + stok hareketleri için audit log helper.

Tek noktadan ``log_event(...)`` çağrılır. Stok snapshot'ı isteğe bağlıdır:
verilmezse fonksiyon barkoddan kendi başına çekmeyi dener.

Bağımsız bir SQLAlchemy session kullanır — log yazımı asıl işlemi
zincirlemez (rollback olsa bile log atılmış olur). Hata olursa sadece
loglar, asıl akışı kırmaz.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from flask import g, has_request_context, session
from sqlalchemy import event, func
from sqlalchemy.orm import Session as SaSession

from models import CentralStock, OrderAuditLog, RafUrun, db

logger = logging.getLogger(__name__)

VALID_SEVERITY = {"info", "warning", "critical"}


def _bind() -> Any:
    return db.session.get_bind()


def _current_user_id() -> int | None:
    """İstek bağlamı varsa kullanıcı id'sini döner."""
    try:
        if has_request_context():
            uid = session.get("user_id") or session.get("id")
            if uid:
                try:
                    return int(uid)
                except (TypeError, ValueError):
                    return None
    except Exception:
        return None
    return None


def _request_origin() -> dict:
    """Değişikliğin hangi bağlamdan geldiğini tespit et (teşhis için).

    Arka plan job'u (request yok) → kind=JOB
    Agent API (X-Agent-Key) → kind=AGENT_API
    Kullanıcı oturumu → kind=USER
    Oturumsuz request → kind=REQUEST
    Asla exception fırlatmaz; her şey boşsa {} döner.
    """
    try:
        if not has_request_context():
            return {"kind": "JOB"}
        from flask import request

        endpoint = getattr(request, "endpoint", None)
        blueprint = getattr(request, "blueprint", None)
        try:
            has_agent_key = bool(request.headers.get("X-Agent-Key"))
        except Exception:
            has_agent_key = False
        uid = _current_user_id()

        if has_agent_key:
            kind = "AGENT_API"
        elif uid:
            kind = "USER"
        else:
            kind = "REQUEST"

        origin = {
            "kind": kind,
            "endpoint": endpoint,
            "blueprint": blueprint,
            "agent_key": has_agent_key,
        }
        if uid:
            origin["user_id"] = uid
        return origin
    except Exception:
        return {}


def _origin_source(origin: dict) -> str:
    """origin dict'inden audit `source` etiketi türet."""
    kind = (origin or {}).get("kind")
    if kind == "AGENT_API":
        return "AGENT_API"
    if kind == "USER":
        return "USER"
    if kind == "REQUEST":
        ep = (origin or {}).get("endpoint")
        return (f"REQ:{ep}"[:32]) if ep else "REQUEST"
    if kind == "JOB":
        return "JOB"
    return "SYSTEM"


def _snapshot(barcode: str | None, sa_sess: SaSession) -> tuple[int | None, int | None]:
    """Verilen barkod için (central_qty, raf_total) anlık değer."""
    if not barcode:
        return None, None
    try:
        cs = sa_sess.get(CentralStock, barcode)
        central = int(cs.qty) if cs else 0
    except Exception:
        central = None
    try:
        raf_total = (
            sa_sess.query(func.coalesce(func.sum(RafUrun.adet), 0))
            .filter(RafUrun.urun_barkodu == barcode, RafUrun.adet > 0)
            .scalar()
        )
        raf_total = int(raf_total or 0)
    except Exception:
        raf_total = None
    return central, raf_total


def log_event(
    event_type: str,
    *,
    order_number: str | None = None,
    package_number: str | None = None,
    barcode: str | None = None,
    quantity: int | None = None,
    central_qty_before: int | None = None,
    central_qty_after: int | None = None,
    raf_total_before: int | None = None,
    raf_total_after: int | None = None,
    raf_kodu: str | None = None,
    status_from: str | None = None,
    status_to: str | None = None,
    source: str | None = None,
    user_id: int | None = None,
    severity: str = "info",
    message: str | None = None,
    details: dict | None = None,
    snapshot: bool = False,
) -> int | None:
    """Tek event yazar. Asıl akışı kırmaz.

    snapshot=True olursa (barcode verildiyse) `central_qty_after` ve
    `raf_total_after` o anki gerçek değerlerden doldurulur — `_before`
    alanı zaten verildiyse korunur.
    """
    if severity not in VALID_SEVERITY:
        severity = "info"

    if user_id is None:
        user_id = _current_user_id()

    sa_sess = SaSession(bind=_bind())
    try:
        if snapshot and barcode:
            cur_central, cur_raf = _snapshot(barcode, sa_sess)
            if central_qty_after is None:
                central_qty_after = cur_central
            if raf_total_after is None:
                raf_total_after = cur_raf

        row = OrderAuditLog(
            ts=datetime.utcnow(),
            order_number=str(order_number) if order_number else None,
            package_number=str(package_number) if package_number else None,
            barcode=str(barcode) if barcode else None,
            event_type=event_type,
            central_qty_before=central_qty_before,
            central_qty_after=central_qty_after,
            raf_total_before=raf_total_before,
            raf_total_after=raf_total_after,
            raf_kodu=raf_kodu,
            status_from=status_from,
            status_to=status_to,
            quantity=quantity,
            source=source,
            user_id=user_id,
            severity=severity,
            message=message,
            details=details,
        )
        sa_sess.add(row)
        sa_sess.commit()
        return row.id
    except Exception:
        sa_sess.rollback()
        logger.exception("[ORDER_AUDIT] log_event yazma hatası")
        return None
    finally:
        sa_sess.close()


def log_many(events: list[dict]) -> int:
    """Birden çok event'i tek transaction'da yazar.

    Her dict, ``log_event`` argümanlarıyla aynıdır (ama snapshot=True
    gibi yan etkiler tek tek hesaplanır).
    """
    if not events:
        return 0
    sa_sess = SaSession(bind=_bind())
    written = 0
    try:
        for ev in events:
            if ev.get("snapshot") and ev.get("barcode"):
                c, r = _snapshot(ev["barcode"], sa_sess)
                ev.setdefault("central_qty_after", c)
                ev.setdefault("raf_total_after", r)
            ev_clean = {k: v for k, v in ev.items() if k != "snapshot"}
            sev = ev_clean.get("severity", "info")
            if sev not in VALID_SEVERITY:
                ev_clean["severity"] = "info"
            ev_clean.setdefault("user_id", _current_user_id())
            ev_clean["ts"] = datetime.utcnow()
            sa_sess.add(OrderAuditLog(**ev_clean))
            written += 1
        sa_sess.commit()
    except Exception:
        sa_sess.rollback()
        logger.exception("[ORDER_AUDIT] log_many yazma hatası")
        return 0
    finally:
        sa_sess.close()
    return written


# ════════════════════════════════════════════════════════════════════
# Otomatik dinleyiciler — CentralStock ve RafUrun değiştiğinde
# audit log'a işle. Aynı session'ın info dict'ine snapshot bırakırız,
# after_commit aşamasında bağımsız session ile yazarız.
# ════════════════════════════════════════════════════════════════════

_STOCK_KEY = "_audit_stock_changes"
_RAF_KEY = "_audit_raf_changes"


def _track_central_change(mapper, connection, target):
    sess = db.session
    # Eski qty'i state'den almaya çalış
    try:
        from sqlalchemy import inspect
        ins = inspect(target)
        hist = ins.attrs.qty.history
        old = hist.deleted[0] if hist.deleted else (target.qty if hist.added else None)
    except Exception:
        old = None
    sess.info.setdefault(_STOCK_KEY, []).append(
        {"barcode": target.barcode, "old": old, "new": target.qty,
         "origin": _request_origin()}
    )


def _track_raf_change(mapper, connection, target):
    sess = db.session
    sess.info.setdefault(_RAF_KEY, []).append(
        {
            "barcode": target.urun_barkodu,
            "raf_kodu": target.raf_kodu,
            "adet": target.adet,
            "origin": _request_origin(),
        }
    )


def _flush_audit_after_commit(sess):
    stock_changes = sess.info.pop(_STOCK_KEY, None) or []
    raf_changes = sess.info.pop(_RAF_KEY, None) or []
    if not stock_changes and not raf_changes:
        return

    events: list[dict] = []
    for ch in stock_changes:
        try:
            old = int(ch["old"]) if ch["old"] is not None else None
        except (TypeError, ValueError):
            old = None
        try:
            new = int(ch["new"]) if ch["new"] is not None else None
        except (TypeError, ValueError):
            new = None
        if old == new:
            continue
        origin = ch.get("origin") or {}
        events.append(
            {
                "event_type": "stock_changed",
                "barcode": ch["barcode"],
                "central_qty_before": old,
                "central_qty_after": new,
                "source": _origin_source(origin),
                "severity": "info",
                "message": f"CentralStock {old} → {new}",
                "details": {"origin": origin},
                "snapshot": False,
            }
        )
    # Raf hareketlerini barkod bazında özetle
    by_barcode: dict[str, list[dict]] = {}
    for ch in raf_changes:
        by_barcode.setdefault(ch["barcode"], []).append(ch)
    for bc, lst in by_barcode.items():
        origin = next((c.get("origin") for c in lst if c.get("origin")), {}) or {}
        events.append(
            {
                "event_type": "raf_changed",
                "barcode": bc,
                "source": _origin_source(origin),
                "severity": "info",
                "message": f"{len(lst)} raf satırı değişti",
                "details": {"changes": lst, "origin": origin},
                "snapshot": True,  # current after değerini doldursun
            }
        )

    if events:
        log_many(events)


def install_listeners() -> None:
    """app context içinde bir kez çağrılır — event listener'ları kayda geçer."""
    event.listen(CentralStock, "after_insert", _track_central_change)
    event.listen(CentralStock, "after_update", _track_central_change)

    # RafUrun değişimlerini de — daha önce CentralStock event'i raf değişiminden
    # tetiklenip orayı zaten loglayacak; raf event'leri ayrıca rafların kendi
    # hareketlerini takip etmek için.
    event.listen(RafUrun, "after_insert", _track_raf_change)
    event.listen(RafUrun, "after_update", _track_raf_change)
    event.listen(RafUrun, "after_delete", _track_raf_change)

    event.listen(db.session, "after_commit", _flush_audit_after_commit)

    logger.info("[ORDER_AUDIT] event listeners yüklendi.")


def ensure_table_exists() -> None:
    """Tablo yoksa oluştur (Alembic migration çalışmadıysa yedek)."""
    try:
        OrderAuditLog.__table__.create(bind=_bind(), checkfirst=True)
    except Exception:
        logger.exception("[ORDER_AUDIT] tablo oluşturma hatası")
