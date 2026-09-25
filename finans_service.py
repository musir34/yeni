# finans_service.py
"""
💰 Finans Kasası — iş kuralları ve bakiye hareketleri.

Mevcut kasa modülünden (kasa.py / AnaKasa) bağımsızdır; kasa.py import EDİLMEZ.

Kurallar
--------
- Üç hesap: beyazit (Ana Bakiye), elde (Kullanılabilir), banka (Banka Hesabı).
- Gelir → yalnızca beyazit'a girer.
- Gider (küçük / ana) → yalnızca elde veya banka'dan çıkar; beyazit'tan doğrudan gider YASAK.
- Transfer: hesaplar arası serbest (beyazit→elde, beyazit→banka, elde↔banka).
- Bakiyenin tek gerçek kaynağı finans_hesap.bakiye; her hareket hesap satırını
  FOR UPDATE kilitleyip snapshot (onceki/yeni) yazar. Silme yok: iptal + ters delta.
- Negatif bakiye hiçbir yolla oluşmaz (hareket ve iptal ikisinde de kontrol).
- Tarihler DB'de naive UTC; form girdisi İstanbul kabul edilip ist_to_utc ile çevrilir.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from models import (db, FinansHesap, FinansKategori, FinansGiderAdi,
                    FinansAnaGiderKalem, FinansIslem, FinansCari, FinansCariHareket)
from time_utils import ist_to_utc, to_ist

logger = logging.getLogger(__name__)

HESAP_KODLARI = ('beyazit', 'elde', 'banka')
GELIR_HESABI = 'beyazit'
GIDER_HESAPLARI = ('elde', 'banka')
KATEGORI_TURLERI = ('gelir', 'kucuk_gider', 'ana_gider')
ISLEM_TURLERI = ('gelir', 'kucuk_gider', 'ana_gider', 'transfer_cikis', 'transfer_giris',
                 'cari_odeme', 'cari_tahsilat')
KATEGORI_TUR_ETIKET = {'gelir': 'Gelir', 'kucuk_gider': 'Günlük Harcamalar', 'ana_gider': 'Düzenli Ödemeler'}
ISLEM_TUR_ETIKET = {
    'gelir': 'Gelir', 'kucuk_gider': 'Günlük Harcamalar', 'ana_gider': 'Düzenli Ödemeler',
    'transfer_cikis': 'Transfer (Çıkış)', 'transfer_giris': 'Transfer (Giriş)',
    'cari_odeme': 'Cari Ödeme', 'cari_tahsilat': 'Cari Tahsilat',
}
IKI_HANE = Decimal('0.01')


class FinansHata(ValueError):
    """Kullanıcıya flash/JSON ile gösterilecek iş kuralı hatası."""


# ============================== #
#   PARSE YARDIMCILARI           #
# ============================== #
def parse_tutar(raw) -> Decimal:
    """'1.250,50' / '1250.50' / 1250 → Decimal('1250.50'); <=0 veya bozuk → FinansHata."""
    s = str(raw if raw is not None else '').strip()
    if not s:
        raise FinansHata('Tutar boş olamaz.')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif '.' in s:
        # Virgülsüz Türkçe binlik yazımı ("1.500", "12.345.678") → noktalar binlik ayırıcı.
        # Tek nokta + 3 haneli olmayan kuyruk ("1.50", "1250.5") ondalık kabul edilir.
        parcalar = s.split('.')
        if len(parcalar) > 1 and all(len(x) == 3 and x.isdigit() for x in parcalar[1:]) and parcalar[0].isdigit():
            s = ''.join(parcalar)
    try:
        tutar = Decimal(s).quantize(IKI_HANE)
    except (InvalidOperation, ValueError):
        raise FinansHata('Tutar geçersiz.')
    if tutar <= 0:
        raise FinansHata('Tutar sıfırdan büyük olmalı.')
    return tutar


def parse_tarih(raw) -> datetime:
    """'YYYY-MM-DD' veya 'YYYY-MM-DDTHH:MM' (İstanbul) → naive UTC; boş → şimdi (UTC)."""
    s = str(raw or '').strip()
    if not s:
        return datetime.utcnow()
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(s, fmt)
            break
        except ValueError:
            continue
    else:
        raise FinansHata('Tarih geçersiz.')
    if fmt == '%Y-%m-%d':
        # Gün seçildiyse İstanbul'da o günün saatini şimdi'den al (sıralama doğal kalsın)
        simdi = to_ist(datetime.utcnow())
        dt = dt.replace(hour=simdi.hour, minute=simdi.minute, second=simdi.second)
    return ist_to_utc(dt)


def bugun_donem() -> str:
    return to_ist(datetime.utcnow()).strftime('%Y-%m')


def parse_donem(raw) -> str:
    """'YYYY-MM' doğrula; boş → İstanbul'daki bugünün ayı."""
    s = str(raw or '').strip()
    if not s:
        return bugun_donem()
    try:
        datetime.strptime(s, '%Y-%m')
    except ValueError:
        raise FinansHata('Dönem geçersiz (YYYY-AA bekleniyor).')
    return s


def donem_utc_araligi(donem: str):
    """İstanbul ay sınırları → naive UTC (bas dahil, son hariç)."""
    yil, ay = int(donem[:4]), int(donem[5:7])
    bas = datetime(yil, ay, 1)
    son = datetime(yil + 1, 1, 1) if ay == 12 else datetime(yil, ay + 1, 1)
    return ist_to_utc(bas), ist_to_utc(son)


def donem_kaydir(donem: str, adim: int) -> str:
    yil, ay = int(donem[:4]), int(donem[5:7])
    idx = yil * 12 + (ay - 1) + adim
    return f'{idx // 12:04d}-{idx % 12 + 1:02d}'


def donem_etiket(donem: str) -> str:
    if len(donem) == 10:
        return f'{date.fromisoformat(donem):%d.%m.%Y} haftası'
    aylar = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
             'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
    return f'{aylar[int(donem[5:7]) - 1]} {donem[:4]}'


def parse_odeme_donemi(raw) -> str:
    s = str(raw or '').strip()
    try:
        if len(s) == 10 and date.fromisoformat(s).isoformat() == s:
            return s
        if len(s) == 7 and datetime.strptime(s, '%Y-%m').strftime('%Y-%m') == s:
            return s
    except ValueError:
        pass
    raise FinansHata('Ödeme dönemi geçersiz.')


def kalem_odeme_donemleri(kalem, donem: str) -> list[str]:
    """Ayın ödeme tarihleri; haftalar ay/yıl sınırında kesilmeden yedi gün ilerler."""
    if donem < kalem.baslangic_donem or (kalem.bitis_donem and donem > kalem.bitis_donem):
        return []
    if kalem.siklik != 'haftalik':
        return [donem]
    ilk = kalem.ilk_odeme_tarihi
    # Aylıktan haftalığa geçişten önceki aylık dönemleri koru.
    if donem < ilk.strftime('%Y-%m'):
        return [donem]
    bas = date.fromisoformat(donem + '-01')
    son = date.fromisoformat(donem_kaydir(donem, 1) + '-01')
    gun = ilk + timedelta(days=max(0, ((bas - ilk).days + 6) // 7) * 7)
    sonuc = []
    while gun < son:
        sonuc.append(gun.isoformat())
        gun += timedelta(days=7)
    return sonuc


# ============================== #
#   HESAP                        #
# ============================== #
def hesap_getir(kod: str, kilitle: bool = False) -> FinansHesap:
    if kod not in HESAP_KODLARI:
        raise FinansHata('Geçersiz hesap.')
    q = FinansHesap.query.filter_by(kod=kod)
    if kilitle:
        q = q.populate_existing().with_for_update()
    hesap = q.first()
    if not hesap:
        raise FinansHata(f'"{kod}" hesabı bulunamadı — scripts/create_finans_tables.py çalıştırılmalı.')
    return hesap


def hesaplar() -> list:
    return FinansHesap.query.order_by(FinansHesap.sira, FinansHesap.id).all()


def _gider_hesabi_kontrol(hesap_kodu: str) -> None:
    if hesap_kodu not in GIDER_HESAPLARI:
        raise FinansHata('Beyazıt (Ana Bakiye) hesabından doğrudan gider çıkılamaz; '
                         'önce Elde veya Banka hesabına transfer yapın.')


# ============================== #
#   HAREKET ÇEKİRDEĞİ            #
# ============================== #
def _hareket(hesap: FinansHesap, tur: str, yon: int, tutar: Decimal, tarih: datetime,
             kullanici_id: int, **alanlar) -> FinansIslem:
    """Tek yerden bakiye değişimi. Hesap FOR UPDATE ile gelmiş olmalı. COMMIT ETMEZ."""
    onceki = Decimal(str(hesap.bakiye or 0))
    yeni = onceki + yon * tutar
    if yeni < 0:
        raise FinansHata(f'Yetersiz bakiye: {hesap.ad} hesabında {onceki:.2f} ₺ var, {tutar:.2f} ₺ çıkılamaz.')
    hesap.bakiye = yeni
    hesap.guncelleme_tarihi = datetime.utcnow()
    islem = FinansIslem(
        hesap_id=hesap.id, tur=tur, yon=yon, tutar=tutar,
        onceki_bakiye=onceki, yeni_bakiye=yeni, tarih=tarih,
        kullanici_id=kullanici_id, **alanlar,
    )
    db.session.add(islem)
    db.session.flush()
    return islem


def _kategori_getir(kategori_id, tur: str, zorunlu: bool = True):
    if not kategori_id:
        if zorunlu:
            raise FinansHata('Kategori seçilmeli.')
        return None
    kat = FinansKategori.query.get(int(kategori_id))
    if not kat or kat.tur != tur or not kat.aktif:
        raise FinansHata('Geçersiz kategori.')
    return kat


def gelir_ekle(kategori_id, tutar: Decimal, tarih: datetime, aciklama: str,
               kullanici_id: int, commit: bool = True) -> FinansIslem:
    try:
        kat = _kategori_getir(kategori_id, 'gelir')
        hesap = hesap_getir(GELIR_HESABI, kilitle=True)
        islem = _hareket(hesap, 'gelir', +1, tutar, tarih, kullanici_id,
                         kategori_id=kat.id, aciklama=(aciklama or '').strip() or kat.ad)
        if commit:
            db.session.commit()
        return islem
    except Exception:
        db.session.rollback()
        raise


def kucuk_gider_ekle(hesap_kodu: str, kategori_id, gider_adi_id, aciklama: str,
                     tutar: Decimal, tarih: datetime, kullanici_id: int,
                     commit: bool = True) -> FinansIslem:
    try:
        _gider_hesabi_kontrol(hesap_kodu)
        kat = _kategori_getir(kategori_id, 'kucuk_gider')
        gider_adi = None
        if gider_adi_id:
            gider_adi = FinansGiderAdi.query.get(int(gider_adi_id))
            if not gider_adi or gider_adi.kategori_id != kat.id:
                raise FinansHata('Gider adı seçilen kategoriye ait değil.')
        aciklama = (aciklama or '').strip() or (gider_adi.ad if gider_adi else kat.ad)
        hesap = hesap_getir(hesap_kodu, kilitle=True)
        islem = _hareket(hesap, 'kucuk_gider', -1, tutar, tarih, kullanici_id,
                         kategori_id=kat.id, gider_adi_id=gider_adi.id if gider_adi else None,
                         aciklama=aciklama)
        if commit:
            db.session.commit()
        return islem
    except Exception:
        db.session.rollback()
        raise


def ana_gider_ode(kalem_id, donem: str, hesap_kodu: str, tutar: Decimal, tarih: datetime,
                  aciklama: str, kullanici_id: int, commit: bool = True) -> FinansIslem:
    try:
        _gider_hesabi_kontrol(hesap_kodu)
        donem = parse_odeme_donemi(donem)
        tutar = parse_tutar(tutar)
        kalem = (FinansAnaGiderKalem.query.filter_by(id=int(kalem_id or 0))
                 .populate_existing().with_for_update().first())
        if not kalem or not kalem.aktif:
            raise FinansHata('Düzenli ödeme bulunamadı ya da pasif.')
        if kalem.calisan_cari_id:
            raise FinansHata('Çalışan için hak ediş ve ödeme formunu kullanın.')
        if donem not in kalem_odeme_donemleri(kalem, donem[:7]):
            raise FinansHata(f'"{kalem.ad}" kalemi {donem_etiket(donem)} dönemi için tanımlı değil.')
        mevcut = FinansIslem.query.filter_by(kalem_id=kalem.id, donem=donem,
                                             tur='ana_gider', iptal=False).first()
        if mevcut:
            raise FinansHata(f'"{kalem.ad}" {donem_etiket(donem)} için zaten ödenmiş.')
        hesap = hesap_getir(hesap_kodu, kilitle=True)
        islem = _hareket(hesap, 'ana_gider', -1, tutar, tarih, kullanici_id,
                         kalem_id=kalem.id, donem=donem, kategori_id=kalem.kategori_id,
                         aciklama=(aciklama or '').strip() or f'{kalem.ad} — {donem_etiket(donem)}')
        if commit:
            db.session.commit()
        return islem
    except IntegrityError:
        db.session.rollback()
        raise FinansHata('Bu kalem bu dönem için zaten ödenmiş.')
    except Exception:
        db.session.rollback()
        raise


def transfer_yap(kaynak_kodu: str, hedef_kodu: str, tutar: Decimal, tarih: datetime,
                 aciklama: str, kullanici_id: int, commit: bool = True):
    try:
        if kaynak_kodu == hedef_kodu:
            raise FinansHata('Kaynak ve hedef hesap aynı olamaz.')
        if kaynak_kodu not in HESAP_KODLARI or hedef_kodu not in HESAP_KODLARI:
            raise FinansHata('Geçersiz hesap.')
        # Deadlock önleme: hesapları id sırasına göre kilitle
        h1 = FinansHesap.query.filter_by(kod=kaynak_kodu).first()
        h2 = FinansHesap.query.filter_by(kod=hedef_kodu).first()
        if not h1 or not h2:
            raise FinansHata('Hesap bulunamadı.')
        for h in sorted((h1, h2), key=lambda x: x.id):
            db.session.query(FinansHesap).filter_by(id=h.id).with_for_update().one()
        db.session.refresh(h1)
        db.session.refresh(h2)
        grup = uuid.uuid4()
        aciklama = (aciklama or '').strip() or f'{h1.ad} → {h2.ad}'
        cikis = _hareket(h1, 'transfer_cikis', -1, tutar, tarih, kullanici_id,
                         transfer_grup=grup, aciklama=aciklama)
        giris = _hareket(h2, 'transfer_giris', +1, tutar, tarih, kullanici_id,
                         transfer_grup=grup, aciklama=aciklama)
        if commit:
            db.session.commit()
        return cikis, giris
    except Exception:
        db.session.rollback()
        raise


def cari_hareket_geri_al(h: FinansCariHareket, kullanici_id: int, simdi: datetime) -> None:
    """Cari hareketi iptal işaretle + cari bakiyeyi ters delta ile geri al. COMMIT ETMEZ.
    Hem islem_iptal (kasa bağlı) hem finans_cari_service.hareket_iptal (bağsız) buradan geçer."""
    h = db.session.query(FinansCariHareket).filter_by(id=h.id).with_for_update().one()
    db.session.refresh(h)
    if h.iptal:
        raise FinansHata('Bu cari hareket az önce başka bir istekle iptal edildi.')
    cari = db.session.query(FinansCari).filter_by(id=h.cari_id).with_for_update().one()
    db.session.refresh(cari)
    cari.bakiye = Decimal(str(cari.bakiye or 0)) - h.yon * Decimal(str(h.tutar))
    cari.guncelleme_tarihi = simdi
    h.iptal = True
    h.iptal_tarihi = simdi
    h.iptal_kullanici_id = kullanici_id


def islem_iptal(islem_id: int, kullanici_id: int, neden: str = None,
                commit: bool = True) -> list:
    """İşlemi (transferse iki bacağını) iptal eder; bakiyeyi ters delta ile geri alır."""
    try:
        islem = FinansIslem.query.get(int(islem_id))
        if not islem:
            raise FinansHata('İşlem bulunamadı.')
        if islem.iptal:
            raise FinansHata('Bu işlem zaten iptal edilmiş.')
        if islem.cari_hareket and islem.cari_hareket.hakedis_id:
            FinansAnaGiderKalem.query.filter_by(
                id=islem.cari_hareket.hakedis.kalem_id).with_for_update().one()
        if islem.transfer_grup:
            bacaklar = FinansIslem.query.filter_by(transfer_grup=islem.transfer_grup, iptal=False).all()
        else:
            bacaklar = [islem]
        simdi = datetime.utcnow()
        for b in sorted(bacaklar, key=lambda x: x.hesap_id):
            # İşlem satırını da kilitle ve iptal bayrağını kilit altında yeniden oku:
            # eşzamanlı çift iptal (çift tıklama / iki sekme) aynı deltayı iki kez geri almasın.
            b = db.session.query(FinansIslem).filter_by(id=b.id).with_for_update().one()
            db.session.refresh(b)
            if b.iptal:
                raise FinansHata('Bu işlem az önce başka bir istekle iptal edildi.')
            hesap = db.session.query(FinansHesap).filter_by(id=b.hesap_id).with_for_update().one()
            db.session.refresh(hesap)
            onceki = Decimal(str(hesap.bakiye or 0))
            yeni = onceki - b.yon * Decimal(str(b.tutar))
            if yeni < 0:
                raise FinansHata(f'İptal edilemez: {hesap.ad} bakiyesi {onceki:.2f} ₺, '
                                 f'{b.tutar:.2f} ₺ geri alınırsa eksiye düşer. '
                                 'Önce bu paraya bağlı giderleri/transferleri iptal edin.')
            hesap.bakiye = yeni
            hesap.guncelleme_tarihi = simdi
            b.iptal = True
            b.iptal_tarihi = simdi
            b.iptal_kullanici_id = kullanici_id
            b.iptal_neden = (neden or '').strip()[:255] or None
            # Cari bağlı işlem (cari_odeme / cari_tahsilat): cari hareketi de birlikte geri al
            if b.cari_hareket and not b.cari_hareket.iptal:
                cari_hareket_geri_al(b.cari_hareket, kullanici_id, simdi)
        if commit:
            db.session.commit()
        return bacaklar
    except Exception:
        db.session.rollback()
        raise


def islem_meta_guncelle(islem_id: int, aciklama=None, kategori_id=None, gider_adi_id=None) -> FinansIslem:
    """Bakiyeye dokunmayan alanları yerinde düzenler."""
    try:
        islem = FinansIslem.query.get(int(islem_id))
        if not islem:
            raise FinansHata('İşlem bulunamadı.')
        if islem.iptal:
            raise FinansHata('İptal edilmiş işlem düzenlenemez.')
        if aciklama is not None:
            islem.aciklama = aciklama.strip()[:500] or islem.aciklama
        if islem.tur in ('gelir', 'kucuk_gider') and kategori_id:
            kat = _kategori_getir(kategori_id, islem.tur)
            islem.kategori_id = kat.id
            if islem.tur == 'kucuk_gider':
                if gider_adi_id:
                    ga = FinansGiderAdi.query.get(int(gider_adi_id))
                    if not ga or ga.kategori_id != kat.id:
                        raise FinansHata('Gider adı seçilen kategoriye ait değil.')
                    islem.gider_adi_id = ga.id
                else:
                    islem.gider_adi_id = None
        db.session.commit()
        return islem
    except Exception:
        db.session.rollback()
        raise


def islem_duzelt(islem_id: int, kullanici_id: int, yeni_tutar: Decimal = None,
                 yeni_hesap_kodu: str = None, yeni_tarih: datetime = None) -> FinansIslem:
    """Tutar/hesap/tarih düzeltmesi = eskiyi iptal + aynı türde yeni kayıt; tek transaction."""
    try:
        eski = FinansIslem.query.get(int(islem_id))
        if not eski:
            raise FinansHata('İşlem bulunamadı.')
        if eski.iptal:
            raise FinansHata('İptal edilmiş işlem düzeltilemez.')
        if eski.tur in ('transfer_cikis', 'transfer_giris', 'cari_odeme', 'cari_tahsilat'):
            raise FinansHata('Bu işlemi düzeltmek için iptal edip yeniden oluşturun.')
        if eski.cari_hareket and eski.cari_hareket.hakedis_id:
            raise FinansHata('Çalışan ödemesini iptal edip ilgili haftaya yeniden ödeme ekleyin.')
        tutar = yeni_tutar or Decimal(str(eski.tutar))
        tarih = yeni_tarih or eski.tarih
        hesap_kodu = yeni_hesap_kodu or eski.hesap.kod
        if eski.tur == 'ana_gider':
            # Ödeme ile aynı kilit sırası: önce plan, sonra işlem/hesap.
            FinansAnaGiderKalem.query.filter_by(id=eski.kalem_id).with_for_update().one()
        islem_iptal(eski.id, kullanici_id, neden='düzeltme', commit=False)
        if eski.tur == 'gelir':
            yeni = gelir_ekle(eski.kategori_id, tutar, tarih, eski.aciklama, kullanici_id, commit=False)
        elif eski.tur == 'kucuk_gider':
            yeni = kucuk_gider_ekle(hesap_kodu, eski.kategori_id, eski.gider_adi_id, eski.aciklama,
                                    tutar, tarih, kullanici_id, commit=False)
        else:  # ana_gider
            yeni = ana_gider_ode(eski.kalem_id, eski.donem, hesap_kodu, tutar, tarih,
                                 eski.aciklama, kullanici_id, commit=False)
        db.session.commit()
        return yeni
    except Exception:
        db.session.rollback()
        raise


# ============================== #
#   TANIMLAR                     #
# ============================== #
def _ad_temizle(ad, maks: int) -> str:
    s = ' '.join(str(ad or '').split())[:maks]
    if not s:
        raise FinansHata('Ad boş olamaz.')
    return s


def _ad_esit(a: str, b: str) -> bool:
    """Büyük/küçük harf duyarsız ad karşılaştırması (Türkçe karakterler dahil, DB'den bağımsız)."""
    tr = str.maketrans('Iİ', 'ıi')
    return str(a or '').translate(tr).casefold() == str(b or '').translate(tr).casefold()


def kategori_ekle(tur: str, ad: str, kullanici_id: int) -> FinansKategori:
    if tur not in KATEGORI_TURLERI:
        raise FinansHata('Geçersiz kategori türü.')
    ad = _ad_temizle(ad, 100)
    try:
        mevcut = next((k for k in FinansKategori.query.filter_by(tur=tur).all() if _ad_esit(k.ad, ad)), None)
        if mevcut:
            if mevcut.aktif:
                raise FinansHata(f'"{ad}" zaten var.')
            mevcut.aktif = True
            db.session.commit()
            return mevcut
        kat = FinansKategori(tur=tur, ad=ad, olusturan_kullanici_id=kullanici_id)
        db.session.add(kat)
        db.session.commit()
        return kat
    except Exception:
        db.session.rollback()
        raise


def kategori_sil(kategori_id: int) -> bool:
    """Kullanımdaysa pasife alır (True döner), değilse siler (False döner)."""
    try:
        kat = FinansKategori.query.get(int(kategori_id))
        if not kat:
            raise FinansHata('Kategori bulunamadı.')
        kullanimda = (FinansIslem.query.filter_by(kategori_id=kat.id).first()
                      or FinansAnaGiderKalem.query.filter_by(kategori_id=kat.id).first()
                      or FinansGiderAdi.query.filter_by(kategori_id=kat.id).first())
        if kullanimda:
            kat.aktif = False
            db.session.commit()
            return True
        db.session.delete(kat)
        db.session.commit()
        return False
    except Exception:
        db.session.rollback()
        raise


def gider_adi_ekle(kategori_id, ad: str, varsayilan_tutar=None) -> FinansGiderAdi:
    kat = _kategori_getir(kategori_id, 'kucuk_gider')
    ad = _ad_temizle(ad, 150)
    tutar = parse_tutar(varsayilan_tutar) if str(varsayilan_tutar or '').strip() else None
    try:
        mevcut = next((g for g in FinansGiderAdi.query.filter_by(kategori_id=kat.id).all() if _ad_esit(g.ad, ad)), None)
        if mevcut:
            if mevcut.aktif:
                raise FinansHata(f'"{ad}" bu kategoride zaten var.')
            mevcut.aktif = True
            mevcut.varsayilan_tutar = tutar
            db.session.commit()
            return mevcut
        ga = FinansGiderAdi(kategori_id=kat.id, ad=ad, varsayilan_tutar=tutar)
        db.session.add(ga)
        db.session.commit()
        return ga
    except Exception:
        db.session.rollback()
        raise


def gider_adi_sil(gider_adi_id: int) -> bool:
    try:
        ga = FinansGiderAdi.query.get(int(gider_adi_id))
        if not ga:
            raise FinansHata('Gider adı bulunamadı.')
        if FinansIslem.query.filter_by(gider_adi_id=ga.id).first():
            ga.aktif = False
            db.session.commit()
            return True
        db.session.delete(ga)
        db.session.commit()
        return False
    except Exception:
        db.session.rollback()
        raise


def _kalem_takvimi(siklik, ilk_odeme_tarihi, baslangic_donem, bitis_donem):
    if siklik not in ('aylik', 'haftalik'):
        raise FinansHata('Ödeme sıklığı aylık veya haftalık olmalı.')
    ilk = None
    if siklik == 'haftalik':
        try:
            ilk = date.fromisoformat(str(ilk_odeme_tarihi or ''))
        except ValueError:
            raise FinansHata('İlk haftalık ödeme tarihini seçin.')
    bas = parse_donem(baslangic_donem or (ilk.strftime('%Y-%m') if ilk else None))
    bit = parse_donem(bitis_donem) if str(bitis_donem or '').strip() else None
    if ilk and bas > ilk.strftime('%Y-%m'):
        raise FinansHata('İlk haftalık ödeme başlangıç ayından önce olamaz.')
    if bit and (bit < bas or (ilk and bit < ilk.strftime('%Y-%m'))):
        raise FinansHata('Bitiş ayı başlangıçtan önce olamaz.')
    return bas, bit, ilk


def kalem_ekle(ad: str, kategori_id, varsayilan_tutar, varsayilan_hesap_kodu: str,
               baslangic_donem: str, bitis_donem: str, notlar: str, kullanici_id: int,
               siklik: str = 'aylik', ilk_odeme_tarihi=None, tutar_degisken: bool = False,
               calisan=False, calisan_adi='', calisan_cari_id=None) -> FinansAnaGiderKalem:
    ad = _ad_temizle(ad, 150)
    kat = _kategori_getir(kategori_id, 'ana_gider', zorunlu=False)
    tutar = (parse_tutar(varsayilan_tutar)
             if not tutar_degisken and str(varsayilan_tutar or '').strip() else Decimal('0.00'))
    if varsayilan_hesap_kodu and varsayilan_hesap_kodu not in GIDER_HESAPLARI:
        raise FinansHata('Varsayılan hesap Elde veya Banka olmalı.')
    bas, bit, ilk = _kalem_takvimi(siklik, ilk_odeme_tarihi, baslangic_donem, bitis_donem)
    if siklik == 'haftalik':
        bas = ilk.strftime('%Y-%m')
    try:
        if any(_ad_esit(k.ad, ad) for k in FinansAnaGiderKalem.query.all()):
            raise FinansHata(f'"{ad}" kalemi zaten var.')
        kalem = FinansAnaGiderKalem(ad=ad, kategori_id=kat.id if kat else None, varsayilan_tutar=tutar,
                                    varsayilan_hesap_kodu=varsayilan_hesap_kodu or None,
                                    baslangic_donem=bas, bitis_donem=bit,
                                    siklik=siklik, ilk_odeme_tarihi=ilk, tutar_degisken=tutar_degisken,
                                    notlar=(notlar or '').strip() or None,
                                    olusturan_kullanici_id=kullanici_id)
        db.session.add(kalem)
        db.session.flush()
        if calisan:
            from finans_calisan_service import cari_bagla, plan_hakedislerini_isle
            cari_bagla(kalem, kullanici_id, calisan_adi, calisan_cari_id)
            plan_hakedislerini_isle(kalem)
        db.session.commit()
        return kalem
    except Exception:
        db.session.rollback()
        raise


def kalem_guncelle(kalem_id: int, ad: str, kategori_id, varsayilan_tutar, varsayilan_hesap_kodu: str,
                   baslangic_donem: str, bitis_donem: str, notlar: str,
                   siklik=None, ilk_odeme_tarihi=None, tutar_degisken=None,
                   calisan=None, calisan_adi='', calisan_cari_id=None, kullanici_id=None) -> FinansAnaGiderKalem:
    kalem = (FinansAnaGiderKalem.query.filter_by(id=int(kalem_id))
             .populate_existing().with_for_update().first())
    if not kalem:
        raise FinansHata('Kalem bulunamadı.')
    ad = _ad_temizle(ad, 150)
    kat = _kategori_getir(kategori_id, 'ana_gider', zorunlu=False)
    siklik = siklik or kalem.siklik
    if ilk_odeme_tarihi is None:
        ilk_odeme_tarihi = kalem.ilk_odeme_tarihi
    if tutar_degisken is None:
        tutar_degisken = kalem.tutar_degisken
    tutar = (parse_tutar(varsayilan_tutar)
             if not tutar_degisken and str(varsayilan_tutar or '').strip() else Decimal('0.00'))
    if varsayilan_hesap_kodu and varsayilan_hesap_kodu not in GIDER_HESAPLARI:
        raise FinansHata('Varsayılan hesap Elde veya Banka olmalı.')
    bas, bit, ilk = _kalem_takvimi(siklik, ilk_odeme_tarihi, baslangic_donem, bitis_donem)
    try:
        from finans_calisan_service import cari_bagla, plan_hakedislerini_isle
        if kalem.calisan_cari_id:
            if calisan is False:
                raise FinansHata('Çalışan bağlantısı kaldırılamaz; ayrı bir gider planı açın.')
            if calisan_cari_id and int(calisan_cari_id) != kalem.calisan_cari_id:
                raise FinansHata('Çalışan bağlantısı değiştirilemez.')
            plan_hakedislerini_isle(kalem)
            from models import FinansCalisanHakedis
            if ((siklik != kalem.siklik or ilk != kalem.ilk_odeme_tarihi or bas != kalem.baslangic_donem)
                    and FinansCalisanHakedis.query.filter_by(kalem_id=kalem.id).first()):
                raise FinansHata('Hak edişi oluşmuş planın takvimi değiştirilemez; yeni takvim için ayrı plan açın.')
        odemeler = FinansIslem.query.filter_by(kalem_id=kalem.id, tur='ana_gider', iptal=False).all()
        if siklik != kalem.siklik or ilk != kalem.ilk_odeme_tarihi:
            if any(len(o.donem) == 10 for o in odemeler):
                raise FinansHata('Haftalık ödemesi olan kaydın takvimi değiştirilemez. '
                                 'Bitiş ayı belirleyip yeni takvim için ayrı bir ödeme tanımlayın.')
            if siklik == 'haftalik' and any(o.donem >= ilk.strftime('%Y-%m') for o in odemeler):
                raise FinansHata('Haftalık başlangıcı, ödenmiş son aylık dönemden sonraki bir ayda seçin.')
        cakisan = any(_ad_esit(k.ad, ad) for k in FinansAnaGiderKalem.query.filter(FinansAnaGiderKalem.id != kalem.id).all())
        if cakisan:
            raise FinansHata(f'"{ad}" adında başka bir kalem var.')
        kalem.ad = ad
        kalem.kategori_id = kat.id if kat else None
        kalem.varsayilan_tutar = tutar
        kalem.varsayilan_hesap_kodu = varsayilan_hesap_kodu or None
        kalem.baslangic_donem = bas
        kalem.bitis_donem = bit
        kalem.siklik = siklik
        kalem.ilk_odeme_tarihi = ilk
        kalem.tutar_degisken = tutar_degisken
        kalem.notlar = (notlar or '').strip() or None
        if calisan and not kalem.calisan_cari_id:
            cari_bagla(kalem, kullanici_id or kalem.olusturan_kullanici_id, calisan_adi, calisan_cari_id)
            plan_hakedislerini_isle(kalem)
        db.session.commit()
        return kalem
    except Exception:
        db.session.rollback()
        raise


def kalem_pasif(kalem_id: int, aktif: bool = False) -> FinansAnaGiderKalem:
    try:
        kalem = FinansAnaGiderKalem.query.filter_by(id=int(kalem_id)).populate_existing().with_for_update().first()
        if not kalem:
            raise FinansHata('Kalem bulunamadı.')
        if kalem.calisan_cari_id and kalem.aktif:
            from finans_calisan_service import plan_hakedislerini_isle
            plan_hakedislerini_isle(kalem)
        if aktif and kalem.calisan_cari_id:
            from finans_cari_service import cari_getir
            if not cari_getir(kalem.calisan_cari_id, kilitle=True).aktif:
                raise FinansHata('Önce çalışanın cari hesabını yeniden açın.')
        kalem.aktif = aktif
        db.session.commit()
        return kalem
    except Exception:
        db.session.rollback()
        raise


# ============================== #
#   SORGULAR                     #
# ============================== #
def kategoriler(tur: str, sadece_aktif: bool = True) -> list:
    q = FinansKategori.query.filter_by(tur=tur)
    if sadece_aktif:
        q = q.filter_by(aktif=True)
    return q.order_by(FinansKategori.sira, FinansKategori.ad).all()


def gider_adlari(kategori_id, sadece_aktif: bool = True) -> list:
    q = FinansGiderAdi.query.filter_by(kategori_id=int(kategori_id))
    if sadece_aktif:
        q = q.filter_by(aktif=True)
    return q.order_by(FinansGiderAdi.ad).all()


def defter(hesap_kodu: str, donem: str = None, tur: str = None, iptal_goster: bool = False,
           sayfa: int = 1, adet: int = 100):
    hesap = hesap_getir(hesap_kodu)
    q = FinansIslem.query.filter_by(hesap_id=hesap.id)
    if donem:
        bas, son = donem_utc_araligi(donem)
        q = q.filter(FinansIslem.tarih >= bas, FinansIslem.tarih < son)
    if tur:
        q = q.filter_by(tur=tur)
    if not iptal_goster:
        q = q.filter_by(iptal=False)
    q = q.order_by(FinansIslem.tarih.desc(), FinansIslem.id.desc())
    return hesap, q.paginate(page=max(1, sayfa), per_page=adet, error_out=False)


def son_islemler(adet: int = 15) -> list:
    return (FinansIslem.query.filter_by(iptal=False)
            .order_by(FinansIslem.tarih.desc(), FinansIslem.id.desc()).limit(adet).all())


def donem_islemleri(donem: str, tur: str, hesap_kodu: str = None, kategori_id=None) -> list:
    bas, son = donem_utc_araligi(donem)
    q = FinansIslem.query.filter(FinansIslem.tur == tur, FinansIslem.iptal.is_(False),
                                 FinansIslem.tarih >= bas, FinansIslem.tarih < son)
    if hesap_kodu:
        q = q.join(FinansHesap).filter(FinansHesap.kod == hesap_kodu)
    if kategori_id:
        q = q.filter(FinansIslem.kategori_id == int(kategori_id))
    return q.order_by(FinansIslem.tarih.desc(), FinansIslem.id.desc()).all()


def kategori_toplamlari(islemler: list) -> list:
    """[{ad, toplam, adet}] — verilen işlem listesini kategoriye göre gruplar."""
    toplam = {}
    for i in islemler:
        ad = i.kategori.ad if i.kategori else '—'
        t = toplam.setdefault(ad, {'ad': ad, 'toplam': Decimal('0.00'), 'adet': 0})
        t['toplam'] += Decimal(str(i.tutar))
        t['adet'] += 1
    return sorted(toplam.values(), key=lambda x: -x['toplam'])


def donem_ana_gider_durumu(donem: str) -> list:
    """Aylık/haftalık giderler ve çalışanların hak ediş/ödenen/kalan dökümü."""
    from finans_calisan_service import hakedis_satirlari, durum_satiri
    kalemler = (FinansAnaGiderKalem.query.filter_by(aktif=True)
                .filter(FinansAnaGiderKalem.baslangic_donem <= donem)
                .filter((FinansAnaGiderKalem.bitis_donem.is_(None)) | (FinansAnaGiderKalem.bitis_donem >= donem))
                .order_by(FinansAnaGiderKalem.sira, FinansAnaGiderKalem.ad).all())
    odemeler = {(o.kalem_id, o.donem): o for o in FinansIslem.query
                .filter_by(tur='ana_gider', iptal=False)
                .filter(FinansIslem.donem.startswith(donem)).all() if not o.kalem.calisan_cari_id}
    haklar = {(d['kalem'].id, d['donem']): d for d in hakedis_satirlari(donem)}
    sonuc = []
    for k in kalemler:
        for vade in kalem_odeme_donemleri(k, donem):
            if k.calisan_cari_id:
                sonuc.append(haklar.pop((k.id, vade), None) or durum_satiri(k, vade))
            else:
                sonuc.append({'kalem': k, 'donem': vade, 'etiket': donem_etiket(vade),
                              'odeme': odemeler.pop((k.id, vade), None)})
    for o in odemeler.values():
        sonuc.append({'kalem': o.kalem, 'donem': o.donem,
                      'etiket': donem_etiket(o.donem), 'odeme': o})
    sonuc.extend(haklar.values())
    for d in sonuc:
        if 'calisan' not in d:
            d.update(calisan=False, hakedis=None, hak_tutar=d['kalem'].varsayilan_tutar or None,
                     odenen=d['odeme'].tutar if d['odeme'] else Decimal('0'),
                     kalan=Decimal('0') if d['odeme'] else (d['kalem'].varsayilan_tutar or None),
                     belirsiz=not d['odeme'] and not d['kalem'].varsayilan_tutar,
                     bekleyen=d['odeme'] is None)
    return sorted(sonuc, key=lambda d: (d['donem'], d['kalem'].sira, d['kalem'].ad))


def _donem_toplam(donem: str, tur: str) -> Decimal:
    bas, son = donem_utc_araligi(donem)
    v = (db.session.query(func.coalesce(func.sum(FinansIslem.tutar), 0))
         .filter(FinansIslem.tur == tur, FinansIslem.iptal.is_(False),
                 FinansIslem.tarih >= bas, FinansIslem.tarih < son).scalar())
    return Decimal(str(v or 0)).quantize(IKI_HANE)


def donem_ozet(donem: str) -> dict:
    durum = donem_ana_gider_durumu(donem)
    bekleyen = [d for d in durum if d['bekleyen']]
    from finans_calisan_service import hakedis_satirlari
    bekleyen += [d for d in hakedis_satirlari() if d['donem'][:7] < donem and d['bekleyen']]
    gelir = _donem_toplam(donem, 'gelir')
    kucuk = _donem_toplam(donem, 'kucuk_gider')
    ana = _donem_toplam(donem, 'ana_gider')
    cari_odeme = _donem_toplam(donem, 'cari_odeme')
    cari_tahsilat = _donem_toplam(donem, 'cari_tahsilat')
    return {
        'donem': donem, 'etiket': donem_etiket(donem),
        'gelir': gelir, 'kucuk_gider': kucuk, 'ana_gider': ana,
        'cari_odeme': cari_odeme, 'cari_tahsilat': cari_tahsilat,
        'toplam_gider': kucuk + ana + cari_odeme, 'net': gelir + cari_tahsilat - kucuk - ana - cari_odeme,
        'bekleyen_adet': len(bekleyen),
        'bekleyen_belirsiz_adet': sum(1 for d in bekleyen if d['belirsiz']),
        'bekleyen_tutar': sum((d['kalan'] or Decimal('0') for d in bekleyen), Decimal('0.00')),
        'bekleyenler': bekleyen,
    }


def yillik_rapor(yil: int) -> list:
    satirlar = []
    for ay in range(1, 13):
        donem = f'{yil:04d}-{ay:02d}'
        gelir = _donem_toplam(donem, 'gelir')
        kucuk = _donem_toplam(donem, 'kucuk_gider')
        ana = _donem_toplam(donem, 'ana_gider')
        cari_odeme = _donem_toplam(donem, 'cari_odeme')
        cari_tahsilat = _donem_toplam(donem, 'cari_tahsilat')
        satirlar.append({'donem': donem, 'etiket': donem_etiket(donem), 'gelir': gelir,
                         'kucuk_gider': kucuk, 'ana_gider': ana,
                         'cari_odeme': cari_odeme, 'cari_tahsilat': cari_tahsilat,
                         'toplam_gider': kucuk + ana + cari_odeme,
                         'net': gelir + cari_tahsilat - kucuk - ana - cari_odeme})
    return satirlar


def tutarlilik_kontrol() -> list:
    """Her hesap için bakiye ↔ defter (SUM(yon*tutar), iptal hariç) farkı; fark≠0 olanlar döner."""
    sonuc = []
    for h in hesaplar():
        defter_toplam = (db.session.query(func.coalesce(func.sum(FinansIslem.yon * FinansIslem.tutar), 0))
                         .filter(FinansIslem.hesap_id == h.id, FinansIslem.iptal.is_(False)).scalar())
        defter_toplam = Decimal(str(defter_toplam or 0)).quantize(IKI_HANE)
        bakiye = Decimal(str(h.bakiye or 0)).quantize(IKI_HANE)
        if defter_toplam != bakiye:
            sonuc.append({'hesap': h, 'bakiye': bakiye, 'defter': defter_toplam, 'fark': bakiye - defter_toplam})
    return sonuc
