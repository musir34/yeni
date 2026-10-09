"""
Soru-Cevap kartında soruyu soranın Trendyol siparişleri.

Soru API'si sipariş numarası vermez; ortak anahtar Trendyol hesap kimliği
(customerId). Sipariş senkronu her paket için (sipariş no → customerId) eşlemesini
`trendyol_siparis_musteri` tablosuna yazar (order_service.process_all_orders).
Kart; eşlemeden sipariş numaralarını, sipariş tablolarından da kalemleri
(görsel, model kodu, renk, beden, barkod) ve alıcı adı/adresini okur.

Model kodu sipariş satırındaki product_main_id'den ALINMAZ (orada contentId var);
barkoddan products.product_main_id okunur.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from flask import current_app

from models import (db, Archive, OrderArchived, OrderCancelled, OrderCreated, OrderDelivered,
                    OrderHazirlaniyor, OrderPicking, OrderReadyToShip, OrderShipped, Product,
                    TrendyolSiparisMusteri)
from time_utils import ist_to_utc

logger = logging.getLogger(__name__)

MUSTERI_SIPARIS_AZAMI = 10   # kartta müşteri başına gösterilen en fazla sipariş
_PARCA = 500                 # toplu yazma/okuma parça boyu

SIPARIS_TABLOLARI = [
    (OrderCreated, "Yeni"),
    (OrderHazirlaniyor, "Hazırlanıyor"),
    (OrderPicking, "Paketlendi"),
    (OrderReadyToShip, "Gönderime Hazır"),
    (OrderShipped, "Kargoda"),
    (OrderDelivered, "Teslim Edildi"),
    (OrderCancelled, "İptal"),
    (OrderArchived, "Arşiv"),
    (Archive, "Arşiv"),
]

# Yalnız bu kolonlar seçilir: arşiv tablolarına tam entity select YASAK (prod'da eksik kolon var).
KOLONLAR = ("order_number", "package_number", "order_date", "customer_name", "customer_surname", "customer_address",
            "product_barcode", "product_color", "product_size", "product_name", "quantity", "details")


def _epoch_utc(ms) -> datetime | None:
    # Trendyol orderDate İstanbul duvar saatini kodlar (order_service.combine_line_items ile aynı)
    try:
        return ist_to_utc(datetime.utcfromtimestamp(float(ms) / 1000.0)) if ms else None
    except (TypeError, ValueError, OverflowError):
        return None


def eslemeleri_cikar(paketler) -> list[dict]:
    """API paketlerinden (sipariş no, customerId, tarih) satırları; sipariş no başına bir kez."""
    gorulen: dict[str, dict] = {}
    for p in paketler or []:
        if not isinstance(p, dict):
            continue
        no = str(p.get("orderNumber") or "").strip()
        try:
            musteri = int(p.get("customerId") or 0)
        except (TypeError, ValueError):
            musteri = 0
        if not no or not musteri or no in gorulen:
            continue
        gorulen[no] = {"order_number": no[:50], "customer_id": musteri,
                       "order_date": _epoch_utc(p.get("orderDate")), "created_at": datetime.utcnow()}
    return list(gorulen.values())


def musteri_siparislerini_kaydet(paketler) -> int:
    """Eşlemeleri yazar (var olan sipariş no'ya dokunmaz). Senkron oturumundan ayrı bağlantı kullanır.

    Hata senkronu durdurmaz: loglanır, 0 döner.
    """
    satirlar = eslemeleri_cikar(paketler)
    if not satirlar:
        return 0
    tablo = TrendyolSiparisMusteri.__table__
    try:
        if db.engine.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        with db.engine.begin() as conn:
            for i in range(0, len(satirlar), _PARCA):
                conn.execute(insert(tablo).values(satirlar[i:i + _PARCA])
                             .on_conflict_do_nothing(index_elements=["order_number"]))
        return len(satirlar)
    except Exception:
        logger.exception("[QNA-SIPARIS] müşteri-sipariş eşlemesi yazılamadı")
        return 0


def musteri_siparis_nolari(customer_ids) -> dict[int, list[str]]:
    """Müşteri başına sipariş numaraları, yeniden eskiye (en fazla MUSTERI_SIPARIS_AZAMI)."""
    ids = {int(c) for c in customer_ids if c}
    if not ids:
        return {}
    try:
        rows = (db.session.query(TrendyolSiparisMusteri.customer_id, TrendyolSiparisMusteri.order_number)
                .filter(TrendyolSiparisMusteri.customer_id.in_(ids))
                .order_by(TrendyolSiparisMusteri.order_date.desc().nullslast())
                .all())
    except Exception:
        db.session.rollback()
        logger.exception("[QNA-SIPARIS] eşleme okunamadı (tablo yok olabilir)")
        return {}
    sonuc: dict[int, list[str]] = {}
    for cid, no in rows:
        grup = sonuc.setdefault(cid, [])
        if len(grup) < MUSTERI_SIPARIS_AZAMI:
            grup.append(no)
    return sonuc


def _virgul(deger) -> list[str]:
    return [p.strip() for p in str(deger or "").split(",")]


def _satir_kalemleri(r) -> list[dict]:
    """Sipariş satırının kalemleri: details JSON'u, yoksa virgüllü kolonlar."""
    try:
        detay = json.loads(getattr(r, "details", None) or "[]")
    except (TypeError, ValueError):
        detay = []
    if isinstance(detay, list) and detay:
        return [{"barkod": str(d.get("barcode") or ""), "renk": d.get("color") or "",
                 "beden": d.get("size") or "", "urun": d.get("productName") or "",
                 "adet": d.get("quantity")} for d in detay if isinstance(d, dict)]
    barkodlar = _virgul(getattr(r, "product_barcode", ""))
    renkler, bedenler = _virgul(getattr(r, "product_color", "")), _virgul(getattr(r, "product_size", ""))
    adlar = _virgul(getattr(r, "product_name", ""))
    tek = len(barkodlar) == 1
    return [{"barkod": b, "renk": renkler[i] if i < len(renkler) else "",
             "beden": bedenler[i] if i < len(bedenler) else "",
             "urun": adlar[i] if i < len(adlar) else "",
             "adet": getattr(r, "quantity", None) if tek else None}
            for i, b in enumerate(barkodlar) if b]


def _siparis_satirlari(order_numbers: list[str]) -> list[tuple[object, str]]:
    bulunan = []
    for model, etiket in SIPARIS_TABLOLARI:
        kolonlar = [getattr(model, k) for k in KOLONLAR if hasattr(model, k)]
        for i in range(0, len(order_numbers), _PARCA):
            try:
                rows = (db.session.query(*kolonlar)
                        .filter(model.order_number.in_(order_numbers[i:i + _PARCA])).all())
            except Exception:
                db.session.rollback()
                logger.warning("[QNA-SIPARIS] %s okunamadı", model.__tablename__, exc_info=True)
                break
            bulunan.extend((r, etiket) for r in rows)
    return bulunan


def _urun_bilgileri(barkodlar: set[str]) -> dict[str, tuple[str, str]]:
    """barkod → (model kodu, görsel adresi). Görsel: products.images ilk URL, yoksa static/images/<barkod>."""
    sonuc: dict[str, tuple[str, str]] = {}
    if not barkodlar:
        return sonuc
    try:
        rows = (db.session.query(Product.barcode, Product.product_main_id, Product.images)
                .filter(Product.barcode.in_(list(barkodlar))).all())
    except Exception:
        db.session.rollback()
        logger.warning("[QNA-SIPARIS] ürün bilgisi okunamadı", exc_info=True)
        rows = []
    klasor = os.path.join(current_app.root_path, "static", "images")
    bilinen = {bc: (model or "", (images or "").split(",")[0].strip()) for bc, model, images in rows}
    for bc in barkodlar:
        model, gorsel = bilinen.get(bc, ("", ""))
        if not gorsel.startswith("http"):
            gorsel = next((f"/static/images/{bc}{u}" for u in (".jpg", ".jpeg", ".png")
                           if os.path.exists(os.path.join(klasor, f"{bc}{u}"))), "")
        sonuc[bc] = (model, gorsel)
    return sonuc


def siparis_ozetleri(order_numbers, tarih_bicimle) -> dict[str, dict]:
    """sipariş no → {tarih, durum, alici, adres, kalemler[görsel, model, renk, beden, barkod, adet]}.

    Panele hiç düşmemiş sipariş sonuçta yer almaz.
    """
    nolar = sorted({str(n) for n in order_numbers if n})
    if not nolar:
        return {}
    satirlar = _siparis_satirlari(nolar)
    ozet: dict[str, dict] = {}
    for r, etiket in satirlar:
        o = ozet.setdefault(r.order_number, {
            "no": r.order_number, "tarih": tarih_bicimle(getattr(r, "order_date", None)),
            "durumlar": [], "paketler": set(), "alici": "", "adres": "", "kalemler": []})
        if etiket not in o["durumlar"]:
            o["durumlar"].append(etiket)
        if not o["alici"]:
            o["alici"] = f"{getattr(r, 'customer_name', '') or ''} {getattr(r, 'customer_surname', '') or ''}".strip()
        if not o["adres"]:
            o["adres"] = getattr(r, "customer_address", "") or ""
        # Bölünmüş siparişte her paket ayrı satırdır; aynı paket iki tabloda (ör. arşiv kopyası) bir kez sayılır
        paket = getattr(r, "package_number", None) or r.order_number
        if paket not in o["paketler"]:
            o["paketler"].add(paket)
            o["kalemler"].extend(_satir_kalemleri(r))
    urunler = _urun_bilgileri({k["barkod"] for o in ozet.values() for k in o["kalemler"] if k["barkod"]})
    for o in ozet.values():
        o["durum"] = ", ".join(o.pop("durumlar"))
        o.pop("paketler")
        for k in o["kalemler"]:
            k["model"], k["gorsel"] = urunler.get(k["barkod"], ("", ""))
    return ozet
