#!/usr/bin/env python3
"""Sayfa yetkileri altyapısı — ADDITIVE, IDEMPOTENT.

1) users.is_owner (BOOLEAN NOT NULL DEFAULT false) kolonu
2) kullanici_sayfa_yetki tablosu (rol varsayılanından kişiye özel fark: izin=True ekle / False kaldır)
3) --sahip <kullanici_adi> verilirse o kullanıcı sahip yapılır (her sayfa + yetkileri yalnız o düzenler)

Var olan kolon/tabloya dokunmaz; kimsenin erişimi değişmez (rol varsayılanları = bugünkü erişim).

Çalıştırma (production DB'ye .env üzerinden bağlanır; servis RESTART ÖNCESİ):
    DISABLE_JOBS=1 python scripts/add_sayfa_yetki.py --sahip musir
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sahip", help="Sahip yapılacak kullanıcı adı (ör. musir)")
    args = parser.parse_args()

    from app import app
    from models import db
    from sqlalchemy import text

    with app.app_context():
        db.session.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_owner BOOLEAN NOT NULL DEFAULT false"
        ))
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS kullanici_sayfa_yetki (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                sayfa_kodu VARCHAR(64) NOT NULL,
                izin BOOLEAN NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT uq_kullanici_sayfa_yetki UNIQUE (user_id, sayfa_kodu)
            )
        """))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_kullanici_sayfa_yetki_user_id ON kullanici_sayfa_yetki (user_id)"
        ))
        db.session.commit()
        print("OK: users.is_owner kolonu ve kullanici_sayfa_yetki tablosu hazır.")

        if args.sahip:
            sonuc = db.session.execute(
                text("UPDATE users SET is_owner = true WHERE username = :u"), {"u": args.sahip}
            )
            db.session.commit()
            if sonuc.rowcount:
                print(f"OK: '{args.sahip}' sahip yapıldı.")
            else:
                print(f"UYARI: '{args.sahip}' adlı kullanıcı bulunamadı, sahip atanmadı.")


if __name__ == "__main__":
    main()
