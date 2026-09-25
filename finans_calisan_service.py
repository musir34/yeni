"""Çalışan carisi, dönem hak edişi ve kısmi ödeme; kasa/cari tek transaction.

Kilit sırası: ödeme planı → kasa (varsa) → cari. Sabit hak edişler vadesinde
bir kez oluşturulur. Değişken tutarlar belirlenmeden borç tutarı varsayılmaz.
"""
from datetime import date, datetime
from decimal import Decimal
import uuid

from sqlalchemy import func
from models import (db, FinansAnaGiderKalem, FinansCalisanHakedis,
                    FinansCari, FinansCariHareket, FinansIslem)
import finans_service as fs
import finans_cari_service as cs
from time_utils import ist_to_utc, to_ist


def _tutar(raw):
    if str(raw).strip() in ('0', '0.00', '0,00'):
        return Decimal('0.00')
    value = fs.parse_tutar(raw)
    if not value.is_finite():
        raise fs.FinansHata('Tutar geçersiz.')
    return value


def cari_bagla(kalem, kullanici_id, calisan_adi='', cari_id=None):
    """Plan kaydıyla aynı transaction; yalnız açık çalışan carisine bağlanır."""
    if kalem.calisan_cari_id:
        if cari_id and int(cari_id) != kalem.calisan_cari_id:
            raise fs.FinansHata('Çalışan bağlantısı değiştirilemez; ayrı bir ödeme planı açın.')
        return
    if cari_id:
        cari = cs.cari_getir(cari_id, kilitle=True)
    else:
        ad = fs._ad_temizle(calisan_adi, 150)
        cari = next((c for c in FinansCari.query.all() if fs._ad_esit(c.ad, ad)), None)
        if cari:
            cari = cs.cari_getir(cari.id, kilitle=True)
        else:
            cari = FinansCari(ad=ad, tur='calisan', bakiye=0, aktif=True,
                              olusturan_kullanici_id=kullanici_id)
            db.session.add(cari)
            db.session.flush()
    if cari.tur != 'calisan' or not cari.aktif:
        raise fs.FinansHata('Aynı isimli hesap çalışan hesabı değil veya kapalı; açık bir çalışan hesabı seçin.')
    kalem.calisan_cari_id = cari.id
    if not kalem.olusturan_kullanici_id:
        kalem.olusturan_kullanici_id = kullanici_id
    db.session.flush()


def _getir(kalem, donem):
    h = FinansCalisanHakedis.query.filter_by(kalem_id=kalem.id, donem=donem).first()
    if h is None:
        h = FinansCalisanHakedis(kalem_id=kalem.id, donem=donem)
        db.session.add(h)
        db.session.flush()
    return h


def odenen_tutar(hakedis_id):
    value = (db.session.query(func.coalesce(func.sum(FinansCariHareket.tutar), 0))
             .filter_by(hakedis_id=hakedis_id, tur='odeme', iptal=False).scalar())
    return Decimal(str(value or 0)).quantize(fs.IKI_HANE)


def _hak_yaz(h, cari, tutar, kullanici_id):
    """Hak ediş farkını cari defterine yazar; kasa hareketi oluşturmaz."""
    fark = tutar - (h.tutar or Decimal('0'))
    if fark:
        tarih = ist_to_utc(datetime.combine(date.fromisoformat(
            h.donem if len(h.donem) == 10 else h.donem + '-01'), datetime.min.time()))
        cs._cari_hareket(cari, 'hakedis' if fark > 0 else 'hakedis_azaltma', abs(fark),
                         tarih, f'{h.kalem.ad} — {fs.donem_etiket(h.donem)} hak edişi',
                         kullanici_id, hakedis_id=h.id)
    h.tutar = tutar
    db.session.flush()


def plan_hakedislerini_isle(kalem, bugun=None):
    """Plan kilidi çağıranda alınır; COMMIT ETMEZ. Eski ödemeleri kasaya tekrar yazmaz."""
    if not kalem.calisan_cari_id:
        return
    bugun = bugun or to_ist(datetime.utcnow()).date()
    uid = kalem.olusturan_kullanici_id
    if not uid:
        raise fs.FinansHata('Çalışan planını kaydeden kullanıcı bulunamadı.')
    # Eski kasa ödemeleri cari bağlantısı kurulurken iptal edilemesin.
    # İşlem kilidini cariden önce al: iptal akışıyla aynı sıra.
    eskiler = (FinansIslem.query.filter_by(kalem_id=kalem.id, tur='ana_gider', iptal=False)
               .order_by(FinansIslem.id).populate_existing().with_for_update().all())
    cari = cs.cari_getir(kalem.calisan_cari_id, kilitle=True)
    if not cari.aktif:
        raise fs.FinansHata('Çalışanın cari hesabı kapalı.')
    # Çalışan olarak işaretlenen eski düzenli ödemeler: ödenmiş tutar kadar
    # hak ediş ve cari ödeme; mevcut kasa kaydı aynen korunur.
    for eski in eskiler:
        if FinansCariHareket.query.filter_by(islem_id=eski.id).first():
            continue
        h = _getir(kalem, eski.donem)
        if h.tutar is None:
            _hak_yaz(h, cari, eski.tutar, uid)
        cs._cari_hareket(cari, 'odeme', eski.tutar, eski.tarih,
                         eski.aciklama, eski.kullanici_id, islem_id=eski.id, hakedis_id=h.id)
    if not kalem.aktif:
        return
    ay = kalem.baslangic_donem
    son = min(bugun.strftime('%Y-%m'), kalem.bitis_donem or '9999-12')
    while ay <= son:
        for donem in fs.kalem_odeme_donemleri(kalem, ay):
            gun = date.fromisoformat(donem if len(donem) == 10 else donem + '-01')
            if gun > bugun:
                continue
            h = FinansCalisanHakedis.query.filter_by(kalem_id=kalem.id, donem=donem).first()
            if h is None:
                h = _getir(kalem, donem)
                if not kalem.tutar_degisken and kalem.varsayilan_tutar:
                    _hak_yaz(h, cari, kalem.varsayilan_tutar, uid)
        ay = fs.donem_kaydir(ay, 1)


def hakedisleri_isle(bugun=None):
    """Saatlik görev ve finans sayfaları için idempotent, kaçırılan dönemleri de işler."""
    ids = [k.id for k in FinansAnaGiderKalem.query
           .filter(FinansAnaGiderKalem.calisan_cari_id.isnot(None), FinansAnaGiderKalem.aktif.is_(True))
           .order_by(FinansAnaGiderKalem.id).all()]
    for kid in ids:
        try:
            k = (FinansAnaGiderKalem.query.filter_by(id=kid)
                 .populate_existing().with_for_update().one())
            plan_hakedislerini_isle(k, bugun)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise


def hakedis_ve_odeme(kalem_id, donem, hak_tutar, odeme_tutar, hesap_kodu, tarih,
                     aciklama, kullanici_id, odeme_anahtari, beklenen_hakedis):
    """Hak ediş ve varsa kısmi ödeme atomik; çift tıklama anahtarı tekrar para düşürmez."""
    try:
        try:
            token = str(uuid.UUID(str(odeme_anahtari)))
        except (ValueError, TypeError, AttributeError):
            raise fs.FinansHata('Ödeme anahtarı geçersiz; sayfayı yenileyin.')
        donem = fs.parse_odeme_donemi(donem)
        hak = _tutar(hak_tutar)
        odeme = _tutar(odeme_tutar) if str(odeme_tutar or '').strip() else Decimal('0')
        k = (FinansAnaGiderKalem.query.filter_by(id=int(kalem_id))
             .populate_existing().with_for_update().first())
        if not k or not k.calisan_cari_id:
            raise fs.FinansHata('Çalışan ödeme planı bulunamadı.')
        tekrar = FinansCariHareket.query.filter_by(odeme_anahtari=token).first()
        if tekrar:
            if (tekrar.iptal or tekrar.hakedis.kalem_id != k.id or tekrar.hakedis.donem != donem
                    or tekrar.tutar != odeme or tekrar.hakedis.tutar != hak
                    or tekrar.islem.hesap.kod != hesap_kodu):
                raise fs.FinansHata('Bu ödeme isteği daha önce kullanılmış; sayfayı yenileyin.')
            db.session.commit()
            return tekrar.hakedis, tekrar.islem
        h = FinansCalisanHakedis.query.filter_by(kalem_id=k.id, donem=donem).first()
        yeni_hakedis = h is None
        if h is None:
            if not k.aktif or donem not in fs.kalem_odeme_donemleri(k, donem[:7]):
                raise fs.FinansHata('Bu dönem çalışan planında bulunmuyor.')
            h = _getir(k, donem)
        mevcut = h.tutar
        if yeni_hakedis and mevcut is None and not k.tutar_degisken and k.varsayilan_tutar:
            mevcut = k.varsayilan_tutar
        beklenen = _tutar(beklenen_hakedis) if str(beklenen_hakedis or '').strip() else None
        if mevcut != beklenen:
            raise fs.FinansHata('Hak ediş başka bir işlemde değişmiş; sayfayı yenileyin.')
        odenen = odenen_tutar(h.id)
        if hak < odenen:
            raise fs.FinansHata(f'Hak ediş, ödenen {odenen:.2f} ₺ tutarından az olamaz. Önce hatalı ödemeyi iptal edin.')
        if odeme > hak - odenen:
            raise fs.FinansHata(f'Ödeme kalan borcu aşamaz. Kalan: {hak - odenen:.2f} ₺.')
        hesap = None
        if odeme:
            fs._gider_hesabi_kontrol(hesap_kodu)
            hesap = fs.hesap_getir(hesap_kodu, kilitle=True)
        cari = cs.cari_getir(k.calisan_cari_id, kilitle=True)
        if not cari.aktif:
            raise fs.FinansHata('Çalışanın cari hesabı kapalı.')
        _hak_yaz(h, cari, hak, kullanici_id)
        islem = None
        if odeme:
            aciklama = (aciklama or '').strip() or f'{k.ad} — {fs.donem_etiket(donem)} ödemesi'
            islem = fs._hareket(hesap, 'cari_odeme', -1, odeme, tarih, kullanici_id,
                                kalem_id=k.id, donem=donem, kategori_id=k.kategori_id, aciklama=aciklama)
            cs._cari_hareket(cari, 'odeme', odeme, tarih, aciklama, kullanici_id,
                             islem_id=islem.id, hakedis_id=h.id, odeme_anahtari=token)
        db.session.commit()
        return h, islem
    except Exception:
        db.session.rollback()
        raise


def durum_satiri(kalem, donem, hakedis=None):
    odenen = odenen_tutar(hakedis.id) if hakedis else Decimal('0')
    tutar = hakedis.tutar if hakedis else (kalem.varsayilan_tutar or None)
    kalan = max(Decimal('0'), tutar - odenen) if tutar is not None else None
    return {'kalem': kalem, 'donem': donem, 'etiket': fs.donem_etiket(donem),
            'calisan': True, 'hakedis': hakedis, 'hak_tutar': tutar,
            'odenen': odenen, 'kalan': kalan, 'belirsiz': tutar is None,
            'bekleyen': kalan is None or kalan > 0, 'odeme': None}


def hakedis_satirlari(donem=None, cari_id=None):
    q = FinansCalisanHakedis.query.join(FinansAnaGiderKalem)
    if donem:
        q = q.filter(FinansCalisanHakedis.donem.startswith(donem))
    if cari_id:
        q = q.filter(FinansAnaGiderKalem.calisan_cari_id == cari_id)
    return [durum_satiri(h.kalem, h.donem, h) for h in q.order_by(FinansCalisanHakedis.donem).all()]
