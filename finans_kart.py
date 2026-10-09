# finans_kart.py
"""
💳 Finans — Kredi kartı: PDF ekstre yükleme, satıcı hafızası, mutabakat (finans_bp'ye eklenir).

Kart "kredi_karti" borç hesabıdır (bakiye eksi = kart borcu). Aylık İşbankası Maximum ekstresi
(PDF) yüklenir; satırlar önizlenir, tür/kategori seçilir, mevcut kayıtla eşleşenler (tutar + ±3 gün)
"zaten kayıtlı" diye tiksiz gelir. Kaydet: işletme gideri → kucuk_gider, şahsi → kart_sahsi,
iade → kart_iade, bankadan/elden ödeme → transfer, nakit avans → transfer Kart → Elde.
Şahsi satırda isteğe bağlı şahsi cari seçilir: kart_sahsi işlemine bağlı `borc_alma` cari hareketi yazılır
(kişinin kasaya borcu artar; iptal iki tarafı birlikte geri alır). Yalnız aktif, TL, 'sahsi' türü cari.
Mutabakat: ekstre borcu ↔ yükleme sonrası kart bakiyesi; fark elle satır ekleyerek ya da
düzeltme kaydıyla kapatılabilir (komutan: "mutabakata manuel müdahale şansım olmalı").
Satıcı hafızası PlatformConfig 'finans_kart' torbasında (takip_notu deseni, migration yok).
"""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import render_template, request, redirect, url_for, flash

from login_logout import login_required, roles_required
from finans import finans_bp, _uid, _log, _hata_flash, _bugun_ist
import finans_service as fs
from finans_service import FinansHata
from finans_kart_parser import (ekstre_ayristir, pdf_metni, tutar_cevir, satici_anahtari, oneri_tur,
                                TURLER, TUR_ETIKET, TUR_GIDER, TUR_SAHSI, TUR_ODEME_BANKA,
                                TUR_ODEME_ELDE, TUR_IADE, TUR_NAKIT, TUR_ATLA)
from models import db, FinansCari, FinansIslem, PlatformConfig
import finans_cari_service as cs
from time_utils import ist_to_utc, to_ist

logger = logging.getLogger(__name__)

KART_HESABI = 'kredi_karti'
HAFIZA_PLATFORM = 'finans_kart'
ESLESME_GUN = 3          # ekstre tarihi ile kayıt tarihi arasındaki tolerans (gün)
EN_COK_SATIR = 400


# ============================== #
#   SATICI HAFIZASI              #
# ============================== #
def hafiza_oku() -> dict:
    """{satıcı anahtarı: {'tur': ..., 'kategori_id': ...}} — hata → boş (akış durmaz)."""
    try:
        k = PlatformConfig.query.filter_by(platform=HAFIZA_PLATFORM).first()
        return dict(((k.extra_config or {}).get('satici') or {})) if k else {}
    except Exception:
        logger.warning('[KART] satıcı hafızası okunamadı', exc_info=True)
        db.session.rollback()
        return {}


def hafiza_yaz(guncelle: dict) -> None:
    """Seçilen satırların tür/kategori kararını satıcı anahtarına öğretir. COMMIT ETMEZ."""
    if not guncelle:
        return
    k = PlatformConfig.query.filter_by(platform=HAFIZA_PLATFORM).first()
    if k is None:
        k = PlatformConfig(platform=HAFIZA_PLATFORM, is_active=True, extra_config={})
        db.session.add(k)
    torba = dict(k.extra_config or {})
    satici = dict(torba.get('satici') or {})
    satici.update(guncelle)
    torba['satici'] = satici
    k.extra_config = torba   # JSON kolonu: yeni nesne atanmalı ki değişiklik algılansın


def sahsi_cariler() -> list:
    """Şahsi harcamanın düşebileceği cariler: aktif, TL, 'sahsi' türü."""
    return (FinansCari.query.filter_by(tur='sahsi', aktif=True, para_birimi='TRY')
            .order_by(FinansCari.ad).all())


def hafiza_cari(kayit: dict, cari_idler: set):
    """Hafızadaki şahsi satıcının carisi; tür şahsi değilse ya da cari artık listede yoksa None."""
    if (kayit or {}).get('tur') != TUR_SAHSI:
        return None
    cid = kayit.get('cari_id')
    return cid if cid in cari_idler else None


def _sahsi_cari_getir(cari_id, kaynak: str) -> FinansCari:
    """Kilitli getirir; şahsi/aktif/TL değilse FinansHata. Kilit sırası hesap → cari (kart önce kilitli)."""
    try:
        cari = cs.cari_getir(cari_id, kilitle=True)
    except (ValueError, TypeError):
        raise FinansHata(f'{kaynak}: cari hesap geçersiz.')
    if cari.tur != 'sahsi':
        raise FinansHata(f'{kaynak}: şahsi harcama yalnız şahsi cari hesaba yazılır ({cari.ad}).')
    if not cari.aktif:
        raise FinansHata(f'{kaynak}: {cari.ad} hesabı kapalı.')
    if (cari.para_birimi or 'TRY') != 'TRY':
        raise FinansHata(f'{kaynak}: {cari.ad} dolar hesabı; kart harcaması TL hesaba yazılır.')
    return cari


# ============================== #
#   EŞLEŞTİRME / ÖNİZLEME        #
# ============================== #
def _tarih_utc(gun: date) -> datetime:
    """Ekstre günü (İstanbul) → öğlen 12:00 İstanbul'un naive UTC'si; gün kayması olmaz."""
    return ist_to_utc(datetime(gun.year, gun.month, gun.day, 12, 0))


def _kart_hareketleri(bas: date, son: date) -> list:
    kart = fs.hesap_getir(KART_HESABI)
    return (FinansIslem.query
            .filter(FinansIslem.hesap_id == kart.id, FinansIslem.iptal.is_(False),
                    FinansIslem.tarih >= _tarih_utc(bas - timedelta(days=ESLESME_GUN + 1)),
                    FinansIslem.tarih <= _tarih_utc(son + timedelta(days=ESLESME_GUN + 1)))
            .order_by(FinansIslem.tarih).all())


def eslestir(satirlar: list, hareketler: list) -> dict:
    """Ekstre satırı → mevcut kart kaydı. Aynı tutar, aynı yön, ±ESLESME_GUN gün; açıklaması
    birebir aynı olan (önceki yükleme) öncelikli. Bir kayıt yalnız bir satıra eşlenir."""
    kullanilan: set = set()
    sonuc: dict = {}
    for s in satirlar:
        yon = -1 if s.tutar > 0 else +1
        tutar = abs(s.tutar)
        adaylar = []
        for h in hareketler:
            if h.id in kullanilan or h.yon != yon or Decimal(str(h.tutar)) != tutar:
                continue
            gun = to_ist(h.tarih).date()
            fark = abs((gun - s.tarih).days)
            if fark > ESLESME_GUN:
                continue
            adaylar.append((0 if (h.aciklama or '') == s.aciklama else 1, fark, h))
        if adaylar:
            adaylar.sort(key=lambda a: (a[0], a[1], a[2].id))
            h = adaylar[0][2]
            kullanilan.add(h.id)
            sonuc[s.sira] = h
    return sonuc


def _onizleme_satirlari(ekstre, hafiza: dict, kategoriler: list, cari_idler: set = frozenset()) -> list[dict]:
    hareketler = []
    if ekstre.satirlar:
        bas = min(s.tarih for s in ekstre.satirlar)
        son = max(s.tarih for s in ekstre.satirlar)
        hareketler = _kart_hareketleri(bas, son)
    eslesen = eslestir(ekstre.satirlar, hareketler)
    kat_idler = {k.id for k in kategoriler}
    sonuc = []
    for s in ekstre.satirlar:
        h = hafiza.get(s.satici_anahtari) or {}
        tur = h.get('tur') if h.get('tur') in TURLER else s.oneri_tur
        # Ödeme/iade/nakit önerisi ekstrenin yapısından gelir; hafıza yalnız harcama türünü değiştirir
        if s.oneri_tur in (TUR_ODEME_BANKA, TUR_ODEME_ELDE, TUR_IADE, TUR_NAKIT):
            tur = s.oneri_tur
        kategori_id = h.get('kategori_id') if h.get('kategori_id') in kat_idler else None
        e = eslesen.get(s.sira)
        sonuc.append({
            'sira': s.sira, 'tarih_iso': s.tarih.isoformat(), 'tarih_str': s.tarih.strftime('%d.%m.%Y'),
            'aciklama': s.aciklama, 'tutar': s.tutar, 'tutar_str': f'{s.tutar:.2f}',
            'taksit': s.taksit, 'taksit_toplam': s.taksit_toplam, 'sanal': s.sanal_kart, 'satici': s.satici_anahtari,
            'tur': tur, 'kategori_id': kategori_id, 'cari_id': hafiza_cari(h, cari_idler), 'hafizadan': bool(h),
            'eslesen': e, 'eslesen_metin': (f'{to_ist(e.tarih).strftime("%d.%m")} · {fs.ISLEM_TUR_ETIKET.get(e.tur, e.tur)}'
                                             f' · {(e.aciklama or "")[:40]}') if e else '',
            'secili': e is None,
        })
    return sonuc


def mutabakat_hesapla(borc: Decimal | None, kart_bakiye: Decimal, secili_net: Decimal) -> dict:
    """Ekstre borcu ↔ yükleme sonrası kart bakiyesi. hedef = −borç; sonrası = bakiye − seçili net."""
    sonrasi = (kart_bakiye - secili_net).quantize(Decimal('0.01'))
    hedef = (-borc).quantize(Decimal('0.01')) if borc is not None else None
    fark = (hedef - sonrasi).quantize(Decimal('0.01')) if hedef is not None else None
    return {'kart_bakiye': kart_bakiye, 'secili_net': secili_net, 'sonrasi': sonrasi, 'hedef': hedef, 'fark': fark}


# ============================== #
#   ROUTE'LAR                    #
# ============================== #
def _sayfa_ctx() -> dict:
    kart = fs.hesap_getir(KART_HESABI)
    son = (FinansIslem.query.filter_by(hesap_id=kart.id, iptal=False)
           .order_by(FinansIslem.tarih.desc(), FinansIslem.id.desc()).limit(12).all())
    return {'kart': kart, 'son_hareketler': son, 'kategoriler': fs.kategoriler('kucuk_gider'),
            'sahsi_cariler': sahsi_cariler(),
            'tur_etiket': TUR_ETIKET, 'turler': TURLER, 'satirlar': None, 'bugun': _bugun_ist()}


@finans_bp.route('/kart', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def kart_ekstre():
    try:
        ctx = _sayfa_ctx()
    except FinansHata as e:
        flash(f'{e} — scripts/add_finans_kredi_karti.py çalıştırılmalı.', 'danger')
        return redirect(url_for('finans.panel'))
    if request.method == 'GET':
        return render_template('finans_kart_ekstre.html', **ctx)

    dosya = request.files.get('pdf_file')
    if not dosya or not dosya.filename:
        flash('Ekstre PDF dosyası seçin.', 'danger')
        return redirect(url_for('finans.kart_ekstre'))
    try:
        ekstre = ekstre_ayristir(pdf_metni(dosya))
    except Exception:
        logger.exception('[KART] PDF okunamadı')
        flash('PDF okunamadı. Dosya İşbankası Maximum hesap özeti olmalı.', 'danger')
        return redirect(url_for('finans.kart_ekstre'))
    if not ekstre.satirlar:
        flash('Ekstrede işlem satırı bulunamadı. Dosya İşbankası Maximum hesap özeti mi?', 'danger')
        return redirect(url_for('finans.kart_ekstre'))
    if len(ekstre.satirlar) > EN_COK_SATIR:
        flash(f'Ekstrede {len(ekstre.satirlar)} satır var; en çok {EN_COK_SATIR} satır yüklenebilir.', 'danger')
        return redirect(url_for('finans.kart_ekstre'))

    satirlar = _onizleme_satirlari(ekstre, hafiza_oku(), ctx['kategoriler'],
                                   {c.id for c in ctx['sahsi_cariler']})
    secili_net = sum((s['tutar'] for s in satirlar if s['secili']), Decimal('0.00'))
    ctx.update({
        'satirlar': satirlar, 'ekstre': ekstre, 'dosya_adi': dosya.filename,
        'mutabakat': mutabakat_hesapla(ekstre.borc, Decimal(str(ctx['kart'].bakiye or 0)), secili_net),
        'secili_adet': sum(1 for s in satirlar if s['secili']),
        'eslesen_adet': sum(1 for s in satirlar if s['eslesen']),
        'ic_fark': ekstre.ic_tutarlilik_farki,
    })
    return render_template('finans_kart_ekstre.html', **ctx)


def _form_satirlari(f) -> list[dict]:
    """Önizleme formundaki seçili satırlar + elle eklenen satırlar → tek liste."""
    satirlar = []
    for sira in f.getlist('sec'):
        try:
            satirlar.append({
                'tarih': date.fromisoformat(f.get(f'tarih_{sira}', '')),
                'aciklama': (f.get(f'aciklama_{sira}') or '').strip()[:500],
                'tutar': Decimal(f.get(f'tutar_{sira}', '0')),
                'tur': f.get(f'tur_{sira}', TUR_ATLA),
                'kategori_id': f.get(f'kategori_{sira}') or None,
                'cari_id': f.get(f'cari_{sira}') or None,
                'kaynak': f'satır {sira}',
            })
        except Exception as exc:
            raise FinansHata(f'Satır {sira} okunamadı: {exc}')
    for i, tarih in enumerate(f.getlist('ek_tarih')):
        aciklama = (f.getlist('ek_aciklama')[i] if i < len(f.getlist('ek_aciklama')) else '').strip()
        tutar_ham = f.getlist('ek_tutar')[i] if i < len(f.getlist('ek_tutar')) else ''
        if not (tarih or aciklama or tutar_ham):
            continue  # boş ek satır
        try:
            satirlar.append({
                'tarih': date.fromisoformat(tarih),
                'aciklama': aciklama[:500] or 'Elle eklenen satır',
                'tutar': tutar_cevir(tutar_ham) if ',' in tutar_ham else Decimal(tutar_ham),
                'tur': f.getlist('ek_tur')[i] if i < len(f.getlist('ek_tur')) else TUR_GIDER,
                'kategori_id': (f.getlist('ek_kategori')[i] if i < len(f.getlist('ek_kategori')) else '') or None,
                'cari_id': (f.getlist('ek_cari')[i] if i < len(f.getlist('ek_cari')) else '') or None,
                'kaynak': f'elle eklenen {i + 1}',
            })
        except Exception as exc:
            raise FinansHata(f'Elle eklenen {i + 1}. satır okunamadı (tarih YYYY-AA-GG, tutar 1.250,50): {exc}')
    return satirlar


def _mukerrer_mi(kart_id: int, tarih_utc: datetime, tutar: Decimal, yon: int, aciklama: str) -> bool:
    return db.session.query(FinansIslem.id).filter(
        FinansIslem.hesap_id == kart_id, FinansIslem.iptal.is_(False), FinansIslem.yon == yon,
        FinansIslem.tutar == tutar, FinansIslem.aciklama == aciklama,
        FinansIslem.tarih >= tarih_utc - timedelta(days=ESLESME_GUN),
        FinansIslem.tarih <= tarih_utc + timedelta(days=ESLESME_GUN),
    ).first() is not None


def satirlari_kaydet(satirlar: list[dict], kullanici_id: int) -> dict:
    """Seçili satırları kart hesabına yazar. COMMIT ETMEZ; hata → FinansHata (çağıran rollback eder)."""
    kart = fs.hesap_getir(KART_HESABI, kilitle=True)
    eklenen, atlanan, ogrenilen = 0, 0, {}
    for s in satirlar:
        tur, tutar = s['tur'], abs(s['tutar'])
        if tur == TUR_ATLA or tutar == 0:
            continue
        if tur not in TURLER:
            raise FinansHata(f"{s['kaynak']}: geçersiz tür.")
        tarih = _tarih_utc(s['tarih'])
        yon = +1 if tur in (TUR_ODEME_BANKA, TUR_ODEME_ELDE, TUR_IADE) else -1
        if _mukerrer_mi(kart.id, tarih, tutar, yon, s['aciklama']):
            atlanan += 1
            continue
        if tur == TUR_GIDER:
            if not s['kategori_id']:
                raise FinansHata(f"{s['kaynak']} ({s['aciklama'][:30]}): işletme gideri için kategori seçin.")
            fs.kucuk_gider_ekle(KART_HESABI, s['kategori_id'], None, s['aciklama'], tutar, tarih, kullanici_id, commit=False)
        elif tur == TUR_SAHSI:
            cari = _sahsi_cari_getir(s['cari_id'], s['kaynak']) if s.get('cari_id') else None
            islem = fs._hareket(kart, 'kart_sahsi', -1, tutar, tarih, kullanici_id, aciklama=s['aciklama'])
            if cari is not None:
                cs._cari_hareket(cari, 'borc_alma', tutar, tarih, s['aciklama'], kullanici_id, islem_id=islem.id)
        elif tur == TUR_IADE:
            fs._hareket(kart, 'kart_iade', +1, tutar, tarih, kullanici_id, aciklama=s['aciklama'])
        elif tur == TUR_ODEME_BANKA:
            fs.transfer_yap('banka', KART_HESABI, tutar, tarih, s['aciklama'], kullanici_id, commit=False)
        elif tur == TUR_ODEME_ELDE:
            fs.transfer_yap('elde', KART_HESABI, tutar, tarih, s['aciklama'], kullanici_id, commit=False)
        elif tur == TUR_NAKIT:
            fs.transfer_yap(KART_HESABI, 'elde', tutar, tarih, s['aciklama'], kullanici_id, commit=False)
        eklenen += 1
        if tur in (TUR_GIDER, TUR_SAHSI):
            anahtar = satici_anahtari(s['aciklama'])
            if anahtar:
                ogrenilen[anahtar] = {'tur': tur, 'kategori_id': int(s['kategori_id']) if s['kategori_id'] else None}
                if tur == TUR_SAHSI:
                    ogrenilen[anahtar]['cari_id'] = int(s['cari_id']) if s.get('cari_id') else None
    hafiza_yaz(ogrenilen)
    db.session.refresh(kart)
    return {'eklenen': eklenen, 'atlanan': atlanan, 'bakiye': Decimal(str(kart.bakiye or 0))}


@finans_bp.route('/kart/kaydet', methods=['POST'])
@login_required
@roles_required('admin')
def kart_ekstre_kaydet():
    f = request.form
    try:
        satirlar = _form_satirlari(f)
        if not satirlar:
            raise FinansHata('Kaydedilecek satır seçilmedi.')
        sonuc = satirlari_kaydet(satirlar, _uid())
        duzeltme = None
        borc_ham = (f.get('ekstre_borc') or '').strip()
        if f.get('duzeltme_kapat') == '1' and borc_ham:
            kart = fs.hesap_getir(KART_HESABI, kilitle=True)
            hedef = -Decimal(borc_ham)
            fark = (hedef - Decimal(str(kart.bakiye or 0))).quantize(Decimal('0.01'))
            if fark != 0:
                kesim = (f.get('ekstre_kesim') or '').strip()
                aciklama = (f.get('duzeltme_aciklama') or '').strip()[:400] or 'Ekstre mutabakat düzeltmesi'
                tarih = _tarih_utc(date.fromisoformat(kesim)) if kesim else datetime.utcnow()
                fs._hareket(kart, 'kart_duzeltme', +1 if fark > 0 else -1, abs(fark), tarih, _uid(),
                            aciklama=f'{aciklama} (ekstre {kesim or "-"})')
                duzeltme = fark
        db.session.commit()
    except FinansHata as e:
        db.session.rollback()
        _hata_flash(e)
        return redirect(url_for('finans.kart_ekstre'))
    except Exception:
        db.session.rollback()
        logger.exception('[KART] ekstre kaydı başarısız')
        flash('Ekstre kaydedilemedi, hiçbir satır yazılmadı.', 'danger')
        return redirect(url_for('finans.kart_ekstre'))
    _log('CREATE', f"Kredi kartı ekstresi yüklendi — {sonuc['eklenen']} satır ({sonuc['atlanan']} mükerrer atlandı)"
                   + (f', düzeltme {duzeltme:+.2f}₺' if duzeltme is not None else ''),
         dosya=(f.get('dosya_adi') or '')[:120])
    mesaj = f"✅ {sonuc['eklenen']} satır yazıldı ({sonuc['atlanan']} zaten kayıtlıydı). "
    if duzeltme is not None:
        mesaj += f'Mutabakat düzeltmesi {duzeltme:+.2f} ₺ yazıldı. '
    mesaj += f'Kart bakiyesi: {fs.hesap_getir(KART_HESABI).bakiye:.2f} ₺.'
    flash(mesaj, 'success')
    return redirect(url_for('finans.kart_ekstre'))


@finans_bp.route('/kart/duzelt', methods=['POST'])
@login_required
@roles_required('admin')
def kart_duzelt():
    """Elle mutabakat düzeltmesi: kart borcunu artır/azalt (ekstreden bağımsız)."""
    try:
        tutar = fs.parse_tutar(request.form.get('tutar'))
        yon = -1 if request.form.get('yon') == 'artir' else +1
        aciklama = (request.form.get('aciklama') or '').strip()[:400]
        if not aciklama:
            raise FinansHata('Düzeltme açıklaması zorunlu (neden düzeltildiği izde kalsın).')
        kart = fs.hesap_getir(KART_HESABI, kilitle=True)
        fs._hareket(kart, 'kart_duzeltme', yon, tutar, fs.parse_tarih(request.form.get('tarih')), _uid(),
                    aciklama=f'Elle düzeltme: {aciklama}')
        db.session.commit()
        _log('UPDATE', f'Kredi kartı elle düzeltme — {"borç artırıldı" if yon < 0 else "borç azaltıldı"} {tutar}₺: {aciklama}')
        flash(f'✅ Düzeltme yazıldı, kart bakiyesi {kart.bakiye:.2f} ₺.', 'success')
    except FinansHata as e:
        db.session.rollback()
        _hata_flash(e)
    return redirect(url_for('finans.kart_ekstre'))
