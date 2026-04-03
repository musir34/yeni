"""Kimlik doğrulama, cihaz yönetimi ve oturum sistemi.

Giriş akışı:
  Tanınan cihaz (çerez var) → Sadece 2FA kodu sor → Giriş
  Yeni cihaz (çerez yok)   → Şifre + 2FA → Cihaz kaydet → Giriş

Cihaz limiti: 1 PC + 2 Mobil (toplam 3)
"""

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, Blueprint, make_response, jsonify,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import pyotp
import base64
import qrcode
import secrets
from io import BytesIO
from models import db, User, UserDevice
from logger_config import app_logger as logger
from flask_login import login_user as flask_login_user

login_logout_bp = Blueprint('login_logout', __name__)

DEVICE_COOKIE_NAME = 'gs_device_token'
DEVICE_COOKIE_MAX_AGE = 90 * 24 * 3600  # 90 gün
REMEMBER_DAYS = 30
MAX_PC = 1
MAX_MOBILE = 2


# ═══════════════════════════════════════════════════════════════════════
#  YARDIMCI FONKSİYONLAR
# ═══════════════════════════════════════════════════════════════════════

def _log_action(*args, **kwargs):
    from user_logs import log_user_action
    return log_user_action(*args, **kwargs)


def _detect_device_type(user_agent: str) -> str:
    """User-Agent'tan cihaz tipini belirler: 'mobile' veya 'pc'."""
    ua = (user_agent or '').lower()
    mobile_keywords = ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'opera mini', 'opera mobi']
    return 'mobile' if any(k in ua for k in mobile_keywords) else 'pc'


def _detect_device_name(user_agent: str) -> str:
    """User-Agent'tan okunabilir cihaz adı çıkarır."""
    ua = user_agent or 'Bilinmeyen'
    # Tarayıcı tespiti
    browser = 'Tarayıcı'
    if 'Chrome' in ua and 'Edg' not in ua:
        browser = 'Chrome'
    elif 'Firefox' in ua:
        browser = 'Firefox'
    elif 'Safari' in ua and 'Chrome' not in ua:
        browser = 'Safari'
    elif 'Edg' in ua:
        browser = 'Edge'
    # İşletim sistemi
    os_name = ''
    if 'Windows' in ua:
        os_name = 'Windows'
    elif 'Macintosh' in ua or 'Mac OS' in ua:
        os_name = 'MacOS'
    elif 'Linux' in ua and 'Android' not in ua:
        os_name = 'Linux'
    elif 'iPhone' in ua:
        os_name = 'iPhone'
    elif 'iPad' in ua:
        os_name = 'iPad'
    elif 'Android' in ua:
        os_name = 'Android'
    return f"{browser} - {os_name}" if os_name else browser


def _get_trusted_device() -> UserDevice | None:
    """İstekteki çerezden güvenilen cihazı döner (varsa)."""
    token = request.cookies.get(DEVICE_COOKIE_NAME)
    if not token:
        return None
    device = UserDevice.query.filter_by(device_token=token).first()
    if device:
        # Cihaz sahibinin hesabı aktif mi kontrol et
        user = User.query.get(device.user_id)
        if user and user.status == 'active' and user.totp_confirmed:
            return device
    return None


def _check_device_limit(user: User, device_type: str) -> tuple[bool, str]:
    """Cihaz limitini kontrol eder. (izin_var, mesaj) döner."""
    devices = UserDevice.query.filter_by(user_id=user.id).all()
    pc_count = sum(1 for d in devices if d.device_type == 'pc')
    mobile_count = sum(1 for d in devices if d.device_type == 'mobile')

    user_max_pc = getattr(user, 'max_pc', None) or MAX_PC
    if device_type == 'pc' and pc_count >= user_max_pc:
        return False, f'PC cihaz limitine ulaştınız ({user_max_pc} PC). Mevcut bir cihazı kaldırmanız gerekiyor.'
    if device_type == 'mobile' and mobile_count >= MAX_MOBILE:
        return False, f'Mobil cihaz limitine ulaştınız ({MAX_MOBILE} mobil). Mevcut bir cihazı kaldırmanız gerekiyor.'
    return True, ''


def _register_device(user: User, response) -> None:
    """Yeni cihaz kaydeder ve çerez ayarlar."""
    ua = request.headers.get('User-Agent', '')
    device_type = _detect_device_type(ua)
    device_name = _detect_device_name(ua)
    token = secrets.token_urlsafe(64)

    device = UserDevice(
        user_id=user.id,
        device_token=token,
        device_type=device_type,
        device_name=device_name,
        ip_address=request.remote_addr,
        last_active=datetime.utcnow(),
    )
    db.session.add(device)
    db.session.commit()

    response.set_cookie(
        DEVICE_COOKIE_NAME, token,
        max_age=DEVICE_COOKIE_MAX_AGE,
        httponly=True, samesite='Lax',
    )
    logger.info(f"Yeni cihaz kaydedildi: {user.username} - {device_name} ({device_type})")


def login_user(user):
    logger.info(f"Giriş yapan kullanıcı: {user.username}, rolü: {user.role}")
    flask_login_user(user, remember=True)
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role
    session['first_name'] = user.first_name
    session['last_name'] = user.last_name
    session['authenticated'] = True
    session['session_version'] = user.session_version or 1
    session.permanent = True


# ═══════════════════════════════════════════════════════════════════════
#  DEKORATÖRLER
# ═══════════════════════════════════════════════════════════════════════

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Lütfen giriş yapın.', 'warning')
            return redirect(url_for('login_logout.login'))
        # Oturum versiyon kontrolü (toplu çıkış için)
        user = User.query.get(session['user_id'])
        if user and (user.session_version or 1) != session.get('session_version', 0):
            session.clear()
            flash('Oturumunuz sonlandırıldı. Lütfen tekrar giriş yapın.', 'warning')
            return redirect(url_for('login_logout.login'))
        if not session.get('totp_verified'):
            flash('İki adımlı doğrulama gereklidir.', 'warning')
            return redirect(url_for('login_logout.verify_totp'))
        return f(*args, **kwargs)
    return decorated_function


def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'role' not in session:
                flash('Lütfen giriş yapın.', 'warning')
                return redirect(url_for('login_logout.login'))
            if not session.get('totp_verified'):
                flash('İki adımlı doğrulama gereklidir.', 'warning')
                return redirect(url_for('login_logout.verify_totp'))
            if session.get('role') not in roles:
                flash('Bu sayfaya erişim yetkiniz yok.', 'warning')
                return redirect(url_for('home.home'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ═══════════════════════════════════════════════════════════════════════
#  QR KOD
# ═══════════════════════════════════════════════════════════════════════

def generate_qr_code(data):
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('utf-8')


# ═══════════════════════════════════════════════════════════════════════
#  KAYIT
# ═══════════════════════════════════════════════════════════════════════

@login_logout_bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'role' not in session or session.get('role') != 'admin':
        return '''<script>alert('Yetki Yok!');window.location.href='/';</script>'''

    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        existing = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing:
            flash('Bu kullanıcı adı veya e-posta zaten kullanılıyor!', 'danger')
            return redirect(url_for('login_logout.register'))

        new_user = User(
            first_name=first_name, last_name=last_name,
            username=username, email=email,
            password=generate_password_hash(password),
            role='worker', status='pending',
            totp_secret=pyotp.random_base32(),
            totp_confirmed=True,
            session_version=1,
        )
        db.session.add(new_user)
        db.session.commit()
        _log_action("CREATE", {"işlem_açıklaması": f"Yeni kullanıcı kaydı — {username}", "sayfa": "Kayıt"}, force_log=True)
        flash('Kayıt başarılı! Hesabınızın onaylanmasını bekleyin.', 'info')
        return redirect(url_for('login_logout.login'))
    return render_template('register.html')


# ═══════════════════════════════════════════════════════════════════════
#  GİRİŞ — AKILLI CİHAZ AKIŞI
# ═══════════════════════════════════════════════════════════════════════

@login_logout_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Zaten giriş yapmışsa
    if 'user_id' in session and session.get('authenticated') and session.get('totp_verified'):
        return redirect(url_for('home.home'))

    # Güvenilen cihaz kontrolü (force_password=1 ile zorla şifre moduna geçilebilir)
    trusted = None if request.args.get('force_password') else _get_trusted_device()

    if request.method == 'POST':
        if trusted:
            # ── TANINAN CİHAZ: Sadece 2FA kodu sor ──────────────────
            token = request.form.get('token', '').strip()
            user = User.query.get(trusted.user_id)

            if not user:
                flash('Kullanıcı bulunamadı.', 'danger')
                return redirect(url_for('login_logout.login'))

            totp = pyotp.TOTP(user.totp_secret)
            if token and totp.verify(token):
                session.clear()
                login_user(user)
                session['totp_verified'] = True
                # Cihaz son aktifliğini güncelle
                trusted.last_active = datetime.utcnow()
                trusted.ip_address = request.remote_addr
                db.session.commit()
                _log_action("LOGIN", {"işlem_açıklaması": f"{user.username} güvenilen cihazdan giriş yaptı", "sayfa": "Giriş"})
                flash('Başarıyla giriş yaptınız.', 'success')
                return redirect(url_for('home.home'))
            else:
                flash('Geçersiz doğrulama kodu.', 'danger')
                return render_template('login.html', trusted_device=True, trusted_user=user)
        else:
            # ── YENİ CİHAZ: Şifre + sonra 2FA ───────────────────────
            session.clear()
            username = request.form['username']
            password = request.form['password']
            user = User.query.filter_by(username=username).first()

            if user and check_password_hash(user.password, password):
                if user.status == 'pending':
                    flash('Hesabınız onay bekliyor.', 'warning')
                    return redirect(url_for('login_logout.login'))

                # Cihaz limiti kontrolü
                ua = request.headers.get('User-Agent', '')
                device_type = _detect_device_type(ua)
                allowed, msg = _check_device_limit(user, device_type)
                if not allowed:
                    flash(msg, 'danger')
                    # Kullanıcıya cihaz yönetim linkini göster
                    session['_temp_user_id'] = user.id
                    return redirect(url_for('login_logout.device_limit_reached'))

                login_user(user)
                _log_action("LOGIN", {"işlem_açıklaması": f"{user.username} yeni cihazdan giriş yaptı", "sayfa": "Giriş"})
                session['pending_user'] = user.username
                session['_register_device'] = True  # 2FA sonrası cihaz kaydedilecek
                return redirect(url_for('login_logout.verify_totp'))
            else:
                flash('Kullanıcı adı veya şifre yanlış!', 'danger')
                _log_action("LOGIN", {"işlem_açıklaması": f"Başarısız giriş — {username}", "sayfa": "Giriş", "durum": "Başarısız"}, force_log=True)

    # GET — tanınan cihaz varsa farklı template göster
    if trusted:
        user = User.query.get(trusted.user_id)
        return render_template('login.html', trusted_device=True, trusted_user=user)

    return render_template('login.html', trusted_device=False, trusted_user=None)


# ═══════════════════════════════════════════════════════════════════════
#  CİHAZ LİMİTİ AŞILDI SAYFASI
# ═══════════════════════════════════════════════════════════════════════

@login_logout_bp.route('/device-limit', methods=['GET', 'POST'])
def device_limit_reached():
    user_id = session.get('_temp_user_id')
    if not user_id:
        return redirect(url_for('login_logout.login'))

    user = User.query.get(user_id)
    if not user:
        return redirect(url_for('login_logout.login'))

    devices = UserDevice.query.filter_by(user_id=user.id).order_by(UserDevice.last_active.desc()).all()

    if request.method == 'POST':
        device_id = request.form.get('remove_device_id')
        if device_id:
            device = UserDevice.query.filter_by(id=device_id, user_id=user.id).first()
            if device:
                db.session.delete(device)
                db.session.commit()
                logger.info(f"Cihaz kaldırıldı: {user.username} - {device.device_name}")
                flash(f'"{device.device_name}" cihazı kaldırıldı. Şimdi tekrar giriş yapabilirsiniz.', 'success')
                session.pop('_temp_user_id', None)
                return redirect(url_for('login_logout.login'))

    return render_template('device_limit.html', user=user, devices=devices,
                           max_pc=MAX_PC, max_mobile=MAX_MOBILE)


# ═══════════════════════════════════════════════════════════════════════
#  TOTP KURULUM & DOĞRULAMA
# ═══════════════════════════════════════════════════════════════════════

@login_logout_bp.route('/setup_totp', methods=['GET', 'POST'])
def setup_totp():
    if 'user_id' not in session:
        return redirect(url_for('login_logout.login'))
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('login_logout.login'))
    if user.totp_confirmed:
        return redirect(url_for('home.home'))

    totp = pyotp.TOTP(user.totp_secret)
    provisioning_uri = totp.provisioning_uri(name=user.email or 'user', issuer_name='Güllü Ayakkabı')
    qr_code_data = generate_qr_code(provisioning_uri)

    if request.method == 'POST':
        token = request.form.get('token')
        if token and totp.verify(token):
            user.totp_confirmed = True
            db.session.commit()
            _log_action("CREATE", {"işlem_açıklaması": f"{user.username} 2FA kurulumu tamamladı", "sayfa": "2FA Kurulum"})
            session['totp_verified'] = True
            # İlk cihazı kaydet
            resp = make_response(redirect(url_for('home.home')))
            _register_device(user, resp)
            flash('2FA kurulumu tamamlandı. Hoş geldiniz!', 'success')
            return resp
        flash('Geçersiz doğrulama kodu.', 'danger')
    return render_template('setup_totp.html', qr_code_data=qr_code_data)


@login_logout_bp.route('/verify_totp', methods=['GET', 'POST'])
def verify_totp():
    username = session.get('pending_user')
    if not username:
        return redirect(url_for('login_logout.login'))

    user = User.query.filter_by(username=username).first()
    if not user:
        return redirect(url_for('login_logout.login'))

    totp = pyotp.TOTP(user.totp_secret)

    if request.method == 'POST':
        token = request.form.get('token')
        if token and totp.verify(token):
            login_user(user)
            session.pop('pending_user', None)
            session['totp_verified'] = True
            _log_action("LOGIN", {"işlem_açıklaması": f"{user.username} 2FA doğrulaması tamamlandı", "sayfa": "2FA Doğrulama"})

            # Yeni cihaz kaydı
            should_register = session.pop('_register_device', False)
            if should_register:
                resp = make_response(redirect(url_for('home.home')))
                _register_device(user, resp)
                flash('Başarıyla giriş yaptınız. Cihaz kaydedildi.', 'success')
                return resp

            flash('Başarıyla giriş yaptınız.', 'success')
            return redirect(url_for('home.home'))
        flash('Geçersiz doğrulama kodu.', 'danger')
    return render_template('verify_totp.html')


# ═══════════════════════════════════════════════════════════════════════
#  CİHAZ YÖNETİMİ
# ═══════════════════════════════════════════════════════════════════════

@login_logout_bp.route('/cihazlarim', methods=['GET'])
@login_required
def cihazlarim():
    user = User.query.get(session['user_id'])
    devices = UserDevice.query.filter_by(user_id=user.id).order_by(UserDevice.last_active.desc()).all()
    current_token = request.cookies.get(DEVICE_COOKIE_NAME, '')
    return render_template('cihazlarim.html', devices=devices, current_token=current_token,
                           max_pc=MAX_PC, max_mobile=MAX_MOBILE)


@login_logout_bp.route('/cihaz-sil/<int:device_id>', methods=['POST'])
@login_required
def cihaz_sil(device_id):
    device = UserDevice.query.filter_by(id=device_id, user_id=session['user_id']).first()
    if device:
        name = device.device_name
        db.session.delete(device)
        db.session.commit()
        _log_action("DELETE", {"işlem_açıklaması": f"Cihaz kaldırıldı: {name}", "sayfa": "Cihaz Yönetimi"})
        flash(f'"{name}" cihazı kaldırıldı.', 'success')
    else:
        flash('Cihaz bulunamadı.', 'danger')
    return redirect(url_for('login_logout.cihazlarim'))


@login_logout_bp.route('/tum-cihazlardan-cikis', methods=['POST'])
@login_required
def tum_cihazlardan_cikis():
    """Tüm cihazları siler ve session_version artırarak tüm oturumları geçersiz kılar."""
    user = User.query.get(session['user_id'])
    if user:
        # Tüm cihazları sil
        UserDevice.query.filter_by(user_id=user.id).delete()
        # Session versiyonunu artır → tüm eski oturumlar geçersiz
        user.session_version = (user.session_version or 1) + 1
        db.session.commit()
        _log_action("DELETE", {"işlem_açıklaması": "Tüm cihazlardan çıkış yapıldı", "sayfa": "Cihaz Yönetimi"})
        logger.info(f"Tüm cihazlar silindi: {user.username}")
    session.clear()
    resp = make_response(redirect(url_for('login_logout.login')))
    resp.delete_cookie(DEVICE_COOKIE_NAME)
    flash('Tüm cihazlardan çıkış yapıldı. Lütfen tekrar giriş yapın.', 'success')
    return resp


# ═══════════════════════════════════════════════════════════════════════
#  ADMIN: TÜM KULLANICILARI ÇIKIŞ YAPTIR
# ═══════════════════════════════════════════════════════════════════════

@login_logout_bp.route('/admin/force-logout-all', methods=['POST'])
@roles_required('admin')
def force_logout_all():
    """Tüm kullanıcıların oturumlarını ve cihazlarını geçersiz kılar."""
    users = User.query.all()
    for u in users:
        u.session_version = (u.session_version or 1) + 1
    UserDevice.query.delete()
    db.session.commit()
    _log_action("DELETE", {"işlem_açıklaması": "ADMIN: Tüm kullanıcılar çıkış yaptırıldı", "sayfa": "Admin"})
    logger.warning("ADMIN force logout: Tüm kullanıcı oturumları ve cihazları geçersiz kılındı")
    session.clear()
    resp = make_response(redirect(url_for('login_logout.login')))
    resp.delete_cookie(DEVICE_COOKIE_NAME)
    flash('Tüm kullanıcılar çıkış yaptırıldı.', 'success')
    return resp


# ═══════════════════════════════════════════════════════════════════════
#  DİĞER ROUTE'LAR
# ═══════════════════════════════════════════════════════════════════════

@login_logout_bp.route('/check_role', methods=['GET'])
def check_role():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if user:
        return f"Kullanıcı: {user.username}, Rol: {user.role}"
    return "Kullanıcı bulunamadı"


@login_logout_bp.route('/home')
@login_required
def home_redirect():
    return redirect(url_for('home.home'))


@login_logout_bp.route('/delete_user/<username>', methods=['POST'])
@roles_required('admin')
def delete_user(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('Kullanıcı bulunamadı.', 'danger')
        return redirect(url_for('login_logout.approve_users'))
    if user.id == session.get('user_id'):
        flash('Kendi hesabınızı silemezsiniz.', 'danger')
        return redirect(url_for('login_logout.approve_users'))

    try:
        from models import UserLog, Rapor
        UserLog.query.filter_by(user_id=user.id).delete()
        Rapor.query.filter_by(kullanici_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
        flash(f'{username} kullanıcısı silindi.', 'success')
        _log_action("DELETE", {"işlem_açıklaması": f"{username} silindi", "sayfa": "Kullanıcı Yönetimi"})
    except Exception as e:
        db.session.rollback()
        flash(f'Hata: {e}', 'danger')
    return redirect(url_for('login_logout.approve_users'))


@login_logout_bp.route('/approve_users', methods=['GET', 'POST'])
@roles_required('admin')
def approve_users():
    if request.method == 'POST':
        action_value = request.form.get('action')
        if action_value:
            action_parts = action_value.split('_', 1)
            if len(action_parts) == 2:
                action, username = action_parts
                user = User.query.filter_by(username=username).first()
                if user:
                    if action == 'approve':
                        user.status = 'active'
                        role = request.form.get(f'role_{username}', 'worker')
                        user.role = role
                        db.session.commit()
                        _log_action("UPDATE", {"işlem_açıklaması": f"{username} onaylandı — Rol: {role}", "sayfa": "Kullanıcı Yönetimi"})
                        flash(f"{username} onaylandı, rol: {role}.", 'success')
                    elif action == 'update':
                        role = request.form.get(f'role_{username}', 'worker')
                        user.role = role
                        db.session.commit()
                        _log_action("UPDATE", {"işlem_açıklaması": f"{username} rolü güncellendi — {role}", "sayfa": "Kullanıcı Yönetimi"})
                        flash(f"{username} rolü güncellendi.", 'success')
                    elif action == 'revoke':
                        user.status = 'pending'
                        db.session.commit()
                        _log_action("UPDATE", {"işlem_açıklaması": f"{username} onayı iptal edildi", "sayfa": "Kullanıcı Yönetimi"})
                        flash(f"{username} onayı iptal edildi.", 'warning')
        return redirect(url_for('login_logout.approve_users'))

    pending_users = User.query.filter_by(status='pending').all()
    approved_users = User.query.filter_by(status='active').all()
    return render_template('approve_users.html', pending_users=pending_users, approved_users=approved_users)


@login_logout_bp.route('/admin/update-notify/<username>', methods=['POST'])
@roles_required('admin')
def update_notify(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı.'}), 404
    events = request.json.get('events', [])
    user.notify_events = ','.join(events)
    db.session.commit()
    return jsonify({'success': True, 'events': events})


@login_logout_bp.route('/admin/update-max-pc/<username>', methods=['POST'])
@roles_required('admin')
def update_max_pc(username):
    """Admin: kullanıcının PC cihaz limitini gunceller."""
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'success': False, 'message': 'Kullanici bulunamadi.'}), 404
    max_pc = request.json.get('max_pc', 1)
    max_pc = max(1, min(int(max_pc), 10))  # 1-10 arasi sinirla
    user.max_pc = max_pc
    db.session.commit()
    _log_action('ADMIN_UPDATE_MAX_PC', {
        'hedef_kullanici': username,
        'yeni_pc_limiti': max_pc,
    })
    return jsonify({'success': True, 'max_pc': max_pc})


@login_logout_bp.route('/admin/reset-password/<username>', methods=['POST'])
@roles_required('admin')
def admin_reset_password(username):
    """Admin: kullanıcının şifresini sıfırlar ve yeni geçici şifre oluşturur."""
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('Kullanıcı bulunamadı.', 'danger')
        return redirect(url_for('login_logout.approve_users'))

    new_password = secrets.token_urlsafe(8)  # 8 karakterlik rastgele şifre
    user.password = generate_password_hash(new_password)
    # Oturumları geçersiz kıl
    user.session_version = (user.session_version or 1) + 1
    # Cihazları temizle
    UserDevice.query.filter_by(user_id=user.id).delete()
    db.session.commit()

    _log_action("UPDATE", {"işlem_açıklaması": f"Admin şifre sıfırladı: {username}", "sayfa": "Kullanıcı Yönetimi"})
    logger.info(f"Şifre sıfırlandı: {username} (admin tarafından)")
    flash(f'{username} şifresi sıfırlandı. Yeni geçici şifre: {new_password}', 'success')
    return redirect(url_for('login_logout.approve_users'))


@login_logout_bp.route('/admin/reset-2fa/<username>', methods=['POST'])
@roles_required('admin')
def admin_reset_2fa(username):
    """Admin: kullanıcının 2FA'sını sıfırlar, yeniden kurulum gerektirir."""
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('Kullanıcı bulunamadı.', 'danger')
        return redirect(url_for('login_logout.approve_users'))

    user.totp_secret = pyotp.random_base32()
    user.totp_confirmed = True
    # Oturumları geçersiz kıl
    user.session_version = (user.session_version or 1) + 1
    # Cihazları temizle
    UserDevice.query.filter_by(user_id=user.id).delete()
    db.session.commit()

    _log_action("UPDATE", {"işlem_açıklaması": f"Admin 2FA sıfırladı: {username}", "sayfa": "Kullanıcı Yönetimi"})
    logger.info(f"2FA sıfırlandı: {username} (admin tarafından)")
    flash(f'{username} için 2FA sıfırlandı. Yeni QR kodu admin panelinden gösterilebilir.', 'success')
    return redirect(url_for('login_logout.approve_users'))


@login_logout_bp.route('/admin/reset-all/<username>', methods=['POST'])
@roles_required('admin')
def admin_reset_all(username):
    """Admin: şifre + 2FA + cihazların hepsini sıfırlar."""
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('Kullanıcı bulunamadı.', 'danger')
        return redirect(url_for('login_logout.approve_users'))

    new_password = secrets.token_urlsafe(8)
    user.password = generate_password_hash(new_password)
    user.totp_secret = pyotp.random_base32()
    user.totp_confirmed = True
    user.session_version = (user.session_version or 1) + 1
    UserDevice.query.filter_by(user_id=user.id).delete()
    db.session.commit()

    _log_action("UPDATE", {"işlem_açıklaması": f"Admin tam sıfırlama: {username}", "sayfa": "Kullanıcı Yönetimi"})
    logger.info(f"Tam sıfırlama: {username} (şifre + 2FA + cihazlar)")
    flash(f'{username} için tam sıfırlama yapıldı. Yeni geçici şifre: {new_password} — Yeni QR kodu admin panelinden gösterilebilir.', 'success')
    return redirect(url_for('login_logout.approve_users'))


@login_logout_bp.route('/show_qr_code/<username>')
@roles_required('admin')
def show_qr_code(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('Kullanıcı bulunamadı.', 'danger')
        return redirect(url_for('login_logout.approve_users'))
    totp = pyotp.TOTP(user.totp_secret)
    provisioning_uri = totp.provisioning_uri(name=user.email, issuer_name='Güllü Ayakkabı')
    return render_template('show_qr_code.html', qr_code_data=generate_qr_code(provisioning_uri), username=username)


@login_logout_bp.route('/logout')
def logout():
    _log_action("LOGOUT", {"işlem_açıklaması": "Oturum kapatıldı", "sayfa": "Çıkış"})
    session.clear()
    flash('Başarıyla çıkış yaptınız.', 'success')
    return redirect(url_for('login_logout.login'))
