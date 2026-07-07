"""time_utils — naive-UTC → Europe/Istanbul çeviri/format testleri."""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from time_utils import to_ist, fmt_ist, ist_to_utc, IST  # noqa: E402


def test_naive_assumed_utc_shifts_to_istanbul():
    # 12:00 UTC → 15:00 İstanbul (UTC+3, DST yok)
    d = to_ist(datetime(2026, 7, 7, 12, 0, 0))
    assert (d.hour, d.minute) == (15, 0)
    assert d.utcoffset() == timedelta(hours=3)


def test_tz_aware_utc_converts():
    d = to_ist(datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc))
    assert d.hour == 15


def test_tz_aware_already_istanbul_unchanged_wallclock():
    src = datetime(2026, 7, 7, 15, 0, tzinfo=IST)
    d = to_ist(src)
    assert d.hour == 15  # aynı duvar saati


def test_winter_also_plus_three():
    # Türkiye 2016'dan beri kalıcı UTC+3 (DST yok)
    d = to_ist(datetime(2026, 1, 15, 9, 0, 0))
    assert d.hour == 12


def test_none_and_invalid():
    assert to_ist(None) is None
    assert to_ist("2026-07-07") is None
    assert fmt_ist(None) == ""
    assert fmt_ist("x") == ""


def test_fmt_default_and_custom():
    dt = datetime(2026, 7, 7, 12, 5, 0)  # → 15:05 İstanbul
    assert fmt_ist(dt) == "07.07.2026 15:05"
    assert fmt_ist(dt, "%H:%M") == "15:05"


# ── ist_to_utc (kasa formu / ay sınırı → saklama) ───────────────────────
def test_ist_to_utc_subtracts_three():
    u = ist_to_utc(datetime(2026, 7, 7, 14, 20))  # İstanbul 14:20 → UTC 11:20
    assert (u.hour, u.minute) == (11, 20)
    assert u.tzinfo is None  # naive UTC (naive kolona yazmak için)


def test_ist_to_utc_roundtrip_wallclock():
    # Kullanıcının girdiği İstanbul saati, sakla→göster sonrası AYNI görünmeli
    x = datetime(2026, 7, 7, 14, 20)
    back = to_ist(ist_to_utc(x)).replace(tzinfo=None)
    assert back == x


def test_ist_to_utc_month_boundary():
    # İstanbul ay başı 00:00 → UTC önceki gün 21:00 (filtre sınırı bu şekilde kayar)
    b = ist_to_utc(datetime(2026, 7, 1, 0, 0))
    assert (b.month, b.day, b.hour) == (6, 30, 21)


def test_ist_to_utc_none():
    assert ist_to_utc(None) is None
    assert ist_to_utc("x") is None
