# finans_cari_service.py
"""
📒 Finans — Cari hesap (tedarikçi / müşteri defteri) iş kuralları.

bakiye = "bizim borcumuz": pozitif → biz ona borçluyuz, negatif → o bize borçlu (alacak).

Hareketler (yon: +1 borcumuz artar, -1 azalır):
- alim     (+1) mal girişi, kalem dökümlü; kasaya dokunmaz
- odeme    (-1) ona ödedik → Elde/Banka'dan `cari_odeme` gider kaydı (finans_service._hareket)
- satis    (-1) ona mal verdik (alacak), kalem dökümlü; kasaya dokunmaz
- tahsilat (+1) o bize ödedi → Beyazıt'a `cari_tahsilat` gelir kaydı

Kasa bağı olan hareketler tek transaction'da yazılır ve finans_cari_hareket.islem_id ile
bağlanır; iptal iki tarafı birlikte geri alır (finans_service.islem_iptal bağı tanır).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from models import db, FinansCari, FinansCariHareket, FinansCariKalem, FinansIslem
import finans_service as fs
from finans_service import FinansHata, IKI_HANE

CARI_TURLERI = ('tedarikci', 'musteri', 'diger', 'calisan')
CARI_TUR_ETIKET = {'tedarikci': 'Tedarikçi', 'musteri': 'Müşteri', 'diger': 'Diğer', 'calisan': 'Çalışan'}
HAREKET_TURLERI = {'alim': +1, 'odeme': -1, 'satis': -1, 'tahsilat': +1,
                  'hakedis': +1, 'hakedis_azaltma': -1}
HAREKET_ETIKET = {'alim': 'Mal Girişi', 'odeme': 'Ödeme', 'satis': 'Satış', 'tahsilat': 'Tahsilat',
                 'hakedis': 'Hak ediş', 'hakedis_azaltma': 'Hak ediş düzeltmesi'}


# ============================== #
#   CARİ TANIM                   #
# ============================== #
def cari_getir(cari_id, kilitle: bool = False) -> FinansCari:
    q = FinansCari.query.filter_by(id=int(cari_id or 0))
    if kilitle:
        q = q.populate_existing().with_for_update()
    c = q.first()
    if not c:
        raise FinansHata('Cari hesap bulunamadı.')
    return c


def cariler(sadece_aktif: bool = True) -> list:
    q = FinansCari.query
    if sadece_aktif:
        q = q.filter_by(aktif=True)
    return q.order_by(FinansCari.aktif.desc(), FinansCari.ad).all()


def cari_ekle(ad: str, tur: str, telefon: str, notlar: str, kullanici_id: int) -> FinansCari:
    ad = fs._ad_temizle(ad, 150)
    if tur not in CARI_TURLERI:
        raise FinansHata('Geçersiz cari türü.')
    try:
        if any(fs._ad_esit(c.ad, ad) for c in FinansCari.query.all()):
            raise FinansHata(f'"{ad}" adında cari hesap zaten var.')
        c = FinansCari(ad=ad, tur=tur, telefon=(telefon or '').strip()[:50] or None,
                       notlar=(notlar or '').strip() or None, olusturan_kullanici_id=kullanici_id)
        db.session.add(c)
        db.session.commit()
        return c
    except IntegrityError:
        db.session.rollback()
        raise FinansHata(f'"{ad}" adında cari hesap zaten var.')
    except Exception:
        db.session.rollback()
        raise


def cari_guncelle(cari_id, ad: str, tur: str, telefon: str, notlar: str) -> FinansCari:
    c = cari_getir(cari_id, kilitle=True)
    ad = fs._ad_temizle(ad, 150)
    if tur not in CARI_TURLERI:
        raise FinansHata('Geçersiz cari türü.')
    if c.tur == 'calisan' and tur != 'calisan':
        raise FinansHata('Çalışan hesabının türü değiştirilemez.')
    if c.tur != 'calisan' and tur == 'calisan' and c.hareketler.first():
        raise FinansHata('Hareketi olan cari çalışan hesabına çevrilemez; ayrı bir çalışan hesabı açın.')
    try:
        if any(fs._ad_esit(x.ad, ad) for x in FinansCari.query.filter(FinansCari.id != c.id).all()):
            raise FinansHata(f'"{ad}" adında başka bir cari hesap var.')
        c.ad, c.tur = ad, tur
        c.telefon = (telefon or '').strip()[:50] or None
        c.notlar = (notlar or '').strip() or None
        db.session.commit()
        return c
    except IntegrityError:
        db.session.rollback()
        raise FinansHata(f'"{ad}" adında başka bir cari hesap var.')
    except Exception:
        db.session.rollback()
        raise


def cari_pasif(cari_id, aktif: bool = False) -> FinansCari:
    try:
        c = cari_getir(cari_id, kilitle=True)
        if not aktif and c.tur == 'calisan':
            from models import FinansAnaGiderKalem
            if FinansAnaGiderKalem.query.filter_by(calisan_cari_id=c.id, aktif=True).first():
                raise FinansHata('Önce çalışanın düzenli ödeme planını pasife alın.')
            from finans_calisan_service import hakedis_satirlari
            if any(d['bekleyen'] for d in hakedis_satirlari(cari_id=c.id)):
                raise FinansHata('Bekleyen hak edişi olan çalışan hesabı kapatılamaz.')
        if not aktif and Decimal(str(c.bakiye or 0)) != 0:
            raise FinansHata(f'Bakiyesi sıfır olmayan hesap kapatılamaz ({c.bakiye:.2f} ₺).')
        c.aktif = aktif
        db.session.commit()
        return c
    except Exception:
        db.session.rollback()
        raise


# ============================== #
#   HAREKET                      #
# ============================== #
def parse_kalemler(adlar, adetler, fiyatlar) -> list[dict]:
    """Form dizilerinden kalem listesi; boş satırlar atlanır. Toplam = Σ adet×birim."""
    kalemler = []
    for ad, adet, fiyat in zip(adlar or [], adetler or [], fiyatlar or []):
        ad = ' '.join(str(ad or '').split())[:200]
        if not ad:
            continue
        adet_d = fs.parse_tutar(adet) if str(adet or '').strip() else Decimal('1.00')
        fiyat_d = fs.parse_tutar(fiyat)
        kalemler.append({'ad': ad, 'adet': adet_d, 'birim_fiyat': fiyat_d,
                         'tutar': (adet_d * fiyat_d).quantize(IKI_HANE)})
    return kalemler


def _cari_hareket(cari: FinansCari, tur: str, tutar: Decimal, tarih: datetime, aciklama: str,
                  kullanici_id: int, islem_id=None, kalemler=None,
                  hakedis_id=None, odeme_anahtari=None) -> FinansCariHareket:
    """Cari bakiye değişimi (tek yer). Cari FOR UPDATE ile gelmiş olmalı. COMMIT ETMEZ."""
    yon = HAREKET_TURLERI[tur]
    onceki = Decimal(str(cari.bakiye or 0))
    yeni = onceki + yon * tutar
    cari.bakiye = yeni
    cari.guncelleme_tarihi = datetime.utcnow()
    h = FinansCariHareket(cari_id=cari.id, tur=tur, yon=yon, tutar=tutar, onceki_bakiye=onceki,
                          yeni_bakiye=yeni, tarih=tarih, aciklama=(aciklama or '').strip()[:500] or None,
                          islem_id=islem_id, kullanici_id=kullanici_id,
                          hakedis_id=hakedis_id, odeme_anahtari=odeme_anahtari)
    for k in kalemler or []:
        h.kalemler.append(FinansCariKalem(**k))
    db.session.add(h)
    db.session.flush()
    return h


def mal_girisi(cari_id, kalemler: list[dict], tarih: datetime, aciklama: str, kullanici_id: int,
               tur: str = 'alim') -> FinansCariHareket:
    """alim (borç ↑) veya satis (alacak ↑) — kalem dökümlü, kasaya dokunmaz."""
    if tur not in ('alim', 'satis'):
        raise FinansHata('Geçersiz hareket türü.')
    if not kalemler:
        raise FinansHata('En az bir kalem girin.')
    toplam = sum((k['tutar'] for k in kalemler), Decimal('0.00'))
    if toplam <= 0:
        raise FinansHata('Toplam tutar sıfırdan büyük olmalı.')
    try:
        cari = cari_getir(cari_id, kilitle=True)
        if cari.tur == 'calisan':
            raise FinansHata('Çalışan hak edişini düzenli ödeme planından girin.')
        if not cari.aktif:
            raise FinansHata('Kapalı cari hesaba hareket girilemez.')
        h = _cari_hareket(cari, tur, toplam, tarih, aciklama or (', '.join(k['ad'] for k in kalemler)[:500]),
                          kullanici_id, kalemler=kalemler)
        db.session.commit()
        return h
    except Exception:
        db.session.rollback()
        raise


def odeme_yap(cari_id, hesap_kodu: str, tutar: Decimal, tarih: datetime, aciklama: str,
              kullanici_id: int) -> FinansCariHareket:
    """Ona ödedik: Elde/Banka'dan cari_odeme gideri + cari borç ↓ (tek transaction)."""
    try:
        fs._gider_hesabi_kontrol(hesap_kodu)
        # Kilit sırası her yerde hesap → cari (islem_iptal ile aynı) — deadlock önleme
        hesap = fs.hesap_getir(hesap_kodu, kilitle=True)
        cari = cari_getir(cari_id, kilitle=True)
        if cari.tur == 'calisan':
            raise FinansHata('Çalışana ödeme yapmak için hesabındaki ilgili haftayı seçin.')
        if not cari.aktif:
            raise FinansHata('Kapalı cari hesaba hareket girilemez.')
        aciklama = (aciklama or '').strip() or f'{cari.ad} — ödeme'
        islem = fs._hareket(hesap, 'cari_odeme', -1, tutar, tarih, kullanici_id, aciklama=aciklama)
        h = _cari_hareket(cari, 'odeme', tutar, tarih, aciklama, kullanici_id, islem_id=islem.id)
        db.session.commit()
        return h
    except Exception:
        db.session.rollback()
        raise


def tahsilat_al(cari_id, tutar: Decimal, tarih: datetime, aciklama: str,
                kullanici_id: int) -> FinansCariHareket:
    """O bize ödedi: Beyazıt'a cari_tahsilat geliri + cari alacak ↓ (tek transaction)."""
    try:
        # Kilit sırası hesap → cari (islem_iptal ile aynı) — deadlock önleme
        hesap = fs.hesap_getir(fs.GELIR_HESABI, kilitle=True)
        cari = cari_getir(cari_id, kilitle=True)
        if cari.tur == 'calisan':
            raise FinansHata('Çalışan ödemesini düzeltmek için ilgili ödemeyi iptal edin.')
        if not cari.aktif:
            raise FinansHata('Kapalı cari hesaba hareket girilemez.')
        aciklama = (aciklama or '').strip() or f'{cari.ad} — tahsilat'
        islem = fs._hareket(hesap, 'cari_tahsilat', +1, tutar, tarih, kullanici_id, aciklama=aciklama)
        h = _cari_hareket(cari, 'tahsilat', tutar, tarih, aciklama, kullanici_id, islem_id=islem.id)
        db.session.commit()
        return h
    except Exception:
        db.session.rollback()
        raise


def hareket_iptal(hareket_id, kullanici_id: int, neden: str = None) -> FinansCariHareket:
    """Kasa bağı varsa finans_service.islem_iptal iki tarafı birlikte geri alır; yoksa yalnız cari."""
    try:
        h = FinansCariHareket.query.get(int(hareket_id))
        if not h:
            raise FinansHata('Hareket bulunamadı.')
        if h.iptal:
            raise FinansHata('Bu hareket zaten iptal edilmiş.')
        if h.hakedis_id and not h.islem_id:
            raise FinansHata('Hak edişi iptal etmek yerine ilgili haftanın hak ediş tutarını düzenleyin.')
        if h.islem_id:
            fs.islem_iptal(h.islem_id, kullanici_id, neden=neden, commit=False)
        else:
            fs.cari_hareket_geri_al(h, kullanici_id, datetime.utcnow())
        db.session.commit()
        return h
    except Exception:
        db.session.rollback()
        raise


# ============================== #
#   SORGULAR                     #
# ============================== #
def hareketler(cari_id, iptal_goster: bool = False, sayfa: int = 1, adet: int = 100):
    q = FinansCariHareket.query.filter_by(cari_id=int(cari_id))
    if not iptal_goster:
        q = q.filter_by(iptal=False)
    q = q.order_by(FinansCariHareket.tarih.desc(), FinansCariHareket.id.desc())
    return q.paginate(page=max(1, sayfa), per_page=adet, error_out=False)


def cari_ozet() -> dict:
    """Aktif hesaplar: toplam borcumuz ve toplam alacağımız."""
    borc = alacak = Decimal('0.00')
    for c in FinansCari.query.filter_by(aktif=True).all():
        b = Decimal(str(c.bakiye or 0))
        if b > 0:
            borc += b
        elif b < 0:
            alacak += -b
    return {'borc': borc, 'alacak': alacak}


def cari_tutarlilik_kontrol() -> list:
    """Her cari: bakiye ↔ SUM(yon*tutar) iptal hariç; fark≠0 olanlar."""
    from sqlalchemy import func
    sonuc = []
    for c in FinansCari.query.all():
        toplam = (db.session.query(func.coalesce(func.sum(FinansCariHareket.yon * FinansCariHareket.tutar), 0))
                  .filter(FinansCariHareket.cari_id == c.id, FinansCariHareket.iptal.is_(False)).scalar())
        toplam = Decimal(str(toplam or 0)).quantize(IKI_HANE)
        bakiye = Decimal(str(c.bakiye or 0)).quantize(IKI_HANE)
        if toplam != bakiye:
            sonuc.append({'cari': c, 'bakiye': bakiye, 'defter': toplam, 'fark': bakiye - toplam})
    return sonuc
