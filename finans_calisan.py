"""Çalışan hak edişini kaydet ve isteğe bağlı kısmi ödeme ekle."""
from flask import request, flash, url_for
from login_logout import login_required, roles_required
from finans import finans_bp, _uid, _geri, _log
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
        flash(f'✅ {"Ödeme ve hak ediş" if islem else "Hak ediş"} kaydedildi. '
              f'Bu dönem kalan borç: {kalan:.2f} ₺.', 'success')
    except fs.FinansHata as e:
        flash(str(e), 'danger')
    return _geri(url_for('finans.ana_gider'))
