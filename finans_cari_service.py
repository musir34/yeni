# finans_cari_service.py
"""
📒 Finans — Cari hesap (tedarikçi / müşteri defteri) iş kuralları.

bakiye = "bizim borcumuz": pozitif → biz ona borçluyuz, negatif → o bize borçlu (alacak).

Hareketler (yon: +1 borcumuz artar, -1 azalır):
- alim     (+1) mal girişi, kalem dökümlü; kasaya dokunmaz
- odeme    (-1) ona ödedik → Elde/Banka'dan `cari_odeme` gider kaydı (finans_service._hareket)
- satis    (-1) ona mal verdik (alacak), kalem dökümlü; kasaya dokunmaz
- tahsilat (+1) o bize ödedi → Beyazıt'a `cari_tahsilat` gelir kaydı
- borc_alma  (-1) yalnız şahsi hesapta: kasadan kendimize aldığımız borç; kasa tarafı ödeme gibi
- borc_odeme (+1) yalnız şahsi hesapta: bu borcun kasaya geri ödenmesi; kasa tarafı tahsilat gibi

Kasa bağı olan hareketler tek transaction'da yazılır ve finans_cari_hareket.islem_id ile
bağlanır; iptal iki tarafı birlikte geri alır (finans_service.islem_iptal bağı tanır).

Para birimi: cari açılışta TRY ya da USD seçilir, hareket girildikten sonra değişmez. USD caride
bakiye/hareket/kalem tutarları dolardır; kasa bağlı ödeme/tahsilatta kur girilir, kasaya
tutar×kur TL yazılır ve kur harekette saklanır (iptal iki tarafı kendi biriminde geri alır).
Çalışan carileri her zaman TRY'dir.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from models import db, FinansCari, FinansCariHareket, FinansCariKalem, FinansIslem
import finans_service as fs
from finans_service import FinansHata, IKI_HANE

CARI_TURLERI = ('tedarikci', 'musteri', 'diger', 'calisan', 'sahsi')
CARI_TUR_ETIKET = {'tedarikci': 'Tedarikçi', 'musteri': 'Müşteri', 'diger': 'Diğer', 'calisan': 'Çalışan',
                  'sahsi': 'Şahsi (kasadan borç)'}
HAREKET_TURLERI = {'alim': +1, 'odeme': -1, 'satis': -1, 'tahsilat': +1,
                  'hakedis': +1, 'hakedis_azaltma': -1, 'borc_alma': -1, 'borc_odeme': +1}
HAREKET_ETIKET = {'alim': 'Mal Girişi', 'odeme': 'Ödeme', 'satis': 'Satış', 'tahsilat': 'Tahsilat',
                 'hakedis': 'Hak ediş', 'hakedis_azaltma': 'Hak ediş düzeltmesi',
                 'borc_alma': 'Kasadan borç aldım', 'borc_odeme': 'Borç geri ödemesi'}
PARA_BIRIMLERI = ('TRY', 'USD')
PARA_SEMBOL = {'TRY': '₺', 'USD': '$'}
PARA_ETIKET = {'TRY': 'Türk Lirası (₺)', 'USD': 'Dolar ($)'}
DORT_HANE = Decimal('0.0001')


def sembol(cari: FinansCari) -> str:
    return PARA_SEMBOL.get(cari.para_birimi or 'TRY', '₺')


def parse_kur(raw) -> Decimal:
    """'34,5678' / '34.5' / '1.250' → Decimal(4 hane); boş/≤0/bozuk → FinansHata."""
    s = str(raw if raw is not None else '').strip()
    if not s:
        raise FinansHata('Dolar kuru boş olamaz.')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif '.' in s:
        # parse_tutar ile aynı kural: virgülsüz "1.250" binlik yazımıdır (alanlar binlik nokta koyar).
        parcalar = s.split('.')
        if all(len(x) == 3 and x.isdigit() for x in parcalar[1:]) and parcalar[0].isdigit():
            s = ''.join(parcalar)
    try:
        kur = Decimal(s).quantize(DORT_HANE)
    except Exception:
        raise FinansHata('Dolar kuru geçersiz.')
    if kur <= 0:
        raise FinansHata('Dolar kuru sıfırdan büyük olmalı.')
    return kur


def _sahsi_kontrol(cari: FinansCari, tur: str) -> None:
    """Şahsi hesapta yalnız borç alma/geri ödeme; diğer hesaplarda bu ikisi kullanılamaz."""
    sahsi_hareket = tur in ('borc_alma', 'borc_odeme')
    if cari.tur == 'sahsi' and not sahsi_hareket:
        raise FinansHata('Şahsi hesapta yalnız kasadan borç alma ve geri ödeme kaydedilir.')
    if cari.tur != 'sahsi' and sahsi_hareket:
        raise FinansHata('Kasadan borç alma yalnız şahsi hesapta kullanılır.')


def _para_birimi_kontrol(tur: str, para_birimi: str) -> str:
    para_birimi = (para_birimi or 'TRY').strip().upper()
    if para_birimi not in PARA_BIRIMLERI:
        raise FinansHata('Geçersiz para birimi.')
    if tur == 'calisan' and para_birimi != 'TRY':
        raise FinansHata('Çalışan hesabı yalnız TL ile açılabilir.')
    return para_birimi


def _kasa_tutari(cari: FinansCari, tutar: Decimal, kur):
    """Cari birimindeki tutarın kasaya yazılacak TL karşılığı ve saklanacak kur."""
    if (cari.para_birimi or 'TRY') != 'USD':
        return tutar, None
    if kur is None:
        raise FinansHata('Dolar hesabı için o günkü kuru girin (1 $ = ? ₺).')
    return (tutar * kur).quantize(IKI_HANE), kur


def _kasa_aciklama(aciklama: str, tutar: Decimal, kur) -> str:
    """Kasa defterinde dolar ödemesinin kaynağı görünsün: 'açıklama (120,00 $ × 34,5000)'."""
    if kur is None:
        return aciklama
    ek = f' ({tutar:.2f} $ × {kur:.4f})'
    return (aciklama[:500 - len(ek)] + ek)


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


def cari_ekle(ad: str, tur: str, telefon: str, notlar: str, kullanici_id: int,
              para_birimi: str = 'TRY') -> FinansCari:
    ad = fs._ad_temizle(ad, 150)
    if tur not in CARI_TURLERI:
        raise FinansHata('Geçersiz cari türü.')
    para_birimi = _para_birimi_kontrol(tur, para_birimi)
    try:
        if any(fs._ad_esit(c.ad, ad) for c in FinansCari.query.all()):
            raise FinansHata(f'"{ad}" adında cari hesap zaten var.')
        c = FinansCari(ad=ad, tur=tur, telefon=(telefon or '').strip()[:50] or None,
                       notlar=(notlar or '').strip() or None, para_birimi=para_birimi,
                       olusturan_kullanici_id=kullanici_id)
        db.session.add(c)
        db.session.commit()
        return c
    except IntegrityError:
        db.session.rollback()
        raise FinansHata(f'"{ad}" adında cari hesap zaten var.')
    except Exception:
        db.session.rollback()
        raise


def cari_guncelle(cari_id, ad: str, tur: str, telefon: str, notlar: str,
                  para_birimi: str = None) -> FinansCari:
    c = cari_getir(cari_id, kilitle=True)
    ad = fs._ad_temizle(ad, 150)
    if tur not in CARI_TURLERI:
        raise FinansHata('Geçersiz cari türü.')
    if c.tur == 'calisan' and tur != 'calisan':
        raise FinansHata('Çalışan hesabının türü değiştirilemez.')
    if c.tur != 'calisan' and tur == 'calisan' and c.hareketler.first():
        raise FinansHata('Hareketi olan cari çalışan hesabına çevrilemez; ayrı bir çalışan hesabı açın.')
    if (c.tur == 'sahsi') != (tur == 'sahsi') and c.hareketler.first():
        raise FinansHata('Hareketi olan hesap şahsi hesaba çevrilemez (ya da tersi); ayrı bir hesap açın.')
    para_birimi = _para_birimi_kontrol(tur, para_birimi or c.para_birimi)
    if para_birimi != (c.para_birimi or 'TRY') and c.hareketler.first():
        raise FinansHata('Hareketi olan hesabın para birimi değiştirilemez; yeni bir hesap açın.')
    try:
        if any(fs._ad_esit(x.ad, ad) for x in FinansCari.query.filter(FinansCari.id != c.id).all()):
            raise FinansHata(f'"{ad}" adında başka bir cari hesap var.')
        c.ad, c.tur, c.para_birimi = ad, tur, para_birimi
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
            raise FinansHata(f'Bakiyesi sıfır olmayan hesap kapatılamaz ({c.bakiye:.2f} {sembol(c)}).')
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
                  hakedis_id=None, odeme_anahtari=None, kur=None) -> FinansCariHareket:
    """Cari bakiye değişimi (tek yer). Cari FOR UPDATE ile gelmiş olmalı. COMMIT ETMEZ."""
    yon = HAREKET_TURLERI[tur]
    onceki = Decimal(str(cari.bakiye or 0))
    yeni = onceki + yon * tutar
    cari.bakiye = yeni
    cari.guncelleme_tarihi = datetime.utcnow()
    h = FinansCariHareket(cari_id=cari.id, tur=tur, yon=yon, tutar=tutar, onceki_bakiye=onceki,
                          yeni_bakiye=yeni, tarih=tarih, aciklama=(aciklama or '').strip()[:500] or None,
                          islem_id=islem_id, kullanici_id=kullanici_id,
                          hakedis_id=hakedis_id, odeme_anahtari=odeme_anahtari, kur=kur)
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
        if cari.tur == 'sahsi':
            raise FinansHata('Şahsi hesapta yalnız kasadan borç alma ve geri ödeme kaydedilir.')
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
              kullanici_id: int, kur: Decimal = None, tur: str = 'odeme') -> FinansCariHareket:
    """Ona ödedik: Elde/Banka'dan cari_odeme gideri + cari borç ↓ (tek transaction).
    USD caride tutar dolardır; kasadan tutar×kur TL düşer.
    tur='borc_alma': şahsi hesapta kasadan kendimize aldığımız borç (kasa tarafı aynı)."""
    try:
        fs._gider_hesabi_kontrol(hesap_kodu)
        # Kilit sırası her yerde hesap → cari (islem_iptal ile aynı) — deadlock önleme
        hesap = fs.hesap_getir(hesap_kodu, kilitle=True)
        cari = cari_getir(cari_id, kilitle=True)
        if cari.tur == 'calisan':
            raise FinansHata('Çalışana ödeme yapmak için hesabındaki ilgili haftayı seçin.')
        _sahsi_kontrol(cari, tur)
        if not cari.aktif:
            raise FinansHata('Kapalı cari hesaba hareket girilemez.')
        aciklama = (aciklama or '').strip() or (f'{cari.ad} — kasadan borç' if tur == 'borc_alma'
                                                else f'{cari.ad} — ödeme')
        kasa_tutar, kur = _kasa_tutari(cari, tutar, kur)
        islem = fs._hareket(hesap, 'cari_odeme', -1, kasa_tutar, tarih, kullanici_id,
                            aciklama=_kasa_aciklama(aciklama, tutar, kur))
        h = _cari_hareket(cari, tur, tutar, tarih, aciklama, kullanici_id, islem_id=islem.id, kur=kur)
        db.session.commit()
        return h
    except Exception:
        db.session.rollback()
        raise


def tahsilat_al(cari_id, tutar: Decimal, tarih: datetime, aciklama: str,
                kullanici_id: int, kur: Decimal = None, tur: str = 'tahsilat') -> FinansCariHareket:
    """O bize ödedi: Beyazıt'a cari_tahsilat geliri + cari alacak ↓ (tek transaction).
    USD caride tutar dolardır; Beyazıt'a tutar×kur TL girer.
    tur='borc_odeme': şahsi hesapta kasadan alınan borcun geri ödenmesi (kasa tarafı aynı)."""
    try:
        # Kilit sırası hesap → cari (islem_iptal ile aynı) — deadlock önleme
        hesap = fs.hesap_getir(fs.GELIR_HESABI, kilitle=True)
        cari = cari_getir(cari_id, kilitle=True)
        if cari.tur == 'calisan':
            raise FinansHata('Çalışan ödemesini düzeltmek için ilgili ödemeyi iptal edin.')
        _sahsi_kontrol(cari, tur)
        if not cari.aktif:
            raise FinansHata('Kapalı cari hesaba hareket girilemez.')
        aciklama = (aciklama or '').strip() or (f'{cari.ad} — borç geri ödemesi' if tur == 'borc_odeme'
                                                else f'{cari.ad} — tahsilat')
        kasa_tutar, kur = _kasa_tutari(cari, tutar, kur)
        islem = fs._hareket(hesap, 'cari_tahsilat', +1, kasa_tutar, tarih, kullanici_id,
                            aciklama=_kasa_aciklama(aciklama, tutar, kur))
        h = _cari_hareket(cari, tur, tutar, tarih, aciklama, kullanici_id, islem_id=islem.id, kur=kur)
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
    """Aktif hesaplar: toplam borcumuz ve toplam alacağımız; TL ve USD ayrı toplanır.
    Şahsi hesapların (kasadan alınan borç) TL bakiyesi ayrı toplanır, alacağa karışmaz."""
    borc = alacak = borc_usd = alacak_usd = sahsi = Decimal('0.00')
    for c in FinansCari.query.filter_by(aktif=True).all():
        b = Decimal(str(c.bakiye or 0))
        usd = (c.para_birimi or 'TRY') == 'USD'
        if c.tur == 'sahsi' and b < 0 and not usd:
            sahsi += -b
            continue
        if b > 0:
            if usd:
                borc_usd += b
            else:
                borc += b
        elif b < 0:
            if usd:
                alacak_usd += -b
            else:
                alacak += -b
    return {'borc': borc, 'alacak': alacak, 'borc_usd': borc_usd, 'alacak_usd': alacak_usd,
            'sahsi': sahsi}


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
