# finans.py
"""
💰 Finans Kasası — üç hesaplı (Beyazıt / Elde / Banka) yeni kasa.

Mevcut kasa modülünden (kasa.py, /kasa) tamamen bağımsızdır; iş kuralları
finans_service.py'de, tablolar scripts/create_finans_tables.py ile açılır.

Sayfa formları: form-POST + flash + redirect (kasa.py deseni).
Tanım işlemleri (kategori / gider adı): fetch JSON + `X-Requested-With: fetch`
başlığı (siparis_notu.py deseni) — before_request bunu zorlar.
"""
from datetime import datetime
import uuid

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, session, abort)

from login_logout import login_required, roles_required
from user_logs import log_user_action
from time_utils import to_ist
import finans_service as fs
from finans_service import FinansHata

finans_bp = Blueprint('finans', __name__, url_prefix='/finans')


@finans_bp.before_request
def _api_csrf_kalkani():
    if request.path.startswith('/finans/api/') and request.method == 'POST' \
            and request.headers.get('X-Requested-With') != 'fetch':
        abort(403)


@finans_bp.context_processor
def _finans_ctx():
    return {
        'fn_hesaplar': fs.hesaplar(),
        'fn_tur_etiket': fs.ISLEM_TUR_ETIKET,
        'fn_kat_tur_etiket': fs.KATEGORI_TUR_ETIKET,
        'fn_bugun_donem': fs.bugun_donem(),
        'fn_donem_etiket': fs.donem_etiket,
        'fn_donem_kaydir': fs.donem_kaydir,
        'fn_odeme_anahtari': lambda: str(uuid.uuid4()),
    }


def _uid() -> int:
    return int(session['user_id'])


def _geri(varsayilan: str):
    """Formdaki `next` alanına ya da varsayılan sayfaya dön (yalnızca site içi yol)."""
    nxt = request.form.get('next') or request.args.get('next') or ''
    if nxt.startswith('/') and not nxt.startswith('//'):
        return redirect(nxt)
    return redirect(varsayilan)


def _log(action: str, aciklama: str, **ek):
    try:
        log_user_action(action, {"işlem_açıklaması": aciklama, "sayfa": "Finans", **ek})
    except Exception:
        pass


def _bugun_ist() -> str:
    return to_ist(datetime.utcnow()).strftime('%Y-%m-%d')


def _cari_ozet() -> dict:
    import finans_cari_service as cs  # tembel import: finans_cari(.py) bu modülü import ediyor
    return cs.cari_ozet()


# ============================== #
#   PANEL / TRANSFER             #
# ============================== #
@finans_bp.route('/')
@login_required
@roles_required('admin')
def panel():
    from finans_calisan_service import hakedisleri_isle
    hakedisleri_isle()
    donem = fs.bugun_donem()
    return render_template('finans_panel.html',
                           ozet=fs.donem_ozet(donem),
                           son_islemler=fs.son_islemler(15),
                           bugun=_bugun_ist(),
                           tutarsizlik=fs.tutarlilik_kontrol(),
                           cari_ozet=_cari_ozet())


@finans_bp.route('/transfer', methods=['POST'])
@login_required
@roles_required('admin')
def transfer():
    try:
        tutar = fs.parse_tutar(request.form.get('tutar'))
        cikis, giris = fs.transfer_yap(
            request.form.get('kaynak', ''), request.form.get('hedef', ''), tutar,
            fs.parse_tarih(request.form.get('tarih')), request.form.get('aciklama', ''), _uid())
        _log("CREATE", f"Finans transfer — {cikis.hesap.ad} → {giris.hesap.ad}: {tutar}₺",
             tutar=str(tutar))
        flash(f'✅ {cikis.hesap.ad} → {giris.hesap.ad}: {tutar:.2f} ₺ aktarıldı.', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.panel'))


# ============================== #
#   DEFTER / İŞLEM               #
# ============================== #
@finans_bp.route('/defter/<hesap_kodu>')
@login_required
@roles_required('admin')
def defter(hesap_kodu):
    try:
        donem = request.args.get('donem', '').strip() or None
        if donem:
            donem = fs.parse_donem(donem)
        tur = request.args.get('tur', '').strip() or None
        if tur and tur not in fs.ISLEM_TURLERI:
            tur = None
        sayfa = request.args.get('sayfa', 1, type=int)
        hesap, sayfalama = fs.defter(hesap_kodu, donem=donem, tur=tur,
                                     iptal_goster=request.args.get('iptal') == '1', sayfa=sayfa)
    except FinansHata as e:
        flash(str(e), 'danger')
        return redirect(url_for('finans.panel'))
    return render_template('finans_defter.html', hesap=hesap, sayfalama=sayfalama,
                           donem=donem or '', tur=tur or '',
                           iptal_goster=request.args.get('iptal') == '1',
                           gelir_kategorileri=fs.kategoriler('gelir'),
                           kucuk_kategorileri=fs.kategoriler('kucuk_gider'),
                           bugun=_bugun_ist())


@finans_bp.route('/islem/<int:islem_id>/iptal', methods=['POST'])
@login_required
@roles_required('admin')
def islem_iptal(islem_id):
    try:
        bacaklar = fs.islem_iptal(islem_id, _uid(), request.form.get('neden'))
        _log("DELETE", f"Finans işlem iptal — #{islem_id} ({len(bacaklar)} kayıt)", islem_id=islem_id)
        flash(f'✅ İşlem iptal edildi, bakiye geri alındı ({len(bacaklar)} kayıt).', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.panel'))


@finans_bp.route('/islem/<int:islem_id>/meta', methods=['POST'])
@login_required
@roles_required('admin')
def islem_meta(islem_id):
    try:
        fs.islem_meta_guncelle(islem_id, aciklama=request.form.get('aciklama'),
                               kategori_id=request.form.get('kategori_id') or None,
                               gider_adi_id=request.form.get('gider_adi_id') or None)
        _log("UPDATE", f"Finans işlem açıklama/kategori — #{islem_id}", islem_id=islem_id)
        flash('✅ İşlem güncellendi.', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.panel'))


@finans_bp.route('/islem/<int:islem_id>/duzelt', methods=['POST'])
@login_required
@roles_required('admin')
def islem_duzelt(islem_id):
    try:
        tutar_raw = request.form.get('tutar', '').strip()
        tarih_raw = request.form.get('tarih', '').strip()
        yeni = fs.islem_duzelt(
            islem_id, _uid(),
            yeni_tutar=fs.parse_tutar(tutar_raw) if tutar_raw else None,
            yeni_hesap_kodu=request.form.get('hesap') or None,
            yeni_tarih=fs.parse_tarih(tarih_raw) if tarih_raw else None)
        _log("UPDATE", f"Finans işlem düzeltildi — #{islem_id} → #{yeni.id}", islem_id=islem_id)
        flash(f'✅ İşlem düzeltildi (eski kayıt iptal, yeni kayıt #{yeni.id}).', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.panel'))


# ============================== #
#   GELİR                        #
# ============================== #
@finans_bp.route('/gelir')
@login_required
@roles_required('admin')
def gelir():
    try:
        donem = fs.parse_donem(request.args.get('donem'))
    except FinansHata:
        donem = fs.bugun_donem()
    islemler = fs.donem_islemleri(donem, 'gelir')
    return render_template('finans_gelir.html', donem=donem, islemler=islemler,
                           kategoriler=fs.kategoriler('gelir'),
                           toplamlar=fs.kategori_toplamlari(islemler),
                           toplam=sum((i.tutar for i in islemler), 0), bugun=_bugun_ist())


@finans_bp.route('/gelir/ekle', methods=['POST'])
@login_required
@roles_required('admin')
def gelir_ekle():
    try:
        tutar = fs.parse_tutar(request.form.get('tutar'))
        islem = fs.gelir_ekle(request.form.get('kategori_id'), tutar,
                              fs.parse_tarih(request.form.get('tarih')),
                              request.form.get('aciklama', ''), _uid())
        _log("CREATE", f"Finans gelir — {islem.aciklama}: {tutar}₺", tutar=str(tutar))
        flash(f'✅ Gelir eklendi, Beyazıt bakiyesi {islem.yeni_bakiye:.2f} ₺ oldu.', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.gelir'))


# ============================== #
#   KÜÇÜK GİDER                  #
# ============================== #
@finans_bp.route('/kucuk-gider')
@login_required
@roles_required('admin')
def kucuk_gider():
    try:
        donem = fs.parse_donem(request.args.get('donem'))
    except FinansHata:
        donem = fs.bugun_donem()
    hesap_f = request.args.get('hesap', '').strip()
    if hesap_f not in fs.GIDER_HESAPLARI:
        hesap_f = ''
    kat_f = request.args.get('kategori_id', type=int)
    islemler = fs.donem_islemleri(donem, 'kucuk_gider', hesap_kodu=hesap_f or None, kategori_id=kat_f)
    return render_template('finans_kucuk_gider.html', donem=donem, islemler=islemler,
                           kategoriler=fs.kategoriler('kucuk_gider'),
                           toplamlar=fs.kategori_toplamlari(islemler),
                           toplam=sum((i.tutar for i in islemler), 0),
                           hesap_f=hesap_f, kat_f=kat_f, bugun=_bugun_ist())


@finans_bp.route('/kucuk-gider/ekle', methods=['POST'])
@login_required
@roles_required('admin')
def kucuk_gider_ekle():
    try:
        tutar = fs.parse_tutar(request.form.get('tutar'))
        islem = fs.kucuk_gider_ekle(request.form.get('hesap', ''), request.form.get('kategori_id'),
                                    request.form.get('gider_adi_id') or None,
                                    request.form.get('aciklama', ''), tutar,
                                    fs.parse_tarih(request.form.get('tarih')), _uid())
        _log("CREATE", f"Finans küçük gider — {islem.aciklama}: {tutar}₺ ({islem.hesap.ad})", tutar=str(tutar))
        flash(f'✅ Gider kaydedildi, {islem.hesap.ad} bakiyesi {islem.yeni_bakiye:.2f} ₺ oldu.', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.kucuk_gider'))


# ============================== #
#   ANA GİDER                    #
# ============================== #
@finans_bp.route('/ana-gider')
@login_required
@roles_required('admin')
def ana_gider():
    from finans_calisan_service import hakedisleri_isle
    hakedisleri_isle()
    try:
        donem = fs.parse_donem(request.args.get('donem'))
    except FinansHata:
        donem = fs.bugun_donem()
    durum = fs.donem_ana_gider_durumu(donem)
    odenen = sum((d['odenen'] for d in durum), 0)
    bekleyen = sum((d['kalan'] or 0 for d in durum if d['bekleyen']), 0)
    belirsiz_adet = sum(1 for d in durum if d['belirsiz'])
    from models import FinansAnaGiderKalem, FinansCari
    tum_kalemler = FinansAnaGiderKalem.query.order_by(FinansAnaGiderKalem.aktif.desc(),
                                                      FinansAnaGiderKalem.sira,
                                                      FinansAnaGiderKalem.ad).all()
    return render_template('finans_ana_gider.html', donem=donem, durum=durum,
                           odenen=odenen, bekleyen=bekleyen, tum_kalemler=tum_kalemler,
                           kategoriler=fs.kategoriler('ana_gider'), bugun=_bugun_ist(),
                           belirsiz_adet=belirsiz_adet,
                           calisan_cariler=FinansCari.query.filter_by(tur='calisan', aktif=True).order_by(FinansCari.ad).all())


@finans_bp.route('/ana-gider/ode', methods=['POST'])
@login_required
@roles_required('admin')
def ana_gider_ode():
    donem = request.form.get('donem', '')
    try:
        donem = fs.parse_odeme_donemi(donem)
        tutar = fs.parse_tutar(request.form.get('tutar'))
        islem = fs.ana_gider_ode(request.form.get('kalem_id'), donem, request.form.get('hesap', ''),
                                 tutar, fs.parse_tarih(request.form.get('tarih')),
                                 request.form.get('aciklama', ''), _uid())
        _log("CREATE", f"Finans ana gider ödendi — {islem.aciklama}: {tutar}₺ ({islem.hesap.ad})", tutar=str(tutar))
        flash(f'✅ {islem.kalem.ad} ödendi, {islem.hesap.ad} bakiyesi {islem.yeni_bakiye:.2f} ₺ oldu.', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.ana_gider', donem=donem[:7] or None))


@finans_bp.route('/ana-gider/kalem/ekle', methods=['POST'])
@login_required
@roles_required('admin')
def kalem_ekle():
    f = request.form
    try:
        kalem = fs.kalem_ekle(f.get('ad'), f.get('kategori_id') or None, f.get('varsayilan_tutar'),
                              f.get('varsayilan_hesap_kodu', ''), f.get('baslangic_donem'),
                              f.get('bitis_donem'), f.get('notlar'), _uid(),
                              siklik=f.get('siklik', 'aylik'), ilk_odeme_tarihi=f.get('ilk_odeme_tarihi'),
                              tutar_degisken=f.get('tutar_degisken') == '1',
                              calisan=f.get('calisan') == '1', calisan_adi=f.get('calisan_adi', ''),
                              calisan_cari_id=f.get('calisan_cari_id') or None)
        _log("CREATE", f"Finans ana gider kalemi — {kalem.ad}")
        flash(f'✅ "{kalem.ad}" kalemi eklendi.', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.ana_gider'))


@finans_bp.route('/ana-gider/kalem/<int:kalem_id>/guncelle', methods=['POST'])
@login_required
@roles_required('admin')
def kalem_guncelle(kalem_id):
    f = request.form
    try:
        kalem = fs.kalem_guncelle(kalem_id, f.get('ad'), f.get('kategori_id') or None,
                                  f.get('varsayilan_tutar'), f.get('varsayilan_hesap_kodu', ''),
                                  f.get('baslangic_donem'), f.get('bitis_donem'), f.get('notlar'),
                                  siklik=f.get('siklik'), ilk_odeme_tarihi=f.get('ilk_odeme_tarihi'),
                                  tutar_degisken=(f.get('tutar_degisken') == '1'
                                                   if 'tutar_degisken' in f else None),
                                  calisan=(f.get('calisan') == '1' if 'calisan' in f else None),
                                  calisan_adi=f.get('calisan_adi', ''),
                                  calisan_cari_id=f.get('calisan_cari_id') or None, kullanici_id=_uid())
        _log("UPDATE", f"Finans ana gider kalemi güncellendi — {kalem.ad}", kalem_id=kalem_id)
        flash(f'✅ "{kalem.ad}" güncellendi.', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.ana_gider'))


@finans_bp.route('/ana-gider/kalem/<int:kalem_id>/pasif', methods=['POST'])
@login_required
@roles_required('admin')
def kalem_pasif(kalem_id):
    try:
        aktif = request.form.get('aktif') == '1'
        kalem = fs.kalem_pasif(kalem_id, aktif=aktif)
        _log("UPDATE", f"Finans ana gider kalemi {'aktif' if aktif else 'pasif'} — {kalem.ad}", kalem_id=kalem_id)
        flash(f'✅ "{kalem.ad}" {"yeniden aktif" if aktif else "pasife alındı"}.', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.ana_gider'))


# ============================== #
#   TANIMLAR (sayfa + JSON API)  #
# ============================== #
@finans_bp.route('/tanimlar')
@login_required
@roles_required('admin')
def tanimlar():
    kucuk = fs.kategoriler('kucuk_gider', sadece_aktif=False)
    return render_template('finans_tanimlar.html',
                           gelir_kategorileri=fs.kategoriler('gelir', sadece_aktif=False),
                           kucuk_kategorileri=kucuk,
                           gider_adlari={k.id: fs.gider_adlari(k.id, sadece_aktif=False) for k in kucuk},
                           ana_kategorileri=fs.kategoriler('ana_gider', sadece_aktif=False))


def _json_hata(e, kod=400):
    return jsonify(success=False, message=str(e)), kod


@finans_bp.route('/api/kategori', methods=['POST'])
@login_required
@roles_required('admin')
def api_kategori_ekle():
    d = request.get_json(silent=True) or {}
    try:
        kat = fs.kategori_ekle(d.get('tur', ''), d.get('ad', ''), _uid())
        _log("CREATE", f"Finans kategori — {kat.tur}/{kat.ad}")
        return jsonify(success=True, id=kat.id, ad=kat.ad, tur=kat.tur)
    except FinansHata as e:
        return _json_hata(e)


@finans_bp.route('/api/kategori/<int:kategori_id>/sil', methods=['POST'])
@login_required
@roles_required('admin')
def api_kategori_sil(kategori_id):
    try:
        pasif = fs.kategori_sil(kategori_id)
        _log("DELETE", f"Finans kategori {'pasife alındı' if pasif else 'silindi'} — #{kategori_id}")
        return jsonify(success=True, pasif=pasif)
    except FinansHata as e:
        return _json_hata(e)


@finans_bp.route('/api/gider-adi', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def api_gider_adi():
    if request.method == 'GET':
        kat_id = request.args.get('kategori_id', type=int)
        if not kat_id:
            return jsonify(success=True, items=[])
        return jsonify(success=True, items=[
            {'id': g.id, 'ad': g.ad,
             'varsayilan_tutar': (f'{g.varsayilan_tutar:.2f}' if g.varsayilan_tutar is not None else '')}
            for g in fs.gider_adlari(kat_id)])
    d = request.get_json(silent=True) or {}
    try:
        ga = fs.gider_adi_ekle(d.get('kategori_id'), d.get('ad', ''), d.get('varsayilan_tutar'))
        _log("CREATE", f"Finans gider adı — {ga.ad}")
        return jsonify(success=True, id=ga.id, ad=ga.ad,
                       varsayilan_tutar=(f'{ga.varsayilan_tutar:.2f}' if ga.varsayilan_tutar is not None else ''))
    except FinansHata as e:
        return _json_hata(e)


@finans_bp.route('/api/gider-adi/<int:gider_adi_id>/sil', methods=['POST'])
@login_required
@roles_required('admin')
def api_gider_adi_sil(gider_adi_id):
    try:
        pasif = fs.gider_adi_sil(gider_adi_id)
        _log("DELETE", f"Finans gider adı {'pasife alındı' if pasif else 'silindi'} — #{gider_adi_id}")
        return jsonify(success=True, pasif=pasif)
    except FinansHata as e:
        return _json_hata(e)


# ============================== #
#   RAPOR                        #
# ============================== #
@finans_bp.route('/rapor')
@login_required
@roles_required('admin')
def rapor():
    bu_yil = int(fs.bugun_donem()[:4])
    yil = request.args.get('yil', bu_yil, type=int)
    if yil < 2000 or yil > bu_yil + 1:
        yil = bu_yil
    satirlar = fs.yillik_rapor(yil)
    toplam = {k: sum((s[k] for s in satirlar), 0)
              for k in ('gelir', 'cari_tahsilat', 'kucuk_gider', 'ana_gider', 'cari_odeme', 'toplam_gider', 'net')}
    return render_template('finans_rapor.html', yil=yil, bu_yil=bu_yil, satirlar=satirlar,
                           toplam=toplam, tutarsizlik=fs.tutarlilik_kontrol())


# Cari hesap route'ları aynı blueprint'e finans_cari.py'de eklenir (dosya boyutu için ayrı).
import finans_cari  # noqa: E402,F401
import finans_excel  # noqa: E402,F401  — Excel'den gelir yükleme

import finans_calisan  # noqa: E402,F401 — çalışan hak edişi/ödeme route
