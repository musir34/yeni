"""MNG CBS Info (il / ilçe kodları) — önbellekli çözümleyici.

Canlı Shopify adresleri dağınık: province çoğu zaman boş, city serbest metin ("EyÜpsultan",
"İZMİT/KOCAELİ", "Bursa yenişehir", "Düzce/Merkez", "Tr.03416"). MNG varış şubesini ilçeden
çözdüğü için ilçeyi MNG'nin kendi listesinden eşlemek en sağlamı.

- getcities (82) + her il için getdistricts bir kez çekilir, uploads/mng_cbs.json'a yazılır,
  7 günde bir yenilenir. API yoksa eski önbellek, o da yoksa boş (adlarla devam, kod 0).
- MNG il kodu = plaka kodu ("34" İSTANBUL). Adlar MNG yazımıyla ("AFYON", "İÇEL" değil "MERSİN"…)
  → eşleştirme sadelestir() ile (Türkçe karakter düzleştirme), gönderimde MNG'nin adı kullanılır.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import replace
from pathlib import Path

from .adres import ES_ADLAR, _AYRAC, il_bul, sadelestir
from .govde import Alici

logger = logging.getLogger(__name__)

ONBELLEK_DOSYASI = Path(os.getenv("MNG_CBS_ONBELLEK") or "uploads/mng_cbs.json")
ONBELLEK_OMRU_SN = 7 * 24 * 3600
_bellek: dict | None = None
_ILCE_GENEL = {"MERKEZ"}          # tek başına geçerse il merkezi; metin eşlemesinde öncelik verilmez


def _api_ile_cek() -> dict:
    from .servis import client
    c = client()
    iller = [{"code": str(i.get("code")), "name": str(i.get("name") or "")} for i in c.sehirler() if i.get("code")]
    ilceler = {}
    for il in iller:
        try:
            ilceler[il["code"]] = [{"code": str(d.get("code")), "name": str(d.get("name") or "")}
                                   for d in c.ilceler(il["code"]) if d.get("code")]
        except Exception:
            logger.warning("[MNG CBS] %s ilçeleri çekilemedi", il["name"], exc_info=True)
            ilceler[il["code"]] = []
    return {"zaman": time.time(), "iller": iller, "ilceler": ilceler}


def _oku_dosya() -> dict | None:
    try:
        if ONBELLEK_DOSYASI.exists():
            return json.loads(ONBELLEK_DOSYASI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("[MNG CBS] önbellek dosyası okunamadı", exc_info=True)
    return None


def _yaz_dosya(veri: dict) -> None:
    try:
        ONBELLEK_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
        ONBELLEK_DOSYASI.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    except OSError:
        logger.warning("[MNG CBS] önbellek dosyası yazılamadı", exc_info=True)


def veri(yenile: bool = False) -> dict:
    """{'iller': [{code,name}], 'ilceler': {code: [{code,name}]}} — bellek → dosya → API."""
    global _bellek
    if _bellek and not yenile and time.time() - _bellek.get("zaman", 0) < ONBELLEK_OMRU_SN:
        return _bellek
    dosya = None if yenile else _oku_dosya()
    if dosya and time.time() - dosya.get("zaman", 0) < ONBELLEK_OMRU_SN:
        _bellek = dosya
        return _bellek
    try:
        _bellek = _api_ile_cek()
        _yaz_dosya(_bellek)
    except Exception:
        logger.warning("[MNG CBS] il/ilçe listesi çekilemedi; eski önbellek kullanılacak", exc_info=True)
        _bellek = dosya or _bellek or {"zaman": 0, "iller": [], "ilceler": {}}
    return _bellek


def bellek_ayarla(v: dict | None) -> None:
    """Testler: sahte liste ver / sıfırla."""
    global _bellek
    _bellek = v


# ---------------------------------------------------------------- çözümleme
def il_coz(metin: str) -> tuple[str, str] | None:
    """İl adı/plaka → (MNG kodu, MNG adı). Kanonik ad (AFYONKARAHİSAR) ↔ MNG adı (AFYON) uyumu."""
    if not metin:
        return None
    iller = veri().get("iller") or []
    anahtar = sadelestir(metin).strip()
    if re.fullmatch(r"\d{2}", anahtar):
        for il in iller:
            if il["code"] == anahtar:
                return il["code"], il["name"]
    adaylar = {anahtar, sadelestir(ES_ADLAR.get(anahtar, "")), sadelestir(il_bul(metin))}
    adaylar.discard("")
    for il in iller:
        il_anahtar = sadelestir(il["name"])
        for a in adaylar:
            if a == il_anahtar or a.startswith(il_anahtar) or il_anahtar.startswith(a):
                return il["code"], il["name"]
    return None


def ilce_coz(il_kodu: str, *metinler: str) -> tuple[str, str] | None:
    """İl içindeki ilçelerden metinde geçeni bul → (kod, MNG adı). Uzun ad öncelikli
    ("EYÜPSULTAN" → EYÜP; "BURSA YENİŞEHİR" → YENİŞEHİR). 'MERKEZ' yalnız tek başına."""
    ilceler = (veri().get("ilceler") or {}).get(str(il_kodu)) or []
    if not ilceler:
        return None
    sirali = sorted(ilceler, key=lambda d: -len(d["name"]))
    for metin in metinler:
        if not metin:
            continue
        duz = sadelestir(metin)
        sozcukler = set(s for s in _AYRAC.split(duz) if s)
        for d in sirali:
            ad = sadelestir(d["name"])
            if not ad:
                continue
            if ad in _ILCE_GENEL:
                if ad in sozcukler:
                    return d["code"], d["name"]
                continue
            if ad in sozcukler or (len(ad) >= 4 and ad in duz):
                return d["code"], d["name"]
    return None


def alici_tamamla(alici: Alici) -> Alici:
    """İl/ilçe adlarını MNG listesine oturt, kodları doldur (yeni Alici; bulunamazsa olduğu gibi)."""
    il = il_coz(alici.il) or il_coz(alici.ilce) or il_coz(il_bul(alici.adres))
    if not il:
        return alici
    il_kodu, il_adi = il
    ilce = ilce_coz(il_kodu, alici.ilce, alici.adres)
    if ilce:
        return replace(alici, il=il_adi, il_kodu=int(il_kodu), ilce=ilce[1], ilce_kodu=int(ilce[0]))
    return replace(alici, il=il_adi, il_kodu=int(il_kodu))
