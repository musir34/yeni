"""Shopify yeni siparişleri → MNG gönderisi (zamanlayıcı, 5 dk).

Site siparişleri panele tablo olarak inmez; siparis_hazirla'nın "beklemede" sorgusu
(ödenmiş + kapıda ödemeli, Hazirlaniyor/Kargoda/Teslim/Arsivlendi etiketi olmayan)
burada da kullanılır. Her sipariş için bir kez gönderi açılır (kaynak_ref = Shopify
sipariş id'si). Devreye alma anında eski siparişlere gönderi açılmasın diye yalnız
son MNG_SHOPIFY_GERIYE_GUN (varsayılan 7) gün içindekiler taranır.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from models import db

from .adres import alici_kur
from .servis import KAYNAK_SHOPIFY, gonderi_ac, gonderi_kaydi_var, otomatik_acik, shopify_referansi

logger = logging.getLogger(__name__)

TARAMA_LIMIT = 50


def _geriye_gun() -> int:
    try:
        return max(1, int(os.getenv("MNG_SHOPIFY_GERIYE_GUN") or 7))
    except ValueError:
        return 7


def _olusturma(order: dict) -> datetime | None:
    ham = order.get("createdAt")
    if not ham:
        return None
    try:
        dt = datetime.fromisoformat(str(ham).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def siparis_alicisi(order: dict):
    """Shopify shippingAddress → Alici. TR'de province = il (sık boş), city = ilçe (serbest metin);
    il bulunamazsa posta kodu plakası, o da yoksa adres metni (alici_kur sırası)."""
    shipping = order.get("shippingAddress") or {}
    customer = order.get("customer") or {}
    ad = shipping.get("name") or f"{customer.get('firstName') or ''} {customer.get('lastName') or ''}".strip()
    adres = " ".join(p for p in (shipping.get("address1"), shipping.get("address2")) if p).strip()
    telefon = shipping.get("phone") or customer.get("phone") or ""
    return alici_kur(ad, adres, telefon, il=shipping.get("province") or "", ilce=shipping.get("city") or "",
                     email=order.get("email") or customer.get("email") or "", posta_kodu=shipping.get("zip") or "")


COD_ANAHTARLAR = ("cash on delivery", "kapida", "kapıda", "cod")


def kapida_odeme_mi(order: dict) -> bool:
    """Kuryenin para toplayacağı sipariş: ödeme yöntemi kapıda ödeme VE ödeme henüz alınmamış.
    (siparis_hazirla._is_cod_order 'manual' anahtarını da sayar; burada para söz konusu, dar tutulur.
    Canlı veri: COD siparişler PENDING + 'Cash on Delivery (COD)'; teslimden sonra PAID yapılıyor.)"""
    gateways = [str(g).lower() for g in (order.get("paymentGatewayNames") or [])]
    cod = any(any(k in g for k in COD_ANAHTARLAR) for g in gateways)
    return cod and str(order.get("displayFinancialStatus") or "").upper() != "PAID"


def kapida_odeme_tutari(order: dict):
    if not kapida_odeme_mi(order):
        return None
    try:
        return float(((order.get("currentTotalPriceSet") or {}).get("shopMoney") or {}).get("amount") or 0) or None
    except (TypeError, ValueError):
        return None


def urun_adedi(order: dict) -> int:
    """Siparişteki toplam çift sayısı (shopify_service.get_orders line_items; ham lineItems da desteklenir)."""
    kalemler = order.get("line_items")
    if kalemler is None:
        kalemler = [e.get("node", {}) for e in (order.get("lineItems") or {}).get("edges", [])]
    toplam = 0
    for k in kalemler or []:
        try:
            toplam += int(k.get("currentQuantity") if k.get("currentQuantity") is not None else k.get("quantity") or 0)
        except (TypeError, ValueError):
            continue
    return toplam or 1


def siparis_icin_ac(order: dict):
    kaynak_ref = str(order.get("legacyResourceId") or str(order.get("id") or "").split("/")[-1])
    if not kaynak_ref:
        return None
    if gonderi_kaydi_var(KAYNAK_SHOPIFY, kaynak_ref):     # açık ya da iptal: tekrar açılmaz
        return None
    # Ödenmemiş ve kapıda ödeme de olmayan sipariş (havale bekleyen vb.) kargoya çıkmaz
    if str(order.get("displayFinancialStatus") or "").upper() != "PAID" and not kapida_odeme_mi(order):
        return None
    ad = order.get("name") or f"#{kaynak_ref}"
    return gonderi_ac(
        KAYNAK_SHOPIFY, kaynak_ref, ad, shopify_referansi(ad), siparis_alicisi(order),
        kapida_odeme_tutari=kapida_odeme_tutari(order), aciklama=f"Gullu Shoes siparis {ad}",
        adet=urun_adedi(order),                      # desi = 2 × çift
    )


def iptalleri_tara() -> int:
    """Shopify yönetiminden iptal edilen siparişler: kurye almadıysa MNG gönderisi de iptal edilir."""
    from models import KargoGonderi
    from .durum import HAZIRLANDI, SIPARIS_ACILDI
    from .servis import DURUM_BEKLIYOR, DURUM_HATA, kayit_iptal
    acik = (KargoGonderi.query
            .filter(KargoGonderi.kaynak == KAYNAK_SHOPIFY,
                    KargoGonderi.durum.in_((DURUM_BEKLIYOR, DURUM_HATA, SIPARIS_ACILDI, HAZIRLANDI)))
            .all())
    if not acik:
        return 0
    from shopify_site.shopify_service import shopify_service
    esik = (datetime.now(timezone.utc) - timedelta(days=_geriye_gun())).strftime("%Y-%m-%d")
    sonuc = shopify_service.get_orders(limit=TARAMA_LIMIT, query_filter=f"status:cancelled updated_at:>{esik}")
    if not sonuc.get("success"):
        return 0
    iptal_refler = {str(o.get("legacyResourceId") or str(o.get("id") or "").split("/")[-1])
                    for o in sonuc.get("orders") or []}
    sayi = 0
    for kayit in acik:
        if kayit.kaynak_ref in iptal_refler and kayit_iptal(kayit):
            logger.info("[MNG] Shopify iptali → MNG gönderisi iptal edildi %s (%s)", kayit.kaynak_ad, kayit.referans)
            sayi += 1
    return sayi


def _takip_numaralari(order: dict) -> set[str]:
    numaralar = set()
    for f in order.get("fulfillments") or []:
        for t in f.get("trackingInfo") or []:
            n = str(t.get("number") or "").strip()
            if n:
                numaralar.add(n)
    return numaralar


def baska_kargoyla_karsilananlari_tara() -> int:
    """Shopify'da elle başka takip numarasıyla karşılanan sipariş (ekip eski usul etiket kesmiş, #1464):
    MNG'deki sipariş/gönderi kurye almadıysa iptal edilir; panelde 'barkod bekliyor' diye takılı kalmaz.
    Takip numarası bizim MNG numaramızsa (panelin kendi fulfillment'ı) ya da numara hiç yoksa dokunulmaz."""
    from models import KargoGonderi
    from .durum import HAZIRLANDI, SIPARIS_ACILDI
    from .servis import DURUM_BEKLIYOR, DURUM_HATA, kayit_iptal
    acik = (KargoGonderi.query
            .filter(KargoGonderi.kaynak == KAYNAK_SHOPIFY,
                    KargoGonderi.durum.in_((DURUM_BEKLIYOR, DURUM_HATA, SIPARIS_ACILDI, HAZIRLANDI)))
            .all())
    if not acik:
        return 0
    from shopify_site.shopify_service import shopify_service
    esik = (datetime.now(timezone.utc) - timedelta(days=_geriye_gun())).strftime("%Y-%m-%d")
    sonuc = shopify_service.get_orders(limit=TARAMA_LIMIT, query_filter=f"fulfillment_status:shipped updated_at:>{esik}")
    if not sonuc.get("success"):
        return 0
    numaralar = {str(o.get("legacyResourceId") or str(o.get("id") or "").split("/")[-1]): _takip_numaralari(o)
                 for o in sonuc.get("orders") or []}
    sayi = 0
    for kayit in acik:
        nums = numaralar.get(kayit.kaynak_ref)
        if not nums or (kayit.shipment_id and kayit.shipment_id in nums):
            continue
        if kayit_iptal(kayit):
            kayit.hata = f"Shopify'da başka takip numarasıyla karşılandı ({', '.join(sorted(nums))}); MNG siparişi iptal edildi"
            db.session.commit()
            logger.info("[MNG] Shopify başka kargoyla karşılandı → MNG iptal %s (%s)", kayit.kaynak_ad, kayit.referans)
            sayi += 1
    return sayi


def yeni_siparisleri_tara() -> int:
    """Zamanlayıcı girişi; hata yutulur, açılan gönderi sayısı döner."""
    if not otomatik_acik():
        return 0
    try:
        iptalleri_tara()
    except Exception:
        db.session.rollback()
        logger.exception("[MNG] Shopify iptal taraması hatası (yutuldu)")
    try:
        baska_kargoyla_karsilananlari_tara()
    except Exception:
        db.session.rollback()
        logger.exception("[MNG] Shopify başka-kargo taraması hatası (yutuldu)")
    acilan = 0
    try:
        from siparis_hazirla import _fetch_shopify_beklemede_orders
        esik = datetime.now(timezone.utc) - timedelta(days=_geriye_gun())
        for order in _fetch_shopify_beklemede_orders(limit=TARAMA_LIMIT):
            olusturma = _olusturma(order)
            if olusturma and olusturma < esik:
                continue
            if siparis_icin_ac(order) is not None:
                acilan += 1
    except Exception:
        db.session.rollback()
        logger.exception("[MNG] Shopify taraması hatası (yutuldu)")
    if acilan:
        logger.info("[MNG] Shopify: %s siparişe gönderi açıldı", acilan)
    return acilan
