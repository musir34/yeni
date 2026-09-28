"""whatsapp_duyuru uç noktası testleri — ağa çıkmaz, notify_staff taklit edilir."""
import flask_login
import pytest
from flask import Flask

import whatsapp_duyuru
import whatsapp_notify


class _Kullanici:
    def __init__(self, role: str, giris: bool = True):
        self.role = role
        self.is_authenticated = giris
        self.id = 1
        self.username = "test"


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setenv("WHATSAPP_STAFF_TOKEN", "gizli-anahtar")
    monkeypatch.setenv("WHATSAPP_STAFF_PHONE_NUMBER_ID", "111")
    monkeypatch.setenv("WHATSAPP_STAFF_NUMBERS", "905001112233,905004445566")

    app = Flask(__name__)
    app.secret_key = "test"
    app.register_blueprint(whatsapp_duyuru.whatsapp_duyuru_bp)

    durum = {"kullanici": _Kullanici("admin"), "cagrilar": []}
    monkeypatch.setattr(flask_login.utils, "_get_user", lambda: durum["kullanici"])

    def sahte_notify(baslik, metin, only_last4=None):
        durum["cagrilar"].append((baslik, metin, only_last4))
        return [{"to_last4": a, "ok": True, "via": "template"} for a in only_last4]

    monkeypatch.setattr(whatsapp_notify, "notify_staff", sahte_notify)
    import user_logs
    monkeypatch.setattr(user_logs, "log_user_action", lambda *a, **kw: None)

    istemci = app.test_client()
    with istemci.session_transaction() as oturum:
        oturum["totp_verified"] = True
    durum["istemci"] = istemci
    return durum


def _gonder(durum, govde, basliklar=None):
    return durum["istemci"].post(
        "/whatsapp-duyuru/api/gonder", json=govde,
        headers=basliklar if basliklar is not None else {"X-Requested-With": "fetch"})


def test_secilen_aliciya_gonderir(istemci):
    yanit = _gonder(istemci, {"baslik": "Duyuru", "metin": "satır1\nsatır2",
                              "alicilar": ["5566"]})

    assert yanit.status_code == 200
    assert yanit.get_json()["success"] is True
    assert istemci["cagrilar"] == [("Duyuru", "satır1 satır2", ["5566"])]
    assert "905004445566" not in yanit.get_data(as_text=True)


def test_listede_olmayan_alici_reddedilir(istemci):
    yanit = _gonder(istemci, {"baslik": "Duyuru", "metin": "metin", "alicilar": ["9999"]})

    assert yanit.status_code == 400
    assert istemci["cagrilar"] == []


@pytest.mark.parametrize("govde", [
    {"baslik": "", "metin": "metin", "alicilar": ["5566"]},
    {"baslik": "Duyuru", "metin": "", "alicilar": ["5566"]},
    {"baslik": "Duyuru", "metin": "x" * 201, "alicilar": ["5566"]},
    {"baslik": "b" * 61, "metin": "metin", "alicilar": ["5566"]},
    {"baslik": "Duyuru", "metin": "metin"},
])
def test_gecersiz_girdi_reddedilir(istemci, govde):
    assert _gonder(istemci, govde).status_code == 400
    assert istemci["cagrilar"] == []


def test_admin_olmayan_giremez(istemci):
    istemci["kullanici"] = _Kullanici("worker")

    assert _gonder(istemci, {"baslik": "D", "metin": "m", "alicilar": ["5566"]}).status_code == 403
    assert istemci["cagrilar"] == []


def test_2fa_dogrulanmamis_giremez(istemci):
    with istemci["istemci"].session_transaction() as oturum:
        oturum.pop("totp_verified")

    assert _gonder(istemci, {"baslik": "D", "metin": "m", "alicilar": ["5566"]}).status_code == 403


def test_fetch_basligi_olmadan_post_reddedilir(istemci):
    yanit = _gonder(istemci, {"baslik": "D", "metin": "m", "alicilar": ["5566"]}, basliklar={})

    assert yanit.status_code == 403
    assert istemci["cagrilar"] == []
