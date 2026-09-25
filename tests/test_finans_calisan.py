"""Çalışan carisi + hak ediş/kısmi ödeme regresyonları. Gerçek DB kullanılmaz."""
import unittest
from unittest.mock import patch
from datetime import date, datetime
from decimal import Decimal
import uuid

import test_finans_haftalik as base
import finans_service as fs
import finans_cari_service as cs
import finans_calisan_service as ws
from models import db, FinansCari, FinansCariHareket, FinansCalisanHakedis, FinansIslem


class CalisanCariTest(unittest.TestCase):
    def setUp(self):
        base.HaftalikOdemeTest.setUp(self)
        self.clock = patch('finans_calisan_service.to_ist', return_value=datetime(2026, 1, 2, 12))
        self.clock.start()
        # Defter ve kasa başlangıcı birbiriyle tutarlı olsun.
        hesap = fs.hesap_getir('elde')
        hesap.bakiye = 0
        fs._hareket(hesap, 'gelir', 1, Decimal('10000'), datetime(2026, 1, 1), 1)
        db.session.commit()

    def tearDown(self):
        self.clock.stop()
        base.HaftalikOdemeTest.tearDown(self)

    def plan(self, ad='Ahmet haftalığı', isim='Ahmet', tutar='5000', degisken=False, cari_id=None):
        return fs.kalem_ekle(ad, None, tutar, 'elde', '2026-01', '', '', 1,
                             siklik='haftalik', ilk_odeme_tarihi='2026-01-02',
                             tutar_degisken=degisken, calisan=True, calisan_adi=isim,
                             calisan_cari_id=cari_id)

    def ode(self, k, tutar='', hak='5000', donem='2026-01-02', expected='5000', token=None):
        return ws.hakedis_ve_odeme(k.id, donem, hak, tutar, 'elde', datetime(2026, 1, 2, 12),
                                   '', 1, token or str(uuid.uuid4()), expected)

    def guncelle(self, k, **kw):
        args = dict(kalem_id=k.id, ad=k.ad, kategori_id=None, varsayilan_tutar=k.varsayilan_tutar,
                    varsayilan_hesap_kodu='elde', baslangic_donem=k.baslangic_donem,
                    bitis_donem=k.bitis_donem, notlar='', kullanici_id=1)
        args.update(kw)
        return fs.kalem_guncelle(**args)

    def tutarli(self):
        self.assertEqual(cs.cari_tutarlilik_kontrol(), [])
        self.assertEqual(fs.tutarlilik_kontrol(), [])

    def test_auto_cari_and_fixed_accrual_once_no_cash(self):
        k = self.plan()
        self.assertEqual(k.calisan_cari.tur, 'calisan')
        self.assertEqual(k.calisan_cari.bakiye, Decimal('5000'))
        ws.hakedisleri_isle()
        ws.hakedisleri_isle()
        self.assertEqual(FinansCari.query.count(), 1)
        self.assertEqual(FinansCalisanHakedis.query.count(), 1)
        self.assertEqual(FinansCariHareket.query.count(), 1)
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10000'))
        self.tutarli()

    def test_partial_then_remaining_next_week(self):
        k = self.plan()
        h, first = self.ode(k, '3000')
        self.assertEqual(k.calisan_cari.bakiye, Decimal('2000'))
        row = fs.donem_ana_gider_durumu('2026-01')[0]
        self.assertTrue(row['bekleyen'])
        self.assertEqual(row['odenen'], Decimal('3000'))
        self.assertEqual(row['kalan'], Decimal('2000'))
        ws.hakedisleri_isle(date(2026, 1, 9))
        self.assertEqual(k.calisan_cari.bakiye, Decimal('7000'))
        self.ode(k, '2000')
        self.assertEqual(k.calisan_cari.bakiye, Decimal('5000'))
        self.assertFalse(fs.donem_ana_gider_durumu('2026-01')[0]['bekleyen'])
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('5000'))
        self.tutarli()

    def test_no_payment_variable_accrual_and_zero_due(self):
        k = self.plan(degisken=True)
        self.assertEqual(k.calisan_cari.bakiye, Decimal('0'))
        self.assertIsNone(FinansCalisanHakedis.query.one().tutar)
        h, cash = self.ode(k, hak='4500', expected='')
        self.assertIsNone(cash)
        self.assertEqual(k.calisan_cari.bakiye, Decimal('4500'))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10000'))
        self.ode(k, hak='0', expected='4500')
        ws.hakedisleri_isle()
        self.assertEqual(k.calisan_cari.bakiye, Decimal('0'))
        self.assertEqual(h.tutar, Decimal('0'))
        self.tutarli()

    def test_duplicate_request_does_not_double_charge(self):
        k = self.plan()
        token = str(uuid.uuid4())
        _, cash = self.ode(k, '1000', token=token)
        _, retry = self.ode(k, '1000', token=token)
        self.assertEqual(cash.id, retry.id)
        self.assertEqual(k.calisan_cari.bakiye, Decimal('4000'))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('9000'))
        with self.assertRaises(fs.FinansHata):
            self.ode(k, '2000', token=token)
        self.tutarli()

    def test_insufficient_cash_rolls_back_due_change_and_payment(self):
        k = self.plan(degisken=True)
        with self.assertRaises(fs.FinansHata):
            self.ode(k, '11000', hak='15000', expected='')
        self.assertIsNone(FinansCalisanHakedis.query.one().tutar)
        self.assertEqual(k.calisan_cari.bakiye, Decimal('0'))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10000'))
        self.assertEqual(FinansCariHareket.query.count(), 0)
        self.tutarli()

    def test_overpay_and_reduce_below_paid_are_rejected(self):
        k = self.plan()
        self.ode(k, '3000')
        with self.assertRaises(fs.FinansHata):
            self.ode(k, '2500')
        with self.assertRaises(fs.FinansHata):
            self.ode(k, hak='2000')
        self.assertEqual(k.calisan_cari.bakiye, Decimal('2000'))
        self.tutarli()

    def test_cancel_cash_or_cari_restores_debt_and_can_pay_again(self):
        k = self.plan()
        token = str(uuid.uuid4())
        h, cash = self.ode(k, '3000', token=token)
        fs.islem_iptal(cash.id, 1)
        self.assertEqual(k.calisan_cari.bakiye, Decimal('5000'))
        self.assertEqual(ws.odenen_tutar(h.id), Decimal('0'))
        with self.assertRaises(fs.FinansHata):
            self.ode(k, '3000', token=token)
        _, second = self.ode(k, '2000')
        cs.hareket_iptal(second.cari_hareket.id, 1)
        self.assertEqual(k.calisan_cari.bakiye, Decimal('5000'))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10000'))
        self.tutarli()

    def test_hakedis_edit_adjusts_cari_only_and_cannot_direct_cancel(self):
        k = self.plan()
        self.ode(k, '1000')
        self.ode(k, hak='4000')
        self.assertEqual(k.calisan_cari.bakiye, Decimal('3000'))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('9000'))
        hak = FinansCariHareket.query.filter_by(tur='hakedis').first()
        with self.assertRaises(fs.FinansHata):
            cs.hareket_iptal(hak.id, 1)
        with self.assertRaises(fs.FinansHata):
            self.ode(k, hak='5000', expected='5000')  # stale form
        self.tutarli()

    def test_past_due_remains_visible_on_panel_after_month_changes(self):
        k = self.plan()
        self.ode(k, '3000')
        fs.kalem_pasif(k.id)
        summary = fs.donem_ozet('2026-02')
        self.assertEqual(summary['bekleyen_tutar'], Decimal('2000'))
        self.assertEqual(summary['bekleyenler'][0]['donem'], '2026-01-02')
        self.assertEqual(len(ws.hakedis_satirlari(cari_id=k.calisan_cari_id)), 1)
        with self.assertRaises(fs.FinansHata):
            cs.cari_pasif(k.calisan_cari_id)
        self.ode(k, '2000')  # stopped plan's existing debt remains payable
        cs.cari_pasif(k.calisan_cari_id)
        self.tutarli()

    def test_existing_payment_linked_without_second_cash_charge(self):
        k = fs.kalem_ekle('Eski ücret', None, '5000', 'elde', '2026-01', '', '', 1,
                          siklik='haftalik', ilk_odeme_tarihi='2026-01-02')
        old = fs.ana_gider_ode(k.id, '2026-01-02', 'elde', Decimal('4500'), datetime(2026,1,2), '', 1)
        old_count = FinansIslem.query.count()
        self.guncelle(k, calisan=True, calisan_adi='Mehmet')
        ws.hakedisleri_isle()
        self.assertEqual(FinansIslem.query.count(), old_count)
        self.assertEqual(k.calisan_cari.bakiye, Decimal('0'))
        self.assertEqual(ws.hakedis_satirlari(cari_id=k.calisan_cari_id)[0]['hak_tutar'], Decimal('4500'))
        fs.islem_iptal(old.id, 1)
        self.assertEqual(k.calisan_cari.bakiye, Decimal('4500'))
        self.tutarli()

    def test_shared_employee_account_and_name_collision(self):
        k = self.plan()
        other = self.plan(ad='Ahmet ek ücreti', cari_id=k.calisan_cari_id, tutar='500')
        self.assertEqual(k.calisan_cari_id, other.calisan_cari_id)
        self.assertEqual(FinansCari.query.count(), 1)
        self.assertEqual(k.calisan_cari.bakiye, Decimal('5500'))
        cs.cari_ekle('Tedarikçi', 'tedarikci', '', '', 1)
        with self.assertRaises(fs.FinansHata):
            self.plan(ad='Hatalı', isim='Tedarikçi')
        self.assertIsNone(fs.FinansAnaGiderKalem.query.filter_by(ad='Hatalı').first())
        self.tutarli()

    def test_default_change_does_not_rewrite_accrued_amounts(self):
        k = self.plan()
        self.guncelle(k, varsayilan_tutar='6000')
        ws.hakedisleri_isle(date(2026, 1, 9))
        amounts = [d['hak_tutar'] for d in ws.hakedis_satirlari(cari_id=k.calisan_cari_id)]
        self.assertEqual(amounts, [Decimal('5000'), Decimal('6000')])
        self.assertEqual(k.calisan_cari.bakiye, Decimal('11000'))
        self.tutarli()

    def test_variable_to_fixed_does_not_invent_old_week_amount(self):
        k = self.plan(degisken=True)
        self.guncelle(k, tutar_degisken=False, varsayilan_tutar='4000')
        ws.hakedisleri_isle(date(2026, 1, 9))
        amounts = [d['hak_tutar'] for d in ws.hakedis_satirlari(cari_id=k.calisan_cari_id)]
        self.assertEqual(amounts, [None, Decimal('4000')])
        self.ode(k, '1000', hak='3000', expected='')
        self.tutarli()

    def test_employee_payments_cannot_bypass_due_allocation(self):
        k = self.plan()
        with self.assertRaises(fs.FinansHata):
            fs.ana_gider_ode(k.id, '2026-01-02', 'elde', Decimal('100'), datetime(2026,1,2), '', 1)
        with self.assertRaises(fs.FinansHata):
            cs.odeme_yap(k.calisan_cari_id, 'elde', Decimal('100'), datetime(2026,1,2), '', 1)
        with self.assertRaises(fs.FinansHata):
            cs.cari_guncelle(k.calisan_cari_id, 'Ahmet', 'tedarikci', '', '')
        with self.assertRaises(fs.FinansHata):
            self.guncelle(k, calisan=False)
        self.tutarli()

    def test_reports_count_cash_once_not_accrual(self):
        k = self.plan()
        self.ode(k, '3000')
        summary = fs.donem_ozet('2026-01')
        self.assertEqual(summary['cari_odeme'], Decimal('3000'))
        self.assertEqual(summary['ana_gider'], Decimal('0'))
        self.assertEqual(summary['toplam_gider'], Decimal('3000'))
        self.tutarli()

    def test_http_create_pay_and_render_employee_pages(self):
        from pathlib import Path
        from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader, StrictUndefined
        from finans import finans_bp
        self.app.config.update(SECRET_KEY='isolated-test', TESTING=True)
        self.app.register_blueprint(finans_bp)
        self.app.add_url_rule('/', endpoint='home.home', view_func=lambda: 'home')
        self.app.jinja_loader = ChoiceLoader([
            DictLoader({'base.html': '{% block content %}{% endblock %}{% block scripts %}{% endblock %}'}),
            FileSystemLoader(str(Path(__file__).resolve().parents[1] / 'templates'))])
        self.app.jinja_env.undefined = StrictUndefined
        self.app.jinja_env.filters['tl_format'] = lambda v: str(v)
        self.app.jinja_env.filters['ist'] = lambda v, fmt: v.strftime(fmt)
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=1, role='admin', session_version=1, totp_verified=True)
        with patch('finans._log'), patch('finans_calisan._log'), patch('finans_service.bugun_donem', return_value='2026-01'):
            response = client.post('/finans/ana-gider/kalem/ekle', data={
                'ad': 'Ayşe haftalığı', 'siklik': 'haftalik', 'ilk_odeme_tarihi': '2026-01-02',
                'baslangic_donem': '2026-01', 'varsayilan_tutar': '5000', 'varsayilan_hesap_kodu': 'elde',
                'calisan': '1', 'calisan_adi': 'Ayşe', 'tutar_degisken': '0'})
            self.assertEqual(response.status_code, 302)
            k = fs.FinansAnaGiderKalem.query.filter_by(ad='Ayşe haftalığı').one()
            response = client.post('/finans/calisan/hakedis-odeme', data={
                'kalem_id': k.id, 'donem': '2026-01-02', 'hak_tutar': '5000', 'tutar': '3000',
                'hesap': 'elde', 'tarih': '2026-01-02', 'beklenen_hakedis': '5000',
                'odeme_anahtari': str(uuid.uuid4())})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(k.calisan_cari.bakiye, Decimal('2000'))
            for url in ['/finans/', '/finans/ana-gider?donem=2026-01', '/finans/cari',
                        f'/finans/cari/{k.calisan_cari_id}', '/finans/rapor?yil=2026', '/finans/defter/elde?donem=2026-01']:
                with self.subTest(url=url):
                    rendered = client.get(url)
                    self.assertEqual(rendered.status_code, 200)
                    if '/cari/' in url or '/ana-gider?' in url:
                        self.assertIn('Kısmen ödendi', rendered.get_data(as_text=True))
            with client.session_transaction() as session:
                session['role'] = 'worker'
            denied = client.post('/finans/calisan/hakedis-odeme', data={})
            self.assertEqual(denied.status_code, 302)
            self.assertEqual(k.calisan_cari.bakiye, Decimal('2000'))
        self.tutarli()


if __name__ == '__main__':
    unittest.main()
