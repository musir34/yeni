"""Cari listesi tür grupları + sıralama (komutan emri 2026-10-17). Saf fonksiyon, DB yok.

Çalıştırma: DISABLE_JOBS=1 python -m unittest discover -s tests -p test_finans_cari_gruplari.py
"""
import unittest
from decimal import Decimal
from types import SimpleNamespace as K

import finans_cari_service as cs


def cari(ad, tur='tedarikci', bakiye='0', aktif=True, pb='TRY'):
    return K(ad=ad, tur=tur, bakiye=Decimal(bakiye), aktif=aktif, para_birimi=pb)


class CariGruplariTest(unittest.TestCase):
    def liste(self):
        return [cari('Kavara', 'tedarikci', '37119'), cari('Çetin', 'tedarikci', '56'), cari('ali', 'calisan', '0'),
                cari('Hatice', 'calisan', '45600'), cari('Yusuf', 'tedarikci', '8000', pb='USD'),
                cari('Abdurrahman', 'sahsi', '-5135.33'), cari('Eski', 'diger', '0', aktif=False),
                cari('Müşteri X', 'musteri', '-1200'), cari('Bilinmez', 'uydurma', '10')]

    def test_grup_sirasi_ve_bos_grup_yok(self):
        g = cs.cari_gruplari(self.liste())
        self.assertEqual([x['kod'] for x in g], ['tedarikci', 'calisan', 'diger', 'musteri', 'sahsi', 'kapali'])
        self.assertEqual([x['etiket'] for x in g][:2], ['Tedarikçi', 'Çalışan'])
        self.assertEqual([c.ad for c in g[-1]['cariler']], ['Eski'])              # kapalı en sonda
        self.assertEqual([c.ad for c in g[2]['cariler']], ['Bilinmez'])          # bilinmeyen tür → Diğer
        self.assertEqual([x['kod'] for x in cs.cari_gruplari([cari('A', 'calisan')])], ['calisan'])

    def test_bakiye_siralamasi_buyukten_kucuge_isaretsiz(self):
        g = {x['kod']: x for x in cs.cari_gruplari(self.liste(), 'bakiye')}
        self.assertEqual([c.ad for c in g['tedarikci']['cariler']], ['Kavara', 'Yusuf', 'Çetin'])
        self.assertEqual([c.ad for c in g['calisan']['cariler']], ['Hatice', 'ali'])

    def test_ad_siralamasi_turkce_harf_duyarsiz(self):
        g = {x['kod']: x for x in cs.cari_gruplari(self.liste(), 'ad')}
        self.assertEqual([c.ad for c in g['tedarikci']['cariler']], ['Çetin', 'Kavara', 'Yusuf'])
        self.assertEqual([c.ad for c in g['calisan']['cariler']], ['ali', 'Hatice'])
        self.assertEqual(cs.cari_gruplari(self.liste(), 'saçma')[0]['cariler'][0].ad, 'Kavara')   # bilinmeyen → bakiye

    def test_grup_toplamlari_tl_usd_ayri(self):
        g = {x['kod']: x for x in cs.cari_gruplari(self.liste())}
        self.assertEqual((g['tedarikci']['borc'], g['tedarikci']['borc_usd']), (Decimal('37175'), Decimal('8000')))
        self.assertEqual((g['musteri']['alacak'], g['musteri']['borc']), (Decimal('1200'), Decimal('0')))
        self.assertEqual(g['sahsi']['alacak'], Decimal('5135.33'))
        self.assertEqual(g['calisan']['borc'], Decimal('45600'))


if __name__ == '__main__':
    unittest.main()
