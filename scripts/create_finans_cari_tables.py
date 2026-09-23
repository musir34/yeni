#!/usr/bin/env python3
"""Finans Cari Hesap tablolarını açar — ADDITIVE, IDEMPOTENT.

finans_cari (tedarikçi/müşteri hesabı), finans_cari_hareket (alım/ödeme/satış/tahsilat),
finans_cari_kalem (mal girişi dökümü). Mevcut tablolara dokunmaz; yalnızca
finans_islem'e nullable bir kolon ekler (cari bağı için ters yön gerekmez —
bağ finans_cari_hareket.islem_id üzerinden kurulur, kolon eklenmez).

Çalıştırma (sunucuda proje dizininde):
    DISABLE_JOBS=1 ../venv/bin/python scripts/create_finans_cari_tables.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")

DDL = [
    """
    CREATE TABLE IF NOT EXISTS finans_cari (
        id SERIAL PRIMARY KEY,
        ad VARCHAR(150) NOT NULL UNIQUE,
        tur VARCHAR(20) NOT NULL DEFAULT 'tedarikci',
        telefon VARCHAR(50),
        notlar TEXT,
        bakiye NUMERIC(12,2) NOT NULL DEFAULT 0,
        aktif BOOLEAN NOT NULL DEFAULT TRUE,
        olusturma_tarihi TIMESTAMP,
        guncelleme_tarihi TIMESTAMP,
        olusturan_kullanici_id INTEGER REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS finans_cari_hareket (
        id SERIAL PRIMARY KEY,
        cari_id INTEGER NOT NULL REFERENCES finans_cari(id),
        tur VARCHAR(20) NOT NULL,
        yon SMALLINT NOT NULL CHECK (yon IN (1, -1)),
        tutar NUMERIC(12,2) NOT NULL CHECK (tutar > 0),
        onceki_bakiye NUMERIC(12,2) NOT NULL,
        yeni_bakiye NUMERIC(12,2) NOT NULL,
        tarih TIMESTAMP NOT NULL,
        aciklama VARCHAR(500),
        islem_id INTEGER REFERENCES finans_islem(id),
        iptal BOOLEAN NOT NULL DEFAULT FALSE,
        iptal_tarihi TIMESTAMP,
        iptal_kullanici_id INTEGER REFERENCES users(id),
        kullanici_id INTEGER NOT NULL REFERENCES users(id),
        olusturma_tarihi TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_finans_cari_hareket_cari_tarih ON finans_cari_hareket (cari_id, tarih)",
    "CREATE INDEX IF NOT EXISTS ix_finans_cari_hareket_islem ON finans_cari_hareket (islem_id)",
    """
    CREATE TABLE IF NOT EXISTS finans_cari_kalem (
        id SERIAL PRIMARY KEY,
        hareket_id INTEGER NOT NULL REFERENCES finans_cari_hareket(id) ON DELETE CASCADE,
        ad VARCHAR(200) NOT NULL,
        adet NUMERIC(12,2) NOT NULL DEFAULT 1,
        birim_fiyat NUMERIC(12,2) NOT NULL DEFAULT 0,
        tutar NUMERIC(12,2) NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_finans_cari_kalem_hareket ON finans_cari_kalem (hareket_id)",
]


def main():
    from app import app
    from models import db
    from sqlalchemy import text, inspect

    with app.app_context():
        for stmt in DDL:
            db.session.execute(text(stmt))
        db.session.commit()
        insp = inspect(db.engine)
        for t in ("finans_cari", "finans_cari_hareket", "finans_cari_kalem"):
            print(f"{'OK ' if insp.has_table(t) else 'YOK'}: {t}")


if __name__ == "__main__":
    main()
