from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app, send_from_directory
from models import db, Kasa, User, KasaKategori, Odeme, KasaDurum, AnaKasa, AnaKasaIslem
from datetime import datetime, timedelta
from sqlalchemy import or_, desc, func
from login_logout import login_required, roles_required
from werkzeug.utils import secure_filename
import os, uuid, locale
import pandas as pd
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
    # 🔧 ÖNEMLİ: Ödeme tarihini kasa kaydının tarihi ile eşitle
    yeni_odeme = Odeme(
        kasa_id=kasa_id,
        tutar=odeme_tutari,
        odeme_tarihi=kasa_kaydi.tarih,  # Kasa kaydının tarihini kullan
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
    toplam_yil = request.args.get('toplam_yil', type=int)
    toplam_ay = request.args.get('toplam_ay', type=int)
    bugun = datetime.now()
    ay_filtresi_var = 'ay' in request.args and request.args.get('ay')
    
    yil = request.args.get('yil', type=int)
    ay = request.args.get('ay', type=int)
    baslangic_tarihi = request.args.get('baslangic_tarihi', '')
    bitis_tarihi = request.args.get('bitis_tarihi', '')
    tip = request.args.get('tip', '')
    arama = request.args.get('arama', '')
    durum = request.args.get('durum', '')
    
    sayfa = request.args.get('sayfa', 1, type=int)
    sayfa_basina = request.args.get('adet', 10, type=int)
    if sayfa_basina not in [10, 20, 50]:
        sayfa_basina = 10

    base = (
        db.session.query(Kasa)
        .select_from(Kasa)
        .join(User, Kasa.kullanici_id == User.id)
        .options(contains_eager(Kasa.kullanici))
    )
    
    # Ay/Yıl filtresi - SADECE kullanıcı açıkça filtrelediyse uygula
    if ay_filtresi_var and yil and ay:
        bas, son = month_bounds(yil, ay)
        base = base.filter(Kasa.tarih >= bas, Kasa.tarih < son)

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
    
    if ay_filtresi_var:
        kayitlar = base.order_by(desc(Kasa.tarih)).all()
        toplam_sayfa = 1
        sayfa = 1
    else:
        toplam_sayfa = (toplam_kayit + sayfa_basina - 1) // sayfa_basina
        if toplam_sayfa == 0:
            toplam_sayfa = 1
        offset = (sayfa - 1) * sayfa_basina
        kayitlar = base.order_by(desc(Kasa.tarih)).offset(offset).limit(sayfa_basina).all()

    # 🎯 TOPLAMLAR: Eğer ay filtresi varsa o aya göre, yoksa TÜM ZAMANLAR
    # Bu sayede kullanıcı listedeki kayıtlarla toplamları eşleşir görür
    if ay_filtresi_var and yil and ay:
        # Ay filtresi var - o aya göre hesapla
        toplam_yil = yil
        toplam_ay = ay
        toplam_bas, toplam_son = month_bounds(toplam_yil, toplam_ay)
        toplam_filtre_metni = f"{toplam_ay}. Ay / {toplam_yil}"
        
        # ÖDENEN – Ay filtresine göre
        odenen_gelir_query = (
            db.session.query(func.sum(Odeme.tutar))
            .select_from(Odeme)
            .join(Kasa, Kasa.id == Odeme.kasa_id)
            .filter(Kasa.tip == 'gelir')
            .filter(Odeme.odeme_tarihi >= toplam_bas, Odeme.odeme_tarihi < toplam_son)
        )
        odenen_gelir = odenen_gelir_query.scalar() or 0
        
        odenen_gider_query = (
            db.session.query(func.sum(Odeme.tutar))
            .select_from(Odeme)
            .join(Kasa, Kasa.id == Odeme.kasa_id)
            .filter(Kasa.tip == 'gider')
            .filter(Odeme.odeme_tarihi >= toplam_bas, Odeme.odeme_tarihi < toplam_son)
        )
        odenen_gider = odenen_gider_query.scalar() or 0
        
        # BEKLEYEN – Ay filtresine göre
        # ODENMEDI: Tam tutar bekliyor
        # KISMI_ODENDI: Kalan tutar bekliyor (tutar - ödenen)
        
        # Ödenmemiş kayıtların tam tutarı
        bekleyen_gelir_odenmedi = (
            db.session.query(func.sum(Kasa.tutar))
            .filter(Kasa.tip == 'gelir', Kasa.durum == KasaDurum.ODENMEDI)
            .filter(Kasa.tarih >= toplam_bas, Kasa.tarih < toplam_son)
            .scalar() or 0
        )
        
        # Kısmi ödenen kayıtların kalan tutarı
        kismi_gelir_kayitlar = (
            db.session.query(Kasa.id, Kasa.tutar)
            .filter(Kasa.tip == 'gelir', Kasa.durum == KasaDurum.KISMI_ODENDI)
            .filter(Kasa.tarih >= toplam_bas, Kasa.tarih < toplam_son)
            .all()
        )
        bekleyen_gelir_kismi = 0
        for kasa_id, kasa_tutar in kismi_gelir_kayitlar:
            odenen = db.session.query(func.sum(Odeme.tutar)).filter(Odeme.kasa_id == kasa_id).scalar() or 0
            bekleyen_gelir_kismi += (kasa_tutar - odenen)
        
        bekleyen_gelir = bekleyen_gelir_odenmedi + bekleyen_gelir_kismi
        
        # Gider için aynı mantık
        bekleyen_gider_odenmedi = (
            db.session.query(func.sum(Kasa.tutar))
            .filter(Kasa.tip == 'gider', Kasa.durum == KasaDurum.ODENMEDI)
            .filter(Kasa.tarih >= toplam_bas, Kasa.tarih < toplam_son)
            .scalar() or 0
        )
        
        kismi_gider_kayitlar = (
            db.session.query(Kasa.id, Kasa.tutar)
            .filter(Kasa.tip == 'gider', Kasa.durum == KasaDurum.KISMI_ODENDI)
            .filter(Kasa.tarih >= toplam_bas, Kasa.tarih < toplam_son)
            .all()
        )
        bekleyen_gider_kismi = 0
        for kasa_id, kasa_tutar in kismi_gider_kayitlar:
            odenen = db.session.query(func.sum(Odeme.tutar)).filter(Odeme.kasa_id == kasa_id).scalar() or 0
            bekleyen_gider_kismi += (kasa_tutar - odenen)
        
        bekleyen_gider = bekleyen_gider_odenmedi + bekleyen_gider_kismi
    else:
        # Ay filtresi yok - TÜM ZAMANLAR için hesapla
        toplam_yil = None
        toplam_ay = None
        toplam_filtre_metni = "Tüm Zamanlar"
        
        # ÖDENEN – Tüm zamanlar
        odenen_gelir = (
            db.session.query(func.sum(Odeme.tutar))
            .select_from(Odeme)
            .join(Kasa, Kasa.id == Odeme.kasa_id)
            .filter(Kasa.tip == 'gelir')
            .scalar() or 0
        )
        
        odenen_gider = (
            db.session.query(func.sum(Odeme.tutar))
            .select_from(Odeme)
            .join(Kasa, Kasa.id == Odeme.kasa_id)
            .filter(Kasa.tip == 'gider')
            .scalar() or 0
        )
        
        # BEKLEYEN – Tüm zamanlar
        # ODENMEDI: Tam tutar bekliyor
        # KISMI_ODENDI: Kalan tutar bekliyor (tutar - ödenen)
        
        # Ödenmemiş kayıtların tam tutarı
        bekleyen_gelir_odenmedi = (
            db.session.query(func.sum(Kasa.tutar))
            .filter(Kasa.tip == 'gelir', Kasa.durum == KasaDurum.ODENMEDI)
            .scalar() or 0
        )
        
        # Kısmi ödenen kayıtların kalan tutarı
        kismi_gelir_kayitlar = (
            db.session.query(Kasa.id, Kasa.tutar)
            .filter(Kasa.tip == 'gelir', Kasa.durum == KasaDurum.KISMI_ODENDI)
            .all()
        )
        bekleyen_gelir_kismi = 0
        for kasa_id, kasa_tutar in kismi_gelir_kayitlar:
            odenen = db.session.query(func.sum(Odeme.tutar)).filter(Odeme.kasa_id == kasa_id).scalar() or 0
            bekleyen_gelir_kismi += (kasa_tutar - odenen)
        
        bekleyen_gelir = bekleyen_gelir_odenmedi + bekleyen_gelir_kismi
        
        # Gider için aynı mantık
        bekleyen_gider_odenmedi = (
            db.session.query(func.sum(Kasa.tutar))
            .filter(Kasa.tip == 'gider', Kasa.durum == KasaDurum.ODENMEDI)
            .scalar() or 0
        )
        
        kismi_gider_kayitlar = (
            db.session.query(Kasa.id, Kasa.tutar)
            .filter(Kasa.tip == 'gider', Kasa.durum == KasaDurum.KISMI_ODENDI)
            .all()
        )
        bekleyen_gider_kismi = 0
        for kasa_id, kasa_tutar in kismi_gider_kayitlar:
            odenen = db.session.query(func.sum(Odeme.tutar)).filter(Odeme.kasa_id == kasa_id).scalar() or 0
            bekleyen_gider_kismi += (kasa_tutar - odenen)
        
        bekleyen_gider = bekleyen_gider_odenmedi + bekleyen_gider_kismi
    
    net_durum = odenen_gelir - odenen_gider
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
        yil=yil or '',
        ay=ay or '',
        ay_filtresi_var=ay_filtresi_var,
        # Toplam filtre değerleri
        toplam_yil=toplam_yil,
        toplam_ay=toplam_ay,
        toplam_filtre_metni=toplam_filtre_metni,
        bugun=bugun,
        # Sayfalama
        sayfa=sayfa,
        toplam_sayfa=toplam_sayfa,
        sayfa_basina=sayfa_basina,
        # Ana Kasa
        ana_kasa=AnaKasa.query.first()
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

    # 🔧 ÖDENEN: Odeme tablosundan, odeme_tarihi ile filtrele
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
    
    # 🔧 BEKLEYEN: Kasa tablosundan, Kasa.tarih ile filtrele
    # ODENMEDI: Tam tutar bekliyor
    # KISMI_ODENDI: Kalan tutar bekliyor (tutar - ödenen)
    
    # Gelir bekleyen
    bekleyen_gelir_odenmedi = (
        db.session.query(func.sum(Kasa.tutar))
        .filter(Kasa.tarih >= bas, Kasa.tarih < son, Kasa.tip == 'gelir', Kasa.durum == KasaDurum.ODENMEDI)
        .scalar() or 0
    )
    kismi_gelir_kayitlar = (
        db.session.query(Kasa.id, Kasa.tutar)
        .filter(Kasa.tarih >= bas, Kasa.tarih < son, Kasa.tip == 'gelir', Kasa.durum == KasaDurum.KISMI_ODENDI)
        .all()
    )
    bekleyen_gelir_kismi = 0
    for kasa_id, kasa_tutar in kismi_gelir_kayitlar:
        odenen = db.session.query(func.sum(Odeme.tutar)).filter(Odeme.kasa_id == kasa_id).scalar() or 0
        bekleyen_gelir_kismi += (kasa_tutar - odenen)
    bekleyen_gelir = bekleyen_gelir_odenmedi + bekleyen_gelir_kismi
    
    # Gider bekleyen
    bekleyen_gider_odenmedi = (
        db.session.query(func.sum(Kasa.tutar))
        .filter(Kasa.tarih >= bas, Kasa.tarih < son, Kasa.tip == 'gider', Kasa.durum == KasaDurum.ODENMEDI)
        .scalar() or 0
    )
    kismi_gider_kayitlar = (
        db.session.query(Kasa.id, Kasa.tutar)
        .filter(Kasa.tarih >= bas, Kasa.tarih < son, Kasa.tip == 'gider', Kasa.durum == KasaDurum.KISMI_ODENDI)
        .all()
    )
    bekleyen_gider_kismi = 0
    for kasa_id, kasa_tutar in kismi_gider_kayitlar:
        odenen = db.session.query(func.sum(Odeme.tutar)).filter(Odeme.kasa_id == kasa_id).scalar() or 0
        bekleyen_gider_kismi += (kasa_tutar - odenen)
    bekleyen_gider = bekleyen_gider_odenmedi + bekleyen_gider_kismi

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
    """Kasa'ya gelir veya gider ekle. Gelir eklendiğinde Ana Kasa'dan düşer."""
    if request.method == 'POST':
        tip = request.form.get('tip')
        aciklama = request.form.get('aciklama')
        tutar_str = (request.form.get('tutar') or '0').replace(',', '')
        kategori = request.form.get('kategori', '')

        tarih_str = request.form.get('tarih')
        try:
            secilen_tarih = datetime.strptime(tarih_str, '%Y-%m-%dT%H:%M')
        except (ValueError, TypeError):
            try:
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

        # Eğer GELİR ekleniyorsa, Ana Kasa'dan düş
        if tip == 'gelir':
            ana_kasa = AnaKasa.query.first()
            if not ana_kasa:
                ana_kasa = AnaKasa(bakiye=0)
                db.session.add(ana_kasa)
                db.session.flush()
            
            # Ana Kasa bakiye kontrolü
            if ana_kasa.bakiye < Decimal(str(tutar)):
                flash(f'Ana Kasa\'da yeterli bakiye yok! Mevcut bakiye: {ana_kasa.bakiye} ₺', 'danger')
                return redirect(url_for('kasa.yeni_kasa_kaydi'))
        
        yeni_kayit = Kasa(
            tip=tip,
            aciklama=aciklama,
            tutar=tutar,
            kategori=kategori if kategori else None,
            kullanici_id=session.get('user_id'),
            durum=kayit_durumu,
            tarih=secilen_tarih,
            fis_yolu=fis_yolu,
            ana_kasadan=(tip == 'gelir')  # Gelir ise True
        )
        
        try:
            db.session.add(yeni_kayit)
            db.session.flush()
            
            # Eğer durum "Ödenen" ise, otomatik ödeme kaydı oluştur
            if kayit_durumu == KasaDurum.TAMAMLANDI:
                otomatik_odeme = Odeme(
                    kasa_id=yeni_kayit.id,
                    tutar=Decimal(str(tutar)),
                    odeme_tarihi=secilen_tarih,
                    kullanici_id=session.get('user_id')
                )
                db.session.add(otomatik_odeme)
            
            # Eğer GELİR ise, Ana Kasa'dan düş ve işlem kaydı tut
            if tip == 'gelir':
                onceki_bakiye = ana_kasa.bakiye
                ana_kasa.bakiye -= Decimal(str(tutar))
                ana_kasa.guncelleme_tarihi = datetime.now()
                
                # Ana Kasa işlem kaydı
                islem = AnaKasaIslem(
                    islem_tipi='normal_kasaya_aktarildi',
                    tutar=Decimal(str(tutar)),
                    aciklama=f"Kasa'ya gelir aktarıldı: {aciklama}",
                    onceki_bakiye=onceki_bakiye,
                    yeni_bakiye=ana_kasa.bakiye,
                    kullanici_id=session.get('user_id'),
                    kasa_id=yeni_kayit.id,
                    tarih=secilen_tarih
                )
                db.session.add(islem)
            
            db.session.commit()
            
            if tip == 'gelir':
                flash(f'✅ Gelir kaydı eklendi ve Ana Kasa\'dan {tutar} ₺ düşüldü!', 'success')
            else:
                flash('✅ Gider kaydı başarıyla eklendi!', 'success')
                
            return redirect(url_for('kasa.kasa_sayfasi', yil=secilen_tarih.year, ay=secilen_tarih.month))
        except Exception as e:
            db.session.rollback()
            flash(f'Kayıt eklenirken bir hata oluştu! Detay: {e}', 'error')
            return redirect(url_for('kasa.yeni_kasa_kaydi'))

    kategoriler = KasaKategori.query.filter_by(aktif=True).order_by(KasaKategori.kategori_adi).all()
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
        # 🔧 ÖNEMLİ: Ödeme tarihi, kaydın güncellenmiş tarihini kullanmalı
        if eski_durum != KasaDurum.TAMAMLANDI and yeni_durum == KasaDurum.TAMAMLANDI:
            mevcut_odenen = Decimal(db.session.query(func.coalesce(func.sum(Odeme.tutar), 0))
                                     .filter(Odeme.kasa_id == kayit_id).scalar() or 0)
            kalan = Decimal(str(kayit.tutar)) - mevcut_odenen
            
            if kalan > Decimal('0'):
                # Kalan tutarı tamamla - ödeme tarihini kaydın tarihi ile eşle
                otomatik_odeme = Odeme(
                    kasa_id=kayit_id,
                    tutar=kalan,
                    odeme_tarihi=secilen_tarih,  # Kaydın güncellenmiş tarihini kullan
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

    # 🔧 ÖDENEN: Odeme tablosundan, odeme_tarihi ile filtrele
    bu_ay_gelir = (
        db.session.query(func.sum(Odeme.tutar))
        .select_from(Odeme)
        .join(Kasa, Kasa.id == Odeme.kasa_id)
        .filter(Kasa.tip == 'gelir', Odeme.odeme_tarihi >= bas, Odeme.odeme_tarihi < son)
        .scalar() or 0
    )
    bu_ay_gider = (
        db.session.query(func.sum(Odeme.tutar))
        .select_from(Odeme)
        .join(Kasa, Kasa.id == Odeme.kasa_id)
        .filter(Kasa.tip == 'gider', Odeme.odeme_tarihi >= bas, Odeme.odeme_tarihi < son)
        .scalar() or 0
    )

    # 🔧 KATEGORİ RAPOR: Odeme tablosundan, odeme_tarihi ile filtrele
    kategori_rapor = (
        db.session.query(
            Kasa.kategori, Kasa.tip,
            func.sum(Odeme.tutar).label('toplam'),
            func.count(Odeme.id).label('adet')
        )
        .select_from(Odeme)
        .join(Kasa, Kasa.id == Odeme.kasa_id)
        .filter(Odeme.odeme_tarihi >= bas, Odeme.odeme_tarihi < son)
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

    # 🔧 ÖDENEN: Odeme tablosundan, odeme_tarihi ile filtrele
    gelir_toplam = (
        db.session.query(func.sum(Odeme.tutar))
        .select_from(Odeme)
        .join(Kasa, Kasa.id == Odeme.kasa_id)
        .filter(Kasa.tip == 'gelir', Odeme.odeme_tarihi >= bas, Odeme.odeme_tarihi < son)
        .scalar() or 0
    )
    gider_toplam = (
        db.session.query(func.sum(Odeme.tutar))
        .select_from(Odeme)
        .join(Kasa, Kasa.id == Odeme.kasa_id)
        .filter(Kasa.tip == 'gider', Odeme.odeme_tarihi >= bas, Odeme.odeme_tarihi < son)
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


# ============================== #
#   EXCEL İLE GELİR EKLEME       #
# ============================== #
@kasa_bp.route('/kasa/excel-yukle', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def excel_gelir_yukle():
    """İşbankası Excel formatında gelir yükleme"""
    if request.method == 'GET':
        return render_template('kasa_excel_yukle.html')
    
    if 'excel_file' not in request.files:
        flash('Lütfen bir Excel dosyası seçin!', 'error')
        return redirect(url_for('kasa.excel_gelir_yukle'))
    
    file = request.files['excel_file']
    
    if file.filename == '':
        flash('Dosya seçilmedi!', 'error')
        return redirect(url_for('kasa.excel_gelir_yukle'))
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        flash('Sadece Excel dosyaları (.xlsx, .xls) kabul edilir!', 'error')
        return redirect(url_for('kasa.excel_gelir_yukle'))
    
    kategori = request.form.get('kategori', 'Banka Geliri')
    
    try:
        df = pd.read_excel(file, header=None)
        
        eklenen_kayit = 0
        atlanan_kayit = 0
        hatalar = []
        
        # Satır 7'den itibaren (index 6) veri başlıyor
        for index, row in df.iterrows():
            try:
                # A sütunu (0): Tarih/Saat - Format: 28/11/2025-12:55:35
                tarih_raw = row.iloc[0] if len(row) > 0 else None
                # D sütunu (3): İşlem Tutarı
                tutar_raw = row.iloc[3] if len(row) > 3 else None
                # I sütunu (8): Açıklama
                aciklama_raw = row.iloc[8] if len(row) > 8 else None
                
                # Tarih kontrolü - boş veya başlık satırı ise atla
                if pd.isna(tarih_raw) or tarih_raw is None:
                    atlanan_kayit += 1
                    continue
                
                # Başlık satırlarını atla (Tarih/Saat, Net Bakiye vb.)
                tarih_str_check = str(tarih_raw).lower()
                if any(x in tarih_str_check for x in ['tarih', 'saat', 'net bakiye', 'hesap', 'türkiye']):
                    atlanan_kayit += 1
                    continue
                
                # Tutar kontrolü - boş ise atla
                if pd.isna(tutar_raw) or tutar_raw is None:
                    atlanan_kayit += 1
                    continue
                
                # Tutarı sayıya çevir
                try:
                    if isinstance(tutar_raw, str):
                        # Türkçe format: 1.234,56 -> 1234.56
                        tutar_str = tutar_raw.replace('.', '').replace(',', '.').strip()
                        tutar = float(tutar_str)
                    else:
                        tutar = float(tutar_raw)
                except (ValueError, TypeError):
                    atlanan_kayit += 1
                    continue
                
                if tutar <= 0:
                    atlanan_kayit += 1
                    continue
                
                # Tarihi parse et - İşbankası formatı: 28/11/2025-12:55:35
                tarih = None
                if isinstance(tarih_raw, datetime):
                    tarih = tarih_raw
                elif isinstance(tarih_raw, str):
                    # İşbankası özel formatları
                    date_formats = [
                        '%d/%m/%Y-%H:%M:%S',  # İşbankası formatı: 28/11/2025-12:55:35
                        '%d/%m/%Y-%H:%M',
                        '%d.%m.%Y-%H:%M:%S',
                        '%d.%m.%Y-%H:%M',
                        '%d/%m/%Y %H:%M:%S',
                        '%d/%m/%Y %H:%M',
                        '%d.%m.%Y %H:%M:%S',
                        '%d.%m.%Y %H:%M',
                        '%Y-%m-%d %H:%M:%S',
                        '%Y-%m-%d',
                        '%d.%m.%Y',
                        '%d/%m/%Y'
                    ]
                    for fmt in date_formats:
                        try:
                            tarih = datetime.strptime(tarih_raw.strip(), fmt)
                            break
                        except ValueError:
                            continue
                    
                    if tarih is None:
                        hatalar.append(f"Satır {index + 1}: Tarih formatı tanınamadı - {tarih_raw}")
                        atlanan_kayit += 1
                        continue
                else:
                    try:
                        tarih = pd.to_datetime(tarih_raw).to_pydatetime()
                    except:
                        hatalar.append(f"Satır {index + 1}: Tarih dönüştürülemedi - {tarih_raw}")
                        atlanan_kayit += 1
                        continue
                
                # Açıklama
                if pd.isna(aciklama_raw) or aciklama_raw is None:
                    aciklama = f"İşbankası geliri - {tarih.strftime('%d.%m.%Y')}"
                else:
                    aciklama = str(aciklama_raw).strip()[:255]  # Max 255 karakter
                
                # Önce Ana Kasa'ya ekle
                ana_kasa = AnaKasa.query.first()
                if not ana_kasa:
                    ana_kasa = AnaKasa(bakiye=Decimal('0'))
                    db.session.add(ana_kasa)
                    db.session.flush()
                
                onceki_bakiye = ana_kasa.bakiye
                ana_kasa.bakiye += Decimal(str(round(tutar, 2)))
                ana_kasa.guncelleme_tarihi = datetime.now()
                
                # Ana Kasa işlemi kaydet
                ana_kasa_islem = AnaKasaIslem(
                    islem_tipi='gelir_eklendi',
                    tutar=Decimal(str(round(tutar, 2))),
                    aciklama=f"Excel geliri: {aciklama}",
                    onceki_bakiye=onceki_bakiye,
                    yeni_bakiye=ana_kasa.bakiye,
                    tarih=tarih,
                    kullanici_id=session.get('user_id')
                )
                db.session.add(ana_kasa_islem)
                
                eklenen_kayit += 1
                
            except Exception as e:
                hatalar.append(f"Satır {index + 1}: {str(e)}")
                atlanan_kayit += 1
                continue
        
        if eklenen_kayit > 0:
            db.session.commit()
            flash(f'✅ {eklenen_kayit} gelir kaydı başarıyla eklendi! ({atlanan_kayit} satır atlandı)', 'success')
        else:
            db.session.rollback()
            flash(f'⚠️ Hiçbir kayıt eklenemedi. {atlanan_kayit} satır atlandı.', 'warning')
        
        if hatalar:
            hata_mesaji = "Hatalar: " + "; ".join(hatalar[:5])
            if len(hatalar) > 5:
                hata_mesaji += f" ... ve {len(hatalar) - 5} hata daha."
            flash(hata_mesaji, 'warning')
        
        return redirect(url_for('kasa.kasa_sayfasi'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Excel dosyası okunurken hata oluştu: {str(e)}', 'error')
        return redirect(url_for('kasa.excel_gelir_yukle'))


@kasa_bp.route('/kasa/api/excel-onizleme', methods=['POST'])
@login_required
@roles_required('admin')
def excel_onizleme():
    """Excel dosyasının önizlemesini göster"""
    if 'excel_file' not in request.files:
        return jsonify({'success': False, 'message': 'Dosya bulunamadı'}), 400
    
    file = request.files['excel_file']
    
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Dosya seçilmedi'}), 400
    
    try:
        df = pd.read_excel(file, header=None)
        
        onizleme = []
        for index, row in df.head(20).iterrows():
            tarih_raw = row.iloc[0] if len(row) > 0 else None
            tutar_raw = row.iloc[3] if len(row) > 3 else None
            aciklama_raw = row.iloc[8] if len(row) > 8 else None
            
            is_header = False
            if not pd.isna(tarih_raw):
                tarih_str_check = str(tarih_raw).lower()
                if any(x in tarih_str_check for x in ['tarih', 'saat', 'net bakiye', 'hesap', 'türkiye', 'işlem saatleri']):
                    is_header = True
            
            # Tarihi formatla - İşbankası formatı: 28/11/2025-12:55:35
            if pd.isna(tarih_raw):
                tarih_str = "-"
            elif isinstance(tarih_raw, datetime):
                tarih_str = tarih_raw.strftime('%d.%m.%Y %H:%M')
            elif isinstance(tarih_raw, str):
                # İşbankası formatını dene
                tarih = None
                date_formats = [
                    '%d/%m/%Y-%H:%M:%S',
                    '%d/%m/%Y-%H:%M',
                    '%d.%m.%Y-%H:%M:%S',
                    '%d.%m.%Y %H:%M:%S',
                ]
                for fmt in date_formats:
                    try:
                        tarih = datetime.strptime(tarih_raw.strip(), fmt)
                        tarih_str = tarih.strftime('%d.%m.%Y %H:%M')
                        break
                    except ValueError:
                        continue
                if tarih is None:
                    tarih_str = str(tarih_raw)
            else:
                try:
                    tarih_str = pd.to_datetime(tarih_raw).strftime('%d.%m.%Y %H:%M')
                except:
                    tarih_str = str(tarih_raw)
            
            # Tutarı formatla
            tutar_num = 0
            if pd.isna(tutar_raw) or tutar_raw is None:
                tutar_str = "-"
            else:
                try:
                    if isinstance(tutar_raw, str):
                        cleaned = tutar_raw.replace('.', '').replace(',', '.').strip()
                        tutar_num = float(cleaned)
                    else:
                        tutar_num = float(tutar_raw)
                    tutar_str = f"{tutar_num:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                except (ValueError, TypeError):
                    tutar_str = str(tutar_raw)
                    tutar_num = 0
                    is_header = True  # Sayıya çevrilemezse başlık
            
            # Açıklama
            aciklama_str = str(aciklama_raw)[:60] if not pd.isna(aciklama_raw) else "-"
            
            # Geçerli mi?
            gecerli = tutar_num > 0 and not is_header and tarih_str != "-"
            
            onizleme.append({
                'satir': index + 1,
                'tarih': tarih_str,
                'tutar': tutar_str,
                'tutar_num': tutar_num,
                'aciklama': aciklama_str,
                'gecerli': gecerli
            })
        
        toplam_satir = len(df)
        
        # Geçerli satır sayısını güvenli hesapla
        gecerli_satir = 0
        for index, row in df.iterrows():
            try:
                tarih_raw = row.iloc[0] if len(row) > 0 else None
                tutar_raw = row.iloc[3] if len(row) > 3 else None
                
                # Boş satır
                if pd.isna(tarih_raw) or pd.isna(tutar_raw):
                    continue
                
                # Başlık satırı kontrolü
                tarih_str_check = str(tarih_raw).lower()
                if any(x in tarih_str_check for x in ['tarih', 'saat', 'net bakiye', 'hesap', 'türkiye']):
                    continue
                
                # Tutarı sayıya çevir
                if isinstance(tutar_raw, str):
                    cleaned = tutar_raw.replace('.', '').replace(',', '.').strip()
                    tutar_num = float(cleaned)
                else:
                    tutar_num = float(tutar_raw) if tutar_raw else 0
                
                if tutar_num > 0:
                    gecerli_satir += 1
            except (ValueError, TypeError):
                continue
        
        return jsonify({
            'success': True,
            'onizleme': onizleme,
            'toplam_satir': toplam_satir,
            'gecerli_satir': gecerli_satir
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Dosya okunurken hata: {str(e)}'}), 400


# ============================== #
#   ANA KASA YÖNETİMİ           #
# ============================== #
@kasa_bp.route('/kasa/ana-kasa')
@login_required
@roles_required('admin')
def ana_kasa():
    """Ana Kasa görüntüleme ve işlem geçmişi sayfası"""
    # Ana Kasa kaydını al veya oluştur
    ana_kasa = AnaKasa.query.first()
    if not ana_kasa:
        ana_kasa = AnaKasa(bakiye=0)
        db.session.add(ana_kasa)
        db.session.commit()
    
    # Filtreleme parametreleri
    yil = request.args.get('yil', type=int)
    ay = request.args.get('ay', type=int)
    islem_tipi_filtre = request.args.get('islem_tipi', '')
    sayfa = request.args.get('sayfa', 1, type=int)
    sayfa_basina = 20
    
    # İşlem geçmişini çek
    query = AnaKasaIslem.query
    
    # Filtreler
    if yil and ay:
        bas, son = month_bounds(yil, ay)
        query = query.filter(AnaKasaIslem.tarih >= bas, AnaKasaIslem.tarih < son)
    
    if islem_tipi_filtre:
        query = query.filter(AnaKasaIslem.islem_tipi == islem_tipi_filtre)
    
    # Sayfalama
    toplam_kayit = query.count()
    toplam_sayfa = (toplam_kayit + sayfa_basina - 1) // sayfa_basina
    if toplam_sayfa == 0:
        toplam_sayfa = 1
    
    offset = (sayfa - 1) * sayfa_basina
    islemler = query.order_by(desc(AnaKasaIslem.tarih)).offset(offset).limit(sayfa_basina).all()
    
    # Bugünün tarihini al
    bugun = datetime.now()
    
    return render_template('ana_kasa.html', 
                         ana_kasa=ana_kasa, 
                         islemler=islemler,
                         toplam_kayit=toplam_kayit,
                         sayfa=sayfa,
                         toplam_sayfa=toplam_sayfa,
                         yil=yil,
                         ay=ay,
                         islem_tipi_filtre=islem_tipi_filtre,
                         bugun=bugun)


@kasa_bp.route('/kasa/ana-kasa/guncelle', methods=['POST'])
@login_required
@roles_required('admin')
def ana_kasa_guncelle():
    """Ana Kasa'ya manuel para ekle - Basitleştirilmiş"""
    try:
        islem_tipi = request.form.get('islem_tipi')
        tutar_raw = request.form.get('tutar', '0')
        aciklama = request.form.get('aciklama', '')
        
        # Sadece ekleme yapabilir
        if islem_tipi != 'ekle':
            flash('Sadece ekleme işlemi yapılabilir!', 'warning')
            return redirect(url_for('kasa.kasa_sayfasi'))
        
        # Tutarı parse et
        if isinstance(tutar_raw, str):
            tutar_raw = tutar_raw.replace('.', '').replace(',', '.')
        tutar = Decimal(str(tutar_raw))
        
        if tutar <= 0:
            flash('Geçersiz tutar!', 'danger')
            return redirect(url_for('kasa.kasa_sayfasi'))
        
        # Ana Kasa kaydını al veya oluştur
        ana_kasa = AnaKasa.query.first()
        if not ana_kasa:
            ana_kasa = AnaKasa(bakiye=Decimal('0'))
            db.session.add(ana_kasa)
            db.session.flush()
        
        onceki_bakiye = ana_kasa.bakiye
        ana_kasa.bakiye += tutar
        ana_kasa.guncelleme_tarihi = datetime.now()
        
        # İşlem kaydı oluştur
        islem = AnaKasaIslem(
            islem_tipi='manuel_ekleme',
            tutar=tutar,
            aciklama=aciklama,
            onceki_bakiye=onceki_bakiye,
            yeni_bakiye=ana_kasa.bakiye,
            kullanici_id=session.get('user_id'),
            tarih=datetime.now()
        )
        db.session.add(islem)
        db.session.commit()
        
        flash(f'✅ {tutar} ₺ Ana Kasa\'ya eklendi. ({aciklama})', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Hata: {str(e)}', 'danger')
    
    return redirect(url_for('kasa.kasa_sayfasi'))


@kasa_bp.route('/kasa/ana-kasa/bakiye', methods=['GET'])
@login_required
@roles_required('admin')
def ana_kasa_bakiye():
    """Ana Kasa bakiyesini JSON olarak döndür"""
    ana_kasa = AnaKasa.query.first()
    if not ana_kasa:
        ana_kasa = AnaKasa(bakiye=Decimal('0'))
        db.session.add(ana_kasa)
        db.session.commit()
    
    return jsonify({
        'success': True,
        'bakiye': float(ana_kasa.bakiye)
    })


@kasa_bp.route('/kasa/ana-kasa/kayit-defteri', methods=['GET'])
@login_required
@roles_required('admin')
def ana_kasa_kayit_defteri():
    """Ana Kasa kayıt defterini görüntüle"""
    ana_kasa = AnaKasa.query.first()
    if not ana_kasa:
        ana_kasa = AnaKasa(bakiye=Decimal('0'))
        db.session.add(ana_kasa)
        db.session.commit()
    
    # Tüm Ana Kasa işlemlerini tarih sırasına göre getir (en yeni en üstte)
    islemler = AnaKasaIslem.query.order_by(AnaKasaIslem.tarih.desc()).all()
    
    return render_template('ana_kasa_kayit_defteri.html', 
                          ana_kasa=ana_kasa,
                          islemler=islemler)


@kasa_bp.route('/kasa/ana-kasa/islem-duzenle', methods=['POST'])
@login_required
@roles_required('admin')
def ana_kasa_islem_duzenle():
    """Ana Kasa işlem kaydını düzenle ve bakiyeyi yeniden hesapla"""
    try:
        islem_id = request.form.get('islem_id')
        yeni_tutar_raw = request.form.get('tutar', '0')
        yeni_aciklama = request.form.get('aciklama', '')
        yeni_tarih_str = request.form.get('tarih', '')
        
        # İşlemi bul
        islem = AnaKasaIslem.query.get_or_404(islem_id)
        
        # Eski tutarı sakla
        eski_tutar = islem.tutar
        
        # Yeni tutarı parse et
        if isinstance(yeni_tutar_raw, str):
            yeni_tutar_raw = yeni_tutar_raw.replace('.', '').replace(',', '.')
        yeni_tutar = Decimal(str(yeni_tutar_raw))
        
        if yeni_tutar <= 0:
            flash('Geçersiz tutar!', 'danger')
            return redirect(url_for('kasa.ana_kasa_kayit_defteri'))
        
        # Tarihi parse et
        try:
            yeni_tarih = datetime.strptime(yeni_tarih_str, '%Y-%m-%dT%H:%M')
        except (ValueError, TypeError):
            yeni_tarih = islem.tarih
        
        # İşlem kaydını güncelle
        islem.tutar = yeni_tutar
        islem.aciklama = yeni_aciklama
        islem.tarih = yeni_tarih
        
        # Bakiyeyi yeniden hesapla
        # Bu işlemden sonraki tüm işlemlerin bakiyelerini güncelle
        ana_kasa = AnaKasa.query.first()
        
        # İşlem tipine göre bakiye farkını hesapla
        tutar_farki = yeni_tutar - eski_tutar
        
        if islem.islem_tipi in ['gelir_eklendi', 'manuel_ekleme']:
            # Artırıcı işlemler
            islem.yeni_bakiye = islem.onceki_bakiye + yeni_tutar
            ana_kasa.bakiye += tutar_farki
        elif islem.islem_tipi == 'normal_kasaya_aktarildi':
            # Azaltıcı işlemler
            islem.yeni_bakiye = islem.onceki_bakiye - yeni_tutar
            ana_kasa.bakiye -= tutar_farki
        
        # Bu işlemden sonraki tüm işlemleri güncelle
        sonraki_islemler = AnaKasaIslem.query.filter(
            AnaKasaIslem.tarih > islem.tarih
        ).order_by(AnaKasaIslem.tarih.asc()).all()
        
        for sonraki in sonraki_islemler:
            onceki = sonraki.onceki_bakiye
            if sonraki.islem_tipi in ['gelir_eklendi', 'manuel_ekleme']:
                sonraki.onceki_bakiye = onceki + tutar_farki
                sonraki.yeni_bakiye = sonraki.onceki_bakiye + sonraki.tutar
            elif sonraki.islem_tipi == 'normal_kasaya_aktarildi':
                sonraki.onceki_bakiye = onceki + tutar_farki
                sonraki.yeni_bakiye = sonraki.onceki_bakiye - sonraki.tutar
        
        ana_kasa.guncelleme_tarihi = datetime.now()
        db.session.commit()
        
        flash(f'✅ İşlem kaydı güncellendi ve bakiyeler yeniden hesaplandı!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Hata: {str(e)}', 'danger')
    
    return redirect(url_for('kasa.ana_kasa_kayit_defteri'))


@kasa_bp.route('/kasa/ana-kasa/islem-sil', methods=['POST'])
@login_required
@roles_required('admin')
def ana_kasa_islem_sil():
    """Ana Kasa işlem kaydını sil ve bakiyeyi yeniden hesapla"""
    try:
        islem_id = request.form.get('islem_id')
        
        # İşlemi bul
        islem = AnaKasaIslem.query.get_or_404(islem_id)
        
        # İşlem tutarını sakla
        tutar = islem.tutar
        islem_tipi = islem.islem_tipi
        islem_tarihi = islem.tarih
        
        # Ana Kasa'yı güncelle
        ana_kasa = AnaKasa.query.first()
        
        if islem_tipi in ['gelir_eklendi', 'manuel_ekleme']:
            # Artırıcı işlem silindi, bakiyeden düş
            ana_kasa.bakiye -= tutar
        elif islem_tipi == 'normal_kasaya_aktarildi':
            # Azaltıcı işlem silindi, bakiyeye ekle
            ana_kasa.bakiye += tutar
        
        # Bu işlemden sonraki tüm işlemlerin bakiyelerini güncelle
        sonraki_islemler = AnaKasaIslem.query.filter(
            AnaKasaIslem.tarih > islem_tarihi
        ).order_by(AnaKasaIslem.tarih.asc()).all()
        
        for sonraki in sonraki_islemler:
            if islem_tipi in ['gelir_eklendi', 'manuel_ekleme']:
                # Silinen işlem artırıcıydı, sonraki bakiyeleri azalt
                sonraki.onceki_bakiye -= tutar
                sonraki.yeni_bakiye -= tutar
            elif islem_tipi == 'normal_kasaya_aktarildi':
                # Silinen işlem azaltıcıydı, sonraki bakiyeleri artır
                sonraki.onceki_bakiye += tutar
                sonraki.yeni_bakiye += tutar
        
        # İşlemi sil
        db.session.delete(islem)
        
        ana_kasa.guncelleme_tarihi = datetime.now()
        db.session.commit()
        
        flash(f'✅ İşlem kaydı silindi ve bakiyeler yeniden hesaplandı!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Hata: {str(e)}', 'danger')
    
    return redirect(url_for('kasa.ana_kasa_kayit_defteri'))
