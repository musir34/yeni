"""Akıllı Komisyon Motoru – 10 Modüllü Karar Sistemi.

Trendyol komisyon tarifelerini, sipariş geçmişini ve stok verilerini
birleştirerek her model+renk varyantı için optimal kademe önerisi üretir.

Modüller:
  1. Satış Hızı + Üretim Zekası
  2. Renk Segment Zekası
  3. Ürün Yaşam Döngüsü
  4. Portföy Matrisi (BCG)
  5. Gerçek Maliyet + Nakit Akış
  6. Senaryo Simülatörü
  7. Karar Motoru (Skor Kartı)
  8. Üretim Kapasite Tahsisi
  9. Sezon + Takvim Zekası
  10. Model Verimlilik Karşılaştırma
"""

from flask import (
    Blueprint, request, jsonify, render_template,
    send_file, flash, redirect, url_for,
)
import pandas as pd
import numpy as np
import os
import json
import logging
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from login_logout import login_required, roles_required

logger = logging.getLogger(__name__)

akilli_motor_bp = Blueprint('akilli_motor', __name__)

UPLOAD_FOLDER = './uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Varsayılan Strateji Ağırlıkları ────────────────────────────────────
STRATEGY_WEIGHTS = {
    'buyume':      {'kar': 10, 'hacim': 30, 'stok_devir': 15, 'nakit': 15, 'yasam': 10, 'uretim': 10, 'renk': 10},
    'dengeli':     {'kar': 20, 'hacim': 20, 'stok_devir': 15, 'nakit': 15, 'yasam': 10, 'uretim': 10, 'renk': 10},
    'kar_odakli':  {'kar': 35, 'hacim': 10, 'stok_devir': 10, 'nakit': 15, 'yasam': 10, 'uretim': 10, 'renk': 10},
    'stok_eritme': {'kar': 5,  'hacim': 15, 'stok_devir': 35, 'nakit': 15, 'yasam': 10, 'uretim': 10, 'renk': 10},
}

# ── Fiyat Elastikiyeti Çarpanları ───────────────────────────────────────
ELASTICITY_BASE = -1.5
ELASTICITY_MULTIPLIER = {
    'motor': 0.5,
    'dengeli': 1.0,
    'yavas': 1.5,
    'olu': 2.0,
    'yukselen': 1.2,
}


# ═══════════════════════════════════════════════════════════════════════
#  YARDIMCI FONKSİYONLAR
# ═══════════════════════════════════════════════════════════════════════

def _allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _extract_model_from_sku(sku: str) -> str | None:
    """merchant_sku'dan model kodunu çıkarır: '0172-35 Bej' → '0172'."""
    if not sku:
        return None
    sku = str(sku).strip()
    if ',' in sku and '-' in sku.split(',')[1]:
        return None  # çoklu ürün satırı
    parts = sku.split('-', 1)
    code = parts[0].strip()
    return code if code else None


def _extract_color_from_sku(sku: str, model: str, beden: str = '') -> str:
    """merchant_sku'dan renk çıkarır."""
    if not sku or not model:
        return 'Standart'
    sku = str(sku).strip()
    prefix = f"{model}-"
    if sku.startswith(prefix):
        rest = sku[len(prefix):]
        # beden numarasını atla
        i = 0
        while i < len(rest) and (rest[i].isdigit()):
            i += 1
        color = rest[i:].lstrip(' -')
        return color if color else 'Standart'
    return 'Standart'


def _query_sales_data() -> pd.DataFrame:
    """Son 90 günlük sipariş verisini DB'den çeker."""
    from models import db, OrderShipped, OrderDelivered

    cutoff = datetime.now() - timedelta(days=90)
    rows = []

    for model_cls in [OrderShipped, OrderDelivered]:
        try:
            orders = model_cls.query.filter(
                model_cls.order_date >= cutoff
            ).with_entities(
                model_cls.merchant_sku,
                model_cls.product_color,
                model_cls.amount,
                model_cls.commission,
                model_cls.order_date,
                model_cls.quantity,
            ).all()

            for o in orders:
                model_code = _extract_model_from_sku(o.merchant_sku)
                if not model_code:
                    continue
                rows.append({
                    'model_kodu': model_code,
                    'renk': o.product_color or 'Standart',
                    'tutar': float(o.amount or 0),
                    'komisyon': float(o.commission or 0),
                    'tarih': o.order_date,
                    'adet': int(o.quantity or 1),
                })
        except Exception as e:
            logger.warning(f"Sipariş verisi çekme hatası ({model_cls.__name__}): {e}")

    if not rows:
        return pd.DataFrame(columns=['model_kodu', 'renk', 'tutar', 'komisyon', 'tarih', 'adet'])

    df = pd.DataFrame(rows)
    df['tarih'] = pd.to_datetime(df['tarih'], errors='coerce')
    return df


def _extract_color_from_tariff(sku: str, model_kodu: str, beden) -> str:
    """Tarife Excel'indeki SATICI STOK KODU'ndan renk çıkarır."""
    sku = str(sku).strip()
    beden_str = str(int(beden)) if pd.notna(beden) else ''
    prefix = f"{model_kodu}-{beden_str}"
    if sku.startswith(prefix):
        rest = sku[len(prefix):].lstrip(' -')
        return rest if rest else 'Standart'
    if beden_str and beden_str in sku:
        idx = sku.index(beden_str) + len(beden_str)
        rest = sku[idx:].lstrip(' -')
        return rest if rest else 'Standart'
    return 'Standart'


# ═══════════════════════════════════════════════════════════════════════
#  MODÜL 1: SATIŞ HIZI + ÜRETİM ZEKASI
# ═══════════════════════════════════════════════════════════════════════

def mod1_satis_hizi(sales_df: pd.DataFrame, model: str, renk: str,
                    stok: int, uretim_suresi: int, guvenlik_gun: int,
                    stok_eritme: bool = False) -> dict:
    """Satış hızı, stok tükenme ve üretim alarm hesabı."""
    mask = (sales_df['model_kodu'] == model) & (sales_df['renk'] == renk)
    subset = sales_df[mask].copy()

    if subset.empty:
        return {
            'gunluk_satis': 0, 'haftalik_satis': 0, 'aylik_satis': 0,
            'toplam_90gun': 0, 'kalan_gun': 999, 'uretim_alarm': 'yok',
            'uretim_emri_gun': 999, 'trend': 'veri_yok',
            'trend_katsayi': 1.0,
        }

    now = datetime.now()
    gun_sayisi = max((now - subset['tarih'].min()).days, 1)
    toplam_adet = int(subset['adet'].sum())
    gunluk = toplam_adet / gun_sayisi

    kalan_gun = stok / gunluk if gunluk > 0 else 999
    kritik_esik = uretim_suresi + guvenlik_gun
    uretim_emri_gun = kalan_gun - uretim_suresi

    if stok_eritme:
        alarm = 'yok'
    elif kalan_gun <= kritik_esik:
        alarm = 'kritik'
    elif kalan_gun <= kritik_esik * 2:
        alarm = 'uyari'
    else:
        alarm = 'yok'

    # Trend: son 30 gün vs önceki 30 gün
    d30 = now - timedelta(days=30)
    d60 = now - timedelta(days=60)
    son30 = subset[subset['tarih'] >= d30]['adet'].sum()
    onceki30 = subset[(subset['tarih'] >= d60) & (subset['tarih'] < d30)]['adet'].sum()
    trend_katsayi = son30 / onceki30 if onceki30 > 0 else (1.5 if son30 > 0 else 0.5)

    if trend_katsayi > 1.15:
        trend = 'yukseliyor'
    elif trend_katsayi < 0.85:
        trend = 'dusuyor'
    else:
        trend = 'sabit'

    return {
        'gunluk_satis': round(gunluk, 2),
        'haftalik_satis': round(gunluk * 7, 1),
        'aylik_satis': round(gunluk * 30, 1),
        'toplam_90gun': toplam_adet,
        'kalan_gun': round(kalan_gun, 0),
        'uretim_alarm': alarm,
        'uretim_emri_gun': round(max(uretim_emri_gun, 0), 0),
        'trend': trend,
        'trend_katsayi': round(trend_katsayi, 2),
    }


# ═══════════════════════════════════════════════════════════════════════
#  MODÜL 2: RENK SEGMENT ZEKASI
# ═══════════════════════════════════════════════════════════════════════

def mod2_renk_segment(sales_df: pd.DataFrame, model: str, renk: str) -> dict:
    """Renk segmentini otomatik belirler: motor/dengeli/yavas/olu/yukselen."""
    model_mask = sales_df['model_kodu'] == model
    model_sales = sales_df[model_mask]

    if model_sales.empty:
        return {'segment': 'olu', 'satis_orani': 0, 'aciklama': 'Modelde hiç satış yok'}

    renk_mask = model_sales['renk'] == renk
    renk_sales = model_sales[renk_mask]

    model_toplam = model_sales['adet'].sum()
    renk_toplam = renk_sales['adet'].sum()
    renk_orani = renk_toplam / model_toplam if model_toplam > 0 else 0

    # Renk sayısına göre beklenen oran
    renk_sayisi = model_sales['renk'].nunique()
    beklenen_oran = 1 / renk_sayisi if renk_sayisi > 0 else 0.5

    # Trend
    now = datetime.now()
    d30 = now - timedelta(days=30)
    d60 = now - timedelta(days=60)
    son30 = renk_sales[renk_sales['tarih'] >= d30]['adet'].sum()
    onceki30 = renk_sales[(renk_sales['tarih'] >= d60) & (renk_sales['tarih'] < d30)]['adet'].sum()

    if renk_toplam == 0:
        segment = 'olu'
        aciklama = '21+ gündür satış yok'
    elif son30 > 0 and onceki30 == 0:
        segment = 'yukselen'
        aciklama = 'Son dönemde satış başladı'
    elif renk_orani >= beklenen_oran * 1.5:
        segment = 'motor'
        aciklama = f'Ortalamadan {renk_orani/beklenen_oran:.1f}x daha hızlı'
    elif renk_orani >= beklenen_oran * 0.5:
        segment = 'dengeli'
        aciklama = 'Ortalama satış hızında'
    else:
        segment = 'yavas'
        aciklama = f'Ortalamanın {renk_orani/beklenen_oran:.1f}x altında'

    return {'segment': segment, 'satis_orani': round(renk_orani * 100, 1), 'aciklama': aciklama}


# ═══════════════════════════════════════════════════════════════════════
#  MODÜL 3: ÜRÜN YAŞAM DÖNGÜSÜ
# ═══════════════════════════════════════════════════════════════════════

def mod3_yasam_dongusu(sales_df: pd.DataFrame, model: str, renk: str) -> dict:
    """Ürün aşamasını tespit eder: lansman/yukselis/olgunluk/dusus/olu."""
    mask = (sales_df['model_kodu'] == model) & (sales_df['renk'] == renk)
    subset = sales_df[mask]

    if subset.empty:
        return {'asama': 'olu', 'yas_gun': 999, 'momentum': 0, 'aciklama': 'Satış verisi yok'}

    now = datetime.now()
    ilk_satis = subset['tarih'].min()
    yas_gun = (now - ilk_satis).days if pd.notna(ilk_satis) else 999
    toplam_adet = int(subset['adet'].sum())

    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)
    son7 = subset[subset['tarih'] >= d7]['adet'].sum()
    son30 = subset[subset['tarih'] >= d30]['adet'].sum()
    son30_ort_7 = son30 / 4.3 if son30 > 0 else 0
    momentum = son7 / son30_ort_7 if son30_ort_7 > 0 else 0

    son21 = subset[subset['tarih'] >= (now - timedelta(days=21))]['adet'].sum()

    if son21 == 0:
        asama, aciklama = 'olu', '21+ gündür satış yok'
    elif yas_gun < 45 and toplam_adet < 15:
        asama, aciklama = 'lansman', f'{yas_gun} günlük ürün, {toplam_adet} satış'
    elif momentum > 1.2:
        asama, aciklama = 'yukselis', f'Momentum {momentum:.1f}x (satışlar artıyor)'
    elif momentum < 0.8:
        asama, aciklama = 'dusus', f'Momentum {momentum:.1f}x (satışlar azalıyor)'
    else:
        asama, aciklama = 'olgunluk', f'Momentum {momentum:.1f}x (stabil)'

    return {'asama': asama, 'yas_gun': yas_gun, 'momentum': round(momentum, 2), 'aciklama': aciklama}


# ═══════════════════════════════════════════════════════════════════════
#  MODÜL 4: PORTFÖY MATRİSİ (BCG)
# ═══════════════════════════════════════════════════════════════════════

def mod4_portfoy(gunluk_satis: float, birim_kar: float,
                 ort_gunluk_satis: float, ort_birim_kar: float) -> dict:
    """BCG matrisinde pozisyon belirler."""
    yuksek_satis = gunluk_satis >= ort_gunluk_satis
    yuksek_kar = birim_kar >= ort_birim_kar

    if yuksek_satis and yuksek_kar:
        return {'grup': 'yildiz', 'aksiyon': 'Stok koparma, üretimde öncelik', 'icon': '⭐'}
    elif not yuksek_satis and yuksek_kar:
        return {'grup': 'nakit', 'aksiyon': 'Marjı koru, üretim azalt', 'icon': '🐄'}
    elif yuksek_satis and not yuksek_kar:
        return {'grup': 'firsatci', 'aksiyon': 'Kademe düşür, marj artır', 'icon': '❓'}
    else:
        return {'grup': 'sorun', 'aksiyon': 'Tasfiye et veya üretimden çıkar', 'icon': '🔴'}


# ═══════════════════════════════════════════════════════════════════════
#  MODÜL 5: GERÇEK MALİYET + NAKİT AKIŞ
# ═══════════════════════════════════════════════════════════════════════

def mod5_gercek_maliyet(fiyat: float, komisyon_oran: float, params: dict,
                        ort_stokta_gun: float) -> dict:
    """Tam maliyet hesabı ve nakit akış hızı."""
    maliyet = params.get('maliyet', 0)
    kargo = params.get('kargo', 20)
    iade_orani = params.get('iade_orani', 8) / 100
    paketleme = params.get('paketleme', 5)
    sermaye_aylik = params.get('sermaye_maliyeti', 2.5) / 100

    komisyon_tutar = fiyat * komisyon_oran / 100
    iade_maliyet = iade_orani * (kargo + 10)  # kargo + işçilik
    depo_gun = maliyet * sermaye_aylik / 30 * ort_stokta_gun if maliyet > 0 else 0

    toplam_maliyet = maliyet + kargo + iade_maliyet + paketleme + komisyon_tutar
    net_kar = fiyat - toplam_maliyet
    kar_marji = (net_kar / fiyat * 100) if fiyat > 0 else 0

    # ROI Hızı: kar/maliyet oranının stokta kalma süresine bölümü
    roi_hizi = 0
    if maliyet > 0 and ort_stokta_gun > 0:
        roi_hizi = (net_kar / maliyet) / ort_stokta_gun * 30

    return {
        'komisyon_tutar': round(komisyon_tutar, 2),
        'toplam_maliyet': round(toplam_maliyet, 2),
        'net_kar': round(net_kar, 2),
        'kar_marji': round(kar_marji, 1),
        'roi_hizi': round(roi_hizi, 3),
        'depo_maliyet': round(depo_gun, 2),
    }


# ═══════════════════════════════════════════════════════════════════════
#  MODÜL 6: SENARYO SİMÜLATÖRÜ
# ═══════════════════════════════════════════════════════════════════════

def mod6_senaryo(fiyat: float, komisyon_oran: float, gunluk_satis: float,
                 stok: int, renk_segment: str, params: dict,
                 uretim_suresi: int) -> dict:
    """Belirli bir kademe için 3 aylık projeksiyon."""
    maliyet = params.get('maliyet', 0)
    elastikiyet = ELASTICITY_BASE * ELASTICITY_MULTIPLIER.get(renk_segment, 1.0)

    # Mevcut fiyata göre tahmini satış değişimi
    mevcut_fiyat = params.get('_mevcut_fiyat', fiyat)
    fiyat_degisim = (fiyat - mevcut_fiyat) / mevcut_fiyat if mevcut_fiyat > 0 else 0
    tahmini_satis = gunluk_satis * (1 + elastikiyet * fiyat_degisim)
    tahmini_satis = max(tahmini_satis, 0.01)  # minimum

    net_kar = fiyat * (1 - komisyon_oran / 100) - maliyet if maliyet > 0 else fiyat * (1 - komisyon_oran / 100)
    aylik_kar = tahmini_satis * 30 * net_kar
    stok_bitis_gun = stok / tahmini_satis if tahmini_satis > 0 else 999

    # Üretim uyarısı
    uretim_uyari = ''
    if stok_bitis_gun < (uretim_suresi + 5):
        uretim_uyari = 'Hemen üretim emri ver!'
    elif stok_bitis_gun < (uretim_suresi + 5) * 2:
        uretim_uyari = 'Üretim planla'

    return {
        'tahmini_gunluk_satis': round(tahmini_satis, 2),
        'tahmini_aylik_satis': round(tahmini_satis * 30, 0),
        'birim_kar': round(net_kar, 2),
        'aylik_kar': round(aylik_kar, 0),
        '3aylik_kar': round(aylik_kar * 3, 0),
        'stok_bitis_gun': round(stok_bitis_gun, 0),
        'uretim_uyari': uretim_uyari,
    }


# ═══════════════════════════════════════════════════════════════════════
#  MODÜL 7: KARAR MOTORU (SKOR KARTI)
# ═══════════════════════════════════════════════════════════════════════

def mod7_skor(senaryo: dict, mod1: dict, mod2: dict, mod3: dict,
              mod4: dict, mod5: dict, weights: dict, stok: int,
              uretim_suresi: int, kademe: int = 1) -> float:
    """0-100 arası ağırlıklı skor hesaplar."""
    # Kar skoru (0-100): aylik kara göre normalize
    kar_skor = min(senaryo['aylik_kar'] / 500, 100) if senaryo['aylik_kar'] > 0 else 0

    # Hacim skoru (0-100): tahmini günlük satışa göre
    hacim_skor = min(senaryo['tahmini_gunluk_satis'] / 3 * 100, 100)

    # Stok devir skoru (0-100): stok ne kadar hızlı eritiliyor
    bitis = senaryo['stok_bitis_gun']
    stok_skor = max(0, min(100, 100 - (bitis - 30) * 2)) if bitis < 999 else 0

    # Nakit akış skoru (0-100): ROI hızına göre
    nakit_skor = min(mod5['roi_hizi'] * 50, 100) if mod5['roi_hizi'] > 0 else 0

    # Yaşam döngüsü uyum skoru
    yasam_map = {
        'lansman': {'1': 40, '2': 80, '3': 90, '4': 60},
        'yukselis': {'1': 95, '2': 40, '3': 20, '4': 5},
        'olgunluk': {'1': 85, '2': 60, '3': 40, '4': 20},
        'dusus': {'1': 30, '2': 70, '3': 80, '4': 60},
        'olu': {'1': 5, '2': 30, '3': 60, '4': 90},
    }
    asama = mod3['asama']
    kademe_str = str(kademe)
    yasam_skor = yasam_map.get(asama, {}).get(kademe_str, 50)

    # Üretim güvenlik skoru (0-100)
    kalan = mod1['kalan_gun']
    kritik = uretim_suresi + 5
    if kalan >= kritik * 3:
        uretim_skor = 100
    elif kalan >= kritik:
        uretim_skor = 60
    elif kalan > 0:
        uretim_skor = 20
    else:
        uretim_skor = 0

    # Renk segment skoru
    segment_skor_map = {'motor': 90, 'dengeli': 70, 'yukselen': 60, 'yavas': 40, 'olu': 10}
    renk_skor = segment_skor_map.get(mod2['segment'], 50)

    w = weights
    total = w['kar'] + w['hacim'] + w['stok_devir'] + w['nakit'] + w['yasam'] + w['uretim'] + w['renk']

    skor = (
        w['kar'] * kar_skor +
        w['hacim'] * hacim_skor +
        w['stok_devir'] * stok_skor +
        w['nakit'] * nakit_skor +
        w['yasam'] * yasam_skor +
        w['uretim'] * uretim_skor +
        w['renk'] * renk_skor
    ) / total

    return round(skor, 1)


# ═══════════════════════════════════════════════════════════════════════
#  MODÜL 9: SEZON + TAKVİM ZEKASI
# ═══════════════════════════════════════════════════════════════════════

def mod9_sezon(renk: str) -> dict:
    """Mevsim bazlı renk uyarısı."""
    now = datetime.now()
    ay = now.month
    renk_lower = renk.lower()

    acik_renkler = ['beyaz', 'krem', 'bej', 'pembe', 'lila', 'saks', 'açık']
    koyu_renkler = ['siyah', 'lacivert', 'bordo', 'kahve', 'füme', 'koyu']

    is_acik = any(r in renk_lower for r in acik_renkler)
    is_koyu = any(r in renk_lower for r in koyu_renkler)

    # Bahar/yaz: Mart-Ağustos, Güz/kış: Eylül-Şubat
    if 3 <= ay <= 8:  # bahar-yaz
        if is_acik:
            return {'sezon_uyum': 'yuksek', 'uyari': '', 'skor': 90}
        elif is_koyu:
            return {'sezon_uyum': 'dusuk', 'uyari': 'Koyu renk bahar/yaz döneminde yavaşlar', 'skor': 50}
    else:  # güz-kış
        if is_koyu:
            return {'sezon_uyum': 'yuksek', 'uyari': '', 'skor': 90}
        elif is_acik:
            return {'sezon_uyum': 'dusuk', 'uyari': 'Açık renk güz/kış döneminde yavaşlar', 'skor': 50}

    return {'sezon_uyum': 'normal', 'uyari': '', 'skor': 70}


# ═══════════════════════════════════════════════════════════════════════
#  ANA ANALİZ ORKESTRATÖRÜ
# ═══════════════════════════════════════════════════════════════════════

def run_full_analysis(tariff_df: pd.DataFrame, params: dict,
                      excluded_models: list[str] | None = None) -> dict:
    """Tüm modülleri çalıştırıp birleşik sonuç üretir."""

    # ── Veri Hazırlığı ──────────────────────────────────────────────
    tariff_df.columns = [str(c).strip() for c in tariff_df.columns]

    numeric_cols = [
        '1.Fiyat Alt Limit', '2.Fiyat Üst Limiti', '2.Fiyat Alt Limit',
        '3.Fiyat Üst Limiti', '3.Fiyat Alt Limit', '4.Fiyat Üst Limiti',
        '1.KOMİSYON', '2.KOMİSYON', '3.KOMİSYON', '4.KOMİSYON',
        'KOMİSYONA ESAS FİYAT', 'GÜNCEL KOMİSYON', 'GÜNCEL TSF',
    ]
    for col in numeric_cols:
        if col in tariff_df.columns:
            tariff_df[col] = pd.to_numeric(tariff_df[col], errors='coerce').fillna(0)

    tariff_df['_RENK'] = tariff_df.apply(
        lambda r: _extract_color_from_tariff(
            r.get('SATICI STOK KODU', ''), str(r.get('MODEL KODU', '')), r.get('BEDEN')
        ), axis=1,
    )

    excluded = {m.strip().upper() for m in (excluded_models or []) if m.strip()}

    # Sipariş verisini çek
    sales_df = _query_sales_data()

    uretim_suresi = params.get('uretim_suresi', 25)
    guvenlik_gun = params.get('guvenlik_gun', 5)
    strategy = params.get('strateji', 'dengeli')
    weights = STRATEGY_WEIGHTS.get(strategy, STRATEGY_WEIGHTS['dengeli'])

    # ── Renk Varyantı Bazında Gruplama ──────────────────────────────
    grouped = tariff_df.groupby(['MODEL KODU', '_RENK'], sort=False)

    results = []
    production_alerts = []
    all_gunluk_satis = []
    all_birim_kar = []

    # İlk geçiş: temel verileri topla (portföy ortalamaları için)
    pre_data = []
    for (model_kodu, renk), group in grouped:
        model_str = str(model_kodu).strip()
        if model_str.upper() in excluded:
            continue
        first = group.iloc[0]
        stok = int(group['STOK'].sum()) if 'STOK' in group.columns else 0
        guncel_tsf = float(first.get('GÜNCEL TSF', 0) or 0)
        maliyet = params.get('maliyet', 0)
        guncel_kom = float(first.get('GÜNCEL KOMİSYON', 0) or 0)
        birim_kar = guncel_tsf * (1 - guncel_kom / 100) - maliyet if maliyet > 0 else guncel_tsf * (1 - guncel_kom / 100)

        # Renk eşleştirme (pre-pass)
        eff_renk = renk
        mm = sales_df['model_kodu'] == model_str
        if mm.any():
            db_rs = sales_df[mm]['renk'].unique()
            if renk not in db_rs:
                rl = renk.lower()
                for dr in db_rs:
                    if rl in dr.lower() or dr.lower() in rl:
                        eff_renk = dr
                        break

        is_stok_eritme = strategy == 'stok_eritme'
        m1 = mod1_satis_hizi(sales_df, model_str, eff_renk, stok, uretim_suresi, guvenlik_gun, stok_eritme=is_stok_eritme)
        pre_data.append({
            'model': model_str, 'renk': renk, 'eff_renk': eff_renk, 'stok': stok,
            'gunluk_satis': m1['gunluk_satis'], 'birim_kar': birim_kar,
            'group': group, 'first': first, 'm1': m1,
        })

    if not pre_data:
        return {'success': True, 'results': [], 'alerts': [], 'stats': {}, 'portfolio': {}}

    ort_gunluk = np.mean([p['gunluk_satis'] for p in pre_data]) if pre_data else 0.01
    ort_birim_kar = np.mean([p['birim_kar'] for p in pre_data]) if pre_data else 0

    # ── İkinci Geçiş: Tüm Modülleri Çalıştır ───────────────────────
    for p in pre_data:
        model_str = p['model']
        renk = p['renk']
        group = p['group']
        first = p['first']
        stok = p['stok']
        m1 = p['m1']

        guncel_tsf = float(first.get('GÜNCEL TSF', 0) or 0)
        guncel_kom = float(first.get('GÜNCEL KOMİSYON', 0) or 0)

        k1 = float(first.get('1.KOMİSYON', 0) or 0)
        k2 = float(first.get('2.KOMİSYON', 0) or 0)
        k3 = float(first.get('3.KOMİSYON', 0) or 0)
        k4 = float(first.get('4.KOMİSYON', 0) or 0)
        ust2 = float(first.get('2.Fiyat Üst Limiti', 0) or 0)
        ust3 = float(first.get('3.Fiyat Üst Limiti', 0) or 0)
        ust4 = float(first.get('4.Fiyat Üst Limiti', 0) or 0)

        # Renk eşleştirme: Excel renk adı ile DB renk adı farklı olabilir
        # Önce birebir eşleşmeyi dene, yoksa model bazlı en yakın rengi bul
        effective_renk = renk
        model_mask = sales_df['model_kodu'] == model_str
        if model_mask.any():
            db_renkler = sales_df[model_mask]['renk'].unique()
            if renk not in db_renkler:
                # Basit içerik eşleştirmesi: "Bej Kırışık" ↔ "Bej Kırışık Rugan"
                renk_lower = renk.lower()
                for db_renk in db_renkler:
                    if renk_lower in db_renk.lower() or db_renk.lower() in renk_lower:
                        effective_renk = db_renk
                        break

        # Modül 2: Renk Segment
        m2 = mod2_renk_segment(sales_df, model_str, effective_renk)

        # Modül 3: Yaşam Döngüsü
        m3 = mod3_yasam_dongusu(sales_df, model_str, effective_renk)

        # Modül 4: Portföy (BCG)
        m4 = mod4_portfoy(m1['gunluk_satis'], p['birim_kar'], ort_gunluk, ort_birim_kar)

        # Modül 9: Sezon
        m9 = mod9_sezon(renk)

        # ── Her Kademe İçin Senaryo + Skor ──────────────────────────
        tiers = []
        params_with_price = {**params, '_mevcut_fiyat': guncel_tsf}

        tier_configs = [
            (1, guncel_tsf, k1),
            (2, ust2, k2),
            (3, ust3, k3),
            (4, ust4, k4),
        ]

        for kademe, fiyat, kom in tier_configs:
            if fiyat <= 0 or kom <= 0:
                continue

            ort_stokta_gun = stok / m1['gunluk_satis'] / 2 if m1['gunluk_satis'] > 0 else 90
            m5 = mod5_gercek_maliyet(fiyat, kom, params, ort_stokta_gun)
            m6 = mod6_senaryo(fiyat, kom, m1['gunluk_satis'], stok,
                              m2['segment'], params_with_price, uretim_suresi)
            skor = mod7_skor(m6, m1, m2, m3, m4, m5, weights, stok, uretim_suresi, kademe)

            tiers.append({
                'kademe': kademe,
                'fiyat': round(fiyat, 2),
                'komisyon_oran': kom,
                'net_kar': m5['net_kar'],
                'kar_marji': m5['kar_marji'],
                'tahmini_gunluk': m6['tahmini_gunluk_satis'],
                'tahmini_aylik': m6['tahmini_aylik_satis'],
                'aylik_kar': m6['aylik_kar'],
                'stok_bitis_gun': m6['stok_bitis_gun'],
                'roi_hizi': m5['roi_hizi'],
                'skor': skor,
                'uretim_uyari': m6['uretim_uyari'],
            })

        if not tiers:
            continue

        best = max(tiers, key=lambda t: t['skor'])
        mevcut = tiers[0]  # kademe 1

        # Aksiyon belirleme
        if best['kademe'] == 1:
            aksiyon = 'TUT'
        elif m3['asama'] == 'olu':
            aksiyon = 'TASFİYE'
        else:
            aksiyon = 'DÜŞÜR'

        # Üretim alarmı
        if m1['uretim_alarm'] == 'kritik':
            production_alerts.append({
                'model': model_str, 'renk': renk, 'stok': stok,
                'kalan_gun': m1['kalan_gun'],
                'gunluk_satis': m1['gunluk_satis'],
                'mesaj': f'{model_str}-{renk}: {m1["kalan_gun"]:.0f} gün stok, üretim {uretim_suresi} gün → HEMEN BAŞLAT',
            })

        results.append({
            'model_kodu': model_str,
            'renk': renk,
            'urun_ismi': str(first.get('ÜRÜN İSMİ', '')),
            'kategori': str(first.get('KATEGORİ', '')),
            'stok': stok,
            'varyant': len(group),
            'guncel_tsf': guncel_tsf,
            'guncel_komisyon': guncel_kom,
            # Modül 1
            'gunluk_satis': m1['gunluk_satis'],
            'aylik_satis': m1['aylik_satis'],
            'kalan_gun': m1['kalan_gun'],
            'trend': m1['trend'],
            'trend_katsayi': m1['trend_katsayi'],
            'uretim_alarm': m1['uretim_alarm'],
            'uretim_emri_gun': m1['uretim_emri_gun'],
            # Modül 2
            'renk_segment': m2['segment'],
            'segment_aciklama': m2['aciklama'],
            'satis_orani': m2['satis_orani'],
            # Modül 3
            'yasam_asama': m3['asama'],
            'yasam_aciklama': m3['aciklama'],
            'momentum': m3['momentum'],
            # Modül 4
            'bcg_grup': m4['grup'],
            'bcg_icon': m4['icon'],
            'bcg_aksiyon': m4['aksiyon'],
            # Modül 9
            'sezon_uyum': m9['sezon_uyum'],
            'sezon_uyari': m9['uyari'],
            # Karar
            'aksiyon': aksiyon,
            'onerilen_kademe': best['kademe'],
            'onerilen_fiyat': best['fiyat'],
            'onerilen_komisyon': best['komisyon_oran'],
            'onerilen_skor': best['skor'],
            'mevcut_skor': mevcut['skor'],
            'skor_fark': round(best['skor'] - mevcut['skor'], 1),
            'onerilen_aylik_kar': best['aylik_kar'],
            'mevcut_aylik_kar': mevcut['aylik_kar'],
            'kar_fark_aylik': round(best['aylik_kar'] - mevcut['aylik_kar'], 0),
            # Tüm kademeler
            'kademeler': tiers,
        })

    # ── Portföy Dağılımı ────────────────────────────────────────────
    portfolio = {'yildiz': 0, 'nakit': 0, 'firsatci': 0, 'sorun': 0}
    for r in results:
        portfolio[r['bcg_grup']] = portfolio.get(r['bcg_grup'], 0) + 1

    # ── Excel Güncelleme ────────────────────────────────────────────
    updated_df = tariff_df.copy()
    updated_df['Tarife Sonuna Kadar Uygula'] = 'Evet'

    for r in results:
        if r['aksiyon'] != 'TUT':
            mask = (updated_df['MODEL KODU'].astype(str).str.strip() == r['model_kodu']) & \
                   (updated_df['_RENK'] == r['renk'])
            updated_df.loc[mask, 'YENİ TSF (FİYAT GÜNCELLE)'] = r['onerilen_fiyat']

    if excluded:
        mask_exc = updated_df['MODEL KODU'].astype(str).str.strip().str.upper().isin(excluded)
        updated_df = updated_df[~mask_exc]

    updated_df = updated_df.drop(columns=['_RENK'], errors='ignore')

    # ── İstatistikler ───────────────────────────────────────────────
    stats = {
        'toplam_varyant': len(results),
        'tut': sum(1 for r in results if r['aksiyon'] == 'TUT'),
        'dusur': sum(1 for r in results if r['aksiyon'] == 'DÜŞÜR'),
        'tasfiye': sum(1 for r in results if r['aksiyon'] == 'TASFİYE'),
        'uretim_alarm': len(production_alerts),
        'toplam_stok': sum(r['stok'] for r in results),
        'mevcut_aylik_kar': sum(r['mevcut_aylik_kar'] for r in results),
        'onerilen_aylik_kar': sum(r['onerilen_aylik_kar'] for r in results),
    }
    stats['kar_artis'] = round(stats['onerilen_aylik_kar'] - stats['mevcut_aylik_kar'], 0)

    return {
        'success': True,
        'results': sorted(results, key=lambda x: x['skor_fark'], reverse=True),
        'alerts': sorted(production_alerts, key=lambda x: x['kalan_gun']),
        'stats': stats,
        'portfolio': portfolio,
        'updated_df': updated_df,
    }


# ═══════════════════════════════════════════════════════════════════════
#  FLASK ROUTE'LARI
# ═══════════════════════════════════════════════════════════════════════

@akilli_motor_bp.route('/akilli-motor', methods=['GET'])
@login_required
@roles_required('admin')
def akilli_motor_sayfasi():
    return render_template('akilli_motor.html')


@akilli_motor_bp.route('/akilli-motor/analiz', methods=['POST'])
@login_required
@roles_required('admin')
def akilli_motor_analiz():
    if 'excel_file' not in request.files:
        return jsonify({'success': False, 'message': 'Dosya yüklenmedi'}), 400

    file = request.files['excel_file']
    if not file.filename or not _allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Geçersiz dosya'}), 400

    filename = secure_filename(file.filename)
    save_path = os.path.join(UPLOAD_FOLDER, f"motor_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}")

    try:
        file.save(save_path)
        ext = filename.rsplit('.', 1)[1].lower()
        df = pd.read_excel(save_path, engine='openpyxl' if ext == 'xlsx' else None)

        params = {
            'maliyet': float(request.form.get('maliyet', 0) or 0),
            'kargo': float(request.form.get('kargo', 20) or 20),
            'iade_orani': float(request.form.get('iade_orani', 8) or 8),
            'paketleme': float(request.form.get('paketleme', 5) or 5),
            'sermaye_maliyeti': float(request.form.get('sermaye_maliyeti', 2.5) or 2.5),
            'uretim_suresi': int(request.form.get('uretim_suresi', 25) or 25),
            'guvenlik_gun': int(request.form.get('guvenlik_gun', 5) or 5),
            'strateji': request.form.get('strateji', 'dengeli'),
        }

        excluded_raw = request.form.get('excluded_models', '')
        excluded = [m.strip() for m in excluded_raw.replace('\n', ',').replace(';', ',').split(',') if m.strip()]

        analysis = run_full_analysis(df, params, excluded)

        if not analysis['success']:
            return jsonify(analysis), 400

        # Excel kaydet
        output_path = save_path.replace('.xls', '_motor_optimized.xls')
        analysis['updated_df'].to_excel(output_path, index=False, engine='openpyxl')

        # DataFrame'i response'tan çıkar
        del analysis['updated_df']
        analysis['download_file'] = os.path.basename(output_path)

        return jsonify(analysis)

    except Exception as e:
        logger.exception("Akıllı motor analiz hatası")
        return jsonify({'success': False, 'message': f'Hata: {str(e)}'}), 500
    finally:
        try:
            if os.path.exists(save_path):
                os.remove(save_path)
        except OSError:
            pass


@akilli_motor_bp.route('/akilli-motor/indir/<filename>', methods=['GET'])
@login_required
@roles_required('admin')
def akilli_motor_indir(filename: str):
    safe_name = secure_filename(filename)
    file_path = os.path.join(UPLOAD_FOLDER, safe_name)
    if not os.path.exists(file_path):
        flash('Dosya bulunamadı.', 'danger')
        return redirect(url_for('akilli_motor.akilli_motor_sayfasi'))

    return send_file(
        file_path, as_attachment=True,
        download_name=f"akilli_motor_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
