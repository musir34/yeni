# -*- coding: utf-8 -*-
"""
Idefix Platform Adapter
Idefix API ile stok senkronizasyonu
"""

import os
import base64
import asyncio
from datetime import datetime
from typing import List, Dict, Any
import aiohttp

from .base import BasePlatformAdapter, StockItem, SyncResult
from logger_config import app_logger as logger


class IdefixAdapter(BasePlatformAdapter):
    """Idefix stok senkronizasyon adaptörü"""
    
    PLATFORM_NAME = "idefix"
    BATCH_SIZE = 50  # Idefix için daha küçük batch
    RATE_LIMIT_DELAY = 0.3  # 300ms bekleme
    PIM_BASE_URL = "https://merchantapi.idefix.com/pim"
    
    def _init_config(self):
        """Idefix API yapılandırması"""
        self.seller_id = os.getenv("IDEFIX_SELLER_ID")
        self.seller_name = os.getenv("IDEFIX_SELLER_NAME")
        self.token = os.getenv("IDEFIX_TOKEN")
        self.secret = os.getenv("IDEFIX_SECRET")
        
        if all([self.seller_id, self.token, self.secret]):
            self.is_configured = True
            # Basic auth header
            credentials = f"{self.token}:{self.secret}"
            self._auth_header = base64.b64encode(credentials.encode()).decode()
            logger.info(f"[IDEFIX] Adapter yapılandırıldı - Seller ID: {self.seller_id}")
        else:
            self.is_configured = False
            self._auth_header = None
            missing = [k for k, v in {
                "IDEFIX_SELLER_ID": self.seller_id,
                "IDEFIX_TOKEN": self.token,
                "IDEFIX_SECRET": self.secret
            }.items() if not v]
            logger.warning(f"[IDEFIX] Eksik credentials: {missing}")
    
    def _get_headers(self) -> Dict[str, str]:
        """API request headers"""
        return {
            "Authorization": f"Basic {self._auth_header}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    async def send_stock_batch(self, items: List[StockItem]) -> List[SyncResult]:
        """
        Idefix'e stok batch'i gönder.
        Idefix tek tek güncelleme yapıyor, paralel gönderiyoruz.
        """
        results: List[SyncResult] = []
        
        if not items:
            return results
        
        session = await self.get_session()
        
        # Paralel istekler için task'lar oluştur
        tasks = []
        for item in items:
            task = self._update_single_stock(session, item)
            tasks.append(task)
        
        # Tüm istekleri paralel çalıştır
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for item, result in zip(items, batch_results):
            if isinstance(result, Exception):
                results.append(SyncResult(
                    barcode=item.barcode,
                    success=False,
                    quantity_sent=max(0, item.quantity),
                    error_message=str(result)
                ))
            else:
                results.append(result)
        
        return results
    
    async def _update_single_stock(self, session: aiohttp.ClientSession, item: StockItem) -> SyncResult:
        """Tek bir ürünün stokunu güncelle"""
        url = f"{self.PIM_BASE_URL}/pool/{self.seller_id}/stock"
        
        payload = {
            "barcode": item.barcode,
            "stock": max(0, item.quantity)
        }
        
        sent_at = datetime.utcnow()
        
        try:
            async with session.post(url, json=payload, headers=self._get_headers()) as response:
                response_at = datetime.utcnow()
                response_text = await response.text()
                
                if response.status == 200:
                    try:
                        response_data = await response.json()
                    except:
                        response_data = {"raw": response_text[:200]}
                    
                    return SyncResult(
                        barcode=item.barcode,
                        success=True,
                        quantity_sent=max(0, item.quantity),
                        response_data=response_data,
                        sent_at=sent_at,
                        response_at=response_at
                    )
                else:
                    return SyncResult(
                        barcode=item.barcode,
                        success=False,
                        quantity_sent=max(0, item.quantity),
                        error_message=f"HTTP {response.status}: {response_text[:200]}",
                        sent_at=sent_at,
                        response_at=response_at
                    )
                    
        except Exception as e:
            return SyncResult(
                barcode=item.barcode,
                success=False,
                quantity_sent=max(0, item.quantity),
                error_message=str(e)
            )
    
    async def send_stock_bulk(self, items: List[StockItem]) -> List[SyncResult]:
        """
        Idefix bulk stock update (varsa)
        API: PUT /pim/pool/{sellerId}/stocks
        """
        results: List[SyncResult] = []
        
        if not items:
            return results
        
        url = f"{self.PIM_BASE_URL}/pool/{self.seller_id}/stocks"
        
        payload = {
            "stocks": [
                {
                    "barcode": item.barcode,
                    "stock": max(0, item.quantity)
                }
                for item in items
            ]
        }
        
        sent_at = datetime.utcnow()
        
        try:
            session = await self.get_session()
            
            async with session.put(url, json=payload, headers=self._get_headers()) as response:
                response_at = datetime.utcnow()
                response_text = await response.text()
                
                if response.status == 200:
                    logger.info(f"[IDEFIX] ✅ {len(items)} ürün bulk güncellendi")
                    
                    for item in items:
                        results.append(SyncResult(
                            barcode=item.barcode,
                            success=True,
                            quantity_sent=max(0, item.quantity),
                            sent_at=sent_at,
                            response_at=response_at
                        ))
                else:
                    error_msg = f"HTTP {response.status}: {response_text[:300]}"
                    logger.error(f"[IDEFIX] ❌ Bulk güncelleme hatası: {error_msg}")
                    
                    for item in items:
                        results.append(SyncResult(
                            barcode=item.barcode,
                            success=False,
                            quantity_sent=max(0, item.quantity),
                            error_message=error_msg,
                            sent_at=sent_at,
                            response_at=response_at
                        ))
                        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[IDEFIX] ❌ Bulk güncelleme exception: {error_msg}")
            for item in items:
                results.append(SyncResult(barcode=item.barcode, success=False, quantity_sent=max(0, item.quantity), error_message=error_msg))
        
        return results
    
    async def get_platform_products(self) -> List[Dict[str, Any]]:
        """
        Idefix'teki tüm ürünleri çek
        API: GET /pim/pool/{sellerId}/list
        """
        all_products = []
        page = 1
        limit = 100
        
        try:
            session = await self.get_session()
            
            while True:
                url = f"{self.PIM_BASE_URL}/pool/{self.seller_id}/list"
                params = {"page": page, "limit": limit}
                
                async with session.get(url, params=params, headers=self._get_headers()) as response:
                    if response.status != 200:
                        logger.error(f"[IDEFIX] Ürün çekme hatası: {response.status}")
                        break
                    
                    data = await response.json()
                    products = data.get("products", [])
                    
                    if not products:
                        break
                    
                    all_products.extend(products)
                    logger.info(f"[IDEFIX] Sayfa {page}: {len(products)} ürün (toplam: {len(all_products)})")
                    
                    if len(products) < limit:
                        break
                    
                    page += 1
                    await asyncio.sleep(0.1)
            
            await self.close_session()
            logger.info(f"[IDEFIX] Toplam {len(all_products)} ürün çekildi")
            
        except Exception as e:
            logger.error(f"[IDEFIX] Ürün çekme hatası: {e}")
        
        return all_products


# Singleton instance
idefix_adapter = IdefixAdapter()
