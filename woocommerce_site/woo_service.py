"""
WooCommerce Servis - Sipariş yönetimi
"""
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
from typing import List, Dict, Optional
from .woo_config import WooConfig
from .models import WooOrder
from models import db, Product
import logging

logger = logging.getLogger(__name__)


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
        import logging
        logger = logging.getLogger(__name__)
        
        url = f"{self.base_url}/{endpoint}"
        
        logger.info(f"[WOO_API] {method} {url} (params={params})")
        
        try:
            response = requests.request(
                method=method,
                url=url,
                auth=self.auth,
                params=params,
                json=data,
                timeout=self.timeout
            )
            
            logger.info(f"[WOO_API] Response: {response.status_code}")
            
            # Detaylı hata logu
            if response.status_code >= 400:
                logger.error(f"[WOO_API] ❌ HTTP {response.status_code}: {response.text[:500]}")
            
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"[WOO_API] ✅ Success: {type(result)} (len={len(result) if isinstance(result, (list, dict)) else 'N/A'})")
            
            return result
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"[WOO_API] ❌ HTTP Error: {e}")
            logger.error(f"[WOO_API] Response: {e.response.text if hasattr(e, 'response') else 'No response'}")
            return None
        except requests.exceptions.Timeout as e:
            logger.error(f"[WOO_API] ❌ Timeout: {e}")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[WOO_API] ❌ Connection Error: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"[WOO_API] ❌ Request Error: {e}")
            return None
        except Exception as e:
            logger.error(f"[WOO_API] ❌ Unexpected Error: {e}", exc_info=True)
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
    
    def get_product(self, product_id: int) -> Optional[Dict]:
        """
        Tek bir ürünü getir (meta_data ile birlikte)
        
        Args:
            product_id: Ürün ID'si
            
        Returns:
            Ürün detayları (barcode meta_data dahil)
        """
        return self._make_request(f'products/{product_id}')
    
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
            'processing': 'Hazırlanıyor',
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
        + Siparişteki ürünleri otomatik SKU bazlı eşleştir
        
        Args:
            order_data: WooCommerce API'den gelen sipariş verisi
            
        Returns:
            Kaydedilen WooOrder instance
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            order_id = order_data.get('id')
            if not order_id:
                logger.error("[SAVE_ORDER] order_id bulunamadı!")
                return None
            
            logger.info(f"[SAVE_ORDER] Sipariş kaydediliyor: order_id={order_id}, number={order_data.get('number')}")
            
            # 🔥 SİPARİŞTEKİ ÜRÜNLERİ OTOMATIK EŞLEŞTİR
            line_items = order_data.get('line_items', [])
            if line_items:
                logger.info(f"[SAVE_ORDER] {len(line_items)} ürün için otomatik eşleştirme kontrol ediliyor...")
                for item in line_items:
                    product_id = item.get('product_id')
                    sku = item.get('sku')
                    
                    if product_id and sku:
                        # SKU bazlı otomatik eşleştirme
                        mapped_product = self.auto_map_product_from_sku(product_id, sku)
                        if mapped_product:
                            logger.info(f"[SAVE_ORDER] ✅ Ürün eşleştirildi: {sku} → {mapped_product.barcode}")
                        else:
                            logger.warning(f"[SAVE_ORDER] ⚠️ Ürün eşleştirilemedi: WooID={product_id}, SKU={sku}")
            
            # Mevcut kaydı kontrol et
            existing = WooOrder.query.filter_by(order_id=order_id).first()
            
            if existing:
                # Güncelle
                logger.info(f"[SAVE_ORDER] Mevcut kayıt bulundu (DB ID={existing.id}), güncelleniyor...")
                existing.update_from_woo_data(order_data)
                db.session.commit()
                logger.info(f"[SAVE_ORDER] ✅ Güncelleme başarılı: #{existing.order_number}")
                return existing
            else:
                # Yeni kayıt oluştur
                logger.info(f"[SAVE_ORDER] Yeni kayıt oluşturuluyor...")
                new_order = WooOrder.from_woo_data(order_data)
                if new_order:
                    db.session.add(new_order)
                    db.session.commit()
                    logger.info(f"[SAVE_ORDER] ✅ Yeni kayıt başarılı: DB ID={new_order.id}, #{new_order.order_number}")
                    return new_order
                else:
                    logger.error(f"[SAVE_ORDER] ❌ from_woo_data() None döndürdü!")
                    return None
                
        except Exception as e:
            db.session.rollback()
            logger.error(f"[SAVE_ORDER] ❌ HATA: {e}", exc_info=True)
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
        
        # Veritabanına kaydet (SADECE woo_orders tablosuna)
        saved = self.save_orders_to_db(orders)
        # ❌ OrderCreated tablosuna KAYDETME - WooCommerce ayrı, Trendyol ayrı
        # saved_to_created = self.sync_to_order_created(orders)
        
        return {
            'total_fetched': len(orders),
            'total_saved': saved,
            # 'saved_to_created': saved_to_created,
            'date_range': {
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d')
            }
        }
    
    def sync_to_order_created(self, orders_list: List[Dict]) -> int:
        """
        WooCommerce siparişlerini OrderCreated tablosuna kaydet (Trendyol mantığıyla)
        
        Her sipariş için TEK OrderCreated kaydı oluşturur (Trendyol gibi)
        - Tüm ürünler details JSON'unda
        - Her ürün: barcode (SKU), name, quantity, price, image_url
        - source = 'WOOCOMMERCE'
        
        Koşullar:
        - Durum: processing, on-hold, shipped
        - Müşteri bilgileri eksiksiz
        - Ödeme yöntemi belirtilmiş
        
        Args:
            orders_list: WooCommerce siparişleri
            
        Returns:
            OrderCreated'a kaydedilen sipariş sayısı
        """
        from models import OrderCreated
        import json
        
        saved_count = 0
        
        for order_data in orders_list:
            try:
                # Durum kontrolü
                status = order_data.get('status', '')
                order_id = order_data.get('id')
                
                print(f"[WOO-SYNC] Sipariş #{order_id} kontrol ediliyor, durum: {status}")
                
                if status not in ['processing', 'on-hold', 'shipped']:
                    print(f"[WOO-SYNC] Sipariş #{order_id} atlandı - durum uygun değil: {status}")
                    continue
                
                # Müşteri bilgileri
                billing = order_data.get('billing', {})
                shipping = order_data.get('shipping', {})
                first_name = billing.get('first_name', '').strip()
                last_name = billing.get('last_name', '').strip()
                phone = billing.get('phone', '').strip()
                
                # Adres - önce shipping, yoksa billing
                address = shipping.get('address_1', '').strip() or billing.get('address_1', '').strip()
                city = shipping.get('city', '').strip() or billing.get('city', '').strip()
                full_address = f"{address}, {city}" if city else address
                
                print(f"[WOO-SYNC] Sipariş #{order_id} bilgiler: name={first_name} {last_name}, phone={phone}, address={address[:20] if address else 'YOK'}")
                
                # Bilgiler eksikse atla
                if not all([first_name, last_name, phone, address]):
                    print(f"[WOO-SYNC] Sipariş #{order_id} atlandı - bilgiler eksik")
                    continue
                
                # Ödeme yöntemi
                payment_method = order_data.get('payment_method', '').strip()
                if not payment_method:
                    print(f"[WOO-SYNC] Sipariş #{order_id} atlandı - ödeme yöntemi yok")
                    continue
                
                # Zaten var mı kontrol et
                order_number = str(order_id)
                existing = OrderCreated.query.filter_by(order_number=order_number).first()
                
                if existing:
                    print(f"[WOO-SYNC] Sipariş #{order_id} atlandı - zaten OrderCreated'da var")
                    continue
                
                print(f"[WOO-SYNC] Sipariş #{order_id} OrderCreated'a eklenecek...")
                
                # 🔥 YENİ MANTIK: product_id'yi kaydet, details JSON'da da sakla
                # Sipariş hazırla sayfası product_id ile Product tablosundan bilgi çekecek
                
                line_items = order_data.get('line_items', [])
                details_list = []
                total_qty = 0
                first_product_id = ''  # İlk ürünün WooCommerce ID'si
                
                for item in line_items:
                    product_id = item.get('product_id')
                    variation_id = item.get('variation_id')
                    
                    # WooCommerce'den gelen ID'yi kullan (varyasyon varsa onu, yoksa ürün ID'sini)
                    woo_id = variation_id if variation_id else product_id
                    
                    if not first_product_id:
                        first_product_id = str(woo_id)  # product_barcode alanına kaydedilecek
                    
                    qty = int(item.get('quantity', 1))
                    total_qty += qty
                    
                    # Details JSON'a WooCommerce ID'lerini kaydet
                    details_list.append({
                        'woo_product_id': product_id,
                        'woo_variation_id': variation_id,
                        'woo_id': woo_id,  # Kullanılacak ID (variation > product)
                        'quantity': qty,
                        'price': float(item.get('price', 0)),
                        'line_total_price': float(item.get('total', 0)),
                        'line_id': str(item.get('id', '')),
                        'product_name': item.get('name', '')  # Yedek olarak WooCommerce'den gelen isim
                    })
                    
                    print(f"[WOO-SYNC] ➕ Ürün: WooID={woo_id}, qty={qty}, name={item.get('name', '')[:30]}")
                
                # OrderCreated kaydı oluştur (TEK KAYIT - Trendyol gibi)
                new_order = OrderCreated(
                    order_number=order_number,
                    order_date=datetime.fromisoformat(order_data.get('date_created', '').replace('Z', '+00:00')) if order_data.get('date_created') else datetime.utcnow(),
                    status=status,
                    customer_name=first_name,
                    customer_surname=last_name,
                    customer_address=full_address,
                    customer_id=billing.get('email', ''),
                    product_barcode=first_product_id,  # 🔥 İlk ürünün WooCommerce ID'si
                    product_name=', '.join([item.get('name', '') for item in line_items[:3]]),  # İlk 3 ürün
                    quantity=total_qty,
                    amount=float(order_data.get('total', 0)),
                    currency_code=order_data.get('currency', 'TRY'),
                    package_number=order_number,
                    details=json.dumps(details_list, ensure_ascii=False),  # 🔥 TÜM ÜRÜNLER
                    cargo_provider_name='MNG',
                    shipment_package_id=None,
                    source='WOOCOMMERCE'  # 🔥 KAYNAK BİLGİSİ
                )
                
                db.session.add(new_order)
                db.session.commit()
                saved_count += 1
                print(f"[WOO-SYNC] ✅ Sipariş #{order_id} OrderCreated'a eklendi ({len(details_list)} ürün)")
                
            except Exception as e:
                db.session.rollback()
                print(f"❌ WooCommerce sipariş OrderCreated'a kaydedilemedi ({order_data.get('id')}): {e}")
                import traceback
                traceback.print_exc()
                continue
        
        return saved_count
    
    @staticmethod
    def auto_map_product_from_sku(woo_product_id: int, sku: str) -> Optional[Product]:
        """
        WooCommerce SKU'dan Product tablosunda otomatik eşleştirme yap
        
        SKU Format: PRODUCT_MAIN_ID-SIZE COLOR
        Örnek: 259-37 Siyah, 009-41 Beyaz
        
        Args:
            woo_product_id: WooCommerce ürün ID
            sku: WooCommerce SKU
            
        Returns:
            Eşleşen Product nesnesi veya None
        """
        if not sku or not sku.strip():
            return None
        
        try:
            # SKU'yu parçala: "259-37 Siyah" -> ["259-37", "Siyah"]
            parts = sku.strip().split(' ', 1)
            if len(parts) < 2:
                logger.warning(f"[AUTO_MAP] SKU formatı hatalı: {sku}")
                return None
            
            size_part = parts[0]  # "259-37"
            color = parts[1].strip()  # "Siyah"
            
            # Size part'ı parçala: "259-37" -> product_main_id=259, size=37
            if '-' not in size_part:
                logger.warning(f"[AUTO_MAP] SKU size formatı hatalı: {size_part}")
                return None
            
            product_main_id_str, size = size_part.split('-', 1)
            product_main_id = product_main_id_str.strip()
            size = size.strip()
            
            logger.info(f"[AUTO_MAP] Arama: product_main_id={product_main_id}, size={size}, color={color}")
            
            # Product tablosunda ara
            product = Product.query.filter_by(
                product_main_id=product_main_id,
                size=size,
                color=color
            ).first()
            
            if product:
                # Eşleşme bulundu, woo_product_id ve woo_barcode güncelle
                if not product.woo_product_id:
                    product.woo_product_id = str(woo_product_id)
                    product.woo_barcode = product.barcode
                    db.session.commit()
                    logger.info(f"[AUTO_MAP] ✅ Otomatik eşleştirme: WooID={woo_product_id} → Barcode={product.barcode}")
                else:
                    logger.info(f"[AUTO_MAP] ✓ Zaten eşleşmiş: WooID={product.woo_product_id} → Barcode={product.barcode}")
                
                return product
            else:
                logger.warning(f"[AUTO_MAP] ❌ Product bulunamadı: product_main_id={product_main_id}, size={size}, color={color}")
                return None
                
        except Exception as e:
            logger.error(f"[AUTO_MAP] Hata: {e}", exc_info=True)
            return None
