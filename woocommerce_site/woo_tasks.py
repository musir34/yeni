"""
WooCommerce Celery Tasks - Otomatik sipariş senkronizasyonu
"""
from celery_app import celery
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@celery.task(name='woocommerce.sync_orders')
def sync_woo_orders_task():
    """
    WooCommerce siparişlerini otomatik olarak çeker ve veritabanına kaydeder.
    Trendyol gibi periyodik olarak çalışır.
    """
    try:
        from woocommerce_site.woo_service import WooCommerceService
        from woocommerce_site.woo_config import WooConfig
        
        # API ayarları kontrolü
        if not WooConfig.is_configured():
            logger.warning("WooCommerce API ayarları yapılmamış, senkronizasyon atlandı")
            return {
                'success': False,
                'message': 'API ayarları eksik'
            }
        
        woo_service = WooCommerceService()
        
        # Son 7 günün siparişlerini çek
        result = woo_service.sync_orders_to_db(days=7, status=None)
        
        logger.info(f"WooCommerce senkronizasyonu tamamlandı: {result['total_saved']} sipariş kaydedildi")
        
        return {
            'success': True,
            'total_saved': result['total_saved'],
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"WooCommerce senkronizasyon hatası: {str(e)}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }


@celery.task(name='woocommerce.sync_new_orders')
def sync_new_orders_task():
    """
    Sadece yeni siparişleri çeker (processing, pending, on-hold)
    Daha hızlı çalışır, her 5 dakikada bir çalıştırılabilir
    """
    try:
        from woocommerce_site.woo_service import WooCommerceService
        from woocommerce_site.woo_config import WooConfig
        
        if not WooConfig.is_configured():
            logger.warning("WooCommerce API ayarları yapılmamış")
            return {'success': False}
        
        woo_service = WooCommerceService()
        
        # Sadece aktif durumdaki siparişler
        active_statuses = ['pending', 'processing', 'on-hold']
        total_saved = 0
        
        for status in active_statuses:
            result = woo_service.sync_orders_to_db(days=3, status=status)
            total_saved += result.get('total_saved', 0)
        
        logger.info(f"WooCommerce yeni sipariş senkronizasyonu: {total_saved} sipariş")
        
        return {
            'success': True,
            'total_saved': total_saved,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Yeni sipariş senkronizasyon hatası: {str(e)}", exc_info=True)
        return {'success': False, 'error': str(e)}
