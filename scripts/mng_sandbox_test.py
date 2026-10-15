#!/usr/bin/env python3
"""MNG ApiZone SANDBOX doğrulama — giden gönderi akışının uçtan uca provası.

Yalnız test ortamına (MNG_SANDBOX_*) gider; prod kimliği kullanılmaz, DB'ye dokunmaz,
Flask app yüklenmez. Sırayla:
  1. token
  2. il listesi + İstanbul ilçeleri (cbsinfoapi)
  3. createOrder + createbarcode  (referans: SB-<zaman>, kapıda ödeme 10 TL ile)
  4. getshipmentstatus + trackshipment
  5. cancelorder
Her adımın ham cevabını (şifresiz) ekrana basar; ZPL etiketi scratchpad'e yazar.

Çalıştırma:
    python scripts/mng_sandbox_test.py            # tam akış
    python scripts/mng_sandbox_test.py --cod 0    # kapıda ödemesiz
    python scripts/mng_sandbox_test.py --iptal-yok
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mng_kargo.ayar import MngAyar  # noqa: E402
from mng_kargo.client import MngClient, MngHata  # noqa: E402
from mng_kargo.govde import Alici, GonderiIstegi  # noqa: E402


def _yaz(baslik, veri):
    print(f"\n=== {baslik} ===")
    try:
        metin = json.dumps(veri, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        metin = str(veri)
    if len(metin) > 3000:
        metin = metin[:3000] + "\n... (kısaltıldı)"
    print(metin)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cod", type=float, default=10.0, help="kapıda ödeme tutarı (0 = yok)")
    p.add_argument("--iptal-yok", action="store_true", help="sonda cancelorder çağırma")
    p.add_argument("--il", default="İSTANBUL")
    p.add_argument("--ilce", default="KADIKÖY")
    args = p.parse_args()

    ayar = MngAyar.from_env("sandbox")
    if not ayar.hazir:
        print("HATA: MNG_SANDBOX_CLIENT_ID / CLIENT_SECRET / CUSTOMER_NUMBER / PASSWORD .env'de eksik.")
        return 2
    print(f"Ortam: {ayar.ortam}  {ayar.base_url}  müşteri {ayar.customer_number}")

    c = MngClient(ayar)

    # 1) token
    try:
        c._jwt()
        print("token: OK")
    except MngHata as exc:
        print(f"token: HATA {exc}")
        return 1

    # 2) il / ilçe
    il_kodu = 0
    try:
        iller = c.sehirler()
        print(f"il sayısı: {len(iller)}; ilk 3: {iller[:3]}")
        for il in iller:
            if str(il.get("name") or "").upper().startswith(args.il.upper()):
                il_kodu = int(il.get("code") or 0)
                break
        print(f"{args.il} kodu: {il_kodu}")
        if il_kodu:
            ilceler = c.ilceler(il_kodu)
            print(f"{args.il} ilçe sayısı: {len(ilceler)}; ilk 3: {ilceler[:3]}")
    except MngHata as exc:
        print(f"cbsinfoapi: HATA {exc}  (ürün aboneliği yoksa 401 gelir; isimle devam)")

    # 3) gönderi
    referans = f"SB{int(time.time())}"
    alici = Alici(
        ad_soyad="Test Alici", adres="Test Mah. Deneme Sok. No:1 D:2", telefon="5321234567",
        il=args.il, ilce=args.ilce, il_kodu=il_kodu, email="test@gullushoes.com",
    )
    istek = GonderiIstegi(referans=referans, alici=alici, kapida_odeme_tutari=args.cod or None,
                          aciklama="Gullu Shoes sandbox provasi")
    try:
        siparis = c.siparis_olustur(istek)
        _yaz("createOrder", siparis)
    except MngHata as exc:
        _yaz("createOrder HATA", {"mesaj": str(exc), "kod": exc.kod, "govde": exc.govde})
        return 1
    try:
        barkod = c.barkod_olustur(istek)
        ozet = {k: v for k, v in barkod.items() if k != "barcodes"}
        ozet["barcodes"] = [{"barcode": b.get("barcode"), "value_len": len(b.get("value") or "")}
                            for b in (barkod.get("barcodes") or []) if isinstance(b, dict)]
        _yaz("createbarcode", ozet)
        zpl = ((barkod.get("barcodes") or [{}])[0] or {}).get("value") or ""
        if zpl:
            hedef = Path(os.getenv("MNG_ZPL_CIKTI") or PROJECT_ROOT / "uploads" / f"mng_sandbox_{referans}.zpl")
            hedef.parent.mkdir(parents=True, exist_ok=True)
            hedef.write_text(zpl, encoding="utf-8")
            print(f"ZPL etiket yazıldı: {hedef}  (önizleme: http://labelary.com/viewer.html)")
    except MngHata as exc:
        _yaz("createbarcode HATA", {"mesaj": str(exc), "kod": exc.kod, "govde": exc.govde})

    # 4) takip
    try:
        d = c.durum(referans)
        _yaz("getshipmentstatus", d.__dict__ if d else None)
        _yaz("trackshipment", c.hareketler(referans))
    except MngHata as exc:
        _yaz("takip HATA", {"mesaj": str(exc), "kod": exc.kod, "govde": exc.govde})

    # 5) iptal
    if not args.iptal_yok:
        try:
            _yaz("cancelorder", c.iptal(referans))
        except MngHata as exc:
            _yaz("cancelorder HATA", {"mesaj": str(exc), "kod": exc.kod, "govde": exc.govde})

    print(f"\nReferans: {referans}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
