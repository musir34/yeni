# -*- coding: utf-8 -*-
"""Trendyol → alissa_* tabloları. Tekrar çalıştırılabilir (idempotent), yalnız ekler.

Hesap kuralları (2026-09-30, Komutan kararı):
- Bir satış, Trendyol'un satış kaydını kestiği an (= teslim anı) hesaba girer.
- Hakediş = satış − iade − indirim/kupon − komisyon (Trendyol'un sellerRevenue'su).
- Ayrıca düşülür: platform hizmet bedeli (paket başı), sipariş başı masraf, gönderi ve iade kargosu.
- Karma siparişte (Alissa + başka ürün) paket/sipariş başı kalemler adet oranında paylaştırılır.
- Kargo faturası 4-6 hafta gecikir: önce tahmin yazılır, fatura gelince FARK faturanın
  geldiği haftaya işlenir (geçmiş haftaların rakamı değişmez).
"""
import json
import logging
import threading
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.exc import IntegrityError

from models import db, Product
from . import ayar
from .models import (AlissaAyar, AlissaHareket, AlissaKargoKalem, AlissaSiparis,
                     FINANS_TURLERI, KARGO_GONDERI, KARGO_IADE)
from .trendyol import Istemci, KARGO_TIPLERI, utc_ms_ist, duvar_ms_ist

logger = logging.getLogger(__name__)

ISARET = {'satis': 1, 'iade': -1, 'indirim': -1, 'indirim_iptal': 1, 'kupon': -1, 'kupon_iptal': 1}
SIPARIS_GERI_GUN = 90   # sipariş v2 daha eskisini vermiyor
KURUS = Decimal('0.01')


class SenkronHata(Exception):
    pass


def simdi_ist():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=3)


def _d(deger):
    return Decimal(str(deger or 0))


def _k(deger):
    return Decimal(deger).quantize(KURUS, rounding=ROUND_HALF_UP)


def _pay(adet, toplam):
    """Karma siparişte Alissa payı; kolon hassasiyetine (4 hane) yuvarlanır."""
    return (Decimal(adet) / Decimal(toplam)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def _parcala(liste, boy=500):
    for i in range(0, len(liste), boy):
        yield liste[i:i + boy]


def alissa_barkodlar():
    """{barkod: (model, renk, beden)} — etiketli modellerin TÜM varyantları.

    Aynı modelin etiketsiz kalmış rengi de (ör. 856 Bej) dahildir.
    """
    modeller = (db.session.query(Product.product_main_id)
                .filter(Product.tedarikci_kodu == ayar.TEDARIKCI_KODU).distinct())
    satirlar = (db.session.query(Product.barcode, Product.product_main_id, Product.color, Product.size)
                .filter(Product.product_main_id.in_(modeller)).all())
    return {b: (m, r, s) for b, m, r, s in satirlar if b}


def _mevcut(turler, kaynak_idler):
    bulunan = set()
    for parca in _parcala(list(kaynak_idler)):
        sorgu = (db.session.query(AlissaHareket.tur, AlissaHareket.kaynak_id)
                 .filter(AlissaHareket.tur.in_(turler), AlissaHareket.kaynak_id.in_(parca)))
        bulunan.update((t, k) for t, k in sorgu)
    return bulunan


# ── Finans kayıtları ────────────────────────────────────────────────────────

def finans_isle(satirlar, barkodlar, tutarlar):
    """Settlement satırlarını deftere yazar; yeni teslim edilen paket/sipariş için
    platform hizmet bedeli ve sipariş masrafı satırlarını üretir.

    `satirlar` mağazanın TÜM kayıtlarıdır (karma sipariş payı için gerekir).
    Döner: (eklenen satır sayısı, {sipariş no: iade kargo payı}).
    """
    satirlar = list(satirlar)
    bizim = [s for s in satirlar if s.get('barcode') in barkodlar]
    mevcut = _mevcut(FINANS_TURLERI, [str(s['id']) for s in bizim])
    eklenen = 0
    for s in bizim:
        tur = s['_tur']
        anahtar = (tur, str(s['id']))
        if anahtar in mevcut:
            continue
        mevcut.add(anahtar)
        isaret = ISARET[tur]
        db.session.add(AlissaHareket(
            tur=tur, kaynak_id=str(s['id']), order_number=str(s.get('orderNumber') or ''),
            shipment_package_id=str(s.get('shipmentPackageId') or ''), barcode=s['barcode'],
            model_kodu=barkodlar[s['barcode']][0], islem_tarihi=utc_ms_ist(s['transactionDate']),
            adet=1 if tur in ('satis', 'iade') else 0,
            brut=isaret * _k(abs(_d(s.get('credit')) + _d(s.get('debt')))),
            komisyon=isaret * _k(abs(_d(s.get('commissionAmount')))),
            tutar=isaret * _k(abs(_d(s.get('sellerRevenue'))))))
        eklenen += 1

    eklenen += _paket_kalemleri(satirlar, barkodlar, tutarlar)

    iade_tum, iade_biz = defaultdict(int), defaultdict(int)
    for s in satirlar:
        if s['_tur'] == 'iade':
            iade_tum[str(s.get('orderNumber'))] += 1
            if s.get('barcode') in barkodlar:
                iade_biz[str(s.get('orderNumber'))] += 1
    iade_pay = {no: _pay(n, iade_tum[no]) for no, n in iade_biz.items()}
    db.session.flush()
    return eklenen, iade_pay


def _paket_kalemleri(satirlar, barkodlar, tutarlar):
    """Satışı görülen her (paket, model) için PHB, her (sipariş, model) için masraf satırı."""
    sip_tum, pk_tum = defaultdict(int), defaultdict(int)
    sip_biz, pk_biz = defaultdict(int), defaultdict(int)     # (no, model) -> adet
    sip_tarih, pk_tarih, pk_sip = {}, {}, {}
    for s in satirlar:
        if s['_tur'] != 'satis':
            continue
        no, pk = str(s.get('orderNumber') or ''), str(s.get('shipmentPackageId') or '')
        sip_tum[no] += 1
        pk_tum[pk] += 1
        if s.get('barcode') in barkodlar:
            model = barkodlar[s['barcode']][0]
            tarih = utc_ms_ist(s['transactionDate'])
            sip_biz[(no, model)] += 1
            pk_biz[(pk, model)] += 1
            sip_tarih[no] = min(tarih, sip_tarih.get(no, tarih))
            pk_tarih[pk] = min(tarih, pk_tarih.get(pk, tarih))
            pk_sip[pk] = no

    eklenen = 0
    # Sipariş/paket daha önce işlendiyse (örtüşen pencere) yeniden yazılmaz.
    islenmis_sip = _islenmis('masraf', {no for no, _ in sip_biz})
    islenmis_pk = _islenmis('phb', {pk for pk, _ in pk_biz}, paket=True)
    for (no, model), adet in sip_biz.items():
        if no in islenmis_sip:
            continue
        pay = _pay(adet, sip_tum[no])
        db.session.add(AlissaHareket(
            tur='masraf', kaynak_id=f'{no}:{model}', order_number=no, model_kodu=model,
            islem_tarihi=sip_tarih[no], pay=pay, tutar=-_k(tutarlar['siparis_masrafi'] * pay),
            aciklama='Sipariş başı masraf'))
        eklenen += 1
    for (pk, model), adet in pk_biz.items():
        if pk in islenmis_pk:
            continue
        pay = _pay(adet, pk_tum[pk])
        db.session.add(AlissaHareket(
            tur='phb', kaynak_id=f'{pk}:{model}', order_number=pk_sip[pk], shipment_package_id=pk,
            model_kodu=model, islem_tarihi=pk_tarih[pk], pay=pay,
            tutar=-_k(tutarlar['phb_birim'] * pay), aciklama='Platform hizmet bedeli'))
        eklenen += 1
    return eklenen


def _islenmis(tur, numaralar, paket=False):
    kolon = AlissaHareket.shipment_package_id if paket else AlissaHareket.order_number
    bulunan = set()
    for parca in _parcala(list(numaralar)):
        sorgu = db.session.query(kolon).filter(AlissaHareket.tur == tur, kolon.in_(parca))
        bulunan.update(r[0] for r in sorgu)
    return bulunan


# ── Kargo ───────────────────────────────────────────────────────────────────

def kargo_kalem_kaydet(istemci, bas, son):
    """Penceredeki kargo faturalarından henüz kayıtlı olmayanların kalemlerini saklar."""
    kayitli = {r[0] for r in db.session.query(AlissaKargoKalem.fatura_no).distinct()}
    eklenen = 0
    for fatura_no, fatura_tarihi in istemci.kargo_faturalari(bas, son):
        if fatura_no in kayitli:
            continue
        kayitli.add(fatura_no)
        gorulen = set()
        for kalem in istemci.kargo_kalemleri(fatura_no):
            tip = KARGO_TIPLERI.get(kalem.get('shipmentPackageType'))
            anahtar = (str(kalem.get('parcelUniqueId') or ''), tip)
            if not tip or not anahtar[0] or anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            db.session.add(AlissaKargoKalem(
                fatura_no=fatura_no, fatura_tarihi=fatura_tarihi,
                order_number=str(kalem.get('orderNumber') or ''), parcel_id=anahtar[0], tip=tip,
                tutar=_k(_d(kalem.get('amount'))), desi=_d(kalem.get('desi'))))
            eklenen += 1
    db.session.flush()
    return eklenen


def kargo_isle(tutarlar, iade_pay=None):
    """Alissa siparişlerinin gönderi/iade kargosunu deftere işler (gerçek, tahmin veya fark)."""
    iade_pay = iade_pay or {}
    gonderi = {}
    for h in AlissaHareket.query.filter_by(tur='masraf').order_by(AlissaHareket.islem_tarihi):
        aday = gonderi.setdefault(h.order_number, {'pay': Decimal(0), 'tarih': h.islem_tarihi,
                                                   'model': h.model_kodu})
        aday['pay'] += h.pay or 0
    # Karma sipariş ayrı paketlerle giderse diğer paketin kolisi Alissa'ya yazılmasın.
    paketler = defaultdict(set)
    for h in AlissaHareket.query.filter_by(tur='phb'):
        paketler[h.order_number].add(h.shipment_package_id)
    for no, aday in gonderi.items():
        aday['koli_siniri'] = len(paketler[no]) or 1
    iade = {}
    for h in AlissaHareket.query.filter_by(tur='iade').order_by(AlissaHareket.islem_tarihi):
        if h.order_number not in iade:
            pay = (iade_pay.get(h.order_number)
                   or gonderi.get(h.order_number, {}).get('pay') or Decimal(1))
            iade[h.order_number] = {'pay': pay, 'tarih': h.islem_tarihi, 'model': h.model_kodu}
    eklenen = _kargo_aile(gonderi, 'gonderi', KARGO_GONDERI, tutarlar['kargo_tahmin'])
    eklenen += _kargo_aile(iade, 'iade', KARGO_IADE, tutarlar['kargo_tahmin'])
    db.session.flush()
    return eklenen


def _kargo_aile(adaylar, tip, aile, tahmin_tutar):
    gercek, tahmin, fark = aile
    etiket = 'Gönderi kargo' if tip == 'gonderi' else 'İade kargo'
    hareketler, kalemler = defaultdict(list), defaultdict(list)
    for parca in _parcala(list(adaylar)):
        for h in AlissaHareket.query.filter(AlissaHareket.tur.in_(aile),
                                            AlissaHareket.order_number.in_(parca)):
            hareketler[h.order_number].append(h)
        for k in (AlissaKargoKalem.query
                  .filter(AlissaKargoKalem.tip == tip, AlissaKargoKalem.order_number.in_(parca))
                  .order_by(AlissaKargoKalem.fatura_tarihi, AlissaKargoKalem.id)):
            kalemler[k.order_number].append(k)

    eklenen = 0

    def ekle(tur, kaynak_id, no, aday, pay, tarih, tutar, aciklama):
        nonlocal eklenen
        db.session.add(AlissaHareket(tur=tur, kaynak_id=kaynak_id, order_number=no,
                                     model_kodu=aday['model'], islem_tarihi=tarih, pay=pay,
                                     tutar=_k(tutar), aciklama=aciklama))
        eklenen += 1

    for no, aday in adaylar.items():
        onceki = hareketler[no]
        islenen = {h.kaynak_id for h in onceki if h.tur != tahmin}
        yeni = [k for k in kalemler[no] if k.parcel_id not in islenen]
        if aday.get('koli_siniri') is not None:
            yeni = yeni[:max(aday['koli_siniri'] - len(islenen), 0)]
        pay = next((h.pay for h in onceki if h.pay is not None), None) or aday['pay']
        if not onceki:
            # İlk kez görülen sipariş: fatura varsa gerçeği, yoksa tahmini teslim/iade haftasına yaz.
            for k in yeni:
                ekle(gercek, k.parcel_id, no, aday, pay, aday['tarih'], -(k.tutar * pay),
                     f'{etiket} (fatura {k.fatura_no}, {k.desi} desi)')
            if not yeni:
                ekle(tahmin, no, no, aday, pay, aday['tarih'], -(tahmin_tutar * pay),
                     f'{etiket} tahmini — fatura bekleniyor')
            continue
        tahmin_h = next((h for h in onceki if h.tur == tahmin), None)
        fark_var = any(h.tur == fark for h in onceki)
        for k in yeni:
            if tahmin_h is not None and not fark_var:
                # Tahmin yazılmıştı, fatura geldi: yalnız fark, faturanın geldiği haftaya.
                ekle(fark, k.parcel_id, no, aday, pay, k.fatura_tarihi, -(k.tutar * pay) - tahmin_h.tutar,
                     f'{etiket} farkı (fatura {k.fatura_no}: {k.tutar} TL, tahmin {-tahmin_h.tutar} TL)')
                fark_var = True
            else:
                ekle(gercek, k.parcel_id, no, aday, pay, k.fatura_tarihi, -(k.tutar * pay),
                     f'{etiket} ek koli (fatura {k.fatura_no}, {k.desi} desi)')
    return eklenen


# ── Siparişler (bilgi amaçlı: gelen / iptal / yolda) ────────────────────────

def siparis_isle(paketler, barkodlar):
    guncellenen = 0
    for p in sorted(paketler, key=lambda p: p.get('lastModifiedDate') or 0):
        for satir in p.get('lines') or []:
            if satir.get('barcode') not in barkodlar:
                continue
            line_id = str(satir.get('lineId') or satir.get('id'))
            kayit = db.session.get(AlissaSiparis, line_id)
            if kayit is None:
                kayit = AlissaSiparis(line_id=line_id)
                db.session.add(kayit)
            model, renk, beden = barkodlar[satir['barcode']]
            kayit.order_number = str(p.get('orderNumber') or '')
            kayit.shipment_package_id = str(p.get('shipmentPackageId') or p.get('id') or '')
            kayit.barcode = satir['barcode']
            kayit.model_kodu, kayit.renk, kayit.beden = model, renk, beden
            kayit.adet = satir.get('quantity') or 1
            kayit.statu = satir.get('orderLineItemStatusName') or p.get('status')
            kayit.siparis_tarihi = duvar_ms_ist(p['orderDate'])
            kayit.birim_fiyat = _k(_d(satir.get('lineUnitPrice') or satir.get('price')))
            kayit.iptal_eden = satir.get('cancelledBy')
            kayit.iptal_sebebi = (satir.get('cancelReason') or '')[:255] or None
            guncellenen += 1
    db.session.flush()
    return guncellenen


# ── Orkestrasyon ────────────────────────────────────────────────────────────

def senkronla(istemci=None, simdi=None, nabiz=None):
    """Aşamalar ayrı ayrı commit edilir; yarıda kalan senkron bir sonrakinde tamamlanır."""
    simdi = simdi or simdi_ist()
    nabiz = nabiz or (lambda: None)
    barkodlar = alissa_barkodlar()
    if not barkodlar:
        raise SenkronHata(f"'{ayar.TEDARIKCI_KODU}' tedarikçisine atanmış ürün bulunamadı.")
    istemci = istemci or Istemci()
    son = ayar.oku('son_senkron')
    bas = (datetime.fromisoformat(son) - timedelta(days=ayar.ORTUSME_GUN) if son
           else datetime.combine(ayar.BASLANGIC, time.min))
    # Tedarikçiye sonradan etiketlenen model: geçmişi baştan taranır (eski satışları dahil olsun).
    modeller = {m for m, _, _ in barkodlar.values()}
    yeni_modeller = sorted(modeller - set(json.loads(ayar.oku('bilinen_modeller') or '[]')))
    if son and yeni_modeller:
        bas = datetime.combine(ayar.BASLANGIC, time.min)
        logger.info('Alissa: yeni model(ler) %s — geçmiş baştan taranıyor', yeni_modeller)
    tutarlar = ayar.tutarlar()

    ozet = {'kargo_kalem': kargo_kalem_kaydet(istemci, bas, simdi), 'yeni_modeller': yeni_modeller}
    db.session.commit()   # ham fatura kalemleri: sonraki adım hata verse de tekrar çekilmesin
    nabiz()
    satirlar = list(istemci.settlements(bas, simdi))
    nabiz()
    ozet['finans'], iade_pay = finans_isle(satirlar, barkodlar, tutarlar)
    ozet['kargo'] = kargo_isle(tutarlar, iade_pay)
    db.session.commit()
    nabiz()
    siparis_bas = max(bas, simdi - timedelta(days=SIPARIS_GERI_GUN))
    ozet['siparis'] = siparis_isle(list(istemci.siparis_paketleri(siparis_bas, simdi)), barkodlar)
    ayar.yaz('son_senkron', simdi.isoformat(timespec='seconds'))
    ayar.yaz('bilinen_modeller', json.dumps(sorted(modeller)))
    db.session.commit()
    logger.info('Alissa senkron tamam: %s', ozet)
    return ozet


# ── Kilit ve arka plan ──────────────────────────────────────────────────────
# Kilit tek satırdır (alissa_ayar.senkron_kilit): boş = serbest, dolu = son nabız zamanı.
# Tek UPDATE ile alınır; iki worker aynı anda alamaz. Nabız KILIT_DK'dan eskiyse takılmış sayılır.

def _kilit_esigi():
    return (simdi_ist() - timedelta(minutes=ayar.KILIT_DK)).isoformat(timespec='seconds')


def _kilit_al():
    if db.session.get(AlissaAyar, 'senkron_kilit') is None:
        try:
            db.session.add(AlissaAyar(anahtar='senkron_kilit', deger=''))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    alindi = (AlissaAyar.query
              .filter(AlissaAyar.anahtar == 'senkron_kilit',
                      db.or_(AlissaAyar.deger == '', AlissaAyar.deger < _kilit_esigi()))
              .update({'deger': simdi_ist().isoformat(timespec='seconds')}, synchronize_session=False))
    db.session.commit()
    return alindi == 1


def _nabiz():
    ayar.yaz('senkron_kilit', simdi_ist().isoformat(timespec='seconds'))
    db.session.commit()


def durum():
    db.session.expire_all()
    kilit = ayar.oku('senkron_kilit') or ''
    son = ayar.oku('son_senkron')
    return {'calisiyor': bool(kilit) and kilit >= _kilit_esigi(),
            'son_senkron': datetime.fromisoformat(son) if son else None,
            'hata': ayar.oku('senkron_hata') or ''}


def eskidi():
    """Son başarılı senkron VE son deneme ESKIME_SAAT'ten eskiyse True (hata sonrası sürekli denemez)."""
    zamanlar = [z for z in (ayar.oku('son_senkron'), ayar.oku('son_deneme')) if z]
    if not zamanlar:
        return True
    return simdi_ist() - datetime.fromisoformat(max(zamanlar)) > timedelta(hours=ayar.ESKIME_SAAT)


def arka_planda_baslat(app):
    """Senkronu ayrı iş parçacığında başlatır (istek zaman aşımına düşmesin). Zaten çalışıyorsa False."""
    if not _kilit_al():
        return False
    ayar.yaz('son_deneme', simdi_ist().isoformat(timespec='seconds'))
    ayar.yaz('senkron_hata', '')
    db.session.commit()
    threading.Thread(target=_calistir, args=(app,), daemon=True).start()
    return True


def _calistir(app):
    with app.app_context():
        hata = ''
        try:
            senkronla(nabiz=_nabiz)
        except Exception as e:
            db.session.rollback()
            logger.exception('Alissa senkron hatası')
            hata = str(e)[:500]
        try:
            ayar.yaz('senkron_hata', hata)
            ayar.yaz('senkron_kilit', '')
            db.session.commit()
        finally:
            db.session.remove()
