"""Cari ödeme küsuratı: 2997 ₺ borca 3000 ₺ ödenince 3 ₺ alacak kalmaz, 'yuvarlama' ile sıfırlanır.
Gerçek DB kullanılmaz.

Çalıştırma: DISABLE_JOBS=1 PYTHONUTF8=1 PYTHONPATH=. python -m unittest discover -s tests -p test_finans_cari_yuvarlama.py
"""
import unittest
from datetime import datetime
from decimal import Decimal

import test_finans_haftalik as base
import finans_service as fs
import finans_cari_service as cs
from finans_service import FinansHata
from models import db, FinansHesap, FinansCariHareket

T = datetime(2026, 1, 5, 12)


class CariYuvarlamaTest(unittest.TestCase):
    def setUp(self):
        base.HaftalikOdemeTest.setUp(self)
        db.session.add(FinansHesap(kod='beyazit', ad='Beyazıt', bakiye=Decimal('0')))
        hesap = fs.hesap_getir('elde')   # defter ↔ kasa tutarlı başlasın (tutarlilik_kontrol için)
        hesap.bakiye = 0
        fs._hareket(hesap, 'gelir', 1, Decimal('10000'), datetime(2026, 1, 1), 1)
        db.session.commit()

    def tearDown(self):
        base.HaftalikOdemeTest.tearDown(self)

    def tedarikci(self, ad='Mahmut Zikzak', para_birimi='TRY'):
        return cs.cari_ekle(ad, 'tedarikci', '', '', 1, para_birimi=para_birimi)

    def borclan(self, c, tutar):
        return cs.mal_girisi(c.id, cs.parse_kalemler(['Deri'], ['1'], [tutar]), T, '', 1)

    def tutarli(self):
        self.assertEqual(cs.cari_tutarlilik_kontrol(), [])
        self.assertEqual(fs.tutarlilik_kontrol(), [])

    def test_kucuk_fazla_odeme_kusurat_olarak_kapanir(self):
        c = self.tedarikci()
        self.borclan(c, '2997')
        h = cs.odeme_yap(c.id, 'elde', Decimal('3000'), T, '', 1)
        self.assertEqual(c.bakiye, Decimal('0'))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('7000'))   # kasadan gerçek 3000 çıktı
        yuv = cs.yuvarlama_bul(h)
        self.assertIsNotNone(yuv)
        self.assertEqual((yuv.tur, yuv.tutar, yuv.yon), ('yuvarlama', Decimal('3.00'), 1))
        self.assertIsNone(yuv.islem_id)
        self.assertIn('küsurat', yuv.aciklama)
        self.tutarli()

    def test_odeme_iptal_edilince_kusurat_da_geri_alinir(self):
        c = self.tedarikci()
        self.borclan(c, '2997')
        h = cs.odeme_yap(c.id, 'elde', Decimal('3000'), T, '', 1)
        cs.hareket_iptal(h.id, 1)
        self.assertEqual(c.bakiye, Decimal('2997'))
        self.assertTrue(cs.yuvarlama_bul(h) is None)
        self.assertTrue(all(x.iptal for x in FinansCariHareket.query.filter_by(tur='yuvarlama').all()))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10000'))
        self.tutarli()

    def test_kasa_defterinden_iptal_de_kusurati_geri_alir(self):
        c = self.tedarikci()
        self.borclan(c, '2997')
        h = cs.odeme_yap(c.id, 'elde', Decimal('3000'), T, '', 1)
        fs.islem_iptal(h.islem_id, 1)
        self.assertEqual(c.bakiye, Decimal('2997'))
        self.tutarli()

    def test_sinir_ustu_fazla_odeme_alacak_olarak_kalir(self):
        c = self.tedarikci()
        self.borclan(c, '2950')
        h = cs.odeme_yap(c.id, 'elde', Decimal('3000'), T, '', 1)
        self.assertEqual(c.bakiye, Decimal('-50'))
        self.assertIsNone(cs.yuvarlama_bul(h))

    def test_borcsuz_hesaba_kucuk_on_odeme_yuvarlanmaz(self):
        c = self.tedarikci()
        h = cs.odeme_yap(c.id, 'elde', Decimal('5'), T, '', 1)
        self.assertEqual(c.bakiye, Decimal('-5'))
        self.assertIsNone(cs.yuvarlama_bul(h))

    def test_tam_odeme_yuvarlama_satiri_uretmez(self):
        c = self.tedarikci()
        self.borclan(c, '2997')
        cs.odeme_yap(c.id, 'elde', Decimal('2997'), T, '', 1)
        self.assertEqual(c.bakiye, Decimal('0'))
        self.assertEqual(FinansCariHareket.query.filter_by(tur='yuvarlama').count(), 0)

    def test_usd_caride_yuvarlama_yok(self):
        c = self.tedarikci('Dolarcı', para_birimi='USD')
        self.borclan(c, '97')
        h = cs.odeme_yap(c.id, 'elde', Decimal('100'), T, '', 1, kur=Decimal('30'))
        self.assertEqual(c.bakiye, Decimal('-3'))
        self.assertIsNone(cs.yuvarlama_bul(h))
        self.assertFalse(cs.yuvarlama_uygun(c))

    def test_elle_kusurat_kapatma_eski_kayitlar_icin(self):
        c = self.tedarikci()
        c.bakiye = Decimal('-3.00')   # eski fazla ödemeden kalan alacak
        cs._cari_hareket(c, 'odeme', Decimal('3'), T, 'eski', 1)   # defter tutarlı kalsın (-3 → -6 → düzelt)
        c.bakiye = Decimal('-3.00')
        db.session.commit()
        self.assertTrue(cs.yuvarlama_uygun(c))
        h = cs.yuvarlama_kapat(c.id, T, 1)
        self.assertEqual(c.bakiye, Decimal('0'))
        self.assertEqual((h.tur, h.tutar), ('yuvarlama', Decimal('3.00')))
        self.assertFalse(cs.yuvarlama_uygun(c))
        with self.assertRaises(FinansHata):
            cs.yuvarlama_kapat(c.id, T, 1)

    def test_sahsi_ve_buyuk_alacakta_elle_kapatma_reddedilir(self):
        s = cs.cari_ekle('Musir — şahsi', 'sahsi', '', '', 1)
        cs.odeme_yap(s.id, 'elde', Decimal('5'), T, '', 1, tur='borc_alma')
        self.assertFalse(cs.yuvarlama_uygun(s))
        with self.assertRaises(FinansHata):
            cs.yuvarlama_kapat(s.id, T, 1)
        c = self.tedarikci()
        cs.odeme_yap(c.id, 'elde', Decimal('50'), T, '', 1)
        with self.assertRaises(FinansHata):
            cs.yuvarlama_kapat(c.id, T, 1)

    def test_http_detay_sayfasi_kusurat_dugmesi_ve_rota(self):
        from pathlib import Path
        from unittest.mock import patch
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
        self.app.jinja_env.globals['sayfa_erisebilir'] = lambda *a, **k: True
        self.app.jinja_env.filters['ist'] = lambda v, fmt='%d.%m.%Y': v.strftime(fmt)
        c = self.tedarikci()
        cs.odeme_yap(c.id, 'elde', Decimal('3'), T, '', 1)   # borçsuz ön ödeme → -3 alacak (eski durum)
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=1, role='admin', session_version=1, totp_verified=True)
        with patch('finans._log'), patch('finans_cari._log'):
            sayfa = client.get(f'/finans/cari/{c.id}').get_data(as_text=True)
            self.assertIn('Küsuratı Kapat', sayfa)
            self.assertEqual(client.post(f'/finans/cari/{c.id}/yuvarlama', data={'tarih': '2026-01-05'}).status_code, 302)
            self.assertEqual(c.bakiye, Decimal('0'))
            sayfa = client.get(f'/finans/cari/{c.id}').get_data(as_text=True)
            self.assertNotIn('Küsuratı Kapat', sayfa)
            self.assertIn('Küsurat kapatıldı', sayfa)
            self.borclan(c, '2997')
            r = client.post(f'/finans/cari/{c.id}/odeme', data={'hesap': 'elde', 'tutar': '3000', 'tarih': '2026-01-05'},
                            follow_redirects=True)
            self.assertIn('küsurat olarak kapatıldı', r.get_data(as_text=True))
            self.assertEqual(c.bakiye, Decimal('0'))
        self.tutarli()


if __name__ == '__main__':
    unittest.main()
