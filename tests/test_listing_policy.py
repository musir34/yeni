"""İptal-eğilimli ürünler için otomatik listeleme tamponu (stock_listing_policy) — TDD.

İzole tempfile-sqlite; GERÇEK DB'ye dokunmaz.

Çalıştırma:
    DISABLE_JOBS=1 pytest tests/test_listing_policy.py -v
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_tmp_db = tempfile.NamedTemporaryFile(suffix="_policy_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"
os.environ["WERKZEUG_RUN_MAIN"] = "false"

from flask import Flask  # noqa: E402
from sqlalchemy import event  # noqa: E402

from models import (  # noqa: E402
    db, OrderCancelled, StockListingPolicy, Product, CentralStock, BarcodeAlias,
)
import stock_sync.listing_policy as lp  # noqa: E402

_NEEDED = (OrderCancelled, StockListingPolicy, Product, CentralStock, BarcodeAlias)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)


@event.listens_for(db.engine, "connect")
def _on_connect(dbapi_conn, _):
    if isinstance(dbapi_conn, sqlite3.Connection):
        dbapi_conn.create_function(
            "translate", 3,
            lambda s, f, t: None if s is None else s.translate(str.maketrans(f, t)),
        )


with app.app_context():
    for _m in _NEEDED:
        _m.__table__.create(bind=db.engine, checkfirst=True)


@pytest.fixture(autouse=True)
def _ctx():
    with app.app_context():
        for m in (OrderCancelled, StockListingPolicy, Product, CentralStock):
            m.query.delete()
        db.session.commit()
        yield
        db.session.rollback()


NOW = datetime(2026, 7, 7, 12, 0, 0)


def _cancel(barcode, days_ago, order_number="X"):
    db.session.add(OrderCancelled(
        order_number=f"{order_number}{barcode}{days_ago}", status="Cancelled",
        product_barcode=barcode, order_date=NOW - timedelta(days=days_ago),
        source="TRENDYOL",
    ))
    db.session.commit()


# ── compute_cancel_prone ────────────────────────────────────────────────
def test_compute_counts_cancellations_in_window():
    _cancel("BC1", 1); _cancel("BC1", 3); _cancel("BC2", 2)
    prone = lp.compute_cancel_prone(days=30, min_cancels=2, now=NOW)
    assert prone == {"BC1": 2}  # BC2 tek iptal → eşiğin altında


def test_compute_excludes_old_cancellations():
    _cancel("BC1", 5); _cancel("BC1", 40)  # biri pencere dışı
    prone = lp.compute_cancel_prone(days=30, min_cancels=2, now=NOW)
    assert prone == {}  # pencerede yalnız 1 iptal kaldı


def test_compute_ignores_empty_barcode():
    db.session.add(OrderCancelled(order_number="E1", status="Cancelled",
                                  product_barcode="", order_date=NOW - timedelta(days=1)))
    db.session.add(OrderCancelled(order_number="E2", status="Cancelled",
                                  product_barcode=None, order_date=NOW - timedelta(days=1)))
    db.session.commit()
    assert lp.compute_cancel_prone(days=30, min_cancels=1, now=NOW) == {}


# ── refresh_policies (upsert + auto-expire) ─────────────────────────────
def test_refresh_creates_auto_policies():
    _cancel("BC1", 1); _cancel("BC1", 2)
    res = lp.refresh_policies(days=30, min_cancels=2, extra_buffer=2, now=NOW)
    pol = StockListingPolicy.query.get("BC1")
    assert pol and pol.extra_buffer == 2 and pol.auto is True and pol.cancel_count == 2
    assert res["prone"] == 1


def test_refresh_expires_auto_policy_when_no_longer_prone():
    _cancel("BC1", 1); _cancel("BC1", 2)
    lp.refresh_policies(days=30, min_cancels=2, extra_buffer=2, now=NOW)
    # İptaller "eskir": 60 gün sonra tekrar çalıştır → artık eğilimli değil
    later = NOW + timedelta(days=60)
    lp.refresh_policies(days=30, min_cancels=2, extra_buffer=2, now=later)
    assert StockListingPolicy.query.get("BC1") is None  # otomatik temizlendi


def test_refresh_preserves_manual_policy():
    # Elle konmuş override (auto=False) — iptal geçmişi olmasa da silinmemeli
    db.session.add(StockListingPolicy(barcode="MAN", extra_buffer=3, auto=False,
                                      reason="elle", cancel_count=0))
    db.session.commit()
    lp.refresh_policies(days=30, min_cancels=2, extra_buffer=2, now=NOW)
    pol = StockListingPolicy.query.get("MAN")
    assert pol and pol.extra_buffer == 3 and pol.auto is False


def test_refresh_idempotent():
    _cancel("BC1", 1); _cancel("BC1", 2)
    lp.refresh_policies(days=30, min_cancels=2, extra_buffer=2, now=NOW)
    lp.refresh_policies(days=30, min_cancels=2, extra_buffer=2, now=NOW)
    assert StockListingPolicy.query.filter_by(barcode="BC1").count() == 1


# ── get_extra_buffer_map ────────────────────────────────────────────────
def test_get_extra_buffer_map():
    db.session.add(StockListingPolicy(barcode="BC1", extra_buffer=2))
    db.session.add(StockListingPolicy(barcode="BC2", extra_buffer=0))  # 0 → haritada olmasın
    db.session.commit()
    m = lp.get_extra_buffer_map()
    assert m == {"BC1": 2}


def test_effective_buffer_helper():
    db.session.add(StockListingPolicy(barcode="BC1", extra_buffer=2))
    db.session.commit()
    m = lp.get_extra_buffer_map()
    # global tampon 1 + ekstra 2 = 3 → 2 adetlik ürün 0 gönderilir (son-adet yarışı kapanır)
    assert max(0, 2 - 0 - (1 + m.get("BC1", 0))) == 0
    assert max(0, 3 - 0 - (1 + m.get("BC1", 0))) == 0
    assert max(0, 4 - 0 - (1 + m.get("BC1", 0))) == 1
