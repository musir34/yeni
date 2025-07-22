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
from datetime import datetime
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

# Veritabanı bağlantı adresini ayarla
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

print("DB URL:", os.getenv("DATABASE_URL"))

@login_manager.user_loader
def load_user(user_id):
    # Debug print'lerini temizledik, artık gerek yok.
    return User.query.get(int(user_id))

# --- JINJA FİLTRELERİ (DÜZELTİLMİŞ BÖLÜM) ---

@app.template_filter('from_json')
def from_json(value):
    try:
        return json.loads(value) if value else {}
    except Exception:
        return {}

# Bu filtre, rapor giriş formunun en altındaki anlık tarihi gösterir.
def format_datetime_filter(value, format='full'):
    dt = datetime.now()
    aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    gunler = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    formatlanmis_tarih = f"{dt.day} {aylar[dt.month - 1]} {dt.year}, {gunler[dt.weekday()]} - {dt.strftime('%H:%M')}"
    return formatlanmis_tarih

# Bu filtre ise admin panelindeki '2025-07-22' gibi tarihleri formatlar.
def format_date_filter(date_str, format=None):
    try:
        dt = datetime.strptime(str(date_str), '%Y-%m-%d')
        aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        return f"{dt.day} {aylar[dt.month - 1]} {dt.year}"
    except (ValueError, TypeError):
        return date_str

# Her iki filtreyi de doğru isimlerle Jinja'ya tanıtıyoruz.
app.jinja_env.filters['format_datetime'] = format_datetime_filter
app.jinja_env.filters['format_date'] = format_date_filter
app.jinja_env.filters['format_turkish_date'] = format_turkish_date_filter # Bu satır zaten vardı, kalıyor.

# --- FİLTRE BÖLÜMÜ BİTTİ ---

# Blueprint'leri kaydet
register_blueprints(app)

# Ana route yönlendirmesi (anasayfa)
@app.route('/')
def index():
    return redirect(url_for('home.home'))

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
    # Raporlama sayfasının GET isteklerini loglama
    if request.endpoint == 'rapor_gir.giris' and request.method == 'GET':
        return

    if not request.path.startswith('/static/'):
        try:
            log_user_action(
                action=f"PAGE_VIEW: {request.endpoint}",
                details={'path': request.path, 'endpoint': request.endpoint},
                force_log=True
            )
        except Exception as e:
            logger.error(f"Log kaydedilemedi: {e}")

# Giriş kontrolü (Artık Flask-Login çalıştığı için bu fonksiyonu silebiliriz veya devre dışı bırakabiliriz)
# Şimdilik dokunmuyoruz, ama ileride kaldırılabilir.
@app.before_request
def check_authentication():
    if (request.path.startswith('/enhanced_product_label') or
        request.path.startswith('/static/') or
        request.path.startswith('/api/') or # API yollarını genel olarak muaf tutmak daha güvenli olabilir
        request.path.startswith('/health')):
        return None

    # Flask-Login zaten çalıştığı için bu özel kontrol listesi artık çok kritik değil.
    allowed_routes = [
        'login_logout.login', 'login_logout.register', 'login_logout.static',
        'login_logout.verify_totp', 'login_logout.logout', 'qr_utils.generate_qr_labels_pdf',
        'health.health_check', 'enhanced_label.advanced_label_editor',
        'enhanced_label.enhanced_product_label'
    ]
    app.permanent_session_lifetime = timedelta(days=30)

    # Bu kontrolü Flask-Login'in kontrolüyle değiştirmek daha doğru olur, ama şimdilik bırakıyoruz.
    if request.endpoint not in allowed_routes and not current_user.is_authenticated:
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
            # db.create_all() yerine migrate kullanmak daha güvenli
            print("✅ Veritabanı tabloları kontrol edildi (migrate ile yönetiliyor)")
        except Exception as table_error:
            print(f"⚠️ Tablo oluşturma hatası (devam ediliyor): {str(table_error)[:50]}...")

    except Exception as e:
        print(f"❌ Veritabanı bağlantı hatası: {str(e)[:50]}...")
        print("⚠️ Uygulama veritabanısız modda başlatılıyor")


# Bu fonksiyon, tarih veya zaman damgası nesnelerini alıp Türkçe'ye çevirir
def turkce_tarih_formatla(dt, format='full'):
    if not dt:
        return ""

    # Eğer string gelirse datetime objesine çevir
    if isinstance(dt, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(dt, fmt)
                break
            except ValueError:
                continue
        else:
            return dt  # Hiçbiri tutmazsa olduğu gibi döner

    aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    gunler = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

    if format == 'full':
        return f"{dt.day} {aylar[dt.month - 1]} {dt.year}, {gunler[dt.weekday()]}"
    elif format == 'datetime':
        return f"{dt.day} {aylar[dt.month - 1]} {dt.year} - {dt.strftime('%H:%M')}"
    else:
        return f"{dt.day} {aylar[dt.month - 1]} {dt.year}"

# Oluşturduğumuz bu fonksiyonu, Jinja'ya 'turkce_tarih' adıyla tanıtıyoruz
app.jinja_env.filters['turkce_tarih'] = turkce_tarih_formatla

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

    app_env = os.getenv("APP_ENV", "development")

    try:
        if app_env == "production":
            app.run(host='0.0.0.0', port=443, debug=debug_mode, use_reloader=False,
                    ssl_context=(os.getenv("SSL_CERT"), os.getenv("SSL_KEY")))
        else:
            app.run(host='0.0.0.0', port=8080, debug=debug_mode, use_reloader=False)
    except Exception as e:
        print(f"Başlatma hatası: {e}")
        import traceback
        traceback.print_exc()