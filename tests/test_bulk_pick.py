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
    OrderCreated, OrderHazirlaniyor, OrderPicking, OrderShipped, OrderDelivered,
    OrderCancelled, OrderAuditLog, Archive,
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["TESTING"] = True
app.secret_key = "test-secret"   # flash() için
db.init_app(app)

# flask-login: confirm_packing → log_user_action içinde current_user kullanılır.
# Prod app.py'de LoginManager kurulu; testte de kurmazsak 'login_manager yok'
# AttributeError'ı başarılı paketlemeyi rollback'e düşürür. Null user_loader →
# current_user anonim (is_authenticated=False) → log_user_action güvenle atlar.
from flask_login import LoginManager  # noqa: E402
_login_manager = LoginManager()
_login_manager.init_app(app)


@_login_manager.user_loader
def _load_user(_uid):  # pragma: no cover - test stub
    return None

_NEEDED = (Raf, RafUrun, CentralStock, StockMovement, Product, BarcodeAlias,
           OrderCreated, OrderHazirlaniyor, OrderPicking, OrderShipped,
           OrderDelivered, OrderCancelled, OrderAuditLog, Archive)


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

from update_service import update_service_bp  # noqa: E402
app.register_blueprint(update_service_bp)


@pytest.fixture(autouse=True)
def _ctx_clean():
    with app.app_context():
        for m in (StockMovement, RafUrun, CentralStock, OrderCreated,
                  OrderHazirlaniyor, OrderPicking, OrderShipped, OrderDelivered,
                  OrderCancelled, Raf, Archive):
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


def test_pick_endpoint_zebra_shelf_decrements(client):
    # Toplu ekran: Zebra '-' yerine '=' gönderse de (depo "A-1", okutma "A=1")
    # picking_service normalize edip doğru raftan düşmeli ve GERÇEK kodu damgalamalı.
    _seed_shelf(barcode="BC1", shelf="A-1", adet=5)
    _mk_hazirlaniyor("OZ3", "BC1")
    resp = client.post("/prepare-new-orders/pick", json={
        "order_number": "OZ3", "raf_barkodu": "A=1", "urun_barkodu": "BC1"})
    data = resp.get_json()
    assert data["success"] is True
    assert _shelf_qty("BC1", "A-1") == 4
    with app.app_context():
        o = OrderHazirlaniyor.query.filter_by(order_number="OZ3").first()
        assert o.toplandi_raf == "A-1"   # ham "A=1" değil, gerçek depo kodu


def test_pick_endpoint_unknown_order_404(client):
    resp = client.post("/prepare-new-orders/pick", json={
        "order_number": "YOK", "raf_barkodu": "A1", "urun_barkodu": "BC1"})
    assert resp.status_code == 404


# ── confirm_packing: Trendyol API kaldırıldı + sıralı-kapalı toplandı kontrolü ──
def test_confirm_packing_blocks_unpicked_sequential_off(client):
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    _mk_hazirlaniyor("O5", "BC1")  # toplandi_at = None
    resp = client.post("/confirm_packing", data={"order_number": "O5", "sirali": "0"},
                       headers={"X-Requested-With": "XMLHttpRequest"})
    data = resp.get_json()
    assert data["ok"] is False           # toplanmadığı için engellendi
    assert _shelf_qty("BC1", "A1") == 5   # düşmedi
    with app.app_context():
        assert OrderPicking.query.filter_by(order_number="O5").count() == 0


def test_confirm_packing_packs_picked_without_decrement(client):
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    _mk_hazirlaniyor("O6", "BC1")
    # önce toplu ekranda topla (5→4, toplandı)
    client.post("/prepare-new-orders/pick", json={
        "order_number": "O6", "raf_barkodu": "A1", "urun_barkodu": "BC1"})
    assert _shelf_qty("BC1", "A1") == 4
    # sıralı-kapalı paketle → tekrar DÜŞMEDEN Picking'e geçmeli
    resp = client.post("/confirm_packing", data={"order_number": "O6", "sirali": "0"},
                       headers={"X-Requested-With": "XMLHttpRequest"})
    assert _shelf_qty("BC1", "A1") == 4   # ikinci düşüm YOK
    with app.app_context():
        assert OrderPicking.query.filter_by(order_number="O6").count() == 1
        assert OrderHazirlaniyor.query.filter_by(order_number="O6").count() == 0


def test_reserved_excludes_picked_hazirlaniyor(client):
    # Rezerv: toplanmamış Hazırlanıyor sayılmalı; TOPLANINCA çıkmalı (stok zaten düştü).
    import types
    from stock_sync.service import StockSyncService
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    _mk_hazirlaniyor("RX1", "BC1", qty=2)

    with app.app_context():
        res = StockSyncService.get_reserved_barcodes(types.SimpleNamespace())
        assert res.get("BC1", 0) == 2   # toplanmamış → rezerv

    # Topla (stok 5→3, toplandi_at dolar)
    client.post("/prepare-new-orders/pick", json={
        "order_number": "RX1", "raf_barkodu": "A1", "urun_barkodu": "BC1"})

    with app.app_context():
        res2 = StockSyncService.get_reserved_barcodes(types.SimpleNamespace())
        assert res2.get("BC1", 0) == 0   # toplandı → rezervden çıktı (çift düşüm yok)


def test_confirm_packing_sequential_zebra_shelf_decrements(client):
    # Sıralı-AÇIK, TOPLANMAMIŞ sipariş: Zebra rafı '-' yerine '=' gönderse de
    # (depo "A-1", okutma "A=1") backend normalize edip doğru raftan düşmeli.
    # Eski hata: ham "A=1" RafUrun'da bulunamaz → "0 adet var" → rollback.
    _seed_shelf(barcode="BC1", shelf="A-1", adet=5)
    _mk_hazirlaniyor("OZ1", "BC1")  # toplandi_at = None → pakette düşüm yapılır
    resp = client.post("/confirm_packing", data={
        "order_number": "OZ1", "sirali": "1", "raf_BC1": "A=1",
        "barkod_right_0_0": "BC1"},
        headers={"X-Requested-With": "XMLHttpRequest"})
    data = resp.get_json()
    assert data["ok"] is True              # normalize edilip başarıyla paketlendi
    assert _shelf_qty("BC1", "A-1") == 4   # doğru raftan 1 adet düştü
    with app.app_context():
        assert OrderPicking.query.filter_by(order_number="OZ1").count() == 1
        assert OrderHazirlaniyor.query.filter_by(order_number="OZ1").count() == 0


def test_confirm_packing_sequential_lowercase_shelf_decrements(client):
    # Büyük/küçük harf farkı da reddedilmemeli (frontend normRaf uppercase yapıyor).
    _seed_shelf(barcode="BC2", shelf="B-2", adet=3)
    _mk_hazirlaniyor("OZ2", "BC2")
    resp = client.post("/confirm_packing", data={
        "order_number": "OZ2", "sirali": "1", "raf_BC2": "b-2",
        "barkod_right_0_0": "BC2"},
        headers={"X-Requested-With": "XMLHttpRequest"})
    assert resp.get_json()["ok"] is True
    assert _shelf_qty("BC2", "B-2") == 2


def test_confirm_packing_picked_then_sequential_on_no_double(client):
    # Toplu ekranda toplanmış sipariş, sıralı-AÇIK pakete gelse bile tekrar düşmemeli.
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    _mk_hazirlaniyor("O7", "BC1")
    client.post("/prepare-new-orders/pick", json={
        "order_number": "O7", "raf_barkodu": "A1", "urun_barkodu": "BC1"})
    assert _shelf_qty("BC1", "A1") == 4
    client.post("/confirm_packing", data={
        "order_number": "O7", "sirali": "1", "raf_BC1": "A1",
        "barkod_right_0_0": "BC1"},
        headers={"X-Requested-With": "XMLHttpRequest"})
    assert _shelf_qty("BC1", "A1") == 4   # toplandı kilidi → ikinci düşüm yok
    with app.app_context():
        assert OrderPicking.query.filter_by(order_number="O7").count() == 1
