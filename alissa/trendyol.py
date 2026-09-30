# -*- coding: utf-8 -*-
"""Trendyol güncel servisleri — yalnız GET (salt-okunur).

Canlıda doğrulanmış kurallar (2026-09):
- finans: `transactionType` zorunlu, tarih aralığı en çok 15 gün, `size` 500/1000, 100 istek/dk.
- finans tarihleri gerçek UTC epoch; sipariş v2 `orderDate` ise İstanbul duvar saatini kodlar.
- sipariş v2 tarih filtresi paketin son değişim tarihine bakar, ~90 günden eskisini vermez.
"""
import base64
import logging
import os
import time
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)

KOK = 'https://apigw.trendyol.com/integration'
EPOCH = datetime(1970, 1, 1)
PENCERE_GUN = 14
BEKLEME_SN = 0.65
SETTLEMENT_TIPLERI = {
    'Sale': 'satis', 'Return': 'iade', 'Discount': 'indirim',
    'DiscountCancel': 'indirim_iptal', 'Coupon': 'kupon', 'CouponCancel': 'kupon_iptal',
}
KARGO_TIPLERI = {'Gönderi Kargo Bedeli': 'gonderi', 'İade Kargo Bedeli': 'iade'}


class TrendyolHata(Exception):
    pass


def utc_ms_ist(ms):
    """Gerçek UTC epoch (finans) → İstanbul duvar saati (naive)."""
    return EPOCH + timedelta(milliseconds=ms, hours=3)


def duvar_ms_ist(ms):
    """İstanbul duvar saatini kodlayan epoch (sipariş orderDate) → naive İstanbul."""
    return EPOCH + timedelta(milliseconds=ms)


def _ist_ms(dt):
    """Naive İstanbul → gerçek UTC epoch ms (sorgu parametresi)."""
    return int((dt - timedelta(hours=3) - EPOCH).total_seconds() * 1000)


def pencereler(bas, son, gun=PENCERE_GUN):
    while bas < son:
        bit = min(bas + timedelta(days=gun), son)
        yield bas, bit
        bas = bit


class Istemci:
    def __init__(self, api_key=None, api_secret=None, satici_id=None):
        api_key = api_key or os.getenv('API_KEY')
        api_secret = api_secret or os.getenv('API_SECRET')
        self.satici_id = satici_id or os.getenv('SUPPLIER_ID')
        if not (api_key and api_secret and self.satici_id):
            raise TrendyolHata('Trendyol API bilgileri (.env: API_KEY, API_SECRET, SUPPLIER_ID) eksik.')
        kimlik = base64.b64encode(f'{api_key}:{api_secret}'.encode()).decode()
        self.basliklar = {'Authorization': f'Basic {kimlik}',
                          'User-Agent': f'{self.satici_id} - SelfIntegration'}

    def _get(self, yol, params):
        url = f'{KOK}/{yol}'
        for deneme in range(4):
            yanit = requests.get(url, headers=self.basliklar, params=params, timeout=60)
            if yanit.status_code == 429:
                time.sleep(10 * (deneme + 1))
                continue
            if yanit.status_code != 200:
                raise TrendyolHata(f'{yol} → {yanit.status_code}: {yanit.text[:200]}')
            time.sleep(BEKLEME_SN)
            return yanit.json()
        raise TrendyolHata(f'{yol} → istek sınırı aşıldı (429)')

    def _sayfalar(self, yol, params):
        sayfa, toplam = 0, 1
        while sayfa < toplam:
            veri = self._get(yol, dict(params, page=sayfa))
            toplam = veri.get('totalPages') or 1
            yield from veri.get('content') or []
            sayfa += 1

    def settlements(self, bas, son):
        """Satış/iade/indirim/kupon kayıtları; her satıra `_tur` eklenir."""
        yol = f'finance/che/sellers/{self.satici_id}/settlements'
        for tip, tur in SETTLEMENT_TIPLERI.items():
            for b, s in pencereler(bas, son):
                for satir in self._sayfalar(yol, {'transactionType': tip, 'size': 1000,
                                                  'startDate': _ist_ms(b), 'endDate': _ist_ms(s)}):
                    satir['_tur'] = tur
                    yield satir

    def kargo_faturalari(self, bas, son):
        """Kesinti faturalarından 'Kargo Fatura' olanlar: [(fatura_no, fatura_tarihi)]."""
        yol = f'finance/che/sellers/{self.satici_id}/otherfinancials'
        for b, s in pencereler(bas, son):
            for satir in self._sayfalar(yol, {'transactionType': 'DeductionInvoices', 'size': 1000,
                                              'startDate': _ist_ms(b), 'endDate': _ist_ms(s)}):
                if satir.get('transactionType') == 'Kargo Fatura':
                    yield str(satir['id']), utc_ms_ist(satir['transactionDate'])

    def kargo_kalemleri(self, fatura_no):
        yol = f'finance/che/sellers/{self.satici_id}/cargo-invoice/{fatura_no}/items'
        yield from self._sayfalar(yol, {'size': 1000})

    def siparis_paketleri(self, bas, son):
        yol = f'order/sellers/{self.satici_id}/v2/orders'
        for b, s in pencereler(bas, son):
            yield from self._sayfalar(yol, {'startDate': _ist_ms(b), 'endDate': _ist_ms(s), 'size': 200,
                                            'orderByField': 'PackageLastModifiedDate',
                                            'orderByDirection': 'ASC'})
