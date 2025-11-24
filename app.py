# -*- coding: utf-8 -*-

import os
import json
from dotenv import load_dotenv
load_dotenv()
import asyncio
from datetime import datetime, timedelta

from flask import Flask, request, url_for, redirect, flash, session, render_template
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
    CentralStock (Created rezerv düşülmüş) → Trendyol
    POST /sapigw/suppliers/{SUPPLIER_ID}/products/price-and-inventory
    """
    with app.app_context():
        import base64, aiohttp, asyncio, math
        from models import OrderCreated

        logger.info("=" * 80)
        logger.info("[PUSH] 🚀 Stok gönderme işlemi başlatıldı")
        logger.info(f"[PUSH] ⏰ Zaman: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')}")
        
        def _parse(raw):
            try:
                if not raw: return []
                d = json.loads(raw) if isinstance(raw, str) else raw
                return d if isinstance(d, list) else [d]
            except Exception as e:
                logger.warning(f"[PUSH] ⚠️ JSON parse hatası: {e}")
                return []

        def _i(x, d=0):
            try:
                return int(str(x).strip())
            except Exception:
                return d

        # 1. CentralStock Kontrolü
        logger.info("[PUSH] 📦 Step 1: CentralStock verisi okunuyor...")
        rows = CentralStock.query.all()
        logger.info(f"[PUSH] 📊 CentralStock'ta {len(rows)} kayıt bulundu")
        
        if not rows:
            logger.warning("[PUSH] ⚠️ CentralStock boş; gönderim yapılamadı!")
            return

        # İlk 5 kaydı örnek göster
        if rows:
            logger.info("[PUSH] 📋 İlk 5 CentralStock örneği:")
            for idx, r in enumerate(rows[:5], 1):
                logger.info(f"[PUSH]   {idx}. Barkod: {r.barcode}, Miktar: {r.qty}")

        # 2. Created Rezerv Hesaplama
        logger.info("[PUSH] 🔒 Step 2: Created siparişler rezerv hesaplanıyor...")
        reserved = {}
        created_orders = OrderCreated.query.with_entities(OrderCreated.details).all()
        logger.info(f"[PUSH] 📦 {len(created_orders)} adet Created sipariş bulundu")
        
        total_reserved_items = 0
        for (details_str,) in created_orders:
            for it in _parse(details_str):
                bc = (it.get("barcode") or "").strip()
                q  = _i(it.get("quantity"), 0)
                if bc and q > 0:
                    reserved[bc] = reserved.get(bc, 0) + q
                    total_reserved_items += q
        
        logger.info(f"[PUSH] 🔒 Toplam {len(reserved)} farklı barkod için {total_reserved_items} adet rezerve edildi")
        
        # En çok rezerve edilen 5 ürünü göster
        if reserved:
            top_reserved = sorted(reserved.items(), key=lambda x: x[1], reverse=True)[:5]
            logger.info("[PUSH] 📋 En çok rezerve edilen 5 ürün:")
            for idx, (bc, qty) in enumerate(top_reserved, 1):
                logger.info(f"[PUSH]   {idx}. Barkod: {bc}, Rezerve: {qty}")

        # 3. Available Stok Hesaplama
        logger.info("[PUSH] 🧮 Step 3: Kullanılabilir stok hesaplanıyor...")
        items = []
        zero_stock_count = 0
        negative_adjusted_count = 0
        
        for r in rows:
            central_qty = _i(r.qty, 0)
            reserved_qty = reserved.get(r.barcode, 0)
            available = central_qty - reserved_qty
            
            if available < 0:
                negative_adjusted_count += 1
                logger.debug(f"[PUSH] ⚠️ Negatif stok düzeltildi: {r.barcode} (Central: {central_qty}, Rezerve: {reserved_qty} → 0)")
                available = 0
            
            if available == 0:
                zero_stock_count += 1
                
            items.append({"barcode": r.barcode.strip(), "quantity": available})

        logger.info(f"[PUSH] 📊 Stok İstatistikleri:")
        logger.info(f"[PUSH]   • Toplam ürün: {len(items)}")
        logger.info(f"[PUSH]   • Sıfır stoklu: {zero_stock_count}")
        logger.info(f"[PUSH]   • Negatif düzeltilen: {negative_adjusted_count}")
        logger.info(f"[PUSH]   • Pozitif stoklu: {len(items) - zero_stock_count}")

        if not items:
            logger.warning("[PUSH] ⚠️ Gönderilecek kalem yok!")
            return

        # Pozitif stoklu ilk 5 ürünü göster
        positive_items = [it for it in items if it["quantity"] > 0][:5]
        if positive_items:
            logger.info("[PUSH] 📋 Gönderilecek örnek 5 ürün:")
            for idx, it in enumerate(positive_items, 1):
                logger.info(f"[PUSH]   {idx}. Barkod: {it['barcode']}, Miktar: {it['quantity']}")

        # 4. API İsteği Hazırlık
        logger.info("[PUSH] 🌐 Step 4: Trendyol API isteği hazırlanıyor...")
        url = f"https://api.trendyol.com/sapigw/suppliers/{SUPPLIER_ID}/products/price-and-inventory"
        auth = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"GulluAyakkabiApp-V2/{SUPPLIER_ID}"
        }
        
        logger.info(f"[PUSH] 🔗 API URL: {url}")
        logger.info(f"[PUSH] 🔑 Supplier ID: {SUPPLIER_ID}")
        logger.info(f"[PUSH] 🔐 Auth hazırlandı (API_KEY mevcut: {bool(API_KEY)})")

        BATCH_SIZE = 100
        total = len(items)
        parts = math.ceil(total / BATCH_SIZE)
        logger.info(f"[PUSH] 📦 Batch ayarları: {total} kalem, {parts} paket (Batch size: {BATCH_SIZE})")

        # 5. Asenkron Gönderim
        logger.info("[PUSH] 📤 Step 5: Asenkron gönderim başlatılıyor...")
        
        async def _run():
            success_count = 0
            error_count = 0
            timeout = aiohttp.ClientTimeout(total=60)
            
            async with aiohttp.ClientSession() as session:
                for i in range(0, total, BATCH_SIZE):
                    batch_num = i//BATCH_SIZE + 1
                    batch = items[i:i+BATCH_SIZE]
                    payload = {"items": [{"barcode": it["barcode"], "quantity": max(0, int(it["quantity"]))}
                                         for it in batch if it.get("barcode")]}
                    
                    logger.info(f"[PUSH] 📮 Batch {batch_num}/{parts} gönderiliyor ({len(payload['items'])} ürün)...")
                    
                    try:
                        async with session.post(url, headers=headers, json=payload, timeout=timeout) as resp:
                            body = await resp.text()
                            
                            if resp.status == 200:
                                success_count += 1
                                logger.info(f"[PUSH] ✅ Batch {batch_num}/{parts} başarılı! Status: {resp.status}")
                                logger.debug(f"[PUSH] 📄 Response: {body[:300]}")
                            else:
                                error_count += 1
                                logger.error(f"[PUSH] ❌ Batch {batch_num}/{parts} hata! Status: {resp.status}")
                                logger.error(f"[PUSH] 📄 Error Response: {body[:500]}")
                                
                    except asyncio.TimeoutError:
                        error_count += 1
                        logger.error(f"[PUSH] ⏱️ Batch {batch_num}/{parts} zaman aşımı (60s)")
                    except Exception as e:
                        error_count += 1
                        logger.error(f"[PUSH] ⚠️ Batch {batch_num}/{parts} istisna: {e}")
                        
                    await asyncio.sleep(0.4)
            
            logger.info(f"[PUSH] 📊 Gönderim özeti: Başarılı: {success_count}/{parts}, Hatalı: {error_count}/{parts}")

        try:
            logger.info("[PUSH] 🚀 Asenkron döngü başlatılıyor...")
            asyncio.run(_run())
            logger.info("[PUSH] ✅ price-and-inventory işlemi tamamlandı!")
        except Exception as e:
            logger.error(f"[PUSH] ❌ KRITIK HATA: {e}", exc_info=True)
        
        logger.info("[PUSH] 🏁 Stok gönderme işlemi sona erdi")
        logger.info("=" * 80)

def push_stock_job():
    """Zamanlayıcı tetiklemesinde direkt stok gönderir (zamanlamayı schedule ayarlar)."""
    push_central_stock_to_trendyol()

def sync_woo_orders_background():
    """WooCommerce siparişlerini arka planda senkronize eder (zamanlayıcı için)"""
    with app.app_context():
        try:
            from woocommerce_site.woo_service import WooCommerceService
            from woocommerce_site.woo_config import WooConfig
            
            # API ayarları kontrolü
            if not WooConfig.is_configured():
                logger.debug("WooCommerce API ayarları yapılmamış, senkronizasyon atlandı")
                return
            
            woo_service = WooCommerceService()
            
            # Son 3 günün siparişlerini çek (sadece aktif olanlar)
            active_statuses = ['pending', 'processing', 'on-hold']
            total = 0
            
            for status in active_statuses:
                result = woo_service.sync_orders_to_db(status=status, days=3)
                total += result.get('total_saved', 0)
            
            if total > 0:
                logger.info(f"WooCommerce otomatik senkronizasyon: {total} sipariş güncellendi")
                
        except Exception as e:
            logger.error(f"WooCommerce arka plan senkronizasyon hatası: {str(e)}")

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

    # >>> WooCommerce sipariş senkronizasyonu: her 10 dakika - DEVRE DIŞI
    # _add_job_safe(
    #     sync_woo_orders_background,
    #     trigger='interval',
    #     id="woo_sync_orders",
    #     minutes=10,
    #     next_run_time=now + timedelta(minutes=1)  # 1 dk sonra başlasın
    # )

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