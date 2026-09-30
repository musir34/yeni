"""Alissa hesabı testleri — izole SQLite; app.py/.env veya gerçek veritabanını açmaz, Trendyol'a gitmez.

Çalıştırma: .venv/bin/python -m unittest alissa.tests.test_alissa
"""
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from flask import Flask

from models import db
from alissa import hesap, senkron
from alissa.models import TABLOLAR, AlissaHareket, AlissaOdeme
from alissa.routes import _tutar_oku

BARKODLAR = {'B1': ('160', 'Krem', '38'), 'B2': ('4480', 'Pembe', '37')}
PZT = datetime(2026, 9, 7, 9)            # Pazartesi 12:00 İstanbul (kayıtlar UTC)
HAFTA1, HAFTA2 = date(2026, 9, 7), date(2026, 9, 14)


def ms(dt):
    return int((dt - datetime(1970, 1, 1)).total_seconds() * 1000)


def kayit(kimlik, tur, siparis, barkod, tarih, brut, komisyon, paket=None):
    borc = tur in ('iade', 'indirim', 'kupon')
    return {'id': kimlik, '_tur': tur, 'orderNumber': siparis, 'shipmentPackageId': paket or f'P{siparis}',
            'barcode': barkod, 'transactionDate': ms(tarih), 'debt': brut if borc else 0,
            'credit': 0 if borc else brut, 'commissionAmount': komisyon, 'sellerRevenue': brut - komisyon}


class SahteIstemci:
    def __init__(self):
        self.finans, self.faturalar, self.paketler = [], {}, []

    def settlements(self, bas, son):
        return list(self.finans)

    def kargo_faturalari(self, bas, son):
        return [(no, tarih) for no, (tarih, _) in self.faturalar.items()]

    def kargo_kalemleri(self, fatura_no):
        return self.faturalar[fatura_no][1]

    def siparis_paketleri(self, bas, son):
        return list(self.paketler)


class AlissaTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.metadata.create_all(db.engine, tables=[m.__table__ for m in TABLOLAR])
        self.yama = patch('alissa.senkron.alissa_barkodlar', return_value=BARKODLAR)
        self.yama.start()
        self.istemci = SahteIstemci()

    def tearDown(self):
        self.yama.stop()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def senkron(self, gun_sonra=1):
        return senkron.senkronla(self.istemci, PZT + timedelta(days=gun_sonra))

    def hafta(self, bas):
        return next(h for h in hesap.haftalik(date(2026, 9, 30))['haftalar'] if h['bas'] == bas)

    def test_satis_kesintileriyle_teslim_haftasina_yazilir(self):
        self.istemci.finans = [kayit(1, 'satis', 'S1', 'B1', PZT, 1000, 200),
                               kayit(2, 'indirim', 'S1', 'B1', PZT, 100, 20)]
        self.senkron()
        h = self.hafta(HAFTA1)
        self.assertEqual((h['satis_adet'], h['siparis']), (1, 1))
        self.assertEqual(h['satis'], Decimal('1000'))
        self.assertEqual(h['indirim'], Decimal('100'))
        self.assertEqual(h['komisyon'], Decimal('180'))
        self.assertEqual(h['phb'], Decimal('13.19'))
        self.assertEqual(h['masraf'], Decimal('100'))
        self.assertEqual(h['kargo'], Decimal('117.59'))          # fatura yok → tahmin
        self.assertTrue(h['tahmin'])
        self.assertEqual(h['net'], Decimal('1000') - 100 - 180 - Decimal('13.19') - 100 - Decimal('117.59'))

    def test_tekrar_senkron_hicbir_sey_eklemez(self):
        self.istemci.finans = [kayit(1, 'satis', 'S1', 'B1', PZT, 1000, 200)]
        self.senkron()
        once = AlissaHareket.query.count()
        ozet = self.senkron(gun_sonra=2)
        self.assertEqual(AlissaHareket.query.count(), once)
        self.assertEqual((ozet['finans'], ozet['kargo']), (0, 0))

    def test_karma_sipariste_paket_kalemleri_adet_oraninda(self):
        self.istemci.finans = [kayit(1, 'satis', 'S1', 'B1', PZT, 1000, 200),
                               kayit(2, 'satis', 'S1', 'BASKA', PZT, 500, 100)]
        self.senkron()
        h = self.hafta(HAFTA1)
        self.assertEqual(h['satis'], Decimal('1000'))            # başka ürünün satışı girmez
        self.assertEqual(h['masraf'], Decimal('50.00'))
        self.assertEqual(h['phb'], Decimal('6.60'))
        self.assertEqual(h['kargo'], Decimal('58.80'))

    def test_iade_kesildigi_haftadan_duser(self):
        self.istemci.finans = [kayit(1, 'satis', 'S1', 'B1', PZT, 1000, 200)]
        self.senkron()
        ilk_hafta_neti = self.hafta(HAFTA1)['net']
        self.istemci.finans.append(kayit(3, 'iade', 'S1', 'B1', PZT + timedelta(days=8), 1000, 200))
        self.senkron(gun_sonra=9)
        self.assertEqual(self.hafta(HAFTA1)['net'], ilk_hafta_neti)   # ödenmiş hafta değişmez
        h2 = self.hafta(HAFTA2)
        self.assertEqual((h2['satis_adet'], h2['iade_adet']), (0, 1))
        self.assertEqual(h2['net'], Decimal('-800') - Decimal('117.59'))   # iade + iade kargosu tahmini

    def test_kargo_faturasi_gelince_fark_fatura_haftasina_yazilir(self):
        self.istemci.finans = [kayit(1, 'satis', 'S1', 'B1', PZT, 1000, 200)]
        self.senkron()
        ilk_hafta_neti = self.hafta(HAFTA1)['net']
        self.istemci.faturalar['F1'] = (PZT + timedelta(days=8), [
            {'shipmentPackageType': 'Gönderi Kargo Bedeli', 'parcelUniqueId': 111, 'orderNumber': 'S1',
             'amount': 149.99, 'desi': 4}])
        self.senkron(gun_sonra=9)
        self.assertEqual(self.hafta(HAFTA1)['net'], ilk_hafta_neti)
        h2 = self.hafta(HAFTA2)
        self.assertTrue(h2['fark'])
        self.assertEqual(h2['kargo'], Decimal('149.99') - Decimal('117.59'))
        toplam = hesap.haftalik(date(2026, 9, 30))['toplam']
        self.assertEqual(toplam['kargo'], Decimal('149.99'))     # toplamda gerçek fatura tutarı
        self.senkron(gun_sonra=10)                               # fatura ikinci kez işlenmez
        self.assertEqual(hesap.haftalik(date(2026, 9, 30))['toplam']['kargo'], Decimal('149.99'))

    def test_fatura_hazirsa_tahmin_yazilmaz(self):
        self.istemci.finans = [kayit(1, 'satis', 'S1', 'B1', PZT, 1000, 200)]
        self.istemci.faturalar['F1'] = (PZT, [
            {'shipmentPackageType': 'Gönderi Kargo Bedeli', 'parcelUniqueId': 111, 'orderNumber': 'S1',
             'amount': 111.59, 'desi': 2}])
        self.senkron()
        h = self.hafta(HAFTA1)
        self.assertEqual(h['kargo'], Decimal('111.59'))
        self.assertFalse(h['tahmin'])

    def test_bakiye_odemeyle_azalir_iptal_odeme_sayilmaz(self):
        self.istemci.finans = [kayit(1, 'satis', 'S1', 'B1', PZT, 1000, 200)]
        self.senkron()
        net = hesap.haftalik(date(2026, 9, 30))['toplam']['net']
        db.session.add(AlissaOdeme(tarih=date(2026, 9, 14), tutar=Decimal('500')))
        db.session.add(AlissaOdeme(tarih=date(2026, 9, 14), tutar=Decimal('999'), iptal=True))
        db.session.commit()
        ozet = hesap.haftalik(date(2026, 9, 30))
        self.assertEqual(ozet['odenen'], Decimal('500'))
        self.assertEqual(ozet['bakiye'], net - 500)

    def test_siparis_satirlari_gelen_ve_iptal_sayilir(self):
        paket = lambda no, durum: {                                            # noqa: E731
            'orderNumber': no, 'shipmentPackageId': f'P{no}', 'orderDate': ms(PZT + timedelta(hours=3)),
            'lastModifiedDate': 1, 'status': durum,
            'lines': [{'lineId': f'L{no}', 'barcode': 'B2', 'quantity': 1, 'orderLineItemStatusName': durum,
                       'lineUnitPrice': 900, 'cancelledBy': 'customer', 'cancelReason': 'Vazgeçtim'},
                      {'lineId': f'X{no}', 'barcode': 'BASKA', 'quantity': 1, 'orderLineItemStatusName': durum}]}
        self.istemci.paketler = [paket('S1', 'Shipped'), paket('S2', 'Cancelled')]
        self.senkron()
        ozet = hesap.haftalik(date(2026, 9, 30))
        h = next(h for h in ozet['haftalar'] if h['bas'] == HAFTA1)
        self.assertEqual((h['gelen'], h['iptal'], ozet['yolda']), (2, 1, 1))

    def test_baska_paketin_kolisi_alissaya_yazilmaz(self):
        # Karma sipariş iki ayrı paketle gitti: Alissa ürünü PA'da, diğer ürün PB'de.
        self.istemci.finans = [kayit(1, 'satis', 'S1', 'B1', PZT, 1000, 200, paket='PA')]
        self.istemci.faturalar['F1'] = (PZT, [
            {'shipmentPackageType': 'Gönderi Kargo Bedeli', 'parcelUniqueId': 111, 'orderNumber': 'S1',
             'amount': 111.59, 'desi': 2},
            {'shipmentPackageType': 'Gönderi Kargo Bedeli', 'parcelUniqueId': 222, 'orderNumber': 'S1',
             'amount': 149.99, 'desi': 4}])
        self.senkron()
        self.assertEqual(self.hafta(HAFTA1)['kargo'], Decimal('111.59'))
        self.senkron(gun_sonra=2)
        self.assertEqual(self.hafta(HAFTA1)['kargo'], Decimal('111.59'))

    def test_kilit_ayni_anda_iki_kez_alinamaz(self):
        self.assertTrue(senkron._kilit_al())
        self.assertTrue(senkron.durum()['calisiyor'])
        self.assertFalse(senkron._kilit_al())

    def test_hata_sonrasi_hemen_yeniden_denenmez(self):
        self.assertTrue(senkron.eskidi())
        from alissa import ayar
        ayar.yaz('son_deneme', senkron.simdi_ist().isoformat(timespec='seconds'))
        db.session.commit()
        self.assertFalse(senkron.eskidi())

    def test_tutar_oku(self):
        self.assertEqual(_tutar_oku('1.234,56'), Decimal('1234.56'))
        self.assertEqual(_tutar_oku('1234.5'), Decimal('1234.50'))
        self.assertEqual(_tutar_oku('1.500'), Decimal('1500.00'))      # nokta binlik ayırıcı
        self.assertEqual(_tutar_oku('150.000'), Decimal('150000.00'))
        self.assertIsNone(_tutar_oku('99999999999'))                   # kolon sınırı
        self.assertIsNone(_tutar_oku('abc'))
        self.assertIsNone(_tutar_oku(''))


if __name__ == '__main__':
    unittest.main()
