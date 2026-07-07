"""Akıllı Komisyon Motoru — saf analiz modülleri (mod1..mod10).

Flask'a ve DB'ye dokunmaz; tüm fonksiyonlar saf hesaplamadır ve
DataFrame/parametre alıp dict döndürür. Orkestrasyon ve route'lar
akilli_motor.py'dedir. Testler: tests/test_akilli_motor.py

Modüller:
  1. Satış Hızı + Üretim Zekası        mod1_satis_hizi
  2. Renk Segment Zekası               mod2_renk_segment
  3. Ürün Yaşam Döngüsü                mod3_yasam_dongusu
  4. Portföy Matrisi (BCG)             mod4_portfoy
  5. Gerçek Maliyet + Nakit Akış       mod5_gercek_maliyet
  6. Senaryo Simülatörü                mod6_senaryo
  7. Karar Motoru (Skor Kartı)         mod7_skor
  8. Üretim Kapasite Tahsisi           mod8_kapasite
  9. Sezon + Takvim Zekası             mod9_sezon
 10. Model Verimlilik Karşılaştırma    mod10_model_verimlilik

Ek: estimate_elasticity (geçmiş satıştan ölçülmüş fiyat elastikiyeti),
beklenen_birim_kar (iade oranını beklenen değer olarak katan birim kâr),
hesapla_skor_olcek (skor normalizasyonu için portföy p90 referansları).
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# ── Varsayılan Strateji Ağırlıkları ────────────────────────────────────
STRATEGY_WEIGHTS = {
    'buyume':      {'kar': 10, 'hacim': 30, 'stok_devir': 15, 'nakit': 15, 'yasam': 10, 'uretim': 10, 'renk': 10},
    'dengeli':     {'kar': 20, 'hacim': 20, 'stok_devir': 15, 'nakit': 15, 'yasam': 10, 'uretim': 10, 'renk': 10},
    'kar_odakli':  {'kar': 35, 'hacim': 10, 'stok_devir': 10, 'nakit': 15, 'yasam': 10, 'uretim': 10, 'renk': 10},
    'stok_eritme': {'kar': 5,  'hacim': 15, 'stok_devir': 35, 'nakit': 15, 'yasam': 10, 'uretim': 10, 'renk': 10},
}

# ── Fiyat Elastikiyeti ─────────────────────────────────────────────────
# ELASTICITY_BASE yalnızca geçmiş veriden ölçüm yapılamadığında kullanılan
# yedek değerdir; asıl taban estimate_elasticity() ile ölçülür.
ELASTICITY_BASE = -1.5
ELASTICITY_MULTIPLIER = {
    'motor': 0.5,
    'dengeli': 1.0,
    'yavas': 1.5,
    'olu': 2.0,
    'yukselen': 1.2,
    'veri_az': 1.0,
}

# Trend/segment/momentum sınıflaması için minimum satış adedi.
# Bunun altında 1-2 adetlik dalgalanmalar kategori değiştirtiyordu.
MIN_VERI_ADET = 5

# İade işlem maliyeti: dönüş kargosu üzerine işçilik/elleçleme (TL)
IADE_ISCILIK_TL = 10


# ═══════════════════════════════════════════════════════════════════════
#  YARDIMCI FONKSİYONLAR (Excel/SKU ayrıştırma)
# ═══════════════════════════════════════════════════════════════════════

def _resolve_commission_columns(columns, period: str = '3') -> list[str]:
    """Komisyon kademesi sütunlarını seçilen teslimat tarifesine göre çözer.

    Yeni Trendyol formatında '1.KOMİSYON'..'4.KOMİSYON' başlıkları İKİ kez
    geçer: 'Tarih aralığı (3 Gün)' ve 'Tarih aralığı (4 Gün)' bloklarından
    hemen sonra. pandas tekrar eden ikinci seti '.1' ekiyle adlandırdığı için
    güvenilir yöntem konumdur: ilgili marker'dan sonraki 4 sütun. Eski
    tek-tarifeli formatta marker yoktur; doğrudan '1.KOMİSYON'..'4.KOMİSYON'
    döner.
    """
    cols = [str(c) for c in columns]
    marker = f'Tarih aralığı ({period} Gün)'
    if marker in cols:
        i = cols.index(marker)
        return cols[i + 1:i + 5]
    return ['1.KOMİSYON', '2.KOMİSYON', '3.KOMİSYON', '4.KOMİSYON']


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
#  BEKLENEN BİRİM KÂR (iade oranı beklenen değer olarak)
# ═══════════════════════════════════════════════════════════════════════

def beklenen_birim_kar(fiyat: float, komisyon_oran: float, params: dict) -> float:
    """İade oranını beklenen değer olarak hesaba katan birim kâr (TL).

    Gönderilen her siparişin (1 - iade_oranı) kadarı kesinleşir; bu
    satışlarda fiyat - komisyon - ürün maliyeti kazanılır (iadede komisyon
    Trendyol'dan geri gelir, ürün stoğa döner → ürün maliyeti kaybolmaz).
    Kargo + paketleme her gönderimde harcanır; iade başına ayrıca dönüş
    kargosu + işçilik ödenir.

    Eski formül iadenin yalnızca kargo maliyetini sayıp satış gelirini %100
    kabul ediyordu; mod5 ile mod6 da birbirinden farklı kâr hesaplıyordu.
    Bu fonksiyon her ikisinin ortak ve tutarlı temeli.
    """
    maliyet = params.get('maliyet', 0)
    kargo = params.get('kargo', 20)
    iade = params.get('iade_orani', 8) / 100
    paketleme = params.get('paketleme', 5)

    satis_kari = fiyat * (1 - komisyon_oran / 100) - maliyet
    return (1 - iade) * satis_kari - kargo - paketleme - iade * (kargo + IADE_ISCILIK_TL)


# ═══════════════════════════════════════════════════════════════════════
#  ÖLÇÜLMÜŞ FİYAT ELASTİKİYETİ
# ═══════════════════════════════════════════════════════════════════════

def estimate_elasticity(sales_df: pd.DataFrame,
                        min_gozlem: int = 8) -> tuple[float | None, int]:
    """Geçmiş satışlardan portföy geneli fiyat elastikiyetini ölçer.

    Yöntem: her model+renk için haftalık ortalama birim fiyat ve toplam adet
    hesaplanır; ardışık haftalar arasında fiyat en az %5 değiştiyse
    Δlog(adet)/Δlog(fiyat) gözlemi alınır. Gözlemlerin medyanı elastikiyettir
    (medyan, tekil kampanya/stok-out gürültüsüne ortalamadan dayanıklıdır).

    Dönüş: (elastikiyet, gözlem_sayısı). Yeterli gözlem yoksa veya işaret
    pozitifse (fiyat artınca satış artmış görünüyorsa — gürültü) None döner
    ve çağıran ELASTICITY_BASE'e düşer. Sonuç [-4, -0.3] aralığına kıstırılır.
    """
    if sales_df.empty:
        return None, 0

    df = sales_df.dropna(subset=['tarih'])
    df = df[(df['adet'] > 0) & (df['tutar'] > 0)]
    if df.empty:
        return None, 0

    df = df.assign(hafta=df['tarih'].dt.to_period('W'))
    haftalik = df.groupby(['model_kodu', 'renk', 'hafta']).agg(
        adet=('adet', 'sum'), tutar=('tutar', 'sum'),
    ).reset_index()
    haftalik = haftalik.assign(fiyat=haftalik['tutar'] / haftalik['adet'])

    gozlemler = []
    for _, grup in haftalik.groupby(['model_kodu', 'renk']):
        grup = grup.sort_values('hafta')
        fiyatlar = grup['fiyat'].to_numpy()
        adetler = grup['adet'].to_numpy()
        haftalar = grup['hafta'].to_numpy()
        for i in range(1, len(grup)):
            # Yalnız ardışık haftalar (aradaki sıfır-satış haftaları atlanmasın)
            if (haftalar[i] - haftalar[i - 1]).n != 1:
                continue
            # Anlamlı fiyat değişimi + minimum hacim (gürültü filtresi)
            if adetler[i] < 2 or adetler[i - 1] < 2:
                continue
            d_fiyat = np.log(fiyatlar[i] / fiyatlar[i - 1])
            if abs(d_fiyat) < 0.05:
                continue
            d_adet = np.log(adetler[i] / adetler[i - 1])
            gozlemler.append(d_adet / d_fiyat)

    n = len(gozlemler)
    if n < min_gozlem:
        return None, n

    e = float(np.median(gozlemler))
    if e >= 0:
        # Talep fiyatla artıyor görünüyor → ölçüm güvenilmez, yedek değere düş
        return None, n
    return float(np.clip(e, -4.0, -0.3)), n


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

    # Trend: son 30 gün vs önceki 30 gün — ama çok az veriyle sınıflama
    # yapma: 2-3 adetlik dalgalanma 'yükseliyor/düşüyor' üretmesin.
    if toplam_adet < MIN_VERI_ADET:
        trend, trend_katsayi = 'veri_az', 1.0
    else:
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
    """Renk segmentini otomatik belirler: motor/dengeli/yavas/olu/yukselen/veri_az."""
    model_mask = sales_df['model_kodu'] == model
    model_sales = sales_df[model_mask]

    if model_sales.empty:
        return {'segment': 'olu', 'satis_orani': 0, 'aciklama': 'Modelde hiç satış yok'}

    renk_mask = model_sales['renk'] == renk
    renk_sales = model_sales[renk_mask]

    model_toplam = model_sales['adet'].sum()
    renk_toplam = renk_sales['adet'].sum()
    renk_orani = renk_toplam / model_toplam if model_toplam > 0 else 0

    # Model genelinde çok az satış varsa segment sınıflaması gürültüdür
    if model_toplam < MIN_VERI_ADET:
        return {'segment': 'veri_az', 'satis_orani': round(renk_orani * 100, 1),
                'aciklama': f'Yetersiz veri ({int(model_toplam)} satış/90g)'}

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
    elif son30 < MIN_VERI_ADET:
        # 30 günde 5 adetten az satışla momentum sınıflaması gürültüdür
        asama, aciklama = 'olgunluk', f'Veri az ({int(son30)} satış/30g), stabil varsayıldı'
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
    """Tam maliyet hesabı ve nakit akış hızı (iade beklenen-değerli)."""
    maliyet = params.get('maliyet', 0)
    kargo = params.get('kargo', 20)
    iade_orani = params.get('iade_orani', 8) / 100
    sermaye_aylik = params.get('sermaye_maliyeti', 2.5) / 100

    komisyon_tutar = fiyat * komisyon_oran / 100
    depo_gun = maliyet * sermaye_aylik / 30 * ort_stokta_gun if maliyet > 0 else 0

    net_kar = beklenen_birim_kar(fiyat, komisyon_oran, params)
    # Beklenen değer bazında efektif toplam maliyet (fiyat - beklenen kâr)
    toplam_maliyet = fiyat - net_kar
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
        'iade_maliyet': round(iade_orani * (kargo + IADE_ISCILIK_TL), 2),
    }


# ═══════════════════════════════════════════════════════════════════════
#  MODÜL 6: SENARYO SİMÜLATÖRÜ
# ═══════════════════════════════════════════════════════════════════════

def mod6_senaryo(fiyat: float, komisyon_oran: float, gunluk_satis: float,
                 stok: int, renk_segment: str, params: dict,
                 uretim_suresi: int,
                 elastic_base: float = ELASTICITY_BASE) -> dict:
    """Belirli bir kademe için 3 aylık projeksiyon.

    elastic_base: portföyden ölçülmüş elastikiyet (estimate_elasticity);
    ölçüm yoksa ELASTICITY_BASE varsayılanı. Segment çarpanı üzerine biner;
    çarpan SONRASI da [-4, -0.3] güvenlik aralığına kıstırılır (ölü segment
    çarpanı 2.0, ölçülmüş -4 tabanı -8'e taşıyıp projeksiyonu şişirmesin).
    """
    elastikiyet = float(np.clip(
        elastic_base * ELASTICITY_MULTIPLIER.get(renk_segment, 1.0), -4.0, -0.3))

    # Mevcut fiyata göre tahmini satış değişimi
    mevcut_fiyat = params.get('_mevcut_fiyat', fiyat)
    fiyat_degisim = (fiyat - mevcut_fiyat) / mevcut_fiyat if mevcut_fiyat > 0 else 0
    tahmini_satis = gunluk_satis * (1 + elastikiyet * fiyat_degisim)
    tahmini_satis = max(tahmini_satis, 0.01)  # minimum

    # mod5 ile aynı beklenen-değerli birim kâr (eskiden iki modül farklı
    # formül kullanıyor, mod6 kargo/paketleme/iadeyi hiç saymıyordu)
    net_kar = beklenen_birim_kar(fiyat, komisyon_oran, params)
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
        'elastikiyet': round(elastikiyet, 2),
    }


# ═══════════════════════════════════════════════════════════════════════
#  MODÜL 7: KARAR MOTORU (SKOR KARTI)
# ═══════════════════════════════════════════════════════════════════════

# Portföyden ölçek hesaplanamadığında kullanılan yedek referanslar
# (eski sabitlerle birebir aynı davranış: 50.000 TL/ay kâr = 100 puan,
#  3 adet/gün = 100 puan, ROI hızı 2 = 100 puan).
SKOR_OLCEK_VARSAYILAN = {'kar_p90': 50000.0, 'gunluk_p90': 3.0, 'roi_p90': 2.0}


def hesapla_skor_olcek(pre_data: list[dict]) -> dict:
    """Skor normalizasyon referanslarını portföyün kendi dağılımından üretir.

    Sabit eşikler ('50k TL = 100 puan') iş hacmi değişince skorları ya hep
    100'e yapıştırır ya da hep dipte bırakır. Bunun yerine portföyün p90'ı
    referans alınır: p90 üstü 100 puan, gerisi orantılı. Küçük portföyde
    (<5 varyant) güvenilir p90 çıkmaz → boş dict döner ve mod7 varsayılan
    ölçeğe düşer.
    """
    if len(pre_data) < 5:
        return {}

    olcek = {}
    kar = [p['gunluk_satis'] * 30 * p['birim_kar']
           for p in pre_data if p['gunluk_satis'] > 0 and p['birim_kar'] > 0]
    gunluk = [p['gunluk_satis'] for p in pre_data if p['gunluk_satis'] > 0]

    roi = []
    for p in pre_data:
        maliyet = p.get('maliyet', 0)
        if maliyet > 0 and p['gunluk_satis'] > 0 and p['stok'] > 0 and p['birim_kar'] > 0:
            ort_stokta = p['stok'] / p['gunluk_satis'] / 2
            if ort_stokta > 0:
                roi.append((p['birim_kar'] / maliyet) / ort_stokta * 30)

    for anahtar, degerler in (('kar_p90', kar), ('gunluk_p90', gunluk), ('roi_p90', roi)):
        if len(degerler) >= 5:
            p90 = float(np.percentile(degerler, 90))
            if p90 > 0:
                olcek[anahtar] = p90
    return olcek


def mod7_skor(senaryo: dict, mod1: dict, mod2: dict, mod3: dict,
              mod4: dict, mod5: dict, weights: dict, stok: int,
              uretim_suresi: int, kademe: int = 1,
              olcek: dict | None = None) -> float:
    """0-100 arası ağırlıklı skor hesaplar.

    olcek: hesapla_skor_olcek() çıktısı (portföy p90 referansları);
    verilmez/eksikse SKOR_OLCEK_VARSAYILAN kullanılır.
    """
    sc = {**SKOR_OLCEK_VARSAYILAN, **(olcek or {})}

    # Kar skoru (0-100): portföy p90'ına göre normalize
    kar_skor = min(senaryo['aylik_kar'] / sc['kar_p90'] * 100, 100) if senaryo['aylik_kar'] > 0 else 0

    # Hacim skoru (0-100): tahmini günlük satışa göre
    hacim_skor = min(senaryo['tahmini_gunluk_satis'] / sc['gunluk_p90'] * 100, 100)

    # Stok devir skoru (0-100): stok ne kadar hızlı eritiliyor
    bitis = senaryo['stok_bitis_gun']
    stok_skor = max(0, min(100, 100 - (bitis - 30) * 2)) if bitis < 999 else 0

    # Nakit akış skoru (0-100): ROI hızına göre
    nakit_skor = min(mod5['roi_hizi'] / sc['roi_p90'] * 100, 100) if mod5['roi_hizi'] > 0 else 0

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
    segment_skor_map = {'motor': 90, 'dengeli': 70, 'yukselen': 60,
                        'yavas': 40, 'olu': 10, 'veri_az': 50}
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
#  MODÜL 8: ÜRETİM KAPASİTE TAHSİSİ
# ═══════════════════════════════════════════════════════════════════════

def mod8_kapasite(results: list[dict], uretim_suresi: int,
                  guvenlik_gun: int, haftalik_kapasite: int = 0) -> dict:
    """Haftalık üretim kapasitesini alarm veren varyantlara dağıtır.

    İhtiyaç = hedef dönem (üretim süresi + güvenlik payı + 14 gün satış
    tamponu) boyunca satışı karşılamak için gereken stok açığı. Tahsis
    aciliyet sırasıyla (kalan_gun küçükten büyüğe) yapılır.
    haftalik_kapasite <= 0 ise kapasite sınırsız kabul edilir (plan yine
    üretilir, yalnızca kısıt uygulanmaz).
    """
    hedef_gun = uretim_suresi + guvenlik_gun + 14

    adaylar = []
    for r in results:
        if r.get('uretim_alarm') not in ('kritik', 'uyari'):
            continue
        ihtiyac = int(np.ceil(r['gunluk_satis'] * hedef_gun - r['stok']))
        if ihtiyac <= 0:
            continue
        adaylar.append({
            'model_kodu': r['model_kodu'],
            'renk': r['renk'],
            'alarm': r['uretim_alarm'],
            'kalan_gun': r['kalan_gun'],
            'gunluk_satis': r['gunluk_satis'],
            'stok': r['stok'],
            'ihtiyac': ihtiyac,
        })

    adaylar = sorted(adaylar, key=lambda a: a['kalan_gun'])

    sinirli = bool(haftalik_kapasite and haftalik_kapasite > 0)
    kalan_kapasite = haftalik_kapasite if sinirli else 0
    plan = []
    for a in adaylar:
        tahsis = min(a['ihtiyac'], kalan_kapasite) if sinirli else a['ihtiyac']
        if sinirli:
            kalan_kapasite -= tahsis
        plan.append({**a, 'tahsis': int(tahsis),
                     'karsilama': round(tahsis / a['ihtiyac'] * 100)})

    toplam_ihtiyac = sum(a['ihtiyac'] for a in plan)
    karsilanan = sum(a['tahsis'] for a in plan)
    return {
        'plan': plan,
        'toplam_ihtiyac': toplam_ihtiyac,
        'kapasite': int(haftalik_kapasite or 0),
        'karsilanan': karsilanan,
        'acik': max(toplam_ihtiyac - karsilanan, 0),
        'sinirli': sinirli,
    }


# ═══════════════════════════════════════════════════════════════════════
#  MODÜL 9: SEZON + TAKVİM ZEKASI
# ═══════════════════════════════════════════════════════════════════════

YAZ_KATEGORILERI = ('sandalet', 'terlik', 'espadril', 'plaj')
KIS_KATEGORILERI = ('bot', 'çizme', 'cizme', 'panduf')


def mod9_sezon(renk: str, kategori: str = '') -> dict:
    """Mevsim uyumu: önce ürün kategorisi (asıl sinyal), sonra renk.

    Ayakkabıda sezonu belirleyen esas şey kategoridir (sandalet/bot);
    renk yalnızca kategori mevsimsel değilse ikincil ipucudur.
    """
    now = datetime.now()
    ay = now.month
    yaz_sezonu = 3 <= ay <= 8  # bahar-yaz: Mart-Ağustos

    # 1) Kategori sinyali
    kat = str(kategori or '').lower()
    kat_yaz = any(k in kat for k in YAZ_KATEGORILERI)
    kat_kis = any(k in kat for k in KIS_KATEGORILERI)
    if kat_yaz or kat_kis:
        urun_yaz = kat_yaz  # ikisi de eşleşirse yaz kabul et (nadir)
        if urun_yaz == yaz_sezonu:
            return {'sezon_uyum': 'yuksek', 'uyari': '', 'skor': 95}
        donem = 'güz/kış' if urun_yaz else 'bahar/yaz'
        return {'sezon_uyum': 'dusuk',
                'uyari': f'Sezon dışı ürün: bu kategori {donem} döneminde yavaşlar',
                'skor': 35}

    # 2) Renk sinyali (kategori mevsimsel değilse)
    renk_lower = renk.lower()
    acik_renkler = ['beyaz', 'krem', 'bej', 'pembe', 'lila', 'açık']
    koyu_renkler = ['siyah', 'lacivert', 'bordo', 'kahve', 'füme', 'koyu']

    is_acik = any(r in renk_lower for r in acik_renkler)
    is_koyu = any(r in renk_lower for r in koyu_renkler)

    if yaz_sezonu:
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
#  MODÜL 10: MODEL VERİMLİLİK KARŞILAŞTIRMA
# ═══════════════════════════════════════════════════════════════════════

def mod10_model_verimlilik(results: list[dict]) -> list[dict]:
    """Model bazında verimlilik: stok başına aylık kâr sıralaması.

    Varyant sonuçlarını model koduna toplar; 'verim' = önerilen aylık kâr /
    toplam stok (TL/çift·ay). Hangi modelin rafta yatan parayı en iyi paraya
    çevirdiğini gösterir — üretim ve indirim önceliği buradan okunur.
    """
    modeller: dict[str, dict] = {}
    for r in results:
        m = modeller.setdefault(r['model_kodu'], {
            'model_kodu': r['model_kodu'],
            'kategori': r.get('kategori', ''),
            'varyant': 0, 'stok': 0, 'gunluk_satis': 0.0,
            'mevcut_aylik_kar': 0.0, 'onerilen_aylik_kar': 0.0,
            'en_iyi_skor': 0.0, 'kritik_alarm': 0,
        })
        m['varyant'] += 1
        m['stok'] += r['stok']
        m['gunluk_satis'] += r['gunluk_satis']
        m['mevcut_aylik_kar'] += r['mevcut_aylik_kar']
        m['onerilen_aylik_kar'] += r['onerilen_aylik_kar']
        m['en_iyi_skor'] = max(m['en_iyi_skor'], r['onerilen_skor'])
        if r.get('uretim_alarm') == 'kritik':
            m['kritik_alarm'] += 1

    cikti = []
    for m in modeller.values():
        cikti.append({
            **m,
            'gunluk_satis': round(m['gunluk_satis'], 2),
            'mevcut_aylik_kar': round(m['mevcut_aylik_kar'], 0),
            'onerilen_aylik_kar': round(m['onerilen_aylik_kar'], 0),
            'verim': round(m['onerilen_aylik_kar'] / m['stok'], 1) if m['stok'] > 0 else 0.0,
        })
    return sorted(cikti, key=lambda x: x['verim'], reverse=True)
