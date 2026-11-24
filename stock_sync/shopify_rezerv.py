"""Shopify (site) açık siparişlerinin stok rezervi.

SORUN
-----
Rezerv yalnız Trendyol tablolarından hesaplanıyordu. Site siparişleri DB'ye yazılmaz;
stok ancak paketleme onayında (``pack_out``, ``order_number='SH-<id>'``) düşer.
Shopify push'u mutlak SET olduğundan paketlenmemiş her site siparişinin birimi bir
sonraki turda tekrar satışa açılıyordu → oversell.

ÇÖZÜM
-----
Shopify'daki açık (karşılanmamış, iptal/arşiv olmayan) siparişlerin kalemleri, ledger'da
o sipariş için ZATEN düşülmüş adet çıkarılarak rezerve sayılır.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

ONBELLEK_SURESI_SN = 90          # aynı 3 dk'lık turda TY push + Shopify push + monitör
BAYAT_AZAMI_SN = 30 * 60         # çekim başarısızsa en fazla bu kadar eski önbellek kullanılır
SAYFA_BOYU = 100
AZAMI_SAYFA = 10
ARSIV_ETIKETI = "Arsivlendi"

ACIK_SIPARIS_SORGUSU = """
query AcikSiparisler($first: Int!, $after: String) {
  orders(first: $first, after: $after, sortKey: CREATED_AT, reverse: true,
         query: "status:open AND (fulfillment_status:unfulfilled OR fulfillment_status:partial OR fulfillment_status:on_hold OR fulfillment_status:scheduled)") {
    pageInfo { hasNextPage endCursor }
    nodes { legacyResourceId cancelledAt tags
            lineItems(first: 50) { nodes { unfulfilledQuantity variant { id } } } }
  }
}
"""

_onbellek: dict = {"harita": None, "zaman": 0.0}


def hesapla_rezerv(siparisler, varyant_barkod, dusulmus, arsivli) -> dict[str, int]:
    """SAF: açık siparişlerden barkod → rezerv adedi (DB/ağ yok).

    Args:
        siparisler: Shopify sipariş düğümleri (legacyResourceId, cancelledAt, tags, lineItems.nodes).
        varyant_barkod: Shopify varyant kimliği → panel barkodu (normalize edilmiş).
        dusulmus: {(order_number, barkod): adet} — ledger'da zaten düşülmüş net adet.
        arsivli: panelde arşivlenmiş 'SH-…' sipariş numaraları.
    """
    rezerv: dict[str, int] = {}
    for siparis in siparisler or []:
        if siparis.get("cancelledAt"):
            continue
        order_number = f"SH-{siparis.get('legacyResourceId')}"
        if ARSIV_ETIKETI in (siparis.get("tags") or []) or order_number in arsivli:
            continue
        # Düşülmüş adet sipariş+barkod başına bir kez; aynı barkodlu kalemlere sırayla tüketilir
        kalan_dusum: dict[str, int] = {}
        for kalem in ((siparis.get("lineItems") or {}).get("nodes") or []):
            varyant = kalem.get("variant")
            if not varyant:
                continue
            barkod = varyant_barkod.get(varyant.get("id"))
            if not barkod:
                continue
            if barkod not in kalan_dusum:
                kalan_dusum[barkod] = int(dusulmus.get((order_number, barkod), 0) or 0)
            adet = int(kalem.get("unfulfilledQuantity") or 0)
            tuketilen = min(adet, kalan_dusum[barkod])
            kalan_dusum[barkod] -= tuketilen
            kalan = adet - tuketilen
            if kalan > 0:
                rezerv[barkod] = rezerv.get(barkod, 0) + kalan
    return rezerv


def _acik_siparisleri_cek() -> list:
    from shopify_site.shopify_service import shopify_service

    siparisler: list = []
    after = None
    for _ in range(AZAMI_SAYFA):
        sonuc = shopify_service.run_graphql(ACIK_SIPARIS_SORGUSU, {"first": SAYFA_BOYU, "after": after})
        if not sonuc.get("success"):
            raise RuntimeError(f"Shopify açık sipariş sorgusu başarısız: {sonuc.get('error')}")
        blok = (sonuc.get("data") or {}).get("orders") or {}
        siparisler.extend(blok.get("nodes") or [])
        sayfa = blok.get("pageInfo") or {}
        if not sayfa.get("hasNextPage"):
            return siparisler
        after = sayfa.get("endCursor")
    logger.warning("[REZERV][SHOPIFY] %d sayfa sınırına ulaşıldı, kalan siparişler sayılmadı", AZAMI_SAYFA)
    return siparisler


def _rezervi_hesapla() -> dict[str, int]:
    from sqlalchemy import func
    from barcode_alias_helper import normalize_barcode
    from models import db, Archive, ShopifyMapping, StockMovement

    # Eşleştirme yoksa barkod çözülemez → ağa hiç çıkmadan boş rezerv
    eslesme = dict(db.session.query(ShopifyMapping.shopify_variant_id, ShopifyMapping.barcode).all())
    if not eslesme:
        return {}

    siparisler = _acik_siparisleri_cek()

    varyant_barkod: dict[str, str] = {}
    for siparis in siparisler:
        for kalem in ((siparis.get("lineItems") or {}).get("nodes") or []):
            vid = (kalem.get("variant") or {}).get("id")
            if vid and vid in eslesme and vid not in varyant_barkod:
                varyant_barkod[vid] = normalize_barcode(eslesme[vid])

    numaralar = [f"SH-{s.get('legacyResourceId')}" for s in siparisler]
    dusulmus: dict = {}
    if numaralar:
        satirlar = (db.session.query(StockMovement.order_number, StockMovement.barcode,
                                     func.sum(StockMovement.delta))
                    .filter(StockMovement.order_number.in_(numaralar))
                    .group_by(StockMovement.order_number, StockMovement.barcode).all())
        dusulmus = {(no, bc): max(0, -int(toplam or 0)) for no, bc, toplam in satirlar}

    arsivli = {r[0] for r in db.session.query(Archive.order_number)
               .filter(Archive.order_number.like("SH-%")).all()}

    rezerv = hesapla_rezerv(siparisler, varyant_barkod, dusulmus, arsivli)
    logger.info("[REZERV][SHOPIFY] %d açık sipariş, %d barkod, toplam %d adet rezerv",
                len(siparisler), len(rezerv), sum(rezerv.values()))
    return rezerv


def get_shopify_reserved() -> dict[str, int]:
    """Shopify açık siparişlerinin barkod → rezerv haritası (90 sn önbellekli).

    Hata dışarı sızmaz: çekim başarısızsa ≤30 dk'lık önbellek, yoksa boş harita
    (senkron durmaz, eski davranışa düşer).
    """
    try:
        from shopify_site.shopify_config import ShopifyConfig
        if not ShopifyConfig.is_configured():
            return {}

        simdi = time.monotonic()
        yas = simdi - _onbellek["zaman"]
        if _onbellek["harita"] is not None and yas < ONBELLEK_SURESI_SN:
            return dict(_onbellek["harita"])

        try:
            harita = _rezervi_hesapla()
        except Exception as exc:
            # Yalnız DB hatasında rollback: Postgres'te bozulan transaction çağıranı
            # zehirlemesin. Ağ hatasında çağıranın oturumuna dokunulmaz.
            try:
                from sqlalchemy.exc import SQLAlchemyError
                if isinstance(exc, SQLAlchemyError):
                    from models import db
                    db.session.rollback()
            except Exception:
                pass
            if _onbellek["harita"] is not None and yas < BAYAT_AZAMI_SN:
                logger.warning("[REZERV][SHOPIFY] çekim başarısız, %d sn'lik önbellek kullanılıyor: %s",
                               int(yas), exc)
                return dict(_onbellek["harita"])
            logger.error("[REZERV][SHOPIFY] çekim başarısız, Shopify rezervi uygulanmadı: %s", exc)
            return {}

        _onbellek["harita"] = harita
        _onbellek["zaman"] = simdi
        return dict(harita)
    except Exception:
        logger.exception("[REZERV][SHOPIFY] beklenmeyen hata (yutuldu, boş harita)")
        return {}
