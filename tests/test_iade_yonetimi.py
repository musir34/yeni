import requests
from flask import Flask

import iade_yonetimi


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


def make_app(**config):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="test-secret", IADE_API_URL="http://localhost:3434")
    app.config.update(config)
    app.register_blueprint(iade_yonetimi.iade_yonetimi_bp)
    return app


def test_veri_requires_panel_key(monkeypatch):
    app = make_app(IADE_PANEL_KEY="")
    monkeypatch.delenv("IADE_PANEL_KEY", raising=False)

    with app.test_client() as client:
        response = client.get("/iade-yonetimi/veri")

    assert response.status_code == 503
    assert "anahtar" in response.get_json()["mesaj"].lower()


def test_veri_rejects_unknown_category(monkeypatch):
    app = make_app(IADE_PANEL_KEY="secret")

    def unexpected_request(*args, **kwargs):
        raise AssertionError("Geçersiz kategori köprü servisine gönderilmemeli")

    monkeypatch.setattr(iade_yonetimi.requests, "get", unexpected_request)
    with app.test_client() as client:
        response = client.get("/iade-yonetimi/veri?durum=iptal")

    assert response.status_code == 400


def test_veri_proxies_filter_sync_and_key(monkeypatch):
    captured = {}
    payload = {
        "toplam": 1,
        "sayac": {"bekliyor": 0, "kargoda": 1, "teslim": 0},
        "guncelleme": "2026-08-10T15:40:00.000Z",
        "iadeler": [{"referenceId": "1332-1", "kategori": "kargoda"}],
    }

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse(payload)

    monkeypatch.setattr(iade_yonetimi.requests, "get", fake_get)
    app = make_app(IADE_PANEL_KEY="top-secret", IADE_API_URL="http://bridge:3434/")

    with app.test_client() as client:
        response = client.get("/iade-yonetimi/veri?durum=kargoda&sync=1")

    assert response.status_code == 200
    assert response.get_json() == payload
    assert captured["url"] == "http://bridge:3434/api/admin/iadeler"
    assert captured["headers"]["X-Admin-Key"] == "top-secret"
    assert captured["params"] == {"durum": "kargoda", "sync": "1"}
    assert captured["timeout"] == (3.05, 45)


def test_veri_hides_upstream_auth_failure(monkeypatch):
    monkeypatch.setattr(
        iade_yonetimi.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"mesaj": "Yetkisiz"}, status_code=401),
    )
    app = make_app(IADE_PANEL_KEY="wrong")

    with app.test_client() as client:
        response = client.get("/iade-yonetimi/veri")

    assert response.status_code == 503
    assert "geçersiz" in response.get_json()["mesaj"].lower()


def test_veri_reports_bridge_timeout(monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.Timeout("bridge timeout")

    monkeypatch.setattr(iade_yonetimi.requests, "get", timeout)
    app = make_app(IADE_PANEL_KEY="secret")

    with app.test_client() as client:
        response = client.get("/iade-yonetimi/veri")

    assert response.status_code == 503
    assert "zaman aşımı" in response.get_json()["mesaj"].lower()


def test_real_panel_routes_require_login(client):
    page_response = client.get("/iade-yonetimi")
    data_response = client.get("/iade-yonetimi/veri")
    create_response = client.post("/iade-yonetimi/olustur", json={})

    assert page_response.status_code == 302
    assert data_response.status_code == 302
    assert create_response.status_code == 302
    assert "/login" in page_response.headers["Location"]
    assert "/login" in data_response.headers["Location"]
    assert "/login" in create_response.headers["Location"]


def test_create_iade_proxies_admin_key_and_payload(monkeypatch):
    captured = {}
    result = {
        "ok": True,
        "referenceId": "TY123-1",
        "iadeKodu": "TY123-1",
        "labelUrl": "https://mn.tc/example",
    }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse(result, status_code=201)

    monkeypatch.setattr(iade_yonetimi.requests, "post", fake_post)
    app = make_app(IADE_PANEL_KEY="panel-secret", IADE_API_URL="http://bridge:3434/")
    payload = {
        "orderNumber": "TY123",
        "email": "",
        "customerName": "Test Müşteri",
        "reason": "Değişim gönderimi",
        "source": "trendyol",
        "requestId": "9a46ce15-421d-4d02-8060-cf13f0cb5426",
        "createdBy": "admin",
    }

    with app.app_context():
        response = iade_yonetimi.create_iade(payload)

    assert response == result
    assert captured["url"] == "http://bridge:3434/api/admin/iadeler"
    assert captured["headers"]["X-Admin-Key"] == "panel-secret"
    assert captured["json"] == payload
    assert captured["timeout"] == (5, 45)


def test_create_route_allows_manager_and_keeps_email_optional(monkeypatch):
    captured = {}

    def fake_create(payload):
        captured.update(payload)
        return {"ok": True, "iadeKodu": "789-1", "referenceId": "789-1", "labelUrl": ""}

    monkeypatch.setattr(iade_yonetimi, "create_iade", fake_create)
    app = make_app(IADE_PANEL_KEY="secret")
    request_payload = {
        "orderNumber": "789",
        "email": "",
        "customerName": "Ayşe Yılmaz",
        "reason": "Değişim gönderimi — 39 numara",
        "source": "trendyol",
        "requestId": "9a46ce15-421d-4d02-8060-cf13f0cb5426",
    }

    with app.test_client() as client:
        with client.session_transaction() as flask_session:
            flask_session["role"] = "manager"
            flask_session["username"] = "yonetici"
        response = client.post(
            "/iade-yonetimi/olustur",
            json=request_payload,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

    assert response.status_code == 200
    assert response.get_json()["iadeKodu"] == "789-1"
    assert captured["source"] == "trendyol"
    assert captured["email"] == ""
    assert captured["createdBy"] == "yonetici"


def test_create_route_rejects_worker_before_bridge_call(monkeypatch):
    monkeypatch.setattr(
        iade_yonetimi,
        "create_iade",
        lambda payload: (_ for _ in ()).throw(AssertionError("Köprü çağrılmamalı")),
    )
    app = make_app(IADE_PANEL_KEY="secret")

    with app.test_client() as client:
        with client.session_transaction() as flask_session:
            flask_session["role"] = "worker"
        response = client.post(
            "/iade-yonetimi/olustur",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

    assert response.status_code == 403


def test_create_route_rejects_invalid_email(monkeypatch):
    monkeypatch.setattr(
        iade_yonetimi,
        "create_iade",
        lambda payload: (_ for _ in ()).throw(AssertionError("Köprü çağrılmamalı")),
    )
    app = make_app(IADE_PANEL_KEY="secret")

    with app.test_client() as client:
        with client.session_transaction() as flask_session:
            flask_session["role"] = "admin"
        response = client.post(
            "/iade-yonetimi/olustur",
            json={
                "orderNumber": "123",
                "email": "gecersiz",
                "reason": "Değişim",
                "source": "degisim",
                "requestId": "9a46ce15-421d-4d02-8060-cf13f0cb5426",
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

    assert response.status_code == 400
    assert "e-posta" in response.get_json()["mesaj"].lower()
