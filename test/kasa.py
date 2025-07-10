from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models import db, Kasa, User, KasaKategori
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, desc, func, extract
from login_logout import login_required, roles_required
import json

kasa_bp = Blueprint('kasa', __name__)

@kasa_bp.route('/kasa')
@login_required
@roles_required('admin')
def kasa_sayfasi():
    """Kasa ana sayfası - Admin yetkisi gerekli"""
    # Filtreleme parametreleri
    baslangic_tarihi = request.args.get('baslangic_tarihi', '')
    bitis_tarihi = request.args.get('bitis_tarihi', '')
    tip = request.args.get('tip', '')
    arama = request.args.get('arama', '')
    
    # Sayfalama parametreleri
    sayfa = request.args.get('sayfa', 1, type=int)
    sayfa_boyutu = 20
    
    # Temel sorgu
    sorgu = Kasa.query.join(User).add_columns(
        Kasa.id,
        Kasa.tip,
        Kasa.aciklama,
        Kasa.tutar,
        Kasa.tarih,
        Kasa.kategori,
        User.first_name,
        User.last_name
    )
    
    # Filtreleme
    if baslangic_tarihi:
        try:
            baslangic = datetime.strptime(baslangic_tarihi, '%Y-%m-%d')
            sorgu = sorgu.filter(Kasa.tarih >= baslangic)
        except ValueError:
            pass
    
    if bitis_tarihi:
        try:
            bitis = datetime.strptime(bitis_tarihi, '%Y-%m-%d')
            # Gün sonuna kadar dahil etmek için
            bitis = bitis + timedelta(days=1)
            sorgu = sorgu.filter(Kasa.tarih < bitis)
        except ValueError:
            pass
    
    if tip:
        sorgu = sorgu.filter(Kasa.tip == tip)
    
    if arama:
        sorgu = sorgu.filter(
            or_(
                Kasa.aciklama.contains(arama),
                Kasa.kategori.contains(arama),
                User.first_name.contains(arama),
                User.last_name.contains(arama)
            )
        )
    
    # Sıralama (en yeni önce)
    sorgu = sorgu.order_by(desc(Kasa.tarih))
    
    # Sayfalama
    toplam_kayit = sorgu.count()
    kayitlar = sorgu.offset((sayfa - 1) * sayfa_boyutu).limit(sayfa_boyutu).all()
    
    # Özet istatistikler
    toplam_gelir = db.session.query(func.sum(Kasa.tutar)).filter(Kasa.tip == 'gelir').scalar() or 0
    toplam_gider = db.session.query(func.sum(Kasa.tutar)).filter(Kasa.tip == 'gider').scalar() or 0
    net_durum = toplam_gelir - toplam_gider
    
    # Sayfalama bilgisi
    toplam_sayfa = (toplam_kayit + sayfa_boyutu - 1) // sayfa_boyutu
    
    return render_template('kasa.html', 
                         kayitlar=kayitlar,
                         toplam_gelir=toplam_gelir,
                         toplam_gider=toplam_gider,
                         net_durum=net_durum,
                         sayfa=sayfa,
                         toplam_sayfa=toplam_sayfa,
                         toplam_kayit=toplam_kayit,
                         baslangic_tarihi=baslangic_tarihi,
                         bitis_tarihi=bitis_tarihi,
                         tip=tip,
                         arama=arama)

@kasa_bp.route('/kasa/yeni', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def yeni_kasa_kaydi():
    """Yeni kasa kaydı ekleme"""
    if request.method == 'POST':
        tip = request.form.get('tip')
        aciklama = request.form.get('aciklama')
        tutar = request.form.get('tutar')
        kategori = request.form.get('kategori', '')
        
        # Validasyon
        if not tip or not aciklama or not tutar:
            flash('Tüm alanları doldurmanız gerekiyor!', 'error')
            return redirect(url_for('kasa.yeni_kasa_kaydi'))
        
        try:
            tutar = float(tutar)
            if tutar <= 0:
                flash('Tutar 0\'dan büyük olmalıdır!', 'error')
                return redirect(url_for('kasa.yeni_kasa_kaydi'))
        except ValueError:
            flash('Geçersiz tutar formatı!', 'error')
            return redirect(url_for('kasa.yeni_kasa_kaydi'))
        
        # Kayıt oluştur
        yeni_kayit = Kasa(
            tip=tip,
            aciklama=aciklama,
            tutar=tutar,
            kategori=kategori if kategori else None,
            kullanici_id=session['user_id']
        )
        
        try:
            db.session.add(yeni_kayit)
            db.session.commit()
            flash(f'{tip.title()} kaydı başarıyla eklendi!', 'success')
            return redirect(url_for('kasa.kasa_sayfasi'))
        except Exception as e:
            db.session.rollback()
            flash('Kayıt eklenirken bir hata oluştu!', 'error')
            return redirect(url_for('kasa.yeni_kasa_kaydi'))
    
    # Kategorileri al
    kategoriler = KasaKategori.query.filter_by(aktif=True).order_by(KasaKategori.kategori_adi).all()
    return render_template('kasa_yeni.html', kategoriler=kategoriler)

@kasa_bp.route('/kasa/duzenle/<int:kayit_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def kasa_duzenle(kayit_id):
    """Kasa kaydını düzenleme"""
    kayit = Kasa.query.get_or_404(kayit_id)
    
    if request.method == 'POST':
        tip = request.form.get('tip')
        aciklama = request.form.get('aciklama')
        tutar = request.form.get('tutar')
        kategori = request.form.get('kategori', '')
        
        # Validasyon
        if not tip or not aciklama or not tutar:
            flash('Tüm alanları doldurmanız gerekiyor!', 'error')
            return redirect(url_for('kasa.kasa_duzenle', kayit_id=kayit_id))
        
        try:
            tutar = float(tutar)
            if tutar <= 0:
                flash('Tutar 0\'dan büyük olmalıdır!', 'error')
                return redirect(url_for('kasa.kasa_duzenle', kayit_id=kayit_id))
        except ValueError:
            flash('Geçersiz tutar formatı!', 'error')
            return redirect(url_for('kasa.kasa_duzenle', kayit_id=kayit_id))
        
        # Kayıt güncelle
        kayit.tip = tip
        kayit.aciklama = aciklama
        kayit.tutar = tutar
        kayit.kategori = kategori if kategori else None
        
        try:
            db.session.commit()
            flash('Kayıt başarıyla güncellendi!', 'success')
            return redirect(url_for('kasa.kasa_sayfasi'))
        except Exception as e:
            db.session.rollback()
            flash('Kayıt güncellenirken bir hata oluştu!', 'error')
    
    # Kategorileri al
    kategoriler = KasaKategori.query.filter_by(aktif=True).order_by(KasaKategori.kategori_adi).all()
    return render_template('kasa_duzenle.html', kayit=kayit, kategoriler=kategoriler)

@kasa_bp.route('/kasa/sil/<int:kayit_id>', methods=['POST'])
@login_required
@roles_required('admin')
def kasa_sil(kayit_id):
    """Kasa kaydını silme"""
    kayit = Kasa.query.get_or_404(kayit_id)
    
    try:
        db.session.delete(kayit)
        db.session.commit()
        flash('Kayıt başarıyla silindi!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Kayıt silinirken bir hata oluştu!', 'error')
    
    return redirect(url_for('kasa.kasa_sayfasi'))

@kasa_bp.route('/kasa/rapor')
@login_required
@roles_required('admin')
def kasa_rapor():
    """Kasa raporu - Aylık/Yıllık istatistikler"""
    
    # Bu ayın istatistikleri
    bu_ay_baslangic = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    bu_ay_gelir = db.session.query(func.sum(Kasa.tutar)).filter(
        and_(Kasa.tip == 'gelir', Kasa.tarih >= bu_ay_baslangic)
    ).scalar() or 0
    
    bu_ay_gider = db.session.query(func.sum(Kasa.tutar)).filter(
        and_(Kasa.tip == 'gider', Kasa.tarih >= bu_ay_baslangic)
    ).scalar() or 0
    
    # Geçen ayın istatistikleri
    gecen_ay_baslangic = (bu_ay_baslangic - timedelta(days=1)).replace(day=1)
    gecen_ay_bitis = bu_ay_baslangic
    
    gecen_ay_gelir = db.session.query(func.sum(Kasa.tutar)).filter(
        and_(Kasa.tip == 'gelir', Kasa.tarih >= gecen_ay_baslangic, Kasa.tarih < gecen_ay_bitis)
    ).scalar() or 0
    
    gecen_ay_gider = db.session.query(func.sum(Kasa.tutar)).filter(
        and_(Kasa.tip == 'gider', Kasa.tarih >= gecen_ay_baslangic, Kasa.tarih < gecen_ay_bitis)
    ).scalar() or 0
    
    # Kategori bazlı raporlar
    kategori_rapor = db.session.query(
        Kasa.kategori,
        Kasa.tip,
        func.sum(Kasa.tutar).label('toplam'),
        func.count(Kasa.id).label('adet')
    ).filter(
        Kasa.tarih >= bu_ay_baslangic
    ).group_by(Kasa.kategori, Kasa.tip).all()
    
    return render_template('kasa_rapor.html',
                         bu_ay_gelir=bu_ay_gelir,
                         bu_ay_gider=bu_ay_gider,
                         gecen_ay_gelir=gecen_ay_gelir,
                         gecen_ay_gider=gecen_ay_gider,
                         kategori_rapor=kategori_rapor)

@kasa_bp.route('/kasa/api/ozet')
@login_required
@roles_required('admin')
def kasa_ozet_api():
    """Kasa özeti API - AJAX istekleri için"""
    baslangic = request.args.get('baslangic', '')
    bitis = request.args.get('bitis', '')
    
    sorgu = Kasa.query
    
    if baslangic:
        try:
            baslangic_tarihi = datetime.strptime(baslangic, '%Y-%m-%d')
            sorgu = sorgu.filter(Kasa.tarih >= baslangic_tarihi)
        except ValueError:
            pass
    
    if bitis:
        try:
            bitis_tarihi = datetime.strptime(bitis, '%Y-%m-%d') + timedelta(days=1)
            sorgu = sorgu.filter(Kasa.tarih < bitis_tarihi)
        except ValueError:
            pass
    
    gelir_toplam = sorgu.filter(Kasa.tip == 'gelir').with_entities(func.sum(Kasa.tutar)).scalar() or 0
    gider_toplam = sorgu.filter(Kasa.tip == 'gider').with_entities(func.sum(Kasa.tutar)).scalar() or 0
    
    return jsonify({
        'toplam_gelir': gelir_toplam,
        'toplam_gider': gider_toplam,
        'net_durum': gelir_toplam - gider_toplam
    })

# Kategori Yönetimi Rotaları
@kasa_bp.route('/kasa/kategoriler')
@login_required
@roles_required('admin')
def kategoriler():
    """Kategori listesi"""
    kategoriler = KasaKategori.query.order_by(KasaKategori.kategori_adi).all()
    return render_template('kasa_kategoriler.html', kategoriler=kategoriler)

@kasa_bp.route('/kasa/kategori/yeni', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def yeni_kategori():
    """Yeni kategori ekleme"""
    if request.method == 'POST':
        kategori_adi = request.form.get('kategori_adi')
        aciklama = request.form.get('aciklama', '')
        renk = request.form.get('renk', '#007bff')
        
        if not kategori_adi:
            flash('Kategori adı gereklidir!', 'error')
            return redirect(url_for('kasa.yeni_kategori'))
        
        # Aynı isimde kategori var mı kontrol et
        existing = KasaKategori.query.filter_by(kategori_adi=kategori_adi).first()
        if existing:
            flash('Bu kategori adı zaten kullanılıyor!', 'error')
            return redirect(url_for('kasa.yeni_kategori'))
        
        try:
            yeni_kategori = KasaKategori(
                kategori_adi=kategori_adi,
                aciklama=aciklama,
                renk=renk,
                olusturan_kullanici_id=session['user_id']
            )
            db.session.add(yeni_kategori)
            db.session.commit()
            flash('Kategori başarıyla eklendi!', 'success')
            return redirect(url_for('kasa.kategoriler'))
        except Exception as e:
            db.session.rollback()
            flash('Kategori eklenirken bir hata oluştu!', 'error')
    
    return render_template('kasa_kategori_yeni.html')

@kasa_bp.route('/kasa/kategori/duzenle/<int:kategori_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def kategori_duzenle(kategori_id):
    """Kategori düzenleme"""
    kategori = KasaKategori.query.get_or_404(kategori_id)
    
    if request.method == 'POST':
        kategori_adi = request.form.get('kategori_adi')
        aciklama = request.form.get('aciklama', '')
        renk = request.form.get('renk', '#007bff')
        aktif = request.form.get('aktif') == 'on'
        
        if not kategori_adi:
            flash('Kategori adı gereklidir!', 'error')
            return redirect(url_for('kasa.kategori_duzenle', kategori_id=kategori_id))
        
        # Aynı isimde başka kategori var mı kontrol et
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
            flash('Kategori başarıyla güncellendi!', 'success')
            return redirect(url_for('kasa.kategoriler'))
        except Exception as e:
            db.session.rollback()
            flash('Kategori güncellenirken bir hata oluştu!', 'error')
    
    return render_template('kasa_kategori_duzenle.html', kategori=kategori)

@kasa_bp.route('/kasa/kategori/sil/<int:kategori_id>', methods=['POST'])
@login_required
@roles_required('admin')
def kategori_sil(kategori_id):
    """Kategori silme"""
    kategori = KasaKategori.query.get_or_404(kategori_id)
    
    # Bu kategoriye ait kayıt var mı kontrol et
    kullaniliyor = Kasa.query.filter_by(kategori=kategori.kategori_adi).first()
    if kullaniliyor:
        flash('Bu kategori aktif kayıtlarda kullanılıyor, silinemez!', 'error')
        return redirect(url_for('kasa.kategoriler'))
    
    try:
        db.session.delete(kategori)
        db.session.commit()
        flash('Kategori başarıyla silindi!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Kategori silinirken bir hata oluştu!', 'error')
    
    return redirect(url_for('kasa.kategoriler'))

@kasa_bp.route('/kasa/api/kategori/ekle', methods=['POST'])
@login_required
@roles_required('admin')
def api_kategori_ekle():
    """AJAX ile hızlı kategori ekleme"""
    kategori_adi = request.form.get('kategori_adi')
    if not kategori_adi:
        return jsonify({'success': False, 'message': 'Kategori adı gereklidir!'})
    
    # Aynı isimde kategori var mı kontrol et
    existing = KasaKategori.query.filter_by(kategori_adi=kategori_adi).first()
    if existing:
        return jsonify({'success': False, 'message': 'Bu kategori adı zaten kullanılıyor!'})
    
    try:
        yeni_kategori = KasaKategori(
            kategori_adi=kategori_adi,
            olusturan_kullanici_id=session['user_id']
        )
        db.session.add(yeni_kategori)
        db.session.commit()
        return jsonify({
            'success': True, 
            'message': 'Kategori başarıyla eklendi!',
            'kategori_id': yeni_kategori.id,
            'kategori_adi': yeni_kategori.kategori_adi
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Kategori eklenirken bir hata oluştu!'})