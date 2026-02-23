"""
Hepsiburada Marketplace API Konfigürasyonu
Hepsiburada Satıcı API entegrasyonu için gerekli ayarlar
"""
import os
from dotenv import load_dotenv

load_dotenv()


class HepsiburadaConfig:
    """Hepsiburada Marketplace API ayarları"""

    # ═══════════════════════════════════════════════════════════════════════════
    # HEPSİBURADA SATICI PANELİNDEN ALINACAK BİLGİLER
    # ═══════════════════════════════════════════════════════════════════════════

    # 1️⃣ Merchant ID (Satıcı ID) - Satıcı Paneli > Bilgilerim > Entegrasyon
    MERCHANT_ID = os.getenv('HB_MERCHANT_ID', '')

    # 2️⃣ Username (Kullanıcı Adı) - HTTP Basic Auth için
    # Satıcı Paneli > Bilgilerim > Entegrasyon > Entegratör Bilgileri
    USERNAME = os.getenv('HB_USERNAME', '')

    # 3️⃣ Password (Şifre / Servis Anahtarı) - HTTP Basic Auth için
    # Satıcı Paneli > Bilgilerim > Entegrasyon > Entegratör Bilgileri > Servis Anahtarı
    PASSWORD = os.getenv('HB_PASSWORD', '')

    # 4️⃣ User Agent - Entegratör adı (zorunlu!)
    USER_AGENT = os.getenv('HB_USER_AGENT', 'gullushoes_dev')

    # ═══════════════════════════════════════════════════════════════════════════
    # API ENDPOINT AYARLARI
    # ═══════════════════════════════════════════════════════════════════════════

    # Test (SIT) ortamı - URL'de "-sit" bulunur
    # Canlı ortam - URL'den "-sit" kaldırılır
    IS_PRODUCTION = os.getenv('HB_IS_PRODUCTION', 'false').lower() == 'true'

    # Sipariş API Base URL
    ORDER_BASE_URL_TEST = "https://oms-external-sit.hepsiburada.com"
    ORDER_BASE_URL_PROD = "https://oms-external.hepsiburada.com"

    # Listeleme API Base URL
    LISTING_BASE_URL_TEST = "https://listing-external-sit.hepsiburada.com"
    LISTING_BASE_URL_PROD = "https://listing-external.hepsiburada.com"

    # Katalog API Base URL
    CATALOG_BASE_URL_TEST = "https://mpop-sit.hepsiburada.com"
    CATALOG_BASE_URL_PROD = "https://mpop.hepsiburada.com"

    # ═══════════════════════════════════════════════════════════════════════════
    # RATE LIMITING
    # ═══════════════════════════════════════════════════════════════════════════
    RATE_LIMIT_ORDERS = 1000  # 1000 istek / 1 saniye
    RATE_LIMIT_LISTINGS = 240  # 240 istek / 1 dakika

    # Sayfalama
    PAGE_SIZE = 50
    TIMEOUT = 30

    @classmethod
    def is_configured(cls):
        """API ayarlarının yapılıp yapılmadığını kontrol et"""
        required = [
            cls.MERCHANT_ID,
            cls.USERNAME,
            cls.PASSWORD,
        ]
        return all(required)

    @classmethod
    def get_order_base_url(cls):
        """Aktif sipariş API base URL'ini döndür"""
        return cls.ORDER_BASE_URL_PROD if cls.IS_PRODUCTION else cls.ORDER_BASE_URL_TEST

    @classmethod
    def get_listing_base_url(cls):
        """Aktif listeleme API base URL'ini döndür"""
        return cls.LISTING_BASE_URL_PROD if cls.IS_PRODUCTION else cls.LISTING_BASE_URL_TEST

    @classmethod
    def get_catalog_base_url(cls):
        """Aktif katalog API base URL'ini döndür"""
        return cls.CATALOG_BASE_URL_PROD if cls.IS_PRODUCTION else cls.CATALOG_BASE_URL_TEST

    @classmethod
    def get_auth(cls):
        """HTTP Basic Auth tuple döndür"""
        return (cls.USERNAME, cls.PASSWORD)

    @classmethod
    def get_env_label(cls):
        """Aktif ortam etiketini döndür"""
        return "CANLI" if cls.IS_PRODUCTION else "TEST (SIT)"


# ═══════════════════════════════════════════════════════════════════════════════
# HEPSİBURADA SATICI PANELİ AYAR REHBERİ
# ═══════════════════════════════════════════════════════════════════════════════
#
# ADIM 1: Hepsiburada Satıcı Paneline giriş yapın
# https://merchant.hepsiburada.com/
#
# ADIM 2: Bilgilerim > Entegrasyon sayfasına gidin
#
# ADIM 3: "Entegratör Bilgileri" tabına geçin
#
# ADIM 4: Entegratörünüzü seçin ve "Servis Anahtarı" butonuna tıklayın
#
# ADIM 5: Servis anahtarını kopyalayın
#
# ADIM 6: Merchant ID'nizi öğrenin
# - Satıcı Paneli > Bilgilerim > Hesap Bilgileri
# - veya Hepsiburada destek ekibinden talep edin
#
# ADIM 7: .env dosyasına bilgileri ekleyin:
# HB_MERCHANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
# HB_USERNAME=your_username
# HB_PASSWORD=your_secret_key
# HB_IS_PRODUCTION=false  (test için false, canlı için true)
