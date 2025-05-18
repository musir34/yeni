from flask import Flask, render_template, request, redirect, url_for, flash, session, Blueprint
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import pyotp
import base64
import qrcode
from io import BytesIO
from models import db, User
from logger_config import app_logger as logger

login_logout_bp = Blueprint('login_logout', __name__)

def login_user(user):
    logger.info(f"Giriş yapan kullanıcı: {user.username}, rolü: {user.role}")
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role
    session['first_name'] = user.first_name
    session['last_name'] = user.last_name
    session['authenticated'] = True
    # Oturum süresini uzatmak için permanent oturumu kullanıyoruz
    session.permanent = True
    logger.debug(f"Oturumda atanan rol: {session['role']}")






# Oturum gerektiren dekoratör
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Lütfen giriş yapın.', 'warning')
            return redirect(url_for('login_logout.login'))
        return f(*args, **kwargs)
    return decorated_function

# Belirli bir role sahip olmayı gerektiren dekoratör
def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Kullanıcının oturum açıp açmadığını kontrol et
            if 'role' not in session:
                flash('Lütfen giriş yapın.', 'warning')
                logger.warning("No role found in session.")
                return redirect(url_for('login_logout.login'))

            # Oturumdaki rolü kontrol et
            user_role = session.get('role')
            logger.debug(f"User role in session: {user_role}")
            logger.debug(f"Required roles: {roles}")

            # Eğer kullanıcı rolü gereken roller arasında değilse, erişimi reddet
            if user_role not in roles:
                flash('Bu sayfaya erişim yetkiniz yok.', 'warning')
                return redirect(url_for('login_logout.home'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator




#  QR kodu oluşturma fonksiyonu
def generate_qr_code(data):
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return img_str

# Kullanıcı kaydı
@login_logout_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        existing_user = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()
        if existing_user:
            flash('Bu kullanıcı adı veya e-posta zaten kullanılıyor!', 'danger')
            return redirect(url_for('login_logout.register'))

        hashed_password = generate_password_hash(password)
        totp_secret = pyotp.random_base32()

        new_user = User(
            first_name=first_name,
            last_name=last_name,
            username=username,
            password=hashed_password,
            email=email,
            role='worker',
            status='pending',
            totp_secret=totp_secret
        )

        db.session.add(new_user)
        db.session.commit()
        flash('Kayıt başarılı! Hesabınızın onaylanmasını bekleyin.', 'info')
        return redirect(url_for('login_logout.login'))
    return render_template('register.html')

@login_logout_bp.route('/check_role', methods=['GET'])
def check_role():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if user:
        return f"Kullanıcı: {user.username}, Rol: {user.role}"
    return "Kullanıcı bulunamadı"


# Kullanıcı girişi
@login_logout_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Eğer kullanıcı zaten doğrulanmışsa
    if 'user_id' in session and session.get('authenticated', False) and session.get('totp_verified', False):
        return redirect(url_for('login_logout.home'))
        
    if request.method == 'POST':
        session.clear()
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user:
            logger.debug(f"Veritabanından gelen kullanıcı: {user.username}, rolü: {user.role}")

        if user and check_password_hash(user.password, password):
            if user.status == 'pending':
                flash('Hesabınız onay bekliyor.', 'warning')
                return redirect(url_for('login_logout.login'))

            # Kullanıcı TOTP kurulumunu yapmamışsa yönlendir
            if not user.totp_confirmed:
                login_user(user)
                return redirect(url_for('login_logout.setup_totp'))

            # Kullanıcı doğrulandıktan sonra oturum bilgilerini ayarla
            login_user(user)
            session['pending_user'] = user.username
            return redirect(url_for('login_logout.verify_totp'))
        else:
            flash('Kullanıcı adı veya şifre yanlış!', 'danger')
    return render_template('login.html')


# TOTP Kurulum
@login_logout_bp.route('/setup_totp', methods=['GET', 'POST'])
@login_required
def setup_totp():
    user = User.query.get(session['user_id'])

    if user.totp_confirmed:
        return redirect(url_for('login_logout.home'))

    totp = pyotp.TOTP(user.totp_secret)
    provisioning_uri = totp.provisioning_uri(name=user.email, issuer_name='Firma İsmi')
    qr_code_data = generate_qr_code(provisioning_uri)

    if request.method == 'POST':
        token = request.form.get('token')
        if totp.verify(token):
            user.totp_confirmed = True
            db.session.commit()
            flash('TOTP başarıyla kuruldu.', 'success')
            return redirect(url_for('login_logout.home'))
        flash('Geçersiz doğrulama kodu.', 'danger')
    return render_template('verify_totp.html', qr_code_data=qr_code_data)

# TOTP Doğrulama
@login_logout_bp.route('/verify_totp', methods=['GET', 'POST'])
def verify_totp():
    username = session.get('pending_user')
    if not username:
        return redirect(url_for('login_logout.login'))

    user = User.query.filter_by(username=username).first()
    totp = pyotp.TOTP(user.totp_secret)

    if request.method == 'POST':
        token = request.form.get('token')
        if totp.verify(token):
            login_user(user)
            session.pop('pending_user', None)
            # 2FA tamamlandı
            session['totp_verified'] = True
            flash('Başarıyla giriş yaptınız.', 'success')
            return redirect(url_for('login_logout.home'))
        flash('Geçersiz doğrulama kodu.', 'danger')
    return render_template('verify_totp.html')


# Kullanıcı silme
@login_logout_bp.route('/delete_user/<username>', methods=['POST'])
@roles_required('admin')
def delete_user(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('Kullanıcı bulunamadı.', 'danger')
        return redirect(url_for('login_logout.approve_users'))

    try:
        db.session.delete(user)
        db.session.commit()
        flash(f'{username} kullanıcısı başarıyla silindi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Kullanıcı silinirken bir hata oluştu: {e}', 'danger')

    return redirect(url_for('login_logout.approve_users'))



# Yönetici onayı ve rol yönetimi
@login_logout_bp.route('/approve_users', methods=['GET', 'POST'])
@roles_required('admin')
def approve_users():
    if request.method == 'POST':
        action_value = request.form.get('action')
        if action_value:
            # İşlem türünü ve kullanıcı adını ayırma
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
                        flash(f"{username} kullanıcısı onaylandı ve rolü {role} olarak ayarlandı.", 'success')
                    elif action == 'update':
                        role = request.form.get(f'role_{username}', 'worker')
                        user.role = role
                        db.session.commit()
                        flash(f"{username} kullanıcısının rolü güncellendi.", 'success')
                    elif action == 'revoke':
                        user.status = 'pending'
                        db.session.commit()
                        flash(f"{username} kullanıcısının onayı iptal edildi.", 'warning')
                else:
                    flash('Kullanıcı bulunamadı.', 'danger')
            else:
                flash('Geçersiz işlem.', 'danger')
        else:
            flash('Herhangi bir işlem seçilmedi.', 'danger')
        return redirect(url_for('login_logout.approve_users'))

    pending_users = User.query.filter_by(status='pending').all()
    approved_users = User.query.filter_by(status='active').all()
    return render_template('approve_users.html', pending_users=pending_users, approved_users=approved_users)

# QR kodunu gösterme
@login_logout_bp.route('/show_qr_code/<username>')
@roles_required('admin')
def show_qr_code(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('Kullanıcı bulunamadı.', 'danger')
        return redirect(url_for('login_logout.approve_users'))

    totp_secret = user.totp_secret
    totp = pyotp.TOTP(totp_secret)
    provisioning_uri = totp.provisioning_uri(name=user.email, issuer_name='Firma İsmi')
    qr_code_data = generate_qr_code(provisioning_uri)

    return render_template('show_qr_code.html', qr_code_data=qr_code_data, username=username)

# Oturumu kapatma
@login_logout_bp.route('/logout')
def logout():
    session.clear()
    flash('Başarıyla çıkış yaptınız.', 'success')
    return redirect(url_for('login_logout.login'))

# Ana Sayfa
@login_logout_bp.route('/home')
@login_required
def home():
    return render_template('home.html')
