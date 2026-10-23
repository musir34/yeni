"""İşten ayrılan çalışanı arşivle / geri al (calisan_arsivle). Gerçek DB kullanılmaz.

Çalıştırma: cd tests && DISABLE_JOBS=1 python -m unittest test_finans_calisan_arsiv
"""
import unittest
from decimal import Decimal

import test_finans_calisan as base
import finans_service as fs
import finans_calisan_service as ws
from models import FinansCariHareket, FinansCalisanHakedis


class CalisanArsivTest(base.CalisanCariTest):
    def test_bekleyen_hakedis_varken_arsivlenemez(self):
        k = self.plan()   # 02.01 haftası hak edişi 5000 bekliyor
        with self.assertRaisesRegex(fs.FinansHata, 'bekleyen hak ediş'):
            ws.calisan_arsivle(k.id)
        self.assertTrue(k.aktif)
        self.assertTrue(k.calisan_cari.aktif)

    def test_odenmis_calisan_arsivlenir_ve_geri_alinir(self):
        k = self.plan()
        self.ode(k, tutar='5000')   # hafta kapandı, bakiye 0
        self.assertEqual(k.calisan_cari.bakiye, Decimal('0'))
        hareket_sayisi = FinansCariHareket.query.count()

        ws.calisan_arsivle(k.id)
        self.assertFalse(k.aktif)
        self.assertFalse(k.calisan_cari.aktif)
        self.assertTrue(ws.arsivde(k))
        self.assertNotIn(k.calisan_cari, ws.maas_carileri())   # yeni plan listesine düşmez
        self.assertEqual(FinansCariHareket.query.count(), hareket_sayisi)   # geçmişe dokunulmaz
        self.assertEqual(FinansCalisanHakedis.query.count(), 1)
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('5000'))

        ws.calisan_arsivle(k.id, arsiv=False)
        self.assertTrue(k.aktif)
        self.assertTrue(k.calisan_cari.aktif)
        self.assertFalse(ws.arsivde(k))
        self.tutarli()

    def test_calisan_olmayan_plan_arsivlenemez(self):
        k = fs.kalem_ekle('Kira', None, '1000', 'elde', '2026-01', '', '', 1)
        with self.assertRaisesRegex(fs.FinansHata, 'bulunamadı'):
            ws.calisan_arsivle(k.id)

    def test_sadece_pasif_plan_arsiv_sayilmaz(self):
        k = self.plan()
        self.ode(k, tutar='5000')
        fs.kalem_pasif(k.id, aktif=False)   # eski yol: yalnız plan pasif, cari açık
        self.assertFalse(ws.arsivde(k))

    def test_http_arsivle_geri_al_ve_sayfa_render(self):
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
        self.app.jinja_env.filters['ist'] = lambda v, fmt: v.strftime(fmt)
        k = self.plan()
        self.ode(k, tutar='5000')
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=1, role='admin', session_version=1, totp_verified=True)
        with patch('finans._log'), patch('finans_calisan._log'), patch('finans_service.bugun_donem', return_value='2026-01'):
            sayfa = client.get('/finans/ana-gider?donem=2026-01').get_data(as_text=True)
            self.assertIn('Arşivle', sayfa)
            self.assertNotIn('işten ayrılan çalışanlar', sayfa)
            self.assertEqual(client.post(f'/finans/calisan/{k.id}/arsiv', data={'arsiv': '1'}).status_code, 302)
            self.assertTrue(ws.arsivde(k))
            sayfa = client.get('/finans/ana-gider?donem=2026-01').get_data(as_text=True)
            self.assertIn('işten ayrılan çalışanlar (1)', sayfa)
            self.assertIn('Geri Al', sayfa)
            self.assertEqual(client.post(f'/finans/calisan/{k.id}/arsiv', data={'arsiv': '0'}).status_code, 302)
            self.assertFalse(ws.arsivde(k))
            with client.session_transaction() as session:
                session['role'] = 'worker'
            client.post(f'/finans/calisan/{k.id}/arsiv', data={'arsiv': '1'})
            self.assertFalse(ws.arsivde(k))   # yetkisiz kullanıcı arşivleyemez
        self.tutarli()

if __name__ == '__main__':
    unittest.main()
