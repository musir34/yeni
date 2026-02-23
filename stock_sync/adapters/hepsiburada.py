# -*- coding: utf-8 -*-
"""
Hepsiburada Platform Adapter
Hepsiburada Listing API ile stok senkronizasyonu
"""

import os
import base64
import asyncio
import json
from datetime import datetime
from typing import List, Dict, Any
import aiohttp

from .base import BasePlatformAdapter, StockItem, SyncResult
from logger_config import app_logger as logger


class HepsiburadaAdapter(BasePlatformAdapter):
    """Hepsiburada stok senkronizasyon adaptörü - Listing API ile güncelleme"""

    PLATFORM_NAME = "hepsiburada"
    BATCH_SIZE = 50  # Listing API batch boyutu
    RATE_LIMIT_DELAY = 0.3  # 300ms (240 req/min limit)
    TIMEOUT = 30

    def _init_config(self):
        """Hepsiburada API yapılandırması"""
        self.merchant_id = os.getenv("HB_MERCHANT_ID", "")
        self.username = os.getenv("HB_USERNAME", "")
        self.password = os.getenv("HB_PASSWORD", "")
        self.user_agent = os.getenv("HB_USER_AGENT", "gullushoes_dev")
        self.is_production = os.getenv("HB_IS_PRODUCTION", "false").lower() == "true"

        if all([self.merchant_id, self.username, self.password]):
            self.is_configured = True
            # Basic auth header
            credentials = f"{self.username}:{self.password}"
            self._auth_header = base64.b64encode(credentials.encode()).decode()

            # Base URL'ler
            if self.is_production:
                self.listing_base_url = "https://listing-external.hepsiburada.com"
                self.order_base_url = "https://oms-external.hepsiburada.com"
            else:
                self.listing_base_url = "https://listing-external-sit.hepsiburada.com"
                self.order_base_url = "https://oms-external-sit.hepsiburada.com"

            logger.info(f"[HEPSIBURADA] Adapter yapılandırıldı - Merchant: {self.merchant_id[:8]}... | Ortam: {'CANLI' if self.is_production else 'TEST'}")
        else:
            self.is_configured = False
            self._auth_header = None
            missing = [k for k, v in {
                "HB_MERCHANT_ID": self.merchant_id,
                "HB_USERNAME": self.username,
                "HB_PASSWORD": self.password
            }.items() if not v]
            logger.warning(f"[HEPSIBURADA] Eksik credentials: {missing}")

        # Barkod → HepsiburadaSku/MerchantSku eşleştirme cache
        self._sku_map: Dict[str, Dict] = {}
        self._sku_map_loaded = False

    def _get_headers(self) -> Dict[str, str]:
        """API request headers"""
        return {
            "Authorization": f"Basic {self._auth_header}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }

    async def _load_sku_map(self):
        """
        Hepsiburada listing'lerinden merchantSku → hepsiburadaSku eşleştirmesini yükle.
        merchantSku bizim barkodumuz olarak kullanılıyor.
        """
        if self._sku_map_loaded:
            return

        logger.info("[HEPSIBURADA] SKU eşleştirme map'i yükleniyor...")

        # Önce cache dosyasından dene
        cache_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'hepsiburada', 'listings_cache.json')
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    listings = json.load(f)
                for l in listings:
                    msku = l.get('merchantSku', '')
                    hbsku = l.get('hepsiburadaSku', '')
                    if msku and hbsku:
                        self._sku_map[msku] = {
                            'hepsiburadaSku': hbsku,
                            'merchantSku': msku,
                        }
                self._sku_map_loaded = True
                logger.info(f"[HEPSIBURADA] Cache'den {len(self._sku_map)} SKU eşleştirmesi yüklendi")
                return
            except Exception as e:
                logger.warning(f"[HEPSIBURADA] Cache okuma hatası: {e}")

        # Cache yoksa API'den çek
        try:
            await self._fetch_sku_map_from_api()
        except Exception as e:
            logger.error(f"[HEPSIBURADA] SKU map API'den yüklenemedi: {e}")

    async def _fetch_sku_map_from_api(self):
        """API'den tüm listing'leri çekip SKU map oluştur"""
        session = await self.get_session()
        offset = 0
        limit = 100
        total_loaded = 0

        while True:
            url = f"{self.listing_base_url}/listings/merchantid/{self.merchant_id}"
            params = {'offset': offset, 'limit': limit}

            try:
                async with session.get(url, params=params, headers=self._get_headers()) as response:
                    if response.status != 200:
                        text = await response.text()
                        logger.error(f"[HEPSIBURADA] Listing çekme hatası: {response.status} - {text[:200]}")
                        break

                    data = await response.json()
                    listings = data.get('listings', [])
                    total_count = data.get('totalCount', 0)

                    if not listings:
                        break

                    for l in listings:
                        msku = l.get('merchantSku', '')
                        hbsku = l.get('hepsiburadaSku', '')
                        if msku and hbsku:
                            self._sku_map[msku] = {
                                'hepsiburadaSku': hbsku,
                                'merchantSku': msku,
                            }

                    total_loaded += len(listings)
                    logger.info(f"[HEPSIBURADA] SKU map: {total_loaded}/{total_count} listing yüklendi")

                    if total_loaded >= total_count:
                        break

                    offset += limit
                    await asyncio.sleep(0.25)  # Rate limit

            except Exception as e:
                logger.error(f"[HEPSIBURADA] Listing çekme hatası: {e}")
                break

        self._sku_map_loaded = True
        logger.info(f"[HEPSIBURADA] API'den toplam {len(self._sku_map)} SKU eşleştirmesi yüklendi")

    def _find_sku_info(self, barcode: str) -> Dict:
        """
        Barkoda karşılık gelen HB SKU bilgisini bul.
        merchantSku genellikle barkod olarak kullanılıyor.
        """
        # Doğrudan eşleşme
        if barcode in self._sku_map:
            return self._sku_map[barcode]

        # Büyük/küçük harf duyarsız arama
        barcode_lower = barcode.lower()
        for msku, info in self._sku_map.items():
            if msku.lower() == barcode_lower:
                return info

        return {}

    async def send_stock_batch(self, items: List[StockItem]) -> List[SyncResult]:
        """
        Hepsiburada'ya stok batch'i gönder.
        API: POST /listings/merchantid/{merchantId}
        Listing API ile stok güncelleme yapılıyor.
        """
        results: List[SyncResult] = []

        if not items:
            return results

        # SKU map'i yükle (henüz yüklenmediyse)
        await self._load_sku_map()

        # Payload oluştur
        listing_updates = []
        unmatched_items = []

        for item in items:
            sku_info = self._find_sku_info(item.barcode)
            if sku_info:
                listing_updates.append({
                    "HepsiburadaSku": sku_info['hepsiburadaSku'],
                    "MerchantSku": sku_info['merchantSku'],
                    "AvailableStock": str(max(0, item.quantity)),
                })
            else:
                unmatched_items.append(item)

        # Eşleşmeyenleri logla ve başarısız döndür
        for item in unmatched_items:
            results.append(SyncResult(
                barcode=item.barcode,
                success=False,
                quantity_sent=0,
                error_message=f"HB'de eşleşen SKU bulunamadı: {item.barcode}"
            ))

        if not listing_updates:
            return results

        # API'ye gönder
        url = f"{self.listing_base_url}/listings/merchantid/{self.merchant_id}"
        sent_at = datetime.utcnow()

        try:
            session = await self.get_session()

            async with session.post(url, json=listing_updates, headers=self._get_headers()) as response:
                response_at = datetime.utcnow()
                response_text = await response.text()

                if response.status in [200, 201, 202]:
                    try:
                        response_data = await response.json()
                    except Exception:
                        response_data = {"raw": response_text[:500]}

                    logger.info(f"[HEPSIBURADA] ✅ {len(listing_updates)} ürün stok güncellendi")

                    # Başarılı sonuçları oluştur
                    matched_barcodes = {u['MerchantSku'] for u in listing_updates}
                    for item in items:
                        if item.barcode in matched_barcodes or self._find_sku_info(item.barcode):
                            results.append(SyncResult(
                                barcode=item.barcode,
                                success=True,
                                quantity_sent=max(0, item.quantity),
                                response_data=response_data,
                                sent_at=sent_at,
                                response_at=response_at
                            ))
                else:
                    error_msg = f"HTTP {response.status}: {response_text[:300]}"
                    logger.error(f"[HEPSIBURADA] ❌ Batch hatası: {error_msg}")

                    matched_barcodes = {u['MerchantSku'] for u in listing_updates}
                    for item in items:
                        if item.barcode in matched_barcodes or self._find_sku_info(item.barcode):
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
            logger.error(f"[HEPSIBURADA] ❌ {error_msg}")
            for item in items:
                if item.barcode not in {i.barcode for i in unmatched_items}:
                    results.append(SyncResult(barcode=item.barcode, success=False, quantity_sent=max(0, item.quantity), error_message=error_msg))

        except aiohttp.ClientError as e:
            error_msg = f"Bağlantı hatası: {str(e)}"
            logger.error(f"[HEPSIBURADA] ❌ {error_msg}")
            for item in items:
                if item.barcode not in {i.barcode for i in unmatched_items}:
                    results.append(SyncResult(barcode=item.barcode, success=False, quantity_sent=max(0, item.quantity), error_message=error_msg))

        except Exception as e:
            error_msg = f"Beklenmeyen hata: {str(e)}"
            logger.error(f"[HEPSIBURADA] ❌ {error_msg}")
            for item in items:
                if item.barcode not in {i.barcode for i in unmatched_items}:
                    results.append(SyncResult(barcode=item.barcode, success=False, quantity_sent=max(0, item.quantity), error_message=error_msg))

        return results

    async def get_platform_products(self) -> List[Dict[str, Any]]:
        """
        Hepsiburada'daki tüm ürünleri çek (listing'ler).
        """
        all_products = []
        offset = 0
        limit = 100

        try:
            session = await self.get_session()

            while True:
                url = f"{self.listing_base_url}/listings/merchantid/{self.merchant_id}"
                params = {'offset': offset, 'limit': limit}

                async with session.get(url, params=params, headers=self._get_headers()) as response:
                    if response.status != 200:
                        text = await response.text()
                        logger.error(f"[HEPSIBURADA] Ürün çekme hatası: {response.status} - {text[:200]}")
                        break

                    data = await response.json()
                    listings = data.get('listings', [])
                    total_count = data.get('totalCount', 0)

                    if not listings:
                        break

                    all_products.extend(listings)
                    logger.info(f"[HEPSIBURADA] {len(all_products)}/{total_count} listing çekildi")

                    if len(all_products) >= total_count:
                        break

                    offset += limit
                    await asyncio.sleep(0.25)

            await self.close_session()
            logger.info(f"[HEPSIBURADA] Toplam {len(all_products)} listing çekildi")

        except Exception as e:
            logger.error(f"[HEPSIBURADA] Ürün çekme hatası: {e}")

        return all_products


# Singleton instance
hepsiburada_adapter = HepsiburadaAdapter()
