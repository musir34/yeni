"""Stok Hareket Defteri (Ledger) — merkezi stok mutasyon katmanı.

AMAÇ
----
Sipariş yaşam döngüsünün her statü geçişinde stok mutasyonu ayrı ayrı, elle
yazılıyordu; biri "düşmeyi unutunca" hayalet stok sızıntısı oluyordu (kronik
bug sınıfı). Bu modül stok etkisini TEK yerden, **bildirimsel** (declarative)
ve **idempotent** yönetir:

- `record_movement(...)`     — tek bir fiziksel hareketi (delta) deftere yazar
                               ve gerekiyorsa rafı mutasyona uğratır.
- `apply_lifecycle_effect(...)` — (from_status → to_status) geçişinin stok
                               etkisini ``LIFECYCLE_EFFECTS`` haritasından
                               bulup uygular.

TASARIM
-------
- RafUrun.adet operasyonel kaynak olarak KALIR. Fiziksel mutasyon, kanıtlanmış
  mevcut fonksiyonlara delege edilir (yeniden yazılmaz):
    * çıkış (delta<0) → ``allocate_from_shelf_and_decrement``
    * giriş (delta>0) → ``restore_stock_to_shelf``
  Bunlar zaten ``with_for_update`` kilidi + ``sync_central_stock`` çağırır,
  böylece CentralStock/Product ve audit listener'ları normal tetiklenir.
- Idempotency: anahtarlı hareketler ``stock_movement.idempotency_key`` (unique)
  ile çift-apply'a karşı korunur. 3 saatlik reconcile job aynı geçişi tekrar
  beslese bile raf ikinci kez düşmez.
- ``mutate_shelf=False``: çağıran tarafın rafı zaten mutasyona uğrattığı
  durumlar (ör. confirm_packing seçili raftan düşer) — defter sadece kaydeder.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from models import db, StockMovement
from barcode_alias_helper import normalize_barcode
from stock_management import (
    allocate_from_shelf_and_decrement,
    restore_stock_to_shelf,
)

logger = logging.getLogger(__name__)

# Reason sabitleri (models.StockMovement.REASONS / CHECK constraint ile eşleşir)
REASON_GOODS_IN = "goods_in"
REASON_PACK_OUT = "pack_out"
REASON_SHIP_OUT = "ship_out"
REASON_CANCEL_RETURN = "cancel_return"
REASON_MANUAL = "manual_adjust"
REASON_OPENING = "opening_balance"
REASON_EXCHANGE = "exchange"
REASON_RECONCILE = "reconcile"


# ════════════════════════════════════════════════════════════════════════
# Bildirimsel geçiş → stok etkisi haritası
# (from_status, to_status) -> reason | None
#
# KRİTİK: non-Picking aktif (Created/Hazirlaniyor/None) → Shipped/Delivered =
# ship_out (FİZİKSEL DÜŞÜM). Eksik olan, hayalet stoğa yol açan geçiş buydu.
# Picking→Shipped/Delivered = None: stok zaten paketlemede (pack_out) düşmüştü.
# ════════════════════════════════════════════════════════════════════════
LIFECYCLE_EFFECTS: dict[tuple[str | None, str], str | None] = {
    # paketlemeden geçmeden kargolanan → düş
    ("Created", "Shipped"): REASON_SHIP_OUT,
    ("Created", "Delivered"): REASON_SHIP_OUT,
    ("Hazirlaniyor", "Shipped"): REASON_SHIP_OUT,
    ("Hazirlaniyor", "Delivered"): REASON_SHIP_OUT,
    # NOT: (None→Shipped/Delivered) — yani sistemde hiç görülmeden ilk kez
    # kargolanmış gelen sipariş — BİLEREK no-op. Ledger devreye girdiğinde
    # geçmiş kargolanmış siparişlerin ilk sync'inde çift düşümü önler (cutover
    # güvenliği). Asıl kronik sızıntı Created/Hazırlanıyor→Shipped'tir; o kapsanır.
    # zaten pakette düşmüştü → tekrar düşme
    ("Picking", "Shipped"): None,
    ("Picking", "Delivered"): None,
    # sadece rezervdi → iade yok
    ("Created", "Cancelled"): None,
    ("Hazirlaniyor", "Cancelled"): None,
    # pakette düşmüştü → rafa geri yükle
    ("Picking", "Cancelled"): REASON_CANCEL_RETURN,
    ("Picking", "Created"): REASON_CANCEL_RETURN,  # nadir geri-dönüş
}


@dataclass(frozen=True)
class MovementResult:
    movement_id: int | None
    applied: bool        # False => idempotency ile atlandı (hiçbir mutasyon olmadı)
    delta: int           # gerçekleşen fiziksel değişim (kısmi tahsiste istenenden farklı olabilir)
    barcode: str
    reason: str


def has_movement(idempotency_key: str) -> bool:
    """Verilen idempotency anahtarıyla bir hareket zaten yazılmış mı."""
    if not idempotency_key:
        return False
    return (
        db.session.query(StockMovement.id)
        .filter(StockMovement.idempotency_key == idempotency_key)
        .first()
        is not None
    )


def record_movement(
    *,
    barcode: str,
    delta: int,
    reason: str,
    shelf_code: str | None = None,
    order_number: str | None = None,
    idempotency_key: str | None = None,
    source: str | None = None,
    note: str | None = None,
    mutate_shelf: bool = True,
    commit: bool = True,
) -> MovementResult:
    """Tek bir stok hareketini deftere yazar (ve gerekiyorsa rafı mutasyona uğratır).

    - ``mutate_shelf=True``: ``delta<0`` raftan düşer, ``delta>0`` rafa iade eder.
      Fiziksel düşüm kısmi olabilir (yeterli stok yoksa); defter GERÇEKLEŞEN
      delta'yı kaydeder.
    - ``mutate_shelf=False``: rafı çağıran taraf zaten değiştirdi; sadece kaydet.
    - ``idempotency_key`` zaten varsa: hiçbir şey yapmaz, ``applied=False`` döner.
    """
    barcode = normalize_barcode(barcode)
    if not barcode or delta == 0:
        return MovementResult(None, False, 0, barcode or "", reason)

    if idempotency_key and has_movement(idempotency_key):
        logger.info("[LEDGER] idempotent atlandı: %s", idempotency_key)
        return MovementResult(None, False, 0, barcode, reason)

    # Raf mutasyonu + movement insert TEK bir SAVEPOINT içinde. İdempotency
    # yarışında (başka akış aynı key'i araya yazdı) yalnızca bu savepoint geri
    # alınır — DIŞ transaction (çağıranın order taşıma/delete/insert işlemleri)
    # KORUNUR. Bare db.session.rollback() tüm dış transaction'ı çökertirdi.
    row = None
    actual_delta = delta
    try:
        with db.session.begin_nested():
            note_extra = None
            if mutate_shelf:
                if delta < 0:
                    res = allocate_from_shelf_and_decrement(barcode, qty=-delta)
                    allocated = int(res.get("allocated", 0))
                    actual_delta = -allocated
                    if allocated < -delta:
                        note_extra = f"partial: requested={-delta} allocated={allocated}"
                        logger.warning(
                            "[LEDGER] kısmi çıkış %s istenen=%s tahsis=%s (ord=%s)",
                            barcode, -delta, allocated, order_number,
                        )
                    if not shelf_code and res.get("shelf_codes"):
                        shelf_code = res["shelf_codes"][0]
                elif delta > 0:
                    restore_stock_to_shelf(barcode, delta, shelf_code=shelf_code, commit=False)
                    actual_delta = delta

            row_note = f"{note} | {note_extra}" if (note and note_extra) else (note or note_extra)
            row = StockMovement(
                barcode=barcode,
                shelf_code=shelf_code,
                delta=actual_delta,
                reason=reason,
                order_number=str(order_number) if order_number else None,
                idempotency_key=idempotency_key,
                source=source,
                note=row_note,
            )
            db.session.add(row)
            # savepoint çıkışında flush edilir; IntegrityError burada fırlar.
    except IntegrityError:
        # Yarış: aynı idempotency_key araya yazıldı → yalnızca savepoint geri alındı.
        logger.info("[LEDGER] idempotency yarışı atlandı: %s", idempotency_key)
        return MovementResult(None, False, 0, barcode, reason)

    if commit:
        db.session.commit()

    return MovementResult(row.id if row else None, True, actual_delta, barcode, reason)


def _canon_status(s: str | None) -> str | None:
    """Statü etiketini kanonik forma getirir.

    Çağrı yerleri statüyü farklı biçimlerde verir: tablo adından gelen
    küçük harf ('created', 'picking', 'hazirlaniyor') ve normalize statü
    büyük harf ('Shipped', 'Delivered', 'Cancelled'). Hepsini tek forma indir.
    """
    if not s:
        return None
    return s.strip().capitalize()


def _parse_details(details) -> list[dict]:
    """details JSON'unu (str veya list) normalize edip {barcode, quantity} listesi döner."""
    if not details:
        return []
    try:
        det = json.loads(details) if isinstance(details, str) else details
    except (ValueError, TypeError):
        return []
    return det if isinstance(det, list) else []


def apply_lifecycle_effect(
    *,
    order_number: str,
    from_status: str | None,
    to_status: str,
    details,
    shelf_code: str | None = None,
    source: str = "TRENDYOL_SYNC",
    commit: bool = True,
) -> list[MovementResult]:
    """Bir statü geçişinin stok etkisini ``LIFECYCLE_EFFECTS`` haritasından uygular.

    Harita ``None`` döndürürse (veya anahtar yoksa) hiçbir şey yapmaz — güvenli no-op.
    İdempotency anahtarı: ``"{order}:{from}->{to}:{barcode}:{reason}"`` — aynı geçiş
    tekrar beslense bile (3 saatlik reconcile) çift düşüm/iade olmaz.
    """
    cfrom = _canon_status(from_status)
    cto = _canon_status(to_status)
    reason = LIFECYCLE_EFFECTS.get((cfrom, cto), None)
    if reason is None:
        return []

    items = _parse_details(details)
    if not items:
        return []

    sign = -1 if reason in (REASON_SHIP_OUT, REASON_PACK_OUT) else 1
    results: list[MovementResult] = []

    for it in items:
        bc = it.get("barcode")
        qty = int(it.get("quantity") or 1)
        if not bc or qty <= 0:
            continue
        norm = normalize_barcode(bc)
        idem = f"{order_number}:{cfrom or 'NEW'}->{cto}:{norm}:{reason}"
        results.append(
            record_movement(
                barcode=bc,
                delta=sign * qty,
                reason=reason,
                shelf_code=shelf_code,
                order_number=order_number,
                idempotency_key=idem,
                source=source,
                note=f"{from_status or 'NEW'}→{to_status}",
                mutate_shelf=True,
                commit=False,
            )
        )

    if commit:
        db.session.commit()

    return results
