# stock_alert_service.py
"""
Rafta bulunmayan (stoksuz) siparişler için mail uyarıları.

- ANLIK:    Sipariş stok yetersizliğinden hazırlanamadığında (terfi edilemediğinde),
            o sipariş için bir kez 'bu siparişin stoğu yok' maili gider (cooldown:
            OrderCreated.stok_yok_mail_at ile bir daha gönderilmez).
- PERİYODİK: Günlük olarak, o an stoksuz bekleyen TÜM siparişlerin hatırlatma özeti.

İkisi de mevcut bildirim aboneliği üzerinden gider (mail_service.notify → ilgili
olaya abone kullanıcılara). Sipariş bazlı içerik.
"""
import json
import logging
from datetime import datetime

from models import db, OrderCreated
from mail_service import build_stock_shortage_email, notify

logger = logging.getLogger(__name__)


def _order_to_info(order):
    """OrderCreated → mail için sipariş bilgisi (sipariş no, müşteri, ürünler)."""
    products = []
    try:
        details = json.loads(order.details) if isinstance(order.details, str) else (order.details or [])
        if isinstance(details, list):
            for d in details:
                products.append({
                    'sku': d.get('sku') or d.get('merchantSku') or '-',
                    'barcode': d.get('barcode') or '-',
                    'quantity': d.get('quantity', 1),
                })
    except (json.JSONDecodeError, TypeError):
        pass
    return {
        'order_number': order.order_number,
        'customer_name': ' '.join(filter(None, [order.customer_name, order.customer_surname])) or '-',
        'source': getattr(order, 'source', 'TRENDYOL'),
        'agreed': order.agreed_delivery_date.strftime('%d.%m.%Y %H:%M') if order.agreed_delivery_date else '-',
        'products': products,
    }


def alert_uncovered_orders(orders):
    """
    ANLIK: terfi edilemeyen (stoksuz) siparişlerden HENÜZ bildirilmemiş olanlar için
    tek bir mail gönderir ve onları işaretler. orders: OrderCreated listesi.
    """
    fresh = [o for o in orders if not getattr(o, 'stok_yok_mail_at', None)]
    if not fresh:
        return 0
    try:
        infos = [_order_to_info(o) for o in fresh]
        body = build_stock_shortage_email(
            'stok_yok_siparis',
            headline=f'{len(fresh)} sipariş stok yetersizliğinden hazırlanamadı.',
            orders=infos,
        )
        notify('stok_yok_siparis',
               subject=f'⚠️ {len(fresh)} sipariş stoksuz — hazırlanamıyor',
               body=body)
        now = datetime.utcnow()
        for o in fresh:
            o.stok_yok_mail_at = now
        db.session.commit()
        logger.info(f"[STOK-UYARI] Anlık: {len(fresh)} sipariş için stok-yok maili gönderildi.")
        return len(fresh)
    except Exception as e:
        db.session.rollback()
        logger.error(f"[STOK-UYARI] Anlık mail hatası: {e}", exc_info=True)
        return 0


def _currently_uncovered():
    """O an stoksuz bekleyen (fiziksel karşılanamayan) orders_created siparişleri."""
    from promotion_service import _physical_central, _committed_in_hazirlaniyor, _order_can_be_covered
    central = _physical_central()
    committed = _committed_in_hazirlaniyor()
    available = {bc: central.get(bc, 0) - committed.get(bc, 0) for bc in set(central) | set(committed)}
    uncovered = []
    for order in OrderCreated.query.all():
        ok, _need = _order_can_be_covered(order, available)
        if not ok:
            uncovered.append(order)
    return uncovered


def send_periodic_reminder():
    """PERİYODİK: o an stoksuz bekleyen tüm siparişlerin hatırlatma özeti (günlük)."""
    try:
        uncovered = _currently_uncovered()
        if not uncovered:
            logger.info("[STOK-UYARI] Periyodik: stoksuz bekleyen sipariş yok, mail atlanıyor.")
            return 0
        infos = [_order_to_info(o) for o in uncovered]
        body = build_stock_shortage_email(
            'stok_yok_hatirlatma',
            headline=f'{len(uncovered)} sipariş stok bekliyor (rafta ürün yok).',
            orders=infos,
        )
        notify('stok_yok_hatirlatma',
               subject=f'📋 {len(uncovered)} sipariş stok bekliyor — hatırlatma',
               body=body)
        logger.info(f"[STOK-UYARI] Periyodik: {len(uncovered)} sipariş için hatırlatma maili gönderildi.")
        return len(uncovered)
    except Exception as e:
        logger.error(f"[STOK-UYARI] Periyodik mail hatası: {e}", exc_info=True)
        return 0
