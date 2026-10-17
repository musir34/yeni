"""Kasa sayım mutabakatı (komutan emri 2026-10-17): sayılan − defter farkı tek satır, bakiye sayılana eşitlenir.

Çalıştırma: DISABLE_JOBS=1 python -m unittest discover -s tests -p test_finans_sayim.py
"""
import unittest
from datetime import datetime
from decimal import Decimal

import test_finans_haftalik as base
import finans_service as fs
from finans_service import FinansHata
from models import db, FinansHesap, FinansIslem

T = datetime(2026, 1, 20, 12)


class SayimTest(unittest.TestCase):
    def setUp(self):
        base.HaftalikOdemeTest.setUp(self)   # miras değil: taban testleri tekrar koşmasın
        db.session.add(FinansHesap(kod='kredi_karti', ad='Kart', bakiye=Decimal('0')))
        hesap = fs.hesap_getir('elde')
        hesap.bakiye = 0
        fs._hareket(hesap, 'gelir', 1, Decimal('10000'), datetime(2026, 1, 1), 1)
        db.session.commit()

    def tearDown(self):
        base.HaftalikOdemeTest.tearDown(self)

    def test_fazla_sayim_arti_satir_ve_bakiye_sayilana_esitlenir(self):
        islem = fs.sayim_mutabakat('elde', Decimal('10250.50'), T, 'Bozuk para', 1)
        self.assertEqual((islem.tur, islem.yon, islem.tutar), ('sayim_farki', 1, Decimal('250.50')))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10250.50'))
        self.assertIn('Sayım fazlası', islem.aciklama); self.assertIn('Bozuk para', islem.aciklama)
        self.assertEqual(fs.tutarlilik_kontrol(), [])

    def test_eksik_sayim_eksi_satir(self):
        islem = fs.sayim_mutabakat('elde', Decimal('9000'), T, 'Girilmeyen harcama', 1)
        self.assertEqual((islem.yon, islem.tutar), (-1, Decimal('1000.00')))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('9000'))
        self.assertEqual(fs.tutarlilik_kontrol(), [])

    def test_sifir_sayim_kasa_bos(self):
        self.assertEqual(fs.parse_sayilan('0'), Decimal('0.00'))
        fs.sayim_mutabakat('elde', fs.parse_sayilan('0,00'), T, 'Kasa boşaltıldı', 1)
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('0'))

    def test_fark_yoksa_aciklama_yoksa_kart_ise_hata(self):
        with self.assertRaises(FinansHata):
            fs.sayim_mutabakat('elde', Decimal('10000'), T, 'x', 1)          # fark 0
        with self.assertRaises(FinansHata):
            fs.sayim_mutabakat('elde', Decimal('9000'), T, '  ', 1)          # açıklama boş
        with self.assertRaises(FinansHata):
            fs.sayim_mutabakat('kredi_karti', Decimal('0'), T, 'x', 1)       # kart kendi mutabakatını kullanır
        with self.assertRaises(FinansHata):
            fs.parse_sayilan('-5')
        self.assertEqual(FinansIslem.query.filter_by(tur='sayim_farki').count(), 0)
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10000'))

    def test_fark_raporlara_girmez(self):
        fs.sayim_mutabakat('elde', Decimal('9000'), T, 'Girilmeyen harcama', 1)
        ozet = fs.donem_ozet('2026-01')
        self.assertEqual((ozet['gelir'], ozet['kucuk_gider'], ozet['ana_gider']), (Decimal('10000'), Decimal('0'), Decimal('0')))
        self.assertIn('sayim_farki', fs.ISLEM_TURLERI)
        self.assertEqual(fs.ISLEM_TUR_ETIKET['sayim_farki'], 'Sayım Farkı')


if __name__ == '__main__':
    unittest.main()
