"""sync_details gece temizliği — izole sqlite.
  DISABLE_JOBS=1 python -m pytest --noconftest tests/test_sync_detay_temizlik.py -q
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_tmp = tempfile.NamedTemporaryFile(suffix="_sync_temizlik.db", delete=False); _tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["DISABLE_JOBS"] = "1"

from flask import Flask  # noqa: E402

from models import SyncDetail, SyncSession, db  # noqa: E402
from stock_sync.temizlik import sync_detay_temizle  # noqa: E402

app = Flask(__name__)
app.config.update(SQLALCHEMY_DATABASE_URI=os.environ["DATABASE_URL"], SQLALCHEMY_TRACK_MODIFICATIONS=False, TESTING=True)
db.init_app(app)


@pytest.fixture()
def ctx():
    # Yalnız gerekli tablolar: tüm metadata'da (tasks.commit_due) çift indeks sqlite'ı kırıyor
    tablolar = [SyncSession.__table__, SyncDetail.__table__]
    with app.app_context():
        db.metadata.drop_all(bind=db.engine, tables=tablolar)
        db.metadata.create_all(bind=db.engine, tables=tablolar)
        yield
        db.session.remove()


def _satir(oturum, gun_once, simdi):
    return SyncDetail(session_id=oturum.id, barcode="B1", platform="trendyol", stock_sent=1, status="success",
                      created_at=simdi - timedelta(days=gun_once))


def test_eski_satirlar_partilerle_silinir_yeniler_kalir(ctx):
    simdi = datetime(2026, 10, 19, 3, 30)
    oturum = SyncSession(session_id="s1", platform="trendyol", status="completed")
    db.session.add(oturum); db.session.flush()
    db.session.add_all([_satir(oturum, g, simdi) for g in (30, 20, 8, 7.5, 6, 1, 0)])
    db.session.commit()
    assert sync_detay_temizle(gun=7, parti=2, azami_parti=10, simdi=simdi) == 4      # 30, 20, 8, 7.5 gün
    kalan = sorted((simdi - d.created_at).days for d in SyncDetail.query.all())
    assert kalan == [0, 1, 6]
    assert sync_detay_temizle(gun=7, simdi=simdi) == 0                                # ikinci koşu boş


def test_azami_parti_siniri_kalanı_ertesi_geceye_birakir(ctx):
    simdi = datetime(2026, 10, 19, 3, 30)
    oturum = SyncSession(session_id="s2", platform="trendyol", status="completed")
    db.session.add(oturum); db.session.flush()
    db.session.add_all([_satir(oturum, 10, simdi) for _ in range(5)])
    db.session.commit()
    assert sync_detay_temizle(gun=7, parti=2, azami_parti=1, simdi=simdi) == 2
    assert SyncDetail.query.count() == 3
