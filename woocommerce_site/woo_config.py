"""
WooCommerce API Konfigürasyonu
"""
import os
from dotenv import load_dotenv

load_dotenv()


class WooConfig:
    """WooCommerce API ayarları"""
    
    # WooCommerce site URL'i
    STORE_URL = os.getenv('WOO_STORE_URL', 'https://your-site.com')
    
    # WooCommerce API anahtarları
    CONSUMER_KEY = os.getenv('WOO_CONSUMER_KEY', '')
    CONSUMER_SECRET = os.getenv('WOO_CONSUMER_SECRET', '')
    
    # API versiyonu
    API_VERSION = 'wc/v3'
    
    # Timeout ayarları (saniye)
    TIMEOUT = 30
    
    # Sayfalama ayarları
    PER_PAGE = 50
    
    @classmethod
    def is_configured(cls):
        """API ayarlarının yapılıp yapılmadığını kontrol et"""
        return bool(cls.CONSUMER_KEY and cls.CONSUMER_SECRET and cls.STORE_URL)
    
    @classmethod
    def get_api_url(cls):
        """API base URL'ini döndür"""
        return f"{cls.STORE_URL}/wp-json/{cls.API_VERSION}"
