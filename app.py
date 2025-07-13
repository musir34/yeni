import os
import json
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta
from flask import Flask, request, url_for, redirect, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.routing import BuildError
from flask_login import LoginManager, current_user

from models import db, User
from archive import format_turkish_date_filter
from logger_config import app_logger as logger
from cache_config import cache, CACHE_TIMES
from flask_restx import Api
from routes import register_blueprints
from user_logs import log_user_action
from celery_app import init_celery
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text

# Flask Uygulamasını Başlat
app = Flask(__name__)

# Ortam yapılandırması
env = os.getenv('FLASK_ENV', 'development')
app.config.from_object(
    __import__('config').config_map.get(env, __import__('config').DevelopmentConfig)
)

# Veritabanı bağlantı adresini ayarla (en son yaz!)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Uzantıları başlat
cache.init_app(app)
db.init_app(app)
CORS(app)
celery = init_celery(app)

# Flask-Login ayarları
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_logout.login"

# DEBUG: Veritabanı bağlantı adresini logla
print("DB URL:", os.getenv("DATABASE_URL"))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Jinja filtreleri
@app.template_filter('from_json')
def from_json(value):
    try:
        return json.loads(value) if value else {}
    except Exception:
        return {}

app.jinja_env.filters['format_turkish_date'] = format_turkish_date_filter

# Blueprint'leri kaydet
register_blueprints(app)

# Ana route yönlendirmesi (anasayfa)
@app.route('/')
def index():
    return redirect(url_for('home.home'))  # 'home' blueprint içindeki 'home' fonksiyonu

# Flask-RESTX API
api = Api(app, title='Güllü Shoes API', version='1.0', doc='/docs')

# URL builder fallback
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

def safe_url_for(endpoint, **values):
    try:
        return custom_url_for(endpoint, **values)
    except Exception:
        return '#'

app.jinja_env.globals['safe_url_for'] = safe_url_for

# İstek loglama
@app.before_request
def log_request():
    if not request.path.startswith('/static/'):
        try:
            log_user_action(
                action=f"PAGE_VIEW: {request.endpoint}",
                details={'path': request.path, 'endpoint': request.endpoint},
                force_log=True
            )
        except Exception as e:
            logger.error(f"Log kaydedilemedi: {e}")

# Giriş kontrolü
@app.before_request
def check_authentication():
    if (request.path.startswith('/enhanced_product_label') or
        request.path.startswith('/static/') or
        request.path.startswith('/api/generate_advanced_label_preview') or
        request.path.startswith('/api/save_label_preset') or
        request.path.startswith('/api/generate_label_preview') or
        request.path.startswith('/health') or
        (request.endpoint and 'enhanced_label' in str(request.endpoint))):
        return None

    allowed_routes = [
        'login_logout.login',
        'login_logout.register',
        'login_logout.static',
        'login_logout.verify_totp',
        'login_logout.logout',
        'qr_utils.generate_qr_labels_pdf',
        'health.health_check',
        'enhanced_label.advanced_label_editor',
        'enhanced_label.enhanced_product_label'
    ]
    app.permanent_session_lifetime = timedelta(days=30)

    if request.endpoint not in allowed_routes:
        if 'username' not in session:
            flash('Lütfen giriş yapınız.', 'danger')
            return redirect(url_for('login_logout.login'))
        if 'pending_user' in session and request.endpoint != 'login_logout.verify_totp':
            return redirect(url_for('login_logout.verify_totp'))

# APScheduler – Arka planda cron job
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

# Veritabanı bağlantı testi
with app.app_context():
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("✅ Neon veritabanına bağlantı başarılı!")

        try:
            db.create_all()
            print("✅ Veritabanı tabloları kontrol edildi")
        except Exception as table_error:
            print(f"⚠️ Tablo oluşturma hatası (devam ediliyor): {str(table_error)[:50]}...")

    except Exception as e:
        print(f"❌ Veritabanı bağlantı hatası: {str(e)[:50]}...")
        print("⚠️ Uygulama veritabanısız modda başlatılıyor")

# Uygulama başlat
if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False') == 'True'

    if os.environ.get("RUN_DB_SETUP") == "True":
        try:
            from db_setup import run_setup
            run_setup()
        except Exception as e:
            logger.warning(f"Veritabanı kurulumu sırasında hata: {e}")

    print("Uygulama başlatılıyor...")
    try:
        app.run(
            host='0.0.0.0',
            port=443,
            debug=debug_mode,
            use_reloader=False,
            ssl_context=(
                '/home/musir/gullupanel/yeni/cert.pem',
                '/home/musir/gullupanel/yeni/key.pem'
            )
        )
    except Exception as e:
        print(f"Başlatma hatası: {e}")
        import traceback
        traceback.print_exc()
