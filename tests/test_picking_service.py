"""picking_service.pick_order_from_shelf testleri — TDD, izole sqlite."""
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

_tmp_db = tempfile.NamedTemporaryFile(suffix="_pick_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"
os.environ["WERKZEUG_RUN_MAIN"] = "false"

from flask import Flask  # noqa: E402
from sqlalchemy import event  # noqa: E402

from models import (  # noqa: E402
    db, Raf, RafUrun, CentralStock, StockMovement, Product, BarcodeAlias,
    OrderHazirlaniyor, OrderAuditLog,
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

_NEEDED = (Raf, RafUrun, CentralStock, StockMovement, Product, BarcodeAlias,
           OrderHazirlaniyor, OrderAuditLog)


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


@pytest.fixture(autouse=True)
def _ctx_clean():
    with app.app_context():
        for m in (StockMovement, RafUrun, CentralStock, OrderHazirlaniyor, Raf):
            m.query.delete()
        db.session.commit()
        yield
        db.session.rollback()


def _seed_shelf(barcode="BC1", shelf="A1", adet=5):
    db.session.add(Raf(kod=shelf, ana="A", ikincil="1", kat="1"))
    db.session.add(RafUrun(raf_kodu=shelf, urun_barkodu=barcode, adet=adet))
    db.session.commit()


def _shelf_qty(barcode="BC1", shelf="A1"):
    r = RafUrun.query.filter_by(raf_kodu=shelf, urun_barkodu=barcode).first()
    return r.adet if r else None


def _mk_order(order_number="O1", barcode="BC1", qty=1):
    o = OrderHazirlaniyor(
        order_number=order_number, status="Hazırlanıyor", source="TRENDYOL",
        product_barcode=barcode, details=f'[{{"barcode":"{barcode}","quantity":{qty}}}]',
        order_date=datetime.utcnow(), package_number="PKG1",
    )
    db.session.add(o)
    db.session.commit()
    return o


def test_pick_decrements_scanned_shelf_and_stamps():
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    o = _mk_order()
    from picking_service import pick_order_from_shelf
    res = pick_order_from_shelf(order=o, barcode="BC1", raf_kodu="A1", qty=1, source="USER")
    assert res["success"] is True
    assert _shelf_qty("BC1", "A1") == 4
    assert o.toplandi_at is not None and o.toplandi_raf == "A1"
    assert StockMovement.query.filter_by(reason="pack_out", order_number="O1").count() == 1


def test_pick_wrong_shelf_rejected():
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    o = _mk_order()
    from picking_service import pick_order_from_shelf
    res = pick_order_from_shelf(order=o, barcode="BC1", raf_kodu="Z9", qty=1)
    assert res["success"] is False and "yeterli yok" in res["error"]
    assert _shelf_qty("BC1", "A1") == 5
    assert o.toplandi_at is None


def test_pick_wrong_product_rejected():
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    o = _mk_order(barcode="BC1")
    from picking_service import pick_order_from_shelf
    res = pick_order_from_shelf(order=o, barcode="BCX", raf_kodu="A1", qty=1)
    assert res["success"] is False
    assert _shelf_qty("BC1", "A1") == 5


def test_pick_idempotent_no_double_decrement():
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    o = _mk_order()
    from picking_service import pick_order_from_shelf
    pick_order_from_shelf(order=o, barcode="BC1", raf_kodu="A1", qty=1)
    second = pick_order_from_shelf(order=o, barcode="BC1", raf_kodu="A1", qty=1)
    assert second.get("already") is True
    assert _shelf_qty("BC1", "A1") == 4   # yalnızca bir kez düştü


def test_pick_insufficient_qty_rejected():
    _seed_shelf(barcode="BC1", shelf="A1", adet=1)
    o = _mk_order(qty=3)
    from picking_service import pick_order_from_shelf
    res = pick_order_from_shelf(order=o, barcode="BC1", raf_kodu="A1", qty=3)
    assert res["success"] is False
    assert _shelf_qty("BC1", "A1") == 1
