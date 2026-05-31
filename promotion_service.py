# promotion_service.py
"""
Yeni → Hazırlanıyor terfi motoru
════════════════════════════════
Stoğu teyit edilen 'Yeni' (OrderCreated) siparişleri Trendyol'da 'Picking'e çekip
'Hazırlanıyor' (OrderHazirlaniyor) statüsüne taşır.

- Stok REZERVİ bu statüde tutulur (stock_sync.get_reserved_barcodes orders_hazirlaniyor okur).
- Fiziksel stok HÂLÂ paketleme onayında düşer (çift düşüm yok).
- Müsait stok = merkez_fiziksel − Hazırlanıyor'da söz verilmiş. Yeni'de bekleyenler taahhüt değil.
- Trendyol API patlarsa sipariş Yeni'de kalır, sonraki turda tekrar denenir (idempotent).
- Throttle: çağrılar arası küçük gecikme + tur başına üst sınır (rate limit dostu).
"""
import json
import logging
import asyncio
from collections import defaultdict
from datetime import datetime

from models import db, OrderCreated, OrderHazirlaniyor, CentralStock
from barcode_alias_helper import normalize_barcode

logger = logging.getLogger(__name__)

# Tur başına en fazla terfi (Trendyol rate-limit'i zorlamamak için)
MAX_PROMOTIONS_PER_RUN = 80
# Trendyol çağrıları arası gecikme (saniye)
THROTTLE_DELAY = 0.25
# Üst üste bu kadar Trendyol hatasında turu durdur (API çökmüş/rate-limit → boşa dövme).
MAX_CONSECUTIVE_API_FAILURES = 5


def _parse_details(details_raw):
    """details (JSON string ya da list) -> list[dict]."""
    if not details_raw:
        return []
    try:
        items = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
        return items if isinstance(items, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _physical_central():
    """barkod(canonical) -> fiziksel merkez stok adedi."""
    return {cs.barcode: int(cs.qty or 0) for cs in CentralStock.query.all()}


def _committed_in_hazirlaniyor():
    """Hazırlanıyor'da söz verilmiş (fiziksel taahhüt) barkod -> toplam adet."""
    committed = {}
    rows = db.session.query(OrderHazirlaniyor.details).all()
    for (det,) in rows:
        for it in _parse_details(det):
            bc = normalize_barcode(str(it.get('barcode', '') or '').strip())
            if not bc:
                continue
            qty = int(it.get('quantity', 1) or 1)
            committed[bc] = committed.get(bc, 0) + qty
    return committed


def _order_can_be_covered(order, available):
    """
    Siparişin TÜM kalemleri 'available' (kalan müsait) stoktan karşılanabiliyor mu?
    Karşılanıyorsa True döner ve tüketimi (bc -> normalized) bir dict olarak verir.
    """
    details = _parse_details(order.details)
    if not details:
        return False, None
    need = {}  # normalized_bc -> toplam adet
    for it in details:
        bc = normalize_barcode(str(it.get('barcode', '') or '').strip())
        if not bc:
            return False, None  # barkodsuz kalem → güvenli tarafta kal, terfi etme
        need[bc] = need.get(bc, 0) + int(it.get('quantity', 1) or 1)
    for bc, qty in need.items():
        if available.get(bc, 0) < qty:
            return False, None
    return True, need


def _build_trendyol_lines(order):
    """
    confirm_packing ile aynı mantık: paket(shipmentPackageId) -> [{lineId, quantity}, ...].
    Eksik/biçimsiz veri varsa (None, None) döner → sipariş terfi edilmez.
    """
    details = _parse_details(order.details)
    if not details:
        return None
    sp_default = order.shipment_package_id or order.package_number
    lines_by_sp = defaultdict(list)
    try:
        for d in details:
            lid = d.get('line_id') or d.get('line_ids_api')
            if not lid:
                return None
            q = int(d.get('quantity', 1) or 1)
            sp = d.get('shipmentPackageId') or sp_default
            if not sp:
                return None
            # line_id virgülle birleşik olabilir; her birini ayrı satır yap
            parts = [p.strip() for p in str(lid).split(',') if p.strip()]
            if not parts:
                return None
            for one in parts:
                lines_by_sp[str(sp)].append({"lineId": int(one), "quantity": q})
    except (ValueError, TypeError) as e:
        logger.warning(f"[TERFI] {order.order_number}: line/paket biçimi çözülemedi ({e}) — atlandı")
        return None
    return dict(lines_by_sp) if lines_by_sp else None


def _move_created_to_hazirlaniyor(order):
    """OrderCreated kaydını OrderHazirlaniyor'a taşır (id autoincrement, atanan_raf korunur)."""
    data = order.__dict__.copy()
    data.pop('_sa_instance_state', None)
    data.pop('id', None)  # yeni tabloda otomatik üretilsin
    cols = {c.name for c in OrderHazirlaniyor.__table__.columns}
    data = {k: v for k, v in data.items() if k in cols}
    new_rec = OrderHazirlaniyor(**data)
    new_rec.hazirlaniyor_since = datetime.utcnow()
    db.session.add(new_rec)
    db.session.delete(order)
    db.session.commit()


async def promote_eligible_orders(max_promotions=MAX_PROMOTIONS_PER_RUN):
    """
    Stoğu müsait olan Yeni siparişleri Hazırlanıyor'a terfi ettirir.
    Dönüş: {'promoted': int, 'checked': int, 'skipped_stock': int, 'skipped_api': int}
    """
    # Trendyol bağımlılıklarını fonksiyon içinde import et (circular import'tan kaçın)
    from update_service import update_order_status_to_picking
    from trendyol_api import SUPPLIER_ID

    stats = {'promoted': 0, 'checked': 0, 'skipped_stock': 0, 'skipped_api': 0}
    consecutive_api_fail = 0  # devre kesici sayacı
    uncovered = []  # stok yetersizliğinden terfi edilemeyenler (anlık mail için)

    central = _physical_central()
    committed = _committed_in_hazirlaniyor()
    # Müsait = fiziksel − Hazırlanıyor taahhütleri
    available = {bc: central.get(bc, 0) - committed.get(bc, 0) for bc in set(central) | set(committed)}

    # Yeni siparişler: cut-off'a göre (acil önce), tarihi olmayan en sona, sonra FIFO
    candidates = (OrderCreated.query
                  .order_by(OrderCreated.agreed_delivery_date.asc().nullslast(),
                            OrderCreated.order_date.asc())
                  .all())

    for order in candidates:
        if stats['promoted'] >= max_promotions:
            logger.info(f"[TERFI] Tur sınırına ulaşıldı ({max_promotions}); kalanlar sonraki turda.")
            break
        stats['checked'] += 1

        ok, need = _order_can_be_covered(order, available)
        if not ok:
            stats['skipped_stock'] += 1
            uncovered.append(order)
            continue

        lines_by_sp = _build_trendyol_lines(order)
        if not lines_by_sp:
            stats['skipped_api'] += 1
            continue

        # Trendyol: tüm paketleri Picking'e çek (hepsi başarılı olmalı)
        all_ok = True
        for sp_id, lines in lines_by_sp.items():
            try:
                res = await update_order_status_to_picking(SUPPLIER_ID, sp_id, lines)
            except Exception as e:
                logger.error(f"[TERFI] {order.order_number} paket {sp_id} API hatası: {e}")
                res = False
            if not res:
                all_ok = False
                break
            await asyncio.sleep(THROTTLE_DELAY)

        if not all_ok:
            stats['skipped_api'] += 1
            consecutive_api_fail += 1
            logger.info(f"[TERFI] {order.order_number}: Trendyol Picking başarısız — Yeni'de kalıyor, sonra denenecek")
            # Devre kesici: üst üste çok hata → API çökmüş/rate-limit, turu bitir (boşa dövme).
            if consecutive_api_fail >= MAX_CONSECUTIVE_API_FAILURES:
                logger.warning(f"[TERFI] Üst üste {consecutive_api_fail} Trendyol hatası — tur durduruldu (sonraki turda denenecek).")
                break
            continue

        consecutive_api_fail = 0  # başarılı çağrı sayacı sıfırlar

        # API başarılı → DB'de taşı ve müsait stoğu düş
        try:
            order_no = order.order_number
            _move_created_to_hazirlaniyor(order)
            for bc, qty in need.items():
                available[bc] = available.get(bc, 0) - qty
            stats['promoted'] += 1
            logger.info(f"[TERFI] ✅ {order_no} → Hazırlanıyor (Trendyol Picking)")
            try:
                from order_audit import log_event as _audit_log
                _audit_log(
                    "status_changed",
                    order_number=order_no,
                    status_from="created",
                    status_to="hazirlaniyor",
                    source="AUTO_PROMOTE",
                    message="Stok teyit edildi, otomatik Hazırlanıyor'a alındı (Trendyol Picking)",
                )
            except Exception:
                pass
        except Exception as e:
            db.session.rollback()
            stats['skipped_api'] += 1
            logger.error(f"[TERFI] {order.order_number}: DB taşıma hatası: {e}")

    # Anlık stok-yok bildirimi: bu turda terfi edilemeyen (stoksuz) ve henüz
    # bildirilmemiş siparişler için tek bir mail gönder + işaretle.
    if uncovered:
        try:
            from stock_alert_service import alert_uncovered_orders
            alert_uncovered_orders(uncovered)
        except Exception as e:
            logger.error(f"[TERFI] Stok-yok anlık bildirim hatası: {e}", exc_info=True)

    if stats['promoted'] or stats['checked']:
        logger.info(f"[TERFI] Tur bitti: {stats}")
    return stats
