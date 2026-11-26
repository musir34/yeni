"""Tek adet raf teyidi — merkezi stoğu tam 1 olan barkodun platforma gönderim kuralı.

SORUN
-----
Kayıtta 1 adet görünen ama rafta bulunmayan ürün satılıyor, sipariş "tedarik
edilemedi" diye arşive düşüyordu.

KURAL
-----
``central_stock.qty == 1`` olan barkod, biri rafa bakıp /tek-adet-teyit sayfasında
"Var" diyene kadar platformlara 0 gider. Teyitliyse ``max(0, 1 - rezerv)`` gider
(güvenlik/ekstra tampon bu tek adette uygulanmaz — insan teyit etti). qty != 1
olan barkodlarda ve Üretim Modu barkodlarında mevcut formül AYNEN kalır.

Teyit geçerli ⇔ qty == 1 VE teyit kaydı var VE teyit_at >= central_stock.updated_at.
central_stock.updated_at yalnız qty değişince ilerler → stok değişince teyit düşer.

Aynı kural üç yerde birebir uygulanır (yoksa monitör sahte alarm üretir):
stock_sync.service (_get_all_stocks / _get_stocks_by_barcodes), Shopify push_stock,
health_monitor.check_sync_staleness.

models bu modülde fonksiyon içinde import edilir → saf fonksiyonlar app'siz test edilir.
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def teyit_gecerli(qty, updated_at: datetime | None, teyit_at: datetime | None) -> bool:
    """qty == 1 VE teyit var VE teyit stok son değiştikten sonra (ya da aynı anda) verilmiş."""
    if qty != 1 or teyit_at is None:
        return False
    return updated_at is None or teyit_at >= updated_at


def tek_adet_miktari(raw_qty, reserved: int, normal_qty: int, teyitli: bool, muaf: bool) -> int:
    """Platforma gidecek adet. qty != 1 ya da muaf (üretim modu) → normal formül aynen."""
    if muaf or raw_qty != 1:
        return normal_qty
    return max(0, 1 - (reserved or 0)) if teyitli else 0


def teyit_kumeleri() -> tuple[set[str], set[str]]:
    """(teyitli barkodlar, kuraldan muaf üretim modu barkodları).

    Hata → teyitli boş küme (güvenli taraf: tek adetler 0 gider), senkron durmaz.
    """
    from models import db, CentralStock, StokTeyit
    try:
        rows = (db.session.query(StokTeyit.barcode, CentralStock.qty,
                                 CentralStock.updated_at, StokTeyit.teyit_at)
                .join(CentralStock, CentralStock.barcode == StokTeyit.barcode)
                .filter(CentralStock.qty == 1)
                .all())
        teyitli = {bc for bc, qty, upd, tey in rows if teyit_gecerli(qty, upd, tey)}
    except Exception:
        logger.exception("[TEK-ADET] teyitler okunamadı (yutuldu, tek adetler 0 gider)")
        db.session.rollback()
        teyitli = set()
    try:
        from uretim_modu import get_uretim_barcodes
        muaf = get_uretim_barcodes()
    except Exception:
        logger.exception("[TEK-ADET] üretim barkodları okunamadı (yutuldu)")
        muaf = set()
    return teyitli, muaf
