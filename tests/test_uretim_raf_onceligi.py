"""Üretim modu raf önceliği — izole sqlite kanıt testi.

Senaryo (Komutan tarifi, 2026-09-24):
  * Model üretim modunda; bir bedeni rafta var, diğeri yok.
  * Sipariş gelince rafta olan beden ÜRETİME YAZILMAZ (normal yol),
    rafta olmayan beden üretime yazılır (kayıt + mail).
  * Üretilip gönderilen ürün iade gelip rafa okutulunca, aynı barkoda
    yeni sipariş artık üretime düşmez.
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

_tmp_db = tempfile.NamedTemporaryFile(suffix="_uretim_raf_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"
os.environ["WERKZEUG_RUN_MAIN"] = "false"

from flask import Flask  # noqa: E402

from models import (  # noqa: E402
    db, Raf, RafUrun, Product, BarcodeAlias, PlatformConfig, UretimSiparis,
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

_NEEDED = (Raf, RafUrun, Product, BarcodeAlias, PlatformConfig, UretimSiparis)

with app.app_context():
    for _m in _NEEDED:
        _m.__table__.create(bind=db.engine, checkfirst=True)

MODEL = "0121"
BC_RAFTA = "079950000036"   # 36 numara — rafta var
BC_YOK = "079950000037"     # 37 numara — rafta yok


@pytest.fixture(autouse=True)
def _ctx_clean(monkeypatch):
    with app.app_context():
        for m in (UretimSiparis, RafUrun, Raf, Product, PlatformConfig):
            m.query.delete()
        db.session.commit()
        # Model üretim modunda
        db.session.add(PlatformConfig(platform="uretim_ayar", is_active=True,
                                      extra_config={"models": [MODEL]}))
        db.session.add(Product(barcode=BC_RAFTA, product_main_id=MODEL))
        db.session.add(Product(barcode=BC_YOK, product_main_id=MODEL))
        db.session.add(Raf(kod="A1", ana="A", ikincil="1", kat="1"))
        db.session.add(RafUrun(raf_kodu="A1", urun_barkodu=BC_RAFTA, adet=1))
        db.session.commit()
        # Mail/WhatsApp dışarı çıkmasın — sadece çağrı sayılsın
        import mail_service
        import whatsapp_service
        gonderilen = []
        monkeypatch.setattr(mail_service, "notify",
                            lambda ev, **kw: gonderilen.append(ev))
        monkeypatch.setattr(whatsapp_service, "notify_whatsapp",
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


def test_rafta_olan_beden_uretime_yazilmaz_olmayan_yazilir(_ctx_clean):
    from uretim_modu import isle_yeni_siparisler

    eklenen = isle_yeni_siparisler([_siparis("TY-1", [(BC_RAFTA, 1), (BC_YOK, 1)])])

    assert eklenen == 1
    kayit = UretimSiparis.query.filter_by(order_number="TY-1").one()
    uretilecek = {u["barcode"] for u in json.loads(kayit.details)}
    assert uretilecek == {BC_YOK}, "yalnız rafta olmayan beden üretime girmeli"
    assert _ctx_clean == ["uretim_siparis"], "tek mail gitmeli"


def test_tum_kalemler_raftaysa_kayit_ve_mail_yok(_ctx_clean):
    from uretim_modu import isle_yeni_siparisler

    eklenen = isle_yeni_siparisler([_siparis("TY-2", [(BC_RAFTA, 1)])])

    assert eklenen == 0
    assert UretimSiparis.query.count() == 0
    assert _ctx_clean == []


def test_iade_rafa_girince_yeni_siparis_uretime_dusmez(_ctx_clean):
    from uretim_modu import isle_yeni_siparisler

    # 1) Rafta yok → üretime düşer
    assert isle_yeni_siparisler([_siparis("TY-3", [(BC_YOK, 1)])]) == 1

    # 2) Üretildi, gönderildi, iade geldi, rafa okutuldu (raf_sistemi ile aynı yazım)
    db.session.add(RafUrun(raf_kodu="A1", urun_barkodu=BC_YOK, adet=1))
    db.session.commit()

    # 3) Aynı barkoda yeni sipariş → artık normal yol
    assert isle_yeni_siparisler([_siparis("TY-4", [(BC_YOK, 1)])]) == 0
    assert UretimSiparis.query.filter_by(order_number="TY-4").first() is None
    assert _ctx_clean == ["uretim_siparis"], "ikinci siparişe mail gitmemeli"


def test_rafta_adet_yetmiyorsa_kalem_uretime_girer(_ctx_clean):
    from uretim_modu import isle_yeni_siparisler

    # Rafta 1 var, sipariş 2 istiyor → kalem üretime yazılır
    assert isle_yeni_siparisler([_siparis("TY-5", [(BC_RAFTA, 2)])]) == 1
