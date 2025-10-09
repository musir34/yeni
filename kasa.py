from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app, send_from_directory
from models import db, Kasa, User, KasaKategori
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, desc, func
from login_logout import login_required, roles_required
from werkzeug.utils import secure_filename
import os, uuid, locale

kasa_bp = Blueprint('kasa', __name__)


# =================================================================
# TÜRK LİRASI FORMATI İÇİN ÖZEL FİLTRE TANIMLAMA
# =================================================================
# Bu fonksiyon, Blueprint kaydedildikten sonra çalışır.
@kasa_bp.record_once
def setup_kasa_filters(state):
    # 1. Yerel ayarları Türkçe'ye ayarla
    try:
        # Linux/Mac için daha yaygın
        locale.setlocale(locale.LC_ALL, 'tr_TR.UTF-8') 
    except locale.Error:
        try:
            # Windows için daha yaygın
            locale.setlocale(locale.LC_ALL, 'Turkish_Turkey.1254')
        except locale.Error:
            # Yedek: Eğer yerel ayar desteklenmezse
            state.app.logger.warning("Türkçe yerel ayar (locale) sistemde bulunamadı. Sayı formatı yanlış olabilir.")
            locale.setlocale(locale.LC_ALL, '') 

    def tl_format(value):
        """
        Sayıyı binlik ayraç olarak nokta ve ondalık ayraç olarak virgül kullanarak formatlar.
        Örn: 50000.61 -> 50.000,61
        """
        # None gelirse 0.00 TL olarak göster
        if value is None:
            value = 0.00
        # Para birimi sembolü olmadan formatlama yapıyoruz
        return locale.format_string("%.2f", float(value), grouping=True) 

    # Jinja2 ortamına bu filtreyi ekle
    state.app.jinja_env.filters['tl_format'] = tl_format
# =================================================================

def month_bounds(yil:int, ay:int):
    bas = datetime(yil, ay, 1)
    if ay == 12:
        son = datetime(yil+1, 1, 1)
    else:
        son = datetime(yil, ay+1, 1)
    return bas, son

def allowed_image(filename:str):
    ext = (filename.rsplit('.',1)[-1] if '.' in filename else '').lower()
    return ext in current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'png','jpg','jpeg','webp','heic','heif'})

@kasa_bp.route('/uploads/receipts/<path:fname>')
@login_required
def serve_receipt(fname):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], fname, as_attachment=False)

# kasa.py dosyanın içine yapıştırılacak doğru fonksiyon

# kasa.py dosyasındaki kasa_sayfasi fonksiyonunun güncel hali

@kasa_bp.route('/kasa')
@login_required
@roles_required('admin')
def kasa_sayfasi():
    yil = request.args.get('yil', type=int) or datetime.now().year
    ay  = request.args.get('ay',  type=int) or datetime.now().month
    baslangic_tarihi = request.args.get('baslangic_tarihi', '')
    bitis_tarihi     = request.args.get('bitis_tarihi', '')
    tip              = request.args.get('tip', '')
    arama            = request.args.get('arama', '')
    durum            = request.args.get('durum', '')
    sayfa            = request.args.get('sayfa', 1, type=int)
    sayfa_boyutu     = 20

    sorgu = (Kasa.query
             .join(User)
             .add_columns(
                Kasa.id, Kasa.tip, Kasa.aciklama, Kasa.tutar, Kasa.tarih,
                Kasa.kategori, Kasa.durum, Kasa.ay, Kasa.yil,
                Kasa.fis_yolu,
                User.first_name, User.last_name))

    sorgu = sorgu.filter(Kasa.yil == yil, Kasa.ay == ay)

    if baslangic_tarihi:
        try:
            bas = datetime.strptime(baslangic_tarihi, '%Y-%m-%d')
            sorgu = sorgu.filter(Kasa.tarih >= bas)
        except ValueError: pass
    if bitis_tarihi:
        try:
            bitis = datetime.strptime(bitis_tarihi, '%Y-%m-%d') + timedelta(days=1)
            sorgu = sorgu.filter(Kasa.tarih < bitis)
        except ValueError: pass
    if tip:
        sorgu = sorgu.filter(Kasa.tip == tip)
    if durum:
        sorgu = sorgu.filter(Kasa.durum == durum)
    if arama:
        sorgu = sorgu.filter(or_(
            Kasa.aciklama.ilike(f"%{arama}%"),
            Kasa.kategori.ilike(f"%{arama}%"),
            User.first_name.ilike(f"%{arama}%"),
            User.last_name.ilike(f"%{arama}%"),
        ))

    sorgu = sorgu.order_by(desc(Kasa.tarih))
    toplam_kayit = sorgu.count()
    kayitlar = sorgu.offset((sayfa-1)*sayfa_boyutu).limit(sayfa_boyutu).all()

    # Ödenen toplamlar
    odenen_gelir = db.session.query(func.sum(Kasa.tutar)).filter(Kasa.yil==yil, Kasa.ay==ay, Kasa.tip=='gelir', Kasa.durum=='ödenen').scalar() or 0
    odenen_gider = db.session.query(func.sum(Kasa.tutar)).filter(Kasa.yil==yil, Kasa.ay==ay, Kasa.tip=='gider', Kasa.durum=='ödenen').scalar() or 0
    net_durum = odenen_gelir - odenen_gider
    
    # Bekleyen toplamlar
    bekleyen_gelir = db.session.query(func.sum(Kasa.tutar)).filter(Kasa.yil==yil, Kasa.ay==ay, Kasa.tip=='gelir', Kasa.durum=='bekleyen').scalar() or 0
    bekleyen_gider = db.session.query(func.sum(Kasa.tutar)).filter(Kasa.yil==yil, Kasa.ay==ay, Kasa.tip=='gider', Kasa.durum=='bekleyen').scalar() or 0

    # YENİ EKLENEN HESAPLAMA: Bekleyenler dahil genel net durum
    net_dahil_bekleyen = (odenen_gelir + bekleyen_gelir) - (odenen_gider + bekleyen_gider)

    toplam_sayfa = (toplam_kayit + sayfa_boyutu - 1) // sayfa_boyutu

    # render_template çağrısını yeni değişkenlerle güncelle
    return render_template('kasa.html',
        kayitlar=kayitlar, 
        toplam_gelir=odenen_gelir, 
        toplam_gider=odenen_gider, 
        net_durum=net_durum,
        bekleyen_gelir=bekleyen_gelir,
        bekleyen_gider=bekleyen_gider,
        net_dahil_bekleyen=net_dahil_bekleyen, # <-- YENİ EKLENDİ
        sayfa=sayfa, 
        toplam_sayfa=toplam_sayfa, 
        toplam_kayit=toplam_kayit,
        baslangic_tarihi=baslangic_tarihi, 
        bitis_tarihi=bitis_tarihi,
        tip=tip, 
        arama=arama, 
        durum=durum, 
        yil=yil, 
        ay=ay
    )

### ---- YENİ FONKSİYON: ANASAYFA İÇİN ÖZET BİLGİLER --- ###
@kasa_bp.route('/kasa/api/anasayfa-ozet')
@login_required
def anasayfa_ozet_api():
    """
    Anasayfa için mevcut ayın özetini döner.
    - Ödenen Gelir/Gider
    - Bekleyen Gelir/Gider
    """
    now = datetime.now()
    yil, ay = now.year, now.month

    # Mevcut ay için temel sorgu
    q = db.session.query(func.sum(Kasa.tutar)).filter(Kasa.yil == yil, Kasa.ay == ay)

    # Dört farklı değeri hesapla
    odenen_gelir = q.filter(Kasa.tip == 'gelir', Kasa.durum == 'ödenen').scalar() or 0
    odenen_gider = q.filter(Kasa.tip == 'gider', Kasa.durum == 'ödenen').scalar() or 0
    bekleyen_gelir = q.filter(Kasa.tip == 'gelir', Kasa.durum == 'bekleyen').scalar() or 0
    bekleyen_gider = q.filter(Kasa.tip == 'gider', Kasa.durum == 'bekleyen').scalar() or 0

    return jsonify({
        'odenen_gelir': float(odenen_gelir),
        'odenen_gider': float(odenen_gider),
        'net_odenen': float(odenen_gelir - odenen_gider),
        'bekleyen_gelir': float(bekleyen_gelir),
        'bekleyen_gider': float(bekleyen_gider)
    })
### --------------------------------------------------------- ###


@kasa_bp.route('/kasa/yeni', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def yeni_kasa_kaydi():
    if request.method == 'POST':
        tip = request.form.get('tip')
        aciklama = request.form.get('aciklama')
        tutar = request.form.get('tutar')
        kategori = request.form.get('kategori', '')
        yil = int(request.form.get('yil') or datetime.now().year)
        ay  = int(request.form.get('ay')  or datetime.now().month)
        
        durum_raw = (request.form.get('durum') or '').strip().lower().replace('ö','o')
        if durum_raw not in {'bekleyen','odenen'}:
            durum_raw = 'bekleyen'
        kayit_durumu = 'ödenen' if durum_raw == 'odenen' else 'bekleyen'

        if not tip or not aciklama or not tutar:
            flash('Tüm alanları doldurmanız gerekiyor!', 'error'); return redirect(url_for('kasa.yeni_kasa_kaydi'))
        try:
            tutar = float(tutar)
            if tutar <= 0:
                flash('Tutar 0\'dan büyük olmalıdır!', 'error'); return redirect(url_for('kasa.yeni_kasa_kaydi'))
        except ValueError:
            flash('Geçersiz tutar formatı!', 'error'); return redirect(url_for('kasa.yeni_kasa_kaydi'))
        
        fis_yolu = None
        file = request.files.get('fis_foto')
        if file and file.filename and allowed_image(file.filename):
            fname = secure_filename(file.filename)
            ext = fname.rsplit('.',1)[-1].lower()
            uid = uuid.uuid4().hex
            fname = f"{uid}.{ext}"
            save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], fname)
            file.save(save_path)
            fis_yolu = fname

        yeni_kayit = Kasa(
            tip=tip, aciklama=aciklama, tutar=tutar,
            kategori=kategori if kategori else None,
            kullanici_id=session['user_id'],
            durum=kayit_durumu,
            yil=yil, ay=ay, fis_yolu=fis_yolu
        )
        try:
            db.session.add(yeni_kayit); db.session.commit()
            flash(f'{tip.title()} kaydı eklendi.', 'success'); return redirect(url_for('kasa.kasa_sayfasi', yil=yil, ay=ay))
        except Exception as e:
            db.session.rollback(); flash(f'Kayıt eklenirken bir hata oluştu! Detay: {e}', 'error')
            return redirect(url_for('kasa.yeni_kasa_kaydi'))

    kategoriler = KasaKategori.query.filter_by(aktif=True).order_by(KasaKategori.kategori_adi).all()
    now = datetime.now()
    return render_template('kasa_yeni.html', kategoriler=kategoriler, default_yil=now.year, default_ay=now.month)

@kasa_bp.route('/kasa/duzenle/<int:kayit_id>', methods=['GET','POST'])
@login_required
@roles_required('admin')
def kasa_duzenle(kayit_id):
    kayit = Kasa.query.get_or_404(kayit_id)
    if request.method == 'POST':
        kayit.tip = request.form.get('tip')
        kayit.aciklama = request.form.get('aciklama')
        kayit.tutar = float(request.form.get('tutar') or 0)
        kayit.kategori = request.form.get('kategori', '') or None
        kayit.yil = int(request.form.get('yil') or kayit.yil)
        kayit.ay = int(request.form.get('ay') or kayit.ay)

        durum_raw = (request.form.get('durum') or kayit.durum).strip().lower().replace('ö','o')
        if durum_raw not in {'bekleyen','odenen'}:
            durum_raw = 'bekleyen'
        kayit.durum = 'ödenen' if durum_raw=='odenen' else 'bekleyen'
        
        file = request.files.get('fis_foto')
        if file and file.filename and allowed_image(file.filename):
            fname = secure_filename(file.filename)
            ext = fname.rsplit('.',1)[-1].lower()
            uid = uuid.uuid4().hex
            fname = f"{uid}.{ext}"
            save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], fname)
            file.save(save_path)
            kayit.fis_yolu = fname
        
        try:
            db.session.commit(); flash('Kayıt güncellendi.', 'success')
            return redirect(url_for('kasa.kasa_sayfasi', yil=kayit.yil, ay=kayit.ay))
        except Exception as e:
            db.session.rollback(); flash(f'Kayıt güncellenirken bir hata oluştu! Detay: {e}', 'error')
    
    kategoriler = KasaKategori.query.filter_by(aktif=True).order_by(KasaKategori.kategori_adi).all()
    return render_template('kasa_duzenle.html', kayit=kayit, kategoriler=kategoriler)

@kasa_bp.route('/kasa/odendi/<int:kayit_id>', methods=['POST'])
@login_required
@roles_required('admin')
def kasa_odendi(kayit_id):
    kayit = Kasa.query.get_or_404(kayit_id)
    kayit.durum = 'ödenen'
    try:
        db.session.commit(); flash('Kayıt ödendi olarak işaretlendi.', 'success')
    except Exception as e:
        db.session.rollback(); flash(f'Güncelleme hatası! Detay: {e}', 'error')
    return redirect(url_for('kasa.kasa_sayfasi', yil=kayit.yil, ay=kayit.ay))


@kasa_bp.route('/kasa/sil/<int:kayit_id>', methods=['POST'])
@login_required
@roles_required('admin')
def kasa_sil(kayit_id):
    kayit = Kasa.query.get_or_404(kayit_id)
    yil, ay = kayit.yil, kayit.ay
    try:
        db.session.delete(kayit)
        db.session.commit()
        flash('Kayıt silindi.', 'success')
    except Exception:
        db.session.rollback()
        flash('Kayıt silinirken hata oluştu!', 'error')
    return redirect(url_for('kasa.kasa_sayfasi', yil=yil, ay=ay))

@kasa_bp.route('/kasa/rapor')
@login_required
@roles_required('admin')
def kasa_rapor():
    yil = request.args.get('yil', type=int) or datetime.now().year
    ay  = request.args.get('ay',  type=int) or datetime.now().month
    bas, son = month_bounds(yil, ay)

    # GÜNCELLEME: Raporlar da sadece 'ödenen' kayıtları baz alıyor
    bu_ay_gelir = db.session.query(func.sum(Kasa.tutar)).filter(
        Kasa.tip=='gelir', Kasa.durum=='ödenen', Kasa.tarih>=bas, Kasa.tarih<son
    ).scalar() or 0
    bu_ay_gider = db.session.query(func.sum(Kasa.tutar)).filter(
        Kasa.tip=='gider', Kasa.durum=='ödenen', Kasa.tarih>=bas, Kasa.tarih<son
    ).scalar() or 0

    kategori_rapor = db.session.query(
        Kasa.kategori, Kasa.tip, func.sum(Kasa.tutar).label('toplam'), func.count(Kasa.id).label('adet')
    ).filter(
        Kasa.durum=='ödenen', Kasa.tarih>=bas, Kasa.tarih<son
    ).group_by(Kasa.kategori, Kasa.tip).all()

    return render_template('kasa_rapor.html',
        bu_ay_gelir=bu_ay_gelir,
        bu_ay_gider=bu_ay_gider,
        gecen_ay_gelir=None,
        gecen_ay_gider=None,
        kategori_rapor=kategori_rapor,
        yil=yil, ay=ay
    )

@kasa_bp.route('/kasa/api/ozet')
@login_required
@roles_required('admin')
def kasa_ozet_api():
    yil = request.args.get('yil', type=int) or datetime.now().year
    ay  = request.args.get('ay',  type=int) or datetime.now().month

    # GÜNCELLEME: API özeti de sadece 'ödenen' kayıtları baz alıyor
    gelir_toplam = db.session.query(func.sum(Kasa.tutar)).filter(Kasa.yil==yil, Kasa.ay==ay, Kasa.tip=='gelir', Kasa.durum=='ödenen').scalar() or 0
    gider_toplam = db.session.query(func.sum(Kasa.tutar)).filter(Kasa.yil==yil, Kasa.ay==ay, Kasa.tip=='gider', Kasa.durum=='ödenen').scalar() or 0

    return jsonify({
        'toplam_gelir': float(gelir_toplam),
        'toplam_gider': float(gider_toplam),
        'net_durum': float(gelir_toplam - gider_toplam),
        'yil': yil,
        'ay': ay
    })

# ... (Kategori rotaları aynı kalabilir, onlara dokunmadım) ...
@kasa_bp.route('/kasa/kategoriler')
@login_required
@roles_required('admin')
def kategoriler():
    kategoriler = KasaKategori.query.order_by(KasaKategori.kategori_adi).all()
    return render_template('kasa_kategoriler.html', kategoriler=kategoriler)

@kasa_bp.route('/kasa/kategori/yeni', methods=['GET','POST'])
@login_required
@roles_required('admin')
def yeni_kategori():
    if request.method == 'POST':
        kategori_adi = request.form.get('kategori_adi')
        aciklama = request.form.get('aciklama','')
        renk = request.form.get('renk','#007bff')
        if not kategori_adi:
            flash('Kategori adı gereklidir!', 'error'); return redirect(url_for('kasa.yeni_kategori'))
        existing = KasaKategori.query.filter_by(kategori_adi=kategori_adi).first()
        if existing:
            flash('Bu kategori adı zaten kullanılıyor!', 'error'); return redirect(url_for('kasa.yeni_kategori'))
        try:
            yeni_kategori = KasaKategori(kategori_adi=kategori_adi, aciklama=aciklama, renk=renk, olusturan_kullanici_id=session['user_id'])
            db.session.add(yeni_kategori); db.session.commit()
            flash('Kategori eklendi!', 'success'); return redirect(url_for('kasa.kategoriler'))
        except Exception:
            db.session.rollback(); flash('Kategori eklenirken hata!', 'error')
    return render_template('kasa_kategori_yeni.html')

@kasa_bp.route('/kasa/kategori/duzenle/<int:kategori_id>', methods=['GET','POST'])
@login_required
@roles_required('admin')
def kategori_duzenle(kategori_id):
    kategori = KasaKategori.query.get_or_404(kategori_id)
    if request.method == 'POST':
        kategori_adi = request.form.get('kategori_adi')
        aciklama = request.form.get('aciklama','')
        renk = request.form.get('renk','#007bff')
        aktif = request.form.get('aktif') == 'on'
        if not kategori_adi:
            flash('Kategori adı gereklidir!', 'error'); return redirect(url_for('kasa.kategori_duzenle', kategori_id=kategori_id))
        existing = KasaKategori.query.filter(KasaKategori.kategori_adi==kategori_adi, KasaKategori.id!=kategori_id).first()
        if existing:
            flash('Bu kategori adı zaten kullanılıyor!', 'error'); return redirect(url_for('kasa.kategori_duzenle', kategori_id=kategori_id))
        try:
            kategori.kategori_adi = kategori_adi; kategori.aciklama = aciklama; kategori.renk = renk; kategori.aktif = aktif
            db.session.commit(); flash('Kategori güncellendi!', 'success'); return redirect(url_for('kasa.kategoriler'))
        except Exception:
            db.session.rollback(); flash('Kategori güncellenirken hata!', 'error')
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
        db.session.delete(kategori); db.session.commit(); flash('Kategori silindi!', 'success')
    except Exception:
        db.session.rollback(); flash('Kategori silinirken hata!', 'error')
    return redirect(url_for('kasa.kategoriler'))

@kasa_bp.route('/kasa/api/kategori/ekle', methods=['POST'])
@login_required
@roles_required('admin')
def api_kategori_ekle():
    kategori_adi = request.form.get('kategori_adi')
    if not kategori_adi:
        return jsonify({'success': False, 'message': 'Kategori adı gereklidir!'})
    existing = KasaKategori.query.filter_by(kategori_adi=kategori_adi).first()
    if existing:
        return jsonify({'success': False, 'message': 'Bu kategori adı zaten kullanılıyor!'})
    try:
        yeni_kategori = KasaKategori(kategori_adi=kategori_adi, olusturan_kullanici_id=session['user_id'])
        db.session.add(yeni_kategori); db.session.commit()
        return jsonify({'success': True,'message':'Kategori başarıyla eklendi!','kategori_id':yeni_kategori.id,'kategori_adi':yeni_kategori.kategori_adi})
    except Exception:
        db.session.rollback(); return jsonify({'success': False, 'message': 'Kategori eklenirken bir hata oluştu!'})