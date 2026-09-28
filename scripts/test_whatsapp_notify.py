#!/usr/bin/env python3
"""whatsapp_notify kurulum testi — WHATSAPP_STAFF_NUMBERS'taki herkese deneme bildirimi atar.

.env'e WHATSAPP_STAFF_TOKEN yazıldıktan sonra uçtan uca doğrulama içindir.
DB'ye DOKUNMAZ. Anahtarı ve tam numarayı ekrana basmaz.

Çalıştırma:
    python scripts/test_whatsapp_notify.py
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from whatsapp_notify import is_configured, notify_staff


def main():
    if not is_configured():
        print("HATA: .env'de WHATSAPP_STAFF_TOKEN / WHATSAPP_STAFF_PHONE_NUMBER_ID / "
              "WHATSAPP_STAFF_NUMBERS eksik.")
        sys.exit(1)
    sonuclar = notify_staff("Deneme bildirimi", "Panel bağlantı testi başarılı")
    for s in sonuclar:
        durum = "OK" if s["ok"] else f"BAŞARISIZ ({s.get('code')}: {s.get('message')})"
        print(f"…{s['to_last4']}: {durum}")
    sys.exit(0 if sonuclar and all(s["ok"] for s in sonuclar) else 1)


if __name__ == "__main__":
    main()
