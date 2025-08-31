# -*- coding: utf-8 -*-

import os
import json
from dotenv import load_dotenv
load_dotenv()
import asyncio
from datetime import datetime, timedelta

from flask import Flask, request, url_for, redirect, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.routing import BuildError
from flask_login import LoginManager, current_user
from archive import format_turkish_date_filter
from models import db, User, CentralStock  # OrderCreated içerden import edilecek
from logger_config import app_logger as logger
from cache_config import cache
from flask_restx import Api
from routes import register_blueprints
from user_logs import log_user_action
from celery_app import init_celery
from sqlalchemy import text
from trendyol_api import SUPPLIER_ID, API_KEY, API_SECRET
from apscheduler.schedulers.background import BackgroundScheduler  # <-- DOĞRU YER

# ──────────────────────────────────────────────────────────────────────────────
# Platform-safe lock import (Unix: fcntl, Windows: msvcrt+tempfile)
# ──────────────────────────────────────────────────────────────────────────────
try:
    import fcntl  # Unix
except ImportError:
    fcntl = None
    import msvcrt  # Windows
    import tempfile

# ──────────────────────────────────────────────────────────────────────────────
# Flask Uygulaması
# ──────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)

env = os.getenv('FLASK_ENV', 'development')
app.config.from_object(
    __import__('config').config_map.get(env, __import__('config').DevelopmentConfig)
)
import platform, os, time
os.environ['TZ'] = 'Europe/Istanbul'
if platform.system() in ('Linux', 'Darwin'):  # Windows'ta tzset yok
    try:
        time.tzset()
    except Exception:
        pass

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Jinja filtre kaydı
app.add_template_filter(format_turkish_date_filter, name='turkce_tarih')

cache.init_app(app)
db.init_app(app)
CORS(app)
celery = init_celery(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_logout.login"

print("DB URL:", os.getenv("DATABASE_URL"))

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

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

app.jinja_env.filters['format_datetime'] = format_datetime_filter
app.jinja_env.filters['format_date'] = format_turkish_date_filter

# ──────────────────────────────────────────────────────────────────────────────
# Blueprint & API
# ──────────────────────────────────────────────────────────────────────────────
register_blueprints(app)

@app.route('/')
def index():
    return redirect(url_for('home.home'))

api = Api(app, title='Güllü Shoes API', version='1.0', doc='/docs')

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

# ──────────────────────────────────────────────────────────────────────────────
# Request log & Basit auth kalkanı
# ──────────────────────────────────────────────────────────────────────────────
@app.before_request
def log_request():
    if request.path.startswith('/static/'):
        return
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
    allowed = [
        'login_logout.login','login_logout.register','login_logout.static',
        'login_logout.verify_totp','login_logout.logout','qr_utils.generate_qr_labels_pdf',
        'health.health_check','enhanced_label.advanced_label_editor',
        'enhanced_label.enhanced_product_label'
    ]
    app.permanent_session_lifetime = timedelta(days=30)
    if request.endpoint not in allowed and not current_user.is_authenticated:
        flash('Lütfen giriş yapınız.', 'danger')
        return redirect(url_for('login_logout.login'))

# ──────────────────────────────────────────────────────────────────────────────
# İşlevler: İade Çekme • Sipariş Çekme • Stok Push
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

def pull_orders_job():
    """Siparişleri Trendyol'dan çeker (Created rezervleri sistemde güncellenir)."""
    with app.app_context():
        try:
            from order_service import fetch_trendyol_orders_async
            asyncio.run(fetch_trendyol_orders_async())
        except Exception as e:
            logger.error(f"pull_orders_job hata: {e}", exc_info=True)

def push_central_stock_to_trendyol():
    """
    CentralStock (Created rezerv düşülmüş) → Trendyol
    POST /sapigw/suppliers/{SUPPLIER_ID}/products/price-and-inventory
    """
    with app.app_context():
        import base64, aiohttp, asyncio, math
        from models import OrderCreated

        def _parse(raw):
            try:
                if not raw: return []
                d = json.loads(raw) if isinstance(raw, str) else raw
                return d if isinstance(d, list) else [d]
            except Exception:
                return []

        def _i(x, d=0):
            try:
                return int(str(x).strip())
            except Exception:
                return d

        rows = CentralStock.query.all()
        if not rows:
            logger.info("[PUSH] CentralStock boş; gönderim yok.")
            return

        # Created rezerv toplamı
        reserved = {}
        for (details_str,) in OrderCreated.query.with_entities(OrderCreated.details).all():
            for it in _parse(details_str):
                bc = (it.get("barcode") or "").strip()
                q  = _i(it.get("quantity"), 0)
                if bc and q > 0:
                    reserved[bc] = reserved.get(bc, 0) + q

        # available = central - reserved
        items = []
        for r in rows:
            available = max(0, _i(r.qty, 0) - reserved.get(r.barcode, 0))
            items.append({"barcode": r.barcode.strip(), "quantity": available})

        if not items:
            logger.info("[PUSH] Gönderilecek kalem yok.")
            return

        url = f"https://api.trendyol.com/sapigw/suppliers/{SUPPLIER_ID}/products/price-and-inventory"
        auth = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"GulluAyakkabiApp-V2/{SUPPLIER_ID}"
        }

        BATCH_SIZE = 100
        total = len(items)
        parts = math.ceil(total / BATCH_SIZE)
        logger.info(f"[PUSH] price-and-inventory gönderiliyor: {total} kalem, {parts} paket")

        async def _run():
            async with aiohttp.ClientSession() as session:
                for i in range(0, total, BATCH_SIZE):
                    batch = items[i:i+BATCH_SIZE]
                    payload = {"items": [{"barcode": it["barcode"], "quantity": max(0, int(it["quantity"]))}
                                         for it in batch if it.get("barcode")]}
                    async with session.post(url, headers=headers, json=payload, timeout=60) as resp:
                        body = await resp.text()
                        logger.info(f"[PINV {i//BATCH_SIZE+1}/{parts}] {resp.status} {body[:200]}")
                    await asyncio.sleep(0.4)

        try:
            asyncio.run(_run())
            logger.info("[PUSH] price-and-inventory tamamlandı.")
        except Exception as e:
            logger.error(f"[PUSH] Hata: {e}", exc_info=True)

def push_stock_job():
    """Zamanlayıcı tetiklemesinde direkt stok gönderir (zamanlamayı schedule ayarlar)."""
    push_central_stock_to_trendyol()

# ──────────────────────────────────────────────────────────────────────────────
# Zamanlayıcı (ENV kontrollü) — ÇEK (0dk) ↔ PUSHA (2dk) ping-pong + iade cron
# ──────────────────────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler(
    timezone="Europe/Istanbul",
    job_defaults={"max_instances": 1, "coalesce": True, "misfire_grace_time": 60}
)

# ENV bayrakları
# DISABLE_JOBS=1  -> tüm job'lar kapalı (local test için birebir)
# DISABLE_JOBS_IDS=pull_orders,push_stock -> seçili job'lar kapalı (virgülle ayır)
ENABLE_JOBS = str(os.getenv("DISABLE_JOBS", "0")).lower() not in ("1", "true", "yes")
DISABLED_IDS = set([s.strip() for s in os.getenv("DISABLE_JOBS_IDS", "").split(",") if s.strip()])

# Gunicorn veya zorla çalıştırma bayrağı
is_gunicorn = "gunicorn" in os.environ.get("SERVER_SOFTWARE", "").lower() \
              or "GUNICORN_CMD_ARGS" in os.environ
force_sched = os.getenv("FORCE_SCHEDULER", "0").lower() in ("1", "true", "yes")

# Eski satırın yerine bu satırı kullan:
is_main_proc = force_sched or is_gunicorn or (not app.debug) or (os.getenv("WERKZEUG_RUN_MAIN") == "true")

# Çoklu worker’da yalnız 1 süreç scheduler/push çalıştırsın (leader lock)
_leader_fd = None          # Unix
_leader_handle = None      # Windows

def become_leader(lock_path=None):
    """
    Unix: fcntl ile non-blocking file lock
    Windows: msvcrt.locking ile lock
    """
    global _leader_fd, _leader_handle

    if os.name == "nt":  # Windows
        if lock_path is None:
            lock_path = os.path.join(tempfile.gettempdir(), "gullupanel_leader.lock")
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        if not os.path.exists(lock_path):
            open(lock_path, "wb").close()
        try:
            _leader_handle = open(lock_path, "r+b")
            msvcrt.locking(_leader_handle.fileno(), msvcrt.LK_NBLCK, 1)  # 1 byte lock
            return True
        except OSError:
            if _leader_handle:
                try: _leader_handle.close()
                except: pass
                _leader_handle = None
            return False

    # Unix (Linux/macOS)
    lock_path = lock_path or "/tmp/gullupanel_leader.lock"
    _leader_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(_leader_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (BlockingIOError, OSError):
        try: os.close(_leader_fd)
        except: pass
        _leader_fd = None
        return False

def _add_job_safe(func, *, trigger, id, **kw):
    if id in DISABLED_IDS:
        logger.info(f"Job disabled by DISABLE_JOBS_IDS: {id}")
        return
    scheduler.add_job(func, trigger=trigger, id=id, **kw)

def schedule_jobs():
    now = datetime.now()

    # ÇEK: hemen başla, her 4 dk
    _add_job_safe(
        pull_orders_job,
        trigger='interval',
        id="pull_orders",
        minutes=4,
        next_run_time=now
    )

    # PUSHA: 2 dk sonra başla, her 4 dk (çek ile ping-pong)
    _add_job_safe(
        push_stock_job,
        trigger='interval',
        id="push_stock",
        minutes=4,
        next_run_time=now + timedelta(minutes=2)
    )

    # İade: her gece 23:50
    _add_job_safe(
        fetch_and_save_returns,
        trigger='cron',
        id="pull_returns_daily",
        hour=23,
        minute=50
    )

# ENV ve liderlik kontrolü
_leader_ok = False
if ENABLE_JOBS and is_main_proc:
    _leader_ok = become_leader()
    if _leader_ok:
        scheduler.start()
        schedule_jobs()
        # GÖREV JOBLARI (scheduler start edildikten sonra ekle)
        from gorev import attach_jobs
        attach_jobs(scheduler)
        logger.info("Scheduler started (ENABLE_JOBS=on, leader ok).")
    else:
        logger.info("Scheduler NOT started (ENABLE_JOBS=on, leader=false)")
else:
    logger.info(
        "Scheduler NOT started (ENABLE_JOBS=%s, is_main_proc=%s, leader=%s)",
        ENABLE_JOBS, is_main_proc, _leader_ok
    )

# ──────────────────────────────────────────────────────────────────────────────
# DB bağlantı testi
# ──────────────────────────────────────────────────────────────────────────────
with app.app_context():
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("✅ Neon veritabanına bağlantı başarılı!")
        print("✅ Veritabanı tabloları kontrol edildi (migrate ile yönetiliyor)")
    except Exception as e:
        print(f"❌ Veritabanı bağlantı hatası: {str(e)[:50]}...")
        print("⚠️ Uygulama veritabanısız modda başlatılıyor")

# ──────────────────────────────────────────────────────────────────────────────
# Main
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
