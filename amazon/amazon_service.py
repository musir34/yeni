"""
Amazon SP-API Servis Modülü
Amazon Seller Partner API ile entegrasyon için servis fonksiyonları

Gerekli paket: pip install python-amazon-sp-api
"""

import os
import json
from datetime import datetime, timedelta
import logging
from .amazon_config import AmazonConfig

logger = logging.getLogger(__name__)

# Cache dosyaları
IMAGE_CACHE_FILE = os.path.join(os.path.dirname(__file__), 'image_cache.json')
PRODUCTS_CACHE_FILE = os.path.join(os.path.dirname(__file__), 'products_cache.json')


class AmazonService:
    """Amazon SP-API ile iletişim için servis sınıfı"""
    
    def __init__(self):
        self.config = AmazonConfig
        self._orders_api = None
        self._catalog_api = None
        self._inventory_api = None
        self._reports_api = None
        self._marketplace = None
        self._image_cache = None
        
    def _load_image_cache(self):
        """Görsel cache'i yükle"""
        if self._image_cache is None:
            try:
                if os.path.exists(IMAGE_CACHE_FILE):
                    with open(IMAGE_CACHE_FILE, 'r') as f:
                        self._image_cache = json.load(f)
                else:
                    self._image_cache = {}
            except Exception as e:
                logger.warning(f"Görsel cache yüklenemedi: {e}")
                self._image_cache = {}
        return self._image_cache
    
    def _save_image_cache(self):
        """Görsel cache'i kaydet"""
        try:
            with open(IMAGE_CACHE_FILE, 'w') as f:
                json.dump(self._image_cache or {}, f)
        except Exception as e:
            logger.warning(f"Görsel cache kaydedilemedi: {e}")
        
    def _get_credentials(self):
        """SP-API credentials döndür (AWS'siz - Grantless mode)"""
        return {
            'lwa_app_id': self.config.LWA_CLIENT_ID,
            'lwa_client_secret': self.config.LWA_CLIENT_SECRET,
            'refresh_token': self.config.REFRESH_TOKEN,
        }
    
    def _get_marketplace(self):
        """Marketplace enum objesi döndür"""
        if self._marketplace is None:
            try:
                from sp_api.base import Marketplaces
                # Türkiye marketplace'i için
                marketplace_map = {
                    'A33AVAJ2PDY3EV': Marketplaces.TR,
                    'A1PA6795UKMFR9': Marketplaces.DE,
                    'A1F83G8C2ARO7P': Marketplaces.UK,
                    'A13V1IB3VIYBER': Marketplaces.FR,
                    'APJ6JRA9NG5V4': Marketplaces.IT,
                    'A1RKKUPIHCS9HS': Marketplaces.ES,
                }
                self._marketplace = marketplace_map.get(self.config.MARKETPLACE_ID, Marketplaces.TR)
            except Exception as e:
                logger.error(f"Marketplace alınamadı: {str(e)}")
                return None
        return self._marketplace
    
    def _init_orders_api(self):
        """Orders API'yi başlat"""
        if self._orders_api is None:
            try:
                from sp_api.api import Orders
                marketplace = self._get_marketplace()
                if not marketplace:
                    return None
                self._orders_api = Orders(
                    credentials=self._get_credentials(),
                    marketplace=marketplace
                )
            except ImportError:
                logger.error("python-amazon-sp-api paketi yüklü değil! Lütfen: pip install python-amazon-sp-api")
                return None
            except Exception as e:
                logger.error(f"Orders API başlatılamadı: {str(e)}")
                return None
        return self._orders_api
    
    def _init_catalog_api(self):
        """Catalog API'yi başlat"""
        if self._catalog_api is None:
            try:
                from sp_api.api import CatalogItems
                marketplace = self._get_marketplace()
                if not marketplace:
                    return None
                self._catalog_api = CatalogItems(
                    credentials=self._get_credentials(),
                    marketplace=marketplace
                )
            except ImportError:
                logger.error("python-amazon-sp-api paketi yüklü değil!")
                return None
            except Exception as e:
                logger.error(f"Catalog API başlatılamadı: {str(e)}")
                return None
        return self._catalog_api
    
    def _init_inventory_api(self):
        """Inventory API'yi başlat"""
        if self._inventory_api is None:
            try:
                from sp_api.api import Inventories
                marketplace = self._get_marketplace()
                if not marketplace:
                    return None
                self._inventory_api = Inventories(
                    credentials=self._get_credentials(),
                    marketplace=marketplace
                )
            except ImportError:
                logger.error("python-amazon-sp-api paketi yüklü değil!")
                return None
            except Exception as e:
                logger.error(f"Inventory API başlatılamadı: {str(e)}")
                return None
        return self._inventory_api
    
    def _init_reports_api(self):
        """Reports API'yi başlat"""
        if self._reports_api is None:
            try:
                from sp_api.api import Reports
                marketplace = self._get_marketplace()
                if not marketplace:
                    return None
                self._reports_api = Reports(
                    credentials=self._get_credentials(),
                    marketplace=marketplace
                )
            except ImportError:
                logger.error("python-amazon-sp-api paketi yüklü değil!")
                return None
            except Exception as e:
                logger.error(f"Reports API başlatılamadı: {str(e)}")
                return None
        return self._reports_api
    
    def _init_listings_api(self):
        """Listings API'yi başlat"""
        try:
            from sp_api.api import ListingsItems
            marketplace = self._get_marketplace()
            if not marketplace:
                return None
            return ListingsItems(
                credentials=self._get_credentials(),
                marketplace=marketplace
            )
        except ImportError:
            logger.error("python-amazon-sp-api paketi yüklü değil!")
            return None
        except Exception as e:
            logger.error(f"Listings API başlatılamadı: {str(e)}")
            return None
        
    # ═══════════════════════════════════════════════════════════════════════════
    # SİPARİŞ İŞLEMLERİ
    # ═══════════════════════════════════════════════════════════════════════════
        
    def get_orders(self, days_back=7, status=None):
        """
        Amazon siparişlerini getir
        
        Args:
            days_back (int): Kaç gün öncesine kadar sipariş çekileceği
            status (str): Sipariş durumu filtresi
            
        Returns:
            dict: Sipariş listesi ve toplam sayı
        """
        try:
            orders_api = self._init_orders_api()
            if not orders_api:
                return {'orders': [], 'total': 0, 'error': 'API başlatılamadı'}
            
            # Tarih aralığı
            created_after = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
            
            # Parametreler
            params = {
                'CreatedAfter': created_after,
                'MarketplaceIds': self.config.get_marketplace_ids()
            }
            
            if status:
                params['OrderStatuses'] = [status]
            
            # API çağrısı
            response = orders_api.get_orders(**params)
            
            orders = response.payload.get('Orders', [])
            
            logger.info(f"Amazon'dan {len(orders)} sipariş çekildi")
            
            return {
                'orders': orders,
                'total': len(orders),
                'next_token': response.payload.get('NextToken')
            }
            
        except Exception as e:
            logger.error(f"Amazon siparişleri çekilirken hata: {str(e)}")
            return {'orders': [], 'total': 0, 'error': str(e)}
    
    def get_order_detail(self, order_id):
        """
        Sipariş detayını getir
        
        Args:
            order_id (str): Amazon sipariş ID'si
            
        Returns:
            dict: Sipariş detayı
        """
        try:
            orders_api = self._init_orders_api()
            if not orders_api:
                return None
            
            # Sipariş bilgisi
            order_response = orders_api.get_order(order_id)
            order = order_response.payload
            
            # Sipariş ürünleri
            items_response = orders_api.get_order_items(order_id)
            items = items_response.payload.get('OrderItems', [])
            
            order['OrderItems'] = items
            
            return order
            
        except Exception as e:
            logger.error(f"Sipariş detayı çekilirken hata: {str(e)}")
            return None
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ÜRÜN İŞLEMLERİ
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_products(self, page=1, search=None):
        """
        Amazon ürünlerini getir - Reports API kullanarak
        
        Args:
            page (int): Sayfa numarası
            search (str): Arama terimi
            
        Returns:
            dict: Ürün listesi ve toplam
        """
        try:
            reports_api = self._init_reports_api()
            if not reports_api:
                return {'products': [], 'total': 0, 'error': 'Reports API başlatılamadı'}
            
            logger.info("Amazon ürün listesi raporu isteniyor...")
            
            # GET_MERCHANT_LISTINGS_ALL_DATA raporu oluştur
            report_response = reports_api.create_report(
                reportType='GET_MERCHANT_LISTINGS_ALL_DATA',
                marketplaceIds=self.config.get_marketplace_ids()
            )
            
            report_id = report_response.payload.get('reportId')
            logger.info(f"Rapor oluşturuldu, ID: {report_id}")
            
            # Rapor hazır olana kadar bekle (max 60 saniye)
            import time
            max_attempts = 12
            for attempt in range(max_attempts):
                time.sleep(5)  # 5 saniye bekle
                
                report_status = reports_api.get_report(report_id)
                status = report_status.payload.get('processingStatus')
                logger.info(f"Rapor durumu: {status}")
                
                if status == 'DONE':
                    document_id = report_status.payload.get('reportDocumentId')
                    break
                elif status in ['CANCELLED', 'FATAL']:
                    return {'products': [], 'total': 0, 'error': f'Rapor başarısız: {status}'}
            else:
                return {'products': [], 'total': 0, 'error': 'Rapor zaman aşımına uğradı'}
            
            # Rapor içeriğini al
            document_response = reports_api.get_report_document(document_id)
            
            # Raporu indir ve parse et
            products = self._parse_merchant_listings_report(document_response)
            
            # Arama filtresi
            if search:
                search_lower = search.lower()
                products = [p for p in products if 
                    search_lower in p.get('title', '').lower() or
                    search_lower in p.get('sku', '').lower() or
                    search_lower in p.get('asin', '').lower()
                ]
            
            # Sayfalama
            per_page = 20
            start = (page - 1) * per_page
            end = start + per_page
            paginated = products[start:end]
            
            # Görsel URL'lerini Catalog API'den çek (sadece bu sayfadaki ürünler için)
            paginated = self._fetch_product_images(paginated)
            
            return {
                'products': paginated,
                'total': len(products),
                'page': page,
                'per_page': per_page,
                'total_pages': (len(products) + per_page - 1) // per_page
            }
            
        except Exception as e:
            logger.error(f"Amazon ürünleri çekilirken hata: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {'products': [], 'total': 0, 'error': str(e)}
    
    def _parse_merchant_listings_report(self, document_response):
        """
        Merchant Listings raporunu parse et
        
        Args:
            document_response: Reports API document response
            
        Returns:
            list: Ürün listesi
        """
        try:
            import requests
            import csv
            import io
            
            # Document URL'den indir
            url = document_response.payload.get('url')
            compression = document_response.payload.get('compressionAlgorithm')
            
            response = requests.get(url)
            content = response.content
            
            # Eğer sıkıştırılmışsa aç
            if compression == 'GZIP':
                import gzip
                content = gzip.decompress(content)
            
            # UTF-8-BOM karakterini temizle ve decode et
            text = content.decode('utf-8-sig')  # utf-8-sig BOM'u otomatik kaldırır
            
            # Tab-separated olarak parse et
            reader = csv.DictReader(io.StringIO(text), delimiter='\t')
            
            products = []
            for row in reader:
                # "-" değerlerini temizle
                def clean(val):
                    if val and val.strip() != '-':
                        return val.strip()
                    return ''
                
                product = {
                    'sku': clean(row.get('seller-sku', '')),
                    'asin': clean(row.get('asin1', '')),
                    'title': clean(row.get('item-name', '')),
                    'description': clean(row.get('item-description', ''))[:200],
                    'price': clean(row.get('price', '0')),
                    'quantity': clean(row.get('quantity', '0')),
                    'status': clean(row.get('status', 'Active')),
                    'fulfillment_channel': clean(row.get('fulfillment-channel', 'DEFAULT')),
                    'image_url': clean(row.get('image-url', '')),
                    'product_id': clean(row.get('product-id', '')),
                    'product_id_type': clean(row.get('product-id-type', '')),
                    'open_date': clean(row.get('open-date', '')),
                    'listing_id': clean(row.get('listing-id', '')),
                    'condition': clean(row.get('item-condition', '')),
                    'pending_quantity': clean(row.get('pending-quantity', '0')),
                }
                products.append(product)
            
            logger.info(f"Toplam {len(products)} ürün parse edildi")
            return products
            
        except Exception as e:
            logger.error(f"Rapor parse edilirken hata: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def _fetch_product_images(self, products):
        """
        Catalog API kullanarak ürün görsellerini çek
        Rate limiting ile API quota aşımını önle
        Cache kullanarak tekrar istek atmayı önle
        
        Args:
            products (list): Ürün listesi
            
        Returns:
            list: Görsel URL'leri eklenmiş ürün listesi
        """
        import time
        
        # Cache'i yükle
        cache = self._load_image_cache()
        cache_updated = False
        
        # Önce cache'den görselleri ekle
        for product in products:
            asin = product.get('asin')
            if asin and asin in cache:
                product['image_url'] = cache[asin]
        
        # Cache'de olmayan ürünler için API'dan çek
        uncached_products = [p for p in products if not p.get('image_url') and p.get('asin')]
        
        if not uncached_products:
            return products
        
        try:
            catalog_api = self._init_catalog_api()
            if not catalog_api:
                logger.warning("Catalog API başlatılamadı, görseller çekilemedi")
                return products
            
            marketplace_id = self.config.MARKETPLACE_ID
            
            for idx, product in enumerate(uncached_products):
                asin = product.get('asin')
                
                try:
                    # Rate limiting - her 2 üründe bir 0.5 saniye bekle
                    if idx > 0 and idx % 2 == 0:
                        time.sleep(0.5)
                    
                    # Catalog Items API 2022-04-01 versiyonu
                    response = catalog_api.get_catalog_item(
                        asin=asin,
                        marketplaceIds=[marketplace_id],
                        includedData=['images', 'summaries']
                    )
                    
                    image_url = None
                    
                    if response and response.payload:
                        # Görselleri al
                        images = response.payload.get('images', [])
                        if images:
                            for img_set in images:
                                img_list = img_set.get('images', [])
                                if img_list:
                                    for img in img_list:
                                        if img.get('variant') == 'MAIN':
                                            image_url = img.get('link')
                                            break
                                    if not image_url and img_list:
                                        image_url = img_list[0].get('link')
                                    if image_url:
                                        break
                        
                        # summaries'den dene
                        if not image_url:
                            summaries = response.payload.get('summaries', [])
                            for summary in summaries:
                                main_image = summary.get('mainImage', {})
                                if main_image.get('link'):
                                    image_url = main_image.get('link')
                                    break
                    
                    if image_url:
                        product['image_url'] = image_url
                        cache[asin] = image_url
                        cache_updated = True
                                    
                except Exception as e:
                    error_msg = str(e)
                    if 'QuotaExceeded' in error_msg:
                        logger.warning(f"API quota aşıldı, kalan ürünler için görsel çekilemiyor")
                        break
                    logger.debug(f"ASIN {asin} için görsel alınamadı: {error_msg}")
                    continue
            
            # Cache'i kaydet
            if cache_updated:
                self._image_cache = cache
                self._save_image_cache()
            
            return products
            
        except Exception as e:
            logger.error(f"Görseller çekilirken hata: {str(e)}")
            return products
    
    def get_products_quick(self):
        """
        Hızlı ürün listesi - Önceden oluşturulmuş rapordan veya cache'den
        İlk seferde rapor oluşturur, sonrasında cache kullanır
        
        Returns:
            dict: Ürün listesi
        """
        try:
            # Inventory Summary'den hızlı liste al
            inventory_api = self._init_inventory_api()
            if not inventory_api:
                return {'products': [], 'total': 0, 'error': 'Inventory API başlatılamadı'}
            
            response = inventory_api.get_inventory_summary_marketplace(
                details=True,
                marketplaceIds=self.config.get_marketplace_ids()
            )
            
            items = response.payload.get('inventorySummaries', [])
            
            products = []
            for item in items:
                products.append({
                    'sku': item.get('sellerSku', ''),
                    'asin': item.get('asin', ''),
                    'title': item.get('productName', 'İsim yok'),
                    'quantity': item.get('totalQuantity', 0),
                    'fnsku': item.get('fnSku', ''),
                    'condition': item.get('condition', ''),
                })
            
            return {
                'products': products,
                'total': len(products)
            }
            
        except Exception as e:
            logger.error(f"Hızlı ürün listesi alınamadı: {str(e)}")
            return {'products': [], 'total': 0, 'error': str(e)}
    
    def get_all_products_cached(self):
        """
        Tüm Amazon ürünlerini cache'den getir
        Cache yoksa boş liste döner
        
        Returns:
            list: Ürün listesi
        """
        try:
            if os.path.exists(PRODUCTS_CACHE_FILE):
                with open(PRODUCTS_CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('products', [])
            return []
        except Exception as e:
            logger.error(f"Ürün cache okunamadı: {str(e)}")
            return []
    
    def fetch_and_cache_all_products(self):
        """
        Tüm Amazon ürünlerini API'dan çek ve cache'le
        
        Returns:
            dict: Başarı durumu ve ürün sayısı
        """
        try:
            logger.info("Tüm Amazon ürünleri çekiliyor...")
            
            reports_api = self._init_reports_api()
            if not reports_api:
                return {'success': False, 'error': 'Reports API başlatılamadı'}
            
            # Yeni rapor oluştur
            report_response = reports_api.create_report(
                reportType='GET_MERCHANT_LISTINGS_ALL_DATA',
                marketplaceIds=self.config.get_marketplace_ids()
            )
            
            report_id = report_response.payload.get('reportId')
            logger.info(f"Rapor oluşturuldu, ID: {report_id}")
            
            # Rapor hazır olana kadar bekle
            import time
            max_attempts = 24  # 2 dakika
            for attempt in range(max_attempts):
                time.sleep(5)
                
                report_status = reports_api.get_report(report_id)
                status = report_status.payload.get('processingStatus')
                logger.info(f"Rapor durumu: {status}")
                
                if status == 'DONE':
                    document_id = report_status.payload.get('reportDocumentId')
                    break
                elif status in ['CANCELLED', 'FATAL']:
                    return {'success': False, 'error': f'Rapor başarısız: {status}'}
            else:
                return {'success': False, 'error': 'Rapor zaman aşımına uğradı'}
            
            # Rapor içeriğini al
            document_response = reports_api.get_report_document(document_id)
            products = self._parse_merchant_listings_report(document_response)
            
            # Cache'e kaydet
            cache_data = {
                'products': products,
                'total': len(products),
                'cached_at': datetime.now().isoformat()
            }
            
            with open(PRODUCTS_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Toplam {len(products)} ürün cache'e kaydedildi")
            
            return {
                'success': True,
                'total': len(products),
                'cached_at': cache_data['cached_at']
            }
            
        except Exception as e:
            logger.error(f"Ürünler cache'lenirken hata: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {'success': False, 'error': str(e)}
    
    # ═══════════════════════════════════════════════════════════════════════════
    # STOK İŞLEMLERİ
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_inventory(self):
        """
        Stok durumunu getir
        
        Returns:
            dict: Stok listesi
        """
        try:
            inventory_api = self._init_inventory_api()
            if not inventory_api:
                return {'items': [], 'total': 0, 'error': 'API başlatılamadı'}
            
            # FBA stok durumu
            response = inventory_api.get_inventory_summary_marketplace(
                details=True,
                marketplaceIds=self.config.get_marketplace_ids()
            )
            
            items = response.payload.get('inventorySummaries', [])
            
            return {
                'items': items,
                'total': len(items)
            }
            
        except Exception as e:
            logger.error(f"Stok bilgisi çekilirken hata: {str(e)}")
            return {'items': [], 'total': 0, 'error': str(e)}
    
    def update_inventory(self, sku, quantity):
        """
        Amazon stok güncelleme (FBM - Seller Fulfilled)
        
        Args:
            sku (str): Ürün SKU'su
            quantity (int): Yeni stok miktarı
            
        Returns:
            bool: Başarı durumu
        """
        try:
            # Listings API veya Feeds API ile stok güncelleme
            # NOT: Bu işlem için Feeds API kullanılmalı
            
            logger.info(f"Amazon stok güncelleniyor: {sku} -> {quantity}")
            
            # TODO: Feeds API ile implement et
            return True
            
        except Exception as e:
            logger.error(f"Amazon stok güncellenirken hata: {str(e)}")
            return False
    
    def bulk_update_inventory(self, items):
        """
        Amazon toplu stok güncelleme (Listings Items API ile - Rate Limited)
        
        Args:
            items (list): [{'sku': 'SKU123', 'quantity': 10}, ...]
            
        Returns:
            dict: İşlem sonucu
        """
        try:
            from sp_api.api import ListingsItems
            import time
            
            if not items:
                return {'success': False, 'error': 'Güncellenecek ürün yok'}
            
            marketplace = self._get_marketplace()
            if not marketplace:
                return {'success': False, 'error': 'Marketplace başlatılamadı'}
            
            seller_id = self.config.SELLER_ID
            marketplace_ids = self.config.get_marketplace_ids()
            credentials = self._get_credentials()
            
            # Rate limit: saniyede max 5 istek, güvenli mod için 3 istek/sn
            REQUEST_INTERVAL = 0.35  # 350ms = ~3 istek/saniye
            MAX_RETRIES = 3
            BACKOFF_BASE = 2  # Exponential backoff
            
            logger.info(f"[AMAZON] 📦 {len(items)} ürün için stok güncelleniyor (Rate Limited - 3/sn)...")
            
            listings = ListingsItems(
                credentials=credentials,
                marketplace=marketplace
            )
            
            success_count = 0
            error_count = 0
            skipped_count = 0
            errors = []
            
            start_time = time.time()
            
            for idx, item in enumerate(items):
                sku = item.get('sku', '')
                quantity = max(0, int(item.get('quantity', 0)))
                
                if not sku:
                    skipped_count += 1
                    continue
                
                # Retry mekanizması
                success = False
                for retry in range(MAX_RETRIES):
                    try:
                        patches = [
                            {
                                'op': 'replace',
                                'path': '/attributes/fulfillment_availability',
                                'value': [
                                    {
                                        'fulfillment_channel_code': 'DEFAULT',
                                        'quantity': quantity
                                    }
                                ]
                            }
                        ]
                        
                        response = listings.patch_listings_item(
                            sellerId=seller_id,
                            sku=sku,
                            marketplaceIds=marketplace_ids,
                            body={
                                'productType': 'SHOES',
                                'patches': patches
                            }
                        )
                        
                        if hasattr(response, 'payload') and response.payload.get('status') == 'ACCEPTED':
                            success_count += 1
                            success = True
                            break
                        else:
                            # Beklenmeyen response, retry etme
                            error_count += 1
                            if len(errors) < 10:
                                errors.append(f"{sku}: Beklenmeyen response")
                            break
                            
                    except Exception as e:
                        error_msg = str(e)
                        
                        # QuotaExceeded hatası - backoff ile bekle ve tekrar dene
                        if 'QuotaExceeded' in error_msg:
                            wait_time = BACKOFF_BASE ** (retry + 1)
                            logger.warning(f"[AMAZON] ⏳ Rate limit, {wait_time}sn bekleniyor... (retry {retry+1}/{MAX_RETRIES})")
                            time.sleep(wait_time)
                            continue
                        else:
                            # Diğer hatalar
                            error_count += 1
                            if len(errors) < 10:
                                errors.append(f"{sku}: {error_msg[:50]}")
                            break
                
                if not success and 'QuotaExceeded' in str(errors[-1] if errors else ''):
                    error_count += 1
                
                # Rate limiting bekleme
                time.sleep(REQUEST_INTERVAL)
                
                # Her 50 üründe bir log
                if (idx + 1) % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = (idx + 1) / elapsed if elapsed > 0 else 0
                    remaining = (len(items) - idx - 1) / rate if rate > 0 else 0
                    logger.info(f"[AMAZON] 📊 {idx + 1}/{len(items)} (✅{success_count} ❌{error_count}) - {rate:.1f}/sn - Kalan: {remaining:.0f}sn")
            
            elapsed = time.time() - start_time
            logger.info(f"[AMAZON] ✅ Tamamlandı: {success_count} başarılı, {error_count} hatalı ({elapsed:.1f} saniye)")
            
            return {
                'success': True,
                'items_count': len(items),
                'success_count': success_count,
                'error_count': error_count,
                'skipped_count': skipped_count,
                'errors': errors,
                'elapsed_seconds': round(elapsed, 1),
                'message': f'{success_count}/{len(items)} ürün stoku güncellendi ({elapsed:.0f} saniye)'
            }
            
        except ImportError as e:
            logger.error(f"[AMAZON] Import hatası: {e}")
            return {'success': False, 'error': 'Listings API modülü yüklü değil'}
        except Exception as e:
            logger.error(f"[AMAZON] ❌ Toplu stok güncelleme hatası: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _create_inventory_feed_xml(self, items):
        """
        Amazon Inventory Feed XML oluştur
        
        Args:
            items (list): [{'sku': 'SKU123', 'quantity': 10}, ...]
            
        Returns:
            str: XML içeriği
        """
        xml_header = '''<?xml version="1.0" encoding="UTF-8"?>
<AmazonEnvelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="amzn-envelope.xsd">
    <Header>
        <DocumentVersion>1.01</DocumentVersion>
        <MerchantIdentifier>MERCHANT_ID</MerchantIdentifier>
    </Header>
    <MessageType>Inventory</MessageType>
'''
        
        xml_messages = ''
        for idx, item in enumerate(items, 1):
            sku = item.get('sku', '')
            quantity = max(0, int(item.get('quantity', 0)))
            
            xml_messages += f'''    <Message>
        <MessageID>{idx}</MessageID>
        <OperationType>Update</OperationType>
        <Inventory>
            <SKU>{sku}</SKU>
            <Quantity>{quantity}</Quantity>
            <FulfillmentLatency>3</FulfillmentLatency>
        </Inventory>
    </Message>
'''
        
        xml_footer = '</AmazonEnvelope>'
        
        return xml_header + xml_messages + xml_footer
    
    def push_central_stock(self):
        """
        CentralStock'tan Amazon'a stok gönder
        Trendyol ile aynı mantıkta çalışır
        
        Returns:
            dict: İşlem sonucu
        """
        try:
            from models import CentralStock, OrderCreated, Product
            import json as json_module
            
            logger.info("=" * 80)
            logger.info("[AMAZON-PUSH] 🚀 Amazon stok gönderme işlemi başlatıldı")
            logger.info(f"[AMAZON-PUSH] ⏰ Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            def _parse(raw):
                try:
                    if not raw: return []
                    d = json_module.loads(raw) if isinstance(raw, str) else raw
                    return d if isinstance(d, list) else [d]
                except:
                    return []

            def _i(x, d=0):
                try:
                    return int(str(x).strip())
                except:
                    return d
            
            # 1. Amazon eşleşmeli ürünleri bul
            logger.info("[AMAZON-PUSH] 📦 Step 1: Amazon eşleşmeli ürünler sorgulanıyor...")
            amazon_products = Product.query.filter(
                Product.amazon_sku.isnot(None),
                Product.amazon_sku != ''
            ).all()
            
            if not amazon_products:
                logger.warning("[AMAZON-PUSH] ⚠️ Amazon eşleşmeli ürün bulunamadı!")
                return {'success': False, 'error': 'Amazon eşleşmeli ürün yok'}
            
            logger.info(f"[AMAZON-PUSH] 📊 {len(amazon_products)} adet Amazon eşleşmeli ürün bulundu")
            
            # Barkod -> SKU haritası oluştur
            barcode_to_sku = {}
            for p in amazon_products:
                if p.barcode and p.amazon_sku:
                    barcode_to_sku[p.barcode.strip()] = p.amazon_sku.strip()
            
            # 2. CentralStock verilerini al
            logger.info("[AMAZON-PUSH] 📦 Step 2: CentralStock verisi okunuyor...")
            central_stocks = CentralStock.query.all()
            central_map = {cs.barcode.strip(): _i(cs.qty, 0) for cs in central_stocks}
            logger.info(f"[AMAZON-PUSH] 📊 CentralStock'ta {len(central_stocks)} kayıt")
            
            # 3. Created siparişlerden rezerv hesapla
            logger.info("[AMAZON-PUSH] 🔒 Step 3: Created siparişler rezerv hesaplanıyor...")
            reserved = {}
            created_orders = OrderCreated.query.with_entities(OrderCreated.details).all()
            
            for (details_str,) in created_orders:
                for it in _parse(details_str):
                    bc = (it.get("barcode") or "").strip()
                    q = _i(it.get("quantity"), 0)
                    if bc and q > 0:
                        reserved[bc] = reserved.get(bc, 0) + q
            
            logger.info(f"[AMAZON-PUSH] 🔒 {len(reserved)} farklı barkod için rezervasyon var")
            
            # 4. Stok hesapla ve listeyi oluştur
            logger.info("[AMAZON-PUSH] 🧮 Step 4: Kullanılabilir stok hesaplanıyor...")
            items = []
            zero_count = 0
            
            for barcode, sku in barcode_to_sku.items():
                central_qty = central_map.get(barcode, 0)
                reserved_qty = reserved.get(barcode, 0)
                available = max(0, central_qty - reserved_qty)
                
                if available == 0:
                    zero_count += 1
                
                items.append({
                    'sku': sku,
                    'quantity': available,
                    'barcode': barcode  # debug için
                })
            
            logger.info(f"[AMAZON-PUSH] 📊 Stok İstatistikleri:")
            logger.info(f"[AMAZON-PUSH]   • Toplam ürün: {len(items)}")
            logger.info(f"[AMAZON-PUSH]   • Sıfır stoklu: {zero_count}")
            logger.info(f"[AMAZON-PUSH]   • Pozitif stoklu: {len(items) - zero_count}")
            
            # Örnek 5 ürün göster
            positive_items = [it for it in items if it['quantity'] > 0][:5]
            if positive_items:
                logger.info("[AMAZON-PUSH] 📋 Örnek ürünler:")
                for idx, it in enumerate(positive_items, 1):
                    logger.info(f"[AMAZON-PUSH]   {idx}. SKU: {it['sku']}, Miktar: {it['quantity']}")
            
            if not items:
                logger.warning("[AMAZON-PUSH] ⚠️ Gönderilecek ürün yok!")
                return {'success': False, 'error': 'Gönderilecek ürün yok'}
            
            # 5. Feeds API ile gönder
            logger.info("[AMAZON-PUSH] 📤 Step 5: Feeds API ile stok gönderiliyor...")
            result = self.bulk_update_inventory(items)
            
            if result.get('success'):
                logger.info(f"[AMAZON-PUSH] ✅ Stok feed'i başarıyla gönderildi!")
                logger.info(f"[AMAZON-PUSH] 📋 Feed ID: {result.get('feed_id')}")
            else:
                logger.error(f"[AMAZON-PUSH] ❌ Stok gönderimi başarısız: {result.get('error')}")
            
            logger.info("[AMAZON-PUSH] 🏁 Amazon stok gönderme işlemi sona erdi")
            logger.info("=" * 80)
            
            return result
            
        except Exception as e:
            logger.error(f"[AMAZON-PUSH] ❌ KRITIK HATA: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    # ═══════════════════════════════════════════════════════════════════════════
    # RAPORLAR
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_sales_report(self, start_date=None, end_date=None):
        """
        Satış raporu getir
        
        Args:
            start_date: Başlangıç tarihi
            end_date: Bitiş tarihi
            
        Returns:
            dict: Satış raporu
        """
        try:
            # Reports API kullanılacak
            return {
                'total_sales': 0,
                'order_count': 0,
                'items_sold': 0,
                'period': {
                    'start': start_date,
                    'end': end_date
                }
            }
        except Exception as e:
            logger.error(f"Satış raporu çekilirken hata: {str(e)}")
            return {'error': str(e)}
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SENKRONIZASYON
    # ═══════════════════════════════════════════════════════════════════════════
    
    def sync_orders(self):
        """Siparişleri veritabanına senkronize et"""
        try:
            orders_data = self.get_orders(days_back=30)
            orders = orders_data.get('orders', [])
            
            # TODO: Veritabanına kaydet
            
            return {
                'success': True,
                'synced': len(orders),
                'message': f'{len(orders)} sipariş senkronize edildi'
            }
        except Exception as e:
            logger.error(f"Sipariş senkronizasyonu hatası: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def sync_inventory(self):
        """Stok senkronizasyonu"""
        try:
            # Merkezi stoktan Amazon'a senkronizasyon
            return {
                'success': True,
                'message': 'Stok senkronizasyonu tamamlandı'
            }
        except Exception as e:
            logger.error(f"Stok senkronizasyonu hatası: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    # ═══════════════════════════════════════════════════════════════════════════
    # BAĞLANTI TESTİ
    # ═══════════════════════════════════════════════════════════════════════════
    
    def test_connection(self):
        """API bağlantı testi"""
        try:
            orders_api = self._init_orders_api()
            if not orders_api:
                return {
                    'success': False,
                    'message': 'API başlatılamadı. Credentials kontrol edin.'
                }
            
            # Basit bir test çağrısı
            response = orders_api.get_orders(
                CreatedAfter=(datetime.utcnow() - timedelta(days=1)).isoformat(),
                MarketplaceIds=self.config.get_marketplace_ids()
            )
            
            return {
                'success': True,
                'message': 'Amazon API bağlantısı başarılı!',
                'marketplace': self.config.MARKETPLACE_ID
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Bağlantı hatası: {str(e)}'
            }


# Global servis instance
amazon_service = AmazonService()
