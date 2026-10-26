"""MNG giden gönderi istemcisi — saf mantık testleri (ağ yok, DB yok).

Çalıştırma: DISABLE_JOBS=1 python -m pytest tests/test_mng_kargo.py --noconftest -q
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mng_kargo.durum import (  # noqa: E402
    DAGITIMDA, HAZIRLANDI, KARGODA, TESLIM, BILINMIYOR, durum_cozumle, kod_cevir,
)
from mng_kargo.govde import (  # noqa: E402
    Alici, GonderiIstegi, Parca, barkod_govdesi, referans_normalize, siparis_govdesi,
    tek_kayit, telefon_normalize,
)


def _istek(**ek):
    alici = Alici(ad_soyad="Ayşe Yılmaz", adres="Atatürk Cad. No:5", telefon="0532 123 45 67",
                  il="İSTANBUL", ilce="KADIKÖY")
    return GonderiIstegi(referans="dg-1234567", alici=alici, **ek)


def test_referans_buyuk_harf_ve_bosluksuz():
    assert referans_normalize(" dg-12 34 ") == "DG-1234"


def test_referans_20_karakteri_asamaz():
    with pytest.raises(ValueError):
        referans_normalize("A" * 21)


@pytest.mark.parametrize("ham,beklenen", [
    ("0532 123 45 67", "5321234567"),
    ("+90 532 123 45 67", "5321234567"),
    ("905321234567", "5321234567"),
    ("5321234567", "5321234567"),
])
def test_telefon_10_hane(ham, beklenen):
    assert telefon_normalize(ham) == beklenen


def test_siparis_govdesi_temel_alanlar():
    g = siparis_govdesi(_istek(), "800169398")
    assert g["order"]["referenceId"] == "DG-1234567"
    assert g["order"]["barcode"] == "DG-1234567"
    assert g["order"]["isCOD"] == 0 and g["order"]["codAmount"] == 0
    assert g["order"]["paymentType"] == 1          # gönderici ödemeli
    assert g["orderPieceList"] == [{"barcode": "DG-1234567-P1", "desi": 2, "kg": 1, "content": "Ayakkabi"}]
    assert g["recipient"]["fullName"] == "Ayşe Yılmaz"
    assert g["recipient"]["mobilePhoneNumber"] == "5321234567"
    assert g["recipient"]["cityCode"] == 0 and g["recipient"]["cityName"] == "İSTANBUL"
    assert g["recipient"]["taxOffice"] == "SAHIS"
    assert "customerId" not in g["recipient"]      # fullName ile birlikte MNG reddediyor
    assert g["shipper"] == {"customerId": 800169398}


def test_kapida_odeme_tutari_isCOD_acar():
    g = siparis_govdesi(_istek(kapida_odeme_tutari=Decimal("1249.90")), 1)
    assert g["order"]["isCOD"] == 1
    assert g["order"]["codAmount"] == 1249.9
    b = barkod_govdesi(_istek(kapida_odeme_tutari=1249.9))
    assert b["isCOD"] == 1 and b["codAmount"] == 1249.9


def test_sifir_veya_negatif_tutar_kapida_odeme_degil():
    assert siparis_govdesi(_istek(kapida_odeme_tutari=0), 1)["order"]["isCOD"] == 0
    assert siparis_govdesi(_istek(kapida_odeme_tutari=-5), 1)["order"]["isCOD"] == 0


def test_coklu_parca_numaralanir():
    g = siparis_govdesi(_istek(parcalar=(Parca(), Parca(icerik="Kutu 2"))), 1)
    assert [p["barcode"] for p in g["orderPieceList"]] == ["DG-1234567-P1", "DG-1234567-P2"]


def test_il_ilce_kodu_verilince_govdeye_gecer():
    alici = Alici(ad_soyad="A", adres="B", telefon="5", il="İSTANBUL", ilce="KADIKÖY", il_kodu=34, ilce_kodu=1234)
    g = siparis_govdesi(GonderiIstegi(referans="X1", alici=alici), 1)
    assert g["recipient"]["cityCode"] == 34 and g["recipient"]["districtCode"] == 1234


def test_tek_kayit_listeyi_duzlestirir():
    assert tek_kayit([{"a": 1}]) == {"a": 1}
    assert tek_kayit({"a": 1}) == {"a": 1}
    assert tek_kayit([]) == {}
    assert tek_kayit(None) == {}


@pytest.mark.parametrize("kod,beklenen", [
    (1, HAZIRLANDI), (2, KARGODA), (3, KARGODA), (4, DAGITIMDA), (5, TESLIM), ("5", TESLIM),
    (99, BILINMIYOR), (None, BILINMIYOR), ("abc", BILINMIYOR),
])
def test_kod_cevir(kod, beklenen):
    assert kod_cevir(kod) == beklenen


def test_durum_cozumle_tek_elemanli_liste_ve_teslim():
    d = durum_cozumle([{
        "shipmentStatusCode": 5, "shipmentStatus": "Teslim_Edildi", "shipmentId": 614118757013,
        "isDelivered": 1, "deliveryTo": "AYSE YILMAZ", "deliveryDateTime": "14-10-2026 15:42",
        "trackingUrl": "https://kargotakip.mngkargo.com.tr/?id=614118757013",
    }])
    assert d.durum == TESLIM and d.teslim_edildi and d.kapanmis
    assert d.shipment_id == "614118757013"
    assert d.teslim_alan == "AYSE YILMAZ"
    assert d.teslim_zamani is not None and d.teslim_zamani.hour == 15
    assert d.etiket == "Teslim Edildi"


def test_durum_cozumle_yolda():
    d = durum_cozumle({"shipmentStatusCode": "2", "shipmentStatus": "Transfer_Asamasinda", "shipmentId": "1"})
    assert d.durum == KARGODA and d.yolda and not d.kapanmis and not d.teslim_edildi


def test_durum_cozumle_hazirlandi_yolda_degil():
    d = durum_cozumle({"shipmentStatusCode": 1})
    assert d.durum == HAZIRLANDI and not d.yolda


def test_zpl_boyut_mng_etiketi():
    from mng_kargo.etiket import zpl_boyut_inch, zpl_boyut_mm
    zpl = "^XA\n^MMT\n^CI28\n^PW831\n^LL0959\n^LS0\n^XZ"
    assert zpl_boyut_inch(zpl) == (4.09, 4.72)
    assert zpl_boyut_mm(zpl) == (104, 120)
    assert zpl_boyut_mm("") == (104, 120)


def test_sube_cozulmedi_yalniz_gecici_20001():
    from mng_kargo.client import MngHata, sube_cozulmedi
    assert sube_cozulmedi(MngHata("x [20001] VARIŞ ŞUBESİ BULUNAMADI ! DAHA SONRA TEKRAR DENEYİN", kod="20001", http=500))
    assert not sube_cozulmedi(MngHata("x [20001] Tahsilatlı Kapıda Gönderi Tutar en az 20 TL", kod="20001", http=500))
    assert not sube_cozulmedi(MngHata("x [26056] tax", kod="26056", http=400))


def test_email_bos_veya_bozuksa_magaza_adresi():
    from mng_kargo.govde import VARSAYILAN_EMAIL, email_normalize
    assert email_normalize("") == VARSAYILAN_EMAIL
    assert email_normalize("ayse@") == VARSAYILAN_EMAIL
    assert email_normalize(" ayse@ornek.com ") == "ayse@ornek.com"
    assert siparis_govdesi(_istek(), 1)["recipient"]["email"] == VARSAYILAN_EMAIL


def test_png_kirp_bos_kenarlari_atar():
    from io import BytesIO
    from PIL import Image
    from mng_kargo.etiket import png_kirp
    img = Image.new("L", (831, 959), 255)
    for y in range(40, 800):
        for x in range(30, 800, 7):
            img.putpixel((x, y), 0)
    ham = BytesIO(); img.save(ham, format="PNG")
    kirpik = Image.open(BytesIO(png_kirp(ham.getvalue())))
    assert kirpik.width <= 790 and 740 <= kirpik.height <= 780      # 959 → içerik + 8 px kenar
    assert png_kirp(b"bozuk") == b"bozuk"


def test_sms_tercihleri_varsayilan():
    o = siparis_govdesi(_istek(), 1)["order"]
    assert (o["smsPreference1"], o["smsPreference2"], o["smsPreference3"]) == (1, 1, 0)


def test_parca_adetle():
    from mng_kargo.govde import parca_adetle
    assert (parca_adetle(1).desi, parca_adetle(1).kg) == (2, 1)
    assert (parca_adetle(3).desi, parca_adetle(3).kg) == (6, 3)
    assert parca_adetle(0).desi == 2


def test_alici_adresi_200_karakterde_kesilir():
    """#1456 (19.10): MNG 26048 'Recipient.Address 200 karakterden küçük veya eşit olmalıdır'."""
    from mng_kargo.govde import adres_kisalt
    uzun = "Taspazar mahallesi,  Atatürk bulvarı, 40mt yol üzeri, " * 6
    assert len(adres_kisalt(uzun)) <= 200 and "  " not in adres_kisalt(uzun)
    assert adres_kisalt("  Moda  Cad. 3 ") == "Moda Caddesi 3"


def test_adres_normalize_kisaltmalari_acar_ve_ascii_yapar():
    """#1482 (26.10): MNG 'A Keykubat Bulv cevhet atilla caddesi C blok kat1 daire:3' ile şube bulamadı,
    açık yazımla buldu. Kısaltmalar açılır, Türkçe harfler ASCII olur, DB metni değişmez."""
    from mng_kargo.govde import adres_normalize, alici_govdesi
    from mng_kargo.govde import Alici
    assert adres_normalize("Konaklı Mah. A Keykubat Bulv cevhet atilla cad. C blok kat1 daire:3") == \
        "Konakli Mahallesi A Keykubat Bulvari cevhet atilla Caddesi C Blok Kat 1 Daire 3"
    assert adres_normalize("Yayla mahallesi 1412.sokak elif apartmanı no :22 giriş kat daire no :17") == \
        "Yayla Mahallesi 1412.Sokak elif Apartmani No 22 giris kat daire No 17"
    assert adres_normalize("  Moda  Cad. 3 ") == "Moda Caddesi 3"
    g = alici_govdesi(Alici(ad_soyad="A", adres="Şehit Bayram Gökmen mah.Konuralp cad.No:80/1", telefon="5", il="DÜZCE", ilce="MERKEZ"))
    assert g["address"] == "Sehit Bayram Gokmen Mahallesi Konuralp Caddesi No 80/1"
