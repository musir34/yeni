"""Çalışan mesaisi (haftanın hak edişine ek) ve fazla ödeme toleransı regresyonları. Gerçek DB kullanılmaz.

Çalıştırma: python -m unittest discover -s tests -p test_finans_mesai.py
"""
import unittest
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import test_finans_calisan as calisan
import finans_service as fs
import finans_cari_service as cs
import finans_calisan_service as ws
from models import FinansCariHareket

T = datetime(2026, 1, 2, 12)


class MesaiTest(unittest.TestCase):
    """Kurulum ve yardımcılar CalisanCariTest'ten ödünç (miras alınmaz: üst testler iki kez koşmasın)."""
    setUp = calisan.CalisanCariTest.setUp
    tearDown = calisan.CalisanCariTest.tearDown
    plan = calisan.CalisanCariTest.plan
    ode = calisan.CalisanCariTest.ode
    tutarli = calisan.CalisanCariTest.tutarli

    def mesai(self, k, saat='3', tutar='1080', donem='2026-01-02', token=None, aciklama=''):
        return ws.mesai_ekle(k.id, donem, saat, tutar, T, aciklama, 1, token or str(uuid.uuid4()))

    def satir(self, k, donem='2026-01-02'):
        return next(d for d in ws.hakedis_satirlari(cari_id=k.calisan_cari_id) if d['donem'] == donem)

    def test_mesai_hak_edise_eklenir_kasaya_dokunmaz(self):
        k = self.plan()
        h = self.mesai(k, '3', '1080')
        self.assertEqual(h.tutar, Decimal('6080'))
        self.assertEqual(k.calisan_cari.bakiye, Decimal('6080'))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10000'))
        m = FinansCariHareket.query.filter_by(tur='mesai').one()
        self.assertEqual((m.yon, m.tutar, m.hakedis_id), (1, Decimal('1080'), h.id))
        self.assertTrue(m.aciklama.startswith('Mesai 3 saat'))
        d = self.satir(k)
        self.assertEqual((d['hak_tutar'], d['kalan']), (Decimal('6080'), Decimal('6080')))
        self.assertEqual([x.id for x in d['mesailer']], [m.id])
        self.tutarli()

    def test_bucuklu_saat_ve_not(self):
        k = self.plan()
        self.mesai(k, '2,5', '900', aciklama='Pazar')
        m = FinansCariHareket.query.filter_by(tur='mesai').one()
        self.assertIn('Mesai 2.5 saat', m.aciklama)
        self.assertTrue(m.aciklama.endswith('· Pazar'))
        for saat in ('0', '-1', 'abc', ''):
            with self.assertRaises(fs.FinansHata):
                self.mesai(k, saat, '100')
        self.tutarli()

    def test_planli_ama_hakedissiz_haftada_sabit_tutar_once_yazilir(self):
        k = self.plan()
        h = self.mesai(k, '1', '400', donem='2026-01-09')   # henüz hak ediş satırı yok (gelecek hafta)
        self.assertEqual(h.tutar, Decimal('5400'))
        turler = sorted(x.tur for x in FinansCariHareket.query.filter_by(hakedis_id=h.id))
        self.assertEqual(turler, ['hakedis', 'mesai'])
        self.assertEqual(k.calisan_cari.bakiye, Decimal('5000') + Decimal('5400'))
        self.tutarli()

    def test_degisken_planda_once_hak_edis_istenir(self):
        k = self.plan(ad='Veli haftalığı', isim='Veli', tutar='0', degisken=True)
        with self.assertRaises(fs.FinansHata):
            self.mesai(k, '2', '700')
        self.ode(k, hak='4000', expected='')
        h = self.mesai(k, '2', '700')
        self.assertEqual(h.tutar, Decimal('4700'))
        self.tutarli()

    def test_mesai_sonrasi_odeme_ve_cift_istek(self):
        k = self.plan()
        self.mesai(k, '3', '1080')
        token = str(uuid.uuid4())
        self.mesai(k, '1', '300', token=token)
        self.mesai(k, '1', '300', token=token)   # aynı anahtar: tekrar yazmaz
        self.assertEqual(FinansCariHareket.query.filter_by(tur='mesai').count(), 2)
        with self.assertRaises(fs.FinansHata):
            self.mesai(k, '1', '999', token=token)
        h, islem = self.ode(k, '6380', hak='6380', expected='6380')
        self.assertEqual(ws.odenen_tutar(h.id), Decimal('6380'))
        self.assertEqual(k.calisan_cari.bakiye, Decimal('0'))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10000') - Decimal('6380'))
        self.assertFalse(self.satir(k)['bekleyen'])
        self.tutarli()

    def test_mesai_iptali_hak_edisi_dusurur_odenenin_altina_inemez(self):
        k = self.plan()
        self.mesai(k, '3', '1080')
        m = FinansCariHareket.query.filter_by(tur='mesai').one()
        cs.hareket_iptal(m.id, 1)
        h = ws.FinansCalisanHakedis.query.one()
        self.assertEqual(h.tutar, Decimal('5000'))
        self.assertEqual(k.calisan_cari.bakiye, Decimal('5000'))
        self.assertEqual(self.satir(k)['mesailer'], [])
        self.tutarli()
        # Ödenmişse iptal engellenir
        self.mesai(k, '2', '600')
        self.ode(k, '5600', hak='5600', expected='5600')
        m2 = FinansCariHareket.query.filter_by(tur='mesai', iptal=False).one()
        with self.assertRaises(fs.FinansHata):
            cs.hareket_iptal(m2.id, 1)
        self.assertEqual(h.tutar, Decimal('5600'))
        self.tutarli()

    def test_fazla_odeme_hata_vermez_fark_hak_edise_yazilir(self):
        k = self.plan()
        self.mesai(k, '3', '1080')                       # hak ediş 6080
        h, islem = self.ode(k, '6100', hak='6080', expected='6080')
        self.assertEqual(h.tutar, Decimal('6100'))
        self.assertEqual(ws.odenen_tutar(h.id), Decimal('6100'))
        self.assertEqual(k.calisan_cari.bakiye, Decimal('0'))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('3900'))
        fark = FinansCariHareket.query.filter_by(tur='hakedis').order_by(FinansCariHareket.id.desc()).first()
        self.assertEqual(fark.tutar, Decimal('20'))
        self.assertIn('fazla ödeme', fark.aciklama)
        self.assertFalse(self.satir(k)['bekleyen'])
        self.tutarli()

    def test_hesaba_yazma_siniri_korunur(self):
        sahsi = cs.cari_ekle('Ben', 'sahsi', '', '', 1)
        k = self.plan(ad='Benim maaşım', isim='', cari_id=sahsi.id)
        with self.assertRaises(fs.FinansHata):
            ws.hakedis_ve_odeme(k.id, '2026-01-02', '5000', '5100', ws.MAHSUP_HESABI, T, '', 1,
                                str(uuid.uuid4()), '5000')
        self.assertEqual(sahsi.bakiye, Decimal('5000'))
        self.tutarli()

    def test_http_mesai_ve_sayfalar(self):
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
        self.app.jinja_env.globals['sayfa_erisebilir'] = lambda *a, **k: True
        self.app.jinja_env.filters['ist'] = lambda v, fmt: v.strftime(fmt)
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=1, role='admin', session_version=1, totp_verified=True)
        k = self.plan()
        with patch('finans._log'), patch('finans_calisan._log'), patch('finans_service.bugun_donem', return_value='2026-01'):
            response = client.post('/finans/calisan/mesai', data={
                'kalem_id': k.id, 'donem': '2026-01-02', 'saat': '3', 'tutar': '1080',
                'tarih': '2026-01-02', 'aciklama': '', 'odeme_anahtari': str(uuid.uuid4())})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(k.calisan_cari.bakiye, Decimal('6080'))
            for url in ['/finans/ana-gider?donem=2026-01', f'/finans/cari/{k.calisan_cari_id}']:
                with self.subTest(url=url):
                    rendered = client.get(url)
                    self.assertEqual(rendered.status_code, 200)
                    html = rendered.get_data(as_text=True)
                    self.assertIn('fnMesaiModal', html)
                    self.assertIn('Mesai 3 saat', html)
            # Fazla ödeme HTTP üzerinden de hata vermez
            response = client.post('/finans/calisan/hakedis-odeme', data={
                'kalem_id': k.id, 'donem': '2026-01-02', 'hak_tutar': '6080', 'tutar': '6100',
                'hesap': 'elde', 'tarih': '2026-01-02', 'beklenen_hakedis': '6080',
                'odeme_anahtari': str(uuid.uuid4())}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn('Fazla verilen 20.00', html)
            self.assertNotIn('aşamaz', html)
            self.assertEqual(k.calisan_cari.bakiye, Decimal('0'))
            with client.session_transaction() as session:
                session['role'] = 'worker'
            denied = client.post('/finans/calisan/mesai', data={})
            self.assertEqual(denied.status_code, 302)
        self.tutarli()


if __name__ == '__main__':
    unittest.main()
