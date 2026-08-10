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
    app.config.update(TESTING=True, IADE_API_URL="http://localhost:3434")
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

    assert page_response.status_code == 302
    assert data_response.status_code == 302
    assert "/login" in page_response.headers["Location"]
    assert "/login" in data_response.headers["Location"]
