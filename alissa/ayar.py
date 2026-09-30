# -*- coding: utf-8 -*-
"""Alissa hesabı sabitleri ve sayfadan değiştirilebilen ayarlar (alissa_ayar tablosu)."""
from datetime import date
from decimal import Decimal, InvalidOperation

from models import db
from .models import AlissaAyar

TEDARIKCI_KODU = 'TED-003'          # products.tedarikci_kodu — Muhammet ALİSSA
BASLANGIC = date(2026, 5, 10)       # ilk senkron buradan başlar (ilk ürün 14 Mayıs 2026'da açıldı)
ORTUSME_GUN = 20                    # her senkron son senkrondan bu kadar geriye tekrar bakar
ESKIME_SAAT = 6                     # sayfa açılınca veri bundan eskiyse otomatik senkron
KILIT_DK = 20                       # 'çalışıyor' durumu bundan eskiyse takılmış sayılır

# Sayfadan değiştirilebilen tutarlar (TL). Değişiklik yalnız SONRAKİ kayıtları etkiler.
VARSAYILAN = {
    'phb_birim': '13.19',           # platform hizmet bedeli, gönderi başı (KDV dahil)
    'siparis_masrafi': '100',       # sipariş başı iç masraf
    'kargo_tahmin': '117.59',       # faturası henüz kesilmemiş kargo için tahmin (2 desi)
}
ETIKET = {
    'phb_birim': 'Platform hizmet bedeli (gönderi başı)',
    'siparis_masrafi': 'Sipariş başı masraf',
    'kargo_tahmin': 'Kargo tahmini (fatura gelene kadar)',
}


def oku(anahtar, varsayilan=None):
    satir = db.session.get(AlissaAyar, anahtar)
    return satir.deger if satir else varsayilan


def yaz(anahtar, deger):
    satir = db.session.get(AlissaAyar, anahtar)
    if satir:
        satir.deger = str(deger)
    else:
        db.session.add(AlissaAyar(anahtar=anahtar, deger=str(deger)))


def tutar(anahtar):
    try:
        return Decimal(oku(anahtar, VARSAYILAN[anahtar]))
    except InvalidOperation:
        return Decimal(VARSAYILAN[anahtar])


def tutarlar():
    return {a: tutar(a) for a in VARSAYILAN}
