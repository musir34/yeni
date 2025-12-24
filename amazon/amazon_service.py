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
    
    def update_inventory(self, sku: str, quantity: int) -> bool:
        """
        Tek bir ürünün stok miktarını güncelle (Listings Items API)
        
        Args:
            sku: Amazon SKU (barkod olarak kullanılıyor)
            quantity: Yeni stok miktarı
            
        Returns:
            bool: Başarılı ise True
        """
        if not self._is_configured():
            logger.info(f"[AMAZON] Mock: SKU {sku} -> {quantity} (Gerçek API çağrısı yapılmadı)")
            return True
        
        logger.info(f"[AMAZON] Stok güncelleme: SKU={sku}, Quantity={quantity}")
        
        # Listings Items API kullanarak stok güncelle
        # PUT /listings/2021-08-01/items/{sellerId}/{sku}
        path = f"/listings/2021-08-01/items/{self.seller_id}/{sku}"
        
        # Patch document (JSON Patch format)
        json_data = {
            "productType": "SHOES",  # Ayakkabı kategorisi
            "patches": [
                {
                    "op": "replace",
                    "path": "/attributes/fulfillment_availability",
                    "value": [
                        {
                            "fulfillment_channel_code": "DEFAULT",
                            "quantity": quantity
                        }
                    ]
                }
            ]
        }
        
        params = {
            "marketplaceIds": self.marketplace_id
        }
        
        result = self._make_api_request("PATCH", path, params=params, json_data=json_data)
        
        if result and not result.get('errors'):
            logger.info(f"[AMAZON] ✅ Stok güncellendi: {sku} -> {quantity}")
            return True
        else:
            logger.error(f"[AMAZON] ❌ Stok güncellenemedi: {sku}")
            return False
    
    def update_inventory_bulk(self, items: List[Dict]) -> Dict:
        """
        Toplu stok güncelleme
        
        Args:
            items: [{"sku": "xxx", "quantity": 10}, ...]
            
        Returns:
            dict: {"success": bool, "success_count": int, "error_count": int}
        """
        if not self._is_configured():
            logger.info(f"[AMAZON] Mock: {len(items)} ürün için toplu stok güncelleme (Gerçek API çağrısı yapılmadı)")
            return {
                "success": True,
                "success_count": len(items),
                "error_count": 0,
                "message": "Mock mode - Gerçek API çağrısı yapılmadı"
            }
        
        logger.info(f"[AMAZON] Toplu stok güncelleme başlatıldı - {len(items)} ürün")
        
        success_count = 0
        error_count = 0
        
        # Amazon'da tek tek güncelleme yapılıyor (bulk API yok)
        for item in items:
            sku = item.get('sku')
            quantity = item.get('quantity', 0)
            
            if not sku:
                error_count += 1
                continue
            
            # Rate limiting (Listings API: 5 requests per second)
            time.sleep(0.21)  # ~5 req/sec
            
            try:
                if self.update_inventory(sku, quantity):
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                logger.error(f"[AMAZON] Hata: {sku} - {e}")
                error_count += 1
        
        logger.info(f"[AMAZON] Toplu güncelleme tamamlandı - Başarılı: {success_count}, Hata: {error_count}")
        
        return {
            "success": error_count == 0,
            "success_count": success_count,
            "error_count": error_count,
            "total": len(items)
        }
    
    def get_inventory(self, sku: str = None) -> dict:
        """
        Stok bilgisini getir
        
        Args:
            sku: Belirli bir SKU (None ise tümü)
            
        Returns:
            dict: Stok bilgisi
        """
        if not self._is_configured():
            logger.info(f"[AMAZON] Mock: Stok sorgulama - SKU: {sku or 'Tümü'}")
            return {}
        
        logger.info(f"[AMAZON] Stok sorgulama - SKU: {sku or 'Tümü'}")
        
        # FBA Inventory API kullanılabilir
        # GET /fba/inventory/v1/summaries
        path = "/fba/inventory/v1/summaries"
        params = {
            "marketplaceIds": self.marketplace_id,
            "granularityType": "Marketplace"
        }
        
        if sku:
            params["sellerSkus"] = sku
        
        result = self._make_api_request("GET", path, params=params)
        
        return result or {}
    
    def sync_inventory(self) -> dict:
        """
        Merkezi stok ile Amazon'u senkronize et
        
        Returns:
            dict: Senkronizasyon sonucu
        """
        logger.info("[AMAZON] Stok senkronizasyonu başlatıldı")
        
        if not self._is_configured():
            return {
                "success": False,
                "message": "Amazon credentials eksik",
                "synced_count": 0
            }
        
        try:
            from models import db, Product, CentralStock
            from flask import current_app
            
            # Amazon ürünlerini getir
            amazon_products = Product.query.filter(
                Product.platforms.ilike('%amazon%')
            ).all()
            
            if not amazon_products:
                return {
                    "success": True,
                    "message": "Amazon'da senkronize edilecek ürün yok",
                    "synced_count": 0
                }
            
            # Stok verilerini hazırla
            items = []
            for product in amazon_products:
                # CentralStock'tan stok al
                central_stock = CentralStock.query.get(product.barcode)
                quantity = central_stock.qty if central_stock else 0
                
                items.append({
                    "sku": product.barcode,  # Barkod SKU olarak kullanılıyor
                    "quantity": max(0, quantity)
                })
            
            # Toplu güncelleme
            result = self.update_inventory_bulk(items)
            
            return {
                "success": result.get("success", False),
                "message": f"{result.get('success_count', 0)} ürün senkronize edildi",
                "synced_count": result.get("success_count", 0),
                "error_count": result.get("error_count", 0)
            }
            
        except Exception as e:
            logger.error(f"[AMAZON] Senkronizasyon hatası: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Hata: {str(e)}",
                "synced_count": 0
            }


# Global instance
amazon_service = AmazonService()
