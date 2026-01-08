# -*- coding: utf-8 -*-
"""
WooCommerce Platform Adapter
WooCommerce REST API ile stok senkronizasyonu
"""

import os
import base64
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
import aiohttp

from .base import BasePlatformAdapter, StockItem, SyncResult
from logger_config import app_logger as logger


class WooCommerceAdapter(BasePlatformAdapter):
    """WooCommerce stok senkronizasyon adaptörü"""
    
    PLATFORM_NAME = "woocommerce"
    BATCH_SIZE = 100  # WooCommerce batch update destekliyor
    RATE_LIMIT_DELAY = 0.2
    
    def _init_config(self):
        """WooCommerce API yapılandırması"""
        self.store_url = os.getenv("WOO_STORE_URL", "").rstrip("/")
        self.consumer_key = os.getenv("WOO_CONSUMER_KEY")
        self.consumer_secret = os.getenv("WOO_CONSUMER_SECRET")
        
        if all([self.store_url, self.consumer_key, self.consumer_secret]):
            self.is_configured = True
            # Basic auth header
            credentials = f"{self.consumer_key}:{self.consumer_secret}"
            self._auth_header = base64.b64encode(credentials.encode()).decode()
            logger.info(f"[WOOCOMMERCE] Adapter yapılandırıldı - Store: {self.store_url}")
        else:
            self.is_configured = False
            self._auth_header = None
            missing = [k for k, v in {
                "WOO_STORE_URL": self.store_url,
                "WOO_CONSUMER_KEY": self.consumer_key,
                "WOO_CONSUMER_SECRET": self.consumer_secret
            }.items() if not v]
            logger.warning(f"[WOOCOMMERCE] Eksik credentials: {missing}")
        
        # Barkod -> Product ID mapping cache
        self._barcode_to_id_cache: Dict[str, int] = {}
    
    def _get_headers(self) -> Dict[str, str]:
        """API request headers"""
        return {
            "Authorization": f"Basic {self._auth_header}",
            "Content-Type": "application/json"
        }
    
    async def _get_product_id_by_sku(self, session: aiohttp.ClientSession, sku: str) -> Optional[int]:
        """SKU (barkod) ile ürün ID'si bul"""
        # Cache'de var mı?
        if sku in self._barcode_to_id_cache:
            return self._barcode_to_id_cache[sku]
        
        url = f"{self.store_url}/wp-json/wc/v3/products"
        params = {"sku": sku}
        
        try:
            async with session.get(url, params=params, headers=self._get_headers()) as response:
                if response.status == 200:
                    products = await response.json()
                    if products and len(products) > 0:
                        product_id = products[0].get("id")
                        if product_id:
                            self._barcode_to_id_cache[sku] = product_id
                            return product_id
        except Exception as e:
            logger.error(f"[WOOCOMMERCE] SKU arama hatası ({sku}): {e}")
        
        return None
    
    async def send_stock_batch(self, items: List[StockItem]) -> List[SyncResult]:
        """
        WooCommerce'e stok batch'i gönder.
        Direkt woo_product_id kullanarak batch update yapar - API araması gerekmez!
        """
        results: List[SyncResult] = []
        
        if not items:
            return results
        
        session = await self.get_session()
        
        # woo_product_id olan ürünleri batch update için hazırla
        batch_updates = []
        items_with_ids = []
        
        for item in items:
            # Direkt StockItem'daki woo_product_id kullan (Service'den geliyor)
            if item.woo_product_id:
                batch_updates.append({
                    "id": item.woo_product_id,
                    "stock_quantity": max(0, item.quantity),
                    "manage_stock": True
                })
                items_with_ids.append((item, item.woo_product_id))
            else:
                # woo_product_id yoksa hata olarak işaretle (normalde Service atlamış olmalı)
                results.append(SyncResult(
                    barcode=item.barcode,
                    success=False,
                    quantity_sent=max(0, item.quantity),
                    error_message="WooCommerce product_id bulunamadı"
                ))
        
        if not batch_updates:
            return results
        
        # Batch update gönder
        url = f"{self.store_url}/wp-json/wc/v3/products/batch"
        payload = {"update": batch_updates}
        sent_at = datetime.utcnow()
        
        try:
            async with session.post(url, json=payload, headers=self._get_headers()) as response:
                response_at = datetime.utcnow()
                
                if response.status == 200:
                    response_data = await response.json()
                    updated = response_data.get("update", [])
                    
                    logger.info(f"[WOOCOMMERCE] ✅ {len(updated)} ürün güncellendi")
                    
                    # Başarılı olanları işaretle
                    updated_ids = {p.get("id") for p in updated}
                    
                    for item, product_id in items_with_ids:
                        if product_id in updated_ids:
                            results.append(SyncResult(
                                barcode=item.barcode,
                                success=True,
                                quantity_sent=max(0, item.quantity),
                                response_data={"product_id": product_id},
                                sent_at=sent_at,
                                response_at=response_at
                            ))
                        else:
                            results.append(SyncResult(
                                barcode=item.barcode,
                                success=False,
                                quantity_sent=max(0, item.quantity),
                                error_message="Batch içinde güncellenmedi",
                                sent_at=sent_at,
                                response_at=response_at
                            ))
                else:
                    error_text = await response.text()
                    error_msg = f"HTTP {response.status}: {error_text[:300]}"
                    logger.error(f"[WOOCOMMERCE] ❌ Batch hatası: {error_msg}")
                    
                    for item, _ in items_with_ids:
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
            logger.error(f"[WOOCOMMERCE] ❌ Batch exception: {error_msg}")
            for item, _ in items_with_ids:
                results.append(SyncResult(barcode=item.barcode, success=False, quantity_sent=max(0, item.quantity), error_message=error_msg))
        
        return results
    
    async def get_platform_products(self) -> List[Dict[str, Any]]:
        """
        WooCommerce'deki tüm ürünleri çek
        """
        all_products = []
        page = 1
        per_page = 100
        
        try:
            session = await self.get_session()
            
            while True:
                url = f"{self.store_url}/wp-json/wc/v3/products"
                params = {
                    "page": page,
                    "per_page": per_page,
                    "status": "publish"
                }
                
                async with session.get(url, params=params, headers=self._get_headers()) as response:
                    if response.status != 200:
                        logger.error(f"[WOOCOMMERCE] Ürün çekme hatası: {response.status}")
                        break
                    
                    products = await response.json()
                    
                    if not products:
                        break
                    
                    all_products.extend(products)
                    logger.info(f"[WOOCOMMERCE] Sayfa {page}: {len(products)} ürün (toplam: {len(all_products)})")
                    
                    # Total pages header'dan kontrol
                    total_pages = int(response.headers.get("X-WP-TotalPages", 1))
                    
                    if page >= total_pages:
                        break
                    
                    page += 1
                    await asyncio.sleep(0.2)
            
            await self.close_session()
            
            # Varyasyonları da çek
            await self._fetch_variations(all_products)
            
            logger.info(f"[WOOCOMMERCE] Toplam {len(all_products)} ürün çekildi")
            
        except Exception as e:
            logger.error(f"[WOOCOMMERCE] Ürün çekme hatası: {e}")
        
        return all_products
    
    async def _fetch_variations(self, products: List[Dict]) -> None:
        """Variable ürünlerin varyasyonlarını çek"""
        session = await self.get_session()
        
        for product in products:
            if product.get("type") == "variable":
                product_id = product.get("id")
                
                try:
                    url = f"{self.store_url}/wp-json/wc/v3/products/{product_id}/variations"
                    
                    async with session.get(url, headers=self._get_headers()) as response:
                        if response.status == 200:
                            variations = await response.json()
                            product["variations_data"] = variations
                            
                            # Her varyasyonu cache'e ekle
                            for var in variations:
                                sku = var.get("sku")
                                var_id = var.get("id")
                                if sku and var_id:
                                    self._barcode_to_id_cache[sku] = var_id
                                    
                except Exception as e:
                    logger.warning(f"[WOOCOMMERCE] Varyasyon çekme hatası (ID: {product_id}): {e}")
                
                await asyncio.sleep(0.1)


# Singleton instance
woocommerce_adapter = WooCommerceAdapter()
