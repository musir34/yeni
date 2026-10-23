"""Üretim modu renk kapsamı — izole sqlite testi.

Komutan emri (2026-10-23): model üretim moduna alınırken ya tüm renkler ya da
seçilen birkaç renk üretimde olur. Seçilmeyen rengin barkodu sabit adet almaz,
o renge gelen sipariş üretim kaydına düşmez.

Çalıştırma (canlıya dokunmaz):
    DISABLE_JOBS=1 python -m pytest tests/test_uretim_renk_kapsami.py --noconftest -q
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_tmp_db = tempfile.NamedTemporaryFile(suffix="_uretim_renk_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"
os.environ["WERKZEUG_RUN_MAIN"] = "false"

from flask import Flask  # noqa: E402

from models import (  # noqa: E402
    db, Raf, RafUrun, Product, BarcodeAlias, PlatformConfig, UretimSiparis,
    OrderCreated, OrderHazirlaniyor, StockMovement,
    OrderPicking, OrderShipped, OrderDelivered, OrderArchived, OrderCancelled,
    UretimDogrulama, CentralStock,
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

_NEEDED = (Raf, RafUrun, Product, BarcodeAlias, PlatformConfig, UretimSiparis,
           OrderCreated, OrderHazirlaniyor, StockMovement,
           OrderPicking, OrderShipped, OrderDelivered, OrderArchived,
           OrderCancelled, UretimDogrulama, CentralStock)

with app.app_context():
    for _m in _NEEDED:
        _m.__table__.create(bind=db.engine, checkfirst=True)

MODEL = "0121"
BC_SIYAH = "079950000036"
BC_BEJ = "079950000037"
BC_KIRMIZI = "079950000038"


@pytest.fixture(autouse=True)
def _ctx_clean(monkeypatch):
    with app.app_context():
        for m in (UretimSiparis, RafUrun, Raf, Product, PlatformConfig,
                  OrderCreated, OrderHazirlaniyor, StockMovement, OrderShipped,
                  UretimDogrulama, CentralStock):
            m.query.delete()
        db.session.commit()
        db.session.add(Product(barcode=BC_SIYAH, product_main_id=MODEL, color="Siyah"))
        db.session.add(Product(barcode=BC_BEJ, product_main_id=MODEL, color="Bej"))
        db.session.add(Product(barcode=BC_KIRMIZI, product_main_id=MODEL, color="Kırmızı"))
        db.session.commit()
        import mail_service
        import whatsapp_service
        gonderilen = []
        monkeypatch.setattr(mail_service, "notify",
                            lambda ev, **kw: gonderilen.append(ev))
        monkeypatch.setattr(whatsapp_service, "notify_whatsapp",
                            lambda *a, **kw: None)
        import uretim_modu
        monkeypatch.setattr(uretim_modu, "_wa_personel_bildirimi",
                            lambda *a, **kw: None)
        yield gonderilen
        db.session.rollback()


def _siparis(no, kalemler):
    return {
        "order_number": no,
        "package_number": None,
        "customer_name": "Test",
        "customer_surname": "Müşteri",
        "order_date": None,
        "details": json.dumps([
            {"barcode": bc, "quantity": q, "sku": "", "color": "", "size": ""}
            for bc, q in kalemler
        ]),
    }


def test_tum_renkler_eski_davranis():
    from uretim_modu import set_model_renkler, get_uretim_barcodes, get_uretim_ayar

    set_model_renkler(MODEL, [])

    assert get_uretim_barcodes() == {BC_SIYAH, BC_BEJ, BC_KIRMIZI}
    assert get_uretim_ayar()["renkler"] == {}


def test_eski_kayit_renk_alani_olmadan_tum_renkler():
    """Renk alanı hiç olmayan (bugünkü canlı) kayıt aynen çalışmalı."""
    from uretim_modu import get_uretim_barcodes

    db.session.add(PlatformConfig(platform="uretim_ayar", is_active=True,
                                  extra_config={"models": [MODEL]}))
    db.session.commit()

    assert get_uretim_barcodes() == {BC_SIYAH, BC_BEJ, BC_KIRMIZI}


def test_secili_renkler_yalniz_onlarin_barkodlari():
    from uretim_modu import set_model_renkler, get_uretim_barcodes, get_uretim_models

    set_model_renkler(MODEL, ["Siyah", "Bej"])

    assert get_uretim_models() == {MODEL}
    assert get_uretim_barcodes() == {BC_SIYAH, BC_BEJ}


def test_secilmeyen_renge_gelen_siparis_uretime_dusmez(_ctx_clean):
    from uretim_modu import set_model_renkler, isle_yeni_siparisler

    set_model_renkler(MODEL, ["Siyah"])

    assert isle_yeni_siparisler([_siparis("TY-K", [(BC_KIRMIZI, 1)])]) == 0
    assert isle_yeni_siparisler([_siparis("TY-S", [(BC_SIYAH, 1)])]) == 1
    kayit = UretimSiparis.query.filter_by(order_number="TY-S").one()
    assert {u["barcode"] for u in json.loads(kayit.details)} == {BC_SIYAH}
    assert UretimSiparis.query.filter_by(order_number="TY-K").first() is None
    assert _ctx_clean == ["uretim_siparis"]


def test_modelden_cikarinca_renk_kaydi_da_silinir():
    from uretim_modu import set_model_renkler, toggle_model, get_uretim_ayar, get_uretim_barcodes

    set_model_renkler(MODEL, ["Bej"])
    assert toggle_model(MODEL) is False

    ayar = get_uretim_ayar()
    assert ayar == {"models": [], "renkler": {}}
    assert get_uretim_barcodes() == set()

    # Yeniden toggle ile eklenince eski kısıt geri gelmez → tüm renkler
    assert toggle_model(MODEL) is True
    assert get_uretim_barcodes() == {BC_SIYAH, BC_BEJ, BC_KIRMIZI}


def test_renk_guncelleme_listeyi_cogaltmaz():
    from uretim_modu import set_model_renkler, get_uretim_ayar

    set_model_renkler(MODEL, ["Bej"])
    set_model_renkler(MODEL, ["Siyah", "Siyah", " Bej "])

    ayar = get_uretim_ayar()
    assert ayar["models"] == [MODEL]
    assert ayar["renkler"] == {MODEL: ["Bej", "Siyah"]}


def test_model_renkleri_mevcut_renkleri_doner():
    from uretim_modu import model_renkleri

    assert model_renkleri(MODEL) == ["Bej", "Kırmızı", "Siyah"]
    assert model_renkleri("YOK") == []


def test_kart_uretime_dahil_renkleri_gosterir():
    from uretim_gorevi import _urun_haritasi

    _, bilgi = _urun_haritasi({MODEL}, {MODEL: ["Siyah"]})
    assert bilgi[MODEL]["renkler"] == ["Siyah"]

    _, bilgi = _urun_haritasi({MODEL}, {})
    assert bilgi[MODEL]["renkler"] == ["Bej", "Kırmızı", "Siyah"]
