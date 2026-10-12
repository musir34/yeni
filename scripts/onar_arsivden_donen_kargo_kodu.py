#!/usr/bin/env python3
"""Arşivden geri çıkarılıp kargo kodu boş kalan Trendyol siparişlerini onarır — ADDITIVE, IDEMPOTENT.

Eski hata: arşivden çıkarma kargo kodunu statü tablosunda olmayan `shipping_barcode`
alanına yazıyordu → `cargo_tracking_number` boş kalıyordu (archive.py düzeltildi).
Arşiv kaydı geri çıkarmada silindiği için kod Trendyol'dan orderNumber ile çekilir.

Yalnız Yeni / Hazırlanıyor / İşleme Alınmış tablolarında, kaynağı TRENDYOL olan ve
cargo_tracking_number'ı BOŞ olan satırlara bakar; yalnız o alanı doldurur.
Varsayılan KURU çalışma (sadece rapor). Yazmak için --uygula.

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 /home/musir/gullupanel/venv/bin/python scripts/onar_arsivden_donen_kargo_kodu.py [--uygula]
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")


def _trendyol_paketleri(url: str, headers: dict, order_number: str) -> list | None:
    import requests
    r = requests.get(url, headers=headers, params={"orderNumber": order_number}, timeout=60)
    if r.status_code != 200:
        print(f"  ! {order_number}: HTTP {r.status_code} {r.text[:200]}")
        return None
    return r.json().get("content", []) or []


def _kargo_kodu_sec(satir, paketler: list) -> tuple[str, str]:
    """(kod, açıklama). Paket bölünmüşse satırın paket id'siyle eşleşeni seçer."""
    kodlu = [p for p in paketler if (p.get("cargoTrackingNumber") or "")]
    if not kodlu:
        return "", "Trendyol'da kargo kodu yok"
    paket_idleri = {str(satir.shipment_package_id or ""), str(satir.package_number or "")} - {""}
    for p in kodlu:
        if {str(p.get("shipmentPackageId") or ""), str(p.get("id") or "")} & paket_idleri:
            return str(p["cargoTrackingNumber"]), "paket id eşleşti"
    kodlar = {str(p["cargoTrackingNumber"]) for p in kodlu}
    if len(kodlar) == 1:
        return kodlar.pop(), "tek kargo kodu"
    return "", f"belirsiz: {len(kodlar)} farklı paket kodu, paket id eşleşmedi ({', '.join(sorted(kodlar))})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uygula", action="store_true", help="bulunan kodları DB'ye yaz (yoksa yalnız rapor)")
    uygula = ap.parse_args().uygula

    from app import app
    from models import db, OrderCreated, OrderHazirlaniyor, OrderPicking
    from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID

    auth = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
    url = f"https://apigw.trendyol.com/integration/order/sellers/{SUPPLIER_ID}/v2/orders"

    with app.app_context():
        satirlar = []
        for model in (OrderCreated, OrderHazirlaniyor, OrderPicking):
            satirlar += (
                model.query
                .filter(model.source == "TRENDYOL")
                .filter((model.cargo_tracking_number.is_(None)) | (model.cargo_tracking_number == ""))
                .all()
            )
        print(f"Kargo kodu boş aktif Trendyol satırı: {len(satirlar)}")

        bulunan = 0
        for s in satirlar:
            paketler = _trendyol_paketleri(url, headers, s.order_number)
            time.sleep(0.2)
            if paketler is None:
                continue
            kod, aciklama = _kargo_kodu_sec(s, paketler)
            print(f"  {s.__tablename__:<20} {s.order_number:<16} → {kod or '-':<22} ({aciklama})")
            if kod:
                bulunan += 1
                if uygula:
                    s.cargo_tracking_number = kod

        if uygula:
            db.session.commit()
            print(f"OK: {bulunan} satırın kargo kodu yazıldı.")
        else:
            print(f"KURU ÇALIŞMA: {bulunan} satır doldurulabilir. Yazmak için --uygula ekleyin.")


if __name__ == "__main__":
    main()
