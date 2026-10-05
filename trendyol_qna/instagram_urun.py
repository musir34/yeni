"""
Instagram gönderisi ↔ site ürünü eşlemesi.

"Fiyat nedir?" gibi yorumlarda ürün yorumdan anlaşılmaz; gönderi bir kez bir
site (Shopify) ürününe ve rengine bağlanır, o gönderiye gelen bütün yorumların
AI taslağı ürünün CANLI site fiyatı, stoktaki bedenleri ve sayfa bağlantısıyla
hazırlanır.

- Bağlamayı yapay zekâ önerir (confirmed=False), kullanıcı panelde onaylar.
  Onaylanmamış öneri taslağa fiyat olarak GİRMEZ — yanlış ürüne fiyat verilmesin.
- Fiyat/stok her taslakta Shopify'dan yeniden okunur; tabloda yalnız ürün
  kimliği, başlığı ve adresi saklanır.
"""
import logging
import re
import threading
import time
from datetime import datetime, timezone

from models import db, InstagramComment, InstagramMediaProduct

logger = logging.getLogger(__name__)

SITE_URL = "https://www.gullushoes.com"
ARAMA_LIMIT = 8
KATALOG_OMRU_SN = 600
KATALOG_SAYFA = 100
KATALOG_AZAMI = 600
OTOMATIK_TASLAK_AZAMI = 15   # bir gönderi bağlanınca en çok kaç bekleyen yoruma taslak üretilir

_URUN_ALANLARI = """
  legacyResourceId title handle status onlineStoreUrl
  featuredImage{ url }
  variants(first:100){ nodes{ title price compareAtPrice inventoryQuantity availableForSale } }
"""
_ARAMA_SORGUSU = """
query($first:Int!, $query:String, $after:String){
  products(first:$first, query:$query, after:$after, sortKey:TITLE){
    pageInfo{ hasNextPage endCursor }
    nodes{ %s }
  }
}""" % _URUN_ALANLARI
_URUN_SORGUSU = "query($id:ID!){ product(id:$id){ %s } }" % _URUN_ALANLARI


def _shopify(query: str, variables: dict) -> dict:
    """Shopify GraphQL çağrısı; hata → {} (çağıran 'bulunamadı' gibi davranır)."""
    from shopify_site.shopify_service import shopify_service
    sonuc = shopify_service.run_graphql(query, variables)
    if not sonuc.get("success"):
        logger.warning("[INSTAGRAM-URUN] Shopify sorgusu başarısız: %s", str(sonuc.get("error"))[:300])
        return {}
    return sonuc.get("data") or {}


def _sayi(deger) -> float | None:
    try:
        return float(deger)
    except (TypeError, ValueError):
        return None


def _tl(tutar: float) -> str:
    """1749.99 → '1.749,99 TL'"""
    return f"{tutar:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " TL"


def _renk_beden(varyant_basligi: str) -> tuple[str, str]:
    """'Bej Leopar / 36' → ('Bej Leopar', '36'); tek parçaysa renk boş kalır."""
    parcalar = [p.strip() for p in (varyant_basligi or "").split("/")]
    if len(parcalar) >= 2:
        return parcalar[0], parcalar[-1]
    return "", parcalar[0] if parcalar else ""


def _sadelestir(node: dict) -> dict:
    """Shopify ürün düğümünü panelin kullandığı yalın sözlüğe çevirir."""
    renkler: dict[str, dict] = {}
    for v in ((node.get("variants") or {}).get("nodes")) or []:
        renk, beden = _renk_beden(v.get("title"))
        kayit = renkler.setdefault(renk, {"renk": renk, "fiyat": None, "eski_fiyat": None, "bedenler": []})
        fiyat, eski = _sayi(v.get("price")), _sayi(v.get("compareAtPrice"))
        if fiyat is not None and (kayit["fiyat"] is None or fiyat < kayit["fiyat"]):
            kayit["fiyat"] = fiyat
            kayit["eski_fiyat"] = eski if (eski and eski > fiyat) else None
        try:
            adet = int(v.get("inventoryQuantity") or 0)
        except (TypeError, ValueError):
            adet = 0
        kayit["bedenler"].append({"beden": beden, "stokta": adet > 0 and v.get("availableForSale") is not False})
    handle = node.get("handle") or ""
    return {
        "id": str(node.get("legacyResourceId") or ""),
        "title": node.get("title") or "",
        "url": node.get("onlineStoreUrl") or (f"{SITE_URL}/products/{handle}" if handle else ""),
        "gorsel": ((node.get("featuredImage") or {}).get("url")) or "",
        "aktif": node.get("status") == "ACTIVE",
        "renkler": list(renkler.values()),
    }


def urun_ara(q: str, limit: int = ARAMA_LIMIT) -> list[dict]:
    """Sitedeki aktif ürünlerde ara (panelde 'Ürün bağla' kutusu)."""
    q = re.sub(r"[^\w\s\-]", " ", (q or ""), flags=re.UNICODE).strip()[:80]
    if len(q) < 2:
        return []
    data = _shopify(_ARAMA_SORGUSU, {"first": max(1, min(limit, 25)), "query": f"status:active {q}", "after": None})
    return [_sadelestir(n) for n in ((data.get("products") or {}).get("nodes")) or []]


def urun_getir(product_id: str) -> dict | None:
    if not re.fullmatch(r"\d{1,20}", str(product_id or "")):
        return None
    data = _shopify(_URUN_SORGUSU, {"id": f"gid://shopify/Product/{product_id}"})
    node = data.get("product")
    return _sadelestir(node) if isinstance(node, dict) else None


_katalog_kilit = threading.Lock()
_katalog: tuple[float, list[dict]] = (0.0, [])


def katalog() -> list[dict]:
    """Aktif ürünlerin (id, başlık, renkler) listesi — AI önerisi için, 10 dk bellekte."""
    global _katalog
    with _katalog_kilit:
        zaman, liste = _katalog
        if liste and time.monotonic() - zaman < KATALOG_OMRU_SN:
            return liste
    liste, sonra = [], None
    while len(liste) < KATALOG_AZAMI:
        data = _shopify(_ARAMA_SORGUSU, {"first": KATALOG_SAYFA, "query": "status:active", "after": sonra})
        sayfa = data.get("products") or {}
        liste.extend(_sadelestir(n) for n in sayfa.get("nodes") or [])
        bilgi = sayfa.get("pageInfo") or {}
        if not bilgi.get("hasNextPage"):
            break
        sonra = bilgi.get("endCursor")
    with _katalog_kilit:
        _katalog = (time.monotonic(), liste)
    return liste


# ── Bağlama ──────────────────────────────────────────────────────────────────

def bagli_urun(media_id: str) -> InstagramMediaProduct | None:
    if not media_id:
        return None
    return InstagramMediaProduct.query.filter_by(media_id=str(media_id)).first()


def bagla(media_id: str, product_id: str, renk: str = "", username: str | None = None,
          confirmed: bool = True) -> dict:
    """Gönderiyi site ürününe (ve isteğe bağlı rengine) bağla. Dönen: {'ok', 'hata'}"""
    urun = urun_getir(product_id)
    if not urun:
        return {"ok": False, "hata": "Ürün sitede bulunamadı."}
    renk = (renk or "").strip()
    renk_adlari = [r["renk"] for r in urun["renkler"]]
    if renk and renk not in renk_adlari:
        return {"ok": False, "hata": "Bu üründe böyle bir renk yok."}
    if not renk and len(renk_adlari) == 1:
        renk = renk_adlari[0]

    satir = bagli_urun(media_id)
    if satir is None:
        satir = InstagramMediaProduct(media_id=str(media_id))
        db.session.add(satir)
    elif satir.confirmed and not confirmed:
        return {"ok": True, "hata": None}   # kullanıcının onayladığı bağ AI önerisiyle ezilmez
    satir.shopify_product_id = urun["id"]
    satir.title = urun["title"][:300]
    satir.url = urun["url"][:500]
    satir.color = renk[:120]
    satir.confirmed = bool(confirmed)
    satir.updated_by = username or ("AI önerisi" if not confirmed else "panel")
    satir.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return {"ok": True, "hata": None}


def bagi_kaldir(media_id: str) -> None:
    satir = bagli_urun(media_id)
    if satir is not None:
        db.session.delete(satir)
        db.session.commit()


def bekleyen_taslaksiz_yorumlar(media_id: str) -> list[int]:
    """Bağ onaylanınca taslağı üretilecek bekleyen yorumlar (en yeniler, sınırlı sayıda)."""
    satirlar = (
        db.session.query(InstagramComment.id)
        .filter(InstagramComment.media_id == str(media_id), InstagramComment.status == "new")
        .filter(InstagramComment.ai_draft_status.in_(("none", "failed")) | InstagramComment.ai_draft_status.is_(None))
        .order_by(InstagramComment.created_at.desc())
        .limit(OTOMATIK_TASLAK_AZAMI)
        .all()
    )
    return [s[0] for s in satirlar]


# ── AI promptu için ürün bilgisi ─────────────────────────────────────────────

def urun_baglami(media_id: str) -> str | None:
    """Onaylı bağ varsa ürünün canlı fiyat/stok/bağlantı özetini üret; yoksa None."""
    satir = bagli_urun(media_id)
    if satir is None or not satir.confirmed:
        return None
    urun = urun_getir(satir.shopify_product_id)
    if not urun:
        return (f"Bu gönderi '{satir.title}' ürününe bağlı ama ürün şu an siteden okunamadı; "
                "fiyat ya da stok sözü verme.")
    renkler = [r for r in urun["renkler"] if not satir.color or r["renk"] == satir.color] or urun["renkler"]
    satirlar = []
    for r in renkler:
        if r["fiyat"] is None:
            continue
        fiyat = _tl(r["fiyat"])
        if r["eski_fiyat"]:
            fiyat += f" (indirimli; eski fiyat {_tl(r['eski_fiyat'])})"
        var = [b["beden"] for b in r["bedenler"] if b["stokta"] and b["beden"]]
        yok = [b["beden"] for b in r["bedenler"] if not b["stokta"] and b["beden"]]
        stok = ("stokta olan numaralar: " + ", ".join(var)) if var else "şu an stokta numara yok"
        if var and yok:
            stok += "; tükenenler: " + ", ".join(yok)
        satirlar.append(f"- {r['renk'] or 'Tek renk'}: {fiyat} — {stok}")
    return (
        f"Bu gönderideki ürün (kullanıcı onaylı): {urun['title']}\n"
        f"Ürün sayfası: {urun['url']}\n"
        f"Sitedeki güncel fiyat ve stok{'' if urun['aktif'] else ' (DİKKAT: ürün sitede yayında değil)'}:\n"
        + ("\n".join(satirlar) or "- fiyat bilgisi okunamadı")
    )


# ── AI ürün önerisi ──────────────────────────────────────────────────────────

def _oneri_promptu(caption: str, urunler: list[dict]) -> str:
    satirlar = []
    for u in urunler:
        renkler = ", ".join(r["renk"] for r in u["renkler"] if r["renk"])
        satirlar.append(f"{u['id']} | {u['title']}" + (f" | renkler: {renkler}" if renkler else ""))
    return (
        "Bu bir müşteri sorusu DEĞİL; sınıflandırma görevi. Müşteriye cevap yazma.\n"
        "Aşağıda bir Instagram gönderimizin açıklaması ve sitemizdeki ürün listesi var. "
        "Gönderinin hangi ürünü tanıttığını bul.\n"
        "Yalnızca şu biçimde TEK satır yaz, başka hiçbir şey ekleme:\n"
        "URUN: <ürün numarası> | RENK: <listeden renk adı ya da boş>\n"
        "Emin değilsen ya da açıklama tek bir ürünü işaret etmiyorsa: URUN: YOK\n\n"
        f"Gönderi açıklaması:\n{(caption or '(açıklama yok)')[:1500]}\n\n"
        "Ürün listesi (numara | başlık | renkler):\n" + "\n".join(satirlar)
    )


def oner(media_id: str) -> bool:
    """Gönderi için AI ürün önerisi üret ve onaysız kaydet (app context içinde). Öneri kaydedildiyse True."""
    if not media_id or bagli_urun(media_id) is not None:
        return False
    yorum = InstagramComment.query.filter_by(media_id=str(media_id)).first()
    caption = (yorum.media_caption if yorum else "") or ""
    if len(caption.strip()) < 10:
        return False
    urunler = katalog()
    if not urunler:
        return False
    from trendyol_qna.qna_ai import _run_ai
    cevap = _run_ai(_oneri_promptu(caption, urunler)) or ""
    eslesme = re.search(r"URUN:\s*(\d{5,20})(?:\s*\|\s*RENK:\s*([^\n|]*))?", cevap)
    if not eslesme:
        return False
    secilen = next((u for u in urunler if u["id"] == eslesme.group(1)), None)
    if not secilen:
        return False
    renk = (eslesme.group(2) or "").strip()
    if renk not in [r["renk"] for r in secilen["renkler"]]:
        renk = ""
    return bool(bagla(media_id, secilen["id"], renk, confirmed=False).get("ok"))


_oneri_kilit = threading.Lock()
_oneri_denenen: set[str] = set()   # süreç boyunca aynı gönderi için tek deneme


def oner_async(media_ids: list[str]) -> None:
    with _oneri_kilit:
        yeni = [m for m in dict.fromkeys(str(m) for m in media_ids if m) if m not in _oneri_denenen]
        _oneri_denenen.update(yeni)
    if not yeni:
        return

    def _worker():
        from app import app
        with app.app_context():
            for media_id in yeni:
                try:
                    oner(media_id)
                except Exception:
                    db.session.rollback()
                    logger.exception("[INSTAGRAM-URUN] ürün önerisi üretilemedi (gönderi %s)", media_id)

    threading.Thread(target=_worker, name="instagram-urun-oneri", daemon=True).start()


def taslaklari_uret_async(media_id: str, yenile: bool = False) -> None:
    """Onaylı bağı olan gönderinin taslaksız bekleyen yorumlarına taslak üret.

    yenile=True: bağ yeni onaylandı/değişti — ürünsüz ya da eski ürünle yazılmış
    hazır taslaklar da silinip yeniden üretilir (üretimi süren taslağa dokunulmaz).
    """
    satir = bagli_urun(media_id)
    if satir is None or not satir.confirmed:
        return
    if yenile:
        (db.session.query(InstagramComment)
         .filter(InstagramComment.media_id == str(media_id), InstagramComment.status == "new",
                 InstagramComment.ai_draft_status == "ready")
         .update({"ai_draft": None, "ai_draft_status": "none"}, synchronize_session=False))
        db.session.commit()
    from trendyol_qna.qna_ai import generate_instagram_comment_drafts_async
    generate_instagram_comment_drafts_async(bekleyen_taslaksiz_yorumlar(media_id))
