"""Soru-Cevap kartında soranın siparişleri — izole sqlite testi (gerçek uygulama/Trendyol yok).

Çalıştırma (çıplak pytest YASAK — conftest canlı uygulamayı yükler):
  DISABLE_JOBS=1 .venv/bin/python -m pytest --noconftest tests/test_qna_siparis_musteri.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_tmp_db = tempfile.NamedTemporaryFile(suffix="_qna_siparis_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"

from flask import Flask  # noqa: E402

from models import (db, Archive, OrderShipped, OrderDelivered, Product, TrendyolQuestion,  # noqa: E402
                    TrendyolSiparisMusteri)
from trendyol_qna import siparis_musteri as sm  # noqa: E402

TABLOLAR = [m for m, _ in sm.SIPARIS_TABLOLARI] + [Product, TrendyolQuestion, TrendyolSiparisMusteri]

app = Flask(__name__, root_path=str(PROJECT_ROOT))
app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI=os.environ["DATABASE_URL"],
                  SQLALCHEMY_TRACK_MODIFICATIONS=False)
db.init_app(app)

with app.app_context():
    for _m in TABLOLAR:
        _m.__table__.create(bind=db.engine, checkfirst=True)


@pytest.fixture(autouse=True)
def _temiz():
    with app.app_context():
        for m in TABLOLAR:
            db.session.query(m).delete()
        db.session.commit()
        yield


def _paket(no, musteri, ms=1_700_000_000_000):
    return {"orderNumber": no, "customerId": musteri, "orderDate": ms}


def test_esleme_yazilir_tekrar_ve_eksik_kimlik_atlanir():
    n = sm.musteri_siparislerini_kaydet([_paket("111", 7), _paket("111", 7), _paket("222", None),
                                         {"orderNumber": "", "customerId": 7}, "bozuk"])
    assert n == 1
    # ikinci senkron aynı siparişi tekrar yazmaya çalışır → çakışma yok, satır sayısı değişmez
    sm.musteri_siparislerini_kaydet([_paket("111", 7), _paket("333", 7, 1_800_000_000_000)])
    assert db.session.query(TrendyolSiparisMusteri).count() == 2
    assert sm.musteri_siparis_nolari([7, None]) == {7: ["333", "111"]}   # yeniden eskiye


def _siparis(model, no, paket, barkod, renk, beden, **ek):
    detay = json.dumps([{"barcode": barkod, "color": renk, "size": beden, "quantity": 1,
                         "productName": "Sandalet", "product_main_id": "999999"}])
    db.session.add(model(order_number=no, package_number=paket, customer_name="Ayşe", customer_surname="Yılmaz",
                         customer_address="Bağcılar / İstanbul", product_barcode=barkod, details=detay,
                         order_date=datetime(2026, 10, 1, 9, 0), **ek))


def test_ozet_model_kodu_urunden_gorsel_alici_adres_ve_bolunmus_paket():
    db.session.add_all([
        Product(barcode="079950000001", product_main_id="0121", images="https://cdn.x/a.jpg,https://cdn.x/b.jpg"),
        Product(barcode="079950000002", product_main_id="0130", images=""),
    ])
    _siparis(OrderShipped, "555", "P1", "079950000001", "Kırmızı", "38")
    _siparis(OrderDelivered, "555", "P2", "079950000002", "Siyah", "39", status="Delivered")
    _siparis(OrderDelivered, "555", "P2", "079950000002", "Siyah", "39")   # aynı paketin kopyası sayılmaz
    db.session.add(Archive(order_number="666", customer_name="Can", customer_surname="Ak",
                           customer_address="Kadıköy", product_barcode="079950000001",
                           product_color="Kırmızı", product_size="40"))
    db.session.commit()

    oz = sm.siparis_ozetleri(["555", "666", "777"], lambda d: d and d.strftime("%d.%m.%Y"))
    assert set(oz) == {"555", "666"}   # panele düşmeyen sipariş yok
    o = oz["555"]
    assert o["alici"] == "Ayşe Yılmaz" and o["adres"] == "Bağcılar / İstanbul"
    assert o["durum"] == "Kargoda, Teslim Edildi" and o["tarih"] == "01.10.2026"
    assert [(k["barkod"], k["model"], k["renk"], k["beden"]) for k in o["kalemler"]] == [
        ("079950000001", "0121", "Kırmızı", "38"), ("079950000002", "0130", "Siyah", "39")]
    assert o["kalemler"][0]["gorsel"] == "https://cdn.x/a.jpg"
    # details'siz arşiv satırı virgüllü kolonlardan okunur; model yine üründen (contentId değil)
    assert oz["666"]["kalemler"][0]["model"] == "0121" and oz["666"]["kalemler"][0]["beden"] == "40"


def test_kartta_sorulan_model_iceren_siparis_basta():
    from trendyol_qna.qna_routes import _soru_siparisleri
    soru = TrendyolQuestion(id=1, text="?", product_main_id="0130")
    ozet = {"1": {"no": "1", "kalemler": [{"model": "0121"}]},
            "2": {"no": "2", "kalemler": [{"model": "0130"}]}}
    sonuc = _soru_siparisleri(soru, ["1", "2", "3"], ozet)
    assert [(s["no"], s["bu_model"]) for s in sonuc] == [("2", True), ("1", False), ("3", False)]
    assert sonuc[2]["durum"] == "Panelde yok"
