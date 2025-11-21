"""
WooCommerce Servis - Sipariş yönetimi
"""
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
from typing import List, Dict, Optional
from .woo_config import WooConfig
from .models import WooOrder
from models import db


class WooCommerceService:
    """WooCommerce API ile sipariş işlemleri"""
    
    def __init__(self):
        self.config = WooConfig()
        self.base_url = self.config.get_api_url()
        self.auth = HTTPBasicAuth(
            self.config.CONSUMER_KEY,
            self.config.CONSUMER_SECRET
        )
        self.timeout = self.config.TIMEOUT
    
    def _make_request(self, endpoint: str, method: str = 'GET', params: Dict = None, data: Dict = None):
        """
        WooCommerce API'ye istek gönder
        
        Args:
            endpoint: API endpoint (örn: 'orders', 'orders/123')
            method: HTTP metodu (GET, POST, PUT, DELETE)
            params: Query parametreleri
            data: Request body
            
        Returns:
            API yanıtı (dict veya list)
        """
        url = f"{self.base_url}/{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                auth=self.auth,
                params=params,
                json=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"WooCommerce API hatası: {str(e)}")
            return None
    
    def get_orders(self, status: str = None, page: int = 1, per_page: int = None) -> List[Dict]:
        """
        Siparişleri getir
        
        Args:
            status: Sipariş durumu (pending, processing, completed, cancelled, vb.)
            page: Sayfa numarası
            per_page: Sayfa başına sipariş sayısı
            
        Returns:
            Sipariş listesi
        """
        params = {
            'page': page,
            'per_page': per_page or self.config.PER_PAGE,
            'orderby': 'date',
            'order': 'desc'
        }
        
        if status:
            params['status'] = status
        
        orders = self._make_request('orders', params=params)
        return orders if orders else []
    
    def get_order(self, order_id: int) -> Optional[Dict]:
        """
        Tek bir siparişi getir
        
        Args:
            order_id: Sipariş ID'si
            
        Returns:
            Sipariş detayları
        """
        return self._make_request(f'orders/{order_id}')
    
    def update_order_status(self, order_id: int, status: str) -> Optional[Dict]:
        """
        Sipariş durumunu güncelle
        
        Args:
            order_id: Sipariş ID'si
            status: Yeni durum (pending, processing, completed, cancelled, vb.)
            
        Returns:
            Güncellenmiş sipariş
        """
        data = {'status': status}
        return self._make_request(f'orders/{order_id}', method='PUT', data=data)
    
    def add_order_note(self, order_id: int, note: str, customer_note: bool = False) -> Optional[Dict]:
        """
        Siparişe not ekle
        
        Args:
            order_id: Sipariş ID'si
            note: Not metni
            customer_note: Müşteriye gösterilsin mi
            
        Returns:
            Eklenen not
        """
        data = {
            'note': note,
            'customer_note': customer_note
        }
        return self._make_request(f'orders/{order_id}/notes', method='POST', data=data)
    
    def get_order_notes(self, order_id: int) -> List[Dict]:
        """
        Sipariş notlarını getir
        
        Args:
            order_id: Sipariş ID'si
            
        Returns:
            Not listesi
        """
        notes = self._make_request(f'orders/{order_id}/notes')
        return notes if notes else []
    
    def search_orders(self, search_term: str) -> List[Dict]:
        """
        Sipariş ara (sipariş numarası, müşteri adı, email vb.)
        
        Args:
            search_term: Arama terimi
            
        Returns:
            Bulunan siparişler
        """
        params = {
            'search': search_term,
            'per_page': self.config.PER_PAGE
        }
        orders = self._make_request('orders', params=params)
        return orders if orders else []
    
    def get_orders_by_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """
        Tarih aralığına göre siparişleri getir
        
        Args:
            start_date: Başlangıç tarihi (ISO 8601 formatında)
            end_date: Bitiş tarihi (ISO 8601 formatında)
            
        Returns:
            Sipariş listesi
        """
        params = {
            'after': start_date,
            'before': end_date,
            'per_page': self.config.PER_PAGE
        }
        orders = self._make_request('orders', params=params)
        return orders if orders else []
    
    def get_order_statuses(self) -> Dict[str, str]:
        """
        Mevcut sipariş durumlarını döndür (WooCommerce orijinal statüleri)
        
        Returns:
            Durum kodu: Durum adı sözlüğü
        """
        return {
            'pending': 'Ödeme Bekliyor',
            'processing': 'İşleme Alındı',
            'on-hold': 'Beklemede',
            'completed': 'Tamamlandı',
            'cancelled': 'İptal Edildi',
            'refunded': 'İade Edildi',
            'failed': 'Başarısız',
            'shipped': 'Kargoya Verildi',
            'trash': 'Çöp Kutusu'
        }
    
    @staticmethod
    def format_order_data(order: Dict) -> Dict:
        """
        Sipariş verisini görüntülemek için formatla
        
        Args:
            order: Ham sipariş verisi
            
        Returns:
            Formatlanmış sipariş verisi
        """
        if not order:
            return {}
        
        return {
            'id': order.get('id'),
            'order_number': order.get('number'),
            'status': order.get('status'),
            'date_created': order.get('date_created'),
            'total': order.get('total'),
            'currency': order.get('currency'),
            'customer': {
                'first_name': order.get('billing', {}).get('first_name'),
                'last_name': order.get('billing', {}).get('last_name'),
                'email': order.get('billing', {}).get('email'),
                'phone': order.get('billing', {}).get('phone'),
            },
            'billing_address': {
                'address_1': order.get('billing', {}).get('address_1'),
                'address_2': order.get('billing', {}).get('address_2'),
                'city': order.get('billing', {}).get('city'),
                'state': order.get('billing', {}).get('state'),
                'postcode': order.get('billing', {}).get('postcode'),
                'country': order.get('billing', {}).get('country'),
            },
            'shipping_address': {
                'address_1': order.get('shipping', {}).get('address_1'),
                'address_2': order.get('shipping', {}).get('address_2'),
                'city': order.get('shipping', {}).get('city'),
                'state': order.get('shipping', {}).get('state'),
                'postcode': order.get('shipping', {}).get('postcode'),
                'country': order.get('shipping', {}).get('country'),
            },
            'line_items': [
                {
                    'name': item.get('name'),
                    'product_id': item.get('product_id'),
                    'quantity': item.get('quantity'),
                    'total': item.get('total'),
                    'sku': item.get('sku'),
                }
                for item in order.get('line_items', [])
            ],
            'shipping_total': order.get('shipping_total'),
            'payment_method': order.get('payment_method_title'),
            'customer_note': order.get('customer_note'),
        }
    
    def save_order_to_db(self, order_data: Dict) -> Optional[WooOrder]:
        """
        Siparişi veritabanına kaydet veya güncelle
        
        Args:
            order_data: WooCommerce API'den gelen sipariş verisi
            
        Returns:
            Kaydedilen WooOrder instance
        """
        try:
            order_id = order_data.get('id')
            if not order_id:
                return None
            
            # Mevcut kaydı kontrol et
            existing = WooOrder.query.filter_by(order_id=order_id).first()
            
            if existing:
                # Güncelle
                existing.update_from_woo_data(order_data)
                db.session.commit()
                return existing
            else:
                # Yeni kayıt oluştur
                new_order = WooOrder.from_woo_data(order_data)
                if new_order:
                    db.session.add(new_order)
                    db.session.commit()
                    return new_order
                return None
                
        except Exception as e:
            db.session.rollback()
            print(f"Sipariş veritabanına kaydedilemedi: {e}")
            return None
    
    def save_orders_to_db(self, orders_list: List[Dict]) -> int:
        """
        Birden fazla siparişi veritabanına kaydet
        
        Args:
            orders_list: Sipariş listesi
            
        Returns:
            Kaydedilen sipariş sayısı
        """
        saved_count = 0
        for order in orders_list:
            if self.save_order_to_db(order):
                saved_count += 1
        return saved_count
    
    def get_order_from_db(self, order_id: int) -> Optional[WooOrder]:
        """
        Veritabanından sipariş getir
        
        Args:
            order_id: WooCommerce order ID
            
        Returns:
            WooOrder instance veya None
        """
        return WooOrder.query.filter_by(order_id=order_id).first()
    
    def sync_orders_to_db(self, status: str = None, days: int = 30) -> Dict:
        """
        Son X günün siparişlerini WooCommerce'den çekip veritabanına kaydet
        
        Args:
            status: Sipariş durumu filtresi
            days: Kaç günlük sipariş çekilecek
            
        Returns:
            Senkronizasyon özeti
        """
        from datetime import timedelta
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Tarih aralığındaki siparişleri çek
        orders = self.get_orders_by_date_range(
            start_date.isoformat(),
            end_date.isoformat()
        )
        
        if status:
            orders = [o for o in orders if o.get('status') == status]
        
        # Veritabanına kaydet
        saved = self.save_orders_to_db(orders)
        
        return {
            'total_fetched': len(orders),
            'total_saved': saved,
            'date_range': {
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d')
            }
        }
