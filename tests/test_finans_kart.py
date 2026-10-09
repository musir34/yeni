"""Kredi kartı: ekstre ayrıştırma, eşleştirme, kayıt ve mutabakat — izole SQLite, gerçek DB/app yok.

Çalıştırma: DISABLE_JOBS=1 .venv/bin/python -m unittest discover -s tests -p "test_finans_kart.py"
"""
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import test_finans_haftalik as base
import finans_service as fs
import finans_kart as fk
from finans_kart_parser import (ekstre_ayristir, satici_anahtari, TUR_GIDER, TUR_SAHSI, TUR_ODEME_BANKA,
                                TUR_ODEME_ELDE, TUR_IADE, TUR_NAKIT, TUR_ATLA)
from models import db, FinansHesap, FinansKategori, FinansIslem, PlatformConfig

# Gerçek İşbankası Maximum ekstresinin satır biçimleri (kişisel veri yok)
EKSTRE = """isbank.com.tr Hesap Özetiniz ile ilgili açıklamalar
Kart Numarası: 4543********5503
MAXIMUM VISA Klasik Hesap Özetiniz
Hesap Kesim Tarihi: 05.09.2026
Son Ödeme Tarihi: 15.09.2026
Hesap Özeti Borcu: 12.013,52 TL
    İŞLEM
    TARİHİ        AÇIKLAMA TUTAR TAKSİT BİLGİSİ MAXIPUAN
********  BİR ÖNCEKİ HESAP ÖZETİ BAKİYENİZ *** 10.000,00
05/08/2026 İSPARK OTOPARK İŞLET İSTANBUL TR 300,00
05/08/2026 FACEBK *CBHB32JRQ4 FACEBOOK.COM IE 2.124,28 0,21
12/08/2026 WWW.MEDIAMARKT.COM.TR ISTANBUL TR 5.466,41 9/9 taksidi (49.198,01)
17/08/2026 1009-2875956 HESAPTAN AKTARIM 1009 İNTERAKTİF -8.000,00
23/07/2026 ATMDEN ÖDEME 18852 4033 * 07:56 -700,00
29/08/2026 WWW.MAVI.COM ISTANBUL TR -2.759,98 6/6 taksidi (16.559,87)
30/08/2026 STEAMGAMES.COM 42595229912-1844160 WAUS 49,97 USD SATIŞ 2.480,01 0,24
05/09/2026 FAIZ TUTARI FZ:1,692.90 VR/FN:507.88 2.200,78
SANAL KART NO: 4183 **** **** 7603
26/08/2026 GOOGLE ONE LONDON GB 719,99
01/09/2026 NAKİT AVANS ATM 182,03
*** ÖDEMELERINIZ IÇIN TESEKKÜR EDERIZ ***
TOPLAM 12.013,52 TL 36,46 TL
"""


class ParserTest(unittest.TestCase):
    def test_satirlar_meta_ve_ic_tutarlilik(self):
        e = ekstre_ayristir(EKSTRE)
        self.assertEqual(e.kart, '4543********5503')
        self.assertEqual(e.kesim_tarihi, date(2026, 9, 5))
        self.assertEqual(e.son_odeme_tarihi, date(2026, 9, 15))
        self.assertEqual(e.onceki_bakiye, Decimal('10000.00'))
        self.assertEqual(e.borc, Decimal('12013.52'))
        self.assertEqual(len(e.satirlar), 10)
        self.assertEqual(e.okunamayan, [])
        self.assertEqual(e.ic_tutarlilik_farki, Decimal('0.00'))   # 10000 + Σsatır = 12013.52

    def test_satir_alanlari(self):
        s = {x.aciklama.split()[0]: x for x in ekstre_ayristir(EKSTRE).satirlar}
        self.assertEqual(s['FACEBK'].tutar, Decimal('2124.28')); self.assertEqual(s['FACEBK'].puan, Decimal('0.21'))
        self.assertEqual(s['WWW.MEDIAMARKT.COM.TR'].taksit, '9/9'); self.assertEqual(s['WWW.MEDIAMARKT.COM.TR'].taksit_toplam, Decimal('49198.01'))
        self.assertEqual(s['STEAMGAMES.COM'].tutar, Decimal('2480.01'))      # döviz: TL karşılığı
        self.assertEqual(s['FAIZ'].tutar, Decimal('2200.78'))
        self.assertTrue(s['GOOGLE'].sanal_kart); self.assertFalse(s['FAIZ'].sanal_kart)
        self.assertEqual(s['1009-2875956'].oneri_tur, TUR_ODEME_BANKA)
        self.assertEqual(s['ATMDEN'].oneri_tur, TUR_ODEME_ELDE)
        self.assertEqual(s['WWW.MAVI.COM'].oneri_tur, TUR_IADE)
        self.assertEqual(s['NAKİT'].oneri_tur, TUR_NAKIT)
        self.assertEqual(s['İSPARK'].oneri_tur, TUR_GIDER)

    def test_satici_anahtari(self):
        self.assertEqual(satici_anahtari('FACEBK *CBHB32JRQ4 FACEBOOK.COM IE'), 'FACEBK FACEBOOK.COM')
        self.assertEqual(satici_anahtari('UBER EATS/TRENDYOL GO/G ISTANBUL TR'), 'UBER EATS/TRENDYOL')
        self.assertEqual(satici_anahtari('5366648299 TURKCELL FAT.ÖDE.'), 'TURKCELL FAT.ÖDE.')
        self.assertEqual(satici_anahtari('HETZNER ONLİNE WWW.HETZNER.C DE'), satici_anahtari('HETZNER ONLINE GMBH DE'))

    def test_bozuk_satir_okunamayana_duser(self):
        e = ekstre_ayristir("14/07/2026 WWW.TRENDYOL.COM ISTANBUL R TR\n15/07/2026 X ISTANBUL TR 1,00\n")
        self.assertEqual(len(e.satirlar), 1)
        self.assertEqual(e.okunamayan, ['14/07/2026 WWW.TRENDYOL.COM ISTANBUL R TR'])


class KartKayitTest(unittest.TestCase):
    """Taban fixture bileşimle (kalıtım taban testlerini ikinci kez koşturur)."""
    def setUp(self):
        base.HaftalikOdemeTest.setUp(self)
        PlatformConfig.__table__.create(bind=db.engine, checkfirst=True)
        db.session.add_all([FinansHesap(kod='banka', ad='Banka', bakiye=Decimal('0'), sira=3),
                            FinansHesap(kod='kredi_karti', ad='Kredi Kartı', bakiye=Decimal('0'), sira=4),
                            FinansKategori(tur='kucuk_gider', ad='Reklam', aktif=True)])
        db.session.commit()
        # Açılış bakiyeleri defterle tutarlı olsun (tutarlilik_kontrol boş dönmeli)
        elde = fs.hesap_getir('elde'); elde.bakiye = 0
        fs._hareket(elde, 'gelir', 1, Decimal('10000'), datetime(2026, 1, 1), 1)
        fs._hareket(fs.hesap_getir('banka'), 'gelir', 1, Decimal('5000'), datetime(2026, 1, 1), 1)
        db.session.commit()
        self.kat = FinansKategori.query.filter_by(ad='Reklam').one().id

    def tearDown(self):
        base.HaftalikOdemeTest.tearDown(self)

    def bakiye(self, kod):
        return Decimal(str(fs.hesap_getir(kod).bakiye))

    def satir(self, gun, aciklama, tutar, tur, kategori=None):
        return {'tarih': date(2026, 8, gun), 'aciklama': aciklama, 'tutar': Decimal(tutar), 'tur': tur,
                'kategori_id': kategori, 'kaynak': 'test'}

    def test_turler_dogru_hesaplara_yazilir_ve_kart_eksiye_dusebilir(self):
        sonuc = fk.satirlari_kaydet([
            self.satir(5, 'FACEBK *X FACEBOOK.COM IE', '2124.28', TUR_GIDER, self.kat),
            self.satir(6, 'UBER EATS/TRENDYOL GO ISTANBUL TR', '696.00', TUR_SAHSI),
            self.satir(17, '1009 HESAPTAN AKTARIM', '-800.00', TUR_ODEME_BANKA),
            self.satir(23, 'ATMDEN ÖDEME 18852', '-700.00', TUR_ODEME_ELDE),
            self.satir(29, 'WWW.MAVI.COM ISTANBUL TR', '-59.98', TUR_IADE),
            self.satir(30, 'NAKİT AVANS', '3600.00', TUR_NAKIT),
            self.satir(31, 'ATLANAN', '999.00', TUR_ATLA),
        ], 1)
        db.session.commit()
        self.assertEqual(sonuc['eklenen'], 6)
        # kart: -2124.28 -696 +800 +700 +59.98 -3600 = -4860.30
        self.assertEqual(self.bakiye('kredi_karti'), Decimal('-4860.30'))
        self.assertEqual(self.bakiye('banka'), Decimal('4200'))       # 5000 - 800
        self.assertEqual(self.bakiye('elde'), Decimal('12900'))       # 10000 - 700 + 3600
        self.assertEqual(fs.donem_ozet('2026-08')['kucuk_gider'], Decimal('2124.28'))   # şahsi raporda yok
        self.assertEqual(fk.hafiza_oku()['FACEBK FACEBOOK.COM'], {'tur': 'gider', 'kategori_id': self.kat})
        self.assertEqual(fk.hafiza_oku()['UBER EATS/TRENDYOL']['tur'], 'sahsi')
        self.assertEqual(fs.tutarlilik_kontrol(), [])

    def test_gider_kategorisiz_hata_ve_rollback(self):
        with self.assertRaises(fs.FinansHata):
            fk.satirlari_kaydet([self.satir(5, 'X', '10.00', TUR_GIDER, None)], 1)
        db.session.rollback()
        self.assertEqual(self.bakiye('kredi_karti'), Decimal('0'))

    def test_ayni_ekstre_ikinci_kez_yazilmaz(self):
        satirlar = [self.satir(5, 'FACEBK *X FACEBOOK.COM IE', '2124.28', TUR_GIDER, self.kat)]
        fk.satirlari_kaydet(satirlar, 1); db.session.commit()
        sonuc = fk.satirlari_kaydet(satirlar, 1); db.session.commit()
        self.assertEqual((sonuc['eklenen'], sonuc['atlanan']), (0, 1))
        self.assertEqual(self.bakiye('kredi_karti'), Decimal('-2124.28'))

    def test_eslestirme_cari_odemesini_tanir(self):
        """Kartla ödenen tedarikçi cari kaydı (açıklama farklı, tutar aynı, 2 gün fark) 'kayıtlı' sayılır."""
        kart = fs.hesap_getir('kredi_karti', kilitle=True)
        fs._hareket(kart, 'cari_odeme', -1, Decimal('3600'), fk._tarih_utc(date(2026, 8, 10)), 1, aciklama='Ahmet ödeme')
        db.session.commit()
        e = ekstre_ayristir("12/08/2026 AHMET AYAKKABI SAN LTD ISTANBUL TR 3.600,00\n"
                            "20/08/2026 AHMET AYAKKABI SAN LTD ISTANBUL TR 3.600,00\n")
        onizleme = fk._onizleme_satirlari(e, {}, fs.kategoriler('kucuk_gider'))
        self.assertIsNotNone(onizleme[0]['eslesen']); self.assertFalse(onizleme[0]['secili'])
        self.assertIsNone(onizleme[1]['eslesen']); self.assertTrue(onizleme[1]['secili'])   # 10 gün uzak, kayıt zaten kullanıldı

    def test_hafiza_onizlemeye_yansir_odeme_turunu_ezmez(self):
        e = ekstre_ayristir("05/08/2026 FACEBK *Q FACEBOOK.COM IE 10,00\n17/08/2026 1009 HESAPTAN AKTARIM -5,00\n")
        hafiza = {'FACEBK FACEBOOK.COM': {'tur': 'sahsi', 'kategori_id': None}, 'HESAPTAN AKTARIM': {'tur': 'gider', 'kategori_id': self.kat}}
        o = fk._onizleme_satirlari(e, hafiza, fs.kategoriler('kucuk_gider'))
        self.assertEqual(o[0]['tur'], 'sahsi'); self.assertTrue(o[0]['hafizadan'])
        self.assertEqual(o[1]['tur'], TUR_ODEME_BANKA)

    def test_mutabakat_hesabi(self):
        m = fk.mutabakat_hesapla(Decimal('12013.52'), Decimal('-10000'), Decimal('2013.52'))
        self.assertEqual(m['sonrasi'], Decimal('-12013.52')); self.assertEqual(m['fark'], Decimal('0.00'))
        m = fk.mutabakat_hesapla(Decimal('12013.52'), Decimal('-10000'), Decimal('1757.55'))
        self.assertEqual(m['fark'], Decimal('-255.97'))
        self.assertIsNone(fk.mutabakat_hesapla(None, Decimal('0'), Decimal('0'))['fark'])

    def test_http_onizleme_kaydet_duzelt(self):
        from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader, StrictUndefined
        from io import BytesIO
        from finans import finans_bp
        self.app.config.update(SECRET_KEY='isolated-test', TESTING=True)
        self.app.register_blueprint(finans_bp)
        self.app.add_url_rule('/', endpoint='home.home', view_func=lambda: 'home')
        self.app.jinja_loader = ChoiceLoader([
            DictLoader({'base.html': '{% block content %}{% endblock %}{% block scripts %}{% endblock %}'}),
            FileSystemLoader(str(Path(__file__).resolve().parents[1] / 'templates'))])
        self.app.jinja_env.undefined = StrictUndefined
        self.app.jinja_env.filters['tl_format'] = lambda v: f'{v:.2f}'
        self.app.jinja_env.filters['ist'] = lambda v, fmt: v.strftime(fmt)
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=1, role='admin', session_version=1, totp_verified=True)
        with patch('finans._log'), patch('finans_kart.pdf_metni', return_value=EKSTRE):
            self.assertEqual(client.get('/finans/kart').status_code, 200)
            r = client.post('/finans/kart', data={'pdf_file': (BytesIO(b'%PDF-sahte'), 'Eylul.pdf')},
                            content_type='multipart/form-data')
            html = r.get_data(as_text=True)
            self.assertEqual(r.status_code, 200)
            self.assertIn('Mutabakat', html); self.assertIn('12013.52', html); self.assertIn('name="sec" value="1"', html)
            # Önizlemeden: 1 (İSPARK gider), 4 (HESAPTAN AKTARIM ödeme), 9 (GOOGLE ONE şahsi); fark düzeltmeyle kapansın
            r = client.post('/finans/kart/kaydet', data={
                'sec': ['1', '4', '9'], 'ekstre_borc': '12013.52', 'ekstre_kesim': '2026-09-05', 'dosya_adi': 'Eylul.pdf',
                'tarih_1': '2026-08-05', 'tutar_1': '300.00', 'aciklama_1': 'İSPARK OTOPARK', 'tur_1': 'gider', 'kategori_1': str(self.kat),
                'tarih_4': '2026-08-17', 'tutar_4': '-8000.00', 'aciklama_4': 'HESAPTAN AKTARIM', 'tur_4': 'odeme_banka',
                'tarih_9': '2026-08-26', 'tutar_9': '719.99', 'aciklama_9': 'GOOGLE ONE', 'tur_9': 'sahsi',
                'ek_tarih': ['2026-07-14'], 'ek_aciklama': ['Okunamayan Trendyol'], 'ek_tutar': ['255,97'], 'ek_tur': ['gider'], 'ek_kategori': [str(self.kat)],
                'duzeltme_kapat': '1', 'duzeltme_aciklama': 'kalan fark', 'bakiye_onay': '1'})
            self.assertEqual(r.status_code, 302)
            # kart: -300 +8000 -719.99 -255.97 = 6724.04 → hedef -12013.52 → düzeltme -18737.56
            self.assertEqual(self.bakiye('kredi_karti'), Decimal('-12013.52'))
            self.assertEqual(self.bakiye('banka'), Decimal('-3000'))   # 5000 - 8000; önizleme onay sayıldı (bakiye_onay)
            duzeltme = FinansIslem.query.filter_by(tur='kart_duzeltme').one()
            self.assertEqual((duzeltme.yon, duzeltme.tutar), (-1, Decimal('18737.56')))
            r = client.post('/finans/kart/duzelt', data={'tarih': '2026-09-06', 'yon': 'azalt', 'tutar': '13,52', 'aciklama': 'test'})
            self.assertEqual(r.status_code, 302)
            self.assertEqual(self.bakiye('kredi_karti'), Decimal('-12000.00'))
            self.assertEqual(client.get('/finans/kart').status_code, 200)
            self.assertEqual(client.get('/finans/defter/kredi_karti').status_code, 200)
        self.assertEqual(fs.tutarlilik_kontrol(), [])


if __name__ == '__main__':
    unittest.main()
