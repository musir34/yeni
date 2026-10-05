"""Sipariş listesindeki 'Üretim' rozeti — izole sqlite testi.

Çalıştırma (çıplak pytest YASAK — conftest canlı uygulamayı yükler):
  DISABLE_JOBS=1 .venv/bin/python -m pytest --noconftest tests/test_uretim_rozeti.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_tmp_db = tempfile.NamedTemporaryFile(suffix="_uretim_rozeti_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"

from flask import Flask  # noqa: E402

from models import db, UretimSiparis  # noqa: E402
import uretim_modu  # noqa: E402

app = Flask(__name__)
app.config.update(SQLALCHEMY_DATABASE_URI=os.environ["DATABASE_URL"], SQLALCHEMY_TRACK_MODIFICATIONS=False)
db.init_app(app)

with app.app_context():
    UretimSiparis.__table__.create(bind=db.engine, checkfirst=True)


def test_uretim_durum_haritasi_yalniz_uretim_siparislerini_ve_dogru_durumu_verir():
    with app.app_context():
        db.session.query(UretimSiparis).delete()
        db.session.add_all([
            UretimSiparis(order_number="100"),
            UretimSiparis(order_number="200", isleme_alindi=True),
            UretimSiparis(order_number="300", isleme_alindi=True, uretildi=True),
            UretimSiparis(order_number="400", isleme_alindi=True, uretildi=True, paketlendi=True),
        ])
        db.session.commit()
        harita = uretim_modu.uretim_durum_haritasi(["100", "200", "300", "400", "999", None])
        assert harita == {"100": "bekliyor", "200": "uretimde", "300": "uretildi", "400": "paketlendi"}
        assert "999" not in harita                       # üretim kaydı olmayan normal sipariş
        assert uretim_modu.uretim_durum_haritasi([]) == {}
        assert set(harita.values()) <= set(uretim_modu.URETIM_DURUM_ETIKETI)


def test_gercek_uygulama_yuklenmedi():
    assert "app" not in sys.modules
