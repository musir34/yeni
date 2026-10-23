"""Çalışan hak edişini kaydet ve isteğe bağlı kısmi ödeme ekle."""
from flask import request, flash, url_for
from login_logout import login_required, roles_required
from finans import finans_bp, _uid, _geri, _log, _hata_flash
import finans_service as fs
import finans_calisan_service as cs


@finans_bp.route('/calisan/hakedis-odeme', methods=['POST'])
@login_required
@roles_required('admin')
def calisan_hakedis_odeme():
    f = request.form
    try:
        h, islem = cs.hakedis_ve_odeme(
            f.get('kalem_id'), f.get('donem'), f.get('hak_tutar'), f.get('tutar'),
            f.get('hesap', ''), fs.parse_tarih(f.get('tarih')), f.get('aciklama', ''),
            _uid(), f.get('odeme_anahtari'), f.get('beklenen_hakedis'))
        kalan = h.tutar - cs.odenen_tutar(h.id)
        _log('CREATE', f'Çalışan hak ediş/ödeme — {h.kalem.ad} {h.donem}', hakedis_id=h.id)
        mahsup = f.get('hesap') == cs.MAHSUP_HESABI and (f.get('tutar') or '').strip()
        fazla = h.tutar - cs._tutar(f.get('hak_tutar'))
        flash(f'✅ {"Hesaba yazma ve hak ediş" if mahsup else ("Ödeme ve hak ediş" if islem else "Hak ediş")} kaydedildi. '
              f'Bu dönem kalan borç: {kalan:.2f} ₺.'
              + (f' Fazla verilen {fazla:.2f} ₺ hak edişe eklendi.' if fazla > 0 else ''), 'success')
    except fs.FinansHata as e:
        _hata_flash(e)
    return _geri(url_for('finans.ana_gider'))


@finans_bp.route('/calisan/mesai', methods=['POST'])
@login_required
@roles_required('admin')
def calisan_mesai():
    f = request.form
    try:
        h = cs.mesai_ekle(f.get('kalem_id'), f.get('donem'), f.get('saat'), f.get('tutar'),
                          fs.parse_tarih(f.get('tarih')), f.get('aciklama', ''), _uid(), f.get('odeme_anahtari'))
        _log('CREATE', f'Çalışan mesai — {h.kalem.ad} {h.donem} {f.get("saat")} saat', hakedis_id=h.id)
        flash(f'✅ Mesai hak edişe eklendi. Bu dönem toplam hak ediş: {h.tutar:.2f} ₺, '
              f'kalan borç: {h.tutar - cs.odenen_tutar(h.id):.2f} ₺.', 'success')
    except fs.FinansHata as e:
        _hata_flash(e)
    return _geri(url_for('finans.ana_gider'))


@finans_bp.route('/calisan/<int:kalem_id>/arsiv', methods=['POST'])
@login_required
@roles_required('admin')
def calisan_arsiv(kalem_id):
    """İşten ayrılan çalışan: plan pasif + cari kapalı tek adımda; arsiv=0 ile geri alınır."""
    arsiv = request.form.get('arsiv', '1') == '1'
    try:
        k = cs.calisan_arsivle(kalem_id, arsiv=arsiv)
        _log('UPDATE', f'Çalışan {"arşivlendi" if arsiv else "arşivden çıkarıldı"} — {k.calisan_cari.ad}', kalem_id=kalem_id)
        flash(f'✅ "{k.calisan_cari.ad}" {"arşivlendi; ödeme planı ve cari hesabı kapatıldı" if arsiv else "arşivden çıkarıldı; plan ve cari hesabı yeniden açıldı"}.', 'success')
    except fs.FinansHata as e:
        _hata_flash(e)
    return _geri(url_for('finans.ana_gider'))
