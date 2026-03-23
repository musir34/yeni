# -*- coding: utf-8 -*-
"""
Platform Adapters - Her platform için özel stok gönderim adaptörleri
"""

from .base import BasePlatformAdapter
from .trendyol import TrendyolAdapter
from .idefix import IdefixAdapter
from .amazon import AmazonAdapter
from .hepsiburada import HepsiburadaAdapter
from .shopify import ShopifyAdapter

__all__ = [
    'BasePlatformAdapter',
    'TrendyolAdapter',
    'IdefixAdapter',
    'AmazonAdapter',
    'HepsiburadaAdapter',
    'ShopifyAdapter'
]
