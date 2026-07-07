"""İptal-eğilimli ürünler için otomatik listeleme tamponu politikası.

SORUN
-----
Çok satan ürünler fiziksel stokta sık sık 1-2 adede/0'a düşüyor. Pazaryeri ilanı
bir sonraki senkrona kadar "var" görünürken ikinci bir müşteri son adedi sipariş
ediyor → toplarken ürün kalmamış → **iptal** zorunlu kalıyor (son-adet yarışı).

ÇÖZÜM
-----
Barkod bazlı **ekstra listeleme tamponu**. Pazaryerine gönderilen adet:
``max(0, stok - rezerv - (global_tampon + extra_buffer))``. ``extra_buffer=2`` olan
bir SKU'da son 2 adet ilana açılmaz; ilan ancak stok ≥3 olunca açılır → aynı
senkron penceresinde iki sipariş gelip biri iptal edilmez.

Politika, son ``days`` gündeki iptal geçmişinden **otomatik** türetilir
(``refresh_policies``): ``min_cancels``+ iptali olan barkodlara ``extra_buffer``
uygulanır; ürün artık eğilimli değilse otomatik kayıt temizlenir. Operatörün elle
koyduğu (``auto=False``) kayıtlar korunur.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func

from models import db, OrderCancelled, StockListingPolicy

logger = logging.getLogger(__name__)

DEFAULT_DAYS = 30
DEFAULT_MIN_CANCELS = 2
DEFAULT_EXTRA_BUFFER = 2


def compute_cancel_prone(
    days: int = DEFAULT_DAYS,
    min_cancels: int = DEFAULT_MIN_CANCELS,
    now: datetime | None = None,
) -> dict[str, int]:
    """Son ``days`` günde ``>= min_cancels`` iptali olan barkodları döndürür.

    Args:
        now: referans zaman (test için enjekte edilebilir); yoksa ``utcnow``.

    Returns:
        ``{barcode: cancel_count}`` — eşiği geçen barkodlar.
    """
    ref = now or datetime.utcnow()
    cutoff = ref - timedelta(days=days)
    rows = (
        db.session.query(
            OrderCancelled.product_barcode,
            func.count().label("n"),
        )
        .filter(
            OrderCancelled.order_date >= cutoff,
            OrderCancelled.product_barcode.isnot(None),
            OrderCancelled.product_barcode != "",
        )
        .group_by(OrderCancelled.product_barcode)
        .having(func.count() >= min_cancels)
        .all()
    )
    return {b: int(n) for b, n in rows if b}


def refresh_policies(
    days: int = DEFAULT_DAYS,
    min_cancels: int = DEFAULT_MIN_CANCELS,
    extra_buffer: int = DEFAULT_EXTRA_BUFFER,
    now: datetime | None = None,
    commit: bool = True,
) -> dict:
    """İptal geçmişinden otomatik listeleme politikalarını günceller.

    - Eğilimli barkodlara ``auto=True`` politika ekler/günceller (``extra_buffer``).
    - Artık eğilimli olmayan ESKİ otomatik kayıtları temizler (auto-expire).
    - ``auto=False`` (elle) kayıtlara DOKUNMAZ.

    Returns:
        ``{"prone": n, "changed": n, "expired": n}`` özeti.
    """
    prone = compute_cancel_prone(days=days, min_cancels=min_cancels, now=now)
    existing = {p.barcode: p for p in StockListingPolicy.query.all()}

    changed = 0
    reason = f"son {days} günde {{n}} iptal (auto)"
    for bc, cnt in prone.items():
        p = existing.get(bc)
        if p is None:
            db.session.add(StockListingPolicy(
                barcode=bc, extra_buffer=extra_buffer, cancel_count=cnt,
                reason=reason.format(n=cnt), auto=True,
            ))
            changed += 1
        elif p.auto:
            if p.extra_buffer != extra_buffer or p.cancel_count != cnt:
                p.extra_buffer = extra_buffer
                p.cancel_count = cnt
                p.reason = reason.format(n=cnt)
                changed += 1
        # auto=False (elle) kayıt: dokunma

    expired = 0
    for bc, p in existing.items():
        if p.auto and bc not in prone:
            db.session.delete(p)
            expired += 1

    if commit:
        db.session.commit()
    return {"prone": len(prone), "changed": changed, "expired": expired}


def get_extra_buffer_map() -> dict[str, int]:
    """Barkod → ekstra listeleme tamponu haritası (yalnız buffer>0).

    Tablo henüz oluşmadıysa (migration uygulanmamış) sessizce boş harita döner —
    senkron eski davranışıyla (yalnız global tampon) çalışmaya devam eder.
    """
    try:
        rows = StockListingPolicy.query.all()
    except Exception:
        logger.exception("[LISTING-POLICY] tablo okunamadı (yutuldu, boş harita)")
        db.session.rollback()
        return {}
    return {p.barcode: int(p.extra_buffer or 0) for p in rows if (p.extra_buffer or 0) > 0}
