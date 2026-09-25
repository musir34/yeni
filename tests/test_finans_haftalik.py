"""İzole SQLite testleri; app.py/.env veya gerçek veritabanını açmaz.

Çalıştırma: .venv/bin/python -m unittest discover -s tests -p test_finans_haftalik.py
"""
import unittest
from datetime import date, datetime
from decimal import Decimal

from flask import Flask
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import finans_service as fs
from models import (db, User, FinansHesap, FinansKategori, FinansGiderAdi,
                    FinansAnaGiderKalem, FinansIslem, FinansCari,
                    FinansCariHareket, FinansCariKalem, FinansCalisanHakedis)


class HaftalikOdemeTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        tables = [m.__table__ for m in (User, FinansHesap, FinansKategori, FinansGiderAdi,
                  FinansAnaGiderKalem, FinansIslem, FinansCari, FinansCariHareket, FinansCariKalem, FinansCalisanHakedis)]
        db.metadata.create_all(db.engine, tables=tables)
        db.session.execute(text("CREATE UNIQUE INDEX uq_test_kalem_donem ON finans_islem "
                                "(kalem_id, donem) WHERE tur = 'ana_gider' AND iptal = FALSE"))
        db.session.add(User(id=1, first_name='Test', last_name='User', username='test',
                            email='test@example.invalid', password='unused'))
        db.session.add(FinansHesap(kod='elde', ad='Elde', bakiye=Decimal('10000')))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.ctx.pop()

    def plan(self, ad='Haftalık işçilik', tutar='100', ilk='2026-01-02', degisken=False):
        return fs.kalem_ekle(ad, None, tutar, 'elde', ilk[:7], '', '', 1,
                              siklik='haftalik', ilk_odeme_tarihi=ilk, tutar_degisken=degisken)

    def ode(self, k, donem, tutar='100', tarih=datetime(2026, 1, 15, 12)):
        return fs.ana_gider_ode(k.id, donem, 'elde', Decimal(tutar), tarih, '', 1)

    def guncelle(self, k, **kw):
        args = dict(kalem_id=k.id, ad=k.ad, kategori_id=None, varsayilan_tutar=k.varsayilan_tutar,
                    varsayilan_hesap_kodu='elde', baslangic_donem=k.baslangic_donem,
                    bitis_donem=k.bitis_donem, notlar='')
        args.update(kw)
        return fs.kalem_guncelle(**args)

    def test_five_payment_month_and_year_boundary(self):
        k = self.plan(ilk='2025-12-26')
        self.assertEqual(fs.kalem_odeme_donemleri(k, '2026-01'),
                         ['2026-01-02', '2026-01-09', '2026-01-16', '2026-01-23', '2026-01-30'])
        self.assertEqual(fs.kalem_odeme_donemleri(k, '2026-02'),
                         ['2026-02-06', '2026-02-13', '2026-02-20', '2026-02-27'])

    def test_midmonth_start_leap_day_and_end(self):
        k = self.plan(ilk='2024-02-22')
        self.assertEqual(fs.kalem_odeme_donemleri(k, '2024-02'), ['2024-02-22', '2024-02-29'])
        self.guncelle(k, bitis_donem='2024-02')
        self.assertEqual(fs.kalem_odeme_donemleri(k, '2024-03'), [])
        self.assertEqual(fs.kalem_odeme_donemleri(k, '2024-01'), [])

    def test_fixed_default_is_editable_for_each_week(self):
        k = self.plan()
        self.ode(k, '2026-01-02', '125')
        self.ode(k, '2026-01-09', '90')
        self.assertEqual(k.varsayilan_tutar, Decimal('100'))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('9785'))
        rows = fs.donem_ana_gider_durumu('2026-01')
        self.assertEqual(len(rows), 5)
        self.assertEqual(sum(r['odeme'] is not None for r in rows), 2)
        self.assertEqual(fs.donem_ozet('2026-01')['bekleyen_tutar'], Decimal('300'))

    def test_variable_amounts_are_unknown_not_zero_payments(self):
        k = self.plan(degisken=True, tutar='999')
        summary = fs.donem_ozet('2026-01')
        self.assertEqual(summary['bekleyen_belirsiz_adet'], 5)
        self.assertEqual(summary['bekleyen_tutar'], Decimal('0'))
        self.ode(k, '2026-01-02', '150')
        self.ode(k, '2026-01-09', '275')
        self.assertEqual(fs.donem_ozet('2026-01')['bekleyen_belirsiz_adet'], 3)
        self.assertEqual(fs.donem_ozet('2026-01')['ana_gider'], Decimal('425'))
        self.assertEqual(k.varsayilan_tutar, Decimal('0'))

    def test_duplicate_payment_cancel_and_repay(self):
        k = self.plan()
        payment = self.ode(k, '2026-01-02')
        with self.assertRaises(fs.FinansHata):
            self.ode(k, '2026-01-02')
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('9900'))
        fs.islem_iptal(payment.id, 1)
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10000'))
        self.assertIsNone(fs.donem_ana_gider_durumu('2026-01')[0]['odeme'])
        self.ode(k, '2026-01-02', '130')
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('9870'))

    def test_database_duplicate_constraint(self):
        k = self.plan()
        payment = self.ode(k, '2026-01-02')
        duplicate = FinansIslem(hesap_id=payment.hesap_id, tur='ana_gider', yon=-1, tutar=100,
                                onceki_bakiye=9900, yeni_bakiye=9800, kalem_id=k.id,
                                donem=payment.donem, tarih=payment.tarih, kullanici_id=1)
        db.session.add(duplicate)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        self.assertEqual(FinansIslem.query.count(), 1)

    def test_invalid_period_date_amount_and_balance_do_not_write(self):
        k = self.plan()
        for period, amount in [('2026-01', '100'), ('2026-01-03', '100'),
                               ('2025-12-26', '100'), ('2026-02-30', '100'),
                               ('2026-01-02', '0'), ('2026-01-02', '-1'),
                               ('2026-01-02', '10001')]:
            with self.subTest(period=period, amount=amount):
                with self.assertRaises(fs.FinansHata):
                    self.ode(k, period, amount)
        self.assertEqual(FinansIslem.query.count(), 0)
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10000'))

    def test_legacy_monthly_and_conversion_preserve_paid_history(self):
        k = fs.kalem_ekle('Kira', None, '1000', 'elde', '2025-12', '', '', 1)
        old = self.ode(k, '2025-12', '1000')
        old_id = old.id
        with self.assertRaises(fs.FinansHata):
            self.guncelle(k, siklik='haftalik', ilk_odeme_tarihi='2025-12-26')
        self.guncelle(k, siklik='haftalik', ilk_odeme_tarihi='2026-01-02')
        self.assertEqual(fs.donem_ana_gider_durumu('2025-12')[0]['odeme'].id, old_id)
        self.assertEqual(len(fs.donem_ana_gider_durumu('2026-01')), 5)
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('9000'))

    def test_weekly_correction_keeps_target_week_and_actual_date_reporting(self):
        k = self.plan()
        payment = self.ode(k, '2026-01-30', '100', datetime(2026, 2, 2, 12))
        replacement = fs.islem_duzelt(payment.id, 1, yeni_tutar=Decimal('180'))
        self.assertEqual(replacement.donem, '2026-01-30')
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('9820'))
        self.assertEqual(fs.donem_ozet('2026-01')['ana_gider'], Decimal('0'))
        self.assertEqual(fs.donem_ozet('2026-02')['ana_gider'], Decimal('180'))
        self.assertEqual(fs.donem_ana_gider_durumu('2026-01')[-1]['odeme'].id, replacement.id)

    def test_schedule_changes_cannot_reopen_paid_weeks(self):
        k = self.plan()
        self.ode(k, '2026-01-02')
        with self.assertRaises(fs.FinansHata):
            self.guncelle(k, ilk_odeme_tarihi='2026-01-03')
        with self.assertRaises(fs.FinansHata):
            self.guncelle(k, siklik='aylik')
        self.guncelle(k, tutar_degisken=True)
        self.assertEqual(fs.donem_ana_gider_durumu('2026-01')[0]['odeme'].tutar, Decimal('100'))

    def test_closed_plan_still_shows_paid_history(self):
        k = self.plan()
        payment = self.ode(k, '2026-01-02')
        fs.kalem_pasif(k.id)
        rows = fs.donem_ana_gider_durumu('2026-01')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['odeme'].id, payment.id)

    def test_invalid_schedule_and_monthly_default(self):
        for opts in [dict(siklik='gunluk'), dict(siklik='haftalik', ilk_odeme_tarihi=''),
                     dict(siklik='haftalik', ilk_odeme_tarihi='2026-02-30')]:
            with self.assertRaises(fs.FinansHata):
                fs.kalem_ekle('Hatalı', None, '100', 'elde', '2026-01', '', '', 1, **opts)
        k = fs.kalem_ekle('Aylık', None, '100', 'elde', '2026-01', '', '', 1)
        self.assertEqual(fs.kalem_odeme_donemleri(k, '2026-01'), ['2026-01'])
        self.ode(k, '2026-01')
        with self.assertRaises(fs.FinansHata):
            self.ode(k, '2026-01')


if __name__ == '__main__':
    unittest.main()
