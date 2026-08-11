from datetime import datetime, timedelta, timezone

import iade_islemleri


class _FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _CappedClaimsSession:
    def __init__(self):
        self.calls = []

    def get(self, _url, headers, params, timeout=None):
        self.calls.append(dict(params))
        assert timeout == (5, 30)
        start = params["startDate"]
        end = params["endDate"]
        duration = end - start

        # Geniş pencere Trendyol'un 500 kayıt tavanına çarpsın.
        if duration > int(timedelta(days=2).total_seconds() * 1000):
            return _FakeResponse({
                "content": [{"id": "kesilmis-sonuc"}],
                "totalElements": 500,
                "totalPages": 10,
            })

        claim_id = f"claim-{start}-{end}"
        return _FakeResponse({
            "content": [{"id": claim_id, "claimDate": end}],
            "totalElements": 1,
            "totalPages": 1,
        })


def test_claim_fetch_splits_500_record_windows(monkeypatch):
    session = _CappedClaimsSession()
    monkeypatch.setattr(iade_islemleri, "get_requests_session", lambda: session)

    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    result = iade_islemleri.fetch_data_from_api(start, start + timedelta(days=4))

    assert len(result["content"]) == 2
    assert all(row["id"] != "kesilmis-sonuc" for row in result["content"])
    assert len(session.calls) == 3
