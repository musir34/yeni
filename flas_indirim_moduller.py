"""Flaş İndirim Motoru — saf karar modülleri.

Trendyol Flaş İndirim teklif Excel'i ('TeklifÜrünleri' sayfası) satır bazlı
tekliflerden oluşur: her satır bir ürün × tarih penceresi (24 saat / 3 saat).
Trendyol her teklif için bir flaş fiyat önerir ('24 Saat Fiyat' / '3 Saat
Fiyat'); satıcı katılmak istediği satırlarda 'Senin Belirlediğin Flaş
Fiyatı' sütununu doldurur, katılmadığı satırları boş bırakır.

Bu modül Flask'a ve DB'ye dokunmaz. Orkestrasyon ve route'lar
flas_indirim.py'dedir. Testler: tests/test_flas_indirim.py

Karar mantığı:
  1. taban_fiyat: iade/kargo/komisyon/maliyet sonrası minimum kârı (min_kar)
     koruyan en düşük satış fiyatı (akilli_motor_moduller.beklenen_birim_kar
     formülünün fiyata göre analitik tersi).
  2. Trendyol'un önerdiği flaş fiyat tabanın üstündeyse → KATIL (öneri =
     Trendyol fiyatı; en cazip görünürlük, kâr korunur).
  3. Tabanın altındaysa → parametreye göre KATILMA (varsayılan) ya da tabanı
     yaz (Trendyol kabul etmeyebilir — uyarıyla).
  4. Tahmini flaş satışı: model satış hızı × elastikiyet etkisi × flaş
     görünürlük çarpanı × pencere süresi; stokla sınırlandırılır.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from akilli_motor_moduller import IADE_ISCILIK_TL, beklenen_birim_kar

# Trendyol flaş teklif Excel'inde bulunması zorunlu sütunlar
GEREKLI_SUTUNLAR = (
    'Model Kodu', 'Ürün Adı', 'Stok', 'Mevcut Fiyat',
    'Müşterinin Gördüğü Fiyat', 'Mevcut Komisyon',
    '24 Saat Fiyat', '3 Saat Fiyat', 'Senin Belirlediğin Flaş Fiyatı',
    '24 Saat Flaş Başlangıç Tarihi', '3 Saat Flaş Başlangıç Tarihi',
)

# Flaş sayfası görünürlüğünün normal listeye göre satış çarpanı (varsayılan).
# Ölçülemeyen bir büyüklük — kullanıcı parametreyle ayarlar.
FLAS_GORUNURLUK_VARSAYILAN = 3.0

MIN_VERI_ADET = 5  # trend sınıflaması için minimum satış


def _norm_model(model: str) -> tuple[str, str]:
    """Model kodunun ham ve sıfır-öneksiz halini döndürür ('099' → '99')."""
    s = str(model or '').strip()
    return s, (s.lstrip('0') or '0')


def taban_fiyat(komisyon_oran: float, params: dict, min_kar: float = 0.0) -> float | None:
    """min_kar TL beklenen birim kârı koruyan en düşük satış fiyatı.

    beklenen_birim_kar(f) = (1-r)·(f·(1-k) - m) - kargo - pak - r·(kargo+işç.)
    doğrusal olduğundan f analitik çözülür:
        f = (min_kar + kargo + pak + r·(kargo+işç.) + (1-r)·m) / ((1-r)·(1-k))

    Komisyon %100'ü aşarsa ya da iade %100 ise kârlı fiyat yoktur → None.
    """
    maliyet = params.get('maliyet', 0)
    kargo = params.get('kargo', 20)
    r = params.get('iade_orani', 20) / 100
    paketleme = params.get('paketleme', 5)

    payda = (1 - r) * (1 - komisyon_oran / 100)
    if payda <= 0:
        return None
    pay = min_kar + kargo + paketleme + r * (kargo + IADE_ISCILIK_TL) + (1 - r) * maliyet
    return round(pay / payda, 2)


def model_satis_ozeti(sales_df: pd.DataFrame, model: str) -> dict:
    """Model bazlı (tüm renkler) satış özeti; sıfır-önek toleranslı eşleşme."""
    ham, oneksiz = _norm_model(model)
    if sales_df.empty:
        return {'gunluk_satis': 0.0, 'son30_gunluk': 0.0, 'trend': 'veri_yok', 'toplam_90g': 0}

    norm = sales_df['model_kodu'].astype(str).str.strip()
    mask = norm.isin({ham, oneksiz}) | (norm.str.lstrip('0').replace('', '0') == oneksiz)
    subset = sales_df[mask]
    if subset.empty:
        return {'gunluk_satis': 0.0, 'son30_gunluk': 0.0, 'trend': 'veri_yok', 'toplam_90g': 0}

    now = datetime.now()
    gun_sayisi = max((now - subset['tarih'].min()).days, 1)
    toplam = int(subset['adet'].sum())
    gunluk = toplam / gun_sayisi

    d30 = now - timedelta(days=30)
    d60 = now - timedelta(days=60)
    son30 = int(subset[subset['tarih'] >= d30]['adet'].sum())
    onceki30 = int(subset[(subset['tarih'] >= d60) & (subset['tarih'] < d30)]['adet'].sum())

    if toplam < MIN_VERI_ADET:
        trend = 'veri_az'
    elif onceki30 == 0:
        trend = 'yukseliyor' if son30 > 0 else 'veri_az'
    elif son30 / onceki30 > 1.15:
        trend = 'yukseliyor'
    elif son30 / onceki30 < 0.85:
        trend = 'dusuyor'
    else:
        trend = 'sabit'

    return {
        'gunluk_satis': round(gunluk, 2),
        'son30_gunluk': round(son30 / 30, 2),
        'trend': trend,
        'toplam_90g': toplam,
    }


def flas_karar(offer: dict, satis: dict, params: dict,
               elastic_base: float,
               min_kar: float = 0.0,
               gorunurluk: float = FLAS_GORUNURLUK_VARSAYILAN,
               taban_asiminda: str = 'katilma') -> dict:
    """Tek bir flaş teklif satırı için karar üretir.

    offer: {'model_kodu', 'stok', 'mevcut_fiyat', 'musteri_fiyat',
            'komisyon', 'trendyol_fiyat', 'pencere_saat'}
    satis: model_satis_ozeti() çıktısı
    params: maliyet (bu modele özel, TL) + kargo/iade_orani/paketleme
    taban_asiminda: Trendyol fiyatı tabanın altındaysa 'katilma' (varsayılan)
                    veya 'taban_yaz' (tabanı öner; Trendyol reddedebilir).

    Dönüş: {'aksiyon': KATIL|KATILMA, 'oneri_fiyat', 'taban_fiyat',
            'birim_kar', 'indirim_pct', 'tahmini_satis', 'tahmini_kar',
            'stok_uyari', 'neden', 'uyari'}
    """
    trendyol_fiyat = float(offer.get('trendyol_fiyat') or 0)
    musteri_fiyat = float(offer.get('musteri_fiyat') or 0)
    komisyon = float(offer.get('komisyon') or 0)
    stok = int(offer.get('stok') or 0)
    pencere_saat = float(offer.get('pencere_saat') or 24)

    taban = taban_fiyat(komisyon, params, min_kar)

    sonuc = {
        'aksiyon': 'KATILMA', 'oneri_fiyat': None, 'taban_fiyat': taban,
        'birim_kar': None, 'indirim_pct': None,
        'tahmini_satis': 0.0, 'tahmini_kar': 0.0,
        'stok_uyari': False, 'neden': '', 'uyari': '',
    }

    if trendyol_fiyat <= 0:
        return {**sonuc, 'neden': 'Trendyol flaş fiyatı yok'}
    if stok <= 0:
        return {**sonuc, 'neden': 'Stok yok'}
    if taban is None:
        return {**sonuc, 'neden': f'Komisyon %{komisyon:g} ile kârlı fiyat imkansız'}

    uyari = ''
    if trendyol_fiyat >= taban:
        oneri = trendyol_fiyat
    elif taban_asiminda == 'taban_yaz':
        oneri = taban
        uyari = 'Trendyol önerisinin üstünde (taban yazıldı) — kabul edilmeyebilir'
    else:
        zarar = beklenen_birim_kar(trendyol_fiyat, komisyon, params)
        return {**sonuc,
                'neden': f'Trendyol fiyatı ({trendyol_fiyat:.2f}) taban '
                         f'({taban:.2f}) altında: birim {zarar:.0f} TL',
                }

    birim_kar = beklenen_birim_kar(oneri, komisyon, params)

    # Tahmini flaş satışı: mevcut müşteri fiyatına göre fiyat değişimi ×
    # elastikiyet + flaş görünürlük çarpanı, pencere süresine ölçekli.
    gunluk = satis.get('gunluk_satis', 0) or 0
    tahmin = 0.0
    if gunluk > 0 and musteri_fiyat > 0:
        degisim = (oneri - musteri_fiyat) / musteri_fiyat
        lift = max(1 + elastic_base * degisim, 0.1)
        tahmin = gunluk * lift * gorunurluk * (pencere_saat / 24)
    tahmin = min(round(tahmin, 1), stok)

    indirim_pct = round((musteri_fiyat - oneri) / musteri_fiyat * 100, 1) if musteri_fiyat > 0 else None
    stok_uyari = bool(tahmin >= stok * 0.8 and stok > 0)

    return {
        'aksiyon': 'KATIL',
        'oneri_fiyat': round(oneri, 2),
        'taban_fiyat': taban,
        'birim_kar': round(birim_kar, 2),
        'indirim_pct': indirim_pct,
        'tahmini_satis': tahmin,
        'tahmini_kar': round(birim_kar * tahmin, 0),
        'stok_uyari': stok_uyari,
        'neden': '',
        'uyari': uyari or ('Satış verisi yok — tahmin yapılamadı' if gunluk <= 0 else ''),
    }


def model_filtre_setleri(model_listesi: list[str] | None) -> set[str]:
    """Hariç/dahil listelerini normalize eder (ham + sıfır-öneksiz)."""
    kume = set()
    for m in (model_listesi or []):
        s = str(m).strip().upper()
        if not s:
            continue
        kume.add(s)
        kume.add(s.lstrip('0') or '0')
    return kume


def model_filtrede(model: str, kume: set[str]) -> bool:
    ham, oneksiz = _norm_model(model)
    return ham.upper() in kume or oneksiz.upper() in kume
