"""MNG ApiZone istek gövdeleri — saf fonksiyonlar (ağ yok, DB yok).

Alan adları ve sabitler MNG Standard Command / Barcode Command sözleşmesinden;
köprü servisteki createReturnOrder gövdesiyle ve açık kaynak sürücülerle
(omniship-mng, DHL-Cargo-ERPNext) çapraz doğrulandı.

Sabitler:
  shipmentServiceType 1 = STANDART
  packagingType       3 = PAKET
  deliveryType        1 = ADRESE TESLİM
  paymentType         1 = GÖNDERİCİ ÖDEMELİ (2 = alıcı ödemeli)
  smsPreference1      1 = alıcıya "kargon yola çıktı" SMS'i
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from decimal import Decimal

REFERANS_MAX = 20            # ERPNext notu: ≤20 karakter, BÜYÜK harf, müşteri bazında tekil
SHIPMENT_SERVICE_STANDART = 1
PACKAGING_PAKET = 3
DELIVERY_ADRESE_TESLIM = 1
PAYMENT_GONDERICI = 1
VARSAYILAN_DESI = int(os.getenv("MNG_DESI_BIRIM") or 2)   # çift başına desi (Komutan: 1 ürün 2, 2 ürün 4, 3 ürün 6)
VARSAYILAN_KG = int(os.getenv("MNG_KG_BIRIM") or 1)       # çift başına kg
VARSAYILAN_ICERIK = "Ayakkabi"
# MNG recipient.taxNumber'ı boş kabul etmiyor (26056: 11 haneli TC ya da 10 haneli VKN zorunlu).
# Bireysel alıcıdan TC toplanmıyor → entegratörlerin kullandığı yer tutucu.
VARSAYILAN_TC = "11111111111"
# MNG recipient.email'i de boş kabul etmiyor (26039 "geçerli bir e-posta olmalı"); değişim ve
# manuel siparişte müşteri e-postası toplanmıyor → mağaza adresi (MNG_VARSAYILAN_EMAIL ile değişir).
VARSAYILAN_EMAIL = os.getenv("MNG_VARSAYILAN_EMAIL") or "info@gullushoes.com"
# MNG SMS tercihleri (ApiZone createOrder şeması, 2026-10-15):
#   smsPreference1: kargo VARIŞ ŞUBESİNE ulaştığında alıcıya SMS      → açık
#   smsPreference2: kargo İLK HAZIRLANDIĞINDA alıcıya SMS              → açık (MNG_SMS_HAZIRLANDI=0 kapatır)
#   smsPreference3: kargo TESLİM edildiğinde GÖNDERİCİYE SMS           → kapalı (MNG_SMS_TESLIM_GONDERICI=1 açar)
SMS_VARIS = 1
SMS_HAZIRLANDI = 0 if (os.getenv("MNG_SMS_HAZIRLANDI") or "1").strip() in ("0", "false", "hayir", "hayır") else 1
SMS_TESLIM_GONDERICI = 1 if (os.getenv("MNG_SMS_TESLIM_GONDERICI") or "0").strip() in ("1", "true", "evet") else 0
_EMAIL_DESENI = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass(frozen=True)
class Alici:
    ad_soyad: str
    adres: str
    telefon: str
    il: str = ""
    ilce: str = ""
    il_kodu: int = 0
    ilce_kodu: int = 0
    email: str = ""
    tc_vergi_no: str = ""


@dataclass(frozen=True)
class Parca:
    icerik: str = VARSAYILAN_ICERIK
    desi: int = VARSAYILAN_DESI
    kg: int = VARSAYILAN_KG


def parca_adetle(adet: int) -> Parca:
    """Tek paket, içindeki çift sayısına göre beyan: desi = birim × adet, kg = birim × adet."""
    adet = max(1, int(adet or 1))
    return Parca(desi=VARSAYILAN_DESI * adet, kg=VARSAYILAN_KG * adet)


@dataclass(frozen=True)
class GonderiIstegi:
    referans: str
    alici: Alici
    parcalar: tuple[Parca, ...] = field(default_factory=lambda: (Parca(),))
    kapida_odeme_tutari: Decimal | float | int | None = None
    icerik: str = VARSAYILAN_ICERIK
    aciklama: str = ""
    fatura_no: str = ""


def referans_normalize(deger: str) -> str:
    """MNG referansı: büyük harf, boşluksuz, en çok REFERANS_MAX karakter."""
    temiz = re.sub(r"\s+", "", str(deger or "")).upper()
    if not temiz:
        raise ValueError("MNG referans numarası boş olamaz.")
    if len(temiz) > REFERANS_MAX:
        raise ValueError(f"MNG referansı {REFERANS_MAX} karakteri aşamaz: {temiz!r}")
    return temiz


def telefon_normalize(telefon: str) -> str:
    """MNG mobil no: 10 hane, başında 0 veya +90 yok (5xxxxxxxxx)."""
    rakamlar = re.sub(r"\D", "", str(telefon or ""))
    if rakamlar.startswith("90") and len(rakamlar) == 12:
        rakamlar = rakamlar[2:]
    if rakamlar.startswith("0") and len(rakamlar) == 11:
        rakamlar = rakamlar[1:]
    return rakamlar


def email_normalize(email: str) -> str:
    """Geçerli e-posta yoksa mağaza adresi (MNG zorunlu tutuyor)."""
    temiz = (email or "").strip()
    return temiz if _EMAIL_DESENI.match(temiz) else VARSAYILAN_EMAIL


def _kapida_odeme(tutar) -> tuple[int, float]:
    if tutar is None:
        return 0, 0
    deger = float(tutar)
    if deger <= 0:
        return 0, 0
    return 1, round(deger, 2)


def parca_listesi(referans: str, parcalar: tuple[Parca, ...]) -> list[dict]:
    """orderPieceList — her parçaya REFERANS-P<n> barkodu (köprüdeki iade deseniyle aynı)."""
    if not parcalar:
        parcalar = (Parca(),)
    return [
        {
            "barcode": f"{referans}-P{i}",
            "desi": int(p.desi),
            "kg": int(p.kg),
            "content": p.icerik,
        }
        for i, p in enumerate(parcalar, start=1)
    ]


ADRES_AZAMI = 200          # MNG 26048: Recipient.Address 200 karakterden uzun olamaz


def adres_kisalt(adres: str | None) -> str:
    """Fazla boşlukları sıkıştır, 200'ü aşarsa kes (müşteri serbest metni bazen çok uzun)."""
    duz = re.sub(r"\s+", " ", (adres or "")).strip()
    return duz if len(duz) <= ADRES_AZAMI else duz[:ADRES_AZAMI].rstrip()


def alici_govdesi(alici: Alici) -> dict:
    """recipient — customerId GÖNDERİLMEZ (fullName ile birlikte verilince MNG reddediyor).

    il_kodu/ilce_kodu 0 ise MNG cityName/districtName metnini zorunlu sayar;
    kod verilirse metin yine eşlik eder (cbsinfoapi'den gelen adlar).
    """
    return {
        "refCustomerId": "",
        "cityCode": int(alici.il_kodu or 0),
        "cityName": (alici.il or "").strip(),
        "districtCode": int(alici.ilce_kodu or 0),
        "districtName": (alici.ilce or "").strip(),
        "address": adres_kisalt(alici.adres),
        "bussinessPhoneNumber": "",
        "email": email_normalize(alici.email),
        "taxOffice": "" if alici.tc_vergi_no else "SAHIS",
        "taxNumber": (alici.tc_vergi_no or "").strip() or VARSAYILAN_TC,
        "fullName": (alici.ad_soyad or "").strip(),
        "homePhoneNumber": "",
        "mobilePhoneNumber": telefon_normalize(alici.telefon),
    }


def siparis_govdesi(istek: GonderiIstegi, shipper_customer_id: str | int) -> dict:
    """POST /standardcmdapi/createOrder gövdesi."""
    referans = referans_normalize(istek.referans)
    is_cod, cod_amount = _kapida_odeme(istek.kapida_odeme_tutari)
    return {
        "order": {
            "referenceId": referans,
            "barcode": referans,
            "billOfLandingId": istek.fatura_no or "",
            "isCOD": is_cod,
            "codAmount": cod_amount,
            "shipmentServiceType": SHIPMENT_SERVICE_STANDART,
            "packagingType": PACKAGING_PAKET,
            "content": istek.icerik or VARSAYILAN_ICERIK,
            "smsPreference1": SMS_VARIS,
            "smsPreference2": SMS_HAZIRLANDI,
            "smsPreference3": SMS_TESLIM_GONDERICI,
            "paymentType": PAYMENT_GONDERICI,
            "deliveryType": DELIVERY_ADRESE_TESLIM,
            "description": istek.aciklama or istek.icerik or VARSAYILAN_ICERIK,
            "marketPlaceShortCode": "",
            "marketPlaceSaleCode": "",
        },
        "orderPieceList": parca_listesi(referans, istek.parcalar),
        "recipient": alici_govdesi(istek.alici),
        "shipper": {"customerId": int(shipper_customer_id)},
    }


def barkod_govdesi(istek: GonderiIstegi) -> dict:
    """POST /barcodecmdapi/createbarcode gövdesi (createOrder'dan sonra)."""
    referans = referans_normalize(istek.referans)
    is_cod, cod_amount = _kapida_odeme(istek.kapida_odeme_tutari)
    return {
        "referenceId": referans,
        "billOfLandingId": istek.fatura_no or "",
        "isCOD": is_cod,
        "codAmount": cod_amount,
        "printReferenceBarcodeOnError": 0,
        "message": "",
        "additionalContent1": "",
        "additionalContent2": "",
        "additionalContent3": "",
        "additionalContent4": "",
        "orderPieceList": parca_listesi(referans, istek.parcalar),
        "packagingType": PACKAGING_PAKET,
    }


def tek_kayit(govde):
    """MNG tek nesne yerine tek elemanlı liste döndürür ([{...}]); düzleştir."""
    if isinstance(govde, list):
        return govde[0] if govde else {}
    return govde if isinstance(govde, dict) else {}
