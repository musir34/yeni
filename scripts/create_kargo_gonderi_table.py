#!/usr/bin/env python3
"""kargo_gonderi tablosunu açar — ADDITIVE, IDEMPOTENT.

MNG giden gönderi kayıtları (değişim / manuel sipariş / Shopify siparişi için otomatik
açılan kargo). Tablo zaten varsa hiçbir şey yapmaz, başka tabloya/kolona DOKUNMAZ.

Çalıştırma (production DB'ye .env üzerinden bağlanır; RESTART ÖNCESİ):
    DISABLE_JOBS=1 python scripts/create_kargo_gonderi_table.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")


def main():
    from app import app
    from models import db
    from sqlalchemy import text

    with app.app_context():
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS kargo_gonderi (
                id SERIAL PRIMARY KEY,
                kaynak VARCHAR(20) NOT NULL,
                kaynak_ref VARCHAR(120) NOT NULL,
                kaynak_ad VARCHAR(60),
                referans VARCHAR(20) NOT NULL UNIQUE,
                ortam VARCHAR(10) DEFAULT 'sandbox',
                shipment_id VARCHAR(30),
                fatura_id VARCHAR(30),
                barkod VARCHAR(60),
                zpl TEXT,
                durum VARCHAR(20) NOT NULL DEFAULT 'bekliyor',
                kaynak_durum VARCHAR(30),
                barkod_istendi BOOLEAN NOT NULL DEFAULT FALSE,
                parca_adet INTEGER NOT NULL DEFAULT 1,
                mng_durum_kodu INTEGER,
                mng_durum_metni VARCHAR(80),
                takip_url VARCHAR(255),
                kapida_odeme_tutari NUMERIC(10,2),
                tahsil_edildi BOOLEAN NOT NULL DEFAULT FALSE,
                teslim_alan VARCHAR(120),
                teslim_zamani TIMESTAMP,
                alici_ad VARCHAR(120),
                alici_telefon VARCHAR(30),
                alici_adres TEXT,
                il VARCHAR(40),
                ilce VARCHAR(40),
                hata TEXT,
                deneme INTEGER NOT NULL DEFAULT 0,
                son_sorgu_at TIMESTAMP,
                kargoda_at TIMESTAMP,
                iptal_at TIMESTAMP,
                olusturuldu_at TIMESTAMP NOT NULL DEFAULT NOW(),
                guncellendi_at TIMESTAMP
            )
        """))
        # 2026-10-15 (ikinci sürüm): barkod işleme alınınca istenir — mevcut tabloya additive kolon
        db.session.execute(text(
            "ALTER TABLE kargo_gonderi ADD COLUMN IF NOT EXISTS barkod_istendi BOOLEAN NOT NULL DEFAULT FALSE"))
        db.session.execute(text(
            "ALTER TABLE kargo_gonderi ADD COLUMN IF NOT EXISTS parca_adet INTEGER NOT NULL DEFAULT 1"))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_kargo_gonderi_kaynak ON kargo_gonderi (kaynak)"))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_kargo_gonderi_kaynak_ref ON kargo_gonderi (kaynak_ref)"))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_kargo_gonderi_kaynak_kaynak_ref ON kargo_gonderi (kaynak, kaynak_ref)"))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_kargo_gonderi_durum ON kargo_gonderi (durum)"))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_kargo_gonderi_shipment_id ON kargo_gonderi (shipment_id)"))
        db.session.commit()
        print("OK: kargo_gonderi tablosu hazır.")


if __name__ == "__main__":
    main()
