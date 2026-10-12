"""Finans iptal düğmeleri: tojson çıktısı (çift tırnaklı) onclick özniteliğini bozmamalı. DB yok.

Çalıştırma: .venv/bin/python -m unittest discover -s tests -p test_finans_iptal_dugmesi.py
"""
import re
import unittest
from pathlib import Path

from flask import Flask, render_template_string

SABLONLAR = Path(__file__).resolve().parents[1] / 'templates'
BOZUK = re.compile(r'onclick="[^"]*\|\s*tojson')


class IptalDugmesiTest(unittest.TestCase):
    def test_finans_sablonlarinda_cift_tirnakli_onclick_tojson_yok(self):
        bozuk = [f'{p.name}:{i}' for p in SABLONLAR.glob('finans*.html')
                 for i, satir in enumerate(p.read_text().splitlines(), 1) if BOZUK.search(satir)]
        self.assertEqual(bozuk, [])

    def test_tek_tirnakli_oznitelik_aciklamayi_bozmadan_tasir(self):
        app = Flask(__name__)
        with app.app_context():
            html = render_template_string("<b onclick='fnIptal({{ i }}, {{ s | tojson }})'>x</b>",
                                          i=5, s='Halı Saha — "09.10" haftası \' ödemesi')
        m = re.fullmatch(r"<b onclick='([^']*)'>x</b>", html)
        self.assertIsNotNone(m, html)            # öznitelik tek parça kaldı
        self.assertTrue(m.group(1).startswith('fnIptal(5, "'))


if __name__ == '__main__':
    unittest.main()
