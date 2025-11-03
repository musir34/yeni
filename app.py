# -*- coding: utf-8 -*-

import os
import json
import time  # 🔧 time.time() için eklendi
from dotenv import load_dotenv
load_dotenv()
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  # 🔧 Timezone için eklendi

from flask import Flask, request, url_for, redirect, flash, session, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.routing import BuildError
from flask_login import LoginManager, current_user
from archive import format_turkish_date_filter
from models import db, User, CentralStock, StockPushLog  # OrderCreated içerden import edilecek
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

# >>>>>> BURAYA EKLENDİ (register_blueprints'ten önce) <<<<<<
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config.setdefault('UPLOAD_FOLDER', os.path.join(BASE_DIR, 'uploads', 'receipts'))
app.config.setdefault('ALLOWED_IMAGE_EXTENSIONS', {'png', 'jpg', 'jpeg', 'webp', 'heic', 'heif'})
app.config.setdefault('MAX_CONTENT_LENGTH', 10 * 1024 * 1024)  # 10 MB
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

import platform, os, time
from zoneinfo import ZoneInfo

# Türkiye saati için timezone ayarı
os.environ['TZ'] = 'Europe/Istanbul'
if platform.system() in ('Linux', 'Darwin'):  # Windows'ta tzset yok
    try:
        time.tzset()
    except Exception:
        pass

# İstanbul timezone objesi
IST = ZoneInfo("Europe/Istanbul")

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
    """Türkiye saati ile tarih formatı"""
    from weather_service import get_istanbul_time
    dt = get_istanbul_time()
    
    aylar = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
    gunler = ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"]
    
    if format == 'full':
        return f"{dt.day} {aylar[dt.month - 1]} {dt.year}, {gunler[dt.weekday()]} - {dt.strftime('%H:%M:%S')}"
    elif format == 'short':
        return f"{dt.strftime('%d.%m.%Y %H:%M')}"
    elif format == 'time':
        return f"{dt.strftime('%H:%M:%S')}"
    else:
        return f"{dt.strftime('%d/%m/%Y')}"

app.jinja_env.filters['format_datetime'] = format_datetime_filter
app.jinja_env.filters['format_date'] = format_turkish_date_filter

# ──────────────────────────────────────────────────────────────────────────────
# Blueprint & API
# ──────────────────────────────────────────────────────────────────────────────
register_blueprints(app)

# >>> Forecast cache fonksiyonlarını blueprint yüklendikten sonra import et
try:
    # Eğer uretim_oneri blueprint'in kök dizindeyse:
    from uretim_oneri import forecast_worker_loop, rebuild_daily_sales
except Exception:
    # routes paketinde ise:
    from routes.uretim_oneri import forecast_worker_loop, rebuild_daily_sales

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
    if request.path.startswith('/api/'):
        return  # API isteklerini loglama
    try:
        endpoint_name = request.endpoint or 'bilinmeyen'
        log_user_action(
            action=f'PAGE_VIEW: {endpoint_name}',
            details={
                'yol': request.path,
                'metod': request.method
            },
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
# Global Error Handlers
# ──────────────────────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found_error(error):
    """404 - Sayfa Bulunamadı"""
    logger.warning(f"404 Hatası - Yol: {request.path}, IP: {request.remote_addr}")
    if request.path.startswith('/api/'):
        return {'error': 'Endpoint bulunamadı', 'path': request.path}, 404
    return render_template('errors/404.html'), 404

@app.errorhandler(403)
def forbidden_error(error):
    """403 - Yetkisiz Erişim"""
    logger.warning(f"403 Hatası - Kullanıcı: {current_user.username if current_user.is_authenticated else 'Anonim'}, Yol: {request.path}")
    if request.path.startswith('/api/'):
        return {'error': 'Bu işlem için yetkiniz yok', 'path': request.path}, 403
    return render_template('errors/403.html'), 403

@app.errorhandler(500)
def internal_error(error):
    """500 - Sunucu Hatası"""
    import uuid
    error_id = str(uuid.uuid4())[:8]
    logger.error(f"500 Hatası [ID: {error_id}] - Yol: {request.path}, Kullanıcı: {current_user.username if current_user.is_authenticated else 'Anonim'}", exc_info=True)
    db.session.rollback()  # Veritabanı işlemini geri al
    if request.path.startswith('/api/'):
        return {'error': 'Sunucu hatası oluştu', 'error_id': error_id}, 500
    return render_template('errors/500.html', error_id=error_id), 500

@app.errorhandler(Exception)
def handle_exception(error):
    """Tüm yakalanmamış hataları yakala"""
    import uuid
    error_id = str(uuid.uuid4())[:8]
    
    # 404, 403, 500 gibi HTTP hataları için özel handler'ları kullan
    if hasattr(error, 'code'):
        if error.code == 404:
            return not_found_error(error)
        elif error.code == 403:
            return forbidden_error(error)
        elif error.code == 500:
            return internal_error(error)
    
    # Diğer tüm hatalar için genel handler
    logger.error(f"Beklenmeyen Hata [ID: {error_id}] - Yol: {request.path}, Tip: {type(error).__name__}, Mesaj: {str(error)}", exc_info=True)
    db.session.rollback()
    
    if request.path.startswith('/api/'):
        return {
            'error': 'Beklenmeyen bir hata oluştu',
            'error_id': error_id,
            'type': type(error).__name__
        }, 500
    return render_template('errors/500.html', error_id=error_id), 500

# ──────────────────────────────────────────────────────────────────────────────
# Favicon Route
# ──────────────────────────────────────────────────────────────────────────────
@app.route('/favicon.ico')
def favicon():
    """Favicon için özel route"""
    from flask import send_from_directory
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

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
    🔄 CentralStock'tan Trendyol'a stok gönderimi
    
    MANTIK:
    1. OrderCreated (Yeni) siparişler → REZERVE sayılır (stoktan düşülmez)
    2. Available Stock = CentralStock.qty - OrderCreated rezerv
    3. Trendyol'a bu "müsait stok" gönderilir
    4. OrderPicking'e geçen siparişler → CentralStock'tan düşülür (update_service.py)
    
    ZAMANLAMA: Her 5-10 dakikada bir otomatik çalışır
    LOG: StockPushLog tablosuna detay kaydedilir
    """
    start_time = time.time()
    push_success = False
    error_msg = None
    
    with app.app_context():
        import base64, aiohttp, asyncio, math
        from models import OrderCreated, StockPushLog

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

        try:
            rows = CentralStock.query.all()
            if not rows:
                logger.info("[PUSH] CentralStock boş; gönderim yok.")
                # Boş gönderim de log'a yazalım
                log = StockPushLog(
                    total_items=0,
                    total_quantity=0,
                    reserved_quantity=0,
                    batch_count=0,
                    success=True,
                    duration_seconds=time.time() - start_time
                )
                db.session.add(log)
                db.session.commit()
                return

            # 1️⃣ Created (Yeni) siparişlerdeki REZERV hesapla
            reserved = {}
            total_reserved = 0
            for (details_str,) in OrderCreated.query.with_entities(OrderCreated.details).all():
                for it in _parse(details_str):
                    bc = (it.get("barcode") or "").strip()
                    q  = _i(it.get("quantity"), 0)
                    if bc and q > 0:
                        reserved[bc] = reserved.get(bc, 0) + q
                        total_reserved += q

            logger.info(f"[PUSH] 📦 Toplam rezerv (Created siparişler): {total_reserved} adet, {len(reserved)} farklı barkod")

            # 2️⃣ Available = CentralStock - Reserved
            items = []
            total_qty = 0
            barcode_to_obj = {}  # Barkod -> CentralStock object mapping
            for r in rows:
                central_qty = _i(r.qty, 0)
                reserved_qty = reserved.get(r.barcode, 0)
                available = max(0, central_qty - reserved_qty)
                items.append({"barcode": r.barcode.strip(), "quantity": available})
                total_qty += available
                barcode_to_obj[r.barcode.strip()] = r  # Sonra update için

            if not items:
                logger.info("[PUSH] Gönderilecek kalem yok.")
                log = StockPushLog(
                    total_items=0,
                    total_quantity=0,
                    reserved_quantity=total_reserved,
                    batch_count=0,
                    success=True,
                    duration_seconds=time.time() - start_time
                )
                db.session.add(log)
                db.session.commit()
                return

            # 3️⃣ Trendyol API'ye gönder
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
            logger.info(f"[PUSH] 🚀 Trendyol'a gönderiliyor: {total} ürün ({total_qty} adet), {parts} batch")

            async def _run():
                async with aiohttp.ClientSession() as session:
                    for i in range(0, total, BATCH_SIZE):
                        batch = items[i:i+BATCH_SIZE]
                        payload = {"items": [{"barcode": it["barcode"], "quantity": max(0, int(it["quantity"]))}
                                             for it in batch if it.get("barcode")]}
                        async with session.post(url, headers=headers, json=payload, timeout=60) as resp:
                            body = await resp.text()
                            status_icon = "✅" if resp.status == 200 else "❌"
                            logger.info(f"[PUSH {status_icon}] Batch {i//BATCH_SIZE+1}/{parts}: {resp.status} - {body[:200]}")
                            if resp.status != 200:
                                raise Exception(f"API Hatası: {resp.status} - {body}")
                        await asyncio.sleep(0.4)

            asyncio.run(_run())
            push_success = True
            
            # 4️⃣ Gönderilen her barkodun last_push_date'ini güncelle
            push_time = datetime.now(ZoneInfo("Europe/Istanbul"))
            for item in items:
                barcode = item["barcode"]
                if barcode in barcode_to_obj:
                    barcode_to_obj[barcode].last_push_date = push_time
            db.session.commit()
            
            logger.info("[PUSH] ✅ Trendyol stok güncellemesi BAŞARILI!")

        except Exception as e:
            push_success = False
            error_msg = str(e)
            logger.error(f"[PUSH] ❌ Hata: {e}", exc_info=True)

        finally:
            # 4️⃣ Log kaydı oluştur
            duration = time.time() - start_time
            log = StockPushLog(
                total_items=len(items) if 'items' in locals() else 0,
                total_quantity=total_qty if 'total_qty' in locals() else 0,
                reserved_quantity=total_reserved if 'total_reserved' in locals() else 0,
                batch_count=parts if 'parts' in locals() else 0,
                success=push_success,
                error_message=error_msg,
                duration_seconds=duration
            )
            db.session.add(log)
            db.session.commit()
            logger.info(f"[PUSH] 📝 Log kaydedildi: {len(items) if 'items' in locals() else 0} ürün, {duration:.2f}s")

def push_stock_job():
    """Zamanlayıcı tetiklemesinde direkt stok gönderir (zamanlamayı schedule ayarlar)."""
    push_central_stock_to_trendyol()

# ──────────────────────────────────────────────────────────────────────────────
# Forecast cache wrapper'ları (app context ile)
# ──────────────────────────────────────────────────────────────────────────────
def _run_fcache_loop():
    with app.app_context():
        # 14 günlük cache, her döngüde 50 barkod
        forecast_worker_loop(days=14, batch=50)

def _nightly_rebuild():
    with app.app_context():
        # DailySales gece güvenlik senkronu (son 30 gün)
        rebuild_daily_sales(days=30)

# ──────────────────────────────────────────────────────────────────────────────
# Zamanlayıcı (ENV kontrollü) — ÇEK (0dk) ↔ PUSHA (2dk) ping-pong + iade cron + forecast jobs
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

    # PUSHA: 3 dk sonra başla, her 10 dakikada (stok senkronizasyonu)
    _add_job_safe(
        push_stock_job,
        trigger='interval',
        id="push_stock",
        minutes=10,  # 🔧 10 dakikada bir stok gönder
        next_run_time=now + timedelta(minutes=3)
    )

    # İade: her gece 23:50
    _add_job_safe(
        fetch_and_save_returns,
        trigger='cron',
        id="pull_returns_daily",
        hour=23,
        minute=50
    )

    # >>> Forecast cache worker: her 10 saniye
    _add_job_safe(
        _run_fcache_loop,
        trigger='interval',
        id="fcache_loop",
        seconds=30
    )

    # >>> DailySales gece rebuild: her gece 03:10
    _add_job_safe(
        _nightly_rebuild,
        trigger='cron',
        id="daily_sales_rebuild",
        hour=3,
        minute=10
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
        attach_jobs(scheduler, app)
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