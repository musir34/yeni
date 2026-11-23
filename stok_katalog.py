"""
Ürün listesi "Stok Kataloğu (PDF)".

Komutan kararı (2026-11-23): eritme gruplarındaki (Ağır Giden / Çok Satan) modeller
için model → renk satırı (görsel + beden/stok ızgarası) PDF kataloğu. Düzen,
2026-11-23'te CSV'den üretilip beğenilen reportlab kataloğunun birebir taşınmasıdır.
Stok central_stock'tan canlı okunur; model listeleri eritme_gorevi.py'den gelir.
Görseller yalnız yerel static/ altından okunur (http indirme yok), küçültülmüş
kopyalar instance/katalog_cache/ altında tutulur.
"""
import hashlib
import json
import logging
import os
from collections import OrderedDict
from datetime import datetime
from io import BytesIO

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from eritme_gorevi import AGIR_GIDEN_MODELLER, COK_SATAN_MODELLER
from time_utils import IST

logger = logging.getLogger(__name__)

GRUPLAR = {
    'agir_giden': ("Ağır Giden Modeller", AGIR_GIDEN_MODELLER),
    'cok_satan': ("Çok Satan Modeller", COK_SATAN_MODELLER),
}

_FONT_DIZINI = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'fonts')
F, FB = "DejaVuSans", "DejaVuSans-Bold"


def _font_kaydet() -> None:
    """DejaVu fontlarını bir kez kaydeder (Türkçe karakter desteği)."""
    kayitli = pdfmetrics.getRegisteredFontNames()
    for ad in (F, FB):
        if ad not in kayitli:
            pdfmetrics.registerFont(TTFont(ad, os.path.join(_FONT_DIZINI, f"{ad}.ttf")))


_font_kaydet()

MARKA = colors.HexColor("#8B1E3F")
GRI = colors.HexColor("#F3F1F2")
W, H = A4
M = 12 * mm
SATIR_H = 27 * mm
IMG = 24 * mm
HUCRE_W = 11.5 * mm


# ---------------------------------------------------------------- veri

def ilk_url(v: str | None) -> str | None:
    """images alanından ilk görsel değeri (JSON liste / virgüllü / tek değer)."""
    v = (v or "").strip()
    if not v:
        return None
    if v.startswith("["):
        try:
            lst = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return None
        if not lst:
            return None
        x = lst[0]
        return x.get("url") if isinstance(x, dict) else str(x)
    return v.split(",")[0].strip() or None


def yerel_gorsel_yolu(deger: str | None, static_kok: str) -> str | None:
    """'/static/images/x.jpg' → diskteki mutlak yol; http, static dışı veya yoksa None."""
    if not deger or deger.startswith(("http://", "https://", "//")):
        return None
    yol = deger.split("?")[0].lstrip("/")
    if not yol.startswith("static/"):
        return None
    kok = os.path.realpath(static_kok)
    tam = os.path.realpath(os.path.join(kok, yol[len("static/"):]))
    if os.path.commonpath([kok, tam]) != kok or tam == kok:
        logger.warning("Katalog: static dışına çıkan görsel yolu reddedildi: %s", deger)
        return None
    return tam if os.path.isfile(tam) else None


def beden_anahtar(b: str) -> tuple:
    try:
        return (0, float(b.replace(",", ".")))
    except ValueError:
        return (1, b)


def _ham_satirlar(modeller: list[str]) -> list[tuple]:
    from models import db, Product, CentralStock
    return (db.session.query(Product.product_main_id, Product.title, Product.color,
                             Product.size, Product.images, CentralStock.qty)
            .join(CentralStock, CentralStock.barcode == Product.barcode)
            .filter(Product.product_main_id.in_(modeller))
            .order_by(Product.product_main_id, Product.color, Product.size, Product.barcode)
            .all())


def _topla(satirlar: list[tuple], static_kok: str) -> dict:
    """Model → renk → beden stok toplamı; renk başına diskte var olan ilk görsel."""
    ham: dict = {}
    for model, baslik, renk, beden, images, qty in satirlar:
        m = ham.setdefault(model, {"baslik": "", "renkler": OrderedDict()})
        if not m["baslik"] and baslik:
            m["baslik"] = baslik
        rk = m["renkler"].setdefault((renk or "").strip() or "-", {"gorsel": None, "bedenler": {}})
        if rk["gorsel"] is None:
            rk["gorsel"] = yerel_gorsel_yolu(ilk_url(images), static_kok)
        b = (beden or "").strip() or "-"
        rk["bedenler"][b] = rk["bedenler"].get(b, 0) + int(qty or 0)
    return ham


def katalog_verisi(modeller: list[str], alt_sinir: int, static_kok: str | None = None) -> OrderedDict:
    """Katalog verisi (model sırası verilen liste sırası).

    Stoğu ≤0 beden satırı yazılmaz; model toplamı ≤ alt_sinir olan model çıkarılır."""
    if static_kok is None:
        from flask import current_app
        static_kok = os.path.join(current_app.root_path, 'static')
    ham = _topla(_ham_satirlar(modeller), static_kok)
    sonuc = OrderedDict()
    for kod in modeller:
        m = ham.get(kod)
        if not m:
            continue
        renkler = OrderedDict()
        for renk, rk in m["renkler"].items():
            bedenler = sorted(((b, s) for b, s in rk["bedenler"].items() if s > 0),
                              key=lambda x: beden_anahtar(x[0]))
            if bedenler:
                renkler[renk] = {"gorsel": rk["gorsel"], "bedenler": bedenler}
        if sum(s for rk in renkler.values() for _, s in rk["bedenler"]) > alt_sinir:
            sonuc[kod] = {"baslik": m["baslik"], "renkler": renkler}
    return sonuc


# ---------------------------------------------------------------- görsel

def kucuk_gorsel(yol: str | None, onbellek: str) -> str | None:
    """Görselin 300x300 JPEG kopyası (önbellekte md5(yol+mtime) adlı); hata → None."""
    if not yol:
        return None
    try:
        anahtar = f"{yol}{os.path.getmtime(yol)}"
        hedef = os.path.join(onbellek, hashlib.md5(anahtar.encode()).hexdigest() + ".jpg")
        if not os.path.exists(hedef):
            os.makedirs(onbellek, exist_ok=True)
            with Image.open(yol) as im:
                im = im.convert("RGB")
                im.thumbnail((300, 300))
                im.save(hedef, "JPEG", quality=80)
        return hedef
    except Exception as e:
        logger.warning("Katalog görseli hazırlanamadı (%s): %s", yol, e)
        return None


# ---------------------------------------------------------------- PDF

def kisalt(c: canvas.Canvas, metin: str, font: str, boy: float, gen: float) -> str:
    while metin and c.stringWidth(metin, font, boy) > gen:
        metin = metin[:-2]
    return metin


def _stok(m: dict) -> int:
    return sum(s for rk in m["renkler"].values() for _, s in rk["bedenler"])


class Katalog:
    def __init__(self, cikti: BytesIO, modeller: dict, gorseller: dict, baslik: str):
        self.c = canvas.Canvas(cikti, pagesize=A4)
        self.c.setTitle(f"Güllü Shoes — {baslik} Kataloğu")
        self.mod, self.gor, self.baslik = modeller, gorseller, baslik
        self.tarih = datetime.now(IST).strftime("%d.%m.%Y")
        self.sayfa = 0

    def alt_bilgi(self) -> None:
        self.sayfa += 1
        c = self.c
        c.setFont(F, 7.5); c.setFillColor(colors.grey)
        c.drawString(M, 7 * mm, f"Güllü Shoes · {self.baslik} · {self.tarih}")
        c.drawRightString(W - M, 7 * mm, f"Sayfa {self.sayfa}")

    def yeni_sayfa(self) -> float:
        self.alt_bilgi(); self.c.showPage()
        return H - M

    def kapak(self) -> None:
        c = self.c
        toplam = sum(_stok(m) for m in self.mod.values())
        renk_say = sum(len(m["renkler"]) for m in self.mod.values())
        c.setFillColor(MARKA); c.rect(0, H - 95 * mm, W, 95 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(FB, 30); c.drawCentredString(W / 2, H - 50 * mm, "GÜLLÜ SHOES")
        c.setFont(F, 16); c.drawCentredString(W / 2, H - 65 * mm, f"{self.baslik} Kataloğu")
        c.setFont(F, 11); c.drawCentredString(W / 2, H - 78 * mm, f"Stok tarihi: {self.tarih}")
        c.setFillColor(colors.black)
        y = H - 120 * mm
        for et, v in (("Model", len(self.mod)), ("Renk", renk_say),
                      ("Toplam stok (çift)", f"{toplam:,}".replace(",", "."))):
            c.setFont(F, 12); c.drawString(60 * mm, y, et)
            c.setFont(FB, 12); c.drawRightString(W - 60 * mm, y, str(v)); y -= 9 * mm
        self.model_dizini(y - 6 * mm)
        self.yeni_sayfa()

    def model_dizini(self, y: float) -> None:
        c = self.c
        c.setFont(FB, 10); c.drawString(M, y, "Model dizini (stok):"); y -= 6 * mm
        c.setFont(F, 8)
        kol = 5
        kw = (W - 2 * M) / kol
        for i, (kod, m) in enumerate(self.mod.items()):
            c.drawString(M + (i % kol) * kw, y, f"{kod} — {_stok(m)}")
            if i % kol == kol - 1:
                y -= 4.6 * mm
                if y < 15 * mm:
                    self.yeni_sayfa(); y = H - M; c.setFont(F, 8)

    def model_basligi(self, y: float, kod: str, m: dict) -> float:
        c = self.c
        c.setFillColor(MARKA); c.roundRect(M, y - 9 * mm, W - 2 * M, 9 * mm, 2 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont(FB, 12)
        c.drawString(M + 3 * mm, y - 6.3 * mm, f"Model {kod}")
        bx = M + 3 * mm + c.stringWidth(f"Model {kod}", FB, 12) + 5 * mm
        c.setFont(F, 9)
        c.drawString(bx, y - 6.1 * mm, kisalt(c, m["baslik"] or "", F, 9, W - M - 40 * mm - bx))
        c.setFont(FB, 10); c.drawRightString(W - M - 3 * mm, y - 6.3 * mm, f"Toplam: {_stok(m)} çift")
        return y - 11 * mm

    def gorsel_ciz(self, y: float, yuk: float, gorsel: str | None) -> None:
        c = self.c
        yol = self.gor.get(gorsel)
        ix, iy = M + 2 * mm, y - yuk + 1 * mm
        if yol:
            ir = ImageReader(yol)
            iw, ih = ir.getSize(); o = min(IMG / iw, (yuk - 4 * mm) / ih)
            c.drawImage(ir, ix + (IMG - iw * o) / 2, iy + (yuk - 3.5 * mm - ih * o) / 2, iw * o, ih * o)
        else:
            c.setFillColor(colors.white); c.rect(ix, iy + 1 * mm, IMG, yuk - 5 * mm, fill=1, stroke=0)
            c.setFillColor(colors.grey); c.setFont(F, 7)
            c.drawCentredString(ix + IMG / 2, iy + yuk / 2 - 2 * mm, "görsel yok")

    def beden_kutusu(self, cx: float, cy: float, b: str, s: int) -> None:
        c = self.c
        c.setStrokeColor(colors.HexColor("#CCCCCC")); c.setFillColor(colors.white)
        c.rect(cx, cy - 10 * mm, HUCRE_W - 1 * mm, 10 * mm, fill=1, stroke=1)
        c.setFillColor(MARKA); c.rect(cx, cy - 4.5 * mm, HUCRE_W - 1 * mm, 4.5 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont(FB, 8)
        c.drawCentredString(cx + (HUCRE_W - 1 * mm) / 2, cy - 3.4 * mm, b)
        c.setFillColor(colors.black); c.setFont(FB, 10)
        c.drawCentredString(cx + (HUCRE_W - 1 * mm) / 2, cy - 8.7 * mm, str(s))

    def renk_satiri(self, y: float, renk: str, rk: dict) -> float:
        c = self.c
        sag_alan = W - 2 * M - IMG - 6 * mm
        per_satir = max(1, int(sag_alan // HUCRE_W))
        bedenler = rk["bedenler"]
        satir_say = (len(bedenler) + per_satir - 1) // per_satir
        yuk = max(SATIR_H, 12 * mm + satir_say * 12 * mm)
        c.setFillColor(GRI); c.roundRect(M, y - yuk, W - 2 * M, yuk - 1.5 * mm, 2 * mm, fill=1, stroke=0)
        self.gorsel_ciz(y, yuk, rk["gorsel"])
        x0 = M + IMG + 5 * mm
        c.setFillColor(colors.black); c.setFont(FB, 10.5)
        c.drawString(x0, y - 7 * mm, kisalt(c, renk, FB, 10.5, sag_alan - 30 * mm))
        c.setFont(F, 9); c.drawRightString(W - M - 3 * mm, y - 7 * mm, f"{sum(s for _, s in bedenler)} çift")
        for i, (b, s) in enumerate(bedenler):
            self.beden_kutusu(x0 + (i % per_satir) * HUCRE_W, y - 12 * mm - (i // per_satir) * 12 * mm, b, s)
        return y - yuk

    def olustur(self) -> None:
        self.kapak()
        y = H - M
        for kod, m in self.mod.items():
            if y - 11 * mm - SATIR_H < 14 * mm:
                y = self.yeni_sayfa()
            y = self.model_basligi(y, kod, m)
            for renk, rk in m["renkler"].items():
                if y - SATIR_H < 14 * mm:
                    y = self.yeni_sayfa()
                    y = self.model_basligi(y, kod + " (devam)", m)
                y = self.renk_satiri(y, renk, rk)
            y -= 4 * mm
        self.alt_bilgi(); self.c.save()


def katalog_pdf(veri: dict, baslik: str, onbellek: str | None = None) -> BytesIO:
    """Katalog PDF'i (BytesIO). onbellek verilmezse instance/katalog_cache/ kullanılır."""
    if onbellek is None:
        from flask import current_app
        onbellek = os.path.join(current_app.instance_path, 'katalog_cache')
    os.makedirs(onbellek, exist_ok=True)
    yollar = {rk["gorsel"] for m in veri.values() for rk in m["renkler"].values() if rk["gorsel"]}
    gorseller = {y: kucuk_gorsel(y, onbellek) for y in yollar}
    cikti = BytesIO()
    Katalog(cikti, veri, gorseller, baslik).olustur()
    cikti.seek(0)
    return cikti
