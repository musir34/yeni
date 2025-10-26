"""
Utilities Module - Standart Response Fonksiyonları
===================================================
API endpoint'lerinde tutarlı yanıtlar döndürmek için yardımcı fonksiyonlar.
"""

from flask import jsonify
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def success_response(message, data=None, status_code=200, **kwargs):
    """
    Başarılı API yanıtı oluşturur.
    
    Args:
        message (str): Başarı mesajı
        data (dict, optional): Dönülecek veri
        status_code (int): HTTP durum kodu (varsayılan: 200)
        **kwargs: Ek alanlar (örn: count, page, total_pages)
    
    Returns:
        tuple: (jsonify response, status_code)
    
    Örnek:
        return success_response("Ürün başarıyla eklendi", data={"id": 123}, status_code=201)
    """
    response = {
        'success': True,
        'message': message,
        'timestamp': datetime.now().isoformat(),
    }
    
    if data is not None:
        response['data'] = data
    
    # Ek alanları ekle (pagination, count vb.)
    for key, value in kwargs.items():
        response[key] = value
    
    return jsonify(response), status_code


def error_response(message, errors=None, status_code=400, error_code=None):
    """
    Hata API yanıtı oluşturur.
    
    Args:
        message (str): Hata mesajı
        errors (dict/list, optional): Detaylı hata bilgileri
        status_code (int): HTTP durum kodu (varsayılan: 400)
        error_code (str, optional): Özel hata kodu (örn: "INVALID_INPUT")
    
    Returns:
        tuple: (jsonify response, status_code)
    
    Örnek:
        return error_response("Ürün bulunamadı", status_code=404, error_code="NOT_FOUND")
    """
    response = {
        'success': False,
        'message': message,
        'timestamp': datetime.now().isoformat(),
    }
    
    if errors is not None:
        response['errors'] = errors
    
    if error_code:
        response['error_code'] = error_code
    
    # Hataları logla
    logger.warning(f"API Hatası [{status_code}]: {message}")
    if errors:
        logger.debug(f"Hata detayları: {errors}")
    
    return jsonify(response), status_code


def validation_error_response(errors):
    """
    Validasyon hatası yanıtı oluşturur.
    
    Args:
        errors (dict): Alan adı -> hata mesajı eşleşmeleri
    
    Returns:
        tuple: (jsonify response, 422)
    
    Örnek:
        return validation_error_response({
            "barcode": "Barkod alanı zorunludur",
            "price": "Fiyat pozitif olmalıdır"
        })
    """
    return error_response(
        message="Validasyon hatası",
        errors=errors,
        status_code=422,
        error_code="VALIDATION_ERROR"
    )


def unauthorized_response(message="Bu işlem için yetkiniz yok"):
    """
    Yetkisiz erişim yanıtı oluşturur.
    
    Args:
        message (str): Hata mesajı
    
    Returns:
        tuple: (jsonify response, 403)
    """
    return error_response(
        message=message,
        status_code=403,
        error_code="UNAUTHORIZED"
    )


def not_found_response(resource="Kayıt"):
    """
    Kayıt bulunamadı yanıtı oluşturur.
    
    Args:
        resource (str): Bulunamayan kaynak adı
    
    Returns:
        tuple: (jsonify response, 404)
    """
    return error_response(
        message=f"{resource} bulunamadı",
        status_code=404,
        error_code="NOT_FOUND"
    )


def conflict_response(message="Bu kayıt zaten mevcut"):
    """
    Çakışma/tekrar yanıtı oluşturur.
    
    Args:
        message (str): Hata mesajı
    
    Returns:
        tuple: (jsonify response, 409)
    """
    return error_response(
        message=message,
        status_code=409,
        error_code="CONFLICT"
    )


def server_error_response(message="Sunucu hatası oluştu", error_id=None):
    """
    Sunucu hatası yanıtı oluşturur.
    
    Args:
        message (str): Hata mesajı
        error_id (str, optional): Takip için hata ID
    
    Returns:
        tuple: (jsonify response, 500)
    """
    response_data = {
        'success': False,
        'message': message,
        'timestamp': datetime.now().isoformat(),
        'error_code': 'SERVER_ERROR'
    }
    
    if error_id:
        response_data['error_id'] = error_id
    
    logger.error(f"Sunucu hatası [ID: {error_id}]: {message}")
    
    return jsonify(response_data), 500


def paginated_response(items, page, per_page, total_items, message="Başarılı"):
    """
    Sayfalı veri yanıtı oluşturur.
    
    Args:
        items (list): Mevcut sayfadaki öğeler
        page (int): Mevcut sayfa numarası
        per_page (int): Sayfa başına öğe sayısı
        total_items (int): Toplam öğe sayısı
        message (str): Başarı mesajı
    
    Returns:
        tuple: (jsonify response, 200)
    """
    import math
    total_pages = math.ceil(total_items / per_page) if per_page > 0 else 0
    
    return success_response(
        message=message,
        data=items,
        pagination={
            'page': page,
            'per_page': per_page,
            'total_items': total_items,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1
        }
    )


# Hata kodları referansı
ERROR_CODES = {
    'VALIDATION_ERROR': 'Gönderilen veri geçersiz',
    'UNAUTHORIZED': 'Yetki yok',
    'NOT_FOUND': 'Kayıt bulunamadı',
    'CONFLICT': 'Veri çakışması',
    'SERVER_ERROR': 'Sunucu hatası',
    'INVALID_INPUT': 'Geçersiz girdi',
    'DATABASE_ERROR': 'Veritabanı hatası',
    'API_ERROR': 'Dış API hatası',
    'RATE_LIMIT_EXCEEDED': 'İstek limiti aşıldı'
}
