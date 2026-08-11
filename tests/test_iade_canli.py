from datetime import datetime

from flask import Flask

import iade_islemleri


def sample_claim(claim_id="claim-1", status="Created"):
    return {
        "id": claim_id,
        "claimId": claim_id,
        "orderNumber": "12345",
        "customerFirstName": "Ayşe",
        "customerLastName": "Yılmaz",
        "claimDate": 1786370400000,
        "lastModifiedDate": 1786374000000,
        "cargoTrackingNumber": 987654321,
        "cargoProviderName": "Kargo",
        "items": [{
            "orderLine": {
                "barcode": "ABC123",
                "merchantSku": "SKU-1",
                "productName": "Siyah Ayakkabı",
                "productSize": "38",
                "productColor": "Siyah",
            },
            "claimItems": [{
                "id": f"line-{claim_id}",
                "claimItemStatus": {"name": status},
                "customerClaimItemReason": {"name": "Beden uymadı"},
                "customerNote": "Bir numara küçük geldi",
                "autoAccepted": False,
                "acceptedBySeller": False,
            }],
        }],
    }


def reset_live_cache():
    iade_islemleri._live_return_cache["payload"] = None
    iade_islemleri._live_return_cache["stored_at"] = 0.0


def test_normalize_claim_preserves_live_product_details():
    normalized = iade_islemleri._normalize_claim(sample_claim())

    assert normalized["returnRequestNumber"] == "claim-1"
    assert normalized["cargoTrackingNumber"] == "987654321"
    assert normalized["statusGroup"] == "new"
    assert normalized["products"][0]["merchantSku"] == "SKU-1"
    assert normalized["products"][0]["customerNote"] == "Bir numara küçük geldi"


def test_build_live_payload_counts_status_groups():
    claims = [
        sample_claim("new", "Created"),
        sample_claim("action", "WaitingInAction"),
        sample_claim("accepted", "Accepted"),
        sample_claim("rejected", "Rejected"),
        sample_claim("cancelled", "Cancelled"),
    ]

    payload = iade_islemleri._build_live_payload(claims, source="trendyol")

    assert payload["total"] == 5
    assert payload["itemTotal"] == 5
    assert payload["counts"] == {
        "all": 5,
        "new": 1,
        "action": 1,
        "accepted": 1,
        "rejected": 1,
        "cancelled": 1,
    }


def test_live_payload_uses_short_cache(monkeypatch):
    reset_live_cache()
    calls = []

    def fake_fetch(start_date, end_date):
        calls.append((start_date, end_date))
        return {"content": [sample_claim()]}

    monkeypatch.setattr(iade_islemleri, "fetch_data_from_api", fake_fetch)

    first = iade_islemleri.get_live_return_payload()
    second = iade_islemleri.get_live_return_payload()

    assert first["source"] == "trendyol"
    assert second["source"] == "cache"
    assert len(calls) == 1


def test_live_payload_keeps_last_success_on_api_failure(monkeypatch):
    reset_live_cache()
    monkeypatch.setattr(
        iade_islemleri,
        "fetch_data_from_api",
        lambda start_date, end_date: {"content": [sample_claim()]},
    )
    iade_islemleri.get_live_return_payload()
    monkeypatch.setattr(iade_islemleri, "fetch_data_from_api", lambda start_date, end_date: None)

    payload = iade_islemleri.get_live_return_payload(force=True)

    assert payload["source"] == "cache"
    assert payload["stale"] is True
    assert payload["total"] == 1
    assert payload["warning"]


class FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_fetch_uses_official_page_size_user_agent_and_timeout(monkeypatch):
    calls = []
    pages = {
        0: {"totalElements": 201, "totalPages": 2, "content": [sample_claim("a")]},
        1: {"totalElements": 201, "totalPages": 2, "content": [sample_claim("b")]},
    }

    class FakeSession:
        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(pages[kwargs["params"]["page"]])

    monkeypatch.setattr(iade_islemleri, "get_requests_session", lambda: FakeSession())
    result = iade_islemleri.fetch_data_from_api(datetime(2026, 8, 1), datetime(2026, 8, 10))

    assert [item["id"] for item in result["content"]] == ["a", "b"]
    assert len(calls) == 2
    assert calls[0][1]["params"]["size"] == 200
    assert calls[0][1]["headers"]["User-Agent"].endswith("SelfIntegration")
    assert calls[0][1]["timeout"] == (5, 30)


def test_live_data_route_returns_json(monkeypatch):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(iade_islemleri.iade_islemleri)
    expected = iade_islemleri._build_live_payload([sample_claim()], source="trendyol")
    monkeypatch.setattr(iade_islemleri, "get_live_return_payload", lambda force=False: expected)

    with app.test_client() as client:
        response = client.get("/iade-listesi/veri")

    assert response.status_code == 200
    assert response.get_json()["returns"][0]["orderNumber"] == "12345"


def test_real_live_data_route_requires_login(client):
    response = client.get("/iade-listesi/veri")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
