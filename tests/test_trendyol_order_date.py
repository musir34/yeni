"""Trendyol epoch → naive UTC dönüşümü.

Trendyol'un `orderDate` epoch değeri gerçek UTC epoch DEĞİL; İstanbul duvar
saatini kodluyor. Kanıt (2026-07-20, sipariş 11431155266):

    raw orderDate ms : 1784553305943
    utcfromtimestamp : 2026-07-20 13:15:05.943   ← Trendyol panelindeki saat
    gerçek UTC (o an): 2026-07-20 12:41:16       ← yani 34 dk "gelecekte"
    created_at (DB)  : 2026-07-20 10:18:16       ← siparişi çektiğimiz an

Sipariş, kendisini çektiğimiz andan 3 saat sonra oluşmuş olamaz; dolayısıyla
gerçek an 10:15:05 UTC'dir. DB konvansiyonu naive=UTC olduğu için ingest bu
değeri UTC'ye çevirerek yazmalı.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from order_service import combine_line_items  # noqa: E402

# Gerçek siparişten alınan ham değerler
ORDER_DATE_MS = 1784553305943          # Trendyol panelinde 20.07.2026 13:15
BEKLENEN_UTC = datetime(2026, 7, 20, 10, 15, 5, 943000)


def _order(**extra):
    data = {'orderNumber': '11431155266', 'orderDate': ORDER_DATE_MS, 'lines': []}
    data.update(extra)
    return data


def test_order_date_naive_utc_olarak_yazilir():
    rec = combine_line_items(_order(), 'Created')
    assert rec['order_date'] == BEKLENEN_UTC
    assert rec['order_date'].tzinfo is None  # naive UTC (kolon naive)


def test_order_date_ingest_aninin_gerisinde_kalir():
    """Sipariş tarihi, siparişi gördüğümüz andan ileride olamaz."""
    rec = combine_line_items(_order(), 'Created')
    created_at = datetime(2026, 7, 20, 10, 18, 16)  # gerçek ingest anı (UTC)
    assert rec['order_date'] <= created_at


def test_diger_tarih_alanlari_da_cevrilir():
    rec = combine_line_items(_order(
        agreedDeliveryDate=ORDER_DATE_MS,
        estimatedDeliveryStartDate=ORDER_DATE_MS,
        estimatedDeliveryEndDate=ORDER_DATE_MS,
        originShipmentDate=ORDER_DATE_MS,
    ), 'Created')
    for alan in ('agreed_delivery_date', 'estimated_delivery_start',
                 'estimated_delivery_end', 'origin_shipment_date'):
        assert rec[alan] == BEKLENEN_UTC, alan


def test_bos_timestamp_none_kalir():
    rec = combine_line_items(_order(orderDate=None, agreedDeliveryDate=0), 'Created')
    assert rec['order_date'] is None
    assert rec['agreed_delivery_date'] is None


# ── İade tarafı: claims API epoch'u FARKLI davranıyor ───────────────────
# orders API → İstanbul duvar saati kodluyor (yukarıdaki testler).
# claims API → GERÇEK UTC epoch. Kanıt zinciri:
#   1) DB'deki return_date = utcfromtimestamp(claimDate) + 3 (API↔DB eşleştirmesiyle
#      ölçüldü; eski kod fromtimestamp + app.py TZ=Europe/Istanbul).
#   2) return_date histogramının dibi 05:00 → utcfromtimestamp(claimDate) dibi
#      02:00 UTC = 05:00 İstanbul → yani decode edilen değer gerçek UTC.
# Bu yüzden claimDate'e ist_to_utc UYGULANMAZ; doğrudan utcfromtimestamp doğrudur.
def test_claim_date_dogrudan_utc_kabul_edilir():
    from datetime import timezone

    ms = 1784553305943
    beklenen = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)
    assert datetime.utcfromtimestamp(ms / 1000) == beklenen


def test_iade_modulu_ist_to_utc_uygulamaz():
    """Regresyon: claimDate'e ist_to_utc uygulanırsa 3 saat eksik yazılır."""
    import iade_islemleri

    assert not hasattr(iade_islemleri, "ist_to_utc"), (
        "iade_islemleri claimDate'i ist_to_utc ile çevirmemeli — claims epoch'u zaten UTC"
    )
