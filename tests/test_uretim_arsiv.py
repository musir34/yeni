"""Üretim Paketlenen sekmesi 'Arşivle' — izole sqlite testi.

Kargo tespiti düşmeyen eski paketlenmiş siparişler Paketlenen'de sonsuza dek bekliyordu.
Arşivle: kayıt silinmez, aktif sekmelerden düşer, Teslim sekmesinde rozetle görünür, geri alınabilir.

Çalıştırma (çıplak pytest YASAK — conftest canlı uygulamayı yükler):
  DISABLE_JOBS=1 .venv/bin/python -m pytest --noconftest tests/test_uretim_arsiv.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_tmp_db = tempfile.NamedTemporaryFile(suffix="_uretim_arsiv_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"

from flask import Flask  # noqa: E402
from flask_login import LoginManager, UserMixin  # noqa: E402

from models import (  # noqa: E402
    OrderArchived, OrderCancelled, OrderCreated, OrderDelivered, OrderHazirlaniyor,
    OrderPicking, OrderShipped, PlatformConfig, Product, RafUrun, StockMovement,
    UretimDogrulama, UretimSiparis, db,
)
from uretim_routes import uretim_bp  # noqa: E402


class _Kullanici(UserMixin):
    id = 1
    username = "test"
    role = "admin"


app = Flask(__name__)
app.config.update(SECRET_KEY="t", SQLALCHEMY_DATABASE_URI=os.environ["DATABASE_URL"],
                  SQLALCHEMY_TRACK_MODIFICATIONS=False, TESTING=True)
db.init_app(app)
lm = LoginManager(app)
lm.user_loader(lambda uid: _Kullanici())
app.register_blueprint(uretim_bp)

# db.create_all() modeller arasındaki mükerrer indeks adı yüzünden çöküyor → yalnız liste()'nin
# dokunduğu tablolar açılır (orders_archived burada entity şemasıyla; prod'daki stockCode farkı testi etkilemez).
with app.app_context():
    for _m in (UretimSiparis, OrderShipped, OrderDelivered, OrderArchived, OrderCancelled, OrderCreated,
               OrderHazirlaniyor, OrderPicking, Product, RafUrun, StockMovement, UretimDogrulama, PlatformConfig):
        _m.__table__.create(bind=db.engine, checkfirst=True)

FETCH = {"X-Requested-With": "fetch"}


def _client():
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = "1"
        s["totp_verified"] = True
    return c


def _tohum():
    with app.app_context():
        db.session.query(UretimSiparis).delete()
        db.session.add_all([
            UretimSiparis(order_number="SH-1", uretildi=True, paketlendi=True, details="[]"),
            UretimSiparis(order_number="SH-2", uretildi=True, paketlendi=True, details="[]",
                          arsivlendi_at=datetime(2026, 10, 1, 9, 0)),
        ])
        db.session.commit()
        return {r.order_number: r.id for r in db.session.query(UretimSiparis).all()}


def _nolar(c, durum):
    data = c.get(f"/uretim/api/liste?durum={durum}").get_json()
    assert data["success"], data
    return [r["order_number"] for r in data["rows"]]


def test_arsivlenen_paketlenende_gorunmez_teslimde_rozetle_durur():
    _tohum()
    c = _client()
    assert _nolar(c, "paketlenen") == ["SH-1"]
    assert _nolar(c, "teslim") == ["SH-2"]
    satir = c.get("/uretim/api/liste?durum=teslim").get_json()["rows"][0]
    assert satir["arsivlendi_at"] == "01.10.2026 12:00"   # UTC → İstanbul


def test_arsivle_ve_geri_al():
    ids = _tohum()
    c = _client()
    r = c.post(f"/uretim/api/arsivle/{ids['SH-1']}", json={}, headers=FETCH).get_json()
    assert r["success"] and "Arşivlendi" in r["message"]
    assert _nolar(c, "paketlenen") == []
    assert sorted(_nolar(c, "teslim")) == ["SH-1", "SH-2"]
    r = c.post(f"/uretim/api/arsivle/{ids['SH-2']}", json={"geri_al": True}, headers=FETCH).get_json()
    assert r["success"] and "Paketlenenlere" in r["message"]
    assert _nolar(c, "paketlenen") == ["SH-2"]


def test_arsivle_csrf_basligi_olmadan_reddedilir():
    ids = _tohum()
    assert _client().post(f"/uretim/api/arsivle/{ids['SH-1']}", json={}).status_code == 403
    assert _client().post("/uretim/api/arsivle/999999", json={}, headers=FETCH).status_code == 404


def test_gercek_uygulama_yuklenmedi():
    assert "app" not in sys.modules
