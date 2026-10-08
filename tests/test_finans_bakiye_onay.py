"""Yetersiz bakiye: sert hata değil, "Emin misin?" onayı (komutan emri 2026-10-08).

Onaysız → YetersizBakiye (FinansHata alt sınıfı, eski except'ler yakalar); form bakiye_onay=1 ile → işlem
yapılır, bakiye eksiye düşer. İzole SQLite; gerçek DB/app yok.
Çalıştırma: DISABLE_JOBS=1 .venv/bin/python -m pytest --noconftest tests/test_finans_bakiye_onay.py
"""
import unittest
from datetime import datetime
from decimal import Decimal

import test_finans_haftalik as base
import finans_service as fs
from models import db


class BakiyeOnayTest(base.HaftalikOdemeTest):
    def test_onaysiz_yetersiz_bakiye_onay_ister(self):
        hesap = fs.hesap_getir('elde')
        with self.assertRaises(fs.YetersizBakiye) as cm:
            fs._hareket(hesap, 'kucuk_gider', -1, Decimal('12000'), datetime(2026, 1, 2), 1)
        self.assertIsInstance(cm.exception, fs.FinansHata)       # mevcut except FinansHata blokları yakalar
        self.assertIn('-2000.00', str(cm.exception))
        self.assertEqual(Decimal(str(fs.hesap_getir('elde').bakiye)), Decimal('10000'))

    def test_onayli_istek_bakiyeyi_eksiye_dusurur(self):
        with self.app.test_request_context('/finans/kucuk-gider', method='POST', data={'bakiye_onay': '1'}):
            hesap = fs.hesap_getir('elde')
            islem = fs._hareket(hesap, 'kucuk_gider', -1, Decimal('12000'), datetime(2026, 1, 2), 1)
            db.session.commit()
        self.assertEqual(Decimal(str(islem.yeni_bakiye)), Decimal('-2000'))
        self.assertEqual(Decimal(str(fs.hesap_getir('elde').bakiye)), Decimal('-2000'))

    def test_onay_bayragi_json_ile_de_gecerli(self):
        with self.app.test_request_context('/finans/x', method='POST', json={'bakiye_onay': 1}):
            self.assertTrue(fs.bakiye_asimi_onayli())
        with self.app.test_request_context('/finans/x', method='POST', data={'bakiye_onay': '0'}):
            self.assertFalse(fs.bakiye_asimi_onayli())
        self.assertFalse(fs.bakiye_asimi_onayli())              # istek bağlamı yok (betik/test)

    def test_iptal_eksiye_dusurecekse_onay_ister(self):
        hesap = fs.hesap_getir('elde')
        gelir = fs._hareket(hesap, 'gelir', +1, Decimal('5000'), datetime(2026, 1, 2), 1)
        fs._hareket(hesap, 'kucuk_gider', -1, Decimal('14000'), datetime(2026, 1, 3), 1)  # 10000+5000-14000 = 1000
        db.session.commit()
        with self.assertRaises(fs.YetersizBakiye):
            fs.islem_iptal(gelir.id, 1)                           # 1000-5000 = -4000 → onay
        with self.app.test_request_context('/finans/x', method='POST', data={'bakiye_onay': '1'}):
            fs.islem_iptal(gelir.id, 1)
        self.assertEqual(Decimal(str(fs.hesap_getir('elde').bakiye)), Decimal('-4000'))


if __name__ == '__main__':
    unittest.main()
