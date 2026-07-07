"""Merkezi saat dilimi yardımcıları.

KONVANSİYON
-----------
Veritabanındaki **naive** (tz-bilgisiz) timestamp'lar **UTC** kabul edilir:
- Trendyol `order_date` epoch → ``datetime.utcfromtimestamp`` (UTC)
- Uygulama içi yazımlar → ``datetime.utcnow()`` (UTC)

Gösterimde her zaman **Europe/Istanbul**'a çevrilir. Bu kural
``canli_panel.ASSUME_DB_UTC=True`` ile birebir aynıdır. Sunucu OS'i UTC olduğu
için naive UTC saklamak doğru; tek görev gösterimde çevirmek.

Kullanım (Jinja):
    {{ order.order_date | ist }}            → "07.07.2026 18:56"
    {{ order.toplandi_at | ist('%H:%M') }}  → "18:56"
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Europe/Istanbul")
UTC = timezone.utc

DEFAULT_FMT = "%d.%m.%Y %H:%M"


def to_ist(dt):
    """Datetime → Europe/Istanbul tz-aware.

    - Naive datetime UTC varsayılır (konvansiyon) ve İstanbul'a çevrilir.
    - tz-aware datetime doğrudan İstanbul'a çevrilir.
    - datetime olmayan / None → None.
    """
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)


def fmt_ist(dt, fmt: str = DEFAULT_FMT) -> str:
    """Datetime → İstanbul saatinde formatlanmış string. None/geçersiz → ''."""
    d = to_ist(dt)
    return d.strftime(fmt) if d else ""


def ist_to_utc(dt):
    """İstanbul-yerel datetime → **naive UTC** (saklamak için).

    Kullanıcı formundan gelen (datetime-local / '%Y-%m-%d') naive değer İstanbul
    kabul edilir ve UTC'ye çevrilip tz-bilgisi düşürülür (naive UTC kolonlara
    yazmak için). tz-aware girdi de UTC'ye çevrilir. datetime olmayan/None → None.

    ``to_ist`` ile ters işlemdir: ``to_ist(ist_to_utc(x))`` aynı duvar saatini verir.
    """
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(UTC).replace(tzinfo=None)
