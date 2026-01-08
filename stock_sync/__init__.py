# -*- coding: utf-8 -*-
"""
Stock Sync Center - Merkezi Stok Senkronizasyon Sistemi
========================================================
Tüm platformlara (Trendyol, Idefix, Amazon, WooCommerce) stok gönderimi.

Kullanım:
    from stock_sync import stock_sync_service
    
    # Manuel senkronizasyon
    result = await stock_sync_service.sync_all_platforms()
    
    # Tek platform
    result = await stock_sync_service.sync_platform("trendyol")
"""

from .service import StockSyncService, stock_sync_service
from models import SyncSession, SyncDetail, PlatformConfig

__all__ = [
    'StockSyncService',
    'stock_sync_service',
    'SyncSession',
    'SyncDetail', 
    'PlatformConfig'
]
