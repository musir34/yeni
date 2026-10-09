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
from models import db, FinansHesap, FinansCari

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

    def test_calisan_akisi_degismedi(self):
        k = fs.kalem_ekle('Ahmet haftalığı', None, '5000', 'elde', '2026-01', '', '', 1,
                          siklik='haftalik', ilk_odeme_tarihi='2026-01-02', tutar_degisken=False,
                          calisan=True, calisan_adi='Ahmet')
        self.assertEqual(k.calisan_cari.tur, 'calisan')
        self.assertEqual(k.calisan_cari.bakiye, Decimal('5000'))


if __name__ == '__main__':
    unittest.main()
