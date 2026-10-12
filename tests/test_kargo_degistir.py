"""Toplu kargo firması değiştirme (kargo_degistir.py) — izole sqlite testi, Trendyol sahte.

Çalıştırma (çıplak pytest YASAK — conftest canlı uygulamayı yükler):
  DISABLE_JOBS=1 .venv/bin/python -m pytest --noconftest tests/test_kargo_degistir.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_tmp_db = tempfile.NamedTemporaryFile(suffix="_kargo_degistir_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"
os.environ.setdefault("API_KEY", "k")
os.environ.setdefault("API_SECRET", "s")
os.environ.setdefault("SUPPLIER_ID", "123")

from flask import Flask  # noqa: E402
from flask_login import LoginManager, UserMixin  # noqa: E402

from models import (  # noqa: E402
    OrderCreated, OrderHazirlaniyor, OrderPicking, OrderShipped, UretimSiparis, db,
)
import kargo_degistir  # noqa: E402
from kargo_degistir import kargo_degistir_bp  # noqa: E402


class _Kullanici(UserMixin):
    id = 1
    username = "test"
    role = "admin"


app = Flask(__name__)
app.config.update(SECRET_KEY="t", SQLALCHEMY_DATABASE_URI=os.environ["DATABASE_URL"],
                  SQLALCHEMY_TRACK_MODIFICATIONS=False, TESTING=True)
db.init_app(app)
lm = LoginManager(app)
lm.user_loader(lambda uid: _Kullanici())
app.register_blueprint(kargo_degistir_bp)

with app.app_context():
    for _m in (OrderCreated, OrderHazirlaniyor, OrderPicking, OrderShipped, UretimSiparis):
        _m.__table__.create(bind=db.engine, checkfirst=True)

FETCH = {"X-Requested-With": "fetch"}


class _Yanit:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _SahteTrendyol:
    """requests.put / requests.get yerine geçer; çağrıları kaydeder."""

    def __init__(self, put_status=200, put_body=None, get_paket=None, get_paket_oncesi=None):
        self.put_status, self.put_body, self.get_paket = put_status, put_body, get_paket
        self.get_paket_oncesi = get_paket_oncesi  # PUT'tan ÖNCE dönen paket (canlı kontrol)
        self.put_calls, self.get_calls = [], []

    def put(self, url, headers=None, json=None, timeout=None):
        self.put_calls.append((url, json))
        return _Yanit(self.put_status, self.put_body, text=str(self.put_body or ""))

    def get(self, url, headers=None, params=None, timeout=None):
        self.get_calls.append((url, params))
        paket = self.get_paket_oncesi if (not self.put_calls and self.get_paket_oncesi) else self.get_paket
        return _Yanit(200, {"content": [paket] if paket else []})


def _sahte(monkeypatch, **kw):
    s = _SahteTrendyol(**kw)
    monkeypatch.setattr(kargo_degistir.requests, "put", s.put)
    monkeypatch.setattr(kargo_degistir.requests, "get", s.get)
    monkeypatch.setattr(kargo_degistir.time, "sleep", lambda _s: None)  # yeniden çekme beklemesi yok
    return s


def _client():
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = "1"
        s["totp_verified"] = True
    return c


def _temizle():
    with app.app_context():
        for M in (OrderCreated, OrderHazirlaniyor, OrderPicking, OrderShipped, UretimSiparis):
            db.session.query(M).delete()
        db.session.commit()


def _siparis(M, no, pkg="555", kargo="Aras Kargo Marketplace", takip="ARAS111"):
    with app.app_context():
        db.session.add(M(order_number=no, shipment_package_id=pkg, package_number=pkg,
                         cargo_provider_name=kargo, cargo_tracking_number=takip, status="Created"))
        db.session.commit()


def test_basarili_degisim_yerel_kaydi_gunceller(monkeypatch):
    _temizle()
    _siparis(OrderCreated, "100")
    # Aynı siparişin ikinci satırı (çok kalemli sipariş) — ikisi de güncellenmeli
    _siparis(OrderCreated, "100")
    s = _sahte(monkeypatch,
               get_paket_oncesi={"shipmentPackageId": 555, "cargoProviderName": "Aras Kargo Marketplace",
                                 "cargoTrackingNumber": "ARAS111"},
               get_paket={"shipmentPackageId": 555, "cargoProviderName": "Yurtiçi Kargo Marketplace",
                          "cargoTrackingNumber": "YK999", "cargoTrackingLink": "http://x"})
    with app.app_context():
        r = kargo_degistir.siparis_kargo_degistir("100", "YKMP")
        assert r["success"] and not r["skipped"], r
        assert r["cargo_tracking_number"] == "YK999"
        satirlar = OrderCreated.query.filter_by(order_number="100").all()
        assert len(satirlar) == 2
        assert all(x.cargo_provider_name == "Yurtiçi Kargo Marketplace" for x in satirlar)
        assert all(x.cargo_tracking_number == "YK999" for x in satirlar)
    assert s.put_calls[0][0].endswith("/shipment-packages/555/cargo-providers")
    assert s.put_calls[0][1] == {"cargoProvider": "YKMP"}
    assert s.get_calls[0][1] == {"orderNumber": "100"}
    assert len(s.get_calls) == 2  # canlı kontrol + değişiklik sonrası doğrulama
    assert r["firma"]["kod"] == "YKMP"


def test_yeniden_cekme_eski_adi_dondururse_yerel_ad_yazilir_eski_kod_silinir(monkeypatch):
    _temizle()
    _siparis(OrderPicking, "101", takip="733111")
    s = _sahte(monkeypatch, get_paket={"shipmentPackageId": 555, "cargoProviderName": "Trendyol Express Marketplace",
                                       "cargoTrackingNumber": "733111"})
    with app.app_context():
        r = kargo_degistir.siparis_kargo_degistir("101", "PTTMP")
        assert r["success"], r
        assert r["cargo_tracking_number"] is None  # yeni kod henüz yok → sonraki senkronda gelir
        o = OrderPicking.query.filter_by(order_number="101").first()
        assert o.cargo_provider_name == "PTT Kargo"
        assert o.cargo_tracking_number == ""  # eski (artık geçersiz) 733 kodu silindi → rozet TEX kalmaz
    assert r["firma"]["kod"] == "PTTMP"
    assert "eski kod silindi" in r["message"]
    assert len(s.get_calls) == 1 + kargo_degistir.YENIDEN_CEKME_DENEME  # canlı kontrol + denemeler


def test_yeni_ad_geldi_ama_kod_eskiyse_kod_temizlenir(monkeypatch):
    _temizle()
    _siparis(OrderCreated, "108", kargo="Trendyol Express Marketplace", takip="733555")
    _sahte(monkeypatch,
           get_paket_oncesi={"shipmentPackageId": 555, "cargoProviderName": "Trendyol Express Marketplace",
                             "cargoTrackingNumber": "733555"},
           get_paket={"shipmentPackageId": 555, "cargoProviderName": "DHL eCommerce Marketplace",
                      "cargoTrackingNumber": "733555"})  # ad değişti, kod henüz eski
    with app.app_context():
        r = kargo_degistir.siparis_kargo_degistir("108", "DHLECOMMP")
        o = OrderCreated.query.filter_by(order_number="108").first()
        assert o.cargo_provider_name == "DHL eCommerce Marketplace"
        assert o.cargo_tracking_number == ""
    assert r["success"] and r["firma"]["kisa"] == "DHL"


def test_ayni_firma_canli_pakete_gore_atlanir_ve_yerel_hizalanir(monkeypatch):
    _temizle()
    # Yerel kayıt bayat (Aras) ama Trendyol'da paket zaten Yurtiçi → PUT atılmaz, yerel hizalanır
    _siparis(OrderHazirlaniyor, "102", kargo="Aras Kargo Marketplace", takip="ARAS111")
    s = _sahte(monkeypatch, get_paket={"shipmentPackageId": 555, "cargoProviderName": "Yurtiçi Kargo Marketplace",
                                       "cargoTrackingNumber": "YK123"})
    with app.app_context():
        r = kargo_degistir.siparis_kargo_degistir("102", "YKMP")
        o = OrderHazirlaniyor.query.filter_by(order_number="102").first()
        assert o.cargo_provider_name == "Yurtiçi Kargo Marketplace" and o.cargo_tracking_number == "YK123"
    assert r["skipped"] and r["success"] and r["firma"]["kod"] == "YKMP"
    assert not s.put_calls


def test_yerel_ayni_gorunse_de_canli_farkliysa_degistirilir(monkeypatch):
    _temizle()
    _siparis(OrderCreated, "107", kargo="Yurtiçi Kargo Marketplace")
    s = _sahte(monkeypatch, get_paket={"shipmentPackageId": 555, "cargoProviderName": "Aras Kargo Marketplace",
                                       "cargoTrackingNumber": "ARAS9"})
    with app.app_context():
        r = kargo_degistir.siparis_kargo_degistir("107", "YKMP")
    assert not r["skipped"] and r["success"], r
    assert len(s.put_calls) == 1


def test_rozet_takip_onekine_gore_sonra_ada_gore():
    t = kargo_degistir.kargo_firma_tespit
    assert t("733123456789", "Yurtiçi Kargo Marketplace")["kod"] == "TEXMP"   # ön ek ad'ı ezer
    assert t("728000111", None)["kisa"] == "DHL"
    assert t("1234567890", "Aras Kargo Marketplace")["kod"] == "ARASMP"
    assert t("", "MNG Kargo Marketplace")["kisa"] == "MNG"
    assert t(None, None) is None
    with app.app_context():
        html = str(kargo_degistir.kargo_rozet_html("733999", "<x>"))
    assert 'data-kargo-kod="TEXMP"' in html and ">TEX<" in html and "<x>" not in html


def test_kargoya_verilmis_ve_site_siparisi_reddedilir(monkeypatch):
    _temizle()
    _siparis(OrderShipped, "103")
    s = _sahte(monkeypatch)
    with app.app_context():
        r1 = kargo_degistir.siparis_kargo_degistir("103", "YKMP")
        r2 = kargo_degistir.siparis_kargo_degistir("SH-9", "YKMP")
        r3 = kargo_degistir.siparis_kargo_degistir("yok", "YKMP")
    assert not r1["success"] and "kargoya verilmiş" in r1["message"].lower()
    assert r2["skipped"] and not r2["success"]
    assert not r3["success"] and "bulunamadı" in r3["message"]
    assert not s.put_calls


def test_trendyol_reddi_mesaji_yerel_kaydi_bozmaz(monkeypatch):
    _temizle()
    _siparis(OrderCreated, "104")
    _sahte(monkeypatch, put_status=400,
           put_body={"errors": [{"message": "Bu işlem bir paket için 5 dakika içerisinde yalnızca 1 kere yapılabilir."}]})
    with app.app_context():
        r = kargo_degistir.siparis_kargo_degistir("104", "YKMP")
        o = OrderCreated.query.filter_by(order_number="104").first()
        assert o.cargo_provider_name == "Aras Kargo Marketplace"
    assert not r["success"]
    assert "5 dakika" in r["message"]


def test_api_toplu_kayit_idleri_ve_siparis_nolari(monkeypatch):
    _temizle()
    _siparis(OrderCreated, "105")
    _siparis(OrderCreated, "106", pkg="777")
    with app.app_context():
        db.session.add(UretimSiparis(order_number="105", uretildi=True, paketlendi=True, details="[]"))
        db.session.add(UretimSiparis(order_number="SH-5", uretildi=True, paketlendi=True, details="[]"))
        db.session.commit()
        ids = [u.id for u in UretimSiparis.query.all()]
    s = _sahte(monkeypatch, get_paket=None)
    c = _client()
    j = c.post("/kargo-firmasi/api/degistir", json={"kargo_kodu": "ykmp", "kayit_ids": ids,
                                                     "order_numbers": ["106", "106"]}, headers=FETCH).get_json()
    assert j["basarili"] == 2 and j["atlanan"] == 1 and j["hatali"] == 0, j
    assert [x["order_number"] for x in j["sonuclar"]] == ["106", "105", "SH-5"]
    assert {u for u, _ in s.put_calls} == {
        s.put_calls[0][0].rsplit("/shipment-packages/", 1)[0] + "/shipment-packages/777/cargo-providers",
        s.put_calls[0][0].rsplit("/shipment-packages/", 1)[0] + "/shipment-packages/555/cargo-providers",
    }


def test_api_guvenlik_ve_dogrulama():
    _temizle()
    c = _client()
    assert c.post("/kargo-firmasi/api/degistir", json={"kargo_kodu": "YKMP", "order_numbers": ["1"]}).status_code == 403
    assert c.post("/kargo-firmasi/api/degistir", json={"kargo_kodu": "XXX", "order_numbers": ["1"]},
                  headers=FETCH).status_code == 400
    assert c.post("/kargo-firmasi/api/degistir", json={"kargo_kodu": "YKMP"}, headers=FETCH).status_code == 400
    liste = c.get("/kargo-firmasi/api/liste").get_json()
    assert {"kod": "YKMP", "ad": "Yurtiçi Kargo"} in liste["firmalar"]
    anonim = app.test_client()
    assert anonim.get("/kargo-firmasi/api/liste").status_code == 403
