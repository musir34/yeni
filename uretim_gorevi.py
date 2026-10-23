"""
Anasayfa "Üretim Modelleri" kartı.

Komutan emri (2026-10-14): eritme kartının (eritme_gorevi.py) üretim modu eşleniği.
Üretim modundaki her model için son 30 günde gelen üretim siparişi sayısı, son
sipariş fiyatı ve ortalama sipariş fiyatı gösterilir. Model listesi PlatformConfig
'uretim_ayar' torbasından (uretim_modu.get_uretim_models), sipariş sayısı
uretim_siparis tablosundan, fiyatlar sipariş tablolarındaki kalem JSON'undan
(unit_price) okunur. Site (SH-) ve değişim (DG-) kayıtları sipariş tablolarına
inmediği için sayıma girer, fiyata girmez.

Anasayfa her açılışta çağırdığı için sonuç kısa süre (TTL) önbellekte tutulur.
Her hata → boş/None döner, anasayfa bu yüzden düşmez.
"""
import json
import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import func

from models import (db, CentralStock, Product, UretimSiparis,
                    OrderCreated, OrderHazirlaniyor, OrderPicking, OrderShipped,
                    OrderDelivered, OrderCancelled, OrderArchived)
from uretim_modu import get_uretim_models, get_uretim_renkler

logger = logging.getLogger(__name__)

PENCERE_GUN = 30          # kayan pencere (takvim ayı değil)
ONBELLEK_SANIYE = 300     # anasayfa 2,5 dk'da bir yenileniyor; 5 dk yeter
_ONBELLEK = {"zaman": 0.0, "veri": None}

# Fiyat için taranan sipariş tabloları (iptal dahil: "gelen sipariş" sayılır)
_SIPARIS_TABLOLARI = (OrderCreated, OrderHazirlaniyor, OrderPicking, OrderShipped,
                      OrderDelivered, OrderCancelled, OrderArchived)


def _tl(deger) -> str:
    """1568.79 → '1.568,79' (şablonda hesap yapılmasın diye burada biçimlenir)."""
    if deger is None:
        return "—"
    return f"{deger:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _kalemler(details) -> list[dict]:
    """details JSON → [{'barcode','quantity'}]; bozuk JSON → []."""
    try:
        det = json.loads(details) if isinstance(details, str) else details
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(det, list):
        return []
    out = []
    for d in det:
        if not isinstance(d, dict):
            continue
        bc = str(d.get("barcode") or "").strip()
        if not bc:
            continue
        try:
            adet = int(d.get("quantity", 1) or 1)
        except (TypeError, ValueError):
            adet = 1
        out.append({"barcode": bc, "quantity": adet, "unit_price": d.get("unit_price")})
    return out


TEK_KALEM = "*"  # tek barkodlu siparişte barkoddan bağımsız fiyat anahtarı


def _fiyat_haritasi(order_numbers: list[str]) -> dict[tuple[str, str], float]:
    """(order_number, barcode) → unit_price. Tam entity ÇEKİLMEZ (orders_archived
    kolon adı uyumsuzluğu; uretim_routes ile aynı tuzak), yalnız gereken kolonlar.

    Üretim kaydı barkodu normalize (alias çözülmüş), sipariş tablosu ham barkod
    tutar; alias/Türkçe karakter farkında barkodla eşleşmez. Tek barkodlu siparişte
    (order_number, TEK_KALEM) anahtarı geri düşüş olarak yazılır."""
    harita: dict[tuple[str, str], float] = {}
    if not order_numbers:
        return harita
    for M in _SIPARIS_TABLOLARI:
        try:
            satirlar = (M.query.filter(M.order_number.in_(order_numbers))
                        .with_entities(M.order_number, M.details).all())
        except Exception:
            db.session.rollback()
            logger.warning("[URETIM-KART] %s okunamadı", M.__tablename__, exc_info=True)
            continue
        for order_number, details in satirlar:
            kalemler = _kalemler(details)
            fiyatlar: dict[str, float] = {}
            for k in kalemler:
                if k["barcode"] in fiyatlar or k["unit_price"] in (None, ""):
                    continue
                try:
                    fiyatlar[k["barcode"]] = float(k["unit_price"])
                except (TypeError, ValueError):
                    pass
            for bc, fiyat in fiyatlar.items():
                harita.setdefault((order_number, bc), fiyat)
            if len({k["barcode"] for k in kalemler}) == 1 and fiyatlar:
                harita.setdefault((order_number, TEK_KALEM), next(iter(fiyatlar.values())))
    return harita


def _urun_haritasi(modeller: set[str],
                  renk_kisiti: dict[str, list[str]] | None = None
                  ) -> tuple[dict[str, str], dict[str, dict]]:
    """barcode → model kodu; model kodu → {'baslik','stok','renkler'} (stok canlı,
    merkezi). renkler: üretime dahil renkler — kısıtlı modelde seçili renkler,
    kısıtsız modelde modelin tüm renkleri."""
    renk_kisiti = renk_kisiti or {}
    barkod_model: dict[str, str] = {}
    model_bilgi: dict[str, dict] = {m: {"baslik": "", "stok": 0, "renkler": []} for m in modeller}
    if not modeller:
        return barkod_model, model_bilgi
    tum_renkler: dict[str, set[str]] = {}
    try:
        for barcode, model, title, color in (Product.query
                                             .filter(Product.product_main_id.in_(modeller))
                                             .with_entities(Product.barcode, Product.product_main_id,
                                                            Product.title, Product.color).all()):
            model = str(model).strip()
            if barcode:
                barkod_model[str(barcode).strip()] = model
            if title and not model_bilgi[model]["baslik"]:
                model_bilgi[model]["baslik"] = title
            if color and str(color).strip():
                tum_renkler.setdefault(model, set()).add(str(color).strip())
        for model in modeller:
            model_bilgi[model]["renkler"] = (list(renk_kisiti.get(model) or [])
                                             or sorted(tum_renkler.get(model, set())))
        for model, stok in (db.session.query(Product.product_main_id,
                                             func.coalesce(func.sum(CentralStock.qty), 0))
                            .join(CentralStock, CentralStock.barcode == Product.barcode)
                            .filter(Product.product_main_id.in_(modeller))
                            .group_by(Product.product_main_id).all()):
            model_bilgi[str(model).strip()]["stok"] = int(stok or 0)
    except Exception:
        db.session.rollback()
        logger.warning("[URETIM-KART] ürün/stok haritası okunamadı", exc_info=True)
    return barkod_model, model_bilgi


def _hesapla(uretim_satirlari, fiyat_map: dict, barkod_model: dict,
             model_bilgi: dict, normalize=None) -> dict:
    """Saf hesap: model bazında sipariş sayısı, çift, son fiyat, ortalama.

    uretim_satirlari: [(order_number, order_date, details)] — tarih sırası önemsiz.
    normalize: doğrudan eşleşmeyen barkod için alias çözücü (DB'ye gider, barkod
    başına bir kez çağrılır); None ise eşleşmeyen kalem atlanır.
    """
    normalize_onbellek: dict[str, str | None] = {}

    def _model_bul(bc: str) -> str | None:
        if bc in barkod_model:
            return barkod_model[bc]
        if normalize is None:
            return None
        if bc not in normalize_onbellek:
            try:
                normalize_onbellek[bc] = barkod_model.get(normalize(bc))
            except Exception:
                normalize_onbellek[bc] = None
        return normalize_onbellek[bc]

    toplam: dict[str, dict] = {}
    for order_number, order_date, details in uretim_satirlari:
        for k in _kalemler(details):
            bc = k["barcode"]
            model = _model_bul(bc)
            if model is None:
                continue
            t = toplam.setdefault(model, {"siparisler": set(), "cift": 0, "tutar": 0.0,
                                          "fiyatli_cift": 0, "son": None})
            t["siparisler"].add(order_number)
            t["cift"] += k["quantity"]
            fiyat = fiyat_map.get((order_number, bc))
            if fiyat is None:
                fiyat = fiyat_map.get((order_number, TEK_KALEM))  # alias barkod geri düşüşü
            if fiyat is None:
                continue
            t["tutar"] += fiyat * k["quantity"]
            t["fiyatli_cift"] += k["quantity"]
            if t["son"] is None or (order_date or datetime.min) > (t["son"][0] or datetime.min):
                t["son"] = (order_date, fiyat)
    modeller = []
    for model, bilgi in model_bilgi.items():
        t = toplam.get(model)
        siparis = len(t["siparisler"]) if t else 0
        ort = (t["tutar"] / t["fiyatli_cift"]) if t and t["fiyatli_cift"] else None
        son_fiyat = t["son"][1] if t and t["son"] else None
        son_tarih = t["son"][0] if t and t["son"] else None
        fark = (son_fiyat - ort) if (son_fiyat is not None and ort is not None) else None
        modeller.append({
            "kod": model,
            "baslik": bilgi.get("baslik") or "",
            "renkler": list(bilgi.get("renkler") or []),
            "stok": bilgi.get("stok", 0),
            "siparis": siparis,
            "cift": t["cift"] if t else 0,
            "ort_fiyat": ort,
            "ort_fiyat_str": _tl(ort),
            "son_fiyat": son_fiyat,
            "son_fiyat_str": _tl(son_fiyat),
            "son_tarih": son_tarih,
            "fark": fark,   # son − ortalama (TL); şablonda yön/renk için
        })
    modeller.sort(key=lambda m: (-m["siparis"], -m["cift"], m["kod"]))
    toplam_siparis = len({o for t in toplam.values() for o in t["siparisler"]})
    toplam_cift = sum(m["cift"] for m in modeller)
    tutar = sum(t["tutar"] for t in toplam.values())
    fiyatli = sum(t["fiyatli_cift"] for t in toplam.values())
    genel_ort = (tutar / fiyatli) if fiyatli else None
    return {
        "gun": PENCERE_GUN,
        "modeller": modeller,
        "model_sayisi": len(modeller),
        "aktif_model": sum(1 for m in modeller if m["siparis"]),
        "toplam_siparis": toplam_siparis,
        "toplam_cift": toplam_cift,
        "ort_fiyat": genel_ort,
        "ort_fiyat_str": _tl(genel_ort),
        "max_siparis": max((m["siparis"] for m in modeller), default=0),
    }


def _uretim_ozeti_hesapla() -> dict | None:
    modeller = get_uretim_models()
    if not modeller:
        return None
    barkod_model, model_bilgi = _urun_haritasi(modeller, get_uretim_renkler())
    # order_date naive UTC saklanır (ingest ist_to_utc) → kesim de UTC
    kesim = datetime.utcnow() - timedelta(days=PENCERE_GUN)
    try:
        satirlar = (UretimSiparis.query
                    .filter(UretimSiparis.order_date >= kesim)
                    .with_entities(UretimSiparis.order_number, UretimSiparis.order_date,
                                   UretimSiparis.details).all())
    except Exception:
        db.session.rollback()
        logger.warning("[URETIM-KART] üretim siparişleri okunamadı", exc_info=True)
        satirlar = []
    fiyat_map = _fiyat_haritasi([s[0] for s in satirlar])
    from barcode_alias_helper import normalize_barcode
    return _hesapla(satirlar, fiyat_map, barkod_model, model_bilgi, normalize=normalize_barcode)


def uretim_ozeti() -> dict | None:
    """Anasayfa kartı verisi (TTL önbellekli). Üretim modunda model yoksa None."""
    simdi = time.monotonic()
    if _ONBELLEK["veri"] is not None and simdi - _ONBELLEK["zaman"] < ONBELLEK_SANIYE:
        return _ONBELLEK["veri"]
    try:
        veri = _uretim_ozeti_hesapla()
    except Exception:
        db.session.rollback()
        logger.warning("[URETIM-KART] özet hesaplanamadı", exc_info=True)
        return _ONBELLEK["veri"]
    _ONBELLEK.update(zaman=simdi, veri=veri)
    return veri
