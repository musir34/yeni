"""Sipariş Takip (eski adı Sipariş Zaman Çizgisi) — tek bakışta "ne zaman ne oldu" sayfası.

Eski /siparis-iz sayfası tüm audit kayıtlarını (4 dakikada bir tekrarlayan
AUTO_HEAL satırları dahil) ham döker; bu sayfa aynı kaynaklardan yalnızca
anlamlı kilometre taşlarını çıkarır ve İstanbul saatiyle kronolojik dizer.

Kaynaklar (hepsi naive UTC saklar, gösterim fmt_ist ile):
  * orders_* tabloları (order_date, hazirlaniyor_since, toplandi_at, picking_start_time,
    shipping_time, cancellation_date, archive_date)
  * uretim_siparis (isleme_alindi_at, uretildi_at, paketlendi_at, hazirlayan)
  * order_audit_logs (status_changed / order_picked / order_archived / ... — gürültü hariç)
  * user_logs (etiket yazdırma, sipariş hazırlandı, üretim adımları — kullanıcı adıyla)
  * stock_movement (raftan düşüm / iade)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import or_

from models import (
    OrderArchived,
    OrderAuditLog,
    OrderCancelled,
    OrderCreated,
    OrderDelivered,
    OrderHazirlaniyor,
    OrderPicking,
    OrderReadyToShip,
    OrderShipped,
    SiparisNotu,
    StockMovement,
    UretimSiparis,
    User,
    UserLog,
    db,
)
from time_utils import fmt_ist, to_ist
from user_logs import log_user_action

logger = logging.getLogger(__name__)
siparis_zaman_bp = Blueprint("siparis_zaman", __name__)

# Aynı adımın (ör. "Paketlendi") hem audit hem user_log hem tablo kaydından gelmesi normal;
# bu pencere içinde tekrar edenler tek satıra indirilir.
TEKRAR_PENCERESI = timedelta(seconds=5)

# Gürültü: her senkronda yeniden yazılan, sipariş akışında kilometre taşı olmayan kayıtlar.
AUDIT_GURULTU = {"order_received", "warning", "raf_changed", "stock_changed"}

AUDIT_KAYNAK = {
    "TRENDYOL_SYNC": "Trendyol senkron",
    "AUTO_PROMOTE": "Otomatik",
    "AUTO_HEAL": "Otomatik",
    "JOB": "Arka plan",
    "SYSTEM": "Sistem",
    "USER": "Kullanıcı",
}

STATU_ADIM = {
    "created": ("panel", "Yeni sipariş olarak panele alındı"),
    "hazirlaniyor": ("hazirlaniyor", "Hazırlanıyor'a alındı (stok teyit edildi)"),
    "picking": ("hazirlandi", "Paketlendi (Picking)"),
    "readytoship": ("hazirlandi", "Gönderime hazır"),
    "shipped": ("kargoda", "Kargoya verildi"),
    "delivered": ("teslim", "Teslim edildi"),
    "cancelled": ("iptal", "İptal edildi"),
    "archived": ("arsiv", "Arşivlendi"),
}

LEDGER_SEBEP = {
    "pack_out": "Paketlemede raftan düşüldü",
    "ship_out": "Kargoya çıkışta raftan düşüldü",
    "cancel_return": "İptal — rafa geri alındı",
    "exchange": "Değişim hareketi",
    "manual_adjust": "Manuel stok düzeltmesi",
    "goods_in": "Rafa giriş",
    "reconcile": "Stok mutabakatı",
    "opening_balance": "Açılış bakiyesi",
}

# Özet şeridindeki adımlar (sırayla). Üretim adımları yalnızca üretim kaydı varsa gösterilir.
OZET_ADIMLAR = [
    ("siparis", "Sipariş verildi"),
    ("panel", "Panele düştü"),
    ("hazirlaniyor", "Hazırlanıyor"),
    ("uretim_basladi", "Üretim başladı"),
    ("uretildi", "Üretildi"),
    ("hazirlandi", "Paketlendi"),
    ("etiket", "Etiket / Kargo kodu"),
    ("kargoda", "Kargoya verildi"),
    ("teslim", "Teslim edildi"),
    ("iptal", "İptal"),
    ("arsiv", "Arşiv"),
]
ISTEGE_BAGLI_ADIMLAR = {"uretim_basladi", "uretildi", "iptal", "arsiv"}

ADIM_RENK = {
    "siparis": "primary", "panel": "secondary", "hazirlaniyor": "info",
    "uretim_kayit": "purple", "uretim_basladi": "purple", "uretildi": "purple", "paketlendi": "success",
    "hazirlandi": "success", "etiket": "dark", "kargoda": "warning", "teslim": "success",
    "iptal": "danger", "arsiv": "secondary", "stok": "muted", "raf": "muted",
    "not": "info", "hata": "danger", "diger": "muted",
}


@dataclass
class Olay:
    ts: datetime | None          # naive UTC
    adim: str
    baslik: str
    detay: str = ""
    kim: str = ""
    kaynak: str = ""

    def gorunum(self) -> dict:
        d = to_ist(self.ts)
        return {
            "tarih": d.strftime("%d.%m.%Y") if d else "",
            "saat": d.strftime("%H:%M:%S") if d else "",
            "adim": self.adim,
            "renk": ADIM_RENK.get(self.adim, "muted"),
            "baslik": self.baslik,
            "detay": self.detay,
            "kim": self.kim,
            "kaynak": self.kaynak,
        }


# ─────────────────────────────── saf mantık (testlenir) ───────────────────────────────

def kucuk(metin: str) -> str:
    """Türkçe güvenli küçültme: str.lower() 'İ'yi noktalı i̇ yapar, 'işleme' eşleşmez."""
    return (metin or "").replace("İ", "i").replace("I", "ı").lower()


def user_log_adimi(aciklama: str) -> str:
    """user_logs 'Işlem Açıklaması' metnini özet adımına eşler."""
    a = kucuk(aciklama)
    if ("etiket" in a and "yazdır" in a) or "kargo kodu verildi" in a:
        return "etiket"
    if "işleme alındı" in a:
        return "uretim_basladi"
    if "üretildi olarak" in a:
        return "uretildi"
    if "paketlendi" in a:
        return "paketlendi"
    if "sipariş hazırlandı" in a:
        return "hazirlandi"
    if "→ hazirlaniyor" in a or "→ hazırlanıyor" in a:
        return "hazirlaniyor"
    if "→ kargoda" in a or "karşılandı" in a:
        return "kargoda"
    if "→ teslim" in a:
        return "teslim"
    if "iptal" in a:
        return "iptal"
    if "başarısız" in a:
        return "hata"
    if "arşiv" in a:
        return "arsiv"
    return "diger"


SHOPIFY_ID_EN_AZ = 13   # Shopify iç sipariş kimliği (18929721835698); Trendyol sipariş no 10-11 hane
SHOPIFY_AD_EN_COK = 6   # mağazadaki görünür sipariş adı (#1428) kısadır


def girdi_turu(girdi: str) -> tuple[str, str]:
    """Aranan numaranın türü: ('shopify_id', '1893…') | ('shopify_ad', '1428') | ('trendyol', '1168…').

    'SH-' öneki ya da ≥13 haneli rakam → Shopify iç kimliği; ≤6 haneli rakam → site sipariş adı;
    gerisi Trendyol sipariş/paket numarası olarak aranır.
    """
    ham = (girdi or "").strip().lstrip("#").strip()
    sh = ham[:3].upper() == "SH-" or ham[:2].upper() == "SH"
    if sh:
        ham = ham[3:] if ham[:3].upper() == "SH-" else ham[2:]
        ham = ham.strip().lstrip("-").lstrip("#").strip()
    if ham.isdigit() and len(ham) <= SHOPIFY_AD_EN_COK:
        return "shopify_ad", ham          # 'SH-1428' de sipariş adıdır (değişim ekranıyla aynı kabul)
    if ham.isdigit() and (sh or len(ham) >= SHOPIFY_ID_EN_AZ):
        return "shopify_id", ham
    return "trendyol", ham


def _iso_utc(deger) -> datetime | None:
    """Shopify ISO zamanı (…Z / +03:00) → naive UTC (DB konvansiyonu)."""
    if not deger or not isinstance(deger, str):
        return None
    try:
        dt = datetime.fromisoformat(deger.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def shopify_olaylari(order: dict) -> list[Olay]:
    """Shopify sipariş kaydından adımlar: sipariş verildi, iptal, kargoya verildi (fulfillment)."""
    olaylar: list[Olay] = []
    ts = _iso_utc(order.get("createdAt"))
    if ts:
        olaylar.append(Olay(ts, "siparis", "Sipariş verildi (site)", kaynak="Shopify"))
    ts = _iso_utc(order.get("cancelledAt"))
    if ts:
        olaylar.append(Olay(ts, "iptal", "İptal edildi (site)", detay=order.get("cancelReason") or "", kaynak="Shopify"))
    for f in order.get("fulfillments") or []:
        ts = _iso_utc(f.get("createdAt"))
        if not ts:
            continue
        takip = [t for t in (f.get("trackingInfo") or []) if t]
        detay = " · ".join(p for p in ((takip[0].get("company") if takip else ""), (takip[0].get("number") if takip else "")) if p)
        olaylar.append(Olay(ts, "kargoda", "Kargoya verildi (Shopify kayıt)", detay=detay, kaynak="Shopify"))
    return olaylar


def olaylari_birlestir(olaylar: list[Olay]) -> list[Olay]:
    """Kronolojik sırala; aynı adım birkaç saniye içinde tekrar ediyorsa tek satıra indir.

    Tekrar eden kayıt atılırken ilk kayıttaki boş 'kim'/'detay' alanları atılandan doldurulur
    (ör. audit satırında kullanıcı yok, user_log satırında var).
    """
    sirali = sorted((o for o in olaylar if o.ts is not None), key=lambda o: o.ts)
    sonuc: list[Olay] = []
    for o in sirali:
        es = next(
            (k for k in reversed(sonuc)
             if k.adim == o.adim and o.ts - k.ts <= TEKRAR_PENCERESI
             and (o.adim != "stok" or k.detay == o.detay)),
            None,
        )
        if es is None:
            sonuc.append(o)
            continue
        if not es.kim:
            es.kim = o.kim
        if not es.detay:
            es.detay = o.detay
        if es.kaynak in ("", "Otomatik", "Kullanıcı") and o.kaynak:
            es.kaynak = o.kaynak
    return sonuc


def ozet_adimlar(olaylar: list[Olay], gizle: set[str] | None = None) -> list[dict]:
    """Özet şeridi: her adımın İLK zamanı. Üretim/iptal/arşiv adımları yalnızca varsa; `gizle` hiç gösterilmez."""
    ilk: dict[str, datetime] = {}
    for o in olaylar:
        if o.ts is None:
            continue
        anahtar = "hazirlandi" if o.adim == "paketlendi" else o.adim
        if anahtar not in ilk or o.ts < ilk[anahtar]:
            ilk[anahtar] = o.ts
    satirlar = []
    for anahtar, etiket in OZET_ADIMLAR:
        if gizle and anahtar in gizle:
            continue
        ts = ilk.get(anahtar)
        if ts is None and anahtar in ISTEGE_BAGLI_ADIMLAR:
            continue
        d = to_ist(ts)
        satirlar.append({
            "anahtar": anahtar,
            "etiket": etiket,
            "tarih": d.strftime("%d.%m.%Y") if d else "",
            "saat": d.strftime("%H:%M") if d else "",
            "var": ts is not None,
            "renk": ADIM_RENK.get(anahtar, "muted"),
        })
    return satirlar


def sure_metni(bas: datetime | None, son: datetime | None) -> str:
    if not bas or not son or son < bas:
        return ""
    toplam = int((son - bas).total_seconds() // 60)
    gun, kalan = divmod(toplam, 1440)
    saat, dk = divmod(kalan, 60)
    parcalar = []
    if gun:
        parcalar.append(f"{gun} gün")
    if saat:
        parcalar.append(f"{saat} sa")
    parcalar.append(f"{dk} dk")
    return " ".join(parcalar)


# ─────────────────────────────── veri toplama ───────────────────────────────

ORDER_TABLES = [
    (OrderCreated, "Yeni"),
    (OrderHazirlaniyor, "Hazırlanıyor"),
    (OrderPicking, "Paketlendi"),
    (OrderReadyToShip, "Gönderime Hazır"),
    (OrderShipped, "Kargoda"),
    (OrderDelivered, "Teslim Edildi"),
    (OrderCancelled, "İptal"),
    (OrderArchived, "Arşiv"),
]


ARSIV_KOLONLAR = (
    "order_number", "package_number", "status", "order_date", "created_at",
    "customer_name", "customer_surname", "product_name", "merchant_sku", "product_size",
    "product_color", "product_barcode", "quantity", "cargo_provider_name",
    "cargo_tracking_number", "agreed_delivery_date", "archive_date", "archive_reason",
)


def _siparis_satirlari(needles: list[str]) -> list[tuple[object, str]]:
    bulunan = []
    for model, etiket in ORDER_TABLES:
        try:
            if model is OrderArchived:
                # orders_archived'a tam entity select YASAK: prod'da stockCode kolonu yok.
                q = db.session.query(*(getattr(OrderArchived, k) for k in ARSIV_KOLONLAR))
            else:
                q = db.session.query(model)
            rows = q.filter(or_(model.order_number.in_(needles), model.package_number.in_(needles))).all()
        except Exception:
            db.session.rollback()
            logger.warning("siparis_zaman: %s okunamadı", model.__tablename__, exc_info=True)
            continue
        bulunan.extend((r, etiket) for r in rows)
    return bulunan


def _tablo_olaylari(satirlar: list[tuple[object, str]]) -> list[Olay]:
    olaylar: list[Olay] = []
    order_dates = [r.order_date for r, _ in satirlar if getattr(r, "order_date", None)]
    if order_dates:
        olaylar.append(Olay(min(order_dates), "siparis", "Sipariş verildi", kaynak="Trendyol"))
    for r, etiket in satirlar:
        if etiket == "Arşiv":
            if r.archive_date:
                olaylar.append(Olay(r.archive_date, "arsiv", "Arşivlendi", detay=r.archive_reason or ""))
        elif isinstance(r, OrderHazirlaniyor):
            if r.hazirlaniyor_since:
                olaylar.append(Olay(r.hazirlaniyor_since, "hazirlaniyor", "Hazırlanıyor'a alındı (stok teyit edildi)", kaynak="Otomatik"))
            if r.toplandi_at:
                olaylar.append(Olay(r.toplandi_at, "hazirlandi", "Raftan toplandı", detay=f"Raf {r.toplandi_raf}" if r.toplandi_raf else ""))
        elif isinstance(r, OrderPicking) and r.picking_start_time:
            olaylar.append(Olay(r.picking_start_time, "hazirlandi", "Paketlendi (Picking)", kim=r.picked_by or ""))
        elif isinstance(r, OrderShipped) and r.shipping_time:
            olaylar.append(Olay(r.shipping_time, "kargoda", "Kargoya verildi", kaynak="Trendyol senkron"))
        elif isinstance(r, OrderDelivered) and r.created_at:
            olaylar.append(Olay(r.created_at, "teslim", "Teslim edildi", kaynak="Trendyol senkron"))
        elif isinstance(r, OrderCancelled) and r.cancellation_date:
            olaylar.append(Olay(r.cancellation_date, "iptal", "İptal edildi", detay=r.cancellation_reason or ""))
    return olaylar


def _uretim_olaylari(needles: list[str]) -> list[Olay]:
    olaylar: list[Olay] = []
    try:
        rows = db.session.query(UretimSiparis).filter(
            or_(UretimSiparis.order_number.in_(needles), UretimSiparis.package_number.in_(needles))
        ).all()
    except Exception:
        db.session.rollback()
        return olaylar
    for u in rows:
        kim = u.hazirlayan or ""
        if u.created_at:
            olaylar.append(Olay(u.created_at, "uretim_kayit", "Üretim siparişi açıldı (rafta stok yok)", kaynak="Otomatik"))
        if u.isleme_alindi_at:
            olaylar.append(Olay(u.isleme_alindi_at, "uretim_basladi", "Üretim başladı (işleme alındı)"))
        if u.uretildi_at:
            olaylar.append(Olay(u.uretildi_at, "uretildi", "Üretildi", kim=kim))
        if u.paketlendi_at:
            olaylar.append(Olay(u.paketlendi_at, "paketlendi", "Paketlendi — kargoya verilmeyi bekliyor", kim=kim))
    return olaylar


def _kullanici_adlari(ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    try:
        return {u.id: u.username for u in db.session.query(User).filter(User.id.in_(ids)).all()}
    except Exception:
        db.session.rollback()
        return {}


def _audit_olaylari(needles: list[str]) -> list[Olay]:
    try:
        rows = (
            db.session.query(OrderAuditLog)
            .filter(or_(OrderAuditLog.order_number.in_(needles), OrderAuditLog.package_number.in_(needles)))
            .filter(~OrderAuditLog.event_type.in_(AUDIT_GURULTU))
            .order_by(OrderAuditLog.ts.asc())
            .limit(500)
            .all()
        )
    except Exception:
        db.session.rollback()
        return []
    adlar = _kullanici_adlari({r.user_id for r in rows if r.user_id})
    olaylar: list[Olay] = []
    raf_atandi = False
    for r in rows:
        kim = adlar.get(r.user_id, "") if r.user_id else ""
        kaynak = AUDIT_KAYNAK.get(r.source or "", r.source or "")
        et = r.event_type
        if et == "status_changed":
            adim, baslik = STATU_ADIM.get((r.status_to or "").lower(), ("diger", f"Durum: {r.status_from} → {r.status_to}"))
            olaylar.append(Olay(r.ts, adim, baslik, kim=kim, kaynak=kaynak))
        elif et == "order_picked":
            olaylar.append(Olay(r.ts, "hazirlandi", "Paketlendi", detay=f"Raf {r.raf_kodu}" if r.raf_kodu else "", kim=kim, kaynak=kaynak))
        elif et == "stock_decremented":
            olaylar.append(Olay(r.ts, "stok", "Raftan düşüldü", detay=f"{r.barcode} · {r.raf_kodu or '-'} · {r.quantity or 1} adet", kim=kim))
        elif et == "order_archived":
            olaylar.append(Olay(r.ts, "arsiv", "Arşivlendi", detay=r.message or "", kim=kim, kaynak=kaynak))
        elif et == "order_cancelled":
            olaylar.append(Olay(r.ts, "iptal", "İptal edildi", detay=r.message or "", kim=kim, kaynak=kaynak))
        elif et == "raf_assigned":
            if not raf_atandi:
                raf_atandi = True
                olaylar.append(Olay(r.ts, "raf", "Raf atandı", detay=r.raf_kodu or "", kaynak=kaynak))
        elif et == "manual_note":
            olaylar.append(Olay(r.ts, "not", "Not", detay=r.message or "", kim=kim))
        else:
            olaylar.append(Olay(r.ts, "diger", et, detay=r.message or "", kim=kim, kaynak=kaynak))
    return olaylar


def _user_log_olaylari(needles: list[str]) -> list[Olay]:
    try:
        rows = (
            db.session.query(UserLog)
            .filter(or_(*[UserLog.details.like(f"%{n}%") for n in needles]))
            .filter(~UserLog.action.like("PAGE_VIEW%"))
            .order_by(UserLog.timestamp.asc())
            .limit(200)
            .all()
        )
    except Exception:
        db.session.rollback()
        return []
    adlar = _kullanici_adlari({u.user_id for u in rows if u.user_id})
    olaylar: list[Olay] = []
    for u in rows:
        try:
            d = json.loads(u.details or "{}")
        except Exception:
            d = {}
        aciklama = (d.get("Işlem Açıklaması") or d.get("İşlem Açıklaması") or "").strip()
        if not aciklama:
            continue
        detay_parcalari = [p for p in (d.get("Sayfa"), d.get("Kargo Firması"), d.get("Kargo Kodu")) if p]
        olaylar.append(Olay(
            u.timestamp, user_log_adimi(aciklama), aciklama,
            detay=" · ".join(detay_parcalari),
            kim=d.get("Kullanıcı") or adlar.get(u.user_id, ""), kaynak="Kullanıcı",
        ))
    return olaylar


def _ledger_olaylari(needles: list[str]) -> list[Olay]:
    try:
        rows = (
            db.session.query(StockMovement)
            .filter(StockMovement.order_number.in_(needles))
            .order_by(StockMovement.created_at.asc())
            .limit(100)
            .all()
        )
    except Exception:
        db.session.rollback()
        return []
    return [
        Olay(
            m.created_at, "stok",
            LEDGER_SEBEP.get(m.reason, m.reason),
            detay=f"{m.barcode} · {m.shelf_code or '-'} · {m.delta:+d}",
            kaynak=AUDIT_KAYNAK.get(m.source or "", m.source or ""),
        )
        for m in rows
    ]


def _siparis_ozeti(satirlar: list[tuple[object, str]]) -> dict | None:
    if not satirlar:
        return None
    ilk, _ = satirlar[0]
    kalemler = [
        {
            "urun": getattr(r, "product_name", "") or getattr(r, "merchant_sku", "") or "",
            "beden": getattr(r, "product_size", "") or "",
            "renk": getattr(r, "product_color", "") or "",
            "barkod": getattr(r, "product_barcode", "") or "",
            "adet": getattr(r, "quantity", None),
            "tablo": etiket,
        }
        for r, etiket in satirlar
    ]
    kargo = getattr(ilk, "cargo_provider_name", "") or ""
    kargo_l = kucuk(kargo)
    return {
        "order_number": ilk.order_number,
        "package_number": getattr(ilk, "package_number", "") or "",
        "musteri": f"{getattr(ilk, 'customer_name', '') or ''} {getattr(ilk, 'customer_surname', '') or ''}".strip(),
        "durum": ", ".join(sorted({etiket for _, etiket in satirlar})),
        "kargo": kargo,
        "kargo_sinif": "kargo-dhl" if "dhl" in kargo_l else ("kargo-tyex" if "trendyol" in kargo_l or "tyex" in kargo_l else ""),
        "takip": getattr(ilk, "cargo_tracking_number", "") or "",
        "son_teslim": fmt_ist(getattr(ilk, "agreed_delivery_date", None), "%d.%m.%Y %H:%M"),
        "kalemler": kalemler,
    }


def _panele_dusme(needles: list[str], satirlar: list[tuple[object, str]], digerleri: list[Olay]) -> list[Olay]:
    """Panele ilk düşme anı: satır created_at'leri, ilk audit kaydı (gürültü dahil) ve panel
    tarafındaki diğer olayların (üretim kaydı, raf ataması...) en erkeni.

    Satırlar statü tabloları arasında taşınırken created_at yenilendiğinden tek başına güvenilmez.
    """
    adaylar = [r.created_at for r, _ in satirlar if getattr(r, "created_at", None)]
    adaylar += [o.ts for o in digerleri if o.ts and o.adim != "siparis"]
    try:
        ilk_audit = (
            db.session.query(OrderAuditLog.ts)
            .filter(or_(OrderAuditLog.order_number.in_(needles), OrderAuditLog.package_number.in_(needles)))
            .order_by(OrderAuditLog.ts.asc())
            .first()
        )
        if ilk_audit and ilk_audit[0]:
            adaylar.append(ilk_audit[0])
    except Exception:
        db.session.rollback()
    if not adaylar:
        return []
    en_erken = min(adaylar)
    # Eski (audit öncesi) siparişte tek aday, teslim/kargo satırının taşınma anıdır → "panele düştü" demek yanıltır.
    sonraki_adimlar = [o.ts for o in digerleri if o.ts and o.adim in ("kargoda", "teslim", "iptal", "arsiv")]
    if sonraki_adimlar and min(sonraki_adimlar) <= en_erken:
        return []
    return [Olay(en_erken, "panel", "Panele düştü", kaynak="Trendyol senkron")]


SHOPIFY_SORGU = """
query($id: ID!) { order(id: $id) {
  legacyResourceId name createdAt cancelledAt cancelReason closedAt
  displayFulfillmentStatus displayFinancialStatus
  customer { firstName lastName phone }
  shippingAddress { name address1 address2 city province phone }
  fulfillments { createdAt status trackingInfo { company number } }
  lineItems(first: 50) { edges { node { title sku quantity variant { barcode } } } }
} }"""


def _shopify_siparis(shopify_id: str) -> dict | None:
    """Shopify'dan canlı sipariş: site siparişi panel sipariş tablolarına inmediği için
    sipariş saati, müşteri, kargo ve kalemler buradan gelir. Hata → None (panel izleri yine gösterilir)."""
    try:
        from shopify_site.shopify_service import shopify_service
        sonuc = shopify_service.run_graphql(SHOPIFY_SORGU, {"id": f"gid://shopify/Order/{shopify_id}"})
        return ((sonuc.get("data") or {}).get("order")) or None
    except Exception:
        logger.warning("siparis_zaman: Shopify siparişi alınamadı (%s)", shopify_id, exc_info=True)
        return None


def _shopify_ozeti(order: dict, shopify_id: str) -> dict:
    musteri = order.get("customer") or {}
    adres = order.get("shippingAddress") or {}
    ad = f"{musteri.get('firstName') or ''} {musteri.get('lastName') or ''}".strip() or (adres.get("name") or "")
    kalemler = []
    for e in ((order.get("lineItems") or {}).get("edges") or []):
        n = e.get("node") or {}
        kalemler.append({
            "urun": n.get("title") or n.get("sku") or "",
            "beden": "", "renk": "",
            "barkod": ((n.get("variant") or {}).get("barcode")) or n.get("sku") or "",
            "adet": n.get("quantity"),
            "tablo": "Site",
        })
    takip = next((t for f in (order.get("fulfillments") or []) for t in (f.get("trackingInfo") or []) if t), {})
    kargo = takip.get("company") or ""
    kargo_l = kucuk(kargo)
    durum = {"FULFILLED": "Kargolandı", "UNFULFILLED": "Kargolanmadı", "PARTIALLY_FULFILLED": "Kısmen kargolandı"}.get(
        order.get("displayFulfillmentStatus") or "", order.get("displayFulfillmentStatus") or "")
    if order.get("cancelledAt"):
        durum = "İptal"
    return {
        "order_number": order.get("name") or f"#{shopify_id}",
        "package_number": "",
        "alt_kimlik": f"SH-{shopify_id}",
        "kaynak": "Shopify",
        "musteri": ad,
        "adres": " ".join(p for p in (adres.get("address1"), adres.get("address2"), adres.get("city"), adres.get("province")) if p),
        "durum": durum,
        "kargo": kargo,
        "kargo_sinif": "kargo-dhl" if "dhl" in kargo_l else ("kargo-tyex" if "trendyol" in kargo_l or "tyex" in kargo_l else ""),
        "takip": takip.get("number") or "",
        "son_teslim": "",
        "kalemler": kalemler,
    }


def _shopify_adiyla_kimlik(siparis_adi: str) -> str | None:
    """'#1428' → Shopify iç kimliği; değişim ekranındaki çözücü yeniden kullanılır."""
    try:
        from degisim import _shopify_id_adla_bul
        return _shopify_id_adla_bul(siparis_adi)
    except Exception:
        logger.warning("siparis_zaman: Shopify sipariş adı çözülemedi (%s)", siparis_adi, exc_info=True)
        return None


def zaman_cizgisi(needle: str) -> dict:
    tur, ham = girdi_turu(needle)
    shopify_id = ham if tur == "shopify_id" else (_shopify_adiyla_kimlik(ham) if tur == "shopify_ad" else None)
    if shopify_id:
        # Panel izleri iki biçimde tutuluyor: üretim/ledger 'SH-<id>', bazı hareketler çıplak '<id>'
        needles = [f"SH-{shopify_id}", shopify_id]
        shopify = _shopify_siparis(shopify_id)
    else:
        needles = [ham or needle]
        shopify = None
    needle = needles[0]
    satirlar = _siparis_satirlari(needles)
    olaylar = (
        _tablo_olaylari(satirlar)
        + _uretim_olaylari(needles)
        + _audit_olaylari(needles)
        + _user_log_olaylari(needles)
        + _ledger_olaylari(needles)
        + (shopify_olaylari(shopify) if shopify else [])
    )
    # Site siparişi panele "düşmez" (canlı Shopify'dan okunur) → bu adım site siparişinde anlamsız
    if not shopify_id:
        olaylar += _panele_dusme(needles, satirlar, olaylar)
    birlesik = olaylari_birlestir(olaylar)
    ozet = ozet_adimlar(birlesik, gizle={"panel"} if shopify_id else None)
    ilk = {o.adim: o.ts for o in reversed(birlesik)}  # reversed → sözlükte en erken kalır
    paket_ts = min((t for a, t in ilk.items() if a in ("hazirlandi", "paketlendi")), default=None)
    sureler = {
        "siparis_paket": sure_metni(ilk.get("siparis"), paket_ts),
        "paket_kargo": sure_metni(paket_ts, ilk.get("kargoda")),
        "siparis_kargo": sure_metni(ilk.get("siparis"), ilk.get("kargoda")),
    }
    try:
        notu = db.session.query(SiparisNotu).filter(SiparisNotu.order_number.in_(needles)).first()
    except Exception:
        db.session.rollback()
        notu = None
    return {
        "siparis": _shopify_ozeti(shopify, shopify_id) if shopify else _siparis_ozeti(satirlar),
        "ozet": ozet,
        "sureler": sureler,
        "olaylar": [o.gorunum() for o in birlesik],
        "not": {"metin": notu.note, "kim": notu.updated_by or "", "zaman": fmt_ist(notu.updated_at)} if notu else None,
        "bulundu": bool(satirlar or birlesik or shopify),
        "aranan": needle,
    }


@siparis_zaman_bp.route("/siparis-zaman/kargo-kodu-verildi", methods=["POST"], endpoint="kargo_kodu_verildi")
def kargo_kodu_verildi():
    """Otomatik Gönderim: etiket panelden basılmaz, kargo kodu ekranda gösterilip kuryenin
    terminalinden basılır — bu an hiç loglanmıyordu, zaman çizgisinde "Etiket / Kargo kodu"
    adımı boş kalıyordu. /order-label'daki PRINT kaydıyla aynı biçimde iz bırakır."""
    data = request.get_json(silent=True) or {}
    order_number = (data.get("order_number") or "").strip()
    if not order_number:
        return jsonify({"success": False, "message": "order_number gerekli"}), 400
    try:
        log_user_action("PRINT", {
            "işlem_açıklaması": f"Otomatik gönderim — kargo kodu verildi — {order_number}",
            "sayfa": (data.get("sayfa") or "Sipariş Hazırla")[:40],
            "kargo_firması": (data.get("cargo_provider") or "-")[:60],
            "kargo_kodu": (data.get("shipping_barcode") or "-")[:40],
            "sipariş_no": order_number[:40],
        })
    except Exception:
        logger.warning("kargo_kodu_verildi: hareket loglanamadı", exc_info=True)
        return jsonify({"success": False}), 500
    return jsonify({"success": True})


@siparis_zaman_bp.route("/siparis-zaman", endpoint="page")
def page():
    q = (request.args.get("q") or "").strip().lstrip("#")
    sonuc = None
    hata = None
    if q:
        try:
            sonuc = zaman_cizgisi(q)
        except Exception as exc:
            logger.exception("siparis-zaman hatası")
            hata = str(exc)
    return render_template("siparis_zaman.html", q=q, sonuc=sonuc, hata=hata)
