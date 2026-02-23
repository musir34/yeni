# -*- coding: utf-8 -*-
"""
Platform Adapters - Her platform için özel stok gönderim adaptörleri
"""

from .base import BasePlatformAdapter
from .trendyol import TrendyolAdapter
from .idefix import IdefixAdapter
from .amazon import AmazonAdapter
from .woocommerce import WooCommerceAdapter
from .hepsiburada import HepsiburadaAdapter

__all__ = [
    'BasePlatformAdapter',
    'TrendyolAdapter',
    'IdefixAdapter',
    'AmazonAdapter',
    'WooCommerceAdapter',
    'HepsiburadaAdapter'
]
