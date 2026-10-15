"""MNG'nin döndürdüğü ZPL etiketi yazdırılabilir görüntüye çevirme.

MNG createbarcode cevabı Zebra ZPL verir (^PW831 ^LL959 → 203 dpi'da ≈ 104 x 120 mm).
Depodaki yazıcı ZPL konuşmuyorsa, Labelary servisi ZPL'i PNG'ye çevirir; sayfa o görüntüyü
104x120 mm olarak basar. MNG uyarısı: konveyör okuması için 10x10 rulo MNG'den ya da lamine olmalı.

Labelary dış servis (ücretsiz, saniyede ~5 istek). Hata olursa None döner, sayfa ZPL indirme
bağlantısı ve klasik Code128 etikete yönlendirme gösterir.
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections import OrderedDict

import requests

logger = logging.getLogger(__name__)

LABELARY_URL = "https://api.labelary.com/v1/printers/8dpmm/labels/{en}x{boy}/0/"
DPMM = 8                       # 203 dpi
ZAMAN_ASIMI = (5, 20)
_ONBELLEK: "OrderedDict[str, bytes]" = OrderedDict()
_ONBELLEK_BOYUT = 200


def zpl_boyut_inch(zpl: str) -> tuple[float, float]:
    """^PW (genişlik dot) ve ^LL (uzunluk dot) → inç; yoksa MNG etiketi (831x959)."""
    pw = re.search(r"\^PW(\d+)", zpl or "")
    ll = re.search(r"\^LL0*(\d+)", zpl or "")
    en = int(pw.group(1)) if pw else 831
    boy = int(ll.group(1)) if ll else 959
    return round(en / (DPMM * 25.4), 2), round(boy / (DPMM * 25.4), 2)


def zpl_boyut_mm(zpl: str) -> tuple[int, int]:
    en, boy = zpl_boyut_inch(zpl)
    return round(en * 25.4), round(boy * 25.4)


def zpl_png(zpl: str) -> bytes | None:
    """ZPL → PNG (Labelary). Aynı ZPL için bellek önbelleği."""
    if not zpl:
        return None
    anahtar = hashlib.sha1(zpl.encode("utf-8")).hexdigest()
    if anahtar in _ONBELLEK:
        _ONBELLEK.move_to_end(anahtar)
        return _ONBELLEK[anahtar]
    en, boy = zpl_boyut_inch(zpl)
    try:
        r = requests.post(LABELARY_URL.format(en=en, boy=boy), data=zpl.encode("utf-8"),
                          headers={"Accept": "image/png", "Content-Type": "application/x-www-form-urlencoded"},
                          timeout=ZAMAN_ASIMI)
    except requests.RequestException as exc:
        logger.warning("[MNG] Labelary ulaşılamadı: %s", exc)
        return None
    if r.status_code != 200 or not r.content:
        logger.warning("[MNG] Labelary HTTP %s: %s", r.status_code, r.text[:200])
        return None
    _ONBELLEK[anahtar] = r.content
    if len(_ONBELLEK) > _ONBELLEK_BOYUT:
        _ONBELLEK.popitem(last=False)
    return r.content
