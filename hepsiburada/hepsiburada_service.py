"""
Hepsiburada Marketplace API Service
Sipariş, Listeleme ve Katalog yönetimi
"""
import os
import json
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from .hepsiburada_config import HepsiburadaConfig

logger = logging.getLogger(__name__)


class HepsiburadaService:
    """Hepsiburada Marketplace API Servis Sınıfı"""

    def __init__(self):
        """Hepsiburada servisini başlat"""
        self.config = HepsiburadaConfig
        self.merchant_id = self.config.MERCHANT_ID
        self._listings_cache = None
        self._listings_cache_time = None

        if self.config.is_configured():
            logger.info(f"[HB] Service başlatıldı - Merchant: {self.merchant_id[:8]}... | Ortam: {self.config.get_env_label()}")
        else:
            logger.warning("[HB] Credentials eksik - Servis çalışmayacak")

    # ═══════════════════════════════════════════════════════════════════════════
    # GENEL API İSTEK YÖNETİMİ
    # ═══════════════════════════════════════════════════════════════════════════

    def _make_request(self, method: str, base_url: str, path: str,
                      params: dict = None, json_data: dict = None,
                      data: Any = None, headers: dict = None,
                      files: dict = None) -> Optional[requests.Response]:
        """Hepsiburada API'ye HTTP Basic Auth ile istek gönder"""
        if not self.config.is_configured():
            logger.warning("[HB] API ayarları eksik - istek yapılmadı")
            return None

        url = f"{base_url}{path}"
        auth = self.config.get_auth()

        default_headers = {
            'Accept': 'application/json',
            'User-Agent': self.config.USER_AGENT,
        }
        if headers:
            default_headers.update(headers)
        if json_data and 'Content-Type' not in default_headers:
            default_headers['Content-Type'] = 'application/json'

        try:
            response = requests.request(
                method=method,
                url=url,
                auth=auth,
                headers=default_headers,
                params=params,
                json=json_data,
                data=data,
                files=files,
                timeout=self.config.TIMEOUT,
            )

            logger.info(f"[HB] API: {method} {path} -> {response.status_code}")

            if response.status_code == 429:
                logger.warning("[HB] Rate limit aşıldı! Biraz bekleyin.")

            return response

        except requests.exceptions.Timeout:
            logger.error(f"[HB] Timeout: {method} {path}")
            return None
        except Exception as e:
            logger.error(f"[HB] API Exception: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════════
    # SİPARİŞ SERVİSLERİ
    # ═══════════════════════════════════════════════════════════════════════════

    def get_new_orders(self, offset: int = 0, limit: int = 50) -> dict:
        """
        Ödemesi tamamlanmış (yeni) siparişleri listele.
        Sipariş statüsü: Open veya Unpacked
        """
        base_url = self.config.get_order_base_url()
        path = f"/orders/merchantid/{self.merchant_id}"
        params = {
            'offset': offset,
            'limit': limit,
        }

        resp = self._make_request('GET', base_url, path, params=params)
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                return {
                    'success': True,
                    'orders': data.get('items', data.get('content', [])),
                    'total': data.get('totalCount', 0),
                    'offset': offset,
                    'limit': limit,
                    'page_count': data.get('pageCount', 1),
                }
            except Exception as e:
                logger.error(f"[HB] Sipariş parse hatası: {e}")
                return {'success': False, 'orders': [], 'total': 0, 'error': str(e)}
        else:
            status = resp.status_code if resp else 'N/A'
            text = resp.text[:200] if resp else 'No response'
            return {'success': False, 'orders': [], 'total': 0, 'error': f"HTTP {status}: {text}"}

    def get_order_detail(self, order_number: str) -> dict:
        """Siparişe ait detayları listele"""
        base_url = self.config.get_order_base_url()
        path = f"/orders/merchantid/{self.merchant_id}/ordernumber/{order_number}"

        resp = self._make_request('GET', base_url, path)
        if resp and resp.status_code == 200:
            try:
                return {'success': True, 'order': resp.json()}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        return {'success': False, 'error': f"HTTP {resp.status_code if resp else 'N/A'}"}

    def get_packages(self, offset: int = 0, limit: int = 10,
                     begin_date: str = None, end_date: str = None,
                     timespan: int = None) -> dict:
        """Paket bilgilerini listele (paketlenen siparişler)"""
        base_url = self.config.get_order_base_url()
        path = f"/packages/merchantid/{self.merchant_id}"
        params = {}

        if timespan:
            params['timespan'] = timespan
        elif begin_date and end_date:
            params['beginDate'] = begin_date
            params['endDate'] = end_date
        else:
            params['offset'] = offset
            params['limit'] = limit

        resp = self._make_request('GET', base_url, path, params=params)
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                items = data if isinstance(data, list) else data.get('items', data.get('content', []))
                total = int(resp.headers.get('totalcount', len(items) if isinstance(items, list) else 0))
                return {'success': True, 'packages': items, 'total': total}
            except Exception as e:
                return {'success': False, 'packages': [], 'total': 0, 'error': str(e)}
        return {'success': False, 'packages': [], 'total': 0,
                'error': f"HTTP {resp.status_code if resp else 'N/A'}"}

    def cancel_order_item(self, line_item_id: str) -> dict:
        """
        Sipariş kalemini iptal et.
        Sadece Open statüdeki siparişler iptal edilebilir.
        """
        base_url = self.config.get_order_base_url()
        path = f"/lineitems/merchantid/{self.merchant_id}/id/{line_item_id}/cancelbymerchant"

        resp = self._make_request('POST', base_url, path)
        if resp and resp.status_code in [200, 201, 202]:
            return {'success': True, 'message': 'Sipariş kalemi iptal edildi'}
        return {
            'success': False,
            'error': resp.text[:200] if resp else 'Bağlantı hatası'
        }

    def package_items(self, line_item_ids: list, quantities: list = None) -> dict:
        """
        Kalemleri paketle.
        line_item_ids: paketlenecek kalem ID'leri listesi
        quantities: her kalemin adet sayısı listesi
        """
        base_url = self.config.get_order_base_url()
        path = f"/packages/merchantid/{self.merchant_id}"

        body = {
            "lineItemRequests": []
        }
        for i, lid in enumerate(line_item_ids):
            qty = quantities[i] if quantities and i < len(quantities) else 1
            body["lineItemRequests"].append({
                "id": lid,
                "quantity": qty
            })

        resp = self._make_request('POST', base_url, path, json_data=body)
        if resp and resp.status_code in [200, 201]:
            try:
                data = resp.json()
                return {'success': True, 'data': data}
            except Exception:
                return {'success': True, 'data': resp.text}
        return {'success': False, 'error': resp.text[:200] if resp else 'Bağlantı hatası'}

    def unpack_package(self, package_number: str) -> dict:
        """Paketi boz"""
        base_url = self.config.get_order_base_url()
        path = f"/packages/merchantid/{self.merchant_id}/packagenumber/{package_number}/unpack"

        resp = self._make_request('POST', base_url, path)
        if resp and resp.status_code in [200, 201, 202]:
            return {'success': True, 'message': 'Paket bozuldu'}
        return {'success': False, 'error': resp.text[:200] if resp else 'Bağlantı hatası'}

    def get_cancelled_orders(self, offset: int = 0, limit: int = 50,
                             begin_date: str = None, end_date: str = None) -> dict:
        """İptal edilen siparişleri listele"""
        base_url = self.config.get_order_base_url()
        path = f"/lineitems/merchantid/{self.merchant_id}/cancelledlineitems"
        params = {'offset': offset, 'limit': limit}
        if begin_date:
            params['beginDate'] = begin_date
        if end_date:
            params['endDate'] = end_date

        resp = self._make_request('GET', base_url, path, params=params)
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                items = data if isinstance(data, list) else data.get('items', [])
                return {'success': True, 'orders': items, 'total': len(items)}
            except Exception as e:
                return {'success': False, 'orders': [], 'error': str(e)}
        return {'success': False, 'orders': [],
                'error': f"HTTP {resp.status_code if resp else 'N/A'}"}

    def get_delivered_orders(self, offset: int = 0, limit: int = 50,
                             begin_date: str = None, end_date: str = None) -> dict:
        """Teslim edilen siparişleri listele"""
        base_url = self.config.get_order_base_url()
        path = f"/lineitems/merchantid/{self.merchant_id}/deliveredlineitems"
        params = {'offset': offset, 'limit': limit}
        if begin_date:
            params['beginDate'] = begin_date
        if end_date:
            params['endDate'] = end_date

        resp = self._make_request('GET', base_url, path, params=params)
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                items = data if isinstance(data, list) else data.get('items', [])
                return {'success': True, 'orders': items, 'total': len(items)}
            except Exception as e:
                return {'success': False, 'orders': [], 'error': str(e)}
        return {'success': False, 'orders': [],
                'error': f"HTTP {resp.status_code if resp else 'N/A'}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # LİSTELEME SERVİSLERİ (Stok, Fiyat, Ürün Listesi)
    # ═══════════════════════════════════════════════════════════════════════════

    def get_listings(self, offset: int = 0, limit: int = 50,
                     hbsku: str = None, merchant_sku: str = None) -> dict:
        """
        Listing bilgilerini çek.
        Tüm listingleri veya belirli SKU'ya göre filtreleyerek çeker.
        """
        base_url = self.config.get_listing_base_url()
        path = f"/listings/merchantid/{self.merchant_id}"
        params = {'offset': offset, 'limit': limit}

        if hbsku:
            params['hepsiburadaSku'] = hbsku
        if merchant_sku:
            params['merchantSku'] = merchant_sku

        resp = self._make_request('GET', base_url, path, params=params)
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                listings = data.get('listings', data) if isinstance(data, dict) else data
                if isinstance(listings, dict):
                    listings = listings.get('listings', [])
                total = int(resp.headers.get('totalcount', len(listings) if isinstance(listings, list) else 0))
                return {
                    'success': True,
                    'listings': listings if isinstance(listings, list) else [],
                    'total': total,
                    'offset': offset,
                    'limit': limit,
                }
            except Exception as e:
                logger.error(f"[HB] Listing parse hatası: {e}")
                return {'success': False, 'listings': [], 'total': 0, 'error': str(e)}
        return {'success': False, 'listings': [], 'total': 0,
                'error': f"HTTP {resp.status_code if resp else 'N/A'}"}

    def update_listings(self, listings_data: list) -> dict:
        """
        Listing bilgilerini güncelle (fiyat, stok, kargoya veriliş süresi).
        listings_data: [
            {
                "HepsiburadaSku": "...",
                "MerchantSku": "...",
                "Price": "199,99",
                "AvailableStock": "50",
                "DispatchTime": "3",
                "CargoCompany1": "Aras Kargo",
            }, ...
        ]
        """
        base_url = self.config.get_listing_base_url()
        path = f"/listings/merchantid/{self.merchant_id}"
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        resp = self._make_request('POST', base_url, path, json_data=listings_data, headers=headers)
        if resp and resp.status_code in [200, 201, 202]:
            try:
                data = resp.json()
                return {'success': True, 'data': data}
            except Exception:
                return {'success': True, 'data': resp.text}
        return {'success': False, 'error': resp.text[:500] if resp else 'Bağlantı hatası'}

    def check_listing_update(self, upload_id: str) -> dict:
        """Listing güncelleme işlem kontrolü"""
        base_url = self.config.get_listing_base_url()
        path = f"/listings/merchantid/{self.merchant_id}/inventory-uploads/id/{upload_id}"

        resp = self._make_request('GET', base_url, path)
        if resp and resp.status_code == 200:
            try:
                return {'success': True, 'data': resp.json()}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        return {'success': False, 'error': f"HTTP {resp.status_code if resp else 'N/A'}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # KATALOG SERVİSLERİ
    # ═══════════════════════════════════════════════════════════════════════════

    def get_categories(self, page: int = 0, size: int = 1000) -> dict:
        """Kategori bilgilerini al"""
        base_url = self.config.get_catalog_base_url()
        path = "/product/api/categories/get-all-categories"
        params = {'page': page, 'size': size}

        resp = self._make_request('GET', base_url, path, params=params)
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                return {'success': True, 'categories': data.get('data', []), 'total': data.get('totalElements', 0)}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        return {'success': False, 'error': f"HTTP {resp.status_code if resp else 'N/A'}"}

    def get_category_attributes(self, category_id: int) -> dict:
        """Kategori özelliklerini al"""
        base_url = self.config.get_catalog_base_url()
        path = f"/product/api/categories/{category_id}/attributes"

        resp = self._make_request('GET', base_url, path)
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                return {'success': True, 'attributes': data.get('data', [])}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        return {'success': False, 'error': f"HTTP {resp.status_code if resp else 'N/A'}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # PROFİL SERVİSLERİ
    # ═══════════════════════════════════════════════════════════════════════════

    def get_cargo_companies(self) -> dict:
        """Kullanılabilir kargo firmalarını listele"""
        base_url = self.config.get_order_base_url()
        path = f"/cargofirms/merchantid/{self.merchant_id}"

        resp = self._make_request('GET', base_url, path)
        if resp and resp.status_code == 200:
            try:
                return {'success': True, 'companies': resp.json()}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        return {'success': False, 'error': f"HTTP {resp.status_code if resp else 'N/A'}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # BAĞLANTI TESTİ
    # ═══════════════════════════════════════════════════════════════════════════

    def test_connection(self) -> dict:
        """API bağlantı testi - Listing çekerek bağlantıyı doğrula"""
        if not self.config.is_configured():
            return {'success': False, 'message': 'API ayarları yapılmamış'}

        result = self.get_listings(offset=0, limit=1)
        if result.get('success'):
            return {
                'success': True,
                'message': f"Bağlantı başarılı! Ortam: {self.config.get_env_label()}",
                'total_listings': result.get('total', 0),
            }
        return {
            'success': False,
            'message': f"Bağlantı hatası: {result.get('error', 'Bilinmeyen hata')}",
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # CACHE İŞLEMLERİ
    # ═══════════════════════════════════════════════════════════════════════════

    def get_all_listings_cached(self) -> list:
        """Cache'den tüm listingleri döndür (10 dk geçerli)"""
        cache_file = os.path.join(os.path.dirname(__file__), 'listings_cache.json')

        # RAM cache kontrolü
        if self._listings_cache and self._listings_cache_time:
            if datetime.now() - self._listings_cache_time < timedelta(minutes=10):
                return self._listings_cache

        # Dosya cache kontrolü
        if os.path.exists(cache_file):
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(cache_file))
                if datetime.now() - mtime < timedelta(minutes=10):
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        self._listings_cache = json.load(f)
                        self._listings_cache_time = mtime
                        return self._listings_cache
            except Exception:
                pass

        return []

    def fetch_and_cache_all_listings(self) -> dict:
        """Tüm listingleri API'den çekip cache'le"""
        all_listings = []
        offset = 0
        limit = 50
        page = 0
        max_pages = 100  # Güvenlik limiti

        while page < max_pages:
            result = self.get_listings(offset=offset, limit=limit)
            if not result.get('success'):
                break

            listings = result.get('listings', [])
            if not listings:
                break

            all_listings.extend(listings)
            total = result.get('total', 0)

            offset += limit
            page += 1

            if offset >= total:
                break

        # Dosyaya kaydet
        cache_file = os.path.join(os.path.dirname(__file__), 'listings_cache.json')
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(all_listings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[HB] Cache kaydetme hatası: {e}")

        self._listings_cache = all_listings
        self._listings_cache_time = datetime.now()

        return {
            'success': True,
            'total': len(all_listings),
            'message': f"{len(all_listings)} listing cache'lendi"
        }


# Global instance
hb_service = HepsiburadaService()
