"""Shopify açık sipariş rezervi — saf hesapla_rezerv testleri (DB/API yok).

Modül dosya yolundan yüklenir: `stock_sync` paketinin __init__'i models'i import ettiği
için paket üzerinden import edilmez.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_YOL = Path(__file__).resolve().parent.parent / "stock_sync" / "shopify_rezerv.py"
_spec = importlib.util.spec_from_file_location("shopify_rezerv_saf", _YOL)
shopify_rezerv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shopify_rezerv)
hesapla_rezerv = shopify_rezerv.hesapla_rezerv

V1, V2, V_YOK = "gid://shopify/ProductVariant/1", "gid://shopify/ProductVariant/2", "gid://shopify/ProductVariant/9"
ESLESME = {V1: "BC1", V2: "BC2"}


def _kalem(vid, adet):
    return {"unfulfilledQuantity": adet, "variant": {"id": vid} if vid else None}


def _siparis(no, *kalemler, iptal=None, etiketler=None):
    return {"legacyResourceId": no, "cancelledAt": iptal, "tags": etiketler or [],
            "lineItems": {"nodes": list(kalemler)}}


def _hesapla(siparisler, dusulmus=None, arsivli=None):
    return hesapla_rezerv(siparisler, ESLESME, dusulmus or {}, arsivli or set())


def test_duz_acik_siparis():
    assert _hesapla([_siparis("1", _kalem(V1, 2))]) == {"BC1": 2}


def test_iptal_edilmis_atlanir():
    assert _hesapla([_siparis("1", _kalem(V1, 2), iptal="2026-11-20T10:00:00Z")]) == {}


def test_arsivlendi_etiketli_atlanir():
    assert _hesapla([_siparis("1", _kalem(V1, 2), etiketler=["Arsivlendi"])]) == {}


def test_panel_arsivindeki_atlanir():
    assert _hesapla([_siparis("1", _kalem(V1, 2))], arsivli={"SH-1"}) == {}


def test_karsilanmamis_adet_sifir():
    assert _hesapla([_siparis("1", _kalem(V1, 0))]) == {}


def test_pack_out_yazilmis_rezerv_sifir():
    assert _hesapla([_siparis("1", _kalem(V1, 2))], dusulmus={("SH-1", "BC1"): 2}) == {}


def test_kismi_dusum():
    assert _hesapla([_siparis("1", _kalem(V1, 2))], dusulmus={("SH-1", "BC1"): 1}) == {"BC1": 1}


def test_varyanti_silinmis_kalem_atlanir():
    assert _hesapla([_siparis("1", _kalem(None, 3), _kalem(V2, 1))]) == {"BC2": 1}


def test_eslesmesiz_varyant_atlanir():
    assert _hesapla([_siparis("1", _kalem(V_YOK, 3))]) == {}


def test_ayni_barkod_iki_sipariste_toplanir():
    assert _hesapla([_siparis("1", _kalem(V1, 1)), _siparis("2", _kalem(V1, 2))]) == {"BC1": 3}


def test_ayni_sipariste_ayni_barkod_iki_kalem_dusulmus_bir_kez():
    sonuc = _hesapla([_siparis("1", _kalem(V1, 1), _kalem(V1, 1))], dusulmus={("SH-1", "BC1"): 1})
    assert sonuc == {"BC1": 1}


def test_baska_siparisin_dusumu_karismaz():
    assert _hesapla([_siparis("1", _kalem(V1, 1))], dusulmus={("SH-2", "BC1"): 1}) == {"BC1": 1}
