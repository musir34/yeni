"""Stok Hareket Defteri (ledger) testleri — TDD.

İzole, dosya-tabanlı sqlite üzerinde çalışır; GERÇEK DB'ye dokunmaz.
RafUrun→CentralStock otomatik senk listener'ları ayrı session kullandığı için
:memory: değil tempfile sqlite gerekir.

Çalıştırma:
    DISABLE_JOBS=1 pytest tests/test_stock_ledger.py -v
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

# ── Test ortamı: gerçek DB'ye DOKUNMA ──────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_tmp_db = tempfile.NamedTemporaryFile(suffix="_ledger_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"
os.environ["WERKZEUG_RUN_MAIN"] = "false"

from flask import Flask  # noqa: E402
from sqlalchemy import event  # noqa: E402

from models import (  # noqa: E402
    db, Raf, RafUrun, CentralStock, OrderCreated, OrderPicking,
    OrderDelivered, OrderShipped, StockMovement, Product, BarcodeAlias,
    OrderAuditLog, OrderHazirlaniyor, OrderCancelled,
)
import stock_ledger as ledger  # noqa: E402

# Tam db.create_all() sqlite'da çift-index bug'ı yüzünden patlıyor (kod notu);
# yalnızca bu testlerin ihtiyaç duyduğu tabloları oluştur.
_NEEDED_TABLES = (
    Raf, RafUrun, CentralStock, StockMovement, Product, BarcodeAlias,
    OrderCreated, OrderHazirlaniyor, OrderPicking, OrderDelivered,
    OrderShipped, OrderCancelled, OrderAuditLog,
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)


def _install_sqlite_translate():
    """normalize_barcode() PostgreSQL translate() kullanıyor — SQLite UDF ekle."""
    @event.listens_for(db.engine, "connect")
    def _on_connect(dbapi_conn, _):
        if isinstance(dbapi_conn, sqlite3.Connection):
            def _translate(s, frm, to):
                return None if s is None else s.translate(str.maketrans(frm, to))
            dbapi_conn.create_function("translate", 3, _translate)


with app.app_context():
    _install_sqlite_translate()
    for _m in _NEEDED_TABLES:
        _m.__table__.create(bind=db.engine, checkfirst=True)


@pytest.fixture(autouse=True)
def _ctx_and_clean():
    """Her testte temiz tablolarla app context."""
    with app.app_context():
        for model in (StockMovement, RafUrun, CentralStock, OrderCreated,
                      OrderPicking, OrderDelivered, Raf):
            model.query.delete()
        db.session.commit()
        yield
        db.session.rollback()


# ── Yardımcılar ────────────────────────────────────────────────────────
def _seed_shelf(barcode="BC1", shelf="A1", adet=5):
    db.session.add(Raf(kod=shelf, ana="A", ikincil="1", kat="1"))
    db.session.add(RafUrun(raf_kodu=shelf, urun_barkodu=barcode, adet=adet))
    db.session.commit()


def _shelf_qty(barcode="BC1", shelf="A1"):
    rec = RafUrun.query.filter_by(raf_kodu=shelf, urun_barkodu=barcode).first()
    return rec.adet if rec else None


def _movements(barcode="BC1", reason=None):
    q = StockMovement.query.filter_by(barcode=barcode)
    if reason:
        q = q.filter_by(reason=reason)
    return q.all()


# ════════════════════════════════════════════════════════════════════════
# 1) ANA: Created→Shipped/Delivered fiziksel stoğu DÜŞMELİ (eksik olan davranış)
# ════════════════════════════════════════════════════════════════════════
def test_apply_created_to_delivered_decrements_stock():
    _seed_shelf(adet=5)
    res = ledger.apply_lifecycle_effect(
        order_number="O1", from_status="created", to_status="Delivered",
        details='[{"barcode":"BC1","quantity":2}]', shelf_code="A1",
    )
    assert _shelf_qty() == 3, "Created→Delivered'da raf 5→3 düşmeliydi"
    ship = _movements(reason="ship_out")
    assert len(ship) == 1 and ship[0].delta == -2


def test_apply_hazirlaniyor_to_shipped_decrements():
    _seed_shelf(adet=4)
    ledger.apply_lifecycle_effect(
        order_number="O2", from_status="hazirlaniyor", to_status="Shipped",
        details='[{"barcode":"BC1","quantity":1}]',
    )
    assert _shelf_qty() == 3
    assert len(_movements(reason="ship_out")) == 1


# ════════════════════════════════════════════════════════════════════════
# 2) Picking→Shipped: zaten pakette düşmüştü → TEKRAR DÜŞME
# ════════════════════════════════════════════════════════════════════════
def test_picking_to_shipped_no_double_decrement():
    _seed_shelf(adet=5)
    res = ledger.apply_lifecycle_effect(
        order_number="O3", from_status="picking", to_status="Shipped",
        details='[{"barcode":"BC1","quantity":2}]',
    )
    assert res == []
    assert _shelf_qty() == 5
    assert _movements(reason="ship_out") == []


# ════════════════════════════════════════════════════════════════════════
# 3) İdempotency: aynı geçiş iki kez → raf yalnızca bir kez düşer
# ════════════════════════════════════════════════════════════════════════
def test_idempotency_no_double_apply():
    _seed_shelf(adet=5)
    common = dict(order_number="O4", from_status="created", to_status="Shipped",
                  details='[{"barcode":"BC1","quantity":2}]')
    ledger.apply_lifecycle_effect(**common)
    second = ledger.apply_lifecycle_effect(**common)
    assert _shelf_qty() == 3, "İkinci çağrı raftan tekrar düşmemeliydi"
    assert all(not r.applied for r in second)
    assert len(_movements(reason="ship_out")) == 1


# ════════════════════════════════════════════════════════════════════════
# 4) Picking→Cancelled: pakette düşen stok rafa GERİ YÜKLENMELİ
# ════════════════════════════════════════════════════════════════════════
def test_picking_to_cancelled_restores():
    _seed_shelf(adet=2)
    ledger.apply_lifecycle_effect(
        order_number="O5", from_status="picking", to_status="Cancelled",
        details='[{"barcode":"BC1","quantity":3}]', shelf_code="A1",
    )
    assert _shelf_qty() == 5, "İptalde 2+3=5'e geri yüklenmeliydi"
    ret = _movements(reason="cancel_return")
    assert len(ret) == 1 and ret[0].delta == 3


# ════════════════════════════════════════════════════════════════════════
# 5) Created→Cancelled: sadece rezervdi → etki YOK
# ════════════════════════════════════════════════════════════════════════
def test_created_to_cancelled_no_effect():
    _seed_shelf(adet=5)
    res = ledger.apply_lifecycle_effect(
        order_number="O6", from_status="created", to_status="Cancelled",
        details='[{"barcode":"BC1","quantity":2}]',
    )
    assert res == []
    assert _shelf_qty() == 5
    assert _movements() == []


# ════════════════════════════════════════════════════════════════════════
# 6) record_movement mutate_shelf=False: rafı değiştirmez, sadece kaydeder
# ════════════════════════════════════════════════════════════════════════
def test_record_movement_no_mutate_just_logs():
    _seed_shelf(adet=5)
    r = ledger.record_movement(
        barcode="BC1", delta=-2, reason=ledger.REASON_PACK_OUT,
        order_number="O7", mutate_shelf=False,
    )
    assert r.applied and r.delta == -2
    assert _shelf_qty() == 5  # raf değişmedi
    assert len(_movements(reason="pack_out")) == 1


# ════════════════════════════════════════════════════════════════════════
# 7) Kısmi tahsis: stok yetersizse gerçekleşen delta kaydedilir, negatife düşmez
# ════════════════════════════════════════════════════════════════════════
def test_partial_allocation_records_actual_delta():
    _seed_shelf(adet=1)
    ledger.apply_lifecycle_effect(
        order_number="O8", from_status="created", to_status="Shipped",
        details='[{"barcode":"BC1","quantity":3}]',
    )
    assert _shelf_qty() == 0  # negatife düşmedi
    ship = _movements(reason="ship_out")
    assert len(ship) == 1 and ship[0].delta == -1  # gerçekleşen


# ════════════════════════════════════════════════════════════════════════
# 8) ENTEGRASYON: process_bg_orders_bulk Created→Delivered'da stoğu düşmeli
#    (ANA FIX wiring'i — task 4 yapılana kadar KIRMIZI)
# ════════════════════════════════════════════════════════════════════════
def test_bg_handler_created_to_delivered_decrements():
    from order_service import process_bg_orders_bulk

    _seed_shelf(adet=5)
    db.session.add(OrderCreated(
        order_number="BG1", status="Created", source="TRENDYOL",
        product_barcode="BC1", atanan_raf="A1",
        details='[{"barcode":"BC1","quantity":2}]',
        order_date=datetime.utcnow(), package_number="PKG1",
    ))
    db.session.commit()

    bg_orders = [{
        "orderNumber": "BG1", "id": "PKG1", "status": "Delivered",
        "_normalizedStatus": "Delivered",
        "lines": [{"barcode": "BC1", "quantity": 2}],
    }]
    process_bg_orders_bulk(bg_orders, app)

    with app.app_context():
        assert _shelf_qty() == 3, "BG handler Created→Delivered'da raf 5→3 düşmeliydi (hayalet stok fix)"
        assert OrderDelivered.query.filter_by(order_number="BG1").count() == 1
        assert len(_movements(reason="ship_out")) == 1


# ════════════════════════════════════════════════════════════════════════
# 9) CRITICAL regresyon: idempotency yarışında savepoint DIŞ transaction'ı korur
#    (bare rollback() dış işi çökertirdi)
# ════════════════════════════════════════════════════════════════════════
def test_savepoint_preserves_outer_transaction_on_idem_race(monkeypatch):
    _seed_shelf(adet=5)
    # K1 anahtarlı hareket zaten commit'li
    db.session.add(StockMovement(barcode="BC1", delta=-1, reason="ship_out",
                                 idempotency_key="K1"))
    db.session.commit()

    # Dış (henüz commit edilmemiş) iş
    db.session.add(OrderCreated(order_number="OUTER", source="TRENDYOL", status="Created"))

    # Yarış yolunu zorla: ön-kontrolü atla → INSERT IntegrityError tetiklenir
    monkeypatch.setattr(ledger, "has_movement", lambda k: False)
    res = ledger.record_movement(
        barcode="BC1", delta=-1, reason="ship_out",
        idempotency_key="K1", mutate_shelf=False, commit=False,
    )
    assert res.applied is False

    # Savepoint yalnızca çakışan insert'i geri aldı; dış iş AYAKTA olmalı.
    db.session.commit()
    assert OrderCreated.query.filter_by(order_number="OUTER").count() == 1


# ════════════════════════════════════════════════════════════════════════
# 10-11) Sipariş/Barkod izleme aracı (scripts/trace_order.py) — salt okunur
# ════════════════════════════════════════════════════════════════════════
def test_trace_order_includes_ledger_and_location(capsys):
    _seed_shelf(adet=5)
    db.session.add(OrderShipped(
        order_number="TR1", source="TRENDYOL", status="Shipped",
        product_barcode="BC1", details='[{"barcode":"BC1","quantity":2}]',
    ))
    db.session.add(StockMovement(
        barcode="BC1", delta=-2, reason="ship_out", order_number="TR1", shelf_code="A1",
    ))
    db.session.commit()

    from scripts.trace_order import trace_order
    trace_order("TR1")
    out = capsys.readouterr().out
    assert "TR1" in out
    assert "ship_out" in out           # ledger hareketi
    assert "Kargolandı" in out         # anlık konum


def test_trace_barcode_shows_movements(capsys):
    _seed_shelf(adet=3)
    db.session.add(StockMovement(barcode="BC1", delta=-1, reason="ship_out", shelf_code="A1"))
    db.session.commit()

    from scripts.trace_order import trace_barcode
    trace_barcode("BC1")
    out = capsys.readouterr().out
    assert "BC1" in out
    assert "ship_out" in out
    assert "CentralStock" in out       # güncel stok özeti


# ════════════════════════════════════════════════════════════════════════
# 12) Sipariş İz Sürme sayfası (order_audit_routes) ledger entegrasyonu
# ════════════════════════════════════════════════════════════════════════
def test_audit_page_lookup_includes_ledger_movements():
    _seed_shelf(adet=5)
    db.session.add(StockMovement(
        barcode="BC1", delta=-2, reason="ship_out", order_number="TRX", shelf_code="A1",
    ))
    db.session.commit()

    from order_audit_routes import _ledger_movements
    rows = _ledger_movements("TRX", ["BC1"])
    assert any(r["reason"] == "ship_out" and r["delta"] == -2 for r in rows)
    # tablo yoksa bile çökmemeli — boş barkod listesiyle de güvenli
    assert _ledger_movements("YOK", []) == []
