"""Sipariş listesine Shopify (site) siparişlerini kart olarak ekler.

Trendyol siparişleri orders_* tablolarında durur; site siparişleri DB'de yok, canlı
Shopify API'den gelir. Bu modül API yanıtını sipariş listesi kartının beklediği
MockOrder biçimine çevirir:

- order_number  : 'SH-<iç kimlik>' — arşivle/not/üretim gibi panel eylemlerinin anahtarı
                  (archive.py, siparis_notu, uretim_modu hep bu biçimi kullanır)
- display_number: '1428' — mağazadaki sipariş adı ('#1428'), kartta GÖSTERİLEN numara
- status        : Shopify etiketinden panel durum koduna (Created/Hazirlaniyor/Shipped/
                  Delivered/Cancelled) — templates/shopify/orders.html getOrderStatus ile aynı kural

Panelde arşivlenen (Archive 'SH-…') ve Shopify'da 'Arsivlendi' etiketli siparişler listeye
girmez. API yanıtı 60 sn önbellekte tutulur (canli_panel ile aynı yaklaşım); arşiv eleme
her istekte taze yapılır ki arşivlenen kart hemen kaybolsun. Her hata → boş liste
(Trendyol listesi asla Shopify yüzünden bozulmaz).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from types import SimpleNamespace

logger = logging.getLogger(__name__)

# Etiket → panel durum kodu. Sıra önemli: birden fazla etiket kalmışsa en ileri durum kazanır.
ETIKET_DURUM = (
    ("Teslim Edildi", "Delivered"),
    ("Kargoda", "Shipped"),
    ("Hazirlaniyor", "Hazirlaniyor"),
)
VARSAYILAN_DURUM = "Created"          # etiketsiz = Beklemede = Yeni
IPTAL_DURUM = "Cancelled"

LISTE_LIMIT = 100                     # tek GraphQL sayfası (API üst sınırı)
ONBELLEK_SURESI_SN = 60
_onbellek: dict = {"zaman": 0.0, "siparisler": []}


def durum_kodu(order: dict) -> str:
    """Shopify siparişinin panel durum kodu."""
    if order.get("cancelledAt"):
        return IPTAL_DURUM
    etiketler = set(order.get("tags") or [])
    for etiket, kod in ETIKET_DURUM:
        if etiket in etiketler:
            return kod
    return VARSAYILAN_DURUM


def ic_kimlik(order: dict) -> str:
    return str(order.get("legacyResourceId") or str(order.get("id") or "").split("/")[-1])


def goruntu_no(order: dict) -> str:
    """Kartta gösterilen numara: mağaza sipariş adı '#1428' → '1428'."""
    ad = str(order.get("name") or "").strip().lstrip("#")
    return ad or ic_kimlik(order)


def _naive_utc(iso: str | None) -> datetime | None:
    """Shopify ISO-8601 (UTC, 'Z') → DB konvansiyonu olan naive UTC."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _kargo(order: dict) -> tuple[str, str]:
    """(kargo firması, takip no) — ilk dolu fulfillment takip bilgisinden."""
    for f in order.get("fulfillments") or []:
        for t in f.get("trackingInfo") or []:
            if t:
                return (t.get("company") or "", t.get("number") or "")
    return ("", "")


def _musteri(order: dict) -> tuple[str, str]:
    customer = order.get("customer") or {}
    shipping = order.get("shippingAddress") or {}
    ad, soyad = customer.get("firstName") or "", customer.get("lastName") or ""
    if not (ad or soyad):
        parcalar = (shipping.get("name") or "").split(" ")
        ad = parcalar[0] if parcalar and parcalar[0] else "Misafir"
        soyad = " ".join(parcalar[1:])
    return ad, soyad


def _adres(order: dict) -> str:
    shipping = order.get("shippingAddress") or {}
    return " ".join(
        p for p in (shipping.get("address1"), shipping.get("address2"),
                    shipping.get("city"), shipping.get("province"), shipping.get("country")) if p
    ).strip()


def _detaylar(order: dict) -> str:
    """Kalemleri order_list process_order_details'in okuduğu details JSON biçimine çevir.
    Barkod: get_orders'ın eklediği resolved_barcode (panel barkodu) → varyant barkodu → sku."""
    kalemler = []
    for li in order.get("line_items") or []:
        variant = li.get("variant") or {}
        sku = li.get("sku") or ""
        kalemler.append({
            "barcode": li.get("resolved_barcode") or variant.get("barcode") or sku,
            "sku": sku,
            "product_name": li.get("title") or "Shopify Ürün",
            "quantity": li.get("quantity", 1),
        })
    return json.dumps(kalemler)


def karta_cevir(order: dict) -> SimpleNamespace:
    """Tek Shopify siparişi → order_list.html kartının beklediği alanlar."""
    ad, soyad = _musteri(order)
    kargo_firma, takip_no = _kargo(order)
    kimlik = ic_kimlik(order)
    return SimpleNamespace(
        id=f"SH-{kimlik}",
        order_number=f"SH-{kimlik}",
        display_number=goruntu_no(order),
        status=durum_kodu(order),
        order_date=_naive_utc(order.get("createdAt")),
        details=_detaylar(order),
        merchant_sku=", ".join(li.get("sku") or "" for li in order.get("line_items") or []),
        product_barcode="",
        cargo_provider_name=kargo_firma,
        cargo_tracking_number=takip_no,
        customer_name=ad,
        customer_surname=soyad,
        customer_address=_adres(order),
        agreed_delivery_date=None,
        estimated_delivery_end=None,
        siparis_notu="",
        uretim_durumu="", uretim_etiketi="", uretim_aciklamasi="",
        _is_shopify=True,
    )


def aramaya_uyar(kart, aranan: str | None) -> bool:
    """Sipariş listesi aramasıyla aynı kapsam: sipariş no (1428 / #1428 / SH-… / iç kimlik) + müşteri adı."""
    if not aranan:
        return True
    a = aranan.strip().lstrip("#").casefold()
    if not a:
        return True
    adaylar = (
        kart.display_number, kart.order_number, kart.order_number.replace("SH-", "", 1),
        kart.customer_name, kart.customer_surname, f"{kart.customer_name} {kart.customer_surname}",
    )
    return any(a in str(x or "").casefold() for x in adaylar)


def kartlari_sirala(kartlar: list, sort_key: str | None) -> list:
    """Trendyol + Shopify kartlarını order_list_service._sort_clause ile aynı kurala göre sırala
    (deadline_*: tarihi olmayan en sona; eşitlikte sipariş tarihi yeni → eski)."""
    en_eski = datetime.min

    def tarih(k):
        return getattr(k, "order_date", None) or en_eski

    def son_teslim(k):
        return getattr(k, "agreed_delivery_date", None) or getattr(k, "estimated_delivery_end", None)

    tarihe_gore = sorted(kartlar, key=tarih, reverse=True)
    if sort_key not in ("deadline_asc", "deadline_desc"):
        return tarihe_gore
    olanlar = [k for k in tarihe_gore if son_teslim(k) is not None]
    olmayanlar = [k for k in tarihe_gore if son_teslim(k) is None]
    olanlar.sort(key=son_teslim, reverse=(sort_key == "deadline_desc"))   # stable → tarih sırası korunur
    return olanlar + olmayanlar


def _ham_siparisler() -> list:
    """Shopify'dan arşivlenmemiş son LISTE_LIMIT sipariş (60 sn önbellek)."""
    simdi = time.monotonic()
    if _onbellek["siparisler"] and simdi - _onbellek["zaman"] < ONBELLEK_SURESI_SN:
        return _onbellek["siparisler"]

    from shopify_site.shopify_config import ShopifyConfig
    from shopify_site.shopify_service import shopify_service
    if not ShopifyConfig.is_configured():
        return []
    sonuc = shopify_service.get_orders(limit=LISTE_LIMIT, query_filter="-tag:Arsivlendi")
    if not sonuc.get("success"):
        logger.warning("[SIPARIS-LISTESI][SHOPIFY] siparişler çekilemedi: %s", sonuc.get("error"))
        return _onbellek["siparisler"]          # bayat veri boş listeden iyidir
    _onbellek["siparisler"] = sonuc.get("orders") or []
    _onbellek["zaman"] = simdi
    return _onbellek["siparisler"]


def _panelde_arsivli() -> set[str]:
    from models import Archive, db
    try:
        return {r[0] for r in db.session.query(Archive.order_number)
                .filter(Archive.order_number.like("SH-%")).all()}
    except Exception:
        logger.warning("[SIPARIS-LISTESI][SHOPIFY] arşiv okunamadı", exc_info=True)
        db.session.rollback()
        return set()


def _notlari_ve_uretimi_ekle(kartlar: list) -> None:
    """Trendyol kartlarıyla aynı ek bilgiler: siparişe özel not + üretim rozeti (tek toplu sorgu)."""
    if not kartlar:
        return
    from siparis_notu import get_notes_map
    from uretim_modu import URETIM_DURUM_ACIKLAMASI, URETIM_DURUM_ETIKETI, uretim_durum_haritasi
    numaralar = [k.order_number for k in kartlar]
    notlar = get_notes_map(numaralar)
    uretim = uretim_durum_haritasi(numaralar)
    for k in kartlar:
        k.siparis_notu = notlar.get(k.order_number, "")
        k.uretim_durumu = uretim.get(k.order_number, "")
        k.uretim_etiketi = URETIM_DURUM_ETIKETI.get(k.uretim_durumu, "")
        k.uretim_aciklamasi = URETIM_DURUM_ACIKLAMASI.get(k.uretim_durumu, "")


def shopify_kartlari(durum: str | None = None, aranan: str | None = None) -> list:
    """Sipariş listesine eklenecek Shopify kartları.

    durum : panel durum kodu ('Created', 'Shipped', …) → yalnız o durum; None → hepsi
    aranan: liste arama kutusu metni
    Hata → [] (liste Shopify'sız ama çalışır halde kalır).
    """
    try:
        arsivli = _panelde_arsivli()
        kartlar = []
        for order in _ham_siparisler():
            kart = karta_cevir(order)
            if kart.order_number in arsivli:
                continue
            if durum and kart.status != durum:
                continue
            if not aramaya_uyar(kart, aranan):
                continue
            kartlar.append(kart)
        _notlari_ve_uretimi_ekle(kartlar)
        return kartlar
    except Exception:
        logger.warning("[SIPARIS-LISTESI][SHOPIFY] kartlar üretilemedi", exc_info=True)
        return []
