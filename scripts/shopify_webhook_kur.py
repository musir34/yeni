#!/usr/bin/env python3
"""Shopify sipariş webhook aboneliğini kurar — IDEMPOTENT (varsa yeniden açmaz).

Siparişte değişiklik olunca (kalem çıkarma) Shopify panele haber verir; MNG kapıda ödeme tutarı
ve etiketi anında güncellenir (mng_kargo/shopify_webhook.py). Adres: PUBLIC_BASE_URL + webhook yolu.

Çalıştırma (sunucuda, bir kez; kod deploy + restart SONRASI):
    DISABLE_JOBS=1 python scripts/shopify_webhook_kur.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")

KONULAR = ("ORDERS_UPDATED", "ORDERS_EDITED")

MEVCUT = """
query { webhookSubscriptions(first: 100) { edges { node { id topic uri } } } }
"""
OLUSTUR = """
mutation Kur($topic: WebhookSubscriptionTopic!, $sub: WebhookSubscriptionInput!) {
  webhookSubscriptionCreate(topic: $topic, webhookSubscription: $sub) {
    webhookSubscription { id topic uri }
    userErrors { field message }
  }
}
"""


def main() -> int:
    from app import app
    from mng_kargo.shopify_webhook import WEBHOOK_YOLU
    from shopify_site.shopify_service import shopify_service

    taban = (os.environ.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if not taban.startswith("https://"):
        print("HATA: .env PUBLIC_BASE_URL=https://... tanımlı olmalı")
        return 1
    if not (os.environ.get("SHOPIFY_CLIENT_SECRET") or "").strip():
        print("HATA: .env SHOPIFY_CLIENT_SECRET tanımlı olmalı (webhook imzası)")
        return 1
    adres = taban + WEBHOOK_YOLU
    with app.app_context():
        sonuc = shopify_service._post_graphql(MEVCUT)
        if not sonuc.get("success"):
            print("HATA: mevcut abonelikler okunamadı:", sonuc.get("error") or sonuc)
            return 1
        var = {(e["node"]["topic"], e["node"].get("uri"))
               for e in sonuc["data"]["webhookSubscriptions"]["edges"]}
        for konu in KONULAR:
            if (konu, adres) in var:
                print(f"zaten var: {konu} → {adres}")
                continue
            r = shopify_service._post_graphql(OLUSTUR, {"topic": konu, "sub": {"uri": adres, "format": "JSON"}})
            hatalar = (((r.get("data") or {}).get("webhookSubscriptionCreate") or {}).get("userErrors")
                       or ([r.get("error") or r] if not r.get("success") else []))
            if hatalar:
                print(f"HATA: {konu} kurulamadı:", hatalar)
                return 1
            print(f"kuruldu: {konu} → {adres}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
