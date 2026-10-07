"""WhatsApp webhook — izole Flask testi (gerçek uygulama/Meta yok).

Çalıştırma (çıplak pytest YASAK — conftest canlı uygulamayı yükler):
  DISABLE_JOBS=1 .venv/bin/python -m pytest --noconftest tests/test_whatsapp_webhook.py
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask  # noqa: E402

from whatsapp_webhook import whatsapp_webhook_bp  # noqa: E402

VERIFY = "dogrulama-anahtari"
SECRET = "uygulama-sirri"
URL = "/api/whatsapp/webhook"


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", VERIFY)
    monkeypatch.setenv("FB_APP_SECRET", SECRET)
    app = Flask(__name__)
    app.register_blueprint(whatsapp_webhook_bp)
    return app.test_client()


def _imzali_post(istemci, payload: dict, sir: str = SECRET):
    govde = json.dumps(payload).encode("utf-8")
    imza = "sha256=" + hmac.new(sir.encode("utf-8"), govde, hashlib.sha256).hexdigest()
    return istemci.post(URL, data=govde,
                        headers={"Content-Type": "application/json", "X-Hub-Signature-256": imza})


def test_get_dogrulama_dogru_anahtarla_challenge_doner(istemci):
    r = istemci.get(URL, query_string={"hub.mode": "subscribe",
                                       "hub.verify_token": VERIFY, "hub.challenge": "1158201444"})
    assert r.status_code == 200
    assert r.get_data(as_text=True) == "1158201444"


def test_get_dogrulama_yanlis_anahtar_403(istemci):
    r = istemci.get(URL, query_string={"hub.mode": "subscribe",
                                       "hub.verify_token": "yanlis", "hub.challenge": "1"})
    assert r.status_code == 403


def test_post_imzasiz_403(istemci):
    r = istemci.post(URL, json={"object": "whatsapp_business_account", "entry": []})
    assert r.status_code == 403


def test_post_yanlis_imza_403(istemci):
    r = _imzali_post(istemci, {"object": "whatsapp_business_account", "entry": []}, sir="baska")
    assert r.status_code == 403


def test_post_gecerli_imza_200(istemci):
    payload = {"object": "whatsapp_business_account",
               "entry": [{"id": "282075360485298",
                          "changes": [{"field": "smb_message_echoes", "value": {}}]}]}
    r = _imzali_post(istemci, payload)
    assert r.status_code == 200
    assert r.get_json() == {"ok": True}


def test_post_baska_nesne_sessizce_200(istemci):
    r = _imzali_post(istemci, {"object": "instagram", "entry": []})
    assert r.status_code == 200


def test_post_sir_tanimsizsa_403(istemci, monkeypatch):
    monkeypatch.delenv("FB_APP_SECRET")
    r = _imzali_post(istemci, {"object": "whatsapp_business_account", "entry": []})
    assert r.status_code == 403
