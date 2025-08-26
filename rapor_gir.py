import json
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from datetime import datetime
from models import db, Rapor, User
from sqlalchemy import func
from archive import format_turkish_date_filter as _format_tr_date


rapor_gir_bp = Blueprint('rapor_gir', __name__)

@rapor_gir_bp.route('/raporlama', methods=['GET', 'POST'])
@login_required 
def giris():
    if request.method == 'POST':
        kategori = request.form.get('kategori')
        aciklama = request.form.get('aciklama')
        veri_dict = {}

        if not kategori or not aciklama:
            flash('Kategori ve Açıklama alanları zorunludur.', 'danger')
            return redirect(url_for('rapor_gir.giris'))

        if kategori == 'Trendyol - Soru Cevaplama':
            soru_sayisi = request.form.get('cevaplanan_soru_sayisi', '').strip()
            if not soru_sayisi.isdigit() or int(soru_sayisi) == 0:
                flash('Cevaplanan soru sayısı zorunludur.', 'danger')
                return redirect(url_for('rapor_gir.giris'))
            veri_dict['Cevaplanan Soru Sayısı'] = soru_sayisi
            veri_dict['Soru Tipleri'] = request.form.get('soru_tipleri_aciklama', '').strip()

        elif kategori == 'Trendyol - İade Yönetimi':
            iade_sayisi = request.form.get('onaylanan_iade_sayisi', '').strip()
            if not iade_sayisi.isdigit() or int(iade_sayisi) == 0:
                flash('İşlem yapılan iade sayısı zorunludur.', 'danger')
                return redirect(url_for('rapor_gir.giris'))
            veri_dict['İşlem Yapılan İade Sayısı'] = iade_sayisi
            veri_dict['Öne Çıkan İade Sebepleri'] = request.form.get('iade_sebepleri_aciklama', '').strip()

        yeni_rapor = Rapor(
            kullanici_id=current_user.id,
            kategori=kategori,
            aciklama=aciklama,
            veri=veri_dict,
            zaman_damgasi=datetime.utcnow()
        )
        db.session.add(yeni_rapor)
        db.session.commit()
        flash(f'"{kategori}" kategorisindeki raporun başarıyla kaydedildi!', 'success')
        return redirect(url_for('rapor_gir.giris'))

    # --- SAYFA GÖRÜNTÜLEME (GET) ---
    view_mode = 'form'
    view_data = {}

    if current_user.role == 'admin':
        secilen_gun_raw = request.args.get('gun')
        secilen_kullanici_id = request.args.get('kullanici_id')
        secilen_gun = None

        if secilen_gun_raw:
            try:
                secilen_gun = datetime.strptime(secilen_gun_raw, "%Y-%m-%d").date()
            except ValueError:
                flash("Geçersiz tarih formatı.", "danger")
                return redirect(url_for("rapor_gir.giris"))

        if secilen_gun and secilen_kullanici_id:
            view_mode = 'kullanici_detay'
            kullanici = User.query.get_or_404(secilen_kullanici_id)
            raporlar = Rapor.query.filter(
                func.date(Rapor.zaman_damgasi) == secilen_gun,
                Rapor.kullanici_id == secilen_kullanici_id
            ).order_by(Rapor.zaman_damgasi.asc()).all()
            view_data = {'gun': secilen_gun, 'kullanici': kullanici, 'raporlar': raporlar}

        elif secilen_gun:
            view_mode = 'gun_detay'
            kullanicilar = db.session.query(User).join(Rapor).filter(
                func.date(Rapor.zaman_damgasi) == secilen_gun
            ).distinct().all()
            view_data = {'gun': secilen_gun, 'kullanicilar': kullanicilar}

        else:
            view_mode = 'gun_liste'
            gunler = db.session.query(func.date(Rapor.zaman_damgasi).label('gun')).distinct().order_by(
                func.date(Rapor.zaman_damgasi).desc()
            ).all()
            view_data = {'gunler': [g.gun for g in gunler]}

    else:
        view_mode = 'calisan_liste'
        raporlar = Rapor.query.filter_by(kullanici_id=current_user.id).order_by(
            Rapor.zaman_damgasi.desc()
        ).all()
        view_data = {'raporlar': raporlar}

    return render_template('rapor_gir.html', view_mode=view_mode, data=view_data)


# --- Jinja filtre kaydı (rapor_gir_bp tanımından SONRA) ---

@rapor_gir_bp.app_template_filter('turkce_tarih')
def turkce_tarih_filter(value, mode=None):
    """
    Şablonda: {{ r | turkce_tarih('full') }} gibi kullanımlar için.
    archive.format_turkish_date_filter tek param alıyorsa fallback yapar.
    """
    # Önce iki argümanla dene (fonksiyon destekliyorsa)
    if mode is not None:
        try:
            return _format_tr_date(value, mode)  # bazı projelerde iki parametreli olabilir
        except TypeError:
            pass  # tek parametreli ise aşağıdakiye düş

    # Tek argümanlı kullanım
    return _format_tr_date(value)
