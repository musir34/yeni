"""Düzenli Ödemeler listesi: aylıkçılar / haftalıkçılar + hafta grupları. Saf fonksiyon, DB yok.

Çalıştırma: .venv/bin/python -m unittest discover -s tests -p test_finans_ana_gider_gruplari.py
"""
import unittest
from decimal import Decimal
from types import SimpleNamespace as K

import finans_service as fs


def satir(ad, donem, odenen='0', kalan='0', belirsiz=False, bekleyen=True):
    return {'kalem': K(ad=ad, sira=0), 'donem': donem, 'etiket': fs.donem_etiket(donem),
            'odenen': Decimal(odenen), 'kalan': None if belirsiz else Decimal(kalan),
            'belirsiz': belirsiz, 'bekleyen': bekleyen}


class AnaGiderGruplariTest(unittest.TestCase):
    def durum(self):
        return [
            satir('Hatice', '2026-10', '0', '45000'),
            satir('Maya Mutfak', '2026-10', '15000', '21000'),
            satir('Ahmet', '2026-10-02', '10000', '6000'),
            satir('Halı Saha', '2026-10-02', belirsiz=True),
            satir('Ahmet', '2026-10-09', '0', '16000'),
            satir('Ahmet', '2026-10-16', '0', '16000'),
            satir('Ahmet', '2026-10-23', '0', '16000'),
            satir('Ahmet', '2026-10-30', '0', '16000'),
        ]

    def test_aylik_ve_haftalik_ayrilir_haftalar_sirali(self):
        g = fs.ana_gider_gruplari(self.durum(), bugun='2026-10-02')
        self.assertEqual([d['kalem'].ad for d in g['aylik']], ['Hatice', 'Maya Mutfak'])
        self.assertEqual([h['no'] for h in g['haftalar']], [1, 2, 3, 4, 5])
        self.assertEqual([h['donem'] for h in g['haftalar']],
                         ['2026-10-02', '2026-10-09', '2026-10-16', '2026-10-23', '2026-10-30'])
        self.assertEqual([d['kalem'].ad for d in g['haftalar'][0]['satirlar']], ['Ahmet', 'Halı Saha'])
        self.assertEqual(g['haftalar'][0]['etiket'], '02.10.2026 haftası')

    def test_hafta_ara_toplamlari(self):
        h1 = fs.ana_gider_gruplari(self.durum(), bugun='2026-10-02')['haftalar'][0]
        self.assertEqual((h1['odenen'], h1['kalan'], h1['belirsiz_adet'], h1['bekleyen_adet']),
                         (Decimal('10000'), Decimal('6000'), 1, 2))

    def test_bugunun_haftasi_acik_digerleri_kapali(self):
        acik = lambda bugun: [h['acik'] for h in fs.ana_gider_gruplari(self.durum(), bugun=bugun)['haftalar']]
        self.assertEqual(acik('2026-10-02'), [True, False, False, False, False])   # ödeme günü
        self.assertEqual(acik('2026-10-05'), [True, False, False, False, False])   # son geçen vade
        self.assertEqual(acik('2026-10-09'), [False, True, False, False, False])
        self.assertEqual(acik('2026-09-20'), [True, False, False, False, False])   # gelecek ay → ilk hafta
        self.assertEqual(acik('2026-11-15'), [False, False, False, False, False])  # geçmiş ay → hepsi kapalı

    def test_bos_liste_ve_yalniz_aylik(self):
        self.assertEqual(fs.ana_gider_gruplari([], bugun='2026-10-02'), {'aylik': [], 'haftalar': []})
        g = fs.ana_gider_gruplari([satir('Kira', '2026-10', '0', '50000')], bugun='2026-10-02')
        self.assertEqual(len(g['aylik']), 1)
        self.assertEqual(g['haftalar'], [])


if __name__ == '__main__':
    unittest.main()
