# -*- coding: utf-8 -*-
"""
Trendyol Platform Adapter
Trendyol API ile stok senkronizasyonu
"""

import os
import base64
import asyncio
from datetime import datetime
from typing import List, Dict, Any
import aiohttp

from .base import BasePlatformAdapter, StockItem, SyncResult
from logger_config import app_logger as logger


class TrendyolAdapter(BasePlatformAdapter):
    """Trendyol stok senkronizasyon adaptörü"""
    
    PLATFORM_NAME = "trendyol"
    BATCH_SIZE = 100  # Trendyol max 100 ürün/istek
    RATE_LIMIT_DELAY = 0.2  # 200ms bekleme
    BASE_URL = "https://api.trendyol.com/sapigw"
    
    def _init_config(self):
        """Trendyol API yapılandırması"""
        self.api_key = os.getenv("API_KEY") or os.getenv("TRENDYOL_API_KEY")
        self.api_secret = os.getenv("API_SECRET") or os.getenv("TRENDYOL_SECRET_KEY")
        self.supplier_id = os.getenv("SUPPLIER_ID") or os.getenv("TRENDYOL_SUPPLIER_ID")
        
        if all([self.api_key, self.api_secret, self.supplier_id]):
            self.is_configured = True
            # Basic auth header
            credentials = f"{self.api_key}:{self.api_secret}"
            self._auth_header = base64.b64encode(credentials.encode()).decode()
            logger.info(f"[TRENDYOL] Adapter yapılandırıldı - Supplier ID: {self.supplier_id}")
        else:
            self.is_configured = False
            self._auth_header = None
            missing = [k for k, v in {"API_KEY": self.api_key, "API_SECRET": self.api_secret, "SUPPLIER_ID": self.supplier_id}.items() if not v]
            logger.warning(f"[TRENDYOL] Eksik credentials: {missing}")
    
    def _get_headers(self) -> Dict[str, str]:
        """API request headers"""
        return {
            "Authorization": f"Basic {self._auth_header}",
            "Content-Type": "application/json",
            "User-Agent": f"{self.supplier_id} - SelfIntegration"
        }
    
    async def send_stock_batch(self, items: List[StockItem]) -> List[SyncResult]:
        """
        Trendyol'a stok batch'i gönder.
        API: POST /sapigw/suppliers/{supplierId}/products/price-and-inventory
        """
        results: List[SyncResult] = []
        
        if not items:
            return results
        
        # Trendyol payload formatı
        payload = {
            "items": [
                {
                    "barcode": item.barcode,
                    "quantity": max(0, item.quantity)  # Negatif olamaz
                }
                for item in items
            ]
        }
        
        url = f"{self.BASE_URL}/suppliers/{self.supplier_id}/products/price-and-inventory"
        sent_at = datetime.utcnow()
        
        try:
            session = await self.get_session()
            
            async with session.post(url, json=payload, headers=self._get_headers()) as response:
                response_at = datetime.utcnow()
                response_text = await response.text()
                
                if response.status == 200:
                    # Başarılı
                    try:
                        response_data = await response.json()
                    except:
                        response_data = {"raw": response_text[:500]}
                    
                    logger.info(f"[TRENDYOL] ✅ {len(items)} ürün gönderildi")
                    
                    for item in items:
                        results.append(SyncResult(
                            barcode=item.barcode,
                            success=True,
                            quantity_sent=max(0, item.quantity),
                            response_data=response_data,
                            sent_at=sent_at,
                            response_at=response_at
                        ))
                else:
                    # Hata
                    error_msg = f"HTTP {response.status}: {response_text[:300]}"
                    logger.error(f"[TRENDYOL] ❌ Batch hatası: {error_msg}")
                    
                    for item in items:
                        results.append(SyncResult(
                            barcode=item.barcode,
                            success=False,
                            quantity_sent=max(0, item.quantity),
                            error_message=error_msg,
                            sent_at=sent_at,
                            response_at=response_at
                        ))
                        
        except asyncio.TimeoutError:
            error_msg = "İstek zaman aşımı (timeout)"
            logger.error(f"[TRENDYOL] ❌ {error_msg}")
            for item in items:
                results.append(SyncResult(barcode=item.barcode, success=False, quantity_sent=max(0, item.quantity), error_message=error_msg))
                
        except aiohttp.ClientError as e:
            error_msg = f"Bağlantı hatası: {str(e)}"
            logger.error(f"[TRENDYOL] ❌ {error_msg}")
            for item in items:
                results.append(SyncResult(barcode=item.barcode, success=False, quantity_sent=max(0, item.quantity), error_message=error_msg))
                
        except Exception as e:
            error_msg = f"Beklenmeyen hata: {str(e)}"
            logger.error(f"[TRENDYOL] ❌ {error_msg}")
            for item in items:
                results.append(SyncResult(barcode=item.barcode, success=False, quantity_sent=max(0, item.quantity), error_message=error_msg))
        
        return results
    
    async def get_platform_products(self) -> List[Dict[str, Any]]:
        """
        Trendyol'daki tüm ürünleri çek
        API: GET /sapigw/suppliers/{supplierId}/products
        """
        all_products = []
        page = 0
        page_size = 200  # Trendyol max 200/sayfa
        
        try:
            session = await self.get_session()
            
            while True:
                url = f"{self.BASE_URL}/suppliers/{self.supplier_id}/products"
                params = {
                    "page": page,
                    "size": page_size,
                    "approved": "true"
                }
                
                async with session.get(url, params=params, headers=self._get_headers()) as response:
                    if response.status != 200:
                        logger.error(f"[TRENDYOL] Ürün çekme hatası: {response.status}")
                        break
                    
                    data = await response.json()
                    products = data.get("content", [])
                    
                    if not products:
                        break
                    
                    all_products.extend(products)
                    logger.info(f"[TRENDYOL] Sayfa {page}: {len(products)} ürün (toplam: {len(all_products)})")
                    
                    # Son sayfa mı?
                    total_pages = data.get("totalPages", 1)
                    if page >= total_pages - 1:
                        break
                    
                    page += 1
                    await asyncio.sleep(0.1)  # Rate limit
            
            await self.close_session()
            logger.info(f"[TRENDYOL] Toplam {len(all_products)} ürün çekildi")
            
        except Exception as e:
            logger.error(f"[TRENDYOL] Ürün çekme hatası: {e}")
        
        return all_products
    
    async def check_batch_status(self, batch_request_id: str) -> Dict[str, Any]:
        """
        Batch istek durumunu kontrol et
        API: GET /sapigw/suppliers/{supplierId}/products/batch-requests/{batchRequestId}
        """
        url = f"{self.BASE_URL}/suppliers/{self.supplier_id}/products/batch-requests/{batch_request_id}"
        
        try:
            session = await self.get_session()
            async with session.get(url, headers=self._get_headers()) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"error": f"HTTP {response.status}"}
        except Exception as e:
            return {"error": str(e)}


# Singleton instance
trendyol_adapter = TrendyolAdapter()
