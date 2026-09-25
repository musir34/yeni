#!/usr/bin/env python3
"""Haftalık düzenli ödeme desteği; mevcut kayıtları korur, tekrar çalıştırılabilir.

Uygulamayı yeniden başlatmadan önce:
    DISABLE_JOBS=1 python scripts/update_finans_haftalik.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DISABLE_JOBS', '1')
os.environ.setdefault('WERKZEUG_RUN_MAIN', 'false')

DDL = [
    "ALTER TABLE finans_ana_gider_kalem ADD COLUMN IF NOT EXISTS siklik VARCHAR(10) NOT NULL DEFAULT 'aylik'",
    "ALTER TABLE finans_ana_gider_kalem ADD COLUMN IF NOT EXISTS ilk_odeme_tarihi DATE",
    "ALTER TABLE finans_ana_gider_kalem ADD COLUMN IF NOT EXISTS tutar_degisken BOOLEAN NOT NULL DEFAULT FALSE",
    # Aylık YYYY-MM kayıtları ve kalem/dönem mükerrer koruması aynen kalır.
    "ALTER TABLE finans_islem ALTER COLUMN donem TYPE VARCHAR(10)",
]


def main():
    # Önceki dağıtım komutunu kullananlar da güncel çalışan şemasını alsın.
    from scripts.update_finans_calisan import main as tum_finans_guncelle
    tum_finans_guncelle()


if __name__ == '__main__':
    main()
