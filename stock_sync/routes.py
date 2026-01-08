# -*- coding: utf-8 -*-
"""
Stock Sync Routes - Stok Senkronizasyon API Endpoint'leri
"""

import asyncio
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user

from models import db, CentralStock, SyncSession, SyncDetail, PlatformConfig
from logger_config import app_logger as logger
from user_logs import log_user_action

from .service import stock_sync_service, sync_platform_sync, sync_all_platforms_sync


stock_sync_bp = Blueprint('stock_sync', __name__, url_prefix='/stock-sync')


# ════════════════════════════════════════════════════════════════════
# DASHBOARD & VIEWS
# ════════════════════════════════════════════════════════════════════

@stock_sync_bp.route('/')
@login_required
def dashboard():
    """Stok senkronizasyon dashboard'u"""
    log_user_action("PAGE_VIEW", "stock_sync_dashboard")
    
    # Yarıda kalmış session'ları temizle (uygulama context'i içinde)
    stock_sync_service.cleanup_stale_sessions()
    
    # Platform durumları
    platform_status = stock_sync_service.get_platform_status()
    
    # Son sync'ler
    recent_sessions = stock_sync_service.get_session_history(limit=10)
    
    # Aktif session'lar
    active_sessions = stock_sync_service.get_active_sessions()
    
    # İstatistikler
    total_products = CentralStock.query.count()
    
    # Platform son sync zamanları
    platform_configs = {p.platform: p for p in PlatformConfig.query.all()}
    
    return render_template('stock_sync/dashboard.html',
                           platform_status=platform_status,
                           recent_sessions=recent_sessions,
                           active_sessions=active_sessions,
                           total_products=total_products,
                           platform_configs=platform_configs)


@stock_sync_bp.route('/history')
@login_required
def history():
    """Sync geçmişi sayfası"""
    log_user_action("PAGE_VIEW", "stock_sync_history")
    
    platform = request.args.get('platform')
    limit = request.args.get('limit', 100, type=int)
    
    sessions = stock_sync_service.get_session_history(limit=limit, platform=platform)
    
    return render_template('stock_sync/history.html', 
                           sessions=sessions,
                           selected_platform=platform)


@stock_sync_bp.route('/session/<session_id>')
@login_required
def session_detail(session_id: str):
    """Session detay sayfası"""
    log_user_action("PAGE_VIEW", f"stock_sync_session_{session_id}")
    
    session_data = stock_sync_service.get_session_details(session_id)
    
    if not session_data:
        return render_template('stock_sync/error.html', 
                               message="Session bulunamadı"), 404
    
    return render_template('stock_sync/session_detail.html', 
                           session=session_data)


# ════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ════════════════════════════════════════════════════════════════════

@stock_sync_bp.route('/api/status')
@login_required
def api_status():
    """Platform durumlarını döndür"""
    return jsonify({
        "success": True,
        "platforms": stock_sync_service.get_platform_status(),
        "configured": stock_sync_service.get_configured_platforms(),
        "active_sessions": stock_sync_service.get_active_sessions(),
        "total_products": CentralStock.query.count(),
        "reserved_count": stock_sync_service.get_reserved_count(),
        "platform_logos": {
            "trendyol": "/static/logo/trendyol.png",
            "idefix": "/static/logo/idefix.png",
            "amazon": "/static/logo/amazon.png",
            "woocommerce": "/static/logo/woocommerce.png"
        }
    })


@stock_sync_bp.route('/api/sync/all', methods=['POST'])
@login_required
def api_sync_all():
    """Tüm platformlara sync başlat"""
    log_user_action("STOCK_SYNC", "sync_all_platforms")
    
    data = request.get_json(silent=True) or {}
    barcodes = data.get('barcodes')  # Opsiyonel
    
    # Senkron çalıştır (blocking)
    result = sync_all_platforms_sync(
        barcodes=barcodes,
        triggered_by="manual",
        triggered_by_user=current_user.username if current_user.is_authenticated else None
    )
    
    return jsonify(result)


@stock_sync_bp.route('/api/sync/<platform>', methods=['POST'])
@login_required
def api_sync_platform(platform: str):
    """Tek platforma sync başlat"""
    log_user_action("STOCK_SYNC", f"sync_{platform}")
    
    data = request.get_json(silent=True) or {}
    barcodes = data.get('barcodes')
    
    result = sync_platform_sync(
        platform=platform,
        barcodes=barcodes,
        triggered_by="manual",
        triggered_by_user=current_user.username if current_user.is_authenticated else None
    )
    
    return jsonify(result)


@stock_sync_bp.route('/api/sync/barcodes', methods=['POST'])
@login_required
def api_sync_barcodes():
    """Belirli barkodları sync et"""
    data = request.get_json(silent=True) or {}
    barcodes = data.get('barcodes', [])
    platforms = data.get('platforms')  # None ise tümü
    
    if not barcodes:
        return jsonify({"success": False, "error": "Barkod listesi boş"}), 400
    
    log_user_action("STOCK_SYNC", f"sync_barcodes_{len(barcodes)}")
    
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            stock_sync_service.sync_specific_barcodes(
                barcodes=barcodes,
                platforms=platforms,
                triggered_by="manual",
                triggered_by_user=current_user.username if current_user.is_authenticated else None
            )
        )
    finally:
        loop.close()
    
    return jsonify(result)


@stock_sync_bp.route('/api/sync/background', methods=['POST'])
@login_required
def api_sync_background():
    """Arka planda sync başlat (non-blocking)"""
    data = request.get_json() or {}
    platform = data.get('platform', 'all')
    
    log_user_action("STOCK_SYNC", f"sync_background_{platform}")
    
    session_id = stock_sync_service.run_sync_in_background(
        platform=platform,
        triggered_by="manual",
        triggered_by_user=current_user.username if current_user.is_authenticated else None
    )
    
    return jsonify({
        "success": True,
        "message": f"Sync arka planda başlatıldı",
        "session_id": session_id
    })


@stock_sync_bp.route('/api/session/<session_id>')
@login_required
def api_session_detail(session_id: str):
    """Session detaylarını JSON olarak döndür"""
    session_data = stock_sync_service.get_session_details(session_id)
    
    if not session_data:
        return jsonify({"success": False, "error": "Session bulunamadı"}), 404
    
    return jsonify({"success": True, "session": session_data})


@stock_sync_bp.route('/api/session/<session_id>/cancel', methods=['POST'])
@login_required
def api_cancel_session(session_id: str):
    """Aktif session'ı iptal et"""
    log_user_action("STOCK_SYNC", f"cancel_session_{session_id}")
    
    success = stock_sync_service.cancel_session(session_id)
    
    if success:
        return jsonify({"success": True, "message": "Session iptal edildi"})
    else:
        return jsonify({"success": False, "error": "Session bulunamadı veya aktif değil"}), 404


@stock_sync_bp.route('/api/history')
@login_required
def api_history():
    """Sync geçmişini JSON olarak döndür"""
    platform = request.args.get('platform')
    limit = request.args.get('limit', 50, type=int)
    
    sessions = stock_sync_service.get_session_history(limit=limit, platform=platform)
    
    return jsonify({
        "success": True,
        "sessions": sessions,
        "count": len(sessions)
    })


@stock_sync_bp.route('/api/active')
@login_required
def api_active_sessions():
    """Aktif session'ları döndür"""
    return jsonify({
        "success": True,
        "sessions": stock_sync_service.get_active_sessions()
    })


# ════════════════════════════════════════════════════════════════════
# PLATFORM CONFIG
# ════════════════════════════════════════════════════════════════════

@stock_sync_bp.route('/api/config/<platform>', methods=['GET'])
@login_required
def api_get_config(platform: str):
    """Platform config'ini döndür"""
    config = PlatformConfig.query.filter_by(platform=platform).first()
    
    if not config:
        return jsonify({
            "success": True,
            "config": {
                "platform": platform,
                "is_active": True,
                "batch_size": 100,
                "rate_limit_delay": 0.1,
                "max_retries": 3,
                "sync_interval_minutes": 60
            }
        })
    
    return jsonify({
        "success": True,
        "config": {
            "platform": config.platform,
            "is_active": config.is_active,
            "batch_size": config.batch_size,
            "rate_limit_delay": config.rate_limit_delay,
            "max_retries": config.max_retries,
            "sync_interval_minutes": config.sync_interval_minutes,
            "last_sync_at": config.last_sync_at.isoformat() if config.last_sync_at else None
        }
    })


@stock_sync_bp.route('/api/config/<platform>', methods=['PUT'])
@login_required
def api_update_config(platform: str):
    """Platform config'ini güncelle"""
    data = request.get_json() or {}
    
    log_user_action("STOCK_SYNC", f"update_config_{platform}")
    
    config = PlatformConfig.query.filter_by(platform=platform).first()
    
    if not config:
        config = PlatformConfig(platform=platform)
        db.session.add(config)
    
    if 'is_active' in data:
        config.is_active = data['is_active']
    if 'batch_size' in data:
        config.batch_size = max(1, min(500, data['batch_size']))
    if 'rate_limit_delay' in data:
        config.rate_limit_delay = max(0, min(5, data['rate_limit_delay']))
    if 'max_retries' in data:
        config.max_retries = max(1, min(10, data['max_retries']))
    if 'sync_interval_minutes' in data:
        config.sync_interval_minutes = max(5, data['sync_interval_minutes'])
    
    db.session.commit()
    
    return jsonify({"success": True, "message": "Config güncellendi"})


# ════════════════════════════════════════════════════════════════════
# STATISTICS
# ════════════════════════════════════════════════════════════════════

@stock_sync_bp.route('/api/stats')
@login_required
def api_stats():
    """Genel istatistikler"""
    # Toplam sync sayısı
    total_syncs = SyncSession.query.count()
    
    # Başarılı sync sayısı
    successful_syncs = SyncSession.query.filter_by(status='completed').count()
    
    # Platform bazlı istatistikler
    platform_stats = {}
    for platform in ['trendyol', 'idefix', 'amazon', 'woocommerce']:
        sessions = SyncSession.query.filter_by(platform=platform).all()
        if sessions:
            platform_stats[platform] = {
                "total_syncs": len(sessions),
                "success_count": sum(s.success_count or 0 for s in sessions),
                "error_count": sum(s.error_count or 0 for s in sessions),
                "avg_duration": sum(s.duration_seconds or 0 for s in sessions) / len(sessions)
            }
    
    # Son 24 saat
    from datetime import timedelta
    day_ago = datetime.utcnow() - timedelta(days=1)
    recent_syncs = SyncSession.query.filter(SyncSession.created_at >= day_ago).count()
    
    return jsonify({
        "success": True,
        "stats": {
            "total_syncs": total_syncs,
            "successful_syncs": successful_syncs,
            "success_rate": f"{(successful_syncs/total_syncs*100):.1f}%" if total_syncs > 0 else "0%",
            "syncs_last_24h": recent_syncs,
            "total_products": CentralStock.query.count(),
            "platform_stats": platform_stats
        }
    })


# ════════════════════════════════════════════════════════════════════
# ERROR REPORTING
# ════════════════════════════════════════════════════════════════════

@stock_sync_bp.route('/api/errors')
@login_required
def api_errors():
    """Son hataları listele"""
    limit = request.args.get('limit', 100, type=int)
    platform = request.args.get('platform')
    
    query = SyncDetail.query.filter_by(status='error').order_by(SyncDetail.created_at.desc())
    
    if platform:
        query = query.filter_by(platform=platform)
    
    errors = query.limit(limit).all()
    
    return jsonify({
        "success": True,
        "errors": [e.to_dict() for e in errors],
        "count": len(errors)
    })
