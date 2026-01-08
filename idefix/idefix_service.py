"""
Idefix Satıcı Paneli Servisi
Satıcı: Güllü shoes
Satıcı ID: 10594
"""

import os
import base64
import requests
from typing import Optional, Dict, Any, List
from logger_config import app_logger

class IdefixService:
    """Idefix API entegrasyonu için servis sınıfı"""
    
    # Canlı ortam API URL'leri
    PIM_BASE_URL = "https://merchantapi.idefix.com/pim"
    OMS_BASE_URL = "https://merchantapi.idefix.com/oms"
    
    def __init__(self):
        self.seller_id = os.getenv("IDEFIX_SELLER_ID", "10594")
        self.seller_name = os.getenv("IDEFIX_SELLER_NAME", "Güllü shoes")
        self.token = os.getenv("IDEFIX_TOKEN")
        self.secret = os.getenv("IDEFIX_SECRET")
        self._vendor_token = None
        app_logger.info(f"[IDEFIX] Service başlatıldı - Seller ID: {self.seller_id}, Seller Name: {self.seller_name}")
        app_logger.debug(f"[IDEFIX] Token mevcut: {bool(self.token)}, Secret mevcut: {bool(self.secret)}")
        
    def _get_vendor_token(self) -> str:
        """API Key ve Secret'tan vendor token oluşturur (base64 encode)"""
        if self._vendor_token is None:
            credentials = f"{self.token}:{self.secret}"
            self._vendor_token = base64.b64encode(credentials.encode()).decode()
            app_logger.debug(f"[IDEFIX] Vendor token oluşturuldu")
        return self._vendor_token
        
    def _get_headers(self) -> Dict[str, str]:
        """API istekleri için gerekli header'ları döndürür"""
        return {
            "Authorization": f"Basic {self._get_vendor_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def get_products(self, page: int = 1, limit: int = 50, barcode: Optional[str] = None) -> Dict[str, Any]:
        """
        Satıcının ürünlerini listeler
        
        Args:
            page: Sayfa numarası
            limit: Sayfa başına ürün sayısı
            barcode: Barkod ile filtreleme (opsiyonel)
        
        Returns:
            Ürün listesi
        """
        app_logger.info(f"[IDEFIX] get_products çağrıldı - page: {page}, limit: {limit}, barcode: {barcode}")
        
        try:
            url = f"{self.PIM_BASE_URL}/pool/{self.seller_id}/list"
            params: Dict[str, Any] = {
                "page": page,
                "limit": limit
            }
            
            if barcode:
                params["barcode"] = barcode
            
            app_logger.info(f"[IDEFIX] API isteği: GET {url}")
            app_logger.debug(f"[IDEFIX] Params: {params}")
            
            response = requests.get(
                url, 
                headers=self._get_headers(),
                params=params,
                timeout=30
            )
            
            app_logger.info(f"[IDEFIX] API yanıtı: Status {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                product_count = len(data.get('products', []))
                app_logger.info(f"[IDEFIX] Başarılı: {product_count} ürün alındı")
                return {
                    "success": True,
                    "products": data.get("products", []),
                    "page": page,
                    "limit": limit,
                    "total": product_count
                }
            elif response.status_code == 401:
                app_logger.error("[IDEFIX] API: Yetkilendirme hatası (401)")
                return {
                    "success": False,
                    "error": "Yetkilendirme hatası. API Key ve Secret bilgilerini kontrol edin.",
                    "products": []
                }
            elif response.status_code == 429:
                app_logger.warning("[IDEFIX] API: Rate limit aşıldı (429)")
                return {
                    "success": False,
                    "error": "API istek limiti aşıldı. Lütfen biraz bekleyip tekrar deneyin.",
                    "products": []
                }
            else:
                app_logger.error(f"[IDEFIX] API hatası: {response.status_code} - {response.text[:500]}")
                return {
                    "success": False,
                    "error": f"API hatası: {response.status_code}",
                    "products": []
                }
                
        except requests.exceptions.Timeout:
            app_logger.error("[IDEFIX] API: Zaman aşımı")
            return {
                "success": False,
                "error": "İstek zaman aşımına uğradı",
                "products": []
            }
        except requests.exceptions.RequestException as e:
            app_logger.error(f"[IDEFIX] API bağlantı hatası: {str(e)}")
            return {
                "success": False,
                "error": f"Bağlantı hatası: {str(e)}",
                "products": []
            }
        except Exception as e:
            app_logger.error(f"[IDEFIX] Beklenmeyen hata: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "products": []
            }
    
    def get_product_by_barcode(self, barcode: str) -> Dict[str, Any]:
        """Barkod ile ürün arar"""
        return self.get_products(barcode=barcode)
    
    def get_all_products(self, max_pages: int = 100) -> Dict[str, Any]:
        """
        Tüm ürünleri sayfalama ile çeker
        
        Args:
            max_pages: Maksimum sayfa sayısı (güvenlik için)
        
        Returns:
            Tüm ürünlerin listesi
        """
        app_logger.info(f"[IDEFIX] Tüm ürünler çekiliyor (max_pages: {max_pages})")
        
        all_products = []
        page = 1
        limit = 100  # Maksimum limit
        
        while page <= max_pages:
            result = self.get_products(page=page, limit=limit)
            
            if not result.get("success"):
                app_logger.error(f"[IDEFIX] Sayfa {page} çekilirken hata: {result.get('error')}")
                break
            
            products = result.get("products", [])
            if not products:
                app_logger.info(f"[IDEFIX] Sayfa {page} boş, çekme tamamlandı")
                break
            
            all_products.extend(products)
            app_logger.info(f"[IDEFIX] Sayfa {page}: {len(products)} ürün (toplam: {len(all_products)})")
            
            # Eğer gelen ürün sayısı limit'ten azsa, son sayfadayız
            if len(products) < limit:
                break
            
            page += 1
        
        app_logger.info(f"[IDEFIX] Toplam {len(all_products)} ürün çekildi")
        
        return {
            "success": True,
            "products": all_products,
            "total": len(all_products)
        }
    
    def get_orders(self, status: Optional[str] = None) -> Dict[str, Any]:
        """Siparişleri getirir"""
        # TODO: Sipariş entegrasyonu eklenecek
        return {"success": False, "orders": [], "message": "Sipariş entegrasyonu henüz eklenmedi"}
    
    def update_order_status(self, order_id: str, status: str) -> Dict[str, Any]:
        """Sipariş durumunu günceller"""
        # TODO: Sipariş durumu güncelleme endpoint'i eklenecek
        return {"success": False, "message": "Sipariş durumu güncelleme henüz eklenmedi"}


# Singleton instance
idefix_service = IdefixService()
