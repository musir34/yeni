"""Üretim siparişi/iptal WhatsApp personel bildirimi — DB'ye ve ağa dokunmaz."""
import pytest

import uretim_modu
import whatsapp_alici
import whatsapp_notify

KALEM = {"barcode": "111", "sku": "0121-38 Kırmızı", "color": "Kırmızı", "size": "38", "quantity": 2}


@pytest.fixture
def cagrilar(monkeypatch):
    kayit = {"sablon": [], "genel": [], "alicilar": ["0104"], "gorsel": "https://cdn.example.com/u.jpg"}
    monkeypatch.setattr(whatsapp_alici, "alicilar", lambda olay: kayit["alicilar"])
    monkeypatch.setattr(uretim_modu, "_wa_urun_gorseli", lambda eslesen: kayit["gorsel"])
    monkeypatch.setattr(whatsapp_notify, "notify_staff_template_async",
                        lambda sablon, params, **kw: kayit["sablon"].append((sablon, params, kw)))
    monkeypatch.setattr(whatsapp_notify, "notify_staff_async",
                        lambda baslik, detay, **kw: kayit["genel"].append((baslik, detay, kw)))
    return kayit


def test_urun_ozeti_tek_ve_cok_kalem():
    assert uretim_modu._wa_urun_ozeti([KALEM]) == ("0121-38 Kırmızı Kırmızı 38", "2")
    urun, adet = uretim_modu._wa_urun_ozeti([KALEM, {**KALEM, "quantity": "1"}, {"barcode": "3"}])
    assert urun.endswith("(+2 kalem daha)") and adet == "4"
    assert uretim_modu._wa_urun_ozeti([]) == ("-", "-")


def test_uretim_siparisi_gorselli_sablonla_gider(cagrilar):
    uretim_modu._wa_personel_bildirimi("uretim_siparis", "987", "0121", [KALEM])

    (sablon, params, kw), = cagrilar["sablon"]
    assert sablon == "uretim_siparisi"
    assert params == ["987", "0121-38 Kırmızı Kırmızı 38", "2"]
    assert kw["image_url"] == "https://cdn.example.com/u.jpg"
    assert kw["only_last4"] == ["0104"]
    assert cagrilar["genel"] == []


def test_gorsel_yoksa_genel_sablonla_gider(cagrilar):
    cagrilar["gorsel"] = None

    uretim_modu._wa_personel_bildirimi("uretim_siparis", "987", "0121", [KALEM])

    assert cagrilar["sablon"] == []
    (baslik, detay, kw), = cagrilar["genel"]
    assert baslik == "Yeni üretim siparişi" and "987" in detay and kw["only_last4"] == ["0104"]


def test_iptal_gorselsiz_sablonla_gider(cagrilar):
    uretim_modu._wa_personel_bildirimi("uretim_iptal", "987", "0121", [KALEM])

    (sablon, params, kw), = cagrilar["sablon"]
    assert sablon == "uretim_iptal" and params[0] == "987"
    assert "image_url" not in kw and kw["only_last4"] == ["0104"]


def test_alici_yoksa_hic_gonderilmez(cagrilar):
    cagrilar["alicilar"] = []

    uretim_modu._wa_personel_bildirimi("uretim_siparis", "987", "0121", [KALEM])

    assert cagrilar["sablon"] == [] and cagrilar["genel"] == []
