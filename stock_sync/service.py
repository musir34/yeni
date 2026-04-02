# -*- coding: utf-8 -*-
"""
Stock Sync Service - Merkezi Stok Senkronizasyon Servisi
=========================================================
Tüm platformlara stok gönderimini yöneten ana servis.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from concurrent.futures import ThreadPoolExecutor

from models import db, CentralStock, Product, SyncSession, SyncDetail, PlatformConfig, OrderCreated
from logger_config import app_logger as logger

from .adapters.base import StockItem, SyncResult
from .adapters.trendyol import TrendyolAdapter
from .adapters.idefix import IdefixAdapter
from .adapters.amazon import AmazonAdapter
from .adapters.hepsiburada import HepsiburadaAdapter


class StockSyncService:
    """
    Merkezi Stok Senkronizasyon Servisi
    
    Kullanım:
        service = StockSyncService()
        
        # Tüm platformlara sync
        result = await service.sync_all_platforms()
        
        # Tek platforma sync
        result = await service.sync_platform("trendyol")
        
        # Belirli ürünleri sync
        result = await service.sync_specific_barcodes(["BARCODE1", "BARCODE2"], platforms=["trendyol"])
    """
    
    PLATFORM_ADAPTERS = {
        "trendyol": TrendyolAdapter,
        "idefix": IdefixAdapter,
        "amazon": AmazonAdapter,
        "hepsiburada": HepsiburadaAdapter,
    }
    
    def __init__(self):
        self._adapters: Dict[str, Any] = {}
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._active_sessions: Dict[str, SyncSession] = {}
        self._init_adapters()
    
    def _init_adapters(self):
        """Platform adaptörlerini başlat"""
        for platform_name, adapter_class in self.PLATFORM_ADAPTERS.items():
            try:
                adapter = adapter_class()
                self._adapters[platform_name] = adapter
                status = "✅ aktif" if adapter.is_configured else "❌ yapılandırılmamış"
                logger.info(f"[SYNC] {platform_name.upper()} adapter: {status}")
            except Exception as e:
                logger.error(f"[SYNC] {platform_name} adapter başlatma hatası: {e}")
        
        # NOT: cleanup_stale_sessions() route içinde çağrılacak (app context gerekli)
    
    def cleanup_stale_sessions(self, timeout_minutes: int = 30):
        """
        Yarıda kalmış session'ları temizle.
        - 'running' durumunda olup belirli süreden fazla olan session'lar 'cancelled' olarak işaretlenir.
        - Bu metod uygulama başlangıcında veya periyodik olarak çağrılabilir.
        """
        from datetime import timedelta
        
        try:
            timeout_threshold = datetime.utcnow() - timedelta(minutes=timeout_minutes)
            
            stale_sessions = SyncSession.query.filter(
                SyncSession.status == 'running',
                SyncSession.created_at < timeout_threshold
            ).all()
            
            if stale_sessions:
                logger.warning(f"[SYNC] {len(stale_sessions)} adet yarıda kalmış session bulundu, cancelled olarak işaretleniyor...")
                for session in stale_sessions:
                    session.status = 'cancelled'
                    session.completed_at = datetime.utcnow()
                    session.error_message = f"Session zaman aşımına uğradı ({timeout_minutes} dakikadan fazla sürdü veya uygulama yeniden başlatıldı)"
                    if session.created_at:
                        session.duration_seconds = (session.completed_at - session.created_at).total_seconds()
                    logger.info(f"[SYNC] Session {session.session_id} cancelled olarak işaretlendi")
                db.session.commit()
        except Exception as e:
            logger.error(f"[SYNC] Stale session cleanup hatası: {e}")
            db.session.rollback()
    
    def get_configured_platforms(self) -> List[str]:
        """Yapılandırılmış platformları döndür"""
        platforms = [name for name, adapter in self._adapters.items() if adapter.is_configured]
        # Shopify yeni dedicated servisten kontrol edilir
        from shopify_site.shopify_stock_service import shopify_stock_service
        if shopify_stock_service.is_configured():
            platforms.append("shopify")
        return platforms
    
    def get_platform_status(self) -> Dict[str, Dict]:
        """Tüm platformların durumunu döndür"""
        status = {}
        for name, adapter in self._adapters.items():
            status[name] = {
                "configured": adapter.is_configured,
                "batch_size": adapter.BATCH_SIZE,
                "rate_limit_delay": adapter.RATE_LIMIT_DELAY
            }
        # Shopify yeni dedicated servisten kontrol edilir
        from shopify_site.shopify_stock_service import shopify_stock_service
        status["shopify"] = {
            "configured": shopify_stock_service.is_configured(),
            "batch_size": 100,
            "rate_limit_delay": 0.3
        }
        return status
    
    def get_reserved_barcodes(self) -> Dict[str, int]:
        """orders_created tablosundaki siparişlerin details JSON'undan rezerv barkodlarını ve miktarları çıkar"""
        import json

        rows = db.session.query(OrderCreated.order_number, OrderCreated.details).all()
        reserved_map = {}
        parse_errors = 0

        for order_number, details_str in rows:
            if not details_str:
                continue
            try:
                details = json.loads(details_str) if isinstance(details_str, str) else details_str
                if not isinstance(details, list):
                    logger.warning(
                        f"[REZERV] Sipariş {order_number}: details alanı list değil, atlanıyor"
                    )
                    parse_errors += 1
                    continue
                for item in details:
                    barcode = str(item.get('barcode', '') or '').strip()
                    qty = int(item.get('quantity', 1) or 1)
                    if barcode:
                        from barcode_alias_helper import normalize_barcode
                        normalized = normalize_barcode(barcode)
                        reserved_map[normalized] = reserved_map.get(normalized, 0) + qty
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                parse_errors += 1
                logger.error(
                    f"[REZERV] Sipariş {order_number}: details JSON parse hatası — {e}"
                )
                continue

        if parse_errors > 0:
            logger.warning(f"[REZERV] Toplam {parse_errors} sipariş detayı parse edilemedi")

        return reserved_map
    
    def get_reserved_count(self) -> int:
        """Toplam rezerv edilen ürün sayısı"""
        return sum(self.get_reserved_barcodes().values())

    def _get_all_stocks(self, platform: str = None) -> List[StockItem]:
        """CentralStock'tan tüm stokları çek.
        Bekleyen siparişlerdeki (OrderCreated) ürün miktarları rezerv olarak düşülür.
        """
        stocks = CentralStock.query.all()
        items = []

        # Rezerv: Bekleyen siparişlerdeki ürün miktarlarını hesapla
        reserved_map = self.get_reserved_barcodes()
        if reserved_map:
            logger.info(f"[SYNC] {len(reserved_map)} barkod için rezerv hesaplandı (toplam {sum(reserved_map.values())} adet)")

        # Platform'a göre eşleştirme map'leri
        asin_map = {}

        # Amazon için ASIN eşleştirmesi
        if platform == "amazon":
            products_with_asin = Product.query.filter(
                Product.amazon_asin.isnot(None),
                Product.amazon_asin != ''
            ).all()
            asin_map = {p.barcode: p.amazon_asin for p in products_with_asin}
            logger.info(f"[SYNC] Amazon için {len(asin_map)} ASIN eşleşmesi bulundu")

        for stock in stocks:
            asin = asin_map.get(stock.barcode) if platform == "amazon" else None

            # Amazon için ASIN'i olmayan ürünleri atla
            if platform == "amazon" and not asin:
                continue

            reserved = reserved_map.get(stock.barcode, 0)
            available_qty = max(0, (stock.qty or 0) - reserved)

            items.append(StockItem(
                barcode=stock.barcode,
                quantity=available_qty,
                asin=asin,
            ))

        logger.info(f"[SYNC] {len(items)} ürün CentralStock'tan alındı")
        return items
    
    def _get_stocks_by_barcodes(self, barcodes: List[str], platform: str = None) -> List[StockItem]:
        """Belirli barkodlar için stokları çek.
        Bekleyen siparişlerdeki (OrderCreated) ürün miktarları rezerv olarak düşülür.
        """
        stocks = CentralStock.query.filter(CentralStock.barcode.in_(barcodes)).all()
        items = []

        stock_dict = {s.barcode: s.qty for s in stocks}

        # Rezerv: Bekleyen siparişlerdeki ürün miktarları
        reserved_map = self.get_reserved_barcodes()

        # Amazon için ASIN eşleştirmesi
        asin_map = {}

        if platform == "amazon":
            products_with_asin = Product.query.filter(
                Product.barcode.in_(barcodes),
                Product.amazon_asin.isnot(None),
                Product.amazon_asin != ''
            ).all()
            asin_map = {p.barcode: p.amazon_asin for p in products_with_asin}

        for barcode in barcodes:
            asin = asin_map.get(barcode) if platform == "amazon" else None

            # Amazon için ASIN yoksa atla
            if platform == "amazon" and not asin:
                continue

            reserved = reserved_map.get(barcode, 0)
            available_qty = max(0, stock_dict.get(barcode, 0) - reserved)

            items.append(StockItem(
                barcode=barcode,
                quantity=available_qty,
                asin=asin,
            ))

        return items
    
    def _create_session(self, platform: str, triggered_by: str = "manual", 
                        triggered_by_user: Optional[str] = None) -> SyncSession:
        """Yeni sync session oluştur"""
        session = SyncSession(
            session_id=str(uuid.uuid4()),
            platform=platform,
            status="pending",
            triggered_by=triggered_by,
            triggered_by_user=triggered_by_user
        )
        db.session.add(session)
        db.session.commit()
        return session
    
    def _update_session(self, session: SyncSession, **kwargs):
        """Session güncelle"""
        for key, value in kwargs.items():
            if hasattr(session, key):
                setattr(session, key, value)
        db.session.commit()
    
    def _save_sync_details(self, session: SyncSession, results: List[SyncResult], platform: str):
        """Sync detaylarını kaydet"""
        for result in results:
            detail = SyncDetail(
                session_id=session.id,
                barcode=result.barcode,
                platform=platform,
                stock_sent=result.quantity_sent,  # Gönderilen gerçek stok değeri
                status="success" if result.success else "error",
                error_message=result.error_message,
                response_data=result.response_data,
                sent_at=result.sent_at,
                response_at=result.response_at
            )
            db.session.add(detail)
        
        db.session.commit()
    
    def _sync_shopify(
        self,
        triggered_by: str = "manual",
        triggered_by_user: Optional[str] = None,
        barcodes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Shopify stok senkronizasyonu - Yeni dedicated servis üzerinden.
        ShopifyStockService.push_stock() kullanır.
        """
        from shopify_site.shopify_stock_service import shopify_stock_service

        if not shopify_stock_service.is_configured():
            return {"success": False, "error": "Shopify yapılandırılmamış"}

        session = self._create_session("shopify", triggered_by, triggered_by_user)
        self._update_session(session, status="running", started_at=datetime.utcnow())
        self._active_sessions[session.session_id] = session

        try:
            result = shopify_stock_service.push_stock(barcodes=barcodes)

            completed_at = datetime.utcnow()
            duration = (completed_at - session.started_at).total_seconds()

            success_count = result.get("success_count", 0)
            error_count = result.get("error_count", 0)
            total = result.get("total", 0)

            self._update_session(session,
                                 status="completed",
                                 completed_at=completed_at,
                                 duration_seconds=duration,
                                 total_products=total,
                                 sent_count=total,
                                 success_count=success_count,
                                 error_count=error_count)

            # Platform config güncelle
            self._update_platform_last_sync("shopify")

            logger.info(f"[SYNC] SHOPIFY tamamlandı - Başarılı: {success_count}, Hata: {error_count}, Süre: {duration:.1f}s")

            return {
                "success": True,
                "session_id": session.session_id,
                "platform": "shopify",
                "total": total,
                "sent": total,
                "success_count": success_count,
                "error_count": error_count,
                "duration_seconds": duration,
                "success_rate": f"{(success_count / total * 100):.1f}%" if total else "0%"
            }

        except Exception as e:
            logger.error(f"[SYNC] SHOPIFY hatası: {e}")
            self._update_session(session,
                                 status="failed",
                                 completed_at=datetime.utcnow(),
                                 error_message=str(e))
            return {
                "success": False,
                "session_id": session.session_id,
                "error": str(e)
            }
        finally:
            if session.session_id in self._active_sessions:
                del self._active_sessions[session.session_id]

    async def sync_platform(
        self, 
        platform: str,
        barcodes: Optional[List[str]] = None,
        triggered_by: str = "manual",
        triggered_by_user: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Tek bir platforma stok senkronizasyonu.
        
        Args:
            platform: Platform adı (trendyol, idefix, amazon, hepsiburada, shopify)
            barcodes: Belirli barkodlar (None ise tümü)
            triggered_by: Tetikleyici (manual, scheduler, webhook)
            triggered_by_user: Tetikleyen kullanıcı
            progress_callback: İlerleme callback'i (sent, total, message)
            
        Returns:
            Senkronizasyon sonuç raporu
        """
        # Shopify dedicated servis üzerinden çalışır
        if platform == "shopify":
            return self._sync_shopify(triggered_by, triggered_by_user, barcodes=barcodes)

        if platform not in self._adapters:
            return {"success": False, "error": f"Bilinmeyen platform: {platform}"}
        
        adapter = self._adapters[platform]
        
        if not adapter.is_configured:
            return {"success": False, "error": f"{platform} yapılandırılmamış"}
        
        # Session oluştur
        session = self._create_session(platform, triggered_by, triggered_by_user)
        self._active_sessions[session.session_id] = session
        
        try:
            # Stokları al (Amazon için ASIN dahil)
            if barcodes:
                items = self._get_stocks_by_barcodes(barcodes, platform=platform)
            else:
                items = self._get_all_stocks(platform=platform)
            
            self._update_session(session, 
                                 status="running",
                                 started_at=datetime.utcnow(),
                                 total_products=len(items))
            
            if not items:
                self._update_session(session, 
                                     status="completed",
                                     completed_at=datetime.utcnow(),
                                     duration_seconds=0)
                return {
                    "success": True,
                    "session_id": session.session_id,
                    "message": "Gönderilecek ürün yok",
                    "total": 0
                }
            
            # İlerleme callback wrapper
            def _progress(sent: int, total: int):
                self._update_session(session, sent_count=sent)
                if progress_callback:
                    progress_callback(sent, total, f"{platform}: {sent}/{total}")
            
            # Stokları gönder
            logger.info(f"[SYNC] {platform.upper()} senkronizasyonu başladı - {len(items)} ürün")
            
            results = await adapter.send_all_stocks(items, progress_callback=_progress)
            
            # Sonuçları hesapla
            success_count = sum(1 for r in results if r.success)
            error_count = sum(1 for r in results if not r.success)
            
            completed_at = datetime.utcnow()
            duration = (completed_at - session.started_at).total_seconds() if session.started_at else 0
            
            self._update_session(session,
                                 status="completed",
                                 completed_at=completed_at,
                                 duration_seconds=duration,
                                 sent_count=len(results),
                                 success_count=success_count,
                                 error_count=error_count)
            
            # Detayları kaydet
            self._save_sync_details(session, results, platform)
            
            # Platform config güncelle
            self._update_platform_last_sync(platform)
            
            logger.info(f"[SYNC] {platform.upper()} tamamlandı - Başarılı: {success_count}, Hata: {error_count}, Süre: {duration:.1f}s")
            
            return {
                "success": True,
                "session_id": session.session_id,
                "platform": platform,
                "total": len(items),
                "sent": len(results),
                "success_count": success_count,
                "error_count": error_count,
                "duration_seconds": duration,
                "success_rate": f"{(success_count/len(results)*100):.1f}%" if results else "0%"
            }
            
        except Exception as e:
            logger.error(f"[SYNC] {platform} hatası: {e}")
            self._update_session(session,
                                 status="failed",
                                 completed_at=datetime.utcnow(),
                                 error_message=str(e))
            return {
                "success": False,
                "session_id": session.session_id,
                "error": str(e)
            }
        finally:
            if session.session_id in self._active_sessions:
                del self._active_sessions[session.session_id]
    
    async def sync_all_platforms(
        self,
        barcodes: Optional[List[str]] = None,
        triggered_by: str = "manual",
        triggered_by_user: Optional[str] = None,
        parallel: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Tüm aktif platformlara stok senkronizasyonu.
        
        Args:
            barcodes: Belirli barkodlar (None ise tümü)
            triggered_by: Tetikleyici
            triggered_by_user: Tetikleyen kullanıcı
            parallel: Paralel mi yoksa sıralı mı çalışsın
            progress_callback: İlerleme callback'i
            
        Returns:
            Tüm platformların sonuç raporu
        """
        configured_platforms = self.get_configured_platforms()
        
        if not configured_platforms:
            return {"success": False, "error": "Hiçbir platform yapılandırılmamış"}
        
        logger.info(f"[SYNC] Tüm platformlara sync başlıyor: {configured_platforms}")
        
        results = {}
        start_time = datetime.utcnow()
        
        if parallel:
            # Paralel çalıştır
            tasks = []
            for platform in configured_platforms:
                task = self.sync_platform(
                    platform=platform,
                    barcodes=barcodes,
                    triggered_by=triggered_by,
                    triggered_by_user=triggered_by_user,
                    progress_callback=progress_callback
                )
                tasks.append((platform, task))
            
            # Tüm task'ları çalıştır
            platform_results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
            
            for (platform, _), result in zip(tasks, platform_results):
                if isinstance(result, Exception):
                    results[platform] = {"success": False, "error": str(result)}
                else:
                    results[platform] = result
        else:
            # Sıralı çalıştır
            for platform in configured_platforms:
                result = await self.sync_platform(
                    platform=platform,
                    barcodes=barcodes,
                    triggered_by=triggered_by,
                    triggered_by_user=triggered_by_user,
                    progress_callback=progress_callback
                )
                results[platform] = result
        
        end_time = datetime.utcnow()
        total_duration = (end_time - start_time).total_seconds()
        
        # Özet oluştur
        total_success = sum(r.get("success_count", 0) for r in results.values() if isinstance(r, dict))
        total_error = sum(r.get("error_count", 0) for r in results.values() if isinstance(r, dict))
        
        return {
            "success": True,
            "platforms": results,
            "total_duration_seconds": total_duration,
            "summary": {
                "platforms_synced": len(configured_platforms),
                "total_success": total_success,
                "total_error": total_error
            }
        }
    
    async def sync_specific_barcodes(
        self,
        barcodes: List[str],
        platforms: Optional[List[str]] = None,
        triggered_by: str = "manual",
        triggered_by_user: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Belirli barkodları belirli platformlara sync et.
        
        Args:
            barcodes: Sync edilecek barkodlar
            platforms: Hedef platformlar (None ise tümü)
            triggered_by: Tetikleyici
            triggered_by_user: Tetikleyen kullanıcı
        """
        if not barcodes:
            return {"success": False, "error": "Barkod listesi boş"}
        
        if platforms:
            configured = self.get_configured_platforms()
            target_platforms = [p for p in platforms if p in configured]
        else:
            target_platforms = self.get_configured_platforms()
        
        if not target_platforms:
            return {"success": False, "error": "Hedef platform yok"}
        
        results = {}
        for platform in target_platforms:
            result = await self.sync_platform(
                platform=platform,
                barcodes=barcodes,
                triggered_by=triggered_by,
                triggered_by_user=triggered_by_user
            )
            results[platform] = result
        
        return {
            "success": True,
            "barcodes_count": len(barcodes),
            "platforms": results
        }
    
    def _update_platform_last_sync(self, platform: str):
        """Platform son sync zamanını güncelle"""
        try:
            config = PlatformConfig.query.filter_by(platform=platform).first()
            if not config:
                config = PlatformConfig(platform=platform)
                db.session.add(config)
            
            config.last_sync_at = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            logger.warning(f"[SYNC] Platform config güncellenemedi: {e}")
    
    def get_active_sessions(self) -> List[Dict]:
        """Aktif sync session'larını döndür"""
        return [s.to_dict() for s in self._active_sessions.values()]
    
    def get_session_history(self, limit: int = 50, platform: Optional[str] = None) -> List[Dict]:
        """Sync geçmişini döndür"""
        query = SyncSession.query.order_by(SyncSession.created_at.desc())
        
        if platform:
            query = query.filter_by(platform=platform)
        
        sessions = query.limit(limit).all()
        return [s.to_dict() for s in sessions]
    
    def get_session_details(self, session_id: str) -> Optional[Dict]:
        """Session detaylarını döndür (rezerv bilgisiyle birlikte)"""
        session = SyncSession.query.filter_by(session_id=session_id).first()
        
        if not session:
            return None
        
        details = SyncDetail.query.filter_by(session_id=session.id).all()
        
        # Rezerv bilgilerini al
        reserved_barcodes = self.get_reserved_barcodes()
        
        # Her detaya rezerv sayısını ekle
        details_with_reserve = []
        for d in details:
            detail_dict = d.to_dict()
            detail_dict['reserved_qty'] = reserved_barcodes.get(d.barcode, 0)
            details_with_reserve.append(detail_dict)
        
        return {
            **session.to_dict(),
            "details": details_with_reserve,
            "total_reserved": sum(reserved_barcodes.get(d.barcode, 0) for d in details)
        }
    
    def cancel_session(self, session_id: str) -> bool:
        """Aktif session'ı iptal et"""
        if session_id in self._active_sessions:
            session = self._active_sessions[session_id]
            self._update_session(session, status="cancelled", completed_at=datetime.utcnow())
            del self._active_sessions[session_id]
            return True
        return False
    
    def run_sync_in_background(self, platform: str = "all", **kwargs) -> str:
        """
        Sync'i arka planda çalıştır (blocking olmayan).
        
        Returns:
            Session ID
        """
        session_id = str(uuid.uuid4())
        
        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if platform == "all":
                    loop.run_until_complete(self.sync_all_platforms(**kwargs))
                else:
                    loop.run_until_complete(self.sync_platform(platform=platform, **kwargs))
            finally:
                loop.close()
        
        self._executor.submit(_run)
        return session_id


# Singleton instance
stock_sync_service = StockSyncService()


# Sync helper fonksiyonlar (non-async wrapper)
def sync_all_platforms_sync(**kwargs) -> Dict[str, Any]:
    """Sync wrapper for non-async contexts"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(stock_sync_service.sync_all_platforms(**kwargs))
    finally:
        loop.close()


def sync_platform_sync(platform: str, **kwargs) -> Dict[str, Any]:
    """Sync wrapper for non-async contexts"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(stock_sync_service.sync_platform(platform=platform, **kwargs))
    finally:
        loop.close()


def _sync_central_stock_from_raf():
    """
    CentralStock tablosunu raf stoklarıyla otomatik senkronize eder.
    Platform sync'inden ÖNCE çağrılır, böylece güncel stoklar iletilir.
    """
    from models import CentralStock, RafUrun
    from sqlalchemy import func
    from datetime import datetime, timezone
    
    try:
        # 1. Adet 0 veya altı olan RafUrun kayıtlarını sil
        deleted_count = RafUrun.query.filter(RafUrun.adet <= 0).delete()
        
        # 2. Raflardaki toplam stokları hesapla
        raf_totals = db.session.query(
            RafUrun.urun_barkodu.label('barcode'),
            func.sum(RafUrun.adet).label('total')
        ).filter(
            RafUrun.adet > 0
        ).group_by(
            RafUrun.urun_barkodu
        ).all()
        
        raf_dict = {r.barcode: int(r.total) for r in raf_totals}
        
        # 3. CentralStock kayıtlarını güncelle
        fixed_count = 0
        cs_all = CentralStock.query.all()
        
        for cs in cs_all:
            raf_toplam = raf_dict.get(cs.barcode, 0)
            
            if cs.qty != raf_toplam:
                cs.qty = raf_toplam
                cs.updated_at = datetime.now(timezone.utc)
                fixed_count += 1
        
        db.session.commit()
        
        logger.info(f"[AUTO-SYNC] CentralStock raf senkronizasyonu: {fixed_count} düzeltildi, {deleted_count} boş kayıt silindi")
        return {"fixed": fixed_count, "deleted": deleted_count}
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"[AUTO-SYNC] CentralStock raf senkronizasyon hatası: {e}")
        return {"error": str(e)}


def auto_sync_platforms_except_idefix() -> Dict[str, Any]:
    """
    Otomatik stok senkronizasyonu - Idefix HARİÇ tüm platformlar.
    APScheduler tarafından 15 dakikada bir çağrılır.
    Önce CentralStock'u raf toplamlarıyla senkronize eder, sonra platformlara gönderir.
    """
    # Global otomatik sync kontrolü
    global_config = PlatformConfig.query.filter_by(platform='global').first()
    if global_config and not global_config.is_active:
        logger.info("[AUTO-SYNC] Otomatik senkronizasyon DEVRE DIŞI - atlanıyor.")
        return {"skipped": True, "reason": "auto_sync_disabled"}
    
    # ÖNCELİKLE: CentralStock'u raf stoklarıyla senkronize et
    logger.info("[AUTO-SYNC] Önce CentralStock ↔ Raf senkronizasyonu yapılıyor...")
    raf_sync_result = _sync_central_stock_from_raf()
    logger.info(f"[AUTO-SYNC] CentralStock ↔ Raf sync sonucu: {raf_sync_result}")
    
    logger.info("[AUTO-SYNC] Otomatik stok senkronizasyonu başlatılıyor (Idefix hariç)...")
    
    # İdefix hariç platformlar
    platforms_to_sync = ["trendyol", "amazon", "shopify"]
    
    results = {}
    loop = asyncio.new_event_loop()
    
    try:
        for platform in platforms_to_sync:
            try:
                result = loop.run_until_complete(
                    stock_sync_service.sync_platform(
                        platform=platform,
                        triggered_by="auto_scheduler"
                    )
                )
                results[platform] = result
                logger.info(f"[AUTO-SYNC] {platform.upper()}: success={result.get('success_count', 0)}, error={result.get('error_count', 0)}")
            except Exception as e:
                logger.error(f"[AUTO-SYNC] {platform.upper()} hatası: {e}")
                results[platform] = {"success": False, "error": str(e)}
    finally:
        loop.close()
    
    logger.info(f"[AUTO-SYNC] Otomatik senkronizasyon tamamlandı: {len(results)} platform")
    return results


def migrate_existing_reserved_stock() -> Dict[str, Any]:
    """
    Mevcut OrderCreated kayıtları için raf stoğunu tahsis eder (tek seferlik migrasyon).
    Yeni stok tahsis sistemi devreye alındığında, eski siparişlerin
    raf stoğundan düşülmesi için çağrılmalıdır.

    Returns: {"processed": int, "allocated": int, "errors": int}
    """
    from stock_management import allocate_stock_for_order_details

    orders = OrderCreated.query.all()
    processed = 0
    allocated = 0
    errors = 0

    for order in orders:
        if not order.details:
            continue
        try:
            results = allocate_stock_for_order_details(order.details, commit=False)
            for barcode, alloc in results.items():
                allocated += alloc.get('allocated', 0)
            processed += 1
        except Exception as e:
            errors += 1
            logger.error(
                f"[MİGRASYON] Sipariş {order.order_number} stok tahsisi hatası: {e}"
            )

    if processed > 0:
        db.session.commit()

    logger.info(
        f"[MİGRASYON] Tamamlandı: {processed} sipariş işlendi, "
        f"{allocated} adet tahsis edildi, {errors} hata"
    )

    return {"processed": processed, "allocated": allocated, "errors": errors}
