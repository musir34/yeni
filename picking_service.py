"""Manuel raf-okutmalı toplama — ortak düşüm yardımcısı.

İki ekran (toplu `/pick` ve tekli sıralı-açık `confirm_packing`) buradan geçer.
Çalışanın okuttuğu RAFTAN siparişin ürününü fiziksel düşer, ledger'a pack_out
yazar ve siparişi 'toplandı' damgalar. `toplandi_at` doluysa idempotent atlar.

Tasarım: TEK düşüm noktası (DRY) — böylece "okutulan raftan düş" mantığı tek yerde.
"""
from __future__ import annotations

import logging
from datetime import datetime

from models import db, RafUrun
from barcode_alias_helper import normalize_barcode
from stock_management import sync_central_stock
from stock_ledger import record_movement, REASON_PACK_OUT

logger = logging.getLogger(__name__)


def pick_order_from_shelf(
    *,
    order,
    barcode: str,
    raf_kodu: str,
    qty: int = 1,
    source: str = "USER",
    commit: bool = True,
) -> dict:
    """Okutulan raftan düş + 'toplandı' damgala.

    Returns: {"success": bool, "error": str | None, "already": bool}
    Yan etki (başarılıysa): RafUrun.adet düşer, pack_out ledger yazılır,
    order.toplandi_at/toplandi_raf doldurulur.
    """
    bc = normalize_barcode((barcode or "").strip())
    raf_kodu = (raf_kodu or "").strip()
    if not bc:
        return {"success": False, "error": "Geçersiz ürün barkodu.", "already": False}
    if not raf_kodu:
        return {"success": False, "error": "Raf kodu okutulmadı.", "already": False}
    if qty <= 0:
        return {"success": False, "error": "Geçersiz adet.", "already": False}

    # Idempotency: zaten toplanmışsa tekrar düşme.
    if getattr(order, "toplandi_at", None):
        return {"success": True, "error": None, "already": True}

    # Ürün siparişle eşleşiyor mu? (tek-ürünlü; product_barcode'un ilk barkodunu karşılaştır)
    order_bc = normalize_barcode(
        (getattr(order, "product_barcode", "") or "").split(",")[0].strip()
    )
    if order_bc and order_bc != bc:
        return {"success": False, "error": "Okutulan ürün bu siparişle eşleşmiyor.", "already": False}

    # Okutulan rafta bu üründen yeterli var mı?
    rec = (RafUrun.query
           .filter_by(raf_kodu=raf_kodu, urun_barkodu=bc)
           .with_for_update()
           .first())
    if not rec or (rec.adet or 0) < qty:
        mevcut = (rec.adet or 0) if rec else 0
        return {
            "success": False,
            "error": f"{raf_kodu} rafında {bc} ürününden yeterli yok (var: {mevcut}, gerekli: {qty}).",
            "already": False,
        }

    # Düş + ledger + damga (aynı transaction)
    rec.adet = (rec.adet or 0) - qty
    db.session.flush()
    record_movement(
        barcode=bc, delta=-qty, reason=REASON_PACK_OUT, shelf_code=raf_kodu,
        order_number=order.order_number, idempotency_key=f"{order.order_number}:pick:{bc}",
        source=source, mutate_shelf=False, commit=False,
    )
    sync_central_stock(bc, commit=False)
    order.toplandi_at = datetime.utcnow()
    order.toplandi_raf = raf_kodu

    logger.info("[PICK] %s · %s rafından %s × %s düşüldü (toplandı)", order.order_number, raf_kodu, bc, qty)

    if commit:
        db.session.commit()
    return {"success": True, "error": None, "already": False}
