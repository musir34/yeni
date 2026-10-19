"""MNG ApiZone HTTP istemcisi — giden gönderi.

Akış (omniship-mng ve köprü serviste doğrulanan):
  POST /token                                  → {"jwt": ...}   (X-IBM-Client-Id/Secret)
  POST /standardcmdapi/createOrder             → sipariş (orderInvoiceId)
  POST /barcodecmdapi/createbarcode            → shipmentId + barcodes[{barcode, value=ZPL}]
       hata 20001 "VARIŞ ŞUBESİ BULUNAMADI" → MNG şubeyi henüz çözmedi, 5 ve 10 sn sonra tekrar
       hata 3002  "ZATEN VAR"               → createOrder tekrarı; barkoda geç (idempotent)
  GET  /standardqueryapi/getshipmentstatus/{referenceId}
  GET  /standardqueryapi/trackshipment/{referenceId}
  PUT  /standardcmdapi/cancelorder/{referenceId}
  GET  /cbsinfoapi/getcities, /cbsinfoapi/getdistricts/{cityCode}

Cevaplar tek elemanlı liste gelebilir → govde.tek_kayit ile düzleştirilir.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import requests

from .ayar import MngAyar
from .durum import GonderiDurumu, durum_cozumle
from .govde import GonderiIstegi, barkod_govdesi, referans_normalize, siparis_govdesi, tek_kayit

logger = logging.getLogger(__name__)

TOKEN_OMRU_SN = 20 * 60          # köprüyle aynı: 20 dk (MNG 8 saat veriyor, erken yenile)
ZAMAN_ASIMI = (5, 30)
BARKOD_TEKRAR_BEKLEME_SN = (5, 10)
HATA_SUBE_BULUNAMADI = "20001"
HATA_SIPARIS_ZATEN_VAR = "3002"


class MngHata(Exception):
    def __init__(self, mesaj: str, kod: str = "", http: int = 0, govde=None):
        super().__init__(mesaj)
        self.kod = kod
        self.http = http
        self.govde = govde


@dataclass(frozen=True)
class GonderiSonucu:
    referans: str
    shipment_id: str
    fatura_id: str
    barkod: str          # kuryenin okuttuğu barkod metni (barcodes[0].barcode)
    zpl: str             # MNG'nin ürettiği etiket (ZPL)
    siparis_cevabi: dict
    barkod_cevabi: dict


def _hata_ayikla(govde) -> tuple[str, str]:
    """MNG hata gövdesi {"error": {"Code": "...", "Description": "..."}} ya da düz metin."""
    kayit = tek_kayit(govde) if isinstance(govde, (list, dict)) else {}
    hata = kayit.get("error") if isinstance(kayit, dict) else None
    if isinstance(hata, dict):
        kod = str(hata.get("Code") or hata.get("code") or "")
        aciklama = str(hata.get("Description") or hata.get("description") or hata.get("message") or "")
        return kod, aciklama
    if isinstance(kayit, dict) and (kayit.get("Code") or kayit.get("code")):
        return str(kayit.get("Code") or kayit.get("code")), str(kayit.get("Description") or kayit.get("description") or "")
    return "", str(govde)[:300] if govde else ""


def daha_once_kesilmis(exc: MngHata) -> bool:
    """20001 'SİPARİŞ … Tarihinde SA-… NO İLE DAHA ÖNCE KESİLMİŞ' — barkod bu sipariş için zaten üretilmiş
    (eşzamanlı ikinci istek ya da kaydı 'hata'dan yeniden açma). Hata değil, barkod vardır."""
    return exc.kod == HATA_SUBE_BULUNAMADI and "DAHA ÖNCE KESİLMİŞ" in str(exc).upper()


def sube_cozulmedi(exc: MngHata) -> bool:
    """20001 'VARIŞ ŞUBESİ BULUNAMADI ... DAHA SONRA TEKRAR DENEYİN' — geçici, tekrar denenir.
    (MNG aynı 20001 kodunu kalıcı doğrulama hatalarında da kullanıyor, metne bakılır.)"""
    return exc.kod == HATA_SUBE_BULUNAMADI and "VARIŞ ŞUBESİ" in str(exc).upper()


class MngClient:
    def __init__(self, ayar: MngAyar | None = None, *, uyku=time.sleep):
        self.ayar = ayar or MngAyar.from_env()
        self._uyku = uyku
        self._token = ""
        self._token_bitis = 0.0
        self._kilit = threading.Lock()

    # ------------------------------------------------------------------ token
    def _basliklar(self, token: bool = True, json_govde: bool = True) -> dict:
        h = {
            "X-IBM-Client-Id": self.ayar.client_id,
            "X-IBM-Client-Secret": self.ayar.client_secret,
            "Accept": "application/json",
        }
        if json_govde:
            h["Content-Type"] = "application/json"
        if token:
            h["Authorization"] = f"Bearer {self._jwt()}"
        return h

    def _jwt(self) -> str:
        with self._kilit:
            if self._token and time.monotonic() < self._token_bitis - 60:
                return self._token
            if not self.ayar.hazir:
                raise MngHata(f"MNG kimlikleri eksik ({self.ayar.ortam}); .env'i kontrol edin.")
            r = requests.post(
                f"{self.ayar.base_url}/token",
                headers=self._basliklar(token=False),
                json={
                    "customerNumber": self.ayar.customer_number,
                    "password": self.ayar.password,
                    "identityType": self.ayar.identity_type,
                },
                timeout=ZAMAN_ASIMI,
            )
            if r.status_code >= 400:
                raise MngHata(f"MNG token hatası: HTTP {r.status_code} {r.text[:200]}", http=r.status_code)
            jwt = (r.json() or {}).get("jwt") if r.content else None
            if not jwt:
                raise MngHata("MNG token cevabında jwt yok.")
            self._token = jwt
            self._token_bitis = time.monotonic() + TOKEN_OMRU_SN
            return jwt

    # ------------------------------------------------------------------ http
    def _istek(self, yontem: str, yol: str, govde=None):
        url = f"{self.ayar.base_url}{yol}"
        r = requests.request(yontem, url, headers=self._basliklar(), json=govde, timeout=ZAMAN_ASIMI)
        if r.status_code == 401:            # token süresi bitti → bir kez yenile
            with self._kilit:
                self._token = ""
            r = requests.request(yontem, url, headers=self._basliklar(), json=govde, timeout=ZAMAN_ASIMI)
        try:
            veri = r.json() if r.content else None
        except ValueError:
            veri = r.text
        if r.status_code >= 400:
            kod, aciklama = _hata_ayikla(veri)
            raise MngHata(f"MNG {yontem} {yol} HTTP {r.status_code} [{kod}] {aciklama}",
                          kod=kod, http=r.status_code, govde=veri)
        return veri

    # ------------------------------------------------------------------ gönderi
    def siparis_olustur(self, istek: GonderiIstegi) -> dict:
        """createOrder — aynı referans ikinci kez gelirse (3002) sessizce geç."""
        govde = siparis_govdesi(istek, self.ayar.customer_number)
        try:
            return tek_kayit(self._istek("POST", "/standardcmdapi/createOrder", govde))
        except MngHata as exc:
            if exc.kod == HATA_SIPARIS_ZATEN_VAR or "ZATEN VAR" in str(exc).upper():
                logger.info("MNG createOrder: %s zaten kayıtlı, barkoda geçiliyor.", istek.referans)
                return {"zatenVar": True}
            raise

    def barkod_olustur(self, istek: GonderiIstegi, tekrar: bool = True) -> dict:
        """createbarcode — 20001 (varış şubesi çözülmedi) için 5 + 10 sn bekleyip tekrar.

        MNG kuralı: createOrder'dan hemen sonra şube çözülmemiş olabilir (canlıda ~30-45 sn).
        Zamanlayıcıdan çağrılırken tekrar=False: beklemeden hatayı döndür, sonraki turda yine dene.
        """
        govde = barkod_govdesi(istek)
        deneme = 0
        while True:
            deneme += 1
            try:
                return tek_kayit(self._istek("POST", "/barcodecmdapi/createbarcode", govde))
            except MngHata as exc:
                if tekrar and sube_cozulmedi(exc) and deneme <= len(BARKOD_TEKRAR_BEKLEME_SN):
                    bekle = BARKOD_TEKRAR_BEKLEME_SN[deneme - 1]
                    logger.warning("MNG createbarcode %s: şube çözülmedi, %s sn sonra tekrar.", istek.referans, bekle)
                    self._uyku(bekle)
                    continue
                raise

    def barkod_sonucu(self, istek: GonderiIstegi, barkod: dict, siparis: dict | None = None) -> GonderiSonucu:
        """createbarcode cevabını GonderiSonucu'na çevirir (canlıda doğrulanan alanlar:
        shipmentId, invoiceId, barcodes[{barcode, value=ZPL 831x959 dot ≈ 10x12 cm}])."""
        siparis = siparis or {}
        barkodlar = barkod.get("barcodes") or []
        ilk = barkodlar[0] if barkodlar and isinstance(barkodlar[0], dict) else {}
        return GonderiSonucu(
            referans=referans_normalize(istek.referans),
            shipment_id=str(barkod.get("shipmentId") or ""),
            fatura_id=str(barkod.get("invoiceId") or siparis.get("orderInvoiceId") or ""),
            barkod=str(ilk.get("barcode") or ""),
            zpl=str(ilk.get("value") or ""),
            siparis_cevabi=siparis,
            barkod_cevabi=barkod,
        )

    def gonderi_olustur(self, istek: GonderiIstegi) -> GonderiSonucu:
        """createOrder + createbarcode tek seferde (prova/elle kullanım; üretimde iki aşama ayrı)."""
        siparis = self.siparis_olustur(istek)
        barkod = self.barkod_olustur(istek)
        barkodlar = barkod.get("barcodes") or []
        ilk = barkodlar[0] if barkodlar and isinstance(barkodlar[0], dict) else {}
        return GonderiSonucu(
            referans=referans_normalize(istek.referans),
            shipment_id=str(barkod.get("shipmentId") or siparis.get("orderInvoiceId") or ""),
            fatura_id=str(barkod.get("invoiceId") or siparis.get("orderInvoiceId") or ""),
            barkod=str(ilk.get("barcode") or ""),
            zpl=str(ilk.get("value") or ""),
            siparis_cevabi=siparis,
            barkod_cevabi=barkod,
        )

    # ------------------------------------------------------------------ takip
    def durum(self, referans: str) -> GonderiDurumu | None:
        """getshipmentstatus/{referenceId}; kayıt yoksa (404) None."""
        try:
            veri = self._istek("GET", f"/standardqueryapi/getshipmentstatus/{referans_normalize(referans)}")
        except MngHata as exc:
            if exc.http == 404:
                return None
            raise
        return durum_cozumle(veri) if veri else None

    def hareketler(self, referans: str) -> list[dict]:
        """trackshipment/{referenceId} → hareket listesi (eventStatus, eventDateTime2, location...)."""
        try:
            veri = self._istek("GET", f"/standardqueryapi/trackshipment/{referans_normalize(referans)}")
        except MngHata as exc:
            if exc.http == 404:
                return []
            raise
        return [h for h in (veri or []) if isinstance(h, dict)] if isinstance(veri, list) else []

    def iptal(self, referans: str) -> dict:
        """cancelorder/{referenceId} — barkod alınmamış sipariş için."""
        veri = self._istek("PUT", f"/standardcmdapi/cancelorder/{referans_normalize(referans)}")
        return tek_kayit(veri) if veri else {}

    def iptal_gonderi(self, referans: str, shipment_id: str) -> dict:
        """barcodecmdapi/cancelshipment — barkodu alınmış gönderi (şube kabul etmeden önce)."""
        veri = self._istek("PUT", "/barcodecmdapi/cancelshipment",
                           {"referenceId": referans_normalize(referans), "shipmentId": str(shipment_id)})
        return tek_kayit(veri) if veri else {}

    def siparis_getir(self, referans: str) -> dict | None:
        """standardqueryapi/getorder/{referenceId} — MNG'deki sipariş kaydı (isTransformedToShipment vb.)."""
        try:
            veri = self._istek("GET", f"/standardqueryapi/getorder/{referans_normalize(referans)}")
        except MngHata as exc:
            if exc.http == 404:
                return None
            raise
        return tek_kayit(veri) if veri else None

    # ------------------------------------------------------------------ il / ilçe
    def sehirler(self) -> list[dict]:
        veri = self._istek("GET", "/cbsinfoapi/getcities")
        return veri if isinstance(veri, list) else []

    def ilceler(self, il_kodu: int | str) -> list[dict]:
        kod = str(il_kodu).zfill(2)
        veri = self._istek("GET", f"/cbsinfoapi/getdistricts/{kod}")
        return veri if isinstance(veri, list) else []
