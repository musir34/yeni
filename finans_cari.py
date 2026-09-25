# finans_cari.py
"""
📒 Finans — Cari hesap route'ları (finans_bp'ye eklenir; finans.py sonunda import edilir).

Sayfalar: /finans/cari (hesap listesi + yeni hesap), /finans/cari/<id> (defter + mal girişi /
ödeme / satış / tahsilat formları). İş kuralları finans_cari_service.py'de.
"""
from flask import render_template, request, redirect, url_for, flash

from login_logout import login_required, roles_required
from finans import finans_bp, _uid, _geri, _log, _bugun_ist
import finans_service as fs
import finans_cari_service as cs
from finans_service import FinansHata


@finans_bp.route('/cari')
@login_required
@roles_required('admin')
def cari_liste():
    from finans_calisan_service import hakedisleri_isle
    hakedisleri_isle()
    return render_template('finans_cari.html', cariler=cs.cariler(sadece_aktif=False),
                           ozet=cs.cari_ozet(), tur_etiket=cs.CARI_TUR_ETIKET,
                           para_etiket=cs.PARA_ETIKET, para_sembol=cs.PARA_SEMBOL,
                           tutarsizlik=cs.cari_tutarlilik_kontrol())


@finans_bp.route('/cari/ekle', methods=['POST'])
@login_required
@roles_required('admin')
def cari_ekle():
    f = request.form
    try:
        c = cs.cari_ekle(f.get('ad'), f.get('tur', 'tedarikci'), f.get('telefon'), f.get('notlar'), _uid(),
                         para_birimi=f.get('para_birimi', 'TRY'))
        _log("CREATE", f"Finans cari hesap açıldı — {c.ad} ({c.para_birimi})")
        flash(f'✅ "{c.ad}" cari hesabı açıldı.', 'success')
        return redirect(url_for('finans.cari_detay', cari_id=c.id))
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.cari_liste'))


@finans_bp.route('/cari/<int:cari_id>/guncelle', methods=['POST'])
@login_required
@roles_required('admin')
def cari_guncelle(cari_id):
    f = request.form
    try:
        c = cs.cari_guncelle(cari_id, f.get('ad'), f.get('tur', 'tedarikci'), f.get('telefon'), f.get('notlar'),
                             para_birimi=f.get('para_birimi'))
        _log("UPDATE", f"Finans cari hesap güncellendi — {c.ad}", cari_id=cari_id)
        flash('✅ Cari hesap güncellendi.', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.cari_detay', cari_id=cari_id))


@finans_bp.route('/cari/<int:cari_id>/pasif', methods=['POST'])
@login_required
@roles_required('admin')
def cari_pasif(cari_id):
    try:
        aktif = request.form.get('aktif') == '1'
        c = cs.cari_pasif(cari_id, aktif=aktif)
        _log("UPDATE", f"Finans cari hesap {'açıldı' if aktif else 'kapatıldı'} — {c.ad}", cari_id=cari_id)
        flash(f'✅ "{c.ad}" {"yeniden açıldı" if aktif else "kapatıldı"}.', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.cari_liste'))


@finans_bp.route('/cari/<int:cari_id>')
@login_required
@roles_required('admin')
def cari_detay(cari_id):
    from finans_calisan_service import hakedisleri_isle, hakedis_satirlari
    hakedisleri_isle()
    try:
        cari = cs.cari_getir(cari_id)
    except FinansHata as e:
        flash(str(e), 'danger')
        return redirect(url_for('finans.cari_liste'))
    iptal_goster = request.args.get('iptal') == '1'
    return render_template('finans_cari_detay.html', cari=cari,
                           sayfalama=cs.hareketler(cari_id, iptal_goster=iptal_goster,
                                                   sayfa=request.args.get('sayfa', 1, type=int)),
                           iptal_goster=iptal_goster, tur_etiket=cs.CARI_TUR_ETIKET,
                           para_etiket=cs.PARA_ETIKET, sembol=cs.sembol(cari),
                           hareket_var=cari.hareketler.first() is not None,  # iptaller dahil (servis kilidiyle aynı)
                           hareket_etiket=cs.HAREKET_ETIKET, bugun=_bugun_ist(),
                           calisan_haklari=hakedis_satirlari(cari_id=cari_id) if cari.tur == 'calisan' else [])


def _kalemler_from_form():
    f = request.form
    return cs.parse_kalemler(f.getlist('kalem_ad'), f.getlist('kalem_adet'), f.getlist('kalem_fiyat'))


def _kur_from_form():
    """USD caride zorunlu (servis denetler); TL caride alan gelmez/boştur → None."""
    raw = request.form.get('kur', '')
    return cs.parse_kur(raw) if str(raw).strip() else None


def _kasa_eki(h) -> str:
    """Dolar hareketinde flash'a kasaya yazılan TL karşılığını ekler."""
    return f' (= {h.islem.tutar:.2f} ₺, kur {h.kur:.4f})' if h.kur else ''


@finans_bp.route('/cari/<int:cari_id>/alim', methods=['POST'])
@login_required
@roles_required('admin')
def cari_alim(cari_id):
    try:
        h = cs.mal_girisi(cari_id, _kalemler_from_form(), fs.parse_tarih(request.form.get('tarih')),
                          request.form.get('aciklama', ''), _uid(), tur='alim')
        s = cs.sembol(h.cari)
        _log("CREATE", f"Finans cari mal girişi — {h.cari.ad}: {h.tutar}{s}", tutar=str(h.tutar))
        flash(f'✅ Mal girişi kaydedildi: {h.tutar:.2f} {s}. Borç bakiyesi {h.yeni_bakiye:.2f} {s}.', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.cari_detay', cari_id=cari_id))


@finans_bp.route('/cari/<int:cari_id>/satis', methods=['POST'])
@login_required
@roles_required('admin')
def cari_satis(cari_id):
    try:
        h = cs.mal_girisi(cari_id, _kalemler_from_form(), fs.parse_tarih(request.form.get('tarih')),
                          request.form.get('aciklama', ''), _uid(), tur='satis')
        s = cs.sembol(h.cari)
        _log("CREATE", f"Finans cari satış — {h.cari.ad}: {h.tutar}{s}", tutar=str(h.tutar))
        flash(f'✅ Satış kaydedildi: {h.tutar:.2f} {s}. Bakiye {h.yeni_bakiye:.2f} {s}.', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.cari_detay', cari_id=cari_id))


@finans_bp.route('/cari/<int:cari_id>/odeme', methods=['POST'])
@login_required
@roles_required('admin')
def cari_odeme(cari_id):
    try:
        tutar = fs.parse_tutar(request.form.get('tutar'))
        h = cs.odeme_yap(cari_id, request.form.get('hesap', ''), tutar,
                         fs.parse_tarih(request.form.get('tarih')), request.form.get('aciklama', ''), _uid(),
                         kur=_kur_from_form())
        s = cs.sembol(h.cari)
        _log("CREATE", f"Finans cari ödeme — {h.cari.ad}: {tutar}{s} ({h.islem.hesap.ad})", tutar=str(tutar))
        flash(f'✅ Ödeme kaydedildi: {tutar:.2f} {s}{_kasa_eki(h)} {h.islem.hesap.ad} hesabından düştü. '
              f'Borç bakiyesi {h.yeni_bakiye:.2f} {s}.', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.cari_detay', cari_id=cari_id))


@finans_bp.route('/cari/<int:cari_id>/tahsilat', methods=['POST'])
@login_required
@roles_required('admin')
def cari_tahsilat(cari_id):
    try:
        tutar = fs.parse_tutar(request.form.get('tutar'))
        h = cs.tahsilat_al(cari_id, tutar, fs.parse_tarih(request.form.get('tarih')),
                           request.form.get('aciklama', ''), _uid(), kur=_kur_from_form())
        s = cs.sembol(h.cari)
        _log("CREATE", f"Finans cari tahsilat — {h.cari.ad}: {tutar}{s}", tutar=str(tutar))
        flash(f'✅ Tahsilat kaydedildi: {tutar:.2f} {s}{_kasa_eki(h)} Beyazıt hesabına girdi. '
              f'Bakiye {h.yeni_bakiye:.2f} {s}.', 'success')
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.cari_detay', cari_id=cari_id))


@finans_bp.route('/cari/hareket/<int:hareket_id>/iptal', methods=['POST'])
@login_required
@roles_required('admin')
def cari_hareket_iptal(hareket_id):
    try:
        h = cs.hareket_iptal(hareket_id, _uid(), request.form.get('neden'))
        _log("DELETE", f"Finans cari hareket iptal — #{hareket_id} ({h.cari.ad})", hareket_id=hareket_id)
        flash('✅ Hareket iptal edildi; bakiye(ler) geri alındı.', 'success')
        return _geri(url_for('finans.cari_detay', cari_id=h.cari_id))
    except FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.cari_liste'))
