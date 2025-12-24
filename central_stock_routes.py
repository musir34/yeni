"""
Merkezi Stok Gönderim API Endpoint'leri
"""
from flask import Blueprint, jsonify, request
from central_stock_pusher import stock_pusher, push_stocks_sync
from flask_login import login_required
import logging

logger = logging.getLogger(__name__)

central_stock_bp = Blueprint('central_stock', __name__)


@central_stock_bp.route('/api/push-stocks', methods=['POST'])
@login_required
def api_push_stocks():
    """
    Tüm pazaryerlerine (Hepsiburada hariç) stok gönder
    
    POST Body (optional):
    {
        "platforms": ["trendyol", "idefix", "amazon", "woocommerce"]
    }
    """
    try:
        data = request.get_json() or {}
        platforms = data.get('platforms')  # None ise tümü
        
        # Hepsiburada'yı filtrele
        if platforms:
            platforms = [p for p in platforms if p != "hepsiburada"]
        
        logger.info(f"[API] Stok gönderim isteği alındı - Platformlar: {platforms or 'TÜM'}")
        
        result = push_stocks_sync(platforms)
        
        return jsonify(result), 200 if result.get("success") else 207
        
    except Exception as e:
        logger.error(f"[API] Stok gönderim hatası: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@central_stock_bp.route('/api/push-stocks/<platform>', methods=['POST'])
@login_required
def api_push_single_platform(platform: str):
    """
    Tek bir pazaryerine stok gönder
    
    Örnek: POST /api/push-stocks/trendyol
    """
    try:
        # Hepsiburada engelle
        if platform.lower() == "hepsiburada":
            return jsonify({
                "success": False,
                "error": "Hepsiburada'ya stok gönderimi devre dışı"
            }), 403
        
        logger.info(f"[API] {platform.upper()} için stok gönderimi başlatıldı")
        
        result = push_stocks_sync([platform.lower()])
        
        return jsonify(result), 200 if result.get("success") else 207
        
    except Exception as e:
        logger.error(f"[API] {platform} stok gönderim hatası: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@central_stock_bp.route('/api/stock-config', methods=['GET'])
@login_required
def api_get_stock_config():
    """Platform konfigürasyonlarını getir"""
    try:
        return jsonify({
            "success": True,
            "platforms": stock_pusher.PLATFORM_CONFIGS
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@central_stock_bp.route('/api/stock-config/<platform>', methods=['PUT'])
@login_required
def api_update_stock_config(platform: str):
    """
    Platform konfigürasyonunu güncelle
    
    PUT Body:
    {
        "enabled": true,
        "batch_size": 100,
        "max_retries": 3
    }
    """
    try:
        if platform not in stock_pusher.PLATFORM_CONFIGS:
            return jsonify({
                "success": False,
                "error": "Bilinmeyen platform"
            }), 404
        
        data = request.get_json() or {}
        
        # Güncelleme yap
        config = stock_pusher.PLATFORM_CONFIGS[platform]
        
        if "enabled" in data:
            config["enabled"] = bool(data["enabled"])
        if "batch_size" in data:
            config["batch_size"] = int(data["batch_size"])
        if "max_retries" in data:
            config["max_retries"] = int(data["max_retries"])
        if "retry_delay" in data:
            config["retry_delay"] = float(data["retry_delay"])
        if "rate_limit_delay" in data:
            config["rate_limit_delay"] = float(data["rate_limit_delay"])
        if "timeout" in data:
            config["timeout"] = int(data["timeout"])
        
        logger.info(f"[API] {platform} konfigürasyonu güncellendi: {config}")
        
        return jsonify({
            "success": True,
            "platform": platform,
            "config": config
        })
        
    except Exception as e:
        logger.error(f"[API] Konfigürasyon güncelleme hatası: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
