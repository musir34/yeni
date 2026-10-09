"""Kredi kartı ekstresi: şahsi harcamanın seçilen şahsi cari hesaba düşmesi. İzole SQLite, gerçek DB yok.

Çalıştırma: DISABLE_JOBS=1 .venv/bin/python -m unittest discover -s tests -p "test_finans_kart_sahsi_cari.py"
"""
import unittest
from datetime import date
from decimal import Decimal

import test_finans_kart as tk
import finans_service as fs
import finans_cari_service as cs
import finans_kart as fk
from finans_kart_parser import TUR_SAHSI, TUR_GIDER
from models import db, FinansCariHareket, FinansIslem


class KartSahsiCariTest(unittest.TestCase):
    def setUp(self):
        tk.KartKayitTest.setUp(self)
        self.musir = cs.cari_ekle('Musir — şahsi', 'sahsi', '', '', 1)

    def tearDown(self):
        tk.KartKayitTest.tearDown(self)

    bakiye = tk.KartKayitTest.bakiye

    def satir(self, aciklama='UBER EATS YEMEK ISTANBUL TR', tutar='675.00', tur=TUR_SAHSI, cari_id=None, kategori=None):
        return {'tarih': date(2026, 9, 1), 'aciklama': aciklama, 'tutar': Decimal(tutar), 'tur': tur,
                'kategori_id': kategori, 'cari_id': cari_id, 'kaynak': 'test'}

    def kaydet(self, *satirlar):
        sonuc = fk.satirlari_kaydet(list(satirlar), 1)
        db.session.commit()
        return sonuc

    def tutarli(self):
        self.assertEqual(fs.tutarlilik_kontrol(), [])
        self.assertEqual(cs.cari_tutarlilik_kontrol(), [])

    def test_secilen_sahsi_cariye_borc_olarak_duser(self):
        self.kaydet(self.satir(cari_id=self.musir.id))
        self.assertEqual(self.bakiye('kredi_karti'), Decimal('-675.00'))
        db.session.refresh(self.musir)
        self.assertEqual(self.musir.bakiye, Decimal('-675.00'))       # kasaya borcu (şahsi hesapta eksi = borç)
        h = FinansCariHareket.query.one()
        self.assertEqual((h.tur, h.yon, h.tutar), ('borc_alma', -1, Decimal('675.00')))
        self.assertEqual(h.islem.tur, 'kart_sahsi')
        self.assertEqual(h.islem.hesap.kod, 'kredi_karti')
        self.tutarli()

    def test_cari_secilmezse_eskisi_gibi_yalniz_kart(self):
        self.kaydet(self.satir())
        self.assertEqual(self.bakiye('kredi_karti'), Decimal('-675.00'))
        self.assertEqual(FinansCariHareket.query.count(), 0)
        self.tutarli()

    def test_sahsi_olmayan_dolar_ya_da_kapali_cari_reddedilir(self):
        tedarikci = cs.cari_ekle('Taban Ltd', 'tedarikci', '', '', 1)
        dolar = cs.cari_ekle('Musir USD', 'sahsi', '', '', 1, para_birimi='USD')
        kapali = cs.cari_ekle('Eski şahsi', 'sahsi', '', '', 1)
        cs.cari_pasif(kapali.id, aktif=False)
        for c in (tedarikci, dolar, kapali):
            with self.assertRaises(fs.FinansHata):
                fk.satirlari_kaydet([self.satir(cari_id=c.id)], 1)
            db.session.rollback()
        with self.assertRaises(fs.FinansHata):
            fk.satirlari_kaydet([self.satir(cari_id=999999)], 1)
        db.session.rollback()
        self.assertEqual(self.bakiye('kredi_karti'), Decimal('0'))
        self.assertEqual(FinansCariHareket.query.count(), 0)

    def test_cari_yalniz_sahsi_turde_kullanilir(self):
        self.kaydet(self.satir('FACEBK *X FACEBOOK.COM IE', '100.00', TUR_GIDER, cari_id=self.musir.id, kategori=self.kat))
        self.assertEqual(FinansCariHareket.query.count(), 0)            # gider satırında cari yok sayılır
        db.session.refresh(self.musir)
        self.assertEqual(self.musir.bakiye, Decimal('0'))

    def test_iptal_iki_tarafi_birlikte_geri_alir(self):
        self.kaydet(self.satir(cari_id=self.musir.id), self.satir('APPLE.COM/BILL', '249.99', cari_id=self.musir.id))
        h1, h2 = FinansCariHareket.query.order_by(FinansCariHareket.id).all()
        cs.hareket_iptal(h1.id, 1)                                       # cari defterinden
        fs.islem_iptal(h2.islem_id, 1)                                   # kart defterinden
        db.session.refresh(self.musir)
        self.assertEqual(self.musir.bakiye, Decimal('0'))
        self.assertEqual(self.bakiye('kredi_karti'), Decimal('0'))
        self.tutarli()

    def test_hafiza_cariyi_hatirlar_ve_onizlemeye_getirir(self):
        self.kaydet(self.satir(cari_id=self.musir.id))
        kayit = fk.hafiza_oku()[fk.satici_anahtari('UBER EATS YEMEK ISTANBUL TR')]
        self.assertEqual((kayit['tur'], kayit['cari_id']), ('sahsi', self.musir.id))
        cari_idler = {self.musir.id}
        self.assertEqual(fk.hafiza_cari(kayit, cari_idler), self.musir.id)
        self.assertIsNone(fk.hafiza_cari({'tur': 'sahsi', 'cari_id': 424242}, cari_idler))   # silinmiş/kapalı cari
        self.assertIsNone(fk.hafiza_cari({'tur': 'gider', 'cari_id': self.musir.id}, cari_idler))

    def test_ayni_ekstre_tekrar_yuklenince_cariye_ikinci_kez_yazilmaz(self):
        self.kaydet(self.satir(cari_id=self.musir.id))
        sonuc = self.kaydet(self.satir(cari_id=self.musir.id))
        self.assertEqual((sonuc['eklenen'], sonuc['atlanan']), (0, 1))
        self.assertEqual(FinansCariHareket.query.count(), 1)
        db.session.refresh(self.musir)
        self.assertEqual(self.musir.bakiye, Decimal('-675.00'))

    def test_eski_bicimli_hafiza_kaydi_cari_getirmez(self):
        self.assertIsNone(fk.hafiza_cari({'tur': 'sahsi', 'kategori_id': None}, {self.musir.id}))
        self.assertIsNone(fk.hafiza_cari({}, {self.musir.id}))

    def test_form_cari_alanlarini_okur(self):
        with self.app.test_request_context('/', method='POST', data={
                'sec': ['3'], 'tarih_3': '2026-09-01', 'tutar_3': '675.00', 'aciklama_3': 'UBER', 'tur_3': 'sahsi',
                'cari_3': str(self.musir.id),
                'ek_tarih': ['2026-09-02'], 'ek_aciklama': ['Elle'], 'ek_tutar': ['10,00'], 'ek_tur': ['sahsi'],
                'ek_kategori': [''], 'ek_cari': [str(self.musir.id)]}):
            from flask import request
            satirlar = fk._form_satirlari(request.form)
        self.assertEqual([s['cari_id'] for s in satirlar], [str(self.musir.id), str(self.musir.id)])


if __name__ == '__main__':
    unittest.main()
