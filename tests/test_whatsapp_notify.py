"""whatsapp_notify davranış testleri — ağa çıkmaz, requests.post taklit edilir."""
import json

import pytest
import requests

import whatsapp_notify


class _Yanit:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body
        self.content = json.dumps(body).encode()

    def json(self) -> dict:
        return self._body


def _ok() -> _Yanit:
    return _Yanit(200, {"messages": [{"id": "wamid.TEST"}]})


def _hata(code: int) -> _Yanit:
    return _Yanit(400, {"error": {"code": code, "message": "hata"}})


@pytest.fixture
def ayarli(monkeypatch):
    monkeypatch.setenv("WHATSAPP_STAFF_TOKEN", "gizli-anahtar")
    monkeypatch.setenv("WHATSAPP_STAFF_PHONE_NUMBER_ID", "111")
    monkeypatch.setenv("WHATSAPP_STAFF_NUMBERS", "905001112233,905004445566")


@pytest.fixture
def cagrilar(monkeypatch):
    """requests.post çağrılarını kaydeder; yanıtı 'cevapla' işlevi belirler."""
    kayit = {"liste": [], "cevapla": lambda payload: _ok()}

    def sahte_post(url, json=None, headers=None, timeout=None):
        kayit["liste"].append({"url": url, "payload": json, "headers": headers})
        return kayit["cevapla"](json)

    monkeypatch.setattr(whatsapp_notify.requests, "post", sahte_post)
    return kayit


def test_pencere_aciksa_serbest_metin_gider(ayarli, cagrilar):
    sonuc = whatsapp_notify.notify_staff("Shopify sorusu", "Ayşe: 38 var mı?")

    assert [s["ok"] for s in sonuc] == [True, True]
    assert [c["payload"]["type"] for c in cagrilar["liste"]] == ["text", "text"]
    assert cagrilar["liste"][0]["url"].endswith("/v25.0/111/messages")


def test_pencere_kapaliysa_sablona_duser(ayarli, cagrilar):
    cagrilar["cevapla"] = lambda p: (
        _hata(whatsapp_notify.WINDOW_CLOSED_ERROR_CODE) if p["type"] == "text" else _ok()
    )

    sonuc = whatsapp_notify.notify_staff("Shopify sorusu", "satır1\nsatır2")

    assert all(s["ok"] for s in sonuc)
    tipler = [c["payload"]["type"] for c in cagrilar["liste"]]
    assert tipler == ["text", "template", "text", "template"]
    sablon = cagrilar["liste"][1]["payload"]["template"]
    assert sablon["name"] == "gullu_bildirim"
    assert sablon["language"]["code"] == "en"
    parametreler = sablon["components"][0]["parameters"]
    assert parametreler[1]["text"] == "satır1 satır2"


def test_baska_hatada_sablona_dusmez(ayarli, cagrilar):
    cagrilar["cevapla"] = lambda p: _hata(131030)

    sonuc = whatsapp_notify.notify_staff("Test", "özet")

    assert [s["ok"] for s in sonuc] == [False, False]
    assert all(c["payload"]["type"] == "text" for c in cagrilar["liste"])


def test_bir_aliciya_gitmezse_digerine_devam_eder(ayarli, cagrilar):
    def cevapla(payload):
        if payload["to"] == "905001112233":
            raise requests.ConnectionError("bağlantı yok")
        return _ok()

    cagrilar["cevapla"] = cevapla

    sonuc = whatsapp_notify.notify_staff("Test", "özet")

    assert [(s["to_last4"], s["ok"]) for s in sonuc] == [("2233", False), ("5566", True)]


def test_loga_yalniz_son_dort_hane_yazilir(ayarli, cagrilar, caplog):
    cagrilar["cevapla"] = lambda p: _hata(131030)

    whatsapp_notify.notify_staff("Test", "özet")

    assert "2233" in caplog.text
    assert "905001112233" not in caplog.text
    assert "gizli-anahtar" not in caplog.text


def test_ayar_eksikse_istisna_firlatmaz(monkeypatch, cagrilar):
    for ad in ("WHATSAPP_STAFF_TOKEN", "WHATSAPP_STAFF_PHONE_NUMBER_ID",
               "WHATSAPP_STAFF_NUMBERS"):
        monkeypatch.delenv(ad, raising=False)

    assert whatsapp_notify.notify_staff("Test", "özet") == []
    assert whatsapp_notify.is_configured() is False
    whatsapp_notify.notify_staff_async("Test", "özet")
    assert cagrilar["liste"] == []


def test_sirket_hatti_anahtarlarini_okumaz(monkeypatch, cagrilar):
    """whatsapp_service'in anahtarları (WHATSAPP_TOKEN vb.) bu modülü etkinleştirmez."""
    for ad in ("WHATSAPP_STAFF_TOKEN", "WHATSAPP_STAFF_PHONE_NUMBER_ID",
               "WHATSAPP_STAFF_NUMBERS"):
        monkeypatch.delenv(ad, raising=False)
    monkeypatch.setenv("WHATSAPP_TOKEN", "sirket-anahtari")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "999")

    assert whatsapp_notify.is_configured() is False
    assert whatsapp_notify.notify_staff("Test", "özet") == []
    assert cagrilar["liste"] == []


def test_only_last4_yalniz_secilen_aliciya_gonderir(ayarli, cagrilar):
    sonuc = whatsapp_notify.notify_staff("Duyuru", "metin", only_last4=["5566"])

    assert [(s["to_last4"], s["ok"], s["via"]) for s in sonuc] == [("5566", True, "text")]
    assert [c["payload"]["to"] for c in cagrilar["liste"]] == ["905004445566"]


def test_staff_last4_tam_numarayi_vermez(ayarli):
    assert whatsapp_notify.staff_last4() == ["2233", "5566"]
