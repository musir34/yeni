"""
Amazon SP-API Service - Gerçek Amazon SP-API Entegrasyonu
"""
import os
import logging
import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AmazonService:
    """Amazon SP-API Servis Sınıfı"""
    
    def __init__(self):
        """Amazon servisini başlat"""
        self.lwa_client_id = os.getenv('AMAZON_LWA_CLIENT_ID')
        self.lwa_client_secret = os.getenv('AMAZON_LWA_CLIENT_SECRET')
        self.refresh_token = os.getenv('AMAZON_REFRESH_TOKEN')
        self.seller_id = os.getenv('AMAZON_SELLER_ID')
        self.marketplace_id = os.getenv('AMAZON_MARKETPLACE_ID', 'A33AVAJ2PDY3EV')  # Türkiye
        
        # API endpoints
        self.lwa_endpoint = "https://api.amazon.com/auth/o2/token"
        self.sp_api_endpoint = "https://sellingpartnerapi-eu.amazon.com"
        
        # Access token cache
        self._access_token = None
        self._token_expires_at = None
        
        if self._is_configured():
            logger.info(f"[AMAZON] Service başlatıldı - Seller ID: {self.seller_id}, Marketplace: {self.marketplace_id}")
        else:
            logger.warning("[AMAZON] Credentials eksik - Mock mode aktif")
    
    def _is_configured(self) -> bool:
        """Tüm credentials var mı?"""
        return all([
            self.lwa_client_id,
            self.lwa_client_secret,
            self.refresh_token,
            self.seller_id,
            self.marketplace_id
        ])
    
    def _get_access_token(self) -> Optional[str]:
        """LWA access token al (cache'den veya yeni)"""
        # Cache kontrolü
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at:
                return self._access_token
        
        # Yeni token al
        try:
            logger.info("[AMAZON] Access token alınıyor...")
            
            response = requests.post(
                self.lwa_endpoint,
                data={
                    'grant_type': 'refresh_token',
                    'refresh_token': self.refresh_token,
                    'client_id': self.lwa_client_id,
                    'client_secret': self.lwa_client_secret
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self._access_token = data['access_token']
                expires_in = data.get('expires_in', 3600)
                self._token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)
                
                logger.info(f"[AMAZON] ✅ Access token alındı (expires in {expires_in}s)")
                return self._access_token
            else:
                logger.error(f"[AMAZON] ❌ Token alma hatası: {response.status_code} - {response.text[:200]}")
                return None
                
        except Exception as e:
            logger.error(f"[AMAZON] ❌ Token alma exception: {e}")
            return None
    
    def _make_api_request(self, method: str, path: str, params: dict = None, json_data: dict = None) -> Optional[dict]:
        """Amazon SP-API'ye istek gönder"""
        if not self._is_configured():
            logger.warning("[AMAZON] Mock mode - API çağrısı yapılmadı")
            return {"mock": True}
        
        access_token = self._get_access_token()
        if not access_token:
            logger.error("[AMAZON] Access token alınamadı!")
            return None
        
        url = f"{self.sp_api_endpoint}{path}"
        headers = {
            'x-amz-access-token': access_token,
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=60
            )
            
            logger.info(f"[AMAZON] API: {method} {path} -> {response.status_code}")
            
            if response.status_code in [200, 201, 202]:
                return response.json() if response.text else {}
            else:
                logger.error(f"[AMAZON] API Error: {response.status_code} - {response.text[:500]}")
                return None
                
        except Exception as e:
            logger.error(f"[AMAZON] API Exception: {e}")
            return None


# Global instance
amazon_service = AmazonService()