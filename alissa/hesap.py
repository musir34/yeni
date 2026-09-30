# -*- coding: utf-8 -*-
"""Alissa defterinden haftalık hesap özeti (salt-okunur hesaplama).

Hafta: Pazartesi 00:00 – Pazar 23:59 (İstanbul). Bir kalem, deftere işlendiği
tarihin haftasına yazılır: satış teslim haftasına, iade iadenin kesildiği haftaya.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from models import db
from .models import AlissaHareket, AlissaOdeme, AlissaSiparis, KARGO_GONDERI, KARGO_IADE

INDIRIM_TURLERI = ('indirim', 'indirim_iptal', 'kupon', 'kupon_iptal')
KARGO_TURLERI = KARGO_GONDERI + KARGO_IADE
TAHMIN_TURLERI = ('kargo_gonderi_tahmin', 'kargo_iade_tahmin')
FARK_TURLERI = ('kargo_gonderi_fark', 'kargo_iade_fark')
KALEMLER = ('satis', 'iade', 'indirim', 'komisyon', 'phb', 'kargo', 'masraf', 'net')
SIFIR = Decimal('0')


def hafta_basi(tarih):
    gun = tarih.date() if isinstance(tarih, datetime) else tarih
    return gun - timedelta(days=gun.weekday())


def _bos():
    ozet = {k: SIFIR for k in KALEMLER}
    ozet.update(satis_adet=0, iade_adet=0, siparisler=set(), tahmin=False, fark=False)
    return ozet


def _isle(ozet, h):
    """Bir defter satırını özet sözlüğüne ekler. Kesintiler pozitif sayı olarak tutulur."""
    ozet['net'] += h.tutar
    ozet['komisyon'] += h.komisyon or SIFIR
    if h.tur == 'satis':
        ozet['satis'] += h.brut
        ozet['satis_adet'] += h.adet
        ozet['siparisler'].add(h.order_number)
    elif h.tur == 'iade':
        ozet['iade'] -= h.brut
        ozet['iade_adet'] += h.adet
    elif h.tur in INDIRIM_TURLERI:
        ozet['indirim'] -= h.brut
    elif h.tur == 'phb':
        ozet['phb'] -= h.tutar
    elif h.tur == 'masraf':
        ozet['masraf'] -= h.tutar
    elif h.tur in KARGO_TURLERI:
        ozet['kargo'] -= h.tutar
        ozet['tahmin'] = ozet['tahmin'] or h.tur in TAHMIN_TURLERI
        ozet['fark'] = ozet['fark'] or h.tur in FARK_TURLERI


def _bitir(ozet):
    ozet['siparis'] = len(ozet.pop('siparisler'))
    return ozet


def haftalik(bugun):
    """Haftalar (yeniden eskiye) + genel toplam + ödeme bakiyesi."""
    haftalar = defaultdict(_bos)
    toplam = _bos()
    for h in AlissaHareket.query:
        _isle(haftalar[hafta_basi(h.islem_tarihi)], h)
        _isle(toplam, h)

    gelen = defaultdict(lambda: {'gelen': set(), 'iptal': set()})
    yolda = set()
    for s in AlissaSiparis.query:
        if not s.siparis_tarihi:
            continue
        kova = gelen[hafta_basi(s.siparis_tarihi)]
        kova['gelen'].add(s.order_number)
        if s.statu == 'Cancelled':
            kova['iptal'].add(s.order_number)
        elif s.statu not in ('Delivered', 'UnDelivered', 'UnDeliveredAndReturned', 'Returned'):
            yolda.add(s.order_number)

    bu_hafta = hafta_basi(bugun)
    liste = []
    for bas in sorted(set(haftalar) | set(gelen), reverse=True):
        ozet = _bitir(haftalar[bas])
        ozet.update(bas=bas, son=bas + timedelta(days=6), suruyor=bas == bu_hafta,
                    gelen=len(gelen[bas]['gelen']), iptal=len(gelen[bas]['iptal']))
        liste.append(ozet)

    odenen = (db.session.query(db.func.coalesce(db.func.sum(AlissaOdeme.tutar), 0))
              .filter(AlissaOdeme.iptal.is_(False)).scalar())
    odenen = Decimal(str(odenen))
    toplam = _bitir(toplam)
    return {'haftalar': liste, 'toplam': toplam, 'odenen': odenen,
            'bakiye': toplam['net'] - odenen, 'yolda': len(yolda)}


def hafta_detay(bas):
    """Seçilen haftanın sipariş bazlı dökümü."""
    bas_dt = datetime.combine(bas, datetime.min.time())
    satirlar = (AlissaHareket.query
                .filter(AlissaHareket.islem_tarihi >= bas_dt,
                        AlissaHareket.islem_tarihi < bas_dt + timedelta(days=7))
                .order_by(AlissaHareket.islem_tarihi))
    siparisler = {}
    for h in satirlar:
        ozet = siparisler.get(h.order_number)
        if ozet is None:
            ozet = siparisler[h.order_number] = _bos()
            ozet.update(order_number=h.order_number, modeller=set(), tarih=h.islem_tarihi)
        if h.model_kodu:
            ozet['modeller'].add(h.model_kodu)
        _isle(ozet, h)
    liste = []
    for ozet in siparisler.values():
        ozet.pop('siparisler')
        ozet['modeller'] = ', '.join(sorted(ozet['modeller']))
        # Bu hafta satışı yok ama iadesi/farkı var: önceki haftaların siparişi
        ozet['onceki'] = ozet['satis_adet'] == 0
        liste.append(ozet)
    return sorted(liste, key=lambda o: (o['onceki'], o['tarih']))


def model_ozet():
    modeller = defaultdict(_bos)
    for h in AlissaHareket.query:
        _isle(modeller[h.model_kodu or '—'], h)
    liste = []
    for kod in sorted(modeller):
        ozet = _bitir(modeller[kod])
        ozet['model'] = kod
        liste.append(ozet)
    return liste


def odemeler():
    return AlissaOdeme.query.order_by(AlissaOdeme.tarih.desc(), AlissaOdeme.id.desc()).all()
