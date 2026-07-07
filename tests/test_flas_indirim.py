"""Flaş İndirim Motoru saf modül testleri (flas_indirim_moduller).

DB'ye ve Flask'a dokunmaz.

Çalıştırma:
    DISABLE_JOBS=1 pytest tests/test_flas_indirim.py -v
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from akilli_motor_moduller import beklenen_birim_kar  # noqa: E402
from flas_indirim_moduller import (  # noqa: E402
    flas_karar, model_filtre_setleri, model_filtrede,
    model_satis_ozeti, taban_fiyat,
)

NOW = datetime.now()

PARAMS = {'maliyet': 300, 'kargo': 20, 'iade_orani': 20, 'paketleme': 5}

SATIS_VAR = {'gunluk_satis': 2.0, 'son30_gunluk': 2.0, 'trend': 'sabit', 'toplam_90g': 180}
SATIS_YOK = {'gunluk_satis': 0.0, 'son30_gunluk': 0.0, 'trend': 'veri_yok', 'toplam_90g': 0}


def _sales_df(rows):
    return pd.DataFrame([{
        'model_kodu': m, 'renk': r, 'tutar': t, 'komisyon': t * 0.2,
        'tarih': NOW - timedelta(days=g), 'adet': a,
    } for (m, r, t, g, a) in rows])


def _offer(**kw):
    temel = {'model_kodu': '099', 'stok': 50, 'mevcut_fiyat': 2000,
             'musteri_fiyat': 1800, 'komisyon': 21.5,
             'trendyol_fiyat': 1500, 'pencere_saat': 24}
    return {**temel, **kw}


# ═══ Taban fiyat ═══════════════════════════════════════════════════════

class TestTabanFiyat:
    def test_analitik_ters_dogru(self):
        # Tabanda beklenen birim kâr tam min_kar olmalı
        for min_kar in (0, 50, 120):
            taban = taban_fiyat(21.5, PARAMS, min_kar)
            assert beklenen_birim_kar(taban, 21.5, PARAMS) == pytest.approx(min_kar, abs=0.05)

    def test_tabanin_alti_zarar_ustu_kar(self):
        taban = taban_fiyat(21.5, PARAMS, 0)
        assert beklenen_birim_kar(taban - 10, 21.5, PARAMS) < 0
        assert beklenen_birim_kar(taban + 10, 21.5, PARAMS) > 0

    def test_imkansiz_komisyon_none(self):
        assert taban_fiyat(100, PARAMS, 0) is None
        assert taban_fiyat(120, PARAMS, 0) is None

    def test_iade_yuzde_yuz_none(self):
        assert taban_fiyat(20, {**PARAMS, 'iade_orani': 100}, 0) is None

    def test_dusuk_komisyon_dusuk_taban(self):
        assert taban_fiyat(5.7, PARAMS, 0) < taban_fiyat(21.5, PARAMS, 0)


# ═══ Model satış özeti ═════════════════════════════════════════════════

class TestModelSatisOzeti:
    def test_sifir_onek_eslesme(self):
        # DB'de '99' (sıfırsız), Excel'de '099' — eşleşmeli
        df = _sales_df([('99', 'Siyah', 500, g, 1) for g in range(1, 30)])
        oz = model_satis_ozeti(df, '099')
        assert oz['toplam_90g'] == 29
        # tersi: DB'de '099', Excel'de '99'
        df2 = _sales_df([('099', 'Siyah', 500, g, 1) for g in range(1, 30)])
        assert model_satis_ozeti(df2, '99')['toplam_90g'] == 29

    def test_veri_yok(self):
        df = _sales_df([('123', 'Bej', 500, 5, 1)])
        assert model_satis_ozeti(df, '999')['trend'] == 'veri_yok'

    def test_bos_df(self):
        bos = pd.DataFrame(columns=['model_kodu', 'renk', 'tutar', 'komisyon', 'tarih', 'adet'])
        assert model_satis_ozeti(bos, '099')['gunluk_satis'] == 0.0


# ═══ Flaş karar ════════════════════════════════════════════════════════

class TestFlasKarar:
    def test_karli_teklif_katil(self):
        k = flas_karar(_offer(), SATIS_VAR, PARAMS, -1.5)
        assert k['aksiyon'] == 'KATIL'
        assert k['oneri_fiyat'] == 1500  # Trendyol fiyatı aynen
        assert k['birim_kar'] > 0
        assert k['tahmini_satis'] > 0
        assert k['tahmini_kar'] > 0

    def test_taban_alti_katilma(self):
        # Trendyol fiyatı tabanın çok altında → varsayılan davranış KATILMA
        k = flas_karar(_offer(trendyol_fiyat=400), SATIS_VAR, PARAMS, -1.5)
        assert k['aksiyon'] == 'KATILMA'
        assert 'taban' in k['neden']

    def test_taban_alti_taban_yaz(self):
        k = flas_karar(_offer(trendyol_fiyat=400), SATIS_VAR, PARAMS, -1.5,
                       taban_asiminda='taban_yaz')
        assert k['aksiyon'] == 'KATIL'
        assert k['oneri_fiyat'] == k['taban_fiyat']
        assert 'kabul edilmeyebilir' in k['uyari']

    def test_min_kar_tabani_yukseltir(self):
        sifir = flas_karar(_offer(), SATIS_VAR, PARAMS, -1.5, min_kar=0)
        yuz = flas_karar(_offer(), SATIS_VAR, PARAMS, -1.5, min_kar=100)
        assert yuz['taban_fiyat'] > sifir['taban_fiyat']

    def test_stok_yok_katilma(self):
        k = flas_karar(_offer(stok=0), SATIS_VAR, PARAMS, -1.5)
        assert k['aksiyon'] == 'KATILMA'
        assert k['neden'] == 'Stok yok'

    def test_trendyol_fiyati_yok_katilma(self):
        k = flas_karar(_offer(trendyol_fiyat=0), SATIS_VAR, PARAMS, -1.5)
        assert k['aksiyon'] == 'KATILMA'

    def test_imkansiz_komisyon_katilma(self):
        k = flas_karar(_offer(komisyon=100), SATIS_VAR, PARAMS, -1.5)
        assert k['aksiyon'] == 'KATILMA'
        assert 'imkansız' in k['neden']

    def test_tahmin_stokla_sinirli_ve_uyari(self):
        hizli = {**SATIS_VAR, 'gunluk_satis': 10.0}
        k = flas_karar(_offer(stok=5), hizli, PARAMS, -1.5)
        assert k['tahmini_satis'] <= 5
        assert k['stok_uyari'] is True

    def test_pencere_olcekleme(self):
        k24 = flas_karar(_offer(pencere_saat=24), SATIS_VAR, PARAMS, -1.5)
        k3 = flas_karar(_offer(pencere_saat=3), SATIS_VAR, PARAMS, -1.5)
        assert k3['tahmini_satis'] < k24['tahmini_satis']

    def test_satis_verisi_yoksa_yine_katilabilir(self):
        k = flas_karar(_offer(), SATIS_YOK, PARAMS, -1.5)
        assert k['aksiyon'] == 'KATIL'          # kârlıysa katıl
        assert k['tahmini_satis'] == 0           # ama tahmin yok
        assert 'Satış verisi yok' in k['uyari']

    def test_indirim_orani(self):
        k = flas_karar(_offer(musteri_fiyat=2000, trendyol_fiyat=1500), SATIS_VAR, PARAMS, -1.5)
        assert k['indirim_pct'] == pytest.approx(25.0)


# ═══ Model filtreleri ══════════════════════════════════════════════════

class TestModelFiltre:
    def test_sifir_onek_iki_yonlu(self):
        kume = model_filtre_setleri(['0172', '99'])
        assert model_filtrede('172', kume)
        assert model_filtrede('0172', kume)
        assert model_filtrede('099', kume)
        assert not model_filtrede('4407', kume)

    def test_bos_liste(self):
        assert model_filtre_setleri(None) == set()
        assert not model_filtrede('0172', set())
