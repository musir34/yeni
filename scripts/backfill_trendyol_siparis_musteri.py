#!/usr/bin/env python3
"""trendyol_siparis_musteri eşlemesini geçmiş siparişlerle doldurur — ADDITIVE, IDEMPOTENT.

Soru-Cevap kartı soruyu soranın siparişlerini bu tablodan bulur (sipariş no → customerId).
Yeni siparişler senkronda kendiliğinden yazılır; bu betik yalnız geçmişi doldurur.
Sipariş API'si yaklaşık son 3 ayı verir; 2 haftalık pencerelerle geriye gider.
Var olan sipariş no'ya dokunmaz, başka tabloya YAZMAZ. Tablo yoksa açar.

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 /home/musir/gullupanel/venv/bin/python scripts/backfill_trendyol_siparis_musteri.py [--gun 90]
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")

PENCERE = timedelta(days=14)
STATULER = "Created,Picking,Invoiced,ReadyToShip,Shipped,Delivered,Cancelled,UnSupplied"  # senkronla aynı küme


def _paketler(url: str, headers: dict, bas: datetime, son: datetime):
    import requests
    sayfa, toplam = 0, 1
    while sayfa < toplam:
        params = {"startDate": int(bas.timestamp() * 1000), "endDate": int(son.timestamp() * 1000),
                  "status": STATULER, "page": sayfa, "size": 200}
        r = requests.get(url, headers=headers, params=params, timeout=60)
        if r.status_code != 200:
            print(f"  ! HTTP {r.status_code} ({bas:%d.%m}–{son:%d.%m}, sayfa {sayfa}): {r.text[:200]}")
            return
        veri = r.json()
        toplam = veri.get("totalPages", 1) or 1
        yield from veri.get("content", []) or []
        sayfa += 1
        time.sleep(0.2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gun", type=int, default=90, help="kaç gün geriye (varsayılan 90)")
    gun = ap.parse_args().gun

    from app import app
    from models import db, TrendyolSiparisMusteri
    from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID
    from trendyol_qna.siparis_musteri import musteri_siparislerini_kaydet

    auth = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
    url = f"https://apigw.trendyol.com/integration/order/sellers/{SUPPLIER_ID}/v2/orders"

    with app.app_context():
        TrendyolSiparisMusteri.__table__.create(bind=db.engine, checkfirst=True)
        once = db.session.query(TrendyolSiparisMusteri).count()
        son = datetime.now()
        bitis = son - timedelta(days=gun)
        while son > bitis:
            bas = max(son - PENCERE, bitis)
            paketler = list(_paketler(url, headers, bas, son))
            n = musteri_siparislerini_kaydet(paketler)
            print(f"{bas:%d.%m.%Y}–{son:%d.%m.%Y}: {len(paketler)} paket, {n} sipariş no işlendi")
            son = bas
        sonra = db.session.query(TrendyolSiparisMusteri).count()
        print(f"OK: eşleme {once} → {sonra} satır (+{sonra - once}).")


if __name__ == "__main__":
    main()
