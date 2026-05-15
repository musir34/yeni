# -*- coding: utf-8 -*-
"""Yeni audit bağlamı sonrası: stock_changed/raf_changed olaylarının KAYNAK kırılımı.

Kullanım: kod canlıya çıkıp birkaç saat trafik aldıktan sonra çalıştır.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from datetime import datetime, timedelta
from app import app
from models import db, OrderAuditLog
from sqlalchemy import func

HOURS = int(os.getenv("HOURS", "6"))

with app.app_context():
    since = datetime.utcnow() - timedelta(hours=HOURS)
    q = (db.session.query(OrderAuditLog.event_type, OrderAuditLog.source, func.count())
         .filter(OrderAuditLog.ts >= since,
                 OrderAuditLog.event_type.in_(["stock_changed", "raf_changed"]))
         .group_by(OrderAuditLog.event_type, OrderAuditLog.source)
         .order_by(func.count().desc()))
    print(f"=== Son {HOURS} saat: stock_changed/raf_changed KAYNAK kırılımı ===")
    for et, src, c in q.all():
        print(f"  {et:<16} {str(src):<24} {c}")

    # Central ARTIŞ (cb<ca) olaylarını kaynağa göre — fiziksel olmayan şişme
    print(f"\n=== Central ARTIŞ (cb < ca) son {HOURS} saat, kaynağa göre ===")
    rows = (db.session.query(OrderAuditLog.source, func.count())
            .filter(OrderAuditLog.ts >= since,
                    OrderAuditLog.event_type == "stock_changed",
                    OrderAuditLog.central_qty_after > OrderAuditLog.central_qty_before)
            .group_by(OrderAuditLog.source)
            .order_by(func.count().desc()).all())
    for src, c in rows:
        print(f"  {str(src):<24} {c}")

    # Örnek: AGENT_API kaynaklı son artışlar + origin detayı
    print("\n=== Örnek AGENT_API / REQ kaynaklı son 15 central artışı ===")
    ex = (db.session.query(OrderAuditLog)
          .filter(OrderAuditLog.ts >= since,
                  OrderAuditLog.event_type == "stock_changed",
                  OrderAuditLog.central_qty_after > OrderAuditLog.central_qty_before,
                  OrderAuditLog.source.notin_(["JOB", "SYSTEM"]))
          .order_by(OrderAuditLog.ts.desc()).limit(15).all())
    for r in ex:
        org = (r.details or {}).get("origin") if isinstance(r.details, dict) else None
        print(f"  {r.ts} bc={r.barcode} {r.central_qty_before}->{r.central_qty_after} "
              f"src={r.source} origin={org}")
