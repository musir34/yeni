from flask import Blueprint, render_template, session, redirect, url_for, flash

gizli_ozellikler_bp = Blueprint('gizli_ozellikler', __name__)


@gizli_ozellikler_bp.route('/gizli-ozellikler')
def index():
    if session.get('role') != 'admin':
        flash('Bu sayfaya erişim yetkiniz yok.', 'warning')
        return redirect(url_for('home.home'))

    ozellikler = [
        {
            'ad': 'Tab ile Otomatik Barkod Doldurma',
            'sayfa': 'Sipariş Hazırla',
            'aciklama': 'Sipariş hazırlama ekranında Tab tuşuna basarak tüm barkod alanlarını otomatik olarak doğru değerlerle doldurur.',
            'kisayol': 'Tab',
            'rol': 'Admin',
            'ikon': 'fa-barcode',
        },
        {
            'ad': 'Kargo Numarası Otomatik Panoya Kopyalama',
            'sayfa': 'Sipariş Hazırla',
            'aciklama': 'Otomatik gönderim aktifken barkodlar onaylandığında kargo numarası (728...) otomatik olarak panoya kopyalanır.',
            'kisayol': 'Otomatik',
            'rol': 'Herkes',
            'ikon': 'fa-clipboard',
        },
    ]

    return render_template('gizli_ozellikler.html', ozellikler=ozellikler)
