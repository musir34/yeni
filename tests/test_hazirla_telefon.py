"""Sipariş Hazırla — Telefon Eşlik: eşleşme kuralları + senkron akışı — izole sqlite.

Çalıştırma: DISABLE_JOBS=1 python -m pytest tests/test_hazirla_telefon.py --noconftest -q
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_tmp_db = tempfile.NamedTemporaryFile(suffix="_hazirla_tel_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"
os.environ["WERKZEUG_RUN_MAIN"] = "false"

from flask import Flask  # noqa: E402
from flask_login import LoginManager  # noqa: E402

from models import db, User, UserLog, HazirlaEslesme, HazirlaOkutma  # noqa: E402
import hazirla_telefon as ht  # noqa: E402
from hazirla_telefon import hazirla_telefon_bp, baglanabilir_mi  # noqa: E402

app = Flask(__name__, template_folder=str(PROJECT_ROOT / "templates"))
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["TESTING"] = True
app.secret_key = "test-secret"
db.init_app(app)

_login_manager = LoginManager()
_login_manager.init_app(app)


@_login_manager.user_loader
def _load_user(uid):
    return User.query.get(int(uid))


app.register_blueprint(hazirla_telefon_bp)

with app.app_context():
    for _m in (User, UserLog, HazirlaEslesme, HazirlaOkutma):
        _m.__table__.create(bind=db.engine, checkfirst=True)

FETCH = {"X-Requested-With": "fetch"}


def _mk_user(username, role="worker", owner=False):
    u = User(first_name=username.title(), last_name="Test", username=username,
             email=f"{username}@test.local", password="x", role=role, status="approved",
             is_owner=owner)
    db.session.add(u)
    db.session.commit()
    return u.id


@pytest.fixture(autouse=True)
def _ctx_clean():
    # Dikkat: app context'i test boyunca AÇIK tutma — test_client istekleri onu paylaşır ve
    # flask-login current_user'ı g'de önbellekler (ilk isteğin kullanıcısı sonrakilere sızar).
    with app.app_context():
        for m in (HazirlaOkutma, HazirlaEslesme, UserLog, User):
            m.query.delete()
        db.session.commit()
        ids = {
            "worker1": _mk_user("worker1"),
            "worker2": _mk_user("worker2"),
            "manager1": _mk_user("manager1", role="manager"),
            "owner1": _mk_user("owner1", role="worker", owner=True),
        }
    yield ids
    with app.app_context():
        db.session.rollback()


def _login(client, uid, role):
    with client.session_transaction() as s:
        s["_user_id"] = str(uid)
        s["_fresh"] = True
        s["totp_verified"] = True
        s["role"] = role
        s["user_id"] = uid


def _pc(ids, kim="worker1", rol="worker"):
    c = app.test_client()
    _login(c, ids[kim], rol)
    return c


def _tel(ids, kim, rol):
    c = app.test_client()
    _login(c, ids[kim], rol)
    return c


def _baslat(pc):
    r = pc.post("/hazirla-telefon/pc/baslat", json={}, headers=FETCH)
    assert r.status_code == 200, r.data
    return r.get_json()


# ─────────────────────────── Saf kural ───────────────────────────

class _U:
    def __init__(self, id, role="worker", is_owner=False):
        self.id, self.role, self.is_owner = id, role, is_owner


def test_baglanabilir_mi_kurali():
    assert baglanabilir_mi(_U(1), _U(1)) == (True, "")                       # aynı hesap, worker
    assert baglanabilir_mi(_U(1), _U(2))[0] is False                        # farklı hesap, worker → ret
    assert baglanabilir_mi(_U(1), _U(2, role="manager")) == (True, "")      # yönetim herkese
    assert baglanabilir_mi(_U(1), _U(2, role="admin")) == (True, "")
    assert baglanabilir_mi(_U(1), _U(2, is_owner=True)) == (True, "")       # sahip herkese
    assert baglanabilir_mi(None, _U(2))[0] is False


# ─────────────────────────── Eşleşme ───────────────────────────

def test_worker_ayni_hesapla_baglanir(_ctx_clean):
    ids = _ctx_clean
    pc = _pc(ids)
    b = _baslat(pc)
    assert b["token"] and b["qr"].startswith("data:image/png;base64,") and "t=" + b["token"] in b["url"]
    tel = _tel(ids, "worker1", "worker")
    r = tel.post("/hazirla-telefon/bagla", json={"token": b["token"]}, headers=FETCH)
    assert r.status_code == 200, r.data
    j = r.get_json()
    assert j["durum"] == "bagli" and j["pc_kullanici"] == "Worker1 Test"


def test_worker_farkli_hesapla_reddedilir(_ctx_clean):
    ids = _ctx_clean
    b = _baslat(_pc(ids))
    tel = _tel(ids, "worker2", "worker")
    r = tel.post("/hazirla-telefon/bagla", json={"token": b["token"]}, headers=FETCH)
    assert r.status_code == 400
    assert "kendi hesabınla" in r.get_json()["error"]
    with app.app_context():
        e = HazirlaEslesme.query.get(b["eslesme_id"])
        assert e.durum == "bekliyor" and e.telefon_user_id is None   # jeton yanmadı, PC yeniden deneyebilir


def test_manager_ve_sahip_farkli_hesapla_baglanir(_ctx_clean):
    ids = _ctx_clean
    for kim, rol in (("manager1", "manager"), ("owner1", "worker")):
        b = _baslat(_pc(ids))
        r = _tel(ids, kim, rol).post("/hazirla-telefon/bagla", json={"token": b["token"]}, headers=FETCH)
        assert r.status_code == 200, (kim, r.data)
        assert r.get_json()["durum"] == "bagli"


def test_jeton_tek_kullanimlik_ve_sureli(_ctx_clean, monkeypatch):
    ids = _ctx_clean
    b = _baslat(_pc(ids))
    tel = _tel(ids, "worker1", "worker")
    assert tel.post("/hazirla-telefon/bagla", json={"token": b["token"]}, headers=FETCH).status_code == 200
    # ikinci kez aynı jeton → ret
    r = tel.post("/hazirla-telefon/bagla", json={"token": b["token"]}, headers=FETCH)
    assert r.status_code == 400 and "süresi dolmuş ya da kullanılmış" in r.get_json()["error"]
    # süresi geçmiş QR → ret
    b2 = _baslat(_pc(ids))
    gelecek = datetime.utcnow() + timedelta(seconds=ht.QR_GECERLILIK_SN + 5)
    monkeypatch.setattr(ht, "_simdi", lambda: gelecek)
    r = tel.post("/hazirla-telefon/bagla", json={"token": b2["token"]}, headers=FETCH)
    assert r.status_code == 400
    with app.app_context():
        assert HazirlaEslesme.query.get(b2["eslesme_id"]).kapanma_sebebi == "qr_suresi"


def test_yeni_qr_eski_oturumu_kapatir(_ctx_clean):
    ids = _ctx_clean
    pc = _pc(ids)
    b1 = _baslat(pc)
    r = pc.post("/hazirla-telefon/pc/baslat", json={"eski_eslesme_id": b1["eslesme_id"]}, headers=FETCH)
    assert r.status_code == 200
    with app.app_context():
        assert HazirlaEslesme.query.get(b1["eslesme_id"]).kapanma_sebebi == "yeni_qr"


def test_baskasinin_eslesmesine_erisilemez(_ctx_clean):
    ids = _ctx_clean
    b = _baslat(_pc(ids))
    # worker2 PC rotasıyla worker1'in eşleşmesini soramaz
    r = _pc(ids, "worker2").post("/hazirla-telefon/pc/senkron", json={"eslesme_id": b["eslesme_id"]}, headers=FETCH)
    assert r.status_code == 404
    # fetch başlığı olmayan POST → 403
    r = _pc(ids).post("/hazirla-telefon/pc/senkron", json={"eslesme_id": b["eslesme_id"]})
    assert r.status_code == 403


# ─────────────────────────── Senkron akışı ───────────────────────────

def _bagli_cift(ids, tel_kim="worker1", tel_rol="worker"):
    pc = _pc(ids)
    b = _baslat(pc)
    tel = _tel(ids, tel_kim, tel_rol)
    r = tel.post("/hazirla-telefon/bagla", json={"token": b["token"]}, headers=FETCH)
    assert r.status_code == 200
    return pc, tel, b["eslesme_id"]


PAYLOAD = {"order_number": "TY-1", "gosterim_no": "TY-1", "kalemler": [
    {"idx": 0, "sku": "0121-37", "adet": 1, "raflar": [{"kod": "A-1", "adet": 3}],
     "raf": {"deger": "", "ok": False}, "kutular": [{"q": 0, "deger": "", "ok": False}]}]}


def test_pc_goruntusu_telefona_surumle_gider(_ctx_clean):
    ids = _ctx_clean
    pc, tel, eid = _bagli_cift(ids)
    r = pc.post("/hazirla-telefon/pc/senkron", json={"eslesme_id": eid, "payload": PAYLOAD, "son_okutma_id": 0}, headers=FETCH)
    j = r.get_json()
    assert j["durum"] == "bagli" and j["surum"] == 1 and j["telefon_kullanici"] == "Worker1 Test"
    # aynı görüntü tekrar → sürüm artmaz (hareketsizlik sayacı da sıfırlanmaz)
    r = pc.post("/hazirla-telefon/pc/senkron", json={"eslesme_id": eid, "payload": PAYLOAD, "son_okutma_id": 0}, headers=FETCH)
    assert r.get_json()["surum"] == 1
    t = tel.post("/hazirla-telefon/telefon/senkron", json={"eslesme_id": eid}, headers=FETCH).get_json()
    assert t["surum"] == 1 and t["payload"]["order_number"] == "TY-1" and t["pc_canli"] is True
    assert 0 < t["kalan_sn"] <= ht.HAREKETSIZLIK_SN


def test_telefon_okutmasi_pc_ye_bir_kez_gider(_ctx_clean):
    ids = _ctx_clean
    pc, tel, eid = _bagli_cift(ids)
    r = tel.post("/hazirla-telefon/telefon/okut", json={"eslesme_id": eid, "tip": "raf", "kalem": 0, "adet": 0, "deger": "A-1"}, headers=FETCH)
    assert r.status_code == 200, r.data
    r = tel.post("/hazirla-telefon/telefon/okut", json={"eslesme_id": eid, "tip": "urun", "kalem": 0, "adet": 0, "deger": "079950000001"}, headers=FETCH)
    assert r.status_code == 200
    j = pc.post("/hazirla-telefon/pc/senkron", json={"eslesme_id": eid, "son_okutma_id": 0}, headers=FETCH).get_json()
    assert [(o["tip"], o["deger"]) for o in j["okutmalar"]] == [("raf", "A-1"), ("urun", "079950000001")]
    son = j["okutmalar"][-1]["id"]
    # aynı olaylar ikinci turda gelmez
    j = pc.post("/hazirla-telefon/pc/senkron", json={"eslesme_id": eid, "son_okutma_id": son}, headers=FETCH).get_json()
    assert j["okutmalar"] == []
    with app.app_context():
        assert all(o.islendi_at for o in HazirlaOkutma.query.all())
    # geçersiz tür / boş değer
    assert tel.post("/hazirla-telefon/telefon/okut", json={"eslesme_id": eid, "tip": "x", "deger": "1"}, headers=FETCH).status_code == 400
    assert tel.post("/hazirla-telefon/telefon/okut", json={"eslesme_id": eid, "tip": "raf", "deger": " "}, headers=FETCH).status_code == 400


def test_on_dakika_hareketsizlik_oturumu_kapatir(_ctx_clean, monkeypatch):
    ids = _ctx_clean
    pc, tel, eid = _bagli_cift(ids)
    gelecek = datetime.utcnow() + timedelta(seconds=ht.HAREKETSIZLIK_SN + 1)
    monkeypatch.setattr(ht, "_simdi", lambda: gelecek)
    r = tel.post("/hazirla-telefon/telefon/okut", json={"eslesme_id": eid, "tip": "raf", "kalem": 0, "adet": 0, "deger": "A-1"}, headers=FETCH)
    assert r.status_code == 400 and r.get_json()["durum"] == "suresi_doldu"
    j = pc.post("/hazirla-telefon/pc/senkron", json={"eslesme_id": eid, "son_okutma_id": 0}, headers=FETCH).get_json()
    assert j["durum"] == "suresi_doldu" and j["kapanma_sebebi"] == "hareketsizlik" and j["kalan_sn"] == 0
    with app.app_context():
        assert HazirlaOkutma.query.count() == 0


def test_okutma_hareketsizlik_sayacini_sifirlar(_ctx_clean, monkeypatch):
    ids = _ctx_clean
    pc, tel, eid = _bagli_cift(ids)
    t0 = datetime.utcnow()

    def _pc_acik(sn):
        # PC sayfası açık: PC_KAYIP_SN'den sık sorar (yoksa haklı olarak 'pc_kapandi' olur)
        for adim in range(0, sn + 1, ht.PC_KAYIP_SN // 2):
            monkeypatch.setattr(ht, "_simdi", lambda a=adim: t0 + timedelta(seconds=a))
            pc.post("/hazirla-telefon/pc/senkron", json={"eslesme_id": eid, "son_okutma_id": 0}, headers=FETCH)
        monkeypatch.setattr(ht, "_simdi", lambda: t0 + timedelta(seconds=sn))

    _pc_acik(ht.HAREKETSIZLIK_SN - 30)
    assert tel.post("/hazirla-telefon/telefon/okut", json={"eslesme_id": eid, "tip": "raf", "kalem": 0, "adet": 0, "deger": "A-1"}, headers=FETCH).status_code == 200
    _pc_acik(ht.HAREKETSIZLIK_SN + 30)
    j = pc.post("/hazirla-telefon/pc/senkron", json={"eslesme_id": eid, "son_okutma_id": 0}, headers=FETCH).get_json()
    assert j["durum"] == "bagli" and len(j["okutmalar"]) == 1


def test_pc_sayfasi_kapaninca_oturum_kapanir(_ctx_clean, monkeypatch):
    ids = _ctx_clean
    pc, tel, eid = _bagli_cift(ids)
    pc.post("/hazirla-telefon/pc/senkron", json={"eslesme_id": eid, "son_okutma_id": 0}, headers=FETCH)
    gelecek = datetime.utcnow() + timedelta(seconds=ht.PC_KAYIP_SN + 5)
    monkeypatch.setattr(ht, "_simdi", lambda: gelecek)
    t = tel.post("/hazirla-telefon/telefon/senkron", json={"eslesme_id": eid}, headers=FETCH).get_json()
    assert t["durum"] == "kapandi" and t["kapanma_sebebi"] == "pc_kapandi"


def test_elle_kesme_iki_taraftan(_ctx_clean):
    ids = _ctx_clean
    pc, tel, eid = _bagli_cift(ids)
    assert pc.post("/hazirla-telefon/pc/kes", json={"eslesme_id": eid}, headers=FETCH).status_code == 200
    t = tel.post("/hazirla-telefon/telefon/senkron", json={"eslesme_id": eid}, headers=FETCH).get_json()
    assert t["durum"] == "kapandi" and t["kapanma_sebebi"] == "pc_kes"
    pc2, tel2, eid2 = _bagli_cift(ids, "manager1", "manager")
    assert tel2.post("/hazirla-telefon/telefon/kes", json={"eslesme_id": eid2}, headers=FETCH).status_code == 200
    j = pc2.post("/hazirla-telefon/pc/senkron", json={"eslesme_id": eid2, "son_okutma_id": 0}, headers=FETCH).get_json()
    assert j["durum"] == "kapandi" and j["kapanma_sebebi"] == "telefon_kes"


def test_telefon_sayfasi_acilir(_ctx_clean):
    ids = _ctx_clean
    r = _tel(ids, "worker1", "worker").get("/hazirla-telefon/?t=abc")
    assert r.status_code == 200
    assert b"hazirla-telefon.js" in r.data and b'data-oto-token="abc"' in r.data


def test_sayfa_yetki_katalogu():
    from sayfa_yetki import SAYFA_MAP, erisebilir, sayfa_bul
    s = SAYFA_MAP["hazirla_telefon"]
    assert s.ebeveynler == ("siparis_hazirla",) and s.menude is False
    assert sayfa_bul("hazirla_telefon.sayfa", "/hazirla-telefon/").kod == "hazirla_telefon"
    for rol in ("admin", "manager", "worker"):
        assert erisebilir("hazirla_telefon", rol)
