"""Dolar (USD) cari hesabı regresyonları. Gerçek DB kullanılmaz.

Çalıştırma: .venv/bin/python -m unittest discover -s tests -p test_finans_cari_doviz.py
"""
import unittest
from datetime import datetime
from decimal import Decimal

import test_finans_haftalik as base
import finans_service as fs
import finans_cari_service as cs
from finans_service import FinansHata
from models import db, FinansHesap, FinansCari, FinansCariHareket, FinansIslem

T = datetime(2026, 1, 5, 12)


class DovizCariTest(unittest.TestCase):
    def setUp(self):
        base.HaftalikOdemeTest.setUp(self)
        db.session.add(FinansHesap(kod='beyazit', ad='Beyazıt', bakiye=Decimal('0')))
        # Defter ve kasa başlangıcı birbiriyle tutarlı olsun (tutarlilik_kontrol için).
        hesap = fs.hesap_getir('elde')
        hesap.bakiye = 0
        fs._hareket(hesap, 'gelir', 1, Decimal('10000'), datetime(2026, 1, 1), 1)
        db.session.commit()

    def tearDown(self):
        base.HaftalikOdemeTest.tearDown(self)

    def usd(self, ad='Deri USD'):
        return cs.cari_ekle(ad, 'tedarikci', '', '', 1, para_birimi='USD')

    def alim(self, c, fiyat='100', adet='1'):
        return cs.mal_girisi(c.id, cs.parse_kalemler(['Deri'], [adet], [fiyat]), T, '', 1)

    def tutarli(self):
        self.assertEqual(cs.cari_tutarlilik_kontrol(), [])
        self.assertEqual(fs.tutarlilik_kontrol(), [])

    def test_default_currency_is_try(self):
        c = cs.cari_ekle('Taban Ltd', 'tedarikci', '', '', 1)
        self.assertEqual(c.para_birimi, 'TRY')
        self.assertEqual(cs.sembol(c), '₺')

    def test_invalid_currency_and_employee_usd_rejected(self):
        with self.assertRaises(FinansHata):
            cs.cari_ekle('X', 'tedarikci', '', '', 1, para_birimi='EUR')
        with self.assertRaises(FinansHata):
            cs.cari_ekle('Ahmet', 'calisan', '', '', 1, para_birimi='USD')

    def test_usd_payment_converts_to_try_in_cash(self):
        c = self.usd()
        self.alim(c, fiyat='100')            # 100 $ borç
        self.assertEqual(c.bakiye, Decimal('100'))
        h = cs.odeme_yap(c.id, 'elde', Decimal('40'), T, '', 1, kur=cs.parse_kur('34,50'))
        self.assertEqual(h.tutar, Decimal('40'))          # cari dolar
        self.assertEqual(h.kur, Decimal('34.5000'))
        self.assertEqual(h.islem.tutar, Decimal('1380.00'))  # kasa TL
        self.assertIn('40.00 $ × 34.5000', h.islem.aciklama)
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('8620'))
        self.assertEqual(c.bakiye, Decimal('60'))
        self.tutarli()

    def test_usd_payment_without_rate_rejected_and_nothing_written(self):
        c = self.usd()
        self.alim(c)
        with self.assertRaises(FinansHata):
            cs.odeme_yap(c.id, 'elde', Decimal('40'), T, '', 1)
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10000'))
        self.assertEqual(FinansIslem.query.filter_by(tur='cari_odeme').count(), 0)
        self.assertEqual(c.bakiye, Decimal('100'))

    def test_try_cari_ignores_rate(self):
        c = cs.cari_ekle('Taban Ltd', 'tedarikci', '', '', 1)
        self.alim(c, fiyat='500')
        h = cs.odeme_yap(c.id, 'elde', Decimal('200'), T, '', 1, kur=Decimal('34.5'))
        self.assertIsNone(h.kur)
        self.assertEqual(h.islem.tutar, Decimal('200'))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('9800'))

    def test_usd_collection_and_cancel_restore_both_sides(self):
        c = self.usd()
        cs.mal_girisi(c.id, cs.parse_kalemler(['Ayakkabı'], ['2'], ['50']), T, '', 1, tur='satis')
        self.assertEqual(c.bakiye, Decimal('-100'))       # 100 $ alacak
        h = cs.tahsilat_al(c.id, Decimal('100'), T, '', 1, kur=Decimal('35'))
        self.assertEqual(fs.hesap_getir('beyazit').bakiye, Decimal('3500'))
        self.assertEqual(c.bakiye, Decimal('0'))
        cs.hareket_iptal(h.id, 1)
        db.session.refresh(c)
        self.assertEqual(fs.hesap_getir('beyazit').bakiye, Decimal('0'))
        self.assertEqual(c.bakiye, Decimal('-100'))
        self.tutarli()

    def test_currency_locked_after_first_movement(self):
        c = self.usd()
        cs.cari_guncelle(c.id, c.ad, 'tedarikci', '', '', para_birimi='TRY')
        self.assertEqual(c.para_birimi, 'TRY')
        cs.cari_guncelle(c.id, c.ad, 'tedarikci', '', '', para_birimi='USD')
        self.alim(c)
        with self.assertRaises(FinansHata):
            cs.cari_guncelle(c.id, c.ad, 'tedarikci', '', '', para_birimi='TRY')
        cs.cari_guncelle(c.id, 'Deri USD 2', 'tedarikci', '', '')   # birim verilmezse korunur
        self.assertEqual(c.para_birimi, 'USD')

    def test_summary_keeps_currencies_apart(self):
        c1 = self.usd(); self.alim(c1, fiyat='100')
        c2 = cs.cari_ekle('Taban Ltd', 'tedarikci', '', '', 1); self.alim(c2, fiyat='700')
        o = cs.cari_ozet()
        self.assertEqual((o['borc'], o['borc_usd'], o['alacak'], o['alacak_usd']),
                         (Decimal('700'), Decimal('100'), Decimal('0'), Decimal('0')))

    def test_parse_kur(self):
        self.assertEqual(cs.parse_kur('34,5678'), Decimal('34.5678'))
        self.assertEqual(cs.parse_kur('34.5'), Decimal('34.5000'))
        for bad in ('', '0', '-1', 'abc'):
            with self.assertRaises(FinansHata):
                cs.parse_kur(bad)


if __name__ == '__main__':
    unittest.main()
