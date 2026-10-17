"""Alissa ↔ Finans cari köprüsü testleri — izole SQLite; gerçek DB/Trendyol yok.

Çalıştırma: python -m unittest alissa.tests.test_cari
"""
import unittest
from datetime import date, datetime
from decimal import Decimal

from flask import Flask

import finans_service as fs
import finans_cari_service as cs
from finans_service import FinansHata
from models import (db, User, FinansHesap, FinansKategori, FinansGiderAdi, FinansAnaGiderKalem,
                    FinansIslem, FinansCari, FinansCariHareket, FinansCariKalem, FinansCalisanHakedis)
from alissa import ayar, cari, hesap
from alissa.models import TABLOLAR, AlissaHareket, AlissaOdeme, AlissaCariHafta

H1, H2 = date(2026, 9, 7), date(2026, 9, 14)          # Pazartesiler
T = datetime(2026, 9, 20, 12)


class CariKoprusuTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        finans = (User, FinansHesap, FinansKategori, FinansGiderAdi, FinansAnaGiderKalem, FinansIslem,
                  FinansCari, FinansCariHareket, FinansCariKalem, FinansCalisanHakedis)
        db.metadata.create_all(db.engine, tables=[m.__table__ for m in finans + TABLOLAR])
        db.session.add(User(id=1, first_name='Test', last_name='User', username='test',
                            email='test@example.invalid', password='unused', role='admin'))
        for kod, ad, sira, acilis in (('beyazit', 'Beyazıt', 1, '5000'), ('elde', 'Elde', 2, '10000'),
                                      ('banka', 'Banka', 3, '3000')):
            db.session.add(FinansHesap(kod=kod, ad=ad, bakiye=Decimal('0'), sira=sira))
            db.session.flush()
            # Açılış bakiyesi defterle tutarlı olsun (tutarlilik_kontrol)
            fs._hareket(fs.hesap_getir(kod), 'gelir', 1, Decimal(acilis), datetime(2026, 9, 1), 1)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.ctx.pop()

    def satir(self, kimlik, hafta, tutar, tur='satis'):
        db.session.add(AlissaHareket(tur=tur, kaynak_id=str(kimlik), order_number=f'S{kimlik}',
                                     islem_tarihi=datetime.combine(hafta, datetime.min.time()).replace(hour=10),
                                     adet=1, brut=Decimal(tutar), komisyon=0, tutar=Decimal(tutar)))
        db.session.commit()

    def acik_hakedisler(self, c):
        return (FinansCariHareket.query.filter_by(cari_id=c.id, iptal=False)
                .filter(FinansCariHareket.tur.in_(cs.ALISSA_TURLERI)).all())

    def tutarli(self):
        self.assertEqual(cs.cari_tutarlilik_kontrol(), [])
        self.assertEqual(fs.tutarlilik_kontrol(), [])

    # ── cari açma / bağlama ──
    def test_cari_otomatik_acilir_ve_ayarda_tutulur(self):
        c = cari.esitle(1)
        self.assertEqual((c.ad, c.tur, c.para_birimi, c.aktif), ('Muhammet Alissa', 'tedarikci', 'TRY', True))
        self.assertEqual(ayar.oku(cari.AYAR_CARI_ID), str(c.id))
        self.assertIs(cari.esitle(1), cs.cari_getir(c.id))
        self.assertEqual(FinansCari.query.count(), 1)

    def test_finansta_elle_acilmis_ayni_adli_cari_kullanilir(self):
        elle = cs.cari_ekle('MUHAMMET ALİSSA', 'tedarikci', '', '', 1)
        self.assertEqual(cari.esitle(1).id, elle.id)
        self.assertEqual(FinansCari.query.count(), 1)

    # ── haftalık hak ediş ──
    def test_her_hafta_tek_satir_ve_bakiye_toplam_net(self):
        self.satir(1, H1, '1000')
        self.satir(2, H1, '500')
        self.satir(3, H2, '700')
        c = cari.esitle(1)
        acik = self.acik_hakedisler(c)
        self.assertEqual(sorted(h.tutar for h in acik), [Decimal('700'), Decimal('1500')])
        self.assertEqual(c.bakiye, Decimal('2200'))
        self.assertEqual({k.hafta_basi: k.tutar for k in AlissaCariHafta.query}, {H1: Decimal('1500'), H2: Decimal('700')})
        self.assertIn('07.09.2026–13.09.2026', next(h.aciklama for h in acik if h.tutar == 1500))
        self.tutarli()

    def test_degismeyen_hafta_dokunulmaz(self):
        self.satir(1, H1, '1000')
        cari.esitle(1)
        once = [h.id for h in FinansCariHareket.query.all()]
        cari.esitle(1)
        self.assertEqual([h.id for h in FinansCariHareket.query.all()], once)

    def test_hafta_degisince_eski_satir_iptal_tamami_yeniden_yazilir(self):
        self.satir(1, H1, '1000')
        c = cari.esitle(1)
        self.satir(2, H1, '-300', tur='iade')          # aynı haftaya iade geldi
        c = cari.esitle(1)
        acik = self.acik_hakedisler(c)
        self.assertEqual([h.tutar for h in acik], [Decimal('700')])
        self.assertEqual(FinansCariHareket.query.filter_by(cari_id=c.id, iptal=True).count(), 1)
        self.assertEqual(c.bakiye, Decimal('700'))
        self.tutarli()

    def test_eksi_hafta_duzeltme_satiri_sifir_hafta_satirsiz(self):
        self.satir(1, H1, '-250', tur='iade')
        self.satir(2, H2, '100')
        self.satir(3, H2, '-100', tur='iade')
        c = cari.esitle(1)
        acik = self.acik_hakedisler(c)
        self.assertEqual([(h.tur, h.tutar) for h in acik], [('alissa_hakedis_duzeltme', Decimal('250'))])
        self.assertEqual(c.bakiye, Decimal('-250'))
        self.assertIsNone(AlissaCariHafta.query.get(H2).hareket_id)
        self.tutarli()

    def test_alissa_hakedisi_finanstan_elle_iptal_edilemez(self):
        self.satir(1, H1, '1000')
        c = cari.esitle(1)
        h = self.acik_hakedisler(c)[0]
        with self.assertRaises(FinansHata):
            cs.hareket_iptal(h.id, 1)
        self.assertFalse(FinansCariHareket.query.get(h.id).iptal)

    # ── ödemeler ──
    def test_alissa_sayfasindan_odeme_kasadan_duser_ve_iptal_geri_alir(self):
        self.satir(1, H1, '1000')
        c = cari.esitle(1)
        h = cari.odeme_yap(c, 'banka', Decimal('600'), T, '', 1)
        self.assertEqual((h.tur, h.islem.hesap.kod, h.islem.tur), ('odeme', 'banka', 'cari_odeme'))
        self.assertEqual(fs.hesap_getir('banka').bakiye, Decimal('2400'))
        self.assertEqual(cari.odenen(c), Decimal('600'))
        self.assertEqual(c.bakiye, Decimal('400'))
        ozet = hesap.haftalik(date(2026, 9, 30), odenen=cari.odenen(c))
        self.assertEqual(ozet['bakiye'], c.bakiye)
        self.tutarli()
        cari.odeme_iptal(c, h.id, 1)
        self.assertEqual(fs.hesap_getir('banka').bakiye, Decimal('3000'))
        self.assertEqual(cari.odenen(c), Decimal('0'))
        self.assertEqual(cs.cari_getir(c.id).bakiye, Decimal('1000'))
        self.assertEqual([o.iptal for o in cari.odemeler(c)], [True])
        self.tutarli()

    def test_beyazittan_dogrudan_odeme_yapilabilir(self):
        self.satir(1, H1, '1000')
        c = cari.esitle(1)
        h = cari.odeme_yap(c, 'beyazit', Decimal('1000'), T, 'haftalık', 1)
        self.assertEqual(h.islem.hesap.kod, 'beyazit')
        self.assertEqual(fs.hesap_getir('beyazit').bakiye, Decimal('4000'))
        self.assertEqual(c.bakiye, Decimal('0'))
        with self.assertRaises(FinansHata):
            cari.odeme_yap(c, '', Decimal('10'), T, '', 1)      # hesap seçilmedi

    def test_finans_caridan_yapilan_odeme_alissada_gorunur(self):
        self.satir(1, H1, '1000')
        c = cari.esitle(1)
        cs.odeme_yap(c.id, 'elde', Decimal('250'), T, '', 1)          # /finans/cari/<id> "Ödeme Yap"
        self.assertEqual(cari.odenen(c), Decimal('250'))
        self.assertEqual([o.tutar for o in cari.odemeler(c)], [Decimal('250')])

    def test_baska_carinin_hareketi_alissadan_iptal_edilemez(self):
        baska = cs.cari_ekle('Deri Ltd', 'tedarikci', '', '', 1)
        cs.mal_girisi(baska.id, cs.parse_kalemler(['Deri'], ['1'], ['100']), T, '', 1)
        yabanci = cs.odeme_yap(baska.id, 'elde', Decimal('100'), T, '', 1)
        c = cari.esitle(1)
        with self.assertRaises(FinansHata):
            cari.odeme_iptal(c, yabanci.id, 1)
        self.assertFalse(FinansCariHareket.query.get(yabanci.id).iptal)

    # ── bağlantı öncesi ödemelerin devri ──
    def test_eski_alissa_odemeleri_bir_kez_kasasiz_devredilir(self):
        db.session.add(AlissaOdeme(tarih=date(2026, 9, 10), tutar=Decimal('400'), aciklama='elden'))
        db.session.add(AlissaOdeme(tarih=date(2026, 9, 11), tutar=Decimal('999'), iptal=True))
        db.session.commit()
        self.satir(1, H1, '1000')
        c = cari.esitle(1)
        devir = cari.odemeler(c)
        self.assertEqual([(o.tutar, o.islem_id) for o in devir], [(Decimal('400'), None)])
        self.assertIn('bağlantı öncesi', devir[0].aciklama)
        self.assertEqual(cari.odenen(c), Decimal('400'))
        self.assertEqual(c.bakiye, Decimal('600'))
        self.assertEqual(fs.hesap_getir('elde').bakiye, Decimal('10000'))    # kasaya dokunmadı
        cari.esitle(1)
        self.assertEqual(len(cari.odemeler(c)), 1)                            # tekrar devretmez
        self.tutarli()

    # ── ödeme hesapları sırası ──
    def test_odeme_hesaplari_sirasi_nakit_banka_beyazit(self):
        self.assertEqual([h.kod for h in fs.odeme_hesaplari()], ['elde', 'banka', 'beyazit'])
        self.assertIn('beyazit', fs.GIDER_HESAPLARI)


if __name__ == '__main__':
    unittest.main()
