"""Çalışanın cebinden verdiği para (çalışandan borç) regresyonları. Gerçek DB kullanılmaz.

Çalıştırma: .venv/bin/python -m unittest discover -s tests -p test_finans_calisan_borc.py
"""
import unittest
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import test_finans_haftalik as base
import finans_service as fs
import finans_cari_service as cs
import finans_calisan_service as ws
from finans_service import FinansHata
from models import db, FinansHesap, FinansIslem

T = datetime(2026, 1, 5, 12)


class CalisanBorcTest(unittest.TestCase):
    def setUp(self):
        base.HaftalikOdemeTest.setUp(self)
        self.clock = patch('finans_calisan_service.to_ist', return_value=datetime(2026, 1, 2, 12))
        self.clock.start()
        db.session.add(FinansHesap(kod='beyazit', ad='Beyazıt', bakiye=Decimal('0')))
        db.session.add(FinansHesap(kod='banka', ad='Banka', bakiye=Decimal('0')))
        hesap = fs.hesap_getir('elde')
        hesap.bakiye = 0
        fs._hareket(hesap, 'gelir', 1, Decimal('10000'), datetime(2026, 1, 1), 1)
        db.session.commit()

    def tearDown(self):
        self.clock.stop()
        base.HaftalikOdemeTest.tearDown(self)

    def calisan(self, ad='Hatice Yüksel Ertaş'):
        return cs.cari_ekle(ad, 'calisan', '', '', 1)

    def al(self, c, tutar='300', hesap='elde', aciklama='Kargo parası'):
        return cs.tahsilat_al(c.id, Decimal(tutar), T, aciklama, 1, tur='calisan_borc', hesap_kodu=hesap)

    def geri_ode(self, c, tutar, hesap='elde'):
        return cs.odeme_yap(c.id, hesap, Decimal(tutar), T, '', 1, tur='calisan_borc_odeme')

    def tutarli(self):
        self.assertEqual(cs.cari_tutarlilik_kontrol(), [])
        self.assertEqual(fs.tutarlilik_kontrol(), [])

    def test_para_alma_secilen_kasaya_girer_ve_borcu_artirir(self):
        c = self.calisan()
        h = self.al(c, '300')
        self.assertEqual((h.tur, h.yon), ('calisan_borc', 1))
        self.assertEqual(h.islem.tur, 'cari_tahsilat')
        self.assertEqual(h.islem.hesap.kod, 'elde')
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10300'))
        self.assertEqual(fs.hesap_getir('beyazit').bakiye, Decimal('0'))
        self.assertEqual(c.bakiye, Decimal('300'))
        self.assertEqual(cs.calisan_borc_kalan(c.id), Decimal('300'))
        self.tutarli()

    def test_para_alma_bankaya_da_girebilir_beyazita_giremez(self):
        c = self.calisan()
        self.al(c, '100', hesap='banka')
        self.assertEqual(fs.hesap_getir('banka').bakiye, Decimal('100'))
        for kotu in ('beyazit', '', None):
            with self.assertRaises(FinansHata):
                self.al(c, '100', hesap=kotu)
        self.assertEqual(c.bakiye, Decimal('100'))

    def test_geri_odeme_kasadan_duser_ve_borcu_azaltir(self):
        c = self.calisan()
        self.al(c, '300')
        h = self.geri_ode(c, '200')
        self.assertEqual((h.tur, h.yon), ('calisan_borc_odeme', -1))
        self.assertEqual(h.islem.tur, 'cari_odeme')
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10100'))
        self.assertEqual(c.bakiye, Decimal('100'))
        self.assertEqual(cs.calisan_borc_kalan(c.id), Decimal('100'))
        self.tutarli()

    def test_geri_odeme_alinan_paradan_fazla_olamaz(self):
        c = self.calisan()
        self.al(c, '300')
        with self.assertRaises(FinansHata):
            self.geri_ode(c, '300.01')
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10300'))
        self.assertEqual(FinansIslem.query.filter_by(tur='cari_odeme').count(), 0)
        self.geri_ode(c, '300')
        self.assertEqual(cs.calisan_borc_kalan(c.id), Decimal('0'))
        with self.assertRaises(FinansHata):
            self.geri_ode(c, '1')

    def test_iptal_iki_tarafi_geri_alir(self):
        c = self.calisan()
        h = self.al(c, '300')
        cs.hareket_iptal(h.id, 1)
        db.session.refresh(c)
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10000'))
        self.assertEqual(c.bakiye, Decimal('0'))
        self.assertEqual(cs.calisan_borc_kalan(c.id), Decimal('0'))
        self.tutarli()

    def test_yalniz_calisan_hesabinda_kullanilir(self):
        t = cs.cari_ekle('Taban Ltd', 'tedarikci', '', '', 1)
        s = cs.cari_ekle('Musir — şahsi', 'sahsi', '', '', 1)
        for c in (t, s):
            with self.assertRaises(FinansHata):
                self.al(c, '100')
            with self.assertRaises(FinansHata):
                self.geri_ode(c, '100')
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10000'))

    def test_calisanda_normal_odeme_ve_tahsilat_hala_kapali(self):
        c = self.calisan()
        with self.assertRaises(FinansHata):
            cs.odeme_yap(c.id, 'elde', Decimal('100'), T, '', 1)
        with self.assertRaises(FinansHata):
            cs.tahsilat_al(c.id, Decimal('100'), T, '', 1)
        with self.assertRaises(FinansHata):
            cs.odeme_yap(c.id, 'elde', Decimal('100'), T, '', 1, tur='borc_alma')

    def test_maas_hakedisiyle_karismaz(self):
        k = fs.kalem_ekle('Hatice haftalığı', None, '5000', 'elde', '2026-01', '', '', 1,
                          siklik='haftalik', ilk_odeme_tarihi='2026-01-02',
                          tutar_degisken=False, calisan=True, calisan_adi='Hatice')
        c = k.calisan_cari
        self.assertEqual(c.bakiye, Decimal('5000'))            # maaş hak edişi
        self.al(c, '300')
        self.assertEqual(c.bakiye, Decimal('5300'))
        # Geri ödeme yalnız cebinden verdiği kadar; maaş borcuna dokunamaz.
        with self.assertRaises(FinansHata):
            self.geri_ode(c, '301')
        self.geri_ode(c, '300')
        self.assertEqual(c.bakiye, Decimal('5000'))
        # Maaş ödemesi kendi akışından çalışmaya devam eder, hak ediş ödenen tutarı değişmez.
        h, _ = ws.hakedis_ve_odeme(k.id, '2026-01-02', '5000', '5000', 'elde', datetime(2026, 1, 2, 12),
                                   '', 1, str(uuid.uuid4()), '5000')
        self.assertEqual(ws.odenen_tutar(h.id), Decimal('5000'))
        db.session.refresh(c)
        self.assertEqual(c.bakiye, Decimal('0'))
        self.tutarli()


if __name__ == '__main__':
    unittest.main()
