"""
Amazon SP-API Konfigürasyonu
Amazon Seller Partner API için gerekli ayarlar
"""
import os
from dotenv import load_dotenv

load_dotenv()


class AmazonConfig:
    """Amazon SP-API ayarları"""
    
    # ═══════════════════════════════════════════════════════════════════════════
    # AMAZON SELLER CENTRAL'DAN ALINACAK BİLGİLER
    # ═══════════════════════════════════════════════════════════════════════════
    
    # 1️⃣ LWA (Login with Amazon) Bilgileri - Developer Console'dan alınır
    # https://developer.amazon.com/apps-and-games/login-with-amazon
    LWA_CLIENT_ID = os.getenv('AMAZON_LWA_CLIENT_ID', '')
    LWA_CLIENT_SECRET = os.getenv('AMAZON_LWA_CLIENT_SECRET', '')
    
    # 2️⃣ Refresh Token - SP-API uygulaması yetkilendirildikten sonra alınır
    REFRESH_TOKEN = os.getenv('AMAZON_REFRESH_TOKEN', '')
    
    # 3️⃣ Seller ID (Merchant Token) - Seller Central > Settings > Account Info
    SELLER_ID = os.getenv('AMAZON_SELLER_ID', '')
    
    # 4️⃣ Marketplace ID - Türkiye için: A33AVAJ2PDY3EV
    # Diğer marketplace ID'leri:
    # - Almanya: A1PA6795UKMFR9
    # - İngiltere: A1F83G8C2ARO7P
    # - Fransa: A13V1IB3VIYBER
    # - İtalya: APJ6JRA9NG5V4
    # - İspanya: A1RKKUPIHCS9HS
    # - Hollanda: A1805IZSGTT6HS
    # - Polonya: A1C3SOZRARQ6R3
    # - İsveç: A2NODRKZP88ZB9
    # - Belçika: AMEN7PMS3EDWL
    # - Türkiye: A33AVAJ2PDY3EV
    MARKETPLACE_ID = os.getenv('AMAZON_MARKETPLACE_ID', 'A33AVAJ2PDY3EV')
    
    # ═══════════════════════════════════════════════════════════════════════════
    # API AYARLARI
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Timeout ayarları (saniye)
    TIMEOUT = 30
    
    # Rate limiting (SP-API limitleri)
    RATE_LIMIT_ORDERS = 0.0167  # 1 istek / dakika
    RATE_LIMIT_INVENTORY = 2  # 2 istek / saniye
    
    # Sayfalama
    PAGE_SIZE = 100
    
    @classmethod
    def is_configured(cls):
        """API ayarlarının yapılıp yapılmadığını kontrol et (AWS artık zorunlu değil)"""
        required = [
            cls.LWA_CLIENT_ID,
            cls.LWA_CLIENT_SECRET,
            cls.REFRESH_TOKEN,
            cls.SELLER_ID
        ]
        return all(required)
    
    @classmethod
    def get_credentials(cls):
        """SP-API için credentials dict döndür (AWS'siz - Grantless mode)"""
        return {
            'lwa_app_id': cls.LWA_CLIENT_ID,
            'lwa_client_secret': cls.LWA_CLIENT_SECRET,
            'refresh_token': cls.REFRESH_TOKEN
        }
    
    @classmethod
    def get_marketplace_ids(cls):
        """Aktif marketplace ID listesi"""
        return [cls.MARKETPLACE_ID]


# ═══════════════════════════════════════════════════════════════════════════════
# AMAZON SELLER CENTRAL AYAR REHBERİ (AWS GEREKMİYOR!)
# ═══════════════════════════════════════════════════════════════════════════════
#
# ADIM 1: Amazon Seller Central'a giriş yapın
# https://sellercentral.amazon.com.tr (Türkiye için)
#
# ADIM 2: Developer olarak kayıt olun
# - Settings > User Permissions > Developer sayfasına gidin
# - "Register yourself as a developer" seçeneğini tıklayın
#
# ADIM 3: SP-API Uygulaması oluşturun
# - Apps & Services > Develop Apps sayfasına gidin
# - "Add new app client" tıklayın
# - Uygulama adı girin (örn: gullupanel)
#
# ADIM 4: LWA Credentials alın
# - Uygulama listesinde "View" linkine tıklayın
# - Client ID ve Client Secret'ı kopyalayın
#
# ADIM 5: Uygulamayı yetkilendirin
# - Seller Central > Apps & Services > Manage Your Apps
# - Uygulamanızı yetkilendirin (Authorize)
# - Refresh Token alacaksınız
#
# ADIM 6: .env dosyasına bilgileri ekleyin:
# AMAZON_LWA_CLIENT_ID=...
# AMAZON_LWA_CLIENT_SECRET=...
# AMAZON_REFRESH_TOKEN=...
# AMAZON_SELLER_ID=...
# AMAZON_MARKETPLACE_ID=A33AVAJ2PDY3EV
