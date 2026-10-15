"""Serbest adresten il/ilçe çıkarma — saf testler (ağ yok, DB yok).

Çalıştırma: DISABLE_JOBS=1 python -m pytest tests/test_mng_adres.py --noconftest -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mng_kargo.adres import ILLER, alici_kur, il_bul, il_ilce_ayikla, sadelestir  # noqa: E402


def test_81_il():
    assert len(set(ILLER)) == 81


@pytest.mark.parametrize("adres,il,ilce", [
    ("Caferağa Mah. Moda Cad. No:12 D:3 Kadıköy / İstanbul", "İSTANBUL", "KADIKÖY"),
    ("Atatürk Mah. 100. Sok. No 5 Bornova İZMİR", "İZMİR", "BORNOVA"),
    ("Yenişehir Mah. 5. Cad. Çankaya-Ankara 06420", "ANKARA", "ÇANKAYA"),
    ("Merkez mah. no 3 urfa", "ŞANLIURFA", ""),           # eş ad; ilçe 'no 3' değil
    ("Kızılay Meydanı", "", ""),
])
def test_il_ilce_ayikla(adres, il, ilce):
    assert il_ilce_ayikla(adres) == (il, ilce)


def test_il_bul_turkce_i_buyuk_harf():
    assert il_bul("izmir") == "İZMİR"
    assert il_bul("ısparta") == "ISPARTA"
    assert sadelestir("Şanlıurfa") == "SANLIURFA"


def test_alici_kur_form_il_oncelikli_ve_kanonik():
    a = alici_kur("Ayşe Yılmaz", "Bir yer Kadıköy/İstanbul", "0532", il="izmir", ilce="konak")
    assert a.il == "İZMİR" and a.ilce == "KONAK"


def test_alici_kur_form_bos_adresten_bulur():
    a = alici_kur("A", "Moda Cad. 3 Kadıköy / İstanbul", "5", il="", ilce="")
    assert a.il == "İSTANBUL" and a.ilce == "KADIKÖY"


def test_alici_kur_shopify_province_city():
    a = alici_kur("A", "Sok 1", "5", il="İstanbul", ilce="Beşiktaş", email="x@y.com")
    assert a.il == "İSTANBUL" and a.ilce == "BEŞİKTAŞ" and a.email == "x@y.com"


# ---------------------------------------------------------------- Shopify gerçek veri desenleri
@pytest.mark.parametrize("province,city,zip_,adres,il,ilce", [
    ("Istanbul", "Bağcılar", "34212", "x", "İSTANBUL", "BAĞCILAR"),
    (None, "İzmir", None, "x", "İZMİR", ""),                 # city = il, ilçe bilinmiyor
    (None, "EyÜpsultan", None, "x", "", "EYÜPSULTAN"),       # il yok; cbs ya da adres çözer
    (None, "İZMİT/KOCAELİ", None, "x", "KOCAELİ", "İZMİT/KOCAELİ"),
    ("Bir seçenek belirleyin…", "Eskişehir", None, "x", "ESKİŞEHİR", ""),
    (None, "Tr.03416", "34050", "x", "İSTANBUL", "TR.03416"),   # çöp city, plaka kurtarır
    (None, "39afyonkarahisar", None, "Merkez Mah. Afyon", "AFYONKARAHİSAR", "39AFYONKARAHİSAR"),
    ("Düzce", "Düzce/Merkez", "81100", "x", "DÜZCE", "DÜZCE/MERKEZ"),
])
def test_alici_kur_shopify_desenleri(province, city, zip_, adres, il, ilce):
    a = alici_kur("A", adres, "5", il=province or "", ilce=city or "", posta_kodu=zip_ or "")
    assert (a.il, a.ilce) == (il, ilce)


def test_plaka_il():
    from mng_kargo.adres import plaka_il
    assert plaka_il("34212") == "İSTANBUL" and plaka_il("06280") == "ANKARA" and plaka_il("5446807387") == ""


# ---------------------------------------------------------------- CBS (MNG il/ilçe listesi, sahte önbellek)
_CBS = {"zaman": 9e12, "iller": [{"code": "34", "name": "İSTANBUL"}, {"code": "16", "name": "BURSA"},
                                 {"code": "81", "name": "DÜZCE"}, {"code": "03", "name": "AFYON"}, {"code": "41", "name": "KOCAELİ"}],
        "ilceler": {"34": [{"code": "1", "name": "EYÜP"}, {"code": "2", "name": "KADIKÖY"}, {"code": "3", "name": "BAĞCILAR"}],
                    "16": [{"code": "4", "name": "YENİŞEHİR"}, {"code": "5", "name": "NİLÜFER"}],
                    "81": [{"code": "6", "name": "MERKEZ"}, {"code": "7", "name": "AKÇAKOCA"}],
                    "03": [{"code": "8", "name": "MERKEZ"}], "41": [{"code": "9", "name": "İZMİT"}]}}


@pytest.fixture()
def cbs():
    from mng_kargo import cbs as m
    m.bellek_ayarla(_CBS)
    yield m
    m.bellek_ayarla(None)


def test_cbs_il_coz_kanonik_ve_mng_adi(cbs):
    assert cbs.il_coz("AFYONKARAHİSAR") == ("03", "AFYON")
    assert cbs.il_coz("Istanbul") == ("34", "İSTANBUL")
    assert cbs.il_coz("34") == ("34", "İSTANBUL")
    assert cbs.il_coz("Bir seçenek belirleyin…") is None


def test_cbs_ilce_coz_serbest_metin(cbs):
    assert cbs.ilce_coz("34", "EyÜpsultan") == ("1", "EYÜP")
    assert cbs.ilce_coz("16", "Bursa yenişehir") == ("4", "YENİŞEHİR")
    assert cbs.ilce_coz("81", "Düzce/Merkez") == ("6", "MERKEZ")
    assert cbs.ilce_coz("41", "", "Yahya Kaptan Mah. İzmit") == ("9", "İZMİT")
    assert cbs.ilce_coz("34", "İstanbul") is None


def test_cbs_alici_tamamla_kod_doldurur(cbs):
    a = alici_kur("A", "Moda Cad. 3", "5", il="", ilce="EyÜpsultan", posta_kodu="34050")
    t = cbs.alici_tamamla(a)
    assert (t.il, t.il_kodu, t.ilce, t.ilce_kodu) == ("İSTANBUL", 34, "EYÜP", 1)
    b = cbs.alici_tamamla(alici_kur("A", "x", "5", il="Istanbul", ilce="İstanbul"))
    assert (b.il, b.il_kodu, b.ilce, b.ilce_kodu) == ("İSTANBUL", 34, "", 0)
