# overdue_orders.py
"""Geciken (teslimata kalan süresi dolmuş) sipariş hesaplamaları.

Geciken sipariş = Yeni / Hazırlanıyor / İşleme Alındı statüsünde olup teslim
son tarihi geçmiş sipariş. Teslim son tarihi: agreed_delivery_date, yoksa
estimated_delivery_end.

Tarihler veritabanında UTC (naive) saklanır (order_service.ts_to_dt ->
datetime.utcfromtimestamp), bu yüzden karşılaştırma datetime.utcnow() ile
yapılır. Bu, order_list.html'deki "data-end-time + 'Z'" (UTC) canlı sayaç ve
"Süre Doldu" gösterimi ile birebir tutarlıdır.
"""
from datetime import datetime

from sqlalchemy import func

from models import db, OrderCreated, OrderHazirlaniyor, OrderPicking

# (anahtar, model, görünen ad) — geciken kontrolü yapılan 3 statü
OVERDUE_STATUSES = (
    ('created', OrderCreated, 'Yeni'),
    ('hazirlaniyor', OrderHazirlaniyor, 'Hazırlanıyor'),
    ('picking', OrderPicking, 'İşleme Alındı'),
)

# Model -> order_list.html'in beklediği status kodu (translated_status map'i ile uyumlu)
STATUS_CODE = {
    'created': 'Created',
    'hazirlaniyor': 'Hazirlaniyor',
    'picking': 'Picking',
}


def deadline_expr(model):
    """Teslim son tarihi ifadesi: agreed_delivery_date, yoksa estimated_delivery_end."""
    return func.coalesce(model.agreed_delivery_date, model.estimated_delivery_end)


def overdue_counts():
    """Her statü için geciken (benzersiz order_number) sipariş adedi.

    Returns:
        {'created': int, 'hazirlaniyor': int, 'picking': int, 'total': int}
    """
    now = datetime.utcnow()
    counts = {}
    total = 0
    for key, model, _label in OVERDUE_STATUSES:
        d = deadline_expr(model)
        c = (
            db.session.query(func.count(func.distinct(model.order_number)))
            .filter(d.isnot(None), d < now)
            .scalar()
        ) or 0
        counts[key] = c
        total += c
    counts['total'] = total
    return counts


def overdue_orders_query(model):
    """Bir model için geciken siparişler; teslim tarihine göre en gecikmiş önce."""
    now = datetime.utcnow()
    d = deadline_expr(model)
    return model.query.filter(d.isnot(None), d < now).order_by(d.asc())
