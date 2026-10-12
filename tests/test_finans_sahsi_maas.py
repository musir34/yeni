"""Şahsi cari hesaba düzenli (haftalık) maaş planı bağlama. Gerçek DB kullanılmaz.

Çalıştırma: .venv/bin/python -m unittest discover -s tests -p test_finans_sahsi_maas.py
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
from models import db, FinansHesap, FinansCari, FinansCariHareket

T = datetime(2026, 1, 5, 12)


class SahsiMaasTest(unittest.TestCase):
    def setUp(self):
        base.HaftalikOdemeTest.setUp(self)
        self.clock = patch('finans_calisan_service.to_ist', return_value=datetime(2026, 1, 2, 12))
        self.clock.start()
        db.session.add(FinansHesap(kod='beyazit', ad='Beyazıt', bakiye=Decimal('0')))
        hesap = fs.hesap_getir('elde')
        hesap.bakiye = 0
        fs._hareket(hesap, 'gelir', 1, Decimal('100000'), datetime(2026, 1, 1), 1)
        db.session.commit()
        self.musir = cs.cari_ekle('Musir — şahsi', 'sahsi', '', '', 1)

    def tearDown(self):
        self.clock.stop()
        base.HaftalikOdemeTest.tearDown(self)

    def plan(self, cari_id, ad='Musir maaşı', tutar='15000'):
        return fs.kalem_ekle(ad, None, tutar, 'elde', '2026-01', '', '', 1,
                             siklik='haftalik', ilk_odeme_tarihi='2026-01-02',
                             tutar_degisken=False, calisan=True, calisan_adi='', calisan_cari_id=cari_id)

    def tutarli(self):
        self.assertEqual(cs.cari_tutarlilik_kontrol(), [])
        self.assertEqual(fs.tutarlilik_kontrol(), [])

    def test_plan_mevcut_sahsi_cariye_baglanir_yeni_cari_acilmaz(self):
        k = self.plan(self.musir.id)
        self.assertEqual(k.calisan_cari_id, self.musir.id)
        self.assertEqual(FinansCari.query.count(), 1)
        self.assertEqual(self.musir.tur, 'sahsi')
        db.session.refresh(self.musir)
        self.assertEqual(self.musir.bakiye, Decimal('15000'))          # hafta hak edişi: işletme ona borçlu
        self.tutarli()

    def test_maas_kasadan_alinan_borcla_mahsuplasir_ve_odenebilir(self):
        cs.odeme_yap(self.musir.id, 'elde', Decimal('4000'), T, 'ev', 1, tur='borc_alma')
        k = self.plan(self.musir.id)
        db.session.refresh(self.musir)
        self.assertEqual(self.musir.bakiye, Decimal('11000'))          # 15000 hak − 4000 kasa borcu
        h, _ = ws.hakedis_ve_odeme(k.id, '2026-01-02', '15000', '11000', 'elde', datetime(2026, 1, 2, 12),
                                   '', 1, str(uuid.uuid4()), '15000')
        db.session.refresh(self.musir)
        self.assertEqual(self.musir.bakiye, Decimal('0'))
        self.assertEqual(ws.odenen_tutar(h.id), Decimal('11000'))
        self.tutarli()

    def test_sahsi_cari_planla_listelenir_ve_hakedis_satirlari_gelir(self):
        self.plan(self.musir.id)
        self.assertIn(self.musir, ws.maas_carileri())
        self.assertEqual([d['donem'] for d in ws.hakedis_satirlari(cari_id=self.musir.id)], ['2026-01-02'])

    def test_tedarikci_dolar_ve_kapali_sahsi_baglanamaz(self):
        t = cs.cari_ekle('Taban Ltd', 'tedarikci', '', '', 1)
        d = cs.cari_ekle('Musir USD', 'sahsi', '', '', 1, para_birimi='USD')
        kapali = cs.cari_ekle('Eski şahsi', 'sahsi', '', '', 1)
        cs.cari_pasif(kapali.id, aktif=False)
        for i, c in enumerate((t, d, kapali)):
            with self.assertRaises(FinansHata):
                self.plan(c.id, ad=f'Plan {i}')
            db.session.rollback()

    def test_planli_sahsi_hesap_kapatilamaz_doviz_ya_da_ture_cevrilemez(self):
        self.plan(self.musir.id)
        with self.assertRaises(FinansHata):
            cs.cari_pasif(self.musir.id, aktif=False)
        with self.assertRaises(FinansHata):
            cs.cari_guncelle(self.musir.id, self.musir.ad, 'sahsi', '', '', para_birimi='USD')
        with self.assertRaises(FinansHata):
            cs.cari_guncelle(self.musir.id, self.musir.ad, 'tedarikci', '', '')

    def mahsup(self, k, tutar, hak='15000', beklenen='15000', token=None):
        return ws.hakedis_ve_odeme(k.id, '2026-01-02', hak, tutar, ws.MAHSUP_HESABI, datetime(2026, 1, 2, 12),
                                   '', 1, token or str(uuid.uuid4()), beklenen)

    def test_borctan_mahsup_haftayi_kapatir_kasaya_dokunmaz(self):
        cs.odeme_yap(self.musir.id, 'elde', Decimal('4000'), T, 'ev', 1, tur='borc_alma')
        elde = fs.hesap_getir('elde').bakiye
        k = self.plan(self.musir.id)
        h, islem = self.mahsup(k, '4000')
        self.assertIsNone(islem)
        self.assertEqual(fs.hesap_getir('elde').bakiye, elde)               # kasadan para çıkmadı
        self.assertEqual(ws.odenen_tutar(h.id), Decimal('4000'))            # hafta 4000 ödenmiş sayılır
        self.assertEqual(cs.sahsi_kasa_borcu(self.musir.id), Decimal('0'))   # kasa borcu kapandı
        db.session.refresh(self.musir)
        self.assertEqual(self.musir.bakiye, Decimal('11000'))               # kalan maaş alacağı
        ws.hakedis_ve_odeme(k.id, '2026-01-02', '15000', '11000', 'elde', datetime(2026, 1, 2, 12),
                            '', 1, str(uuid.uuid4()), '15000')
        self.assertFalse(ws.durum_satiri(k, '2026-01-02', h)['bekleyen'])   # hafta tamamlandı
        db.session.refresh(self.musir)
        self.assertEqual(self.musir.bakiye, Decimal('0'))
        self.tutarli()

    def test_hesaba_yaz_borc_yokken_maas_alacak_olarak_kalir(self):
        k = self.plan(self.musir.id)
        elde = fs.hesap_getir('elde').bakiye
        h, islem = self.mahsup(k, '15000')
        self.assertIsNone(islem)
        self.assertEqual(fs.hesap_getir('elde').bakiye, elde)               # kasadan para çıkmadı
        self.assertFalse(ws.durum_satiri(k, '2026-01-02', h)['bekleyen'])   # hafta kapandı
        db.session.refresh(self.musir)
        self.assertEqual(self.musir.bakiye, Decimal('15000'))               # maaş hesapta alacak
        # Sonra kasadan alınan para bu alacaktan düşer; kasaya borç oluşmaz.
        cs.odeme_yap(self.musir.id, 'elde', Decimal('3000'), T, 'ev', 1, tur='borc_alma')
        db.session.refresh(self.musir)
        self.assertEqual(self.musir.bakiye, Decimal('12000'))
        self.assertEqual(cs.sahsi_kasa_borcu(self.musir.id), Decimal('0'))
        self.tutarli()

    def test_hesaba_yaz_haftanin_kalanini_asamaz(self):
        k = self.plan(self.musir.id)
        with self.assertRaises(FinansHata):
            self.mahsup(k, '15000.01')
        db.session.rollback()
        self.assertEqual(FinansCariHareket.query.filter_by(tur='mahsup').count(), 0)

    def test_mahsup_yalniz_sahsi_hesapta(self):
        k = fs.kalem_ekle('Ahmet haftalığı', None, '5000', 'elde', '2026-01', '', '', 1,
                          siklik='haftalik', ilk_odeme_tarihi='2026-01-02', tutar_degisken=False,
                          calisan=True, calisan_adi='Ahmet')
        with self.assertRaises(FinansHata):
            ws.hakedis_ve_odeme(k.id, '2026-01-02', '5000', '100', ws.MAHSUP_HESABI, datetime(2026, 1, 2, 12),
                                '', 1, str(uuid.uuid4()), '5000')

    def test_mahsup_iptali_iki_tarafi_birlikte_geri_alir(self):
        cs.odeme_yap(self.musir.id, 'elde', Decimal('4000'), T, 'ev', 1, tur='borc_alma')
        k = self.plan(self.musir.id)
        h, _ = self.mahsup(k, '3000')
        for tur in ('odeme', 'mahsup'):     # hangi satırdan iptal edilirse edilsin
            hareket = FinansCariHareket.query.filter_by(tur=tur, iptal=False).one()
            cs.hareket_iptal(hareket.id, 1)
            self.assertEqual(FinansCariHareket.query.filter_by(iptal=False).filter(
                FinansCariHareket.tur.in_(('odeme', 'mahsup'))).count(), 0)
            self.assertEqual(ws.odenen_tutar(h.id), Decimal('0'))
            self.assertEqual(cs.sahsi_kasa_borcu(self.musir.id), Decimal('4000'))
            self.tutarli()
            if tur == 'odeme':
                h, _ = self.mahsup(k, '3000')

    def test_hesaba_yazildiktan_sonra_kasa_borcu_iptal_edilebilir(self):
        borc = cs.odeme_yap(self.musir.id, 'elde', Decimal('4000'), T, 'ev', 1, tur='borc_alma')
        k = self.plan(self.musir.id)
        self.mahsup(k, '4000')
        cs.hareket_iptal(borc.id, 1)                     # hatalı borç kaydı silinince fark alacağa döner
        db.session.refresh(self.musir)
        self.assertEqual(self.musir.bakiye, Decimal('15000'))
        self.assertEqual(cs.sahsi_kasa_borcu(self.musir.id), Decimal('0'))
        self.tutarli()

    def test_mahsupsuz_kasa_borcu_eskisi_gibi_iptal_edilir(self):
        cs.tahsilat_al(self.musir.id, Decimal('5000'), T, '', 1, tur='borc_odeme')   # fazla yatırma (eski davranış)
        borc = cs.odeme_yap(self.musir.id, 'elde', Decimal('1000'), T, '', 1, tur='borc_alma')
        cs.hareket_iptal(borc.id, 1)
        self.tutarli()

    def test_defterde_hesaba_yazma_tek_satir_gorunur(self):
        k = self.plan(self.musir.id)
        self.mahsup(k, '15000')
        turler = [h.tur for h in cs.hareketler(self.musir.id).items]
        self.assertEqual(turler, ['hakedis'])                               # ikili gizli, hak ediş satırı kalır
        hak = FinansCariHareket.query.filter_by(tur='hakedis').one()
        yazilan = cs.hesaba_yazilanlar(self.musir.id)
        self.assertEqual(yazilan[hak.hakedis_id]['tutar'], Decimal('15000'))
        mahsup = FinansCariHareket.query.filter_by(tur='mahsup').one()
        self.assertEqual(yazilan[hak.hakedis_id]['iptal_id'], mahsup.id)    # geri al düğmesi ikiliyi iptal eder
        cs.hareket_iptal(yazilan[hak.hakedis_id]['iptal_id'], 1)
        self.assertEqual(cs.hesaba_yazilanlar(self.musir.id), {})
        # Kasadan gerçekten ödenen maaş satırı gizlenmez.
        ws.hakedis_ve_odeme(k.id, '2026-01-09', '15000', '1000', 'elde', datetime(2026, 1, 9, 12),
                            '', 1, str(uuid.uuid4()), '15000')
        self.assertIn('odeme', [h.tur for h in cs.hareketler(self.musir.id).items])

    def test_hesap_sayfasi_hesaba_yazmayi_hak_edis_satirinda_tek_satir_basar(self):
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
        self.app.jinja_env.filters['ist'] = lambda v, fmt='%d.%m.%Y %H:%M': v.strftime(fmt)
        k = self.plan(self.musir.id)
        self.mahsup(k, '15000')
        mahsup_id = FinansCariHareket.query.filter_by(tur='mahsup').one().id
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=1, role='admin', session_version=1, totp_verified=True)
        html = client.get(f'/finans/cari/{self.musir.id}').get_data(as_text=True)
        defter = html[html.index('Hesap defteri'):]
        self.assertEqual(defter.count('Hesaba yazıldı</span>'), 1)
        self.assertNotIn('Maaş hesaba yazıldı', defter)                     # ikili ayrı satır olarak basılmaz
        self.assertIn(f'/finans/cari/hareket/{mahsup_id}/iptal', defter)     # geri al düğmesi hak ediş satırında

    def test_mahsup_cift_tiklama_tekrar_yazmaz(self):
        cs.odeme_yap(self.musir.id, 'elde', Decimal('4000'), T, 'ev', 1, tur='borc_alma')
        k = self.plan(self.musir.id)
        token = str(uuid.uuid4())
        self.mahsup(k, '1000', token=token)
        self.mahsup(k, '1000', token=token)
        self.assertEqual(FinansCariHareket.query.filter_by(tur='mahsup').count(), 1)
        self.assertEqual(cs.sahsi_kasa_borcu(self.musir.id), Decimal('3000'))

    def test_calisan_akisi_degismedi(self):
        k = fs.kalem_ekle('Ahmet haftalığı', None, '5000', 'elde', '2026-01', '', '', 1,
                          siklik='haftalik', ilk_odeme_tarihi='2026-01-02', tutar_degisken=False,
                          calisan=True, calisan_adi='Ahmet')
        self.assertEqual(k.calisan_cari.tur, 'calisan')
        self.assertEqual(k.calisan_cari.bakiye, Decimal('5000'))


if __name__ == '__main__':
    unittest.main()
