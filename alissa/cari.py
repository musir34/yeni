# -*- coding: utf-8 -*-
"""Alissa hesabı ↔ Finans cari köprüsü (komutan emri 2026-10-17).

Alissa'nın haftalık net hak edişi Finans'taki "Muhammet Alissa" cari hesabına hafta hafta düşer;
ödeme ister /alissa'dan ister /finans/cari'den yapılsın aynı cari + kasa hareketini yazar
(finans_cari_service.odeme_yap). Böylece /alissa'daki "Ödenecek bakiye" = cari bakiyesi.

Kural: her hafta için cari defterinde EN FAZLA bir açık (iptal edilmemiş) hak ediş satırı bulunur.
Haftanın neti değişince (yeni teslim, iade, kargo faturası farkı) eski satır iptal edilir, haftanın
tamamı yeniden yazılır; alissa_cari_hafta hangi haftanın hangi satırla yazıldığını tutar. Bu satırlar
Finans tarafından elle iptal edilemez (finans_cari_service.ALISSA_TURLERI).

Bağlantı öncesi AlissaOdeme kayıtları ilk bağlantıda kasasız "odeme" satırı olarak cariye devredilir
(o ödemeler kasaya hiç yazılmamıştı; kasa bakiyesi değişmez).
"""
import logging
from datetime import datetime, time, timedelta
from decimal import Decimal

from models import db, FinansCari, FinansCariHareket, User
from time_utils import ist_to_utc
import finans_service as fs
import finans_cari_service as cs
from . import ayar, hesap
from .models import AlissaCariHafta, AlissaOdeme

logger = logging.getLogger(__name__)

CARI_ADI = 'Muhammet Alissa'
CARI_NOT = 'Trendyol haftalık hak edişi /alissa sayfasından otomatik yazılır.'
AYAR_CARI_ID = 'cari_id'
AYAR_DEVIR = 'cari_devir'          # '1': bağlantı öncesi AlissaOdeme kayıtları cariye aktarıldı
ODEME_TURU = 'odeme'
SIFIR = Decimal('0.00')


def _ilk_kullanici_id():
    """Arka plan senkronunda oturum yok: sahip, yoksa admin, yoksa ilk kullanıcı."""
    u = (User.query.filter_by(is_owner=True).order_by(User.id).first()
         or User.query.filter_by(role='admin').order_by(User.id).first()
         or User.query.order_by(User.id).first())
    if u is None:
        raise fs.FinansHata('Cari hareketi yazacak kullanıcı bulunamadı.')
    return u.id


def _kullanici(cari, kullanici_id):
    return int(kullanici_id) if kullanici_id else (cari.olusturan_kullanici_id or _ilk_kullanici_id())


def _mevcut_cari():
    """Ayarda kayıtlı id, yoksa ada göre arama (Finans'tan elle açılmış olabilir)."""
    kayitli = ayar.oku(AYAR_CARI_ID)
    if kayitli:
        c = db.session.get(FinansCari, int(kayitli))
        if c is not None:
            return c
    return next((c for c in FinansCari.query.all() if fs._ad_esit(c.ad, CARI_ADI)), None)


def _devret(cari, kullanici_id):
    """Bağlantı öncesi ödemeleri (iptal olmayan AlissaOdeme) cariye kasasız 'odeme' olarak bir kez aktarır."""
    if ayar.oku(AYAR_DEVIR) == '1':
        return 0
    eski = (AlissaOdeme.query.filter(AlissaOdeme.iptal.is_(False))
            .order_by(AlissaOdeme.tarih, AlissaOdeme.id).all())
    for o in eski:
        aciklama = 'Alissa ödemesi (bağlantı öncesi kayıt)' + (f' — {o.aciklama}' if o.aciklama else '')
        cs._cari_hareket(cari, ODEME_TURU, Decimal(str(o.tutar)),
                         ist_to_utc(datetime.combine(o.tarih, time(12))), aciklama, kullanici_id)
    ayar.yaz(AYAR_DEVIR, '1')
    return len(eski)


def cari_getir(kullanici_id=None):
    """Alissa carisi; yoksa açar, kapalıysa açar, ilk bağlantıda eski ödemeleri devreder. COMMIT EDER."""
    c = _mevcut_cari()
    if c is None:
        c = cs.cari_ekle(CARI_ADI, 'tedarikci', '', CARI_NOT, kullanici_id or _ilk_kullanici_id())
        logger.info('Alissa: "%s" cari hesabı açıldı (#%s)', c.ad, c.id)
    try:
        c = cs.cari_getir(c.id, kilitle=True)
        if not c.aktif:
            c.aktif = True
        ayar.yaz(AYAR_CARI_ID, c.id)
        devir = _devret(c, _kullanici(c, kullanici_id))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    if devir:
        logger.info('Alissa: bağlantı öncesi %s ödeme cariye devredildi', devir)
    return c


def _hafta_tarihi(bas):
    return ist_to_utc(datetime.combine(bas, time.min))


def _aciklama(bas):
    return f'Alissa hak edişi — {bas:%d.%m.%Y}–{bas + timedelta(days=6):%d.%m.%Y} haftası (kesintiler sonrası net)'


def esitle(kullanici_id=None):
    """Haftalık netleri cariye yazar/günceller; carinin bakiyesi = Σ hafta neti − ödemeler olur.

    Değişmeyen hafta dokunulmaz; değişen haftanın açık satırı iptal edilip tamamı yeniden yazılır.
    Dönüş: cari (sayfa bunu kullanır). Hata durumunda rollback + yeniden fırlatır.
    """
    c = cari_getir(kullanici_id)
    try:
        cari = cs.cari_getir(c.id, kilitle=True)
        uid = _kullanici(cari, kullanici_id)
        netler = hesap.hafta_netleri()
        kayitlar = {k.hafta_basi: k for k in AlissaCariHafta.query.populate_existing().all()}
        simdi = datetime.utcnow()
        for bas in sorted(set(netler) | set(kayitlar)):
            net = netler.get(bas, SIFIR).quantize(fs.IKI_HANE)
            k = kayitlar.get(bas)
            acik = k.hareket if k is not None and k.hareket is not None and not k.hareket.iptal else None
            if acik is not None and Decimal(str(k.tutar)).quantize(fs.IKI_HANE) == net:
                continue
            if acik is not None:
                fs.cari_hareket_geri_al(acik, uid, simdi)
            h = None
            if net != 0:
                tur = 'alissa_hakedis' if net > 0 else 'alissa_duzeltme'
                h = cs._cari_hareket(cari, tur, abs(net), _hafta_tarihi(bas), _aciklama(bas), uid)
            if k is None:
                k = AlissaCariHafta(hafta_basi=bas)
                db.session.add(k)
            k.tutar, k.hareket_id, k.guncellendi = net, (h.id if h is not None else None), simdi
        db.session.commit()
        return cari
    except Exception:
        db.session.rollback()
        raise


def odenen(cari):
    """Alissa'ya ödenen toplam: carideki iptal edilmemiş 'odeme' satırları (kasalı + devir)."""
    toplam = (db.session.query(db.func.coalesce(db.func.sum(FinansCariHareket.tutar), 0))
              .filter(FinansCariHareket.cari_id == cari.id, FinansCariHareket.tur == ODEME_TURU,
                      FinansCariHareket.iptal.is_(False)).scalar())
    return Decimal(str(toplam)).quantize(fs.IKI_HANE)


def odemeler(cari, adet=200):
    return (FinansCariHareket.query.filter_by(cari_id=cari.id, tur=ODEME_TURU)
            .order_by(FinansCariHareket.tarih.desc(), FinansCariHareket.id.desc()).limit(adet).all())


def odeme_yap(cari, hesap_kodu, tutar, tarih, aciklama, kullanici_id):
    """Alissa sayfasından ödeme: Finans ile aynı yol (kasa hareketi + cari borç ↓, tek transaction)."""
    return cs.odeme_yap(cari.id, hesap_kodu, tutar, tarih, aciklama or 'Alissa ödemesi', kullanici_id)


def odeme_iptal(cari, hareket_id, kullanici_id):
    h = db.session.get(FinansCariHareket, int(hareket_id))
    if h is None or h.cari_id != cari.id or h.tur != ODEME_TURU:
        raise fs.FinansHata('Ödeme bulunamadı.')
    return cs.hareket_iptal(h.id, kullanici_id)
