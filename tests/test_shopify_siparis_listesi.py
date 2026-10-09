"""Sipariş listesi Shopify kartları — saf mantık testleri (DB/API yok).

Site siparişi kartta mağaza adıyla ('1428') görünür, panel eylemleri 'SH-<iç kimlik>' ile
çalışır; etiket → panel durumu eşlemesi templates/shopify/orders.html getOrderStatus ile aynı.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shopify_siparis_listesi import (  # noqa: E402
    aramaya_uyar,
    durum_kodu,
    goruntu_no,
    karta_cevir,
    kartlari_sirala,
)


def _siparis(**ek):
    temel = {
        "id": "gid://shopify/Order/6543210987654",
        "legacyResourceId": "6543210987654",
        "name": "#1428",
        "createdAt": "2026-10-08T21:15:00Z",
        "tags": [],
        "cancelledAt": None,
        "customer": {"firstName": "Ayşe", "lastName": "Yılmaz"},
        "shippingAddress": {"name": "Ayşe Yılmaz", "address1": "Gül Sk. 3", "city": "İstanbul", "province": "İstanbul", "country": "Türkiye"},
        "fulfillments": [],
        "line_items": [
            {"title": "Topuklu Sandalet", "sku": "0121-38 Kırmızı", "quantity": 2,
             "variant": {"barcode": "079950000001"}, "resolved_barcode": "079950000001"},
        ],
    }
    temel.update(ek)
    return temel


def test_etiket_panel_durumuna_cevrilir():
    assert durum_kodu(_siparis()) == "Created"                                   # etiketsiz = Beklemede = Yeni
    assert durum_kodu(_siparis(tags=["Hazirlaniyor"])) == "Hazirlaniyor"
    assert durum_kodu(_siparis(tags=["Kargoda"])) == "Shipped"
    assert durum_kodu(_siparis(tags=["Teslim Edildi"])) == "Delivered"
    assert durum_kodu(_siparis(tags=["Hazirlaniyor", "Kargoda"])) == "Shipped"   # artık etiket kalsa en ileri durum
    assert durum_kodu(_siparis(tags=["Kargoda"], cancelledAt="2026-10-09T01:00:00Z")) == "Cancelled"


def test_gosterilen_no_magaza_adi_eylem_anahtari_ic_kimlik():
    kart = karta_cevir(_siparis())
    assert kart.display_number == "1428"
    assert kart.order_number == "SH-6543210987654"
    assert goruntu_no({"legacyResourceId": "77"}) == "77"                        # adı olmayan sipariş iç kimliğe düşer


def test_kart_alanlari_listenin_bekledigi_bicimde():
    kart = karta_cevir(_siparis(fulfillments=[{"trackingInfo": [{"company": "DHL", "number": "123456789"}]}]))
    assert kart.order_date == datetime(2026, 10, 8, 21, 15)                      # naive UTC (DB konvansiyonu)
    assert kart.order_date.tzinfo is None
    assert (kart.customer_name, kart.customer_surname) == ("Ayşe", "Yılmaz")
    assert kart.customer_address.startswith("Gül Sk. 3 İstanbul")
    assert (kart.cargo_provider_name, kart.cargo_tracking_number) == ("DHL", "123456789")
    assert kart.agreed_delivery_date is None and kart.estimated_delivery_end is None
    detay = json.loads(kart.details)
    assert detay == [{"barcode": "079950000001", "sku": "0121-38 Kırmızı", "product_name": "Topuklu Sandalet", "quantity": 2}]


def test_musterisiz_siparis_kargo_adindan_misafir():
    kart = karta_cevir(_siparis(customer=None, shippingAddress={"name": "Mehmet Can Demir"}))
    assert (kart.customer_name, kart.customer_surname) == ("Mehmet", "Can Demir")
    kart = karta_cevir(_siparis(customer=None, shippingAddress=None))
    assert kart.customer_name == "Misafir"


def test_arama_numara_bicimlerini_ve_musteriyi_bulur():
    kart = karta_cevir(_siparis())
    for aranan in ("1428", "#1428", "SH-6543210987654", "6543210987654", "ayşe", "Ayşe Yılmaz", "yıl"):
        assert aramaya_uyar(kart, aranan), aranan
    assert not aramaya_uyar(kart, "1429")
    assert aramaya_uyar(kart, None) and aramaya_uyar(kart, "   ")


def test_siralama_trendyol_kurallariyla_ayni():
    t = datetime(2026, 10, 8, 10, 0)
    ty_erken = SimpleNamespace(order_number="T1", order_date=t.replace(hour=8), agreed_delivery_date=t.replace(day=10), estimated_delivery_end=None)
    ty_gec = SimpleNamespace(order_number="T2", order_date=t.replace(hour=12), agreed_delivery_date=t.replace(day=9), estimated_delivery_end=None)
    sh = SimpleNamespace(order_number="SH-1", order_date=t, agreed_delivery_date=None, estimated_delivery_end=None)

    # Tarih: yeni → eski; Shopify kartı tarihine göre araya girer
    assert [k.order_number for k in kartlari_sirala([ty_erken, sh, ty_gec], "date_desc")] == ["T2", "SH-1", "T1"]
    # Teslim süresi: en yakın önce, tarihi olmayan (Shopify) en sona
    assert [k.order_number for k in kartlari_sirala([sh, ty_erken, ty_gec], "deadline_asc")] == ["T2", "T1", "SH-1"]
    assert [k.order_number for k in kartlari_sirala([sh, ty_erken, ty_gec], "deadline_desc")] == ["T1", "T2", "SH-1"]
    # Tarihi olmayan kart sıralamayı çökertmez
    tarihsiz = SimpleNamespace(order_number="T3", order_date=None, agreed_delivery_date=None, estimated_delivery_end=None)
    assert [k.order_number for k in kartlari_sirala([tarihsiz, sh], None)] == ["SH-1", "T3"]
