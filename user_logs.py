from flask import Blueprint, render_template, request, session
from flask_login import current_user
from models import db, UserLog, User
from login_logout import roles_required
from datetime import datetime, timedelta
import json
import urllib.parse
import logging

# Sabit sözlükler
PAGE_NAME_MAP = {
    'home': 'Ana Sayfa',
    'order_list': 'Sipariş Listesi',
    'exchange_form': 'Değişim Formu',
    'analysis': 'Analiz Sayfası',
    'stock_report': 'Stok Raporu',
    'user_logs': 'Kullanıcı Logları',
    'product_list': 'Ürün Listesi',
    'archive': 'Arşiv',
    'login': 'Giriş',
    'register': 'Kayıt',
}

ACTION_TYPE_MAP = {
    'PAGE_VIEW': 'Sayfa Görüntüleme',
    'LOGIN': 'Giriş',
    'LOGOUT': 'Çıkış',
    'CREATE': 'Oluşturma',
    'UPDATE': 'Güncelleme',
    'DELETE': 'Silme',
    'ARCHIVE': 'Arşivleme',
    'PRINT': 'Yazdırma',
    'EXPORT': 'Dışa Aktarma',
}

user_logs_bp = Blueprint('user_logs', __name__)

def translate_page_name(page: str) -> str:
    return PAGE_NAME_MAP.get(page, page or 'Ana Sayfa')

def translate_action_type(action: str) -> str:
    return ACTION_TYPE_MAP.get(action, action)

def get_browser_info() -> str:
    return request.user_agent.browser or "Bilinmiyor"

def get_platform_info() -> str:
    return request.user_agent.platform or "Bilinmiyor"

def extract_page_from_referrer(referrer: str) -> str:
    if referrer:
        parsed_url = urllib.parse.urlparse(referrer)
        page = parsed_url.path.split('/')[-1]
        return PAGE_NAME_MAP.get(page, 'Doğrudan Giriş') if page else 'Doğrudan Giriş'
    return 'Doğrudan Giriş'

def log_user_action(action: str, details: dict = None, force_log: bool = False, log_level: str = "INFO") -> None:
    """
    Aksiyon: 'UPDATE: product_list' vb.
    details: {'stok_kodu': 'ABC123', 'guncellenen_adet': 5} gibi ek ayrıntılar.
    """
    if current_user.is_authenticated or force_log:
        user_id = current_user.id if current_user.is_authenticated else session.get('user_id')
        user_role = getattr(current_user, 'role', session.get('role', 'anonymous'))

        # action içinden 'UPDATE' ve 'product_list' vb. ayrıştır
        action_parts = action.split(': ', 1)
        action_type_raw = action_parts[0].strip()   # 'UPDATE'
        action_page_raw = action_parts[1].strip() if len(action_parts) > 1 else ''  # 'product_list'

        translated_action = translate_action_type(action_type_raw)  # 'Güncelleme'
        translated_page = translate_page_name(action_page_raw)      # 'Ürün Listesi'

        # Detay sözlüğünü genişlet
        extended_details = {
            'İşlem': translated_action,   # 'Güncelleme'
            'Sayfa': translated_page,     # 'Ürün Listesi'
            'Kullanıcı Rolü': (
                'Yönetici' if user_role == 'admin' else
                'Personel' if user_role == 'worker' else
                'Yönetici Yardımcısı' if user_role == 'manager' else
                'Ziyaretçi'
            ),
            'Tarayıcı': get_browser_info(),
            'İşletim Sistemi': get_platform_info(),
            'Gelinen Sayfa': extract_page_from_referrer(request.referrer)
        }

        if details:
            if isinstance(details, dict):
                # details içindeki key-value'ları extended_details'e ekle
                extended_details.update({
                    k.replace('_', ' ').title(): v
                    for k, v in details.items()
                })
            else:
                extended_details['Ek Detaylar'] = details

        try:
            new_log = UserLog(
                user_id=user_id,
                action=action,  # DB'de ham halde saklanır, 'UPDATE: product_list'
                details=json.dumps(extended_details, ensure_ascii=False),
                ip_address=request.remote_addr,
                page_url=request.url
            )
            db.session.add(new_log)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logging.error(f"Log kaydedilemedi: {e}")

@user_logs_bp.route('/user-logs')
@roles_required('admin', 'manager')
def view_logs():
    page = request.args.get('page', 1, type=int)
    per_page = 50

    user_id = request.args.get('user_id', type=int)
    action_filter = request.args.get('action', type=str)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    keyword = request.args.get('keyword', type=str)

    query = UserLog.query.join(User)

    if user_id:
        query = query.filter(UserLog.user_id == user_id)
    if action_filter:
        query = query.filter(UserLog.action.ilike(f'%{action_filter}%'))
    if keyword:
        query = query.filter(UserLog.details.ilike(f'%{keyword}%'))

    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(UserLog.timestamp >= start_date)
    except ValueError as ve:
        logging.error(f"Başlangıç tarihi hatalı: {ve}")

    try:
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(UserLog.timestamp <= end_date)
    except ValueError as ve:
        logging.error(f"Bitiş tarihi hatalı: {ve}")

    logs = query.order_by(UserLog.timestamp.desc()).paginate(page=page, per_page=per_page)
    for log in logs.items:
        try:
            log.details_dict = json.loads(log.details) if log.details else {}
        except Exception as e:
            log.details_dict = {}
            logging.error(f"Log detayları yüklenemedi: {e}")

    users = User.query.all()
    return render_template('user_logs.html', logs=logs, users=users)


import io
import pandas as pd
from flask import send_file

@user_logs_bp.route('/user-logs/export', methods=['GET'])
@roles_required('admin', 'manager')
def export_logs():
    """
    Kullanıcı loglarını filtreye göre Excel'e aktaran endpoint.
    """
    user_id = request.args.get('user_id', type=int)
    action_filter = request.args.get('action')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    keyword = request.args.get('keyword', type=str)

    query = UserLog.query.join(User)

    # Filtreler
    if user_id:
        query = query.filter(UserLog.user_id == user_id)
    if action_filter:
        query = query.filter(UserLog.action.ilike(f'%{action_filter}%'))
    if keyword:
        query = query.filter(UserLog.details.ilike(f'%{keyword}%'))

    # Tarih
    from datetime import datetime, timedelta
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(UserLog.timestamp >= start_date)
    except ValueError:
        pass

    try:
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(UserLog.timestamp <= end_date)
    except ValueError:
        pass

    # Veriyi çek
    logs = query.order_by(UserLog.timestamp.desc()).all()

    # DataFrame'e çevir
    data = []
    for log in logs:
        try:
            details_dict = json.loads(log.details) if log.details else {}
        except:
            details_dict = {}

        data.append({
            "Tarih": log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            "Kullanıcı": log.user.username,
            "IP": log.ip_address,
            "Ham Aksiyon": log.action,
            "Açıklama": details_dict.get('İşlem', ''),
            "Sayfa": details_dict.get('Sayfa', ''),
            **{k: str(v) for k, v in details_dict.items()
               if k not in ['İşlem','Sayfa']}
        })

    # Excel oluştur
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df = pd.DataFrame(data)
        df.to_excel(writer, index=False, sheet_name='Loglar')

    output.seek(0)
    return send_file(output, download_name='kullanici_loglari.xlsx', as_attachment=True)
