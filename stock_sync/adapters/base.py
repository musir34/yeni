# -*- coding: utf-8 -*-
"""
Base Platform Adapter - Tüm platform adaptörlerinin temel sınıfı
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import asyncio
import aiohttp
from logger_config import app_logger as logger


@dataclass
class StockItem:
    """Stok güncellemesi için ürün bilgisi"""
    barcode: str
    quantity: int
    sku: Optional[str] = None
    asin: Optional[str] = None  # Amazon ASIN
    woo_product_id: Optional[int] = None  # WooCommerce product ID
    extra_data: Optional[Dict] = None


@dataclass
class SyncResult:
    """Senkronizasyon sonucu"""
    barcode: str
    success: bool
    quantity_sent: int = 0  # Gönderilen stok miktarı
    error_message: Optional[str] = None
    response_data: Optional[Dict] = None
    sent_at: Optional[datetime] = None
    response_at: Optional[datetime] = None


class BasePlatformAdapter(ABC):
    """
    Tüm platform adaptörlerinin temel sınıfı.
    Her platform bu sınıftan türetilmeli ve gerekli metodları implement etmeli.
    """
    
    PLATFORM_NAME: str = "base"
    BATCH_SIZE: int = 100
    RATE_LIMIT_DELAY: float = 0.1  # saniye
    MAX_RETRIES: int = 3
    TIMEOUT: int = 60
    
    def __init__(self):
        self.is_configured = False
        self._session: Optional[aiohttp.ClientSession] = None
        self._init_config()
    
    @abstractmethod
    def _init_config(self):
        """Platform yapılandırmasını başlat (API keys, URLs vs.)"""
        pass
    
    @abstractmethod
    async def send_stock_batch(self, items: List[StockItem]) -> List[SyncResult]:
        """
        Bir batch stok güncellemesi gönder.
        
        Args:
            items: Güncellenecek ürünler listesi
            
        Returns:
            Her ürün için sonuç listesi
        """
        pass
    
    @abstractmethod
    async def get_platform_products(self) -> List[Dict[str, Any]]:
        """
        Platformdaki ürünleri çek (barkod eşleştirmesi için).
        
        Returns:
            Platform ürünleri listesi
        """
        pass
    
    async def get_session(self) -> aiohttp.ClientSession:
        """HTTP session al veya oluştur"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.TIMEOUT)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close_session(self):
        """HTTP session'ı kapat"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def send_all_stocks(self, items: List[StockItem], progress_callback=None) -> List[SyncResult]:
        """
        Tüm stokları batch'ler halinde gönder.
        
        Args:
            items: Tüm ürünler
            progress_callback: İlerleme callback fonksiyonu (sent_count, total_count)
            
        Returns:
            Tüm sonuçlar
        """
        if not self.is_configured:
            logger.warning(f"[{self.PLATFORM_NAME.upper()}] Platform yapılandırılmamış, gönderim atlanıyor")
            return [SyncResult(barcode=item.barcode, success=False, error_message="Platform yapılandırılmamış") 
                    for item in items]
        
        all_results: List[SyncResult] = []
        total = len(items)
        sent = 0
        
        # Batch'lere böl
        for i in range(0, total, self.BATCH_SIZE):
            batch = items[i:i + self.BATCH_SIZE]
            
            # Retry mekanizması
            for attempt in range(self.MAX_RETRIES):
                try:
                    results = await self.send_stock_batch(batch)
                    all_results.extend(results)
                    sent += len(batch)
                    
                    if progress_callback:
                        progress_callback(sent, total)
                    
                    # Rate limit
                    if self.RATE_LIMIT_DELAY > 0 and i + self.BATCH_SIZE < total:
                        await asyncio.sleep(self.RATE_LIMIT_DELAY)
                    
                    break  # Başarılı, retry'dan çık
                    
                except Exception as e:
                    logger.error(f"[{self.PLATFORM_NAME.upper()}] Batch {i//self.BATCH_SIZE + 1} hatası (deneme {attempt + 1}): {e}")
                    
                    if attempt == self.MAX_RETRIES - 1:
                        # Son deneme de başarısız
                        for item in batch:
                            all_results.append(SyncResult(
                                barcode=item.barcode,
                                success=False,
                                error_message=str(e)
                            ))
                        sent += len(batch)
                        if progress_callback:
                            progress_callback(sent, total)
                    else:
                        # Bekle ve tekrar dene
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        await self.close_session()
        return all_results
    
    def validate_config(self) -> bool:
        """Yapılandırmanın geçerli olup olmadığını kontrol et"""
        return self.is_configured
    
    def __repr__(self):
        return f"<{self.__class__.__name__} configured={self.is_configured}>"
