"""MNG ZPL etiketi → SVG (vektör). Termal yazıcıda PNG pürüzlü çıkıyor; sipariş hazırla etiketi
gibi vektör basılsın diye ZPL'deki öğeler doğrudan SVG'ye çizilir, dış servis gerekmez.

MNG etiketinde kullanılan ZPL alt kümesi (canlı etiket 2026-10-15'ten):
  ^PW/^LL        etiket boyutu (dot; 8 dot = 1 mm)
  ^FTx,y         alan başlangıcı (metin: taban çizgisi sol; döndürülmüşte taban çizgisi x, metin aşağı akar)
  ^FOx,y + ^GBw,h,t   kutu / çizgi (sol-üst köşe)
  ^A0N,h,w / ^A0R,h,w  font 0, normal / 90° saat yönü döndürülmüş, h yükseklik w genişlik (dot)
  ^FH + ^FD..._HH..^FS  hex kaçışlı (UTF-8, ^CI28) metin; ^FX alan içi yorum (basılmaz)
  ^BYm,r,h + ^BCo,h,f,g + ^FD   Code 128 (">:" ">;" ">9" alt küme çağrıları atılır)
  ^BYm + ^BXo,h,q,... + ^FD     DataMatrix ECC200 (pystrich, saf Python)
Satır başındaki ';' yorumları komut dışı metindir, atlanır. Bilinmeyen komutlar yok sayılır.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from html import escape

logger = logging.getLogger(__name__)

DOT_MM = 8                       # 203 dpi
KOMUT = re.compile(r"[\^~]([A-Z][A-Z0-9])")
HEX_KACIS = re.compile(r"_([0-9A-Fa-f]{2})")
ALT_KUME = re.compile(r"^>[:;9]")
FONT_AILE = "Arial Narrow, Arial, Helvetica, sans-serif"


@dataclass(frozen=True)
class Metin:
    x: int
    y: int
    h: int
    w: int
    dondur: bool          # ^A0R
    metin: str


@dataclass(frozen=True)
class Kutu:
    x: int
    y: int
    w: int
    h: int
    t: int


@dataclass(frozen=True)
class Code128:
    x: int
    y: int
    modul: int            # ^BY m
    yukseklik: int        # çubuk yüksekliği (dot)
    dondur: bool          # ^BCR
    veri: str


@dataclass(frozen=True)
class DataMatrix:
    x: int
    y: int
    modul: int            # ^BX h (dot / modül)
    veri: str


@dataclass
class Etiket:
    genislik: int = 831
    yukseklik: int = 959
    ogeler: list = field(default_factory=list)


def hex_coz(metin: str) -> str:
    """^FH: _HH → bayt; UTF-8 (^CI28)."""
    def _parca(m):
        return bytes([int(m.group(1), 16)]).decode("latin-1")
    ham = HEX_KACIS.sub(_parca, metin).encode("latin-1", errors="replace")
    return ham.decode("utf-8", errors="replace")


def _sayi(deger: str, varsayilan: int = 0) -> int:
    try:
        return int(float(deger.strip()))
    except (TypeError, ValueError, AttributeError):
        return varsayilan


def parse(zpl: str) -> Etiket:
    etiket = Etiket()
    komutlar = [(m.group(1), m.start(), m.end()) for m in KOMUT.finditer(zpl)]
    durum = {"x": 0, "y": 0, "font_h": 20, "font_w": 20, "dondur": False, "hex": False,
             "by_m": 2, "by_h": 10, "barkod": None, "bx_h": 7}
    for i, (ad, _, bitis) in enumerate(komutlar):
        son = komutlar[i + 1][1] if i + 1 < len(komutlar) else len(zpl)
        param = zpl[bitis:son]
        p = [s.strip() for s in param.split(",")]
        if ad == "PW":
            etiket.genislik = _sayi(p[0], 831)
        elif ad == "LL":
            etiket.yukseklik = _sayi(p[0], 959)
        elif ad in ("FT", "FO"):
            durum["x"], durum["y"] = _sayi(p[0]), _sayi(p[1] if len(p) > 1 else "0")
            durum["hex"] = False
            durum["barkod"] = None
        elif ad == "A0":
            yon = p[0][:1] if p else "N"
            durum["dondur"] = yon == "R"
            durum["font_h"] = _sayi(p[1] if len(p) > 1 else "20", 20)
            durum["font_w"] = _sayi(p[2] if len(p) > 2 else "0", 0) or durum["font_h"]
        elif ad == "GB":
            etiket.ogeler.append(Kutu(durum["x"], durum["y"], _sayi(p[0]), _sayi(p[1] if len(p) > 1 else "0"),
                                      max(1, _sayi(p[2] if len(p) > 2 else "1", 1))))
        elif ad == "BY":
            durum["by_m"] = max(1, _sayi(p[0], 2))
            if len(p) > 2:
                durum["by_h"] = _sayi(p[2], 10)
        elif ad == "BC":
            durum["barkod"] = ("BC", (p[0][:1] if p and p[0] else "N") == "R",
                               _sayi(p[1] if len(p) > 1 else "", 0) or durum["by_h"])
        elif ad == "BX":
            durum["barkod"] = ("BX", False, _sayi(p[1] if len(p) > 1 else "7", 7))
        elif ad == "FH":
            durum["hex"] = True
        elif ad == "FD":
            veri = param.split("^FX")[0] if "^FX" in param else param
            veri = veri.strip("\r\n")
            if durum["hex"]:
                veri = hex_coz(veri)
            barkod = durum["barkod"]
            if barkod:
                veri = ALT_KUME.sub("", veri.strip())
                if veri:
                    if barkod[0] == "BC":
                        etiket.ogeler.append(Code128(durum["x"], durum["y"], durum["by_m"], barkod[2], barkod[1], veri))
                    else:
                        etiket.ogeler.append(DataMatrix(durum["x"], durum["y"], barkod[2], veri))
                durum["barkod"] = None
            elif veri.strip():
                etiket.ogeler.append(Metin(durum["x"], durum["y"], durum["font_h"], durum["font_w"],
                                           durum["dondur"], veri.strip()))
        elif ad == "FS":
            durum["hex"] = False
    return etiket


# ---------------------------------------------------------------- çizim
def _code128_desen(veri: str) -> str:
    from barcode import get as get_barcode
    from barcode.writer import SVGWriter
    return "".join(get_barcode("code128", veri, writer=SVGWriter()).build())


def _datamatrix(veri: str) -> list[list[int]] | None:
    try:
        from pystrich.datamatrix import DataMatrixEncoder
    except ImportError:
        logger.warning("[MNG] pystrich yok, DataMatrix çizilmedi")
        return None
    return DataMatrixEncoder(veri).matrix


def _metin_svg(m: Metin) -> str:
    sx = round(m.w / m.h, 3) if m.h and m.w and m.w != m.h else 1
    donusum = f"rotate(90 {m.x} {m.y})" if m.dondur else ""
    if sx != 1:
        donusum += f" translate({m.x} {m.y}) scale({sx} 1) translate({-m.x} {-m.y})"
    attr = f' transform="{donusum.strip()}"' if donusum.strip() else ""
    return (f'<text x="{m.x}" y="{m.y}" font-size="{m.h}" font-family="{FONT_AILE}" font-weight="bold"'
            f'{attr}>{escape(m.metin)}</text>')


def _kutu_svg(k: Kutu) -> str:
    if k.w == 0 or k.h == 0:          # çizgi
        return f'<rect x="{k.x}" y="{k.y}" width="{max(k.w, k.t)}" height="{max(k.h, k.t)}" fill="#000"/>'
    return (f'<rect x="{k.x + k.t / 2}" y="{k.y + k.t / 2}" width="{k.w - k.t}" height="{k.h - k.t}" '
            f'fill="none" stroke="#000" stroke-width="{k.t}"/>')


def _code128_svg(b: Code128) -> str:
    desen = _code128_desen(b.veri)
    parcalar = []
    konum = 0
    for ch in desen:
        if ch == "1":
            if b.dondur:     # çubuklar yatay, aşağı doğru dizilir; yükseklik +x yönünde
                parcalar.append(f'<rect x="{b.x}" y="{b.y + konum}" width="{b.yukseklik}" height="{b.modul}"/>')
            else:            # taban çizgisi y, çubuklar yukarı
                parcalar.append(f'<rect x="{b.x + konum}" y="{b.y - b.yukseklik}" width="{b.modul}" height="{b.yukseklik}"/>')
        konum += b.modul
    return f'<g fill="#000">{"".join(parcalar)}</g>'


def _datamatrix_svg(d: DataMatrix) -> str:
    matris = _datamatrix(d.veri)
    if not matris:
        return ""
    n = len(matris)
    boyut = n * d.modul
    # ^BXI (180° ters): simge x'ten sola, y'den aşağı yerleşir (canlı etiketle aynı konum)
    x0, y0 = d.x - boyut, d.y
    parcalar = []
    for r, satir in enumerate(matris):
        for c, dolu in enumerate(satir):
            if dolu:
                rr, cc = n - 1 - r, n - 1 - c
                parcalar.append(f'<rect x="{x0 + cc * d.modul}" y="{y0 + rr * d.modul}" width="{d.modul}" height="{d.modul}"/>')
    return f'<g fill="#000" shape-rendering="crispEdges">{"".join(parcalar)}</g>'


def _bbox(e: Etiket) -> tuple[int, int, int, int]:
    """İçerik kutusu (dot) — boş kenarlar atılır, 100x100 ruloya sığdırılır."""
    xs, ys = [], []
    for o in e.ogeler:
        if isinstance(o, Metin):
            uzunluk = int(len(o.metin) * o.w * 0.6) + 4
            if o.dondur:
                xs += [o.x, o.x + o.h]; ys += [o.y, o.y + uzunluk]
            else:
                xs += [o.x, o.x + uzunluk]; ys += [o.y - o.h, o.y]
        elif isinstance(o, Kutu):
            xs += [o.x, o.x + max(o.w, o.t)]; ys += [o.y, o.y + max(o.h, o.t)]
        elif isinstance(o, Code128):
            uzunluk = len(_code128_desen(o.veri)) * o.modul
            if o.dondur:
                xs += [o.x, o.x + o.yukseklik]; ys += [o.y, o.y + uzunluk]
            else:
                xs += [o.x, o.x + uzunluk]; ys += [o.y - o.yukseklik, o.y]
        elif isinstance(o, DataMatrix):
            boyut = 24 * o.modul
            xs += [o.x - boyut, o.x]; ys += [o.y, o.y + boyut]
    if not xs:
        return 0, 0, e.genislik, e.yukseklik
    kenar = 10
    x0, y0 = max(0, min(xs) - kenar), max(0, min(ys) - kenar)
    x1, y1 = min(e.genislik, max(xs) + kenar), min(e.yukseklik, max(ys) + kenar)
    return x0, y0, x1, y1


def zpl_to_svg(zpl: str, kirp: bool = True) -> str:
    """ZPL → tek SVG (viewBox dot cinsinden; width/height mm). Bilinmeyen öğeler atlanır."""
    e = parse(zpl)
    govde = []
    for o in e.ogeler:
        if isinstance(o, Metin):
            govde.append(_metin_svg(o))
        elif isinstance(o, Kutu):
            govde.append(_kutu_svg(o))
        elif isinstance(o, Code128):
            govde.append(_code128_svg(o))
        elif isinstance(o, DataMatrix):
            govde.append(_datamatrix_svg(o))
    x0, y0, x1, y1 = _bbox(e) if kirp else (0, 0, e.genislik, e.yukseklik)
    w, h = x1 - x0, y1 - y0
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {y0} {w} {h}" '
            f'width="{w / DOT_MM:.1f}mm" height="{h / DOT_MM:.1f}mm" preserveAspectRatio="xMidYMid meet">'
            f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#fff"/>{"".join(govde)}</svg>')
