"""Şahsi cari hesap (dükkânın kasasından alınan borç) regresyonları. Gerçek DB kullanılmaz.

Çalıştırma: .venv/bin/python -m unittest discover -s tests -p test_finans_cari_sahsi.py
"""
import unittest
from datetime import datetime
from decimal import Decimal

import test_finans_haftalik as base
import finans_service as fs
import finans_cari_service as cs
from finans_service import FinansHata
from models import db, FinansHesap, FinansIslem

T = datetime(2026, 1, 5, 12)


class SahsiCariTest(unittest.TestCase):
    def setUp(self):
        base.HaftalikOdemeTest.setUp(self)
        db.session.add(FinansHesap(kod='beyazit', ad='Beyazıt', bakiye=Decimal('0')))
        hesap = fs.hesap_getir('elde')
        hesap.bakiye = 0
        fs._hareket(hesap, 'gelir', 1, Decimal('10000'), datetime(2026, 1, 1), 1)
        db.session.commit()

    def tearDown(self):
        base.HaftalikOdemeTest.tearDown(self)

    def sahsi(self, ad='Musir — şahsi'):
        return cs.cari_ekle(ad, 'sahsi', '', '', 1)

    def tutarli(self):
        self.assertEqual(cs.cari_tutarlilik_kontrol(), [])
        self.assertEqual(fs.tutarlilik_kontrol(), [])

    def test_borc_alma_kasadan_duser_ve_alacak_yazar(self):
        c = self.sahsi()
        h = cs.odeme_yap(c.id, 'elde', Decimal('500'), T, 'Ev harcaması', 1, tur='borc_alma')
        self.assertEqual(h.tur, 'borc_alma')
        self.assertEqual(c.bakiye, Decimal('-500'))            # kasaya borcumuz
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('9500'))
        self.assertEqual(h.islem.tur, 'cari_odeme')
        self.tutarli()

    def test_borc_odeme_beyazita_girer_ve_borcu_azaltir(self):
        c = self.sahsi()
        cs.odeme_yap(c.id, 'elde', Decimal('500'), T, '', 1, tur='borc_alma')
        h = cs.tahsilat_al(c.id, Decimal('200'), T, '', 1, tur='borc_odeme')
        self.assertEqual(h.tur, 'borc_odeme')
        self.assertEqual(c.bakiye, Decimal('-300'))
        self.assertEqual(fs.hesap_getir('beyazit').bakiye, Decimal('200'))
        self.assertEqual(h.islem.tur, 'cari_tahsilat')
        self.tutarli()

    def test_iptal_iki_tarafi_geri_alir(self):
        c = self.sahsi()
        h = cs.odeme_yap(c.id, 'elde', Decimal('500'), T, '', 1, tur='borc_alma')
        cs.hareket_iptal(h.id, 1)
        self.assertEqual(c.bakiye, Decimal('0'))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10000'))
        self.tutarli()

    def test_sahsi_hesapta_normal_hareketler_kapali(self):
        c = self.sahsi()
        with self.assertRaises(FinansHata):
            cs.mal_girisi(c.id, cs.parse_kalemler(['Deri'], ['1'], ['100']), T, '', 1)
        with self.assertRaises(FinansHata):
            cs.odeme_yap(c.id, 'elde', Decimal('100'), T, '', 1)
        with self.assertRaises(FinansHata):
            cs.tahsilat_al(c.id, Decimal('100'), T, '', 1)
        self.assertEqual(c.bakiye, Decimal('0'))
        self.assertEqual(FinansIslem.query.filter_by(tur='cari_odeme').count(), 0)
        self.tutarli()

    def test_borc_alma_diger_hesaplarda_kapali(self):
        t = cs.cari_ekle('Taban Ltd', 'tedarikci', '', '', 1)
        with self.assertRaises(FinansHata):
            cs.odeme_yap(t.id, 'elde', Decimal('100'), T, '', 1, tur='borc_alma')
        with self.assertRaises(FinansHata):
            cs.tahsilat_al(t.id, Decimal('100'), T, '', 1, tur='borc_odeme')
        self.assertEqual(t.bakiye, Decimal('0'))
        self.tutarli()

    def test_hareketli_hesap_sahsiye_cevrilemez(self):
        t = cs.cari_ekle('Taban Ltd', 'tedarikci', '', '', 1)
        cs.mal_girisi(t.id, cs.parse_kalemler(['Deri'], ['1'], ['100']), T, '', 1)
        with self.assertRaises(FinansHata):
            cs.cari_guncelle(t.id, t.ad, 'sahsi', '', '')

    def test_ozet_sahsi_borcu_alacaktan_ayirir(self):
        c = self.sahsi()
        cs.odeme_yap(c.id, 'elde', Decimal('500'), T, '', 1, tur='borc_alma')
        t = cs.cari_ekle('Taban Ltd', 'tedarikci', '', '', 1)
        cs.mal_girisi(t.id, cs.parse_kalemler(['Deri'], ['1'], ['100']), T, '', 1)
        o = cs.cari_ozet()
        self.assertEqual(o['sahsi'], Decimal('500'))
        self.assertEqual(o['alacak'], Decimal('0.00'))
        self.assertEqual(o['borc'], Decimal('100'))

    def test_bakiyeli_sahsi_hesap_kapatilamaz(self):
        c = self.sahsi()
        cs.odeme_yap(c.id, 'elde', Decimal('500'), T, '', 1, tur='borc_alma')
        with self.assertRaises(FinansHata):
            cs.cari_pasif(c.id, aktif=False)


if __name__ == '__main__':
    unittest.main()
