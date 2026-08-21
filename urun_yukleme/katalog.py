# -*- coding: utf-8 -*-
"""
Trendyol katalog yardımcıları — Ürün Yükleme sayfası için.

Bu modül, API ile ürün açma sürecinde kanıtlanmış standartları kod olarak
zorunlu kılar (kaynak: memory/project_urun_yukleme_standartlari.md):
- Barkod: ürün grubu öneki + toplam 9 karakter; boşluk Trendyol listesinden
  (onaylı arşivli dahil + onaysız) ve panel rezerv listesinden doğrulanır.
- Model kodu: 01XX biçimi, boş olanı listeden bul.
- Yasaklı kelimeler: başlık/açıklamada geçemez (içerik reddi verir).
"""
import base64
import json
import logging
import re
import time

import requests

from models import db, PlatformConfig
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID

logger = logging.getLogger(__name__)

BASE = "https://apigw.trendyol.com/integration/product"
MARKA_ID = 1365320          # Güllü Shoes
VARSAYILAN_ONEK = "079950"  # sandalet grubu — form üzerinden değiştirilebilir
BARKOD_UZUNLUK = 9

# İçerik reddi veren söylemler: "trendyol" (yasaklı kelime), iade/garanti/kargo/
# değişim (yanıltıcı beyan — satış/iade koşulu), link/iletişim, "ortopedik"
# (doğrulanamayan sağlık iddiası) ve fiyat/indirim söylemleri (claude-science
# kuralları — AI'ya yasaklanan her kelime burada da denetlenir).
YASAKLI_KELIMELER = ("trendyol", "iade", "garanti", "kargo", "değişim",
                     "http", "www", "tel:", "ortopedik", "@",
                     "indirim", "kampanya", "ücretsiz", "fiyat")
_YIL_DESENI = re.compile(r"20[2-9]\d")  # yıl yazmak yasak (metin eskir)

_ttl_cache: dict = {}


def _headers() -> dict:
    auth = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Content-Type": "application/json",
            "User-Agent": f"SellerId={SUPPLIER_ID} - SelfIntegration"}


def _get(url: str, timeout: int = 60) -> dict:
    r = requests.get(url, headers=_headers(), timeout=timeout)
    r.raise_for_status()
    return r.json()


def _cached(anahtar: str, uret, ttl_sn: int = 6 * 3600):
    kayit = _ttl_cache.get(anahtar)
    if kayit and time.time() - kayit[0] < ttl_sn:
        return kayit[1]
    deger = uret()
    _ttl_cache[anahtar] = (time.time(), deger)
    return deger


# ---------------------------------------------------------------- kategoriler

def kategori_yapraklari() -> list[dict]:
    """Tüm YAPRAK kategoriler: [{id, ad, yol}] (6 saat önbellekli)."""
    def _uret():
        agac = _get(f"{BASE}/product-categories")
        yapraklar = []

        def gez(dugumler, yol):
            for d in dugumler:
                p = yol + [d["name"]]
                alt = d.get("subCategories") or []
                if alt:
                    gez(alt, p)
                else:
                    yapraklar.append({"id": d["id"], "ad": d["name"], "yol": " > ".join(p)})

        gez(agac.get("categories", []), [])
        return yapraklar

    return _cached("kategori_yapraklari", _uret, ttl_sn=24 * 3600)


def kategori_ara(q: str, limit: int = 20) -> list[dict]:
    q = (q or "").strip().lower()
    if not q:
        return []
    return [k for k in kategori_yapraklari() if q in k["yol"].lower()][:limit]


def kategori_ozellikleri(cid: int) -> list[dict]:
    """Kategorinin özellik listesi (değerler AYRI uçtan): [{id, ad, zorunlu, varyant, serbest}]."""
    def _uret():
        d = _get(f"{BASE}/categories/{cid}/attributes")
        sonuc = []
        for a in d.get("categoryAttributes", []):
            attr = a.get("attribute") or {}
            sonuc.append({
                "id": attr.get("id"),
                "ad": attr.get("name"),
                "zorunlu": bool(a.get("required")),
                "varyant": bool(a.get("varianter")),
                "serbest": bool(a.get("allowCustom")),
            })
        # Zorunlular ve varyant üstte
        sonuc.sort(key=lambda x: (not x["varyant"], not x["zorunlu"], x["ad"] or ""))
        return sonuc

    return _cached(f"ozellikler_{cid}", _uret)


def ozellik_degerleri(cid: int, aid: int) -> list[dict]:
    """Bir özelliğin TÜM değerleri (sayfalı uç birleştirilir): [{id, ad}]."""
    def _uret():
        degerler, sayfa = [], 0
        while True:
            d = _get(f"{BASE}/categories/{cid}/attributes/{aid}/values?page={sayfa}&size=200")
            degerler += [{"id": v["attributeValueId"], "ad": v["attributeValue"]}
                         for v in d.get("content", [])]
            if sayfa >= d.get("totalPages", 1) - 1:
                break
            sayfa += 1
        return degerler

    return _cached(f"degerler_{cid}_{aid}", _uret)


def _kategori_taramasi() -> dict:
    """
    Kategori başına, mevcut ürünlerden öğrenilen kalıplar (30 dk önbellek):
    - barkod öneki (6 hane; stiletto 730734, sandalet 079950...)
    - MODEL KODU öneki (productMainId'nin son 2 hane hariç kısmı; 0121 → "01")
    Dönen: {kat: {"barkod": {onek: adet}, "model": {onek: adet}}}
    """
    def _uret():
        sayim: dict = {}
        for uc in ("approved", "unapproved"):
            sayfa = 0
            while True:
                d = _get(f"{BASE}/sellers/{SUPPLIER_ID}/products/{uc}?size=100&page={sayfa}", timeout=90)
                for c in d.get("content", []):
                    kat = (c.get("category") or {}).get("name") or ""
                    if not kat:
                        continue
                    kayit = sayim.setdefault(kat, {"barkod": {}, "model": {}})
                    mid = str(c.get("productMainId") or "").strip()
                    if mid.isdigit() and 3 <= len(mid) <= 6:
                        m_onek = mid[:-2]
                        kayit["model"][m_onek] = kayit["model"].get(m_onek, 0) + 1
                    for v in c.get("variants") or []:
                        bc = str(v.get("barcode") or "")
                        if len(bc) == BARKOD_UZUNLUK and bc.isdigit():
                            kayit["barkod"][bc[:6]] = kayit["barkod"].get(bc[:6], 0) + 1
                if sayfa >= d.get("totalPages", 1) - 1:
                    break
                sayfa += 1
        return sayim

    return _cached("kategori_taramasi", _uret, ttl_sn=1800)


def onek_oner(kategori_ad: str) -> dict:
    """Kategorinin barkod öneki (öğrenilmişse) — yoksa None, kullanıcı elle girer."""
    kayit = (_kategori_taramasi().get((kategori_ad or "").strip()) or {}).get("barkod") or {}
    if kayit:
        onek = max(kayit, key=kayit.get)
        return {"onek": onek, "ornek": kayit[onek]}
    return {"onek": None, "ornek": 0}


def model_onek_oner(kategori_ad: str) -> str:
    """Kategorinin model kodu öneki (öğrenilmişse) — yoksa varsayılan '01'."""
    kayit = (_kategori_taramasi().get((kategori_ad or "").strip()) or {}).get("model") or {}
    return max(kayit, key=kayit.get) if kayit else "01"


# ------------------------------------------------------------- kod tahsisleri

def _dolu_kodlar() -> tuple[set, set]:
    """Trendyol'daki (onaylı arşivli dahil + onaysız) tüm barkodlar ve model kodları."""
    barkodlar, modeller = set(), set()
    for uc in ("approved", "unapproved"):
        sayfa = 0
        while True:
            d = _get(f"{BASE}/sellers/{SUPPLIER_ID}/products/{uc}?size=100&page={sayfa}", timeout=90)
            for c in d.get("content", []):
                mid = str(c.get("productMainId") or "").strip()
                if mid:
                    modeller.add(mid)
                for v in c.get("variants") or []:
                    bc = str(v.get("barcode") or "").strip()
                    if bc:
                        barkodlar.add(bc)
            if sayfa >= d.get("totalPages", 1) - 1:
                break
            sayfa += 1
    return barkodlar, modeller


def _rezerv_kaydi(olustur: bool = False) -> PlatformConfig | None:
    # with_for_update: eşzamanlı iki tahsis aynı satırı okuyup birbirinin
    # rezervini ezmesin (lost update) — kilit commit'e kadar tutulur.
    kayit = (PlatformConfig.query.filter_by(platform="urun_yukleme")
             .with_for_update().first())
    if kayit is None and olustur:
        kayit = PlatformConfig(platform="urun_yukleme", is_active=True, extra_config={})
        db.session.add(kayit)
        db.session.flush()
    return kayit


def _rezervler() -> tuple[set, set]:
    """Panelden tahsis edilmiş ama Trendyol listesinde henüz görünmeyebilecek kodlar.

    ÖNEMLİ: Onay sürecindeki içerikler approved/unapproved listelerinde geçici
    olarak görünmeyebiliyor — bu rezerv listesi o boşluğu kapatır.
    """
    kayit = _rezerv_kaydi()
    cfg = (kayit.extra_config or {}) if kayit else {}
    return set(cfg.get("rezerv_barkod") or []), set(cfg.get("rezerv_model") or [])


def talimat_getir() -> str:
    """Kalıcı özel talimatlar (AI her taslak üretiminde uygular) — salt okuma, kilitsiz."""
    kayit = PlatformConfig.query.filter_by(platform="urun_yukleme").first()
    return ((kayit.extra_config or {}).get("genel_talimat") or "") if kayit else ""


def talimat_kaydet(metin: str) -> None:
    kayit = _rezerv_kaydi(olustur=True)
    kayit.extra_config = {**(kayit.extra_config or {}), "genel_talimat": (metin or "").strip()[:8000]}
    db.session.commit()


_MODEL_ADI_DESENI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")  # alt sürece gidiyor


def claude_model_getir() -> str:
    """'urun' alanının Claude modeli (boş = ai_asistan varsayılanı: opus)."""
    kayit = PlatformConfig.query.filter_by(platform="urun_yukleme").first()
    return ((kayit.extra_config or {}).get("claude_model") or "") if kayit else ""


def claude_model_kaydet(model: str) -> None:
    model = (model or "").strip()
    if model and not _MODEL_ADI_DESENI.match(model):
        raise ValueError(f"Geçersiz model adı: {model}")
    kayit = _rezerv_kaydi(olustur=True)
    kayit.extra_config = {**(kayit.extra_config or {}), "claude_model": model}
    db.session.commit()


def rezerv_ekle(model_kodu: str, barkodlar: list[str]) -> None:
    kayit = _rezerv_kaydi(olustur=True)
    cfg = dict(kayit.extra_config or {})
    cfg["rezerv_barkod"] = (list(cfg.get("rezerv_barkod") or []) + list(barkodlar))[-1000:]
    cfg["rezerv_model"] = (list(cfg.get("rezerv_model") or []) + [model_kodu])[-200:]
    kayit.extra_config = cfg
    db.session.commit()


def kod_oner(onek: str, renk_sayisi: int, beden_sayisi: int,
             model_onek: str = "01", ozel_model: str | None = None) -> dict:
    """
    Model kodu + renk başına ardışık barkod bloğu önerir.
    - ozel_model verilirse (kullanıcı belirledi) doluluk kontrolüyle aynen kullanılır.
    - verilmezse kategorinin KENDİ model serisinden (model_onek, ör. '01') devam edilir.
    """
    onek = (onek or VARSAYILAN_ONEK).strip()
    if not (onek.isdigit() and 1 <= len(onek) <= BARKOD_UZUNLUK - 1):
        raise ValueError(f"Geçersiz barkod öneki: {onek!r} (rakam, en fazla {BARKOD_UZUNLUK - 1} hane)")
    hane = BARKOD_UZUNLUK - len(onek)

    dolu_bc, dolu_model = _dolu_kodlar()
    rez_bc, rez_model = _rezervler()
    dolu_bc |= rez_bc
    dolu_model |= rez_model

    # Model kodu
    if ozel_model:
        ozel_model = ozel_model.strip()
        if not (ozel_model.isdigit() and 3 <= len(ozel_model) <= 6):
            raise ValueError(f"Geçersiz model kodu: {ozel_model!r} (3-6 haneli rakam olmalı)")
        if ozel_model in dolu_model:
            raise ValueError(f"Model kodu {ozel_model} zaten kullanımda — başka bir kod seçin.")
        model_kodu = ozel_model
    else:
        model_onek = (model_onek or "01").strip()
        seri = {int(m[len(model_onek):]) for m in dolu_model
                if m.startswith(model_onek) and len(m) == len(model_onek) + 2
                and m.isdigit()}
        model_kodu = None
        if seri and max(seri) + 1 < 100:
            model_kodu = f"{model_onek}{max(seri) + 1:02d}"
        else:
            for n in range(0, 100):
                if n not in seri:
                    model_kodu = f"{model_onek}{n:02d}"
                    break
        if not model_kodu:
            raise ValueError(f"'{model_onek}XX' serisinde boş model kodu kalmadı — elle belirleyin.")

    # Barkod blokları: önekin en büyük dolu numarasından devam eden ardışık boşluk
    kullanilmis = set()
    for bc in dolu_bc:
        if bc.startswith(onek) and len(bc) == BARKOD_UZUNLUK and bc[len(onek):].isdigit():
            kullanilmis.add(int(bc[len(onek):]))
    aday = (max(kullanilmis) + 1) if kullanilmis else 0

    bloklar, gereken = [], renk_sayisi * beden_sayisi
    uretilen = 0
    while uretilen < gereken:
        if aday >= 10 ** hane:
            raise ValueError(f"'{onek}' önekinde barkod aralığı doldu — yeni önek belirlenmeli.")
        if aday in kullanilmis:
            aday += 1
            continue
        bloklar.append(f"{onek}{aday:0{hane}d}")
        uretilen += 1
        aday += 1

    renk_bloklari = [bloklar[i * beden_sayisi:(i + 1) * beden_sayisi] for i in range(renk_sayisi)]
    for b in bloklar:
        assert len(b) == BARKOD_UZUNLUK, b
    return {"model_kodu": model_kodu, "renk_bloklari": renk_bloklari}


# ------------------------------------------- zorunlu özellik güvencesi

WEB_COLOR_ID = 348
# Web Color'da birebir karşılığı olmayan mağaza renkleri → en yakın resmi renk
WEB_COLOR_ES = {"vizon": "bej", "krem": "ekru", "ten": "bej", "nude": "bej",
                "taba": "kahverengi", "camel": "kahverengi", "gold": "altın",
                "gümüş rengi": "gümüş", "leopar": "kahverengi"}
# Diğer zorunlularda güvenli varsayılanlar (ad → aranacak değer adı)
ZORUNLU_VARSAYILAN = {"cinsiyet": "kadın / kız", "yaş grubu": "yetişkin",
                      "menşei": "tr", "desen": "düz"}


def zorunlu_tamamla(cid: int, secimler: list[dict], renkler: list[str]) -> tuple[list, dict, list]:
    """
    Batch'e eksik zorunlu özellik gitmesin: seçimlerde olmayan zorunluları
    otomatik tamamlar. Döner: (ortak_ek, renk_web_color, tamamlanamayanlar).
    - Web Color RENK BAŞINA eşlenir (Kırmızı→Kırmızı, Vizon→Bej ...).
    - Cinsiyet/Yaş/Menşei/Desen güvenli varsayılanla doldurulur.
    """
    secili_idler = {int(s.get("attributeId")) for s in secimler if s.get("attributeId")}
    ortak_ek, renk_web_color, eksikler = [], {}, []
    for o in kategori_ozellikleri(cid):
        if not o.get("zorunlu") or o.get("varyant") or (o.get("ad") or "") == "Renk":
            continue
        if o["id"] in secili_idler:
            continue
        degerler = {str(v["ad"]).strip().lower(): v["id"]
                    for v in ozellik_degerleri(cid, o["id"])}
        if o["id"] == WEB_COLOR_ID:
            for renk in renkler:
                r = renk.strip().lower()
                deger_id = degerler.get(r) or degerler.get(WEB_COLOR_ES.get(r, "")) \
                    or degerler.get("çok renkli")
                if deger_id:
                    renk_web_color[renk] = {"attributeId": WEB_COLOR_ID,
                                            "attributeValueId": deger_id}
                else:
                    eksikler.append(f"Web Color ({renk})")
            continue
        hedef = ZORUNLU_VARSAYILAN.get((o.get("ad") or "").strip().lower())
        deger_id = degerler.get(hedef) if hedef else None
        if deger_id:
            ortak_ek.append({"attributeId": o["id"], "attributeValueId": deger_id})
        elif o.get("serbest"):
            continue  # serbest zorunlu: boş bırakılabilirlik kategoriye kalmış, zorlamayalım
        else:
            eksikler.append(o.get("ad") or str(o["id"]))
    return ortak_ek, renk_web_color, eksikler


def mevcut_model_kodlari(model_kodu: str, renkler: list[str], bedenler: list[str]) -> dict:
    """
    Model zaten Trendyol'daysa mevcut barkodlarını getirir (yeniden tahsis YOK —
    Shopify/Trendyol barkod tutarlılığı). stockCode deseni: '<model>-<beden> <Renk>'.
    Döner: {renk: [beden sırasında barkodlar]} — yalnız TAM bloklar dahil edilir.
    """
    harita: dict = {}
    for uc in ("approved", "unapproved"):
        d = _get(f"{BASE}/sellers/{SUPPLIER_ID}/products/{uc}"
                 f"?productMainId={model_kodu}&size=100", timeout=90)
        for c in d.get("content", []):
            for v in c.get("variants") or []:
                sc = str(v.get("stockCode") or "")
                bc = str(v.get("barcode") or "")
                if not (sc.startswith(f"{model_kodu}-") and bc):
                    continue
                kalan = sc[len(model_kodu) + 1:]
                parcalar = kalan.split(" ", 1)
                if len(parcalar) == 2:
                    beden, renk = parcalar[0].strip(), parcalar[1].strip()
                    harita.setdefault(renk, {})[beden] = bc
    sonuc = {}
    for renk in renkler:
        kayit = harita.get(renk) or {}
        if all(b in kayit for b in bedenler):
            sonuc[renk] = [kayit[b] for b in bedenler]
    return sonuc


# ------------------------------------------------------------------ denetim

def yasak_tara(*metinler: str) -> list[str]:
    """Başlık/açıklamada yasaklı söylemleri bulur (alt-dize eşleşmesi, bilinçli)."""
    bulunan = []
    for metin in metinler:
        m = (metin or "").lower()
        for k in YASAKLI_KELIMELER:
            if k in m and k not in bulunan:
                bulunan.append(k)
        if _YIL_DESENI.search(m) and "yıl (2026 gibi)" not in bulunan:
            bulunan.append("yıl (2026 gibi)")
    return bulunan


def baslik_denetle(baslik: str) -> str | None:
    """95-100 karakter kuralı + yasak tarama. Hata metni ya da None döner."""
    n = len(baslik or "")
    if not 95 <= n <= 100:
        return f"Başlık {n} karakter — 95-100 aralığında olmalı."
    yasak = yasak_tara(baslik)
    if yasak:
        return f"Başlıkta yasaklı ifade: {', '.join(yasak)}"
    return None


def trendyol_urun_paketi(model_kodu: str) -> dict:
    """
    Trendyol'daki mevcut ürünü 'aktarım paketi'ne çevirir (tek tıkla Shopify'a
    taşıma için): renkler, bedenler, MEVCUT barkodlar, fiyat, teknik özellikler,
    renk başına görsel URL'leri ve ham açıklama.
    """
    icerikler = []
    for uc in ("approved", "unapproved"):
        d = _get(f"{BASE}/sellers/{SUPPLIER_ID}/products/{uc}"
                 f"?productMainId={model_kodu}&size=100", timeout=90)
        icerikler += d.get("content") or []
    if not icerikler:
        raise ValueError(f"Trendyol'da {model_kodu} modeli bulunamadı.")

    paket = {"model_kodu": model_kodu, "renkler": [], "bedenler": [],
             "gorseller": {}, "barkodlar": {}, "teknik": [], "aciklama_ham": "",
             "kategori_ad": "", "baslik": "", "satis_fiyat": None, "liste_fiyat": None}
    bedenler = set()
    for c in icerikler:
        attrs = {a.get("attributeName"): a.get("attributeValue")
                 for a in c.get("attributes") or []}
        renk = (attrs.get("Renk") or "").strip()
        paket["kategori_ad"] = paket["kategori_ad"] or (c.get("category") or {}).get("name", "")
        paket["baslik"] = paket["baslik"] or (c.get("title") or "")
        paket["aciklama_ham"] = paket["aciklama_ham"] or (c.get("description") or "")
        for ad, deger in attrs.items():
            satir = f"{ad}: {deger}"
            if ad not in ("Renk",) and deger and satir not in paket["teknik"]:
                paket["teknik"].append(satir)
        for v in c.get("variants") or []:
            sc = str(v.get("stockCode") or "")
            bc = str(v.get("barcode") or "")
            # stockCode 'model-beden Renk' → renk content'te yoksa buradan
            if sc.startswith(f"{model_kodu}-"):
                parcalar = sc[len(model_kodu) + 1:].split(" ", 1)
                beden = parcalar[0].strip()
                if not renk and len(parcalar) == 2:
                    renk = parcalar[1].strip()
            else:
                beden = next((a.get("attributeValue") for a in v.get("attributes") or []
                              if a.get("attributeName") == "Beden"), "")
            if not (renk and beden and bc):
                continue
            bedenler.add(beden)
            paket["barkodlar"].setdefault(renk, {})[beden] = bc
            fiyat = v.get("price") or {}
            paket["satis_fiyat"] = paket["satis_fiyat"] or fiyat.get("salePrice")
            paket["liste_fiyat"] = paket["liste_fiyat"] or fiyat.get("listPrice")
        if renk and renk not in paket["renkler"]:
            paket["renkler"].append(renk)
            paket["gorseller"][renk] = [g.get("url") for g in c.get("images") or []
                                        if g.get("url")][:8]
    paket["bedenler"] = sorted(bedenler, key=lambda b: (len(b), b))
    if not paket["renkler"]:
        raise ValueError(f"{model_kodu}: renk bilgisi çözülemedi (Renk özelliği/stok kodu biçimi).")
    return paket


# ------------------------------------------------------------------ gönderim

def urun_gonder(items: list[dict]) -> str:
    """Ürün Yaratma v2 — batchRequestId döner."""
    r = requests.post(f"{BASE}/sellers/{SUPPLIER_ID}/v2/products",
                      headers=_headers(), json={"items": items}, timeout=120)
    if r.status_code not in (200, 202):
        raise RuntimeError(f"Trendyol HTTP {r.status_code}: {r.text[:600]}")
    return r.json().get("batchRequestId") or ""


def batch_durum(batch_id: str) -> dict:
    """Batch sonucu: {durum, toplam, hatali, hatalar:[(barkod, sebep)]}."""
    d = _get(f"{BASE}/sellers/{SUPPLIER_ID}/products/batch-requests/{batch_id}")
    hatalar = []
    for it in d.get("items", []):
        if it.get("failureReasons"):
            bc = (it.get("requestItem") or {}).get("barcode")
            hatalar.append({"barkod": bc, "sebepler": it["failureReasons"]})
    return {"durum": d.get("status"), "toplam": d.get("itemCount"),
            "hatali": d.get("failedItemCount"), "hatalar": hatalar}


def onay_durumu(model_kodu: str) -> dict:
    """Modelin onay kuyruğu / satış durumu özeti."""
    sonuc = {}
    for uc in ("unapproved", "approved"):
        d = _get(f"{BASE}/sellers/{SUPPLIER_ID}/products/{uc}?productMainId={model_kodu}&size=100")
        adet, satista = 0, 0
        for c in d.get("content", []):
            varyantlar = c.get("variants") or []
            adet += len(varyantlar) or 1
            satista += sum(1 for v in varyantlar if v.get("onSale"))
        sonuc[uc] = {"kayit": d.get("totalElements", 0), "varyant": adet, "satista": satista}
    return sonuc
