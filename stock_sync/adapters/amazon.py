# -*- coding: utf-8 -*-
"""
Amazon Platform Adapter
Amazon SP-API Feeds API ile toplu stok senkronizasyonu
"""

import os
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import aiohttp

from .base import BasePlatformAdapter, StockItem, SyncResult
from logger_config import app_logger as logger


class AmazonAdapter(BasePlatformAdapter):
    """Amazon SP-API stok senkronizasyon adaptörü - Listings API ile güncelleme"""
    
    PLATFORM_NAME = "amazon"
    BATCH_SIZE = 50  # 50 ürünlük batch'ler
    RATE_LIMIT_DELAY = 1.0  # Rate limit için 1 saniye bekleme
    LWA_ENDPOINT = "https://api.amazon.com/auth/o2/token"
    SP_API_ENDPOINT = "https://sellingpartnerapi-eu.amazon.com"
    
    def _init_config(self):
        """Amazon SP-API yapılandırması"""
        self.lwa_client_id = os.getenv("AMAZON_LWA_CLIENT_ID")
        self.lwa_client_secret = os.getenv("AMAZON_LWA_CLIENT_SECRET")
        self.refresh_token = os.getenv("AMAZON_REFRESH_TOKEN")
        self.seller_id = os.getenv("AMAZON_SELLER_ID")
        self.marketplace_id = os.getenv("AMAZON_MARKETPLACE_ID", "A33AVAJ2PDY3EV")  # Türkiye
        
        # Access token cache
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        
        if all([self.lwa_client_id, self.lwa_client_secret, self.refresh_token, self.seller_id]):
            self.is_configured = True
            logger.info(f"[AMAZON] Adapter yapılandırıldı - Seller ID: {self.seller_id}, Marketplace: {self.marketplace_id}")
        else:
            self.is_configured = False
            missing = [k for k, v in {
                "AMAZON_LWA_CLIENT_ID": self.lwa_client_id,
                "AMAZON_LWA_CLIENT_SECRET": self.lwa_client_secret,
                "AMAZON_REFRESH_TOKEN": self.refresh_token,
                "AMAZON_SELLER_ID": self.seller_id
            }.items() if not v]
            logger.warning(f"[AMAZON] Eksik credentials: {missing}")
    
    async def _get_access_token(self) -> Optional[str]:
        """LWA access token al (cache veya yeni)"""
        # Cache kontrolü
        if self._access_token and self._token_expires_at:
            if datetime.utcnow() < self._token_expires_at:
                return self._access_token
        
        try:
            session = await self.get_session()
            
            payload = {
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token,
                'client_id': self.lwa_client_id,
                'client_secret': self.lwa_client_secret
            }
            
            async with session.post(self.LWA_ENDPOINT, data=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    self._access_token = data['access_token']
                    expires_in = data.get('expires_in', 3600)
                    self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 60)
                    logger.info(f"[AMAZON] ✅ Access token alındı (expires in {expires_in}s)")
                    return self._access_token
                else:
                    text = await response.text()
                    logger.error(f"[AMAZON] ❌ Token alma hatası: {response.status} - {text[:200]}")
                    return None
                    
        except Exception as e:
            logger.error(f"[AMAZON] ❌ Token alma exception: {e}")
            return None
    
    def _get_headers(self, access_token: str, content_type: str = 'application/json') -> Dict[str, str]:
        """API request headers"""
        return {
            'x-amz-access-token': access_token,
            'Content-Type': content_type
        }
    
    async def send_stock_batch(self, items: List[StockItem]) -> List[SyncResult]:
        """
        Amazon Listings API ile stok güncellemesi.
        Paralel isteklerle hızlandırılmış.
        """
        results: List[SyncResult] = []
        
        if not items:
            return results
        
        access_token = await self._get_access_token()
        if not access_token:
            error_msg = "Access token alınamadı"
            for item in items:
                results.append(SyncResult(barcode=item.barcode, success=False, error_message=error_msg))
            return results
        
        session = await self.get_session()
        
        # Paralel istekler (semaphore ile rate limit kontrolü)
        semaphore = asyncio.Semaphore(3)  # Max 3 paralel istek (Amazon rate limit sıkı)
        
        async def update_with_semaphore(item):
            async with semaphore:
                result = await self._update_single_inventory(session, access_token, item)
                await asyncio.sleep(0.5)  # Rate limit için 500ms bekleme
                return result
        
        tasks = [update_with_semaphore(item) for item in items]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for item, result in zip(items, batch_results):
            if isinstance(result, Exception):
                results.append(SyncResult(
                    barcode=item.barcode,
                    success=False,
                    error_message=str(result)
                ))
            else:
                results.append(result)
        
        return results
    
    async def _update_single_inventory(self, session: aiohttp.ClientSession, access_token: str, item: StockItem) -> SyncResult:
        """Tek ürün için inventory güncelle - Listings API (ASIN kullanarak)"""
        # Amazon için ASIN'i SKU olarak kullan (veya SKU varsa onu)
        sku = item.asin or item.sku or item.barcode
        
        if not sku:
            return SyncResult(
                barcode=item.barcode,
                success=False,
                quantity_sent=max(0, item.quantity),
                error_message="ASIN/SKU bulunamadı"
            )
        
        url = f"{self.SP_API_ENDPOINT}/listings/2021-08-01/items/{self.seller_id}/{sku}"
        
        params = {
            "marketplaceIds": self.marketplace_id
        }
        
        # Inventory patch payload
        payload = {
            "productType": "PRODUCT",
            "patches": [
                {
                    "op": "replace",
                    "path": "/attributes/fulfillment_availability",
                    "value": [
                        {
                            "fulfillment_channel_code": "DEFAULT",
                            "quantity": max(0, item.quantity)
                        }
                    ]
                }
            ]
        }
        
        sent_at = datetime.utcnow()
        
        try:
            async with session.patch(url, json=payload, params=params, headers=self._get_headers(access_token)) as response:
                response_at = datetime.utcnow()
                response_text = await response.text()
                
                if response.status in [200, 201, 202]:
                    try:
                        response_data = await response.json()
                    except:
                        response_data = {"status": "accepted"}
                    
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
                        error_message=f"HTTP {response.status}: {response_text[:100]}",
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
    
    def _build_inventory_feed_xml(self, items: List[StockItem]) -> str:
        """Amazon Inventory Feed XML oluştur"""
        messages = ""
        for i, item in enumerate(items, 1):
            sku = item.sku or item.barcode
            qty = max(0, item.quantity)
            messages += f"""
    <Message>
        <MessageID>{i}</MessageID>
        <OperationType>Update</OperationType>
        <Inventory>
            <SKU>{sku}</SKU>
            <Quantity>{qty}</Quantity>
        </Inventory>
    </Message>"""
        
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<AmazonEnvelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="amzn-envelope.xsd">
    <Header>
        <DocumentVersion>1.01</DocumentVersion>
        <MerchantIdentifier>{self.seller_id}</MerchantIdentifier>
    </Header>
    <MessageType>Inventory</MessageType>
    <PurgeAndReplace>false</PurgeAndReplace>{messages}
</AmazonEnvelope>"""
    
    async def get_feed_status(self, feed_id: str) -> Dict[str, Any]:
        """Feed işleme durumunu kontrol et"""
        access_token = await self._get_access_token()
        if not access_token:
            return {"success": False, "error": "Token alınamadı"}
        
        session = await self.get_session()
        url = f"{self.SP_API_ENDPOINT}/feeds/2021-06-30/feeds/{feed_id}"
        
        try:
            async with session.get(url, headers=self._get_headers(access_token)) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "success": True,
                        "feedId": data.get("feedId"),
                        "processingStatus": data.get("processingStatus"),
                        "resultFeedDocumentId": data.get("resultFeedDocumentId")
                    }
                else:
                    text = await response.text()
                    return {"success": False, "error": f"HTTP {response.status}: {text[:200]}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_platform_products(self) -> List[Dict[str, Any]]:
        """
        Amazon'daki ürünleri çek
        Catalog Items API
        """
        all_products = []
        
        access_token = await self._get_access_token()
        if not access_token:
            logger.error("[AMAZON] Token alınamadı, ürünler çekilemedi")
            return all_products
        
        try:
            session = await self.get_session()
            
            # GET /catalog/2022-04-01/items
            url = f"{self.SP_API_ENDPOINT}/catalog/2022-04-01/items"
            
            params = {
                "marketplaceIds": self.marketplace_id,
                "sellerId": self.seller_id,
                "pageSize": 20
            }
            
            next_token = None
            page = 1
            
            while True:
                if next_token:
                    params["pageToken"] = next_token
                
                async with session.get(url, params=params, headers=self._get_headers(access_token)) as response:
                    if response.status != 200:
                        text = await response.text()
                        logger.error(f"[AMAZON] Ürün çekme hatası: {response.status} - {text[:200]}")
                        break
                    
                    data = await response.json()
                    items = data.get("items", [])
                    
                    if not items:
                        break
                    
                    all_products.extend(items)
                    logger.info(f"[AMAZON] Sayfa {page}: {len(items)} ürün (toplam: {len(all_products)})")
                    
                    # Pagination
                    pagination = data.get("pagination", {})
                    next_token = pagination.get("nextToken")
                    
                    if not next_token:
                        break
                    
                    page += 1
                    await asyncio.sleep(0.5)  # Rate limit
            
            await self.close_session()
            logger.info(f"[AMAZON] Toplam {len(all_products)} ürün çekildi")
            
        except Exception as e:
            logger.error(f"[AMAZON] Ürün çekme hatası: {e}")
        
        return all_products


# Singleton instance
amazon_adapter = AmazonAdapter()
