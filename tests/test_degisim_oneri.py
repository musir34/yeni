"""Değişim formundaki hızlı öneriler (bir küçük / bir büyük / diğer renkler) — izole sqlite testi.

Çalıştırma (çıplak pytest YASAK — conftest canlı uygulamayı yükler):
  DISABLE_JOBS=1 .venv/bin/python -m pytest --noconftest tests/test_degisim_oneri.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_tmp_db = tempfile.NamedTemporaryFile(suffix="_degisim_oneri_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"

from flask import Flask  # noqa: E402

from models import db, CentralStock, Product  # noqa: E402
import degisim  # noqa: E402

app = Flask(__name__)
app.config.update(SQLALCHEMY_DATABASE_URI=os.environ["DATABASE_URL"], SQLALCHEMY_TRACK_MODIFICATIONS=False)
db.init_app(app)

with app.app_context():
    for _m in (Product, CentralStock):
        _m.__table__.create(bind=db.engine, checkfirst=True)


@pytest.fixture(autouse=True)
def _urunler():
    with app.app_context():
        for m in (CentralStock, Product):
            db.session.query(m).delete()

        def urun(barkod, model, renk, beden, stok=None, arsiv=False):
            db.session.add(Product(barcode=barkod, product_main_id=model, color=renk, size=beden, archived=arsiv))
            if stok is not None:
                db.session.add(CentralStock(barcode=barkod, qty=stok))

        urun("S36", "0121", "Siyah", "36", 2)
        urun("S37", "0121", "Siyah", "37", 0)
        urun("S38", "0121", "Siyah", "38", 5)
        urun("S385", "0121", "Siyah", "38,5", 1)
        urun("S39", "0121", "Siyah", "39", 4)
        urun("S40", "0121", "Siyah", "40")                 # stok kaydı yok → 0
        urun("K38", "0121", "Kırmızı", "38", 3)
        urun("B38", "0121", "Bej", "38", 0)
        urun("B38x", "0121", "bej", "38", 7)               # aynı renk+numara, ikinci barkod (stoğu çok)
        urun("K39", "0121", "Kırmızı", "39", 9)            # başka numara → renk önerisine girmez
        urun("A38", "0121", "Mavi", "38", 6, arsiv=True)   # arşivli → hiç önerilmez
        urun("X38", "0155", "Siyah", "38", 8)              # başka model
        urun("STD", "0200", "Siyah", "STD", 1)             # numarası sayı olmayan ürün
        db.session.commit()
        yield
        db.session.rollback()


def test_bir_kucuk_bir_buyuk_ve_diger_renkler():
    o = degisim.degisim_onerileri("S38")
    assert (o["model"], o["renk"], o["beden"]) == ("0121", "Siyah", "38")
    assert o["kucuk"] == {"barcode": "S37", "size": "37", "color": "Siyah", "stok": 0}
    assert o["buyuk"] == {"barcode": "S385", "size": "38,5", "color": "Siyah", "stok": 1}   # buçuklu numara sıralanır
    # Aynı numaranın diğer renkleri, ada göre; aynı renkte stoğu çok olan barkod; arşivli ve başka model yok
    assert [(r["color"], r["barcode"], r["stok"]) for r in o["renkler"]] == [("bej", "B38x", 7), ("Kırmızı", "K38", 3)]


def test_uc_numaralarda_tek_yon_onerilir():
    assert degisim.degisim_onerileri("S36")["kucuk"] is None
    assert degisim.degisim_onerileri("S36")["buyuk"]["barcode"] == "S37"
    en_buyuk = degisim.degisim_onerileri("S40")
    assert en_buyuk["buyuk"] is None and en_buyuk["kucuk"]["barcode"] == "S39"
    assert en_buyuk["renkler"] == []                       # 40 numaranın başka rengi yok


def test_bilinmeyen_ve_numarasiz_urunler():
    assert degisim.degisim_onerileri("YOK-BOYLE") is None
    assert degisim.degisim_onerileri("") is None
    assert degisim.degisim_onerileri("../etc/passwd") is None
    std = degisim.degisim_onerileri("STD")
    assert std["kucuk"] is None and std["buyuk"] is None and std["renkler"] == []


def test_siparis_kalemlerine_oneriler_eklenir():
    kalemler = degisim._onerileri_ekle([{"sku": "0121-38 Siyah", "barcode": "S38"}, {"sku": "?", "barcode": "YOK"}])
    assert kalemler[0]["oneriler"]["kucuk"]["barcode"] == "S37"
    assert kalemler[1]["oneriler"] is None


def test_gercek_uygulama_yuklenmedi():
    assert "app" not in sys.modules


# ── Site siparişi adıyla (1423) bulunabilsin ─────────────────────────────────

def test_site_siparisi_adiyla_veya_kimligiyle_cozulur(monkeypatch):
    cagrilar = []

    def sahte_bilgi(order_number):
        cagrilar.append(order_number)
        return {"ad": "Hale", "details": []} if order_number == "SH-5800000000001" else None

    monkeypatch.setattr(degisim, "_fetch_shopify_order_info", sahte_bilgi)
    monkeypatch.setattr(degisim, "_shopify_id_adla_bul", lambda ad: "5800000000001" if ad == "1423" else None)

    for girdi in ("1423", "#1423", "SH-1423", "sh 1423", " SH-#1423 "):
        cagrilar.clear()
        info, kanonik = degisim.shopify_siparis_bilgisi(girdi)
        assert info and kanonik == "SH-5800000000001", girdi
        assert cagrilar == ["SH-5800000000001"]            # kısa numara adla çözülür, kimlik olarak denenmez
    # Uzun sayı doğrudan iç kimliktir
    cagrilar.clear()
    assert degisim.shopify_siparis_bilgisi("SH-5800000000001")[1] == "SH-5800000000001"
    assert cagrilar == ["SH-5800000000001"]
    # Bulunamayan ad ve sayı olmayan girdi
    assert degisim.shopify_siparis_bilgisi("9999") == (None, None)
    assert degisim.shopify_siparis_bilgisi("abc") == (None, None)


def test_site_siparisinin_urunleri_line_items_alanindan_okunur(monkeypatch):
    """get_order kalemleri 'line_items' + 'resolved_barcode' ile verir; form bunu okumalı."""
    import types
    siparis = {"customer": {"firstName": "Hale", "lastName": "Şahin"}, "shippingAddress": {"address1": "Örnek Mah.", "city": "İstanbul"},
               "line_items": [
                   {"sku": "0121-38 Siyah", "resolved_barcode": "S38", "variant": {"barcode": "8690000000001", "image": {"url": "https://cdn.shopify.com/x.jpg"}}},
                   {"sku": "0155-37 Bej", "variant": {"barcode": "8690000000002"}},
               ]}
    sahte = types.SimpleNamespace(get_order=lambda oid: {"success": True, "order": siparis})
    monkeypatch.setitem(sys.modules, "shopify_site.shopify_service", types.SimpleNamespace(shopify_service=sahte))
    info = degisim._fetch_shopify_order_info("SH-5800000000001")
    assert info["ad"] == "Hale" and info["adres"].startswith("Örnek Mah.")
    assert [(d["sku"], d["barcode"]) for d in info["details"]] == [("0121-38 Siyah", "S38"), ("0155-37 Bej", "8690000000002")]
    assert info["details"][0]["image_url"] == "https://cdn.shopify.com/x.jpg"
    # Panel barkodu çözüldüğü için hızlı öneriler site siparişinde de çıkar
    kalemler = degisim._onerileri_ekle(info["details"])
    assert kalemler[0]["oneriler"]["kucuk"]["barcode"] == "S37"
