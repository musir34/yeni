#!/usr/bin/env python3
"""Finans Kasası tablolarını açar — ADDITIVE, IDEMPOTENT.

Mevcut kasa (ana_kasa / kasa / kasa_kategoriler / odeme) tablolarına DOKUNMAZ.
Üç hesaplı yeni kasa: finans_hesap, finans_kategori, finans_gider_adi,
finans_ana_gider_kalem, finans_islem + 3 sabit hesap seed'i (beyazit/elde/banka).
Tablolar zaten varsa hiçbir şey yapmaz.

Çalıştırma (production DB'ye .env üzerinden bağlanır):
    DISABLE_JOBS=1 python scripts/create_finans_tables.py
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
    CREATE TABLE IF NOT EXISTS finans_hesap (
        id SERIAL PRIMARY KEY,
        kod VARCHAR(20) NOT NULL UNIQUE,
        ad VARCHAR(100) NOT NULL,
        bakiye NUMERIC(12,2) NOT NULL DEFAULT 0,
        sira SMALLINT NOT NULL DEFAULT 0,
        guncelleme_tarihi TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS finans_kategori (
        id SERIAL PRIMARY KEY,
        tur VARCHAR(20) NOT NULL,
        ad VARCHAR(100) NOT NULL,
        aktif BOOLEAN NOT NULL DEFAULT TRUE,
        sira SMALLINT NOT NULL DEFAULT 0,
        olusturma_tarihi TIMESTAMP,
        olusturan_kullanici_id INTEGER REFERENCES users(id),
        CONSTRAINT uq_finans_kategori_tur_ad UNIQUE (tur, ad)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS finans_gider_adi (
        id SERIAL PRIMARY KEY,
        kategori_id INTEGER NOT NULL REFERENCES finans_kategori(id),
        ad VARCHAR(150) NOT NULL,
        varsayilan_tutar NUMERIC(12,2),
        aktif BOOLEAN NOT NULL DEFAULT TRUE,
        olusturma_tarihi TIMESTAMP,
        CONSTRAINT uq_finans_gider_adi_kat_ad UNIQUE (kategori_id, ad)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_finans_gider_adi_kategori ON finans_gider_adi (kategori_id)",
    """
    CREATE TABLE IF NOT EXISTS finans_ana_gider_kalem (
        id SERIAL PRIMARY KEY,
        ad VARCHAR(150) NOT NULL UNIQUE,
        kategori_id INTEGER REFERENCES finans_kategori(id),
        varsayilan_tutar NUMERIC(12,2) NOT NULL DEFAULT 0,
        varsayilan_hesap_kodu VARCHAR(20),
        baslangic_donem VARCHAR(7) NOT NULL,
        bitis_donem VARCHAR(7),
        aktif BOOLEAN NOT NULL DEFAULT TRUE,
        sira SMALLINT NOT NULL DEFAULT 0,
        notlar TEXT,
        olusturma_tarihi TIMESTAMP,
        olusturan_kullanici_id INTEGER REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS finans_islem (
        id SERIAL PRIMARY KEY,
        hesap_id INTEGER NOT NULL REFERENCES finans_hesap(id),
        tur VARCHAR(20) NOT NULL,
        yon SMALLINT NOT NULL CHECK (yon IN (1, -1)),
        tutar NUMERIC(12,2) NOT NULL CHECK (tutar > 0),
        onceki_bakiye NUMERIC(12,2) NOT NULL,
        yeni_bakiye NUMERIC(12,2) NOT NULL,
        tarih TIMESTAMP NOT NULL,
        aciklama VARCHAR(500),
        kategori_id INTEGER REFERENCES finans_kategori(id),
        gider_adi_id INTEGER REFERENCES finans_gider_adi(id),
        kalem_id INTEGER REFERENCES finans_ana_gider_kalem(id),
        donem VARCHAR(7),
        transfer_grup UUID,
        iptal BOOLEAN NOT NULL DEFAULT FALSE,
        iptal_tarihi TIMESTAMP,
        iptal_kullanici_id INTEGER REFERENCES users(id),
        iptal_neden VARCHAR(255),
        kullanici_id INTEGER NOT NULL REFERENCES users(id),
        olusturma_tarihi TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_finans_islem_hesap_tarih ON finans_islem (hesap_id, tarih)",
    "CREATE INDEX IF NOT EXISTS ix_finans_islem_tur_tarih ON finans_islem (tur, tarih)",
    "CREATE INDEX IF NOT EXISTS ix_finans_islem_transfer_grup ON finans_islem (transfer_grup)",
    "CREATE INDEX IF NOT EXISTS ix_finans_islem_kalem_donem ON finans_islem (kalem_id, donem)",
    # Aynı kalem aynı ay iki kez ödenemez; iptal edilince tekrar ödenebilir.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_finans_islem_kalem_donem
        ON finans_islem (kalem_id, donem)
        WHERE tur = 'ana_gider' AND iptal = FALSE
    """,
    """
    INSERT INTO finans_hesap (kod, ad, sira) VALUES
        ('beyazit', 'Ana Bakiye (Beyazıt)', 1),
        ('elde',    'Kullanılabilir Bakiye (Elde)', 2),
        ('banka',   'Banka Hesabı', 3)
    ON CONFLICT (kod) DO NOTHING
    """,
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
        for t in ("finans_hesap", "finans_kategori", "finans_gider_adi",
                  "finans_ana_gider_kalem", "finans_islem"):
            print(f"{'OK ' if insp.has_table(t) else 'YOK'}: {t}")
        n = db.session.execute(text("SELECT count(*) FROM finans_hesap")).scalar()
        print(f"finans_hesap satır: {n}")


if __name__ == "__main__":
    main()
