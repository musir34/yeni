# ===================== EN ÜST KISIM =====================sadsad

import os
import json
import logging
from datetime import datetime, timedelta
from flask import Flask, request, url_for, redirect, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.routing import BuildError
from flask_login import LoginManager, current_user
from models import db, User
from archive import format_turkish_date_filter, archive_bp

# ✅ Redis cache config
import cache_config
from cache_config import CACHE_TIMES  # CACHE_TIMES gerekiyorsa


# Logging Ayarı
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Flask Uygulamasını Oluştur
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'varsayılan_anahtar')

# ✅ Redis cache başlat
cache = cache_config.cache
cache.init_app(app)

# Veritabanı Bağlantı Ayarı (Neon PostgreSQL için)
DATABASE_URI = os.environ.get(
    'DATABASE_URL',
    'postgresql://neondb_owner:npg_Z0a3kSwtrOJf@ep-cool-bonus-a64bzq6f.us-west-2.aws.neon.tech/neondb?sslmode=require'
)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Uzantıları Başlat
db.init_app(app)
CORS(app)

# Flask-Login Ayarları
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_logout.login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Jinja2 Template Filtresi
@app.template_filter('from_json')
def from_json(value):
    try:
        return json.loads(value) if value else {}
    except Exception:
        return {}

# ✅ Düzeltme: Jinja filtresini app'in jinja_env'ine kaydet
app.jinja_env.filters['format_turkish_date'] = format_turkish_date_filter


# Blueprint'leri Yükle
from siparisler import siparisler_bp
from product_service import product_service_bp
from claims_service import claims_service_bp
from order_service import order_service_bp
from update_service import update_service_bp
# from archive import archive_bp # Artık yukarıda import edildi
from order_list_service import order_list_service_bp
from login_logout import login_logout_bp
from degisim import degisim_bp
from home import home_bp
from get_products import get_products_bp
from all_orders_service import all_orders_service_bp
from new_orders_service import new_orders_service_bp, qr_utils_bp # qr_utils_bp de import edildi
from processed_orders_service import processed_orders_service_bp
from iade_islemleri import iade_islemleri
from siparis_fisi import siparis_fisi_bp
from analysis import analysis_bp
from stock_report import stock_report_bp
from openai_service import openai_bp
from user_logs import user_logs_bp, log_user_action
from commission_update_routes import commission_update_bp
from profit import profit_bp
from stock_management import stock_management_bp
from catalog import catalog_bp

blueprints = [
    order_service_bp,
    update_service_bp,
    archive_bp, # archive_bp artık yukarıda import edildi
    order_list_service_bp,
    login_logout_bp,
    degisim_bp,
    home_bp,
    get_products_bp,
    all_orders_service_bp,
    new_orders_service_bp,
    qr_utils_bp, # qr_utils_bp app'e kaydedildi
    processed_orders_service_bp,
    iade_islemleri,
    siparis_fisi_bp,
    analysis_bp,
    stock_report_bp,
    openai_bp,
    siparisler_bp,
    product_service_bp,
    claims_service_bp,
    user_logs_bp,
    commission_update_bp,
    stock_management_bp,
    profit_bp,
    catalog_bp,
]

for bp in blueprints:
    app.register_blueprint(bp)

# URL çözümleme hatalarında fallback
def custom_url_for(endpoint, **values):
    try:
        return url_for(endpoint, **values)
    except BuildError:
        if '.' not in endpoint:
            for blueprint in app.blueprints.values():
                try:
                    return url_for(f"{blueprint.name}.{endpoint}", **values)
                except BuildError:
                    continue
        raise BuildError(endpoint, values, method=None)

app.jinja_env.globals['url_for'] = custom_url_for

# İstek Loglama
@app.before_request
def log_request():
    if not request.path.startswith('/static/'):
        log_user_action(
            action=f"PAGE_VIEW: {request.endpoint}",
            details={'path': request.path, 'endpoint': request.endpoint},
            force_log=True
        )

# Giriş Kontrolü
@app.before_request
def check_authentication():
    allowed_routes = [
        'login_logout.login',
        'login_logout.register',
        'login_logout.static',
        'login_logout.verify_totp',
        'login_logout.logout',
        'qr_utils.generate_qr_labels_pdf' # QR PDF route'una geçici olarak izin ver
    ]
    app.permanent_session_lifetime = timedelta(days=30)
    if request.endpoint not in allowed_routes:
        if 'username' not in session:
            flash('Lütfen giriş yapınız.', 'danger')
            return redirect(url_for('login_logout.login'))
        if 'pending_user' in session and request.endpoint != 'login_logout.verify_totp':
            return redirect(url_for('login_logout.verify_totp'))

# APScheduler - Arka Planda Cron İşleri
from apscheduler.schedulers.background import BackgroundScheduler

def fetch_and_save_returns():
    with app.app_context():
        try:
            from iade_islemleri import fetch_data_from_api, save_to_database
            data = fetch_data_from_api(datetime.now() - timedelta(days=1), datetime.now())
            if data:
                save_to_database(data, db.session)
        except Exception as e:
            logger.warning(f"İade çekme hatası: {e}")

def schedule_jobs():
    scheduler = BackgroundScheduler(timezone="Europe/Istanbul")
    scheduler.add_job(func=fetch_and_save_returns, trigger='cron', hour=23, minute=50)
    scheduler.start()

schedule_jobs()

# 🔍 Veritabanı Bağlantı Testi
with app.app_context():
    try:
        with db.engine.connect() as connection:
            connection.execute(db.text("SELECT 1"))
            connection.commit()
        print("✅ Neon veritabanına bağlantı başarılı!")
    except Exception as e:
        print("❌ Veritabanı bağlantı hatası:", e)

# Uygulama Başlat - Opsiyonel Setup
if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False') == 'True'

    if os.environ.get("RUN_DB_SETUP") == "True":
        try:
            from db_setup import run_setup
            run_setup()
        except Exception as e:
            logger.warning(f"Veritabanı kurulumu sırasında hata: {e}")

    print("Uygulama başlatılıyor...")
    app.run(host='0.0.0.0', port=8080, debug=debug_mode)