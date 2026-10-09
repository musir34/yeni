"""Değişimden üretim — izole sqlite testleri (2026-10-09).

Senaryo: üretim modundaki modelin rafı boşken değişim oluşturulur →
"stok yetersiz" yerine kalem üretime yazılır (DG-<degisim_no> üretim kaydı),
abonelere mail + WhatsApp gider; rafta varsa eski akış (raftan tahsis, üretim yok);
üretim modunda olmayan barkodda eski sert hata aynen; etiket kilidi yalnız
üretim doğrulamasını ister; değişim silinince üretim kaydı düşer + iptal bildirimi.
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

_tmp_db = tempfile.NamedTemporaryFile(suffix="_uretim_degisim_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"
os.environ["WERKZEUG_RUN_MAIN"] = "false"

from flask import Flask  # noqa: E402

from models import (  # noqa: E402
    db, Raf, RafUrun, Product, BarcodeAlias, PlatformConfig, UretimSiparis,
    UretimDogrulama, Degisim, StockMovement, CentralStock,
    OrderCreated, OrderHazirlaniyor, OrderPicking, OrderShipped, OrderDelivered, OrderArchived,
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "test"
db.init_app(app)

from degisim import degisim_bp  # noqa: E402
app.register_blueprint(degisim_bp)

_NEEDED = (Raf, RafUrun, Product, BarcodeAlias, PlatformConfig, UretimSiparis,
           UretimDogrulama, Degisim, StockMovement, CentralStock,
           OrderCreated, OrderHazirlaniyor, OrderPicking, OrderShipped, OrderDelivered, OrderArchived)

with app.app_context():
    for _m in _NEEDED:
        _m.__table__.create(bind=db.engine, checkfirst=True)

MODEL = "0121"
BC_URETIM = "079950000037"   # üretim modunda, rafta yok
BC_RAFTA = "079950000036"    # üretim modunda, rafta 1 adet
BC_NORMAL = "079960000040"   # üretim modunda DEĞİL, rafta yok


@pytest.fixture(autouse=True)
def ctx(monkeypatch):
    with app.app_context():
        for m in (UretimDogrulama, UretimSiparis, Degisim, StockMovement, CentralStock,
                  RafUrun, Raf, Product, PlatformConfig):
            m.query.delete()
        db.session.commit()
        db.session.add(PlatformConfig(platform="uretim_ayar", is_active=True,
                                      extra_config={"models": [MODEL]}))
        db.session.add(Product(barcode=BC_URETIM, product_main_id=MODEL))
        db.session.add(Product(barcode=BC_RAFTA, product_main_id=MODEL))
        db.session.add(Product(barcode=BC_NORMAL, product_main_id="0999"))
        db.session.add(Raf(kod="A1", ana="A", ikincil="1", kat="1"))
        db.session.add(RafUrun(raf_kodu="A1", urun_barkodu=BC_RAFTA, adet=1))
        db.session.commit()
        import mail_service
        import whatsapp_service
        gonderilen = {"mail": [], "wa": []}
        monkeypatch.setattr(mail_service, "notify",
                            lambda ev, **kw: gonderilen["mail"].append((ev, kw.get("subject", ""))))
        monkeypatch.setattr(whatsapp_service, "notify_whatsapp",
                            lambda ev, baslik, *a, **kw: gonderilen["wa"].append((ev, baslik)))
        yield gonderilen
        db.session.rollback()


def _form(barkodlar, adetler=None):
    adetler = adetler or [1] * len(barkodlar)
    return {
        "kayit_tipi": "manuel",
        "ad": "Test", "soyad": "Müşteri", "adres": "Adres", "telefon_no": "05551112233",
        "degisim_nedeni": "Beden",
        "urun_barkod": barkodlar,
        "urun_model_kodu": [MODEL] * len(barkodlar),
        "urun_renk": ["Kırmızı"] * len(barkodlar),
        "urun_beden": ["37"] * len(barkodlar),
        "urun_adet": [str(a) for a in adetler],
    }


def _degisim_kaydet(data):
    with app.test_client() as c:
        return c.post("/degisim-kaydet", data=data)


def test_uretim_modunda_raf_bos_ise_uretime_yazilir_ve_bildirim_gider(ctx):
    r = _degisim_kaydet(_form([BC_URETIM]))
    assert r.status_code in (200, 302), r.get_data(as_text=True)

    rec = Degisim.query.one()
    urunler = json.loads(rec.urunler_json)
    assert urunler[0]["uretim"] is True and urunler[0]["tahsis_edilen"] == 0

    kayit = UretimSiparis.query.filter_by(order_number=f"DG-{rec.degisim_no}").one()
    assert {u["barcode"] for u in json.loads(kayit.details)} == {BC_URETIM}
    assert kayit.customer_name == "Test Müşteri"
    assert kayit.product_main_id == MODEL

    assert [ev for ev, _ in ctx["mail"]] == ["uretim_siparis"]
    assert "DEĞİŞİMİ" in ctx["mail"][0][1]
    assert [ev for ev, _ in ctx["wa"]] == ["uretim_siparis"]
    assert "DEĞİŞİMİ" in ctx["wa"][0][1]


def test_uretim_modunda_rafta_varsa_eski_akis_raftan_tahsis(ctx):
    r = _degisim_kaydet(_form([BC_RAFTA]))
    assert r.status_code in (200, 302)
    rec = Degisim.query.one()
    urunler = json.loads(rec.urunler_json)
    assert urunler[0].get("uretim") is None and urunler[0]["tahsis_edilen"] == 1
    assert RafUrun.query.filter_by(urun_barkodu=BC_RAFTA).one().adet == 0
    assert UretimSiparis.query.count() == 0
    assert ctx["mail"] == [] and ctx["wa"] == []


def test_karma_degisim_tek_kayit(ctx):
    r = _degisim_kaydet(_form([BC_RAFTA, BC_URETIM]))
    assert r.status_code in (200, 302)
    rec = Degisim.query.one()
    urunler = {u["barkod"]: u for u in json.loads(rec.urunler_json)}
    assert urunler[BC_RAFTA]["tahsis_edilen"] == 1 and urunler[BC_RAFTA].get("uretim") is None
    assert urunler[BC_URETIM]["uretim"] is True
    kayit = UretimSiparis.query.one()
    assert {u["barcode"] for u in json.loads(kayit.details)} == {BC_URETIM}

    # Üretim ekranı görünümü: tam içerik iki kalem, raftan kalem okutma istemez
    from uretim_modu import _siparis_tam_detay, raftan_kalemler, eksik_raf_okutmalar
    assert {d["barcode"] for d in _siparis_tam_detay(kayit.order_number)} == {BC_RAFTA, BC_URETIM}
    assert raftan_kalemler(kayit) == []
    assert eksik_raf_okutmalar(kayit.order_number) == [BC_URETIM]

    # Üretilen kalem doğrulanınca etiket açılır
    db.session.add(UretimDogrulama(order_number=kayit.order_number, barcode=BC_URETIM))
    db.session.commit()
    assert eksik_raf_okutmalar(kayit.order_number) == []


def test_rafta_adet_yetmiyorsa_kalemin_tamami_uretime(ctx):
    r = _degisim_kaydet(_form([BC_RAFTA], adetler=[2]))
    assert r.status_code in (200, 302)
    urunler = json.loads(Degisim.query.one().urunler_json)
    assert urunler[0]["uretim"] is True and urunler[0]["tahsis_edilen"] == 0
    # Raf dokunulmadı (kısmi tahsis yok — Trendyol raf önceliğiyle aynı kural)
    assert RafUrun.query.filter_by(urun_barkodu=BC_RAFTA).one().adet == 1
    assert json.loads(UretimSiparis.query.one().details)[0]["quantity"] == 2


def test_uretim_modunda_olmayan_barkodda_eski_sert_hata(ctx):
    r = _degisim_kaydet(_form([BC_NORMAL]))
    assert r.status_code == 400
    assert "Stok yetersiz" in r.get_data(as_text=True)
    assert Degisim.query.count() == 0 and UretimSiparis.query.count() == 0


def test_degisim_silinince_uretim_kaydi_duser_ve_iptal_bildirimi(ctx):
    _degisim_kaydet(_form([BC_URETIM]))
    rec = Degisim.query.one()
    with app.test_client() as c:
        r = c.post("/delete_exchange", data={"degisim_no": rec.degisim_no})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert Degisim.query.count() == 0
    assert UretimSiparis.query.count() == 0
    assert [ev for ev, _ in ctx["mail"]] == ["uretim_siparis", "uretim_iptal"]
    assert [ev for ev, _ in ctx["wa"]] == ["uretim_siparis", "uretim_iptal"]


def test_kargolanan_degisimde_etiket_kilidi_kalkar(ctx):
    _degisim_kaydet(_form([BC_URETIM]))
    rec = Degisim.query.one()
    from uretim_modu import eksik_raf_okutmalar
    assert eksik_raf_okutmalar(f"DG-{rec.degisim_no}") == [BC_URETIM]
    rec.degisim_durumu = "Kargoya Verildi"
    db.session.commit()
    assert eksik_raf_okutmalar(f"DG-{rec.degisim_no}") == []
