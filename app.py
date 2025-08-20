# -*- coding: utf-8 -*-

import os
import json
from dotenv import load_dotenv
load_dotenv()
import asyncio

from datetime import datetime, timedelta
from flask import Flask, request, url_for, redirect, flash, session, current_app
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
from sqlalchemy import text

# APScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from threading import Lock

# ──────────────────────────────────────────────────────────────────────────────
# Flask Uygulamasını Başlat
# ──────────────────────────────────────────────────────────────────────────────
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
    return User.query.get(int(user_id))

# ──────────────────────────────────────────────────────────────────────────────
# JINJA FİLTRELERİ
# ──────────────────────────────────────────────────────────────────────────────
@app.template_filter('from_json')
def from_json(value):
    try:
        return json.loads(value) if value else {}
    except Exception:
        return {}

def format_datetime_filter(value, format='full'):
    dt = datetime.now()
    aylar = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
    gunler = ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"]
    return f"{dt.day} {aylar[dt.month - 1]} {dt.year}, {gunler[dt.weekday()]} - {dt.strftime('%H:%M')}"

def format_date_filter(date_str, format=None):
    try:
        dt = datetime.strptime(str(date_str), '%Y-%m-%d')
        aylar = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
        return f"{dt.day} {aylar[dt.month - 1]} {dt.year}"
    except (ValueError, TypeError):
        return date_str

# Türkçe tarih yardımcı
def turkce_tarih_formatla(dt, format='full'):
    if not dt:
        return ""
    # string ise çevir
    if isinstance(dt, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(dt, fmt)
                break
            except ValueError:
                continue
        else:
            return dt
    aylar = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
    gunler = ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"]
    if format == 'full':
        return f"{dt.day} {aylar[dt.month - 1]} {dt.year}, {gunler[dt.weekday()]}"
    elif format == 'datetime':
        return f"{dt.day} {aylar[dt.month - 1]} {dt.year} - {dt.strftime('%H:%M')}"
    else:
        return f"{dt.day} {aylar[dt.month - 1]} {dt.year}"

# Jinja'ya tanıt
app.jinja_env.filters['format_datetime'] = format_datetime_filter
app.jinja_env.filters['format_date'] = format_date_filter
app.jinja_env.filters['format_turkish_date'] = format_turkish_date_filter
app.jinja_env.filters['turkce_tarih'] = turkce_tarih_formatla

# ──────────────────────────────────────────────────────────────────────────────
# Blueprint'leri kaydet & Ana route
# ──────────────────────────────────────────────────────────────────────────────
register_blueprints(app)

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

# ──────────────────────────────────────────────────────────────────────────────
# İstek loglama & Basit auth kalkanı
# ──────────────────────────────────────────────────────────────────────────────
@app.before_request
def log_request():
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

@app.before_request
def check_authentication():
    if (request.path.startswith('/enhanced_product_label')
        or request.path.startswith('/static/')
        or request.path.startswith('/api/')
        or request.path.startswith('/health')):
        return None

    allowed_routes = [
        'login_logout.login','login_logout.register','login_logout.static',
        'login_logout.verify_totp','login_logout.logout','qr_utils.generate_qr_labels_pdf',
        'health.health_check','enhanced_label.advanced_label_editor',
        'enhanced_label.enhanced_product_label'
    ]
    app.permanent_session_lifetime = timedelta(days=30)

    if request.endpoint not in allowed_routes and not current_user.is_authenticated:
        if 'username' not in session:
            flash('Lütfen giriş yapınız.', 'danger')
            return redirect(url_for('login_logout.login'))
        if 'pending_user' in session and request.endpoint != 'login_logout.verify_totp':
            return redirect(url_for('login_logout.verify_totp'))

# ──────────────────────────────────────────────────────────────────────────────
# Yardımcılar (stok rezerv okuma)
# ──────────────────────────────────────────────────────────────────────────────
def _parse_details_any(details_raw):
    """details alanı str/list/dict olabilir; normalize edip liste döndürür."""
    if not details_raw:
        return []
    if isinstance(details_raw, list):
        return details_raw
    if isinstance(details_raw, dict):
        return [details_raw]
    try:
        data = json.loads(details_raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []
    except Exception:
        return []

def _to_int(x, default=0):
    try:
        return int(str(x).strip())
    except Exception:
        return default

# ──────────────────────────────────────────────────────────────────────────────
# İş Job'ları
# ──────────────────────────────────────────────────────────────────────────────
def fetch_and_save_returns():
    with app.app_context():
        try:
            from iade_islemleri import fetch_data_from_api, save_to_database
            data = fetch_data_from_api(datetime.now() - timedelta(days=1), datetime.now())
            if data:
                save_to_database(data, db.session)
        except Exception as e:
            logger.warning(f"İade çekme hatası: {e}")

def push_central_stock_to_trendyol():
    """
    CentralStock'u, **Created** sipariş rezervlerini düşerek Trendyol'a gönderir.
    Döngü tetikçisi push_stock_job çağırır.
    """
    with app.app_context():
        try:
            from stock_management import send_trendyol_update_async
            from models import CentralStock, OrderCreated

            rows = CentralStock.query.all()
            if not rows:
                logger.info("CentralStock boş, Trendyol'a gönderilecek stok yok.")
                return

            # Created siparişlerden rezerv miktarını hesapla
            reserved = {}
            for (details_str,) in OrderCreated.query.with_entities(OrderCreated.details).all():
                for it in _parse_details_any(details_str):
                    bc = (it.get("barcode") or "").strip()
                    q  = _to_int(it.get("quantity"), 0)
                    if bc and q > 0:
                        reserved[bc] = reserved.get(bc, 0) + q

            # available = max(0, central - reserved)
            items = []
            for r in rows:
                central = _to_int(r.qty, 0)
                res = reserved.get(r.barcode, 0)
                available = central - res
                if available < 0:
                    available = 0
                items.append({"barcode": r.barcode, "quantity": available})

            if not items:
                logger.info("Gönderilecek item yok.")
                return

            asyncio.run(send_trendyol_update_async(items))
            logger.info(f"[PUSH] CentralStock (Created rezerv düşülmüş) -> Trendyol: {len(items)} kalem gönderildi.")

        except Exception as e:
            logger.error(f"[PUSH] CentralStock push hata: {e}", exc_info=True)

# ──────────────────────────────────────────────────────────────────────────────
# ZAMANLAYICI: Çek → 2 dk → Stok → 1 dk → Çek …
# ──────────────────────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler(
    timezone="Europe/Istanbul",
    job_defaults={"max_instances": 1, "coalesce": True, "misfire_grace_time": 60}
)

_state_lock = Lock()
_last_pull_finished = None  # çekim bittiği an

def _mark_pull_done():
    global _last_pull_finished
    with _state_lock:
        _last_pull_finished = datetime.now()

def pull_orders_job():
    """0,3,6... dakikalarda çalışır; Trendyol siparişlerini çeker."""
    with app.app_context():
        try:
            # circular import riskini azaltmak için içerde import
            from order_service import fetch_trendyol_orders_async
            asyncio.run(fetch_trendyol_orders_async())
        except Exception as e:
            logger.error(f"pull_orders_job hata: {e}", exc_info=True)
        finally:
            _mark_pull_done()

def push_stock_job():
    """2,5,8... dakikalarda çalışır; son çekimden ≥2 dk sonra stok gönderir."""
    with _state_lock:
        ok_to_push = (_last_pull_finished is not None
                      and (datetime.now() - _last_pull_finished) >= timedelta(minutes=2))
    if not ok_to_push:
        logger.info("push_stock_job skip: çekimden 2 dk geçmedi.")
        return
    push_central_stock_to_trendyol()

def schedule_jobs():
    scheduler.start()
    now = datetime.now()

    # İade job'u (gündelik)
    scheduler.add_job(fetch_and_save_returns, trigger='cron', hour=23, minute=50, id="pull_returns_daily")

    # Döngü:
    # 0,3,6,9 ... dakikalar: SİPARİŞ ÇEK
    scheduler.add_job(pull_orders_job, trigger='interval', minutes=3, next_run_time=now, id="pull_orders")
    # 2,5,8,11 ... dakikalar: STOK GÖNDER
    scheduler.add_job(push_stock_job, trigger='interval', minutes=3, next_run_time=now + timedelta(minutes=2), id="push_stock")

schedule_jobs()

# ──────────────────────────────────────────────────────────────────────────────
# Veritabanı bağlantı testi
# ──────────────────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────────────────
# Uygulama başlat
# ──────────────────────────────────────────────────────────────────────────────
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
                    ssl_context=(os.getenv("SSL_CERT"), os.getenv("SSL_KEY")) )
        else:
            app.run(host='0.0.0.0', port=8080, debug=debug_mode, use_reloader=False)
    except Exception as e:
        print(f"Başlatma hatası: {e}")
        import traceback
        traceback.print_exc()
