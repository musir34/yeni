"""MNG ZPL → SVG dönüştürücü — saf testler (canlı etiketin ZPL alt kümesi, ağ yok).

Çalıştırma: DISABLE_JOBS=1 python -m pytest tests/test_zpl_svg.py --noconftest -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mng_kargo.zpl_svg import Code128, DataMatrix, Kutu, Metin, hex_coz, parse, zpl_to_svg  # noqa: E402

ZPL = """^XA
^MMT
^CI28
^PW831
^LL0959
^FT654,45^A0N,23,25^FH^FDDHL^FS
; Var_C4_b1_C5_9f _C5_9eube
^FT748,53^A0R,62,62^FH^FDSAMYEL_C4_b0 HUB^FS
^FO483,20^GB171,27,2^FS
^FO597,23^GB0,556,2^FS
^FT602,450^A0R,17,19^FH^FD^FXTEL:0000000000^FS
^FT533,49^A0R,17,16^FH^FDTEST MAH. [KADIK_C3_96Y/_C4_b0STANBUL]^FS
^BY3,3,259^FT147,30^BCR,,N,N
;^FD>:D@53BH21RZ13CKAAA6J^FS
^BY126,126^FT567,617^BXI,7,200,0,0,1,~
^FH^FDD@53BH21RZ13CKAAA6J^FS
^BY2,3,90^FT25,30^BCR,,Y,N
^FD>:^FS
^FT130,13^A0R,14,14^FH^FDsetno:68 ^FS
^PQ1,0,1,Y^XZ"""


def test_hex_coz_utf8():
    assert hex_coz("SAMYEL_C4_b0 HUB") == "SAMYELİ HUB"
    assert hex_coz("KADIK_C3_96Y") == "KADIKÖY"


def test_parse_ogeler():
    e = parse(ZPL)
    assert (e.genislik, e.yukseklik) == (831, 959)
    metinler = [o for o in e.ogeler if isinstance(o, Metin)]
    assert [m.metin for m in metinler] == ["DHL", "SAMYELİ HUB", "TEST MAH. [KADIKÖY/İSTANBUL]", "setno:68"]
    assert metinler[1].dondur and metinler[1].h == 62 and (metinler[1].x, metinler[1].y) == (748, 53)
    assert not metinler[0].dondur and metinler[0].w == 25
    kutular = [o for o in e.ogeler if isinstance(o, Kutu)]
    assert kutular[0] == Kutu(483, 20, 171, 27, 2) and kutular[1].w == 0
    barkod = [o for o in e.ogeler if isinstance(o, Code128)]
    assert barkod == [Code128(147, 30, 3, 259, True, "D@53BH21RZ13CKAAA6J")]   # ';' ve '>:' atıldı, boş olan yok
    dm = [o for o in e.ogeler if isinstance(o, DataMatrix)]
    assert dm == [DataMatrix(567, 617, 7, "D@53BH21RZ13CKAAA6J")]


def test_fx_yorum_basilmaz():
    assert "TEL:0000000000" not in zpl_to_svg(ZPL)


def test_svg_ciktisi():
    svg = zpl_to_svg(ZPL)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "SAMYELİ HUB" in svg and 'rotate(90 748 53)' in svg
    assert svg.count("<rect") > 60                      # Code128 çubukları + DataMatrix modülleri + kutular
    assert 'stroke-width="2"' in svg
    assert "viewBox=" in svg and "mm\"" in svg


def test_kirpma_viewbox_icerige_oturur():
    tam = zpl_to_svg(ZPL, kirp=False)
    kirpik = zpl_to_svg(ZPL)
    assert 'viewBox="0 0 831 959"' in tam and 'viewBox="0 0 831 959"' not in kirpik
