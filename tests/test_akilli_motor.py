"""Akıllı Komisyon Motoru saf modül testleri (akilli_motor_moduller).

DB'ye ve Flask'a dokunmaz — tüm modüller sentetik DataFrame'lerle test edilir.

Çalıştırma:
    DISABLE_JOBS=1 pytest tests/test_akilli_motor.py -v
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from akilli_motor_moduller import (  # noqa: E402
    ELASTICITY_BASE, STRATEGY_WEIGHTS, SKOR_OLCEK_VARSAYILAN,
    _extract_model_from_sku, _extract_color_from_tariff,
    _resolve_commission_columns,
    beklenen_birim_kar, estimate_elasticity, hesapla_skor_olcek,
    mod1_satis_hizi, mod2_renk_segment, mod3_yasam_dongusu, mod4_portfoy,
    mod5_gercek_maliyet, mod6_senaryo, mod7_skor, mod8_kapasite,
    mod9_sezon, mod10_model_verimlilik,
)

NOW = datetime.now()

PARAMS = {
    'maliyet': 300, 'kargo': 20, 'iade_orani': 20,
    'paketleme': 5, 'sermaye_maliyeti': 2.5,
}


def _sales_df(rows):
    """rows: (model, renk, tutar, gun_once, adet) listesi → sales DataFrame."""
    return pd.DataFrame([{
        'model_kodu': m, 'renk': r, 'tutar': t, 'komisyon': t * 0.2,
        'tarih': NOW - timedelta(days=g), 'adet': a,
    } for (m, r, t, g, a) in rows])


def _bos_sales():
    return pd.DataFrame(columns=['model_kodu', 'renk', 'tutar', 'komisyon', 'tarih', 'adet'])


# ═══ Yardımcılar ═══════════════════════════════════════════════════════

class TestYardimcilar:
    def test_resolve_commission_eski_format(self):
        cols = ['MODEL KODU', '1.KOMİSYON', '2.KOMİSYON', '3.KOMİSYON', '4.KOMİSYON']
        assert _resolve_commission_columns(cols, '3') == \
            ['1.KOMİSYON', '2.KOMİSYON', '3.KOMİSYON', '4.KOMİSYON']

    def test_resolve_commission_yeni_format(self):
        cols = ['MODEL KODU',
                'Tarih aralığı (3 Gün)', '1.KOMİSYON', '2.KOMİSYON', '3.KOMİSYON', '4.KOMİSYON',
                'Tarih aralığı (4 Gün)', '1.KOMİSYON.1', '2.KOMİSYON.1', '3.KOMİSYON.1', '4.KOMİSYON.1']
        assert _resolve_commission_columns(cols, '3') == \
            ['1.KOMİSYON', '2.KOMİSYON', '3.KOMİSYON', '4.KOMİSYON']
        assert _resolve_commission_columns(cols, '4') == \
            ['1.KOMİSYON.1', '2.KOMİSYON.1', '3.KOMİSYON.1', '4.KOMİSYON.1']

    def test_extract_model_from_sku(self):
        assert _extract_model_from_sku('0172-35 Bej') == '0172'
        assert _extract_model_from_sku('') is None
        assert _extract_model_from_sku('0172-36, 0450-37 Siyah') is None  # çoklu satır

    def test_extract_color_from_tariff(self):
        assert _extract_color_from_tariff('0172-36-Bej Rugan', '0172', 36) == 'Bej Rugan'
        assert _extract_color_from_tariff('0172-36', '0172', 36) == 'Standart'


# ═══ Beklenen birim kâr ════════════════════════════════════════════════

class TestBeklenenBirimKar:
    def test_el_hesabiyla_ayni(self):
        # fiyat 1000, kom %20 → satış kârı = 800 - 300 = 500
        # beklenen = 0.8*500 - 20 - 5 - 0.2*(20+10) = 400 - 25 - 6 = 369
        assert beklenen_birim_kar(1000, 20, PARAMS) == pytest.approx(369.0)

    def test_iade_orani_arttikca_kar_duser(self):
        dusuk = beklenen_birim_kar(1000, 20, {**PARAMS, 'iade_orani': 5})
        yuksek = beklenen_birim_kar(1000, 20, {**PARAMS, 'iade_orani': 30})
        assert yuksek < dusuk

    def test_maliyetsiz_de_calisir(self):
        kar = beklenen_birim_kar(1000, 20, {**PARAMS, 'maliyet': 0})
        assert kar == pytest.approx(369.0 + 0.8 * 300)


# ═══ Elastikiyet ölçümü ════════════════════════════════════════════════

class TestElastikiyet:
    def test_sentetik_veriden_olcum(self):
        # 12 hafta, fiyat 100↔90 alternesi; talep elastikiyet -2 ile üretilir
        rows = []
        for h in range(12):
            fiyat = 100 if h % 2 == 0 else 90
            adet = int(round(10 * (fiyat / 100) ** -2))  # e = -2
            rows.append(('M1', 'Siyah', fiyat * adet, 84 - h * 7, adet))
        e, n = estimate_elasticity(_sales_df(rows))
        assert n >= 8
        assert e is not None
        assert -4.0 <= e <= -0.3
        assert e == pytest.approx(-2.0, abs=0.6)

    def test_yetersiz_veri_none(self):
        rows = [('M1', 'Siyah', 100, 10, 3), ('M1', 'Siyah', 90, 3, 4)]
        e, n = estimate_elasticity(_sales_df(rows))
        assert e is None

    def test_bos_df_none(self):
        e, n = estimate_elasticity(_bos_sales())
        assert (e, n) == (None, 0)

    def test_pozitif_iliski_gurultu_sayilir(self):
        # Fiyat artarken satış da artıyorsa (gürültü) ölçüm reddedilmeli
        rows = []
        for h in range(12):
            fiyat = 100 if h % 2 == 0 else 90
            adet = 12 if h % 2 == 0 else 8  # pahalıyken DAHA çok satmış
            rows.append(('M1', 'Siyah', fiyat * adet, 84 - h * 7, adet))
        e, n = estimate_elasticity(_sales_df(rows))
        assert e is None


# ═══ Modül 1: Satış hızı ═══════════════════════════════════════════════

class TestMod1:
    def test_veri_yok(self):
        r = mod1_satis_hizi(_bos_sales(), 'M1', 'Siyah', 100, 25, 5)
        assert r['trend'] == 'veri_yok'
        assert r['gunluk_satis'] == 0

    def test_az_veri_trend_siniflamaz(self):
        rows = [('M1', 'Siyah', 500, 10, 1), ('M1', 'Siyah', 500, 40, 2)]
        r = mod1_satis_hizi(_sales_df(rows), 'M1', 'Siyah', 100, 25, 5)
        assert r['trend'] == 'veri_az'
        assert r['trend_katsayi'] == 1.0

    def test_yukselen_trend(self):
        rows = [('M1', 'Siyah', 500, g, 1) for g in range(1, 21)]          # son 30: 20 adet
        rows += [('M1', 'Siyah', 500, g, 1) for g in range(35, 40)]        # önceki 30: 5 adet
        r = mod1_satis_hizi(_sales_df(rows), 'M1', 'Siyah', 100, 25, 5)
        assert r['trend'] == 'yukseliyor'
        assert r['trend_katsayi'] > 1.15

    def test_kritik_alarm(self):
        # ~1 adet/gün satış, 10 stok → 10 gün kalan < 30 kritik eşik
        rows = [('M1', 'Siyah', 500, g, 1) for g in range(1, 60)]
        r = mod1_satis_hizi(_sales_df(rows), 'M1', 'Siyah', 10, 25, 5)
        assert r['uretim_alarm'] == 'kritik'

    def test_stok_eritmede_alarm_yok(self):
        rows = [('M1', 'Siyah', 500, g, 1) for g in range(1, 60)]
        r = mod1_satis_hizi(_sales_df(rows), 'M1', 'Siyah', 10, 25, 5, stok_eritme=True)
        assert r['uretim_alarm'] == 'yok'


# ═══ Modül 2: Renk segmenti ════════════════════════════════════════════

class TestMod2:
    def test_az_veri(self):
        rows = [('M1', 'Siyah', 500, 10, 2), ('M1', 'Bej', 500, 20, 2)]
        r = mod2_renk_segment(_sales_df(rows), 'M1', 'Siyah')
        assert r['segment'] == 'veri_az'

    def test_motor_segment(self):
        # Siyah 60 güne yayılmış (son30 ve önceki30 dolu → 'yukselen' tetiklenmez)
        rows = [('M1', 'Siyah', 500, g * 2 + 1, 1) for g in range(30)]
        rows += [('M1', 'Bej', 500, 10, 2), ('M1', 'Krem', 500, 15, 2)]
        r = mod2_renk_segment(_sales_df(rows), 'M1', 'Siyah')
        assert r['segment'] == 'motor'

    def test_hic_satis_yok(self):
        r = mod2_renk_segment(_bos_sales(), 'M1', 'Siyah')
        assert r['segment'] == 'olu'


# ═══ Modül 3: Yaşam döngüsü ════════════════════════════════════════════

class TestMod3:
    def test_olu_21_gun(self):
        rows = [('M1', 'Siyah', 500, 40, 5), ('M1', 'Siyah', 500, 50, 5)]
        r = mod3_yasam_dongusu(_sales_df(rows), 'M1', 'Siyah')
        assert r['asama'] == 'olu'

    def test_lansman(self):
        rows = [('M1', 'Siyah', 500, 5, 2), ('M1', 'Siyah', 500, 10, 2)]
        r = mod3_yasam_dongusu(_sales_df(rows), 'M1', 'Siyah')
        assert r['asama'] == 'lansman'

    def test_az_veri_stabil(self):
        # 60+ günlük ürün, son 30 günde 5'ten az satış → momentum sınıflaması yok
        rows = [('M1', 'Siyah', 500, 70, 10), ('M1', 'Siyah', 500, 65, 10),
                ('M1', 'Siyah', 500, 10, 2), ('M1', 'Siyah', 500, 15, 2)]
        r = mod3_yasam_dongusu(_sales_df(rows), 'M1', 'Siyah')
        assert r['asama'] == 'olgunluk'
        assert 'Veri az' in r['aciklama']


# ═══ Modül 4: BCG ══════════════════════════════════════════════════════

class TestMod4:
    def test_dort_ceyrek(self):
        assert mod4_portfoy(5, 100, 2, 50)['grup'] == 'yildiz'
        assert mod4_portfoy(1, 100, 2, 50)['grup'] == 'nakit'
        assert mod4_portfoy(5, 10, 2, 50)['grup'] == 'firsatci'
        assert mod4_portfoy(1, 10, 2, 50)['grup'] == 'sorun'


# ═══ Modül 5: Gerçek maliyet ═══════════════════════════════════════════

class TestMod5:
    def test_net_kar_beklenen_deger(self):
        r = mod5_gercek_maliyet(1000, 20, PARAMS, 30)
        assert r['net_kar'] == pytest.approx(369.0)
        assert r['kar_marji'] == pytest.approx(36.9)
        assert r['toplam_maliyet'] == pytest.approx(1000 - 369.0)

    def test_roi_pozitif(self):
        r = mod5_gercek_maliyet(1000, 20, PARAMS, 30)
        assert r['roi_hizi'] == pytest.approx((369.0 / 300) / 30 * 30, abs=0.01)


# ═══ Modül 6: Senaryo ══════════════════════════════════════════════════

class TestMod6:
    def test_fiyat_dusunce_satis_artar(self):
        p = {**PARAMS, '_mevcut_fiyat': 1000}
        r = mod6_senaryo(800, 20, 2.0, 100, 'dengeli', p, 25)
        assert r['tahmini_gunluk_satis'] > 2.0

    def test_elastic_base_etkisi(self):
        p = {**PARAMS, '_mevcut_fiyat': 1000}
        zayif = mod6_senaryo(800, 20, 2.0, 100, 'dengeli', p, 25, elastic_base=-0.5)
        guclu = mod6_senaryo(800, 20, 2.0, 100, 'dengeli', p, 25, elastic_base=-3.0)
        assert guclu['tahmini_gunluk_satis'] > zayif['tahmini_gunluk_satis']

    def test_elastikiyet_carpan_sonrasi_kisitlanir(self):
        # Ölçülmüş -4 taban × 'olu' çarpanı 2.0 = -8 OLMAMALI; -4'e kıstırılır.
        # %20 indirimde tavan artış: 1 + (-4)(-0.2) = 1.8x
        p = {**PARAMS, '_mevcut_fiyat': 1000}
        r = mod6_senaryo(800, 20, 2.0, 100, 'olu', p, 25, elastic_base=-4.0)
        assert r['elastikiyet'] == -4.0
        assert r['tahmini_gunluk_satis'] == pytest.approx(2.0 * 1.8)

    def test_birim_kar_mod5_ile_tutarli(self):
        p = {**PARAMS, '_mevcut_fiyat': 1000}
        m6 = mod6_senaryo(1000, 20, 2.0, 100, 'dengeli', p, 25)
        m5 = mod5_gercek_maliyet(1000, 20, PARAMS, 30)
        assert m6['birim_kar'] == pytest.approx(m5['net_kar'])


# ═══ Modül 7: Skor + ölçek ═════════════════════════════════════════════

def _skor_girdileri():
    senaryo = {'aylik_kar': 10000, 'tahmini_gunluk_satis': 2.0, 'stok_bitis_gun': 50}
    m1 = {'kalan_gun': 100}
    m2 = {'segment': 'dengeli'}
    m3 = {'asama': 'olgunluk'}
    m4 = {'grup': 'yildiz'}
    m5 = {'roi_hizi': 1.0}
    return senaryo, m1, m2, m3, m4, m5


class TestMod7:
    def test_olceksiz_varsayilan(self):
        s = mod7_skor(*_skor_girdileri(), STRATEGY_WEIGHTS['dengeli'], 100, 25, 1)
        assert 0 <= s <= 100

    def test_kucuk_p90_skoru_yukseltir(self):
        girdiler = _skor_girdileri()
        w = STRATEGY_WEIGHTS['dengeli']
        buyuk = mod7_skor(*girdiler, w, 100, 25, 1, olcek={'kar_p90': 100000})
        kucuk = mod7_skor(*girdiler, w, 100, 25, 1, olcek={'kar_p90': 5000})
        assert kucuk > buyuk

    def test_veri_az_segment_patlamaz(self):
        senaryo, m1, _, m3, m4, m5 = _skor_girdileri()
        s = mod7_skor(senaryo, m1, {'segment': 'veri_az'}, m3, m4, m5,
                      STRATEGY_WEIGHTS['dengeli'], 100, 25, 1)
        assert 0 <= s <= 100


class TestSkorOlcek:
    def test_kucuk_portfoy_bos(self):
        assert hesapla_skor_olcek([{'gunluk_satis': 1, 'birim_kar': 100, 'stok': 10, 'maliyet': 300}] * 4) == {}

    def test_p90_hesaplanir(self):
        pre = [{'gunluk_satis': g, 'birim_kar': 100 + g * 10, 'stok': 50, 'maliyet': 300}
               for g in range(1, 9)]
        olcek = hesapla_skor_olcek(pre)
        assert olcek['kar_p90'] > 0
        assert olcek['gunluk_p90'] > 0
        assert olcek['roi_p90'] > 0


# ═══ Modül 8: Kapasite tahsisi ═════════════════════════════════════════

def _kapasite_results():
    return [
        {'model_kodu': 'A', 'renk': 'Siyah', 'uretim_alarm': 'kritik',
         'kalan_gun': 10, 'gunluk_satis': 3.0, 'stok': 30},
        {'model_kodu': 'B', 'renk': 'Bej', 'uretim_alarm': 'uyari',
         'kalan_gun': 40, 'gunluk_satis': 2.0, 'stok': 80},
        {'model_kodu': 'C', 'renk': 'Krem', 'uretim_alarm': 'yok',
         'kalan_gun': 200, 'gunluk_satis': 1.0, 'stok': 200},
    ]


class TestMod8:
    def test_alarmsizlar_dahil_edilmez(self):
        plan = mod8_kapasite(_kapasite_results(), 25, 5, 0)
        assert {p['model_kodu'] for p in plan['plan']} == {'A', 'B'}

    def test_aciliyet_sirasi(self):
        plan = mod8_kapasite(_kapasite_results(), 25, 5, 0)
        assert plan['plan'][0]['model_kodu'] == 'A'  # kalan_gun 10 < 40

    def test_kapasite_kisiti(self):
        # hedef 44 gün: A ihtiyaç = ceil(3*44-30)=102, B = ceil(2*44-80)=8
        plan = mod8_kapasite(_kapasite_results(), 25, 5, 50)
        assert plan['sinirli'] is True
        assert plan['plan'][0]['tahsis'] == 50   # A önce, kapasiteyi alır
        assert plan['plan'][1]['tahsis'] == 0    # B'ye kalmaz
        assert plan['acik'] == plan['toplam_ihtiyac'] - 50

    def test_sinirsiz_mod(self):
        plan = mod8_kapasite(_kapasite_results(), 25, 5, 0)
        assert plan['sinirli'] is False
        assert all(p['tahsis'] == p['ihtiyac'] for p in plan['plan'])
        assert plan['acik'] == 0


# ═══ Modül 9: Sezon ════════════════════════════════════════════════════

YAZ_SEZONU = 3 <= datetime.now().month <= 8


class TestMod9:
    def test_kategori_oncelikli(self):
        sandalet = mod9_sezon('Siyah', 'Kadın Sandalet')
        bot = mod9_sezon('Beyaz', 'Kadın Bot')
        if YAZ_SEZONU:
            assert sandalet['sezon_uyum'] == 'yuksek'   # koyu renk olsa bile
            assert bot['sezon_uyum'] == 'dusuk'         # açık renk olsa bile
        else:
            assert sandalet['sezon_uyum'] == 'dusuk'
            assert bot['sezon_uyum'] == 'yuksek'

    def test_kategorisiz_renk_sinyali(self):
        beyaz = mod9_sezon('Beyaz', 'Sneaker')  # sneaker mevsimsel değil
        assert beyaz['sezon_uyum'] == ('yuksek' if YAZ_SEZONU else 'dusuk')

    def test_saks_artik_notr(self):
        r = mod9_sezon('Saks', '')
        assert r['sezon_uyum'] == 'normal'


# ═══ Modül 10: Model verimlilik ════════════════════════════════════════

class TestMod10:
    def test_toplama_ve_siralama(self):
        results = [
            {'model_kodu': 'A', 'kategori': 'Bot', 'stok': 100, 'gunluk_satis': 2.0,
             'mevcut_aylik_kar': 5000, 'onerilen_aylik_kar': 6000,
             'onerilen_skor': 70, 'uretim_alarm': 'yok'},
            {'model_kodu': 'A', 'kategori': 'Bot', 'stok': 50, 'gunluk_satis': 1.0,
             'mevcut_aylik_kar': 2000, 'onerilen_aylik_kar': 3000,
             'onerilen_skor': 80, 'uretim_alarm': 'kritik'},
            {'model_kodu': 'B', 'kategori': 'Sandalet', 'stok': 10, 'gunluk_satis': 3.0,
             'mevcut_aylik_kar': 4000, 'onerilen_aylik_kar': 4500,
             'onerilen_skor': 90, 'uretim_alarm': 'yok'},
        ]
        v = mod10_model_verimlilik(results)
        assert len(v) == 2
        assert v[0]['model_kodu'] == 'B'                    # 450 TL/çift > 60 TL/çift
        a = next(x for x in v if x['model_kodu'] == 'A')
        assert a['varyant'] == 2
        assert a['stok'] == 150
        assert a['verim'] == pytest.approx(9000 / 150, abs=0.1)
        assert a['en_iyi_skor'] == 80
        assert a['kritik_alarm'] == 1

    def test_bos_liste(self):
        assert mod10_model_verimlilik([]) == []
