#!/usr/bin/env python3
"""WhatsApp Cloud API kurulum testi — tek numaraya deneme mesajı atar.

Meta tarafı (token, phone_number_id, onaylı şablon) hazırlanınca .env
doldurulup bu script ile uçtan uca doğrulanır. DB'ye DOKUNMAZ.

Çalıştırma:
    python scripts/test_whatsapp.py 05xxxxxxxxx            # onaylı şablonla
    python scripts/test_whatsapp.py 05xxxxxxxxx --text     # serbest metin
                                    (yalnız alıcı son 24 saatte numaraya yazdıysa ulaşır)
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from whatsapp_service import (is_configured, normalize_whatsapp_no,
                              send_whatsapp_template, send_whatsapp_text)


def main():
    if len(sys.argv) < 2:
        print("Kullanım: python scripts/test_whatsapp.py <numara> [--text]")
        sys.exit(1)
    if not is_configured():
        print("HATA: .env'de WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID eksik.")
        sys.exit(1)
    numara = normalize_whatsapp_no(sys.argv[1])
    if not numara:
        print("HATA: geçersiz numara. 05xx xxx xx xx biçiminde girin.")
        sys.exit(1)
    if "--text" in sys.argv:
        ok = send_whatsapp_text(numara, "Güllü Panel WhatsApp test mesajı ✅")
    else:
        ok = send_whatsapp_template(numara, "Güllü Panel test bildirimi",
                                    "Kurulum başarılı — bu mesajı görüyorsanız hat hazır ✅")
    print(f"{'OK' if ok else 'BAŞARISIZ'}: {numara}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
