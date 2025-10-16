from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app, send_from_directory
from models import db, Kasa, User, KasaKategori, Odeme, KasaDurum
from datetime import datetime, timedelta
from sqlalchemy import or_, desc, func
from login_logout import login_required, roles_required
from werkzeug.utils import secure_filename
import os, uuid, locale
# imports altına ekle
from models import KasaDurum
from decimal import Decimal, InvalidOperation
from sqlalchemy.orm import contains_eager

kasa_bp = Blueprint('kasa', __name__)


def _parse_durum_input(raw: str):
    if not raw:
        return None  # Tümü için None döndür
    s = raw.strip().lower().replace('ö','o')
    if s in ('odenen','tamamlandi'):
        return KasaDurum.TAMAMLANDI
    if s in ('kismi_odendi','kismi odendi','kısmi_ödendi','kısmi odendi'):
        return KasaDurum.KISMI_ODENDI
    if s in ('bekleyen','odenmedi'):
        return KasaDurum.ODENMEDI
    return None

# ============================== #
#   ÖDEME – API (JSON POST)      #
# ============================== #
@kasa_bp.route('/kasa/api/odeme-yap', methods=['POST'])
@login_required
@roles_required('admin')
def api_odeme_yap():
    data = request.json or {}
    kasa_id = data.get('kasa_id')
    odeme_tutari_raw = data.get('odeme_tutari')

    kasa_kaydi = Kasa.query.get(kasa_id)
    if not kasa_kaydi:
        return jsonify({'success': False, 'message': 'Kasa kaydı bulunamadı.'}), 404

    # ---- Decimal parse
    try:
        if isinstance(odeme_tutari_raw, str):
            odeme_tutari_raw = odeme_tutari_raw.replace('.', '').replace(',', '.')
        odeme_tutari = Decimal(str(odeme_tutari_raw))
        if odeme_tutari <= Decimal('0'):
            raise InvalidOperation
    except (InvalidOperation, TypeError):
        return jsonify({'success': False, 'message': 'Geçersiz ödeme tutarı.'}), 400

    # mevcut kalan/ödenen
    toplam_odenen_once = Decimal(db.session.query(func.coalesce(func.sum(Odeme.tutar), 0))
                                 .filter(Odeme.kasa_id == kasa_id).scalar() or 0)
    tutar = Decimal(getattr(kasa_kaydi, 'tutar', 0) or 0)
    kalan_once = tutar - toplam_odenen_once
    if odeme_tutari > kalan_once:
        return jsonify({'success': False, 'message': 'Ödeme tutarı kalan tutardan fazla olamaz.'}), 400

    # ---- ödeme kaydı
    yeni_odeme = Odeme(
        kasa_id=kasa_id,
        tutar=odeme_tutari,
        kullanici_id=session.get('user_id')
    )
    db.session.add(yeni_odeme)

    # ---- durum güncelle
    try:
        db.session.flush()  # id ve tarih için
        toplam_odenen_sonra = toplam_odenen_once + odeme_tutari
        kalan_sonra = tutar - toplam_odenen_sonra

        if kalan_sonra <= Decimal('0'):
            kasa_kaydi.durum = KasaDurum.TAMAMLANDI
        elif toplam_odenen_sonra > Decimal('0'):
            kasa_kaydi.durum = KasaDurum.KISMI_ODENDI
        else:
            kasa_kaydi.durum = KasaDurum.ODENMEDI

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Ödeme kaydedilemedi: {e}'}), 500

    # ---- JSON: gösterilecek alanlar
    durum_text = (
        'Tamamlandı' if kasa_kaydi.durum == KasaDurum.TAMAMLANDI else
        'Kısmi ödendi' if kasa_kaydi.durum == KasaDurum.KISMI_ODENDI else
        'Ödenmedi'
    )

    return jsonify({
        'success': True,
        'message': 'Ödeme başarıyla kaydedildi.',
        'son_odeme': float(odeme_tutari),
        'toplam_odenen': float(toplam_odenen_sonra),
        'kalan_tutar': float(kalan_sonra if kalan_sonra > 0 else Decimal('0')),
        'durum': durum_text,
        'yeni_durum_enum': getattr(kasa_kaydi.durum, 'name', str(kasa_kaydi.durum)),
        'odeme_tarihi': getattr(yeni_odeme, 'odeme_tarihi', datetime.now()).strftime('%d.%m.%Y')
    })


# ============================== #
#   FİLTRE / FORMAT              #
# ============================== #
@kasa_bp.record_once
def setup_kasa_filters(state):
    try:
        locale.setlocale(locale.LC_ALL, 'tr_TR.UTF-8')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_ALL, 'Turkish_Turkey.1254')
        except locale.Error:
            state.app.logger.warning("Türkçe yerel ayar yok; sayı formatı beklenenden farklı olabilir.")
            locale.setlocale(locale.LC_ALL, '')

    def tl_format(value):
        if value is None:
            value = 0.0
        # Türkçe format: 1.000.000,00
        try:
            from decimal import Decimal
            if isinstance(value, Decimal):
                value = float(value)
            # Intl.NumberFormat benzeri Türkçe format
            formatted = "{:,.2f}".format(float(value))
            # Binlik ayırıcıyı nokta, ondalık ayırıcıyı virgül yap
            formatted = formatted.replace(',', 'TEMP').replace('.', ',').replace('TEMP', '.')
            return formatted
        except:
            return "0,00"

    state.app.jinja_env.filters['tl_format'] = tl_format


# ============================== #
#   YARDIMCI                    #
# ============================== #
def month_bounds(yil: int, ay: int):
    bas = datetime(yil, ay, 1)
    son = datetime(yil + 1, 1, 1) if ay == 12 else datetime(yil, ay + 1, 1)
    return bas, son

def allowed_image(filename: str):
    ext = (filename.rsplit('.', 1)[-1] if '.' in filename else '').lower()
    return ext in current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'png', 'jpg', 'jpeg', 'webp', 'heic', 'heif'})


# ============================== #
#   DOSYA SERVİS                #
# ============================== #
@kasa_bp.route('/uploads/receipts/<path:fname>')
@login_required
def serve_receipt(fname):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], fname, as_attachment=False)


# ============================== #
#   KASA – LİSTE / FİLTRE       #
# ============================== #
@kasa_bp.route('/kasa')
@login_required
@roles_required('admin')
def kasa_sayfasi():
    yil = request.args.get('yil', type=int) or datetime.now().year
    ay = request.args.get('ay', type=int) or datetime.now().month
    bas, son = month_bounds(yil, ay)

    baslangic_tarihi = request.args.get('baslangic_tarihi', '')
    bitis_tarihi = request.args.get('bitis_tarihi', '')
    tip = request.args.get('tip', '')
    arama = request.args.get('arama', '')
    durum = request.args.get('durum', '')

    # 🔧 Sadece Kasa modelini döndür (template: kayit.kalan_tutar vs. çalışsın)
    base = (
        db.session.query(Kasa)
        .select_from(Kasa)
        .join(User, Kasa.kullanici_id == User.id)
        .options(contains_eager(Kasa.kullanici))
        .filter(Kasa.tarih >= bas, Kasa.tarih < son)
    )

    if baslangic_tarihi:
        try:
            bas_f = datetime.strptime(baslangic_tarihi, '%Y-%m-%d')
            base = base.filter(Kasa.tarih >= bas_f)
        except ValueError:
            pass

    if bitis_tarihi:
        try:
            bitis_f = datetime.strptime(bitis_tarihi, '%Y-%m-%d') + timedelta(days=1)
            base = base.filter(Kasa.tarih < bitis_f)
        except ValueError:
            pass

    if tip:
        base = base.filter(Kasa.tip == tip)

    if durum:
        parsed_durum = _parse_durum_input(durum)
        if parsed_durum is not None:
            base = base.filter(Kasa.durum == parsed_durum)

    if arama:
        base = base.filter(or_(
            Kasa.aciklama.ilike(f"%{arama}%"),
            Kasa.kategori.ilike(f"%{arama}%"),
            User.first_name.ilike(f"%{arama}%"),
            User.last_name.ilike(f"%{arama}%"),
        ))

    toplam_kayit = base.count()
    # Tüm kayıtları getir (sayfalama yok)
    kayitlar = (base
                .order_by(desc(Kasa.tarih))
                .all())

    # ÖDENEN – Odeme join'leri
    odenen_gelir = (
        db.session.query(func.sum(Odeme.tutar))
        .select_from(Odeme)
        .join(Kasa, Kasa.id == Odeme.kasa_id)
        .filter(Kasa.tip == 'gelir', Odeme.odeme_tarihi >= bas, Odeme.odeme_tarihi < son)
        .scalar() or 0
    )
    odenen_gider = (
        db.session.query(func.sum(Odeme.tutar))
        .select_from(Odeme)
        .join(Kasa, Kasa.id == Odeme.kasa_id)
        .filter(Kasa.tip == 'gider', Odeme.odeme_tarihi >= bas, Odeme.odeme_tarihi < son)
        .scalar() or 0
    )
    net_durum = odenen_gelir - odenen_gider

    # BEKLEYEN – Enum ile
    bekleyen_gelir = (
        db.session.query(func.sum(Kasa.tutar))
        .filter(Kasa.tarih >= bas, Kasa.tarih < son, Kasa.tip == 'gelir', Kasa.durum == KasaDurum.ODENMEDI)
        .scalar() or 0
    )
    bekleyen_gider = (
        db.session.query(func.sum(Kasa.tutar))
        .filter(Kasa.tarih >= bas, Kasa.tarih < son, Kasa.tip == 'gider', Kasa.durum == KasaDurum.ODENMEDI)
        .scalar() or 0
    )

    net_dahil_bekleyen = (odenen_gelir + bekleyen_gelir) - (odenen_gider + bekleyen_gider)

    return render_template(
        'kasa.html',
        kayitlar=kayitlar,
        toplam_gelir=odenen_gelir,
        toplam_gider=odenen_gider,
        net_durum=net_durum,
        bekleyen_gelir=bekleyen_gelir,
        bekleyen_gider=bekleyen_gider,
        net_dahil_bekleyen=net_dahil_bekleyen,
        toplam_kayit=toplam_kayit,
        baslangic_tarihi=baslangic_tarihi,
        bitis_tarihi=bitis_tarihi,
        tip=tip,
        arama=arama,
        durum=durum,
        yil=yil,
        ay=ay
    )


# ============================== #
#   ANASAYFA ÖZET – API         #
# ============================== #
@kasa_bp.route('/kasa/api/anasayfa-ozet')
@login_required
def anasayfa_ozet_api():
    now = datetime.now()
    yil, ay = now.year, now.month
    bas, son = month_bounds(yil, ay)

    q = db.session.query(func.sum(Kasa.tutar))

    odenen_gelir = q.filter(Kasa.tarih >= bas, Kasa.tarih < son, Kasa.tip == 'gelir', Kasa.durum == 'ödenen').scalar() or 0
    odenen_gider = q.filter(Kasa.tarih >= bas, Kasa.tarih < son, Kasa.tip == 'gider', Kasa.durum == 'ödenen').scalar() or 0
    bekleyen_gelir = q.filter(Kasa.tarih >= bas, Kasa.tarih < son, Kasa.tip == 'gelir', Kasa.durum == 'bekleyen').scalar() or 0
    bekleyen_gider = q.filter(Kasa.tarih >= bas, Kasa.tarih < son, Kasa.tip == 'gider', Kasa.durum == 'bekleyen').scalar() or 0

    return jsonify({
        'odenen_gelir': float(odenen_gelir),
        'odenen_gider': float(odenen_gider),
        'net_odenen': float(odenen_gelir - odenen_gider),
        'bekleyen_gelir': float(bekleyen_gelir),
        'bekleyen_gider': float(bekleyen_gider)
    })


# ============================== #
#   KASA – YENİ KAYIT           #
# ============================== #
@kasa_bp.route('/kasa/yeni', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def yeni_kasa_kaydi():
    if request.method == 'POST':
        tip = request.form.get('tip')
        aciklama = request.form.get('aciklama')
        tutar_str = (request.form.get('tutar') or '0').replace(',', '')
        kategori = request.form.get('kategori', '')

        tarih_str = request.form.get('tarih')
        try:
            # Önce datetime-local formatını dene (YYYY-MM-DDTHH:MM)
            secilen_tarih = datetime.strptime(tarih_str, '%Y-%m-%dT%H:%M')
        except (ValueError, TypeError):
            try:
                # Eski format (sadece tarih) için fallback
                secilen_tarih = datetime.strptime(tarih_str, '%Y-%m-%d')
            except (ValueError, TypeError):
                secilen_tarih = datetime.now()

        durum_raw = request.form.get('durum') or ''
        kayit_durumu = _parse_durum_input(durum_raw)

        if not tip or not aciklama or not tutar_str:
            flash('Tip, Açıklama ve Tutar alanları zorunludur!', 'error')
            return redirect(url_for('kasa.yeni_kasa_kaydi'))

        try:
            tutar = float(tutar_str)
            if tutar <= 0:
                flash('Tutar 0\'dan büyük olmalıdır!', 'error')
                return redirect(url_for('kasa.yeni_kasa_kaydi'))
        except ValueError:
            flash('Geçersiz tutar formatı!', 'error')
            return redirect(url_for('kasa.yeni_kasa_kaydi'))

        fis_yolu = None
        file = request.files.get('fis_foto')
        if file and file.filename and allowed_image(file.filename):
            fname = secure_filename(file.filename)
            ext = fname.rsplit('.', 1)[-1].lower()
            uid = uuid.uuid4().hex
            fname = f"{uid}.{ext}"
            save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], fname)
            file.save(save_path)
            fis_yolu = fname

        yeni_kayit = Kasa(
            tip=tip,
            aciklama=aciklama,
            tutar=tutar,
            kategori=kategori if kategori else None,
            kullanici_id=session.get('user_id'),
            durum=kayit_durumu,
            tarih=secilen_tarih,
            fis_yolu=fis_yolu
        )
        try:
            db.session.add(yeni_kayit)
            db.session.flush()  # ID'yi almak için flush
            
            # Eğer durum "Ödenen" ise, otomatik ödeme kaydı oluştur
            if kayit_durumu == KasaDurum.TAMAMLANDI:
                otomatik_odeme = Odeme(
                    kasa_id=yeni_kayit.id,
                    tutar=Decimal(str(tutar)),
                    odeme_tarihi=secilen_tarih,  # Ekleme tarihi ile aynı
                    kullanici_id=session.get('user_id')
                )
                db.session.add(otomatik_odeme)
            
            db.session.commit()
            flash('Kayıt başarıyla eklendi!', 'success')
            return redirect(url_for('kasa.kasa_sayfasi', yil=secilen_tarih.year, ay=secilen_tarih.month))
        except Exception as e:
            db.session.rollback()
            flash(f'Kayıt eklenirken bir hata oluştu! Detay: {e}', 'error')
            return redirect(url_for('kasa.yeni_kasa_kaydi'))

    kategoriler = KasaKategori.query.filter_by(aktif=True).order_by(KasaKategori.kategori_adi).all()
    # datetime-local format: YYYY-MM-DDTHH:MM
    today_str = datetime.now().strftime('%Y-%m-%dT%H:%M')
    return render_template('kasa_yeni.html', kategoriler=kategoriler, default_tarih=today_str)


# ============================== #
#   KASA – DÜZENLE              #
# ============================== #
@kasa_bp.route('/kasa/duzenle/<int:kayit_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def kasa_duzenle(kayit_id):
    kayit = Kasa.query.get_or_404(kayit_id)
    if request.method == 'POST':
        eski_durum = kayit.durum
        
        kayit.tip = request.form.get('tip')
        kayit.aciklama = request.form.get('aciklama')
        tutar_str = (request.form.get('tutar') or '0').replace(',', '')
        kayit.tutar = float(tutar_str)
        kayit.kategori = request.form.get('kategori', '') or None

        tarih_str = request.form.get('tarih')
        try:
            # Önce datetime-local formatını dene (YYYY-MM-DDTHH:MM)
            secilen_tarih = datetime.strptime(tarih_str, '%Y-%m-%dT%H:%M')
        except (ValueError, TypeError):
            try:
                # Eski format (sadece tarih) için fallback
                secilen_tarih = datetime.strptime(tarih_str, '%Y-%m-%d')
            except (ValueError, TypeError):
                secilen_tarih = kayit.tarih

        kayit.tarih = secilen_tarih

        durum_raw = request.form.get('durum') or getattr(kayit.durum, 'name', '')
        yeni_durum = _parse_durum_input(durum_raw)
        kayit.durum = yeni_durum
        
        # Eğer durum "Bekleyen" -> "Ödenen" değiştirilmişse, otomatik ödeme kaydı oluştur
        if eski_durum != KasaDurum.TAMAMLANDI and yeni_durum == KasaDurum.TAMAMLANDI:
            mevcut_odenen = Decimal(db.session.query(func.coalesce(func.sum(Odeme.tutar), 0))
                                     .filter(Odeme.kasa_id == kayit_id).scalar() or 0)
            kalan = Decimal(str(kayit.tutar)) - mevcut_odenen
            
            if kalan > Decimal('0'):
                # Kalan tutarı tamamla
                otomatik_odeme = Odeme(
                    kasa_id=kayit_id,
                    tutar=kalan,
                    odeme_tarihi=secilen_tarih,
                    kullanici_id=session.get('user_id')
                )
                db.session.add(otomatik_odeme)

        file = request.files.get('fis_foto')
        if file and file.filename and allowed_image(file.filename):
            fname = secure_filename(file.filename)
            ext = fname.rsplit('.', 1)[-1].lower()
            uid = uuid.uuid4().hex
            fname = f"{uid}.{ext}"
            save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], fname)
            file.save(save_path)
            kayit.fis_yolu = fname

        try:
            db.session.commit()
            flash('Kayıt başarıyla güncellendi!', 'success')
            return redirect(url_for('kasa.kasa_sayfasi', yil=secilen_tarih.year, ay=secilen_tarih.month))
        except Exception as e:
            db.session.rollback()
            flash(f'Kayıt güncellenirken bir hata oluştu! Detay: {e}', 'error')

    kategoriler = KasaKategori.query.filter_by(aktif=True).order_by(KasaKategori.kategori_adi).all()
    return render_template('kasa_duzenle.html', kayit=kayit, kategoriler=kategoriler)


# ============================== #
#   KASA – DURUM / SİL          #
# ============================== #
@kasa_bp.route('/kasa/odendi/<int:kayit_id>', methods=['POST'])
@login_required
@roles_required('admin')
def kasa_odendi(kayit_id):
    kayit = Kasa.query.get_or_404(kayit_id)
    kayit.durum = KasaDurum.TAMAMLANDI
    try:
        db.session.commit()
        return redirect(url_for('kasa.kasa_sayfasi', yil=kayit.tarih.year, ay=kayit.tarih.month))
    except Exception as e:
        db.session.rollback()
        flash(f'Güncelleme hatası! Detay: {e}', 'error')
        return redirect(url_for('kasa.kasa_sayfasi', yil=datetime.now().year, ay=datetime.now().month))


@kasa_bp.route('/kasa/sil/<int:kayit_id>', methods=['POST'])
@login_required
@roles_required('admin')
def kasa_sil(kayit_id):
    kayit = Kasa.query.get_or_404(kayit_id)
    y, a = kayit.tarih.year, kayit.tarih.month
    try:
        db.session.delete(kayit)
        db.session.commit()
        flash('Kayıt silindi.', 'success')
    except Exception:
        db.session.rollback()
        flash('Kayıt silinirken hata oluştu!', 'error')
    return redirect(url_for('kasa.kasa_sayfasi', yil=y, ay=a))


# ============================== #
#   KASA – RAPOR                #
# ============================== #
@kasa_bp.route('/kasa/rapor')
@login_required
@roles_required('admin')
def kasa_rapor():
    yil = request.args.get('yil', type=int) or datetime.now().year
    ay = request.args.get('ay', type=int) or datetime.now().month
    bas, son = month_bounds(yil, ay)

    bu_ay_gelir = (
        db.session.query(func.sum(Kasa.tutar))
        .filter(Kasa.tip == 'gelir', Kasa.durum == 'ödenen', Kasa.tarih >= bas, Kasa.tarih < son)
        .scalar() or 0
    )
    bu_ay_gider = (
        db.session.query(func.sum(Kasa.tutar))
        .filter(Kasa.tip == 'gider', Kasa.durum == 'ödenen', Kasa.tarih >= bas, Kasa.tarih < son)
        .scalar() or 0
    )

    kategori_rapor = (
        db.session.query(
            Kasa.kategori, Kasa.tip,
            func.sum(Kasa.tutar).label('toplam'),
            func.count(Kasa.id).label('adet')
        )
        .filter(Kasa.durum == 'ödenen', Kasa.tarih >= bas, Kasa.tarih < son)
        .group_by(Kasa.kategori, Kasa.tip)
        .all()
    )

    return render_template(
        'kasa_rapor.html',
        bu_ay_gelir=bu_ay_gelir,
        bu_ay_gider=bu_ay_gider,
        gecen_ay_gelir=None,
        gecen_ay_gider=None,
        kategori_rapor=kategori_rapor,
        yil=yil,
        ay=ay
    )


# ============================== #
#   KASA – ÖZET API             #
# ============================== #
@kasa_bp.route('/kasa/api/ozet')
@login_required
@roles_required('admin')
def kasa_ozet_api():
    yil = request.args.get('yil', type=int) or datetime.now().year
    ay = request.args.get('ay', type=int) or datetime.now().month
    bas, son = month_bounds(yil, ay)

    gelir_toplam = (
        db.session.query(func.sum(Kasa.tutar))
        .filter(Kasa.tarih >= bas, Kasa.tarih < son, Kasa.tip == 'gelir', Kasa.durum == 'ödenen')
        .scalar() or 0
    )
    gider_toplam = (
        db.session.query(func.sum(Kasa.tutar))
        .filter(Kasa.tarih >= bas, Kasa.tarih < son, Kasa.tip == 'gider', Kasa.durum == 'ödenen')
        .scalar() or 0
    )

    return jsonify({
        'toplam_gelir': float(gelir_toplam),
        'toplam_gider': float(gider_toplam),
        'net_durum': float(gelir_toplam - gider_toplam),
        'yil': yil,
        'ay': ay
    })


# ============================== #
#   KATEGORİ – SAYFALAR         #
# ============================== #
@kasa_bp.route('/kasa/kategoriler')
@login_required
@roles_required('admin')
def kategoriler():
    kategoriler = KasaKategori.query.order_by(KasaKategori.kategori_adi).all()
    return render_template('kasa_kategoriler.html', kategoriler=kategoriler)


@kasa_bp.route('/kasa/kategori/yeni', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def yeni_kategori():
    if request.method == 'POST':
        kategori_adi = request.form.get('kategori_adi')
        aciklama = request.form.get('aciklama', '')
        renk = request.form.get('renk', '#007bff')
        if not kategori_adi:
            flash('Kategori adı gereklidir!', 'error')
            return redirect(url_for('kasa.yeni_kategori'))
        existing = KasaKategori.query.filter_by(kategori_adi=kategori_adi).first()
        if existing:
            flash('Bu kategori adı zaten kullanılıyor!', 'error')
            return redirect(url_for('kasa.yeni_kategori'))
        try:
            yeni_kategori = KasaKategori(
                kategori_adi=kategori_adi,
                aciklama=aciklama,
                renk=renk,
                olusturan_kullanici_id=session.get('user_id')
            )
            db.session.add(yeni_kategori)
            db.session.commit()
            flash('Kategori eklendi!', 'success')
            return redirect(url_for('kasa.kategoriler'))
        except Exception:
            db.session.rollback()
            flash('Kategori eklenirken hata!', 'error')
    return render_template('kasa_kategori_yeni.html')


@kasa_bp.route('/kasa/kategori/duzenle/<int:kategori_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def kategori_duzenle(kategori_id):
    kategori = KasaKategori.query.get_or_404(kategori_id)
    if request.method == 'POST':
        kategori_adi = request.form.get('kategori_adi')
        aciklama = request.form.get('aciklama', '')
        renk = request.form.get('renk', '#007bff')
        aktif = request.form.get('aktif') == 'on'
        if not kategori_adi:
            flash('Kategori adı gereklidir!', 'error')
            return redirect(url_for('kasa.kategori_duzenle', kategori_id=kategori_id))
        existing = KasaKategori.query.filter(
            KasaKategori.kategori_adi == kategori_adi,
            KasaKategori.id != kategori_id
        ).first()
        if existing:
            flash('Bu kategori adı zaten kullanılıyor!', 'error')
            return redirect(url_for('kasa.kategori_duzenle', kategori_id=kategori_id))
        try:
            kategori.kategori_adi = kategori_adi
            kategori.aciklama = aciklama
            kategori.renk = renk
            kategori.aktif = aktif
            db.session.commit()
            flash('Kategori güncellendi!', 'success')
            return redirect(url_for('kasa.kategoriler'))
        except Exception:
            db.session.rollback()
            flash('Kategori güncellenirken hata!', 'error')
    return render_template('kasa_kategori_duzenle.html', kategori=kategori)


@kasa_bp.route('/kasa/kategori/sil/<int:kategori_id>', methods=['POST'])
@login_required
@roles_required('admin')
def kategori_sil(kategori_id):
    kategori = KasaKategori.query.get_or_404(kategori_id)
    kullaniliyor = Kasa.query.filter_by(kategori=kategori.kategori_adi).first()
    if kullaniliyor:
        flash('Bu kategori aktif kayıtlarda kullanılıyor, silinemez!', 'error')
        return redirect(url_for('kasa.kategoriler'))
    try:
        db.session.delete(kategori)
        db.session.commit()
        flash('Kategori silindi!', 'success')
    except Exception:
        db.session.rollback()
        flash('Kategori silinirken hata oluştu!', 'error')
    return redirect(url_for('kasa.kategoriler'))


# ============================== #
#   KATEGORİ – API               #
# ============================== #
@kasa_bp.route('/kasa/api/kategori/ekle', methods=['POST'])
@login_required
@roles_required('admin')
def api_kategori_ekle():
    data = request.get_json(silent=True) or {}
    kategori_adi = data.get('kategori_adi')
    if not kategori_adi:
        return jsonify({'success': False, 'message': 'Kategori adı gereklidir!'}), 400

    existing = KasaKategori.query.filter_by(kategori_adi=kategori_adi).first()
    if existing:
        return jsonify({'success': False, 'message': 'Bu kategori adı zaten kullanılıyor!'}), 400

    try:
        yeni_kategori = KasaKategori(
            kategori_adi=kategori_adi,
            olusturan_kullanici_id=session.get('user_id')
        )
        db.session.add(yeni_kategori)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Kategori başarıyla eklendi!',
            'kategori_id': yeni_kategori.id,
            'kategori_adi': yeni_kategori.kategori_adi
        })
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Kategori eklenirken bir hata oluştu!'}), 500
