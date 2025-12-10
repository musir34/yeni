"""
Idefix Satıcı Paneli Servisi
Satıcı: Güllü shoes
Satıcı ID: 10594
"""

import os
import base64
import requests
from typing import Optional, Dict, Any, List
from logger_config import app_logger

class IdefixService:
    """Idefix API entegrasyonu için servis sınıfı"""
    
    # Canlı ortam API URL'leri
    PIM_BASE_URL = "https://merchantapi.idefix.com/pim"
    OMS_BASE_URL = "https://merchantapi.idefix.com/oms"
    
    def __init__(self):
        self.seller_id = os.getenv("IDEFIX_SELLER_ID", "10594")
        self.seller_name = os.getenv("IDEFIX_SELLER_NAME", "Güllü shoes")
        self.token = os.getenv("IDEFIX_TOKEN")
        self.secret = os.getenv("IDEFIX_SECRET")
        self._vendor_token = None
        app_logger.info(f"[IDEFIX] Service başlatıldı - Seller ID: {self.seller_id}, Seller Name: {self.seller_name}")
        app_logger.debug(f"[IDEFIX] Token mevcut: {bool(self.token)}, Secret mevcut: {bool(self.secret)}")
        
    def _get_vendor_token(self) -> str:
        """API Key ve Secret'tan vendor token oluşturur (base64 encode)"""
        if self._vendor_token is None:
            credentials = f"{self.token}:{self.secret}"
            self._vendor_token = base64.b64encode(credentials.encode()).decode()
            app_logger.debug(f"[IDEFIX] Vendor token oluşturuldu")
        return self._vendor_token
        
    def _get_headers(self) -> Dict[str, str]:
        """API istekleri için gerekli header'ları döndürür"""
        return {
            "X-API-KEY": self._get_vendor_token(),
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def get_products(self, page: int = 1, limit: int = 50, barcode: Optional[str] = None) -> Dict[str, Any]:
        """
        Satıcının ürünlerini listeler
        
        Args:
            page: Sayfa numarası
            limit: Sayfa başına ürün sayısı
            barcode: Barkod ile filtreleme (opsiyonel)
        
        Returns:
            Ürün listesi
        """
        app_logger.info(f"[IDEFIX] get_products çağrıldı - page: {page}, limit: {limit}, barcode: {barcode}")
        
        try:
            url = f"{self.PIM_BASE_URL}/pool/{self.seller_id}/list"
            params: Dict[str, Any] = {
                "page": page,
                "limit": limit
            }
            
            if barcode:
                params["barcode"] = barcode
            
            app_logger.info(f"[IDEFIX] API isteği: GET {url}")
            app_logger.debug(f"[IDEFIX] Params: {params}")
            
            response = requests.get(
                url, 
                headers=self._get_headers(),
                params=params,
                timeout=30
            )
            
            app_logger.info(f"[IDEFIX] API yanıtı: Status {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                product_count = len(data.get('products', []))
                app_logger.info(f"[IDEFIX] Başarılı: {product_count} ürün alındı")
                return {
                    "success": True,
                    "products": data.get("products", []),
                    "page": page,
                    "limit": limit,
                    "total": product_count
                }
            elif response.status_code == 401:
                app_logger.error("[IDEFIX] API: Yetkilendirme hatası (401)")
                return {
                    "success": False,
                    "error": "Yetkilendirme hatası. API Key ve Secret bilgilerini kontrol edin.",
                    "products": []
                }
            elif response.status_code == 429:
                app_logger.warning("[IDEFIX] API: Rate limit aşıldı (429)")
                return {
                    "success": False,
                    "error": "API istek limiti aşıldı. Lütfen biraz bekleyip tekrar deneyin.",
                    "products": []
                }
            else:
                app_logger.error(f"[IDEFIX] API hatası: {response.status_code} - {response.text[:500]}")
                return {
                    "success": False,
                    "error": f"API hatası: {response.status_code}",
                    "products": []
                }
                
        except requests.exceptions.Timeout:
            app_logger.error("[IDEFIX] API: Zaman aşımı")
            return {
                "success": False,
                "error": "İstek zaman aşımına uğradı",
                "products": []
            }
        except requests.exceptions.RequestException as e:
            app_logger.error(f"[IDEFIX] API bağlantı hatası: {str(e)}")
            return {
                "success": False,
                "error": f"Bağlantı hatası: {str(e)}",
                "products": []
            }
        except Exception as e:
            app_logger.error(f"[IDEFIX] Beklenmeyen hata: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "products": []
            }
    
    def get_product_by_barcode(self, barcode: str) -> Dict[str, Any]:
        """Barkod ile ürün arar"""
        return self.get_products(barcode=barcode)
    
    def get_all_products(self, max_pages: int = 100) -> Dict[str, Any]:
        """
        Tüm ürünleri sayfalama ile çeker
        
        Args:
            max_pages: Maksimum sayfa sayısı (güvenlik için)
        
        Returns:
            Tüm ürünlerin listesi
        """
        app_logger.info(f"[IDEFIX] Tüm ürünler çekiliyor (max_pages: {max_pages})")
        
        all_products = []
        page = 1
        limit = 100  # Maksimum limit
        
        while page <= max_pages:
            result = self.get_products(page=page, limit=limit)
            
            if not result.get("success"):
                app_logger.error(f"[IDEFIX] Sayfa {page} çekilirken hata: {result.get('error')}")
                break
            
            products = result.get("products", [])
            if not products:
                app_logger.info(f"[IDEFIX] Sayfa {page} boş, çekme tamamlandı")
                break
            
            all_products.extend(products)
            app_logger.info(f"[IDEFIX] Sayfa {page}: {len(products)} ürün (toplam: {len(all_products)})")
            
            # Eğer gelen ürün sayısı limit'ten azsa, son sayfadayız
            if len(products) < limit:
                break
            
            page += 1
        
        app_logger.info(f"[IDEFIX] Toplam {len(all_products)} ürün çekildi")
        
        return {
            "success": True,
            "products": all_products,
            "total": len(all_products)
        }
    
    def get_orders(self, status: Optional[str] = None) -> Dict[str, Any]:
        """Siparişleri getirir"""
        # TODO: Sipariş entegrasyonu eklenecek
        return {"success": False, "orders": [], "message": "Sipariş entegrasyonu henüz eklenmedi"}
    
    def update_stock(self, barcode: str, quantity: int, price: Optional[float] = None) -> Dict[str, Any]:
        """Tek ürün stok günceller"""
        items = [{"barcode": barcode, "inventoryQuantity": quantity}]
        if price:
            items[0]["price"] = price
        return self.update_stocks(items)
    
    def update_stocks(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Toplu stok ve fiyat güncelleme
        inventory-upload endpoint'i hem stok hem de fiyat güncellemesini destekler.
        
        Args:
            items: [{"barcode": "xxx", "inventoryQuantity": 10, "price": 100, "comparePrice": 120}, ...]
        
        Returns:
            API yanıtı
        """
        app_logger.info(f"[IDEFIX] Stok güncelleme başlatıldı - {len(items)} ürün")
        
        try:
            url = f"{self.PIM_BASE_URL}/catalog/{self.seller_id}/inventory-upload"
            
            # API formatına dönüştür - fiyat alanları da ekleniyor
            processed_items = []
            for item in items:
                if not item.get("barcode"):
                    continue
                    
                item_data = {
                    "barcode": item["barcode"],
                    "inventoryQuantity": max(0, int(item.get("inventoryQuantity", 0))),
                    "deliveryDuration": 1,
                    "deliveryType": "regular"
                }
                
                # Fiyat alanları varsa ekle (price = satış fiyatı, comparePrice = liste fiyatı)
                if item.get("price") or item.get("salePrice") or item.get("sale_price"):
                    price = float(item.get("price") or item.get("salePrice") or item.get("sale_price", 0))
                    if price > 0:
                        item_data["price"] = price
                        
                if item.get("comparePrice") or item.get("listPrice") or item.get("list_price"):
                    compare_price = float(item.get("comparePrice") or item.get("listPrice") or item.get("list_price", 0))
                    if compare_price > 0:
                        item_data["comparePrice"] = compare_price
                        
                processed_items.append(item_data)
            
            payload = {"items": processed_items}
            
            app_logger.info(f"[IDEFIX] API isteği: POST {url}")
            app_logger.debug(f"[IDEFIX] Payload örnek: {payload['items'][:3] if payload['items'] else 'boş'}")
            
            response = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=60
            )
            
            app_logger.info(f"[IDEFIX] API yanıtı: Status {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                app_logger.info(f"[IDEFIX] Stok güncelleme başarılı - batchRequestId: {data.get('batchRequestId', 'N/A')}")
                return {
                    "success": True,
                    "batch_request_id": data.get("batchRequestId"),
                    "message": f"{len(items)} ürün stok bilgisi gönderildi"
                }
            elif response.status_code == 401:
                app_logger.error("[IDEFIX] Stok güncelleme: Yetkilendirme hatası (401)")
                return {"success": False, "error": "Yetkilendirme hatası"}
            else:
                app_logger.error(f"[IDEFIX] Stok güncelleme hatası: {response.status_code} - {response.text[:500]}")
                return {"success": False, "error": f"API hatası: {response.status_code}"}
                
        except requests.exceptions.Timeout:
            app_logger.error("[IDEFIX] Stok güncelleme: Zaman aşımı")
            return {"success": False, "error": "İstek zaman aşımına uğradı"}
        except Exception as e:
            app_logger.error(f"[IDEFIX] Stok güncelleme hatası: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def update_order_status(self, order_id: str, status: str) -> Dict[str, Any]:
        """Sipariş durumunu günceller"""
        # TODO: Sipariş durumu güncelleme endpoint'i eklenecek
        return {"success": False, "message": "Sipariş durumu güncelleme henüz eklenmedi"}
    
    def update_prices(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Toplu fiyat güncelleme
        
        Idefix API'de ayrı price-upload endpoint'i yok.
        Fiyat güncellemesi inventory-upload endpoint'i üzerinden yapılıyor.
        price = satış fiyatı, comparePrice = liste/karşılaştırma fiyatı
        
        Args:
            items: [{"barcode": "xxx", "salePrice": 100.0, "listPrice": 120.0}, ...]
        
        Returns:
            API yanıtı
        """
        app_logger.info(f"[IDEFIX] Fiyat güncelleme başlatıldı - {len(items)} ürün")
        
        try:
            # inventory-upload endpoint'i hem stok hem fiyat güncellemesini destekliyor
            url = f"{self.PIM_BASE_URL}/catalog/{self.seller_id}/inventory-upload"
            
            # API formatına dönüştür - fiyat için price ve comparePrice kullanılıyor
            processed_items = []
            for item in items:
                if not item.get("barcode"):
                    continue
                    
                sale_price = float(item.get("salePrice") or item.get("sale_price") or 0)
                list_price = float(item.get("listPrice") or item.get("list_price") or sale_price)
                
                if sale_price <= 0:
                    continue
                    
                item_data = {
                    "barcode": item["barcode"],
                    "price": sale_price,  # Satış fiyatı
                    "comparePrice": list_price if list_price >= sale_price else sale_price,  # Liste fiyatı
                    "deliveryDuration": 1,
                    "deliveryType": "regular"
                }
                processed_items.append(item_data)
            
            if not processed_items:
                app_logger.warning("[IDEFIX] Fiyat güncellenecek ürün yok")
                return {"success": True, "message": "Güncellenecek ürün yok", "total_success": 0, "total_error": 0}
            
            app_logger.info(f"[IDEFIX] API isteği: POST {url}")
            app_logger.debug(f"[IDEFIX] Payload örnek: {processed_items[:3]}")
            
            # Batch gönderim (100'er)
            BATCH_SIZE = 100
            total_success = 0
            total_error = 0
            batch_ids = []
            
            for i in range(0, len(processed_items), BATCH_SIZE):
                batch = processed_items[i:i+BATCH_SIZE]
                batch_payload = {"items": batch}
                
                response = requests.post(
                    url,
                    headers=self._get_headers(),
                    json=batch_payload,
                    timeout=60
                )
                
                app_logger.info(f"[IDEFIX] Fiyat Batch {i//BATCH_SIZE + 1} yanıt: Status {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    batch_ids.append(data.get("batchRequestId", "N/A"))
                    total_success += len(batch)
                    app_logger.info(f"[IDEFIX] ✅ Batch başarılı - batchRequestId: {data.get('batchRequestId', 'N/A')}")
                else:
                    app_logger.error(f"[IDEFIX] ❌ Batch hatası: {response.status_code} - {response.text[:300]}")
                    total_error += len(batch)
            
            app_logger.info(f"[IDEFIX] Fiyat güncelleme tamamlandı - Başarılı: {total_success}, Hatalı: {total_error}")
            
            return {
                "success": total_error == 0,
                "batch_request_ids": batch_ids,
                "total_success": total_success,
                "total_error": total_error,
                "message": f"{total_success} ürün fiyatı gönderildi"
            }
                
        except requests.exceptions.Timeout:
            app_logger.error("[IDEFIX] Fiyat güncelleme: Zaman aşımı")
            return {"success": False, "error": "İstek zaman aşımına uğradı", "total_success": 0, "total_error": len(items)}
        except Exception as e:
            app_logger.error(f"[IDEFIX] Fiyat güncelleme hatası: {str(e)}")
            return {"success": False, "error": str(e), "total_success": 0, "total_error": len(items)}
    
    def update_stock_and_price(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Stok ve fiyatı birlikte günceller (tek API isteğiyle)
        inventory-upload endpoint'i hem stok hem fiyat güncellemesini destekler.
        
        Args:
            items: [{"barcode": "xxx", "quantity": 10, "salePrice": 100.0, "listPrice": 120.0}, ...]
        
        Returns:
            API yanıtı
        """
        app_logger.info(f"[IDEFIX] Stok ve fiyat güncelleme - {len(items)} ürün")
        
        # Tek istek ile hem stok hem fiyat gönder
        combined_items = []
        for it in items:
            item_data = {
                "barcode": it["barcode"],
                "inventoryQuantity": it.get("quantity", it.get("inventoryQuantity", 0))
            }
            
            # Fiyat varsa ekle
            if it.get("salePrice") or it.get("sale_price"):
                item_data["price"] = float(it.get("salePrice") or it.get("sale_price", 0))
            if it.get("listPrice") or it.get("list_price"):
                item_data["comparePrice"] = float(it.get("listPrice") or it.get("list_price", 0))
                
            combined_items.append(item_data)
        
        return self.update_stocks(combined_items)


# Singleton instance
idefix_service = IdefixService()
