"""Toplu /pick endpoint + confirm_packing senaryoları — izole sqlite."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_tmp_db = tempfile.NamedTemporaryFile(suffix="_bulkpick_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"
os.environ["WERKZEUG_RUN_MAIN"] = "false"

from flask import Flask  # noqa: E402
from sqlalchemy import event  # noqa: E402

from models import (  # noqa: E402
    db, Raf, RafUrun, CentralStock, StockMovement, Product, BarcodeAlias,
    OrderHazirlaniyor, OrderPicking, OrderAuditLog, Archive,
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["TESTING"] = True
db.init_app(app)

_NEEDED = (Raf, RafUrun, CentralStock, StockMovement, Product, BarcodeAlias,
           OrderHazirlaniyor, OrderPicking, OrderAuditLog, Archive)


def _install_udf():
    @event.listens_for(db.engine, "connect")
    def _on_connect(dbapi_conn, _):
        if isinstance(dbapi_conn, sqlite3.Connection):
            def _translate(s, frm, to):
                return None if s is None else s.translate(str.maketrans(frm, to))
            dbapi_conn.create_function("translate", 3, _translate)


with app.app_context():
    _install_udf()
    for _m in _NEEDED:
        _m.__table__.create(bind=db.engine, checkfirst=True)

from new_orders_service import new_orders_service_bp  # noqa: E402
app.register_blueprint(new_orders_service_bp)


@pytest.fixture(autouse=True)
def _ctx_clean():
    with app.app_context():
        for m in (StockMovement, RafUrun, CentralStock, OrderHazirlaniyor,
                  OrderPicking, Raf, Archive):
            m.query.delete()
        db.session.commit()
        yield
        db.session.rollback()


@pytest.fixture
def client():
    return app.test_client()


def _seed_shelf(barcode="BC1", shelf="A1", adet=5):
    with app.app_context():
        db.session.add(Raf(kod=shelf, ana="A", ikincil="1", kat="1"))
        db.session.add(RafUrun(raf_kodu=shelf, urun_barkodu=barcode, adet=adet))
        db.session.commit()


def _shelf_qty(barcode="BC1", shelf="A1"):
    with app.app_context():
        r = RafUrun.query.filter_by(raf_kodu=shelf, urun_barkodu=barcode).first()
        return r.adet if r else None


def _mk_hazirlaniyor(order_number="O1", barcode="BC1", qty=1):
    with app.app_context():
        o = OrderHazirlaniyor(
            order_number=order_number, status="Hazırlanıyor", source="TRENDYOL",
            product_barcode=barcode, details=f'[{{"barcode":"{barcode}","quantity":{qty}}}]',
            order_date=datetime.utcnow(), package_number="PKG1",
        )
        db.session.add(o)
        db.session.commit()


def test_pick_endpoint_decrements_and_stamps(client):
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    _mk_hazirlaniyor("O1", "BC1")
    resp = client.post("/prepare-new-orders/pick", json={
        "order_number": "O1", "raf_barkodu": "A1", "urun_barkodu": "BC1"})
    data = resp.get_json()
    assert data["success"] is True
    assert _shelf_qty("BC1", "A1") == 4
    with app.app_context():
        o = OrderHazirlaniyor.query.filter_by(order_number="O1").first()
        assert o.toplandi_at is not None and o.toplandi_raf == "A1"


def test_pick_endpoint_wrong_shelf_rejected(client):
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    _mk_hazirlaniyor("O2", "BC1")
    resp = client.post("/prepare-new-orders/pick", json={
        "order_number": "O2", "raf_barkodu": "Z9", "urun_barkodu": "BC1"})
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False
    assert _shelf_qty("BC1", "A1") == 5


def test_pick_endpoint_unknown_order_404(client):
    resp = client.post("/prepare-new-orders/pick", json={
        "order_number": "YOK", "raf_barkodu": "A1", "urun_barkodu": "BC1"})
    assert resp.status_code == 404
