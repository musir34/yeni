"""Kullanıcı hareketleri + sipariş izi sürme — zaman gösterimi İstanbul olmalı.

DB konvansiyonu: naive timestamp = UTC (`UserLog.timestamp`, `OrderAuditLog.ts`,
`StockMovement.created_at` hepsi `datetime.utcnow` ile yazılıyor). Bu ekranlar
zamanı sunucuda metne çeviriyor; ham `strftime` kullanılırsa panelde 3 saat
GERİDE görünür. Çeviri `time_utils.fmt_ist`/`to_ist` ile yapılmalı.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from types import SimpleNamespace  # noqa: E402

from order_audit_routes import _serialize_order_row, _ts  # noqa: E402
from time_utils import fmt_ist, to_ist  # noqa: E402

UTC_DEGER = datetime(2026, 7, 20, 10, 15, 0)   # naive UTC
IST_METIN = "2026-07-20 13:15:00"               # beklenen İstanbul gösterimi


def test_ts_naive_utc_istanbula_cevrilir():
    assert _ts(UTC_DEGER) == IST_METIN


def test_ts_none_bos_string():
    assert _ts(None) == ""


def test_ts_datetime_olmayan_deger_korunur():
    """Beklenmedik tipte veri gelirse eski davranış (düz metin) sürmeli."""
    assert _ts("elde-yazilmis") == "elde-yazilmis"
    assert _ts(0) == ""


def test_user_log_export_tarihi_istanbul():
    """user_logs Excel çıktısındaki 'Tarih' kolonu ile aynı format."""
    assert fmt_ist(UTC_DEGER, '%Y-%m-%d %H:%M:%S') == IST_METIN


def test_serialize_order_row_zamanlari_istanbul_gosterir():
    """İz sürme ekranının satır serileştirmesi — ham UTC basılırsa 3 saat geride kalır."""
    row = SimpleNamespace(
        id=1, order_number="11431155266", package_number="P1", status="Created",
        order_date=UTC_DEGER, created_at=UTC_DEGER, updated_at=UTC_DEGER,
        picking_start_time=UTC_DEGER,
    )
    out = _serialize_order_row(row, "orders_created")
    for alan in ("order_date", "created_at", "updated_at", "picking_start_time"):
        assert out[alan] == IST_METIN, alan


def test_serialize_order_row_bos_zaman():
    row = SimpleNamespace(id=1, order_number="X", order_date=None, picking_start_time=None)
    out = _serialize_order_row(row, "orders_created")
    assert out["order_date"] == ""
    assert out["picking_start_time"] is None


def test_isoformat_ofset_tasir():
    """Makine tüketicisi için ISO çıktı +03:00 ofsetini taşımalı (tek anlamlı)."""
    iso = to_ist(UTC_DEGER).isoformat()
    assert iso.startswith("2026-07-20T13:15:00")
    assert iso.endswith("+03:00")
