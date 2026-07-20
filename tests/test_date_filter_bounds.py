"""Takvim-günü filtreleri: İstanbul günü → UTC sınır.

Kullanıcı "2026-07-20" seçtiğinde kastettiği **İstanbul** takvim günüdür
(00:00–23:59:59 IST). DB'deki `order_date`/`return_date` ise naive UTC.
Sınır çevrilmezse gün 3 saat kayar ve yerel 00:00–03:00 arası siparişler
bir önceki güne düşer.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from time_utils import ist_to_utc, to_ist  # noqa: E402


def test_gun_basi_utc_sinirina_cevrilir():
    """İstanbul 20.07 00:00 → UTC 19.07 21:00."""
    sinir = ist_to_utc(datetime.strptime("2026-07-20", "%Y-%m-%d"))
    assert sinir == datetime(2026, 7, 19, 21, 0, 0)


def test_gun_sonu_sinirinin_ust_ucu():
    """İstanbul 20.07 23:59:59.999999 → UTC 20.07 20:59:59.999999."""
    ust = datetime.strptime("2026-07-20", "%Y-%m-%d") + timedelta(days=1, microseconds=-1)
    assert ist_to_utc(ust) == datetime(2026, 7, 20, 20, 59, 59, 999999)


def test_gece_yarisi_siparisi_dogru_gune_dusuyor():
    """İstanbul 20.07 01:30'da verilen sipariş (UTC 19.07 22:30) 20 Temmuz'a ait."""
    siparis_utc = datetime(2026, 7, 19, 22, 30)          # = 20.07 01:30 IST
    alt = ist_to_utc(datetime.strptime("2026-07-20", "%Y-%m-%d"))
    ust = ist_to_utc(datetime.strptime("2026-07-20", "%Y-%m-%d")
                     + timedelta(days=1, microseconds=-1))
    assert alt <= siparis_utc <= ust

    # Çevrim yapılmasaydı (eski hatalı davranış) bu sipariş aralığın DIŞINDA kalırdı
    ham_alt = datetime.strptime("2026-07-20", "%Y-%m-%d")
    assert not (ham_alt <= siparis_utc)


def test_aksam_siparisi_ertesi_gune_kaymaz():
    """İstanbul 20.07 23:30 (UTC 20.07 20:30) hâlâ 20 Temmuz'a ait."""
    siparis_utc = datetime(2026, 7, 20, 20, 30)
    ust = ist_to_utc(datetime.strptime("2026-07-20", "%Y-%m-%d")
                     + timedelta(days=1, microseconds=-1))
    assert siparis_utc <= ust


def test_istanbul_gun_basi_hesabi():
    """agent_api 'bugünkü siparişler' sınırı: IST gün başı → UTC."""
    an_utc = datetime(2026, 7, 20, 1, 30)   # IST 04:30, yani gün 20 Temmuz
    ist_gun_basi = to_ist(an_utc).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )
    assert ist_gun_basi == datetime(2026, 7, 20, 0, 0)
    assert ist_to_utc(ist_gun_basi) == datetime(2026, 7, 19, 21, 0)


def test_gece_yarisi_oncesi_utc_ani_dogru_istanbul_gunu():
    """UTC 19.07 22:00 aslında IST 20.07 01:00 → 'bugün' 20 Temmuz olmalı."""
    an_utc = datetime(2026, 7, 19, 22, 0)
    assert to_ist(an_utc).date() == datetime(2026, 7, 20).date()
