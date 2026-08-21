# -*- coding: utf-8 -*-
"""
Shopify'a ürün açma — tema RENK KURALINA göre (0122 birleştirmesinde kanıtlandı):
TEK ürün + Renk/Beden seçenekleri; galeri renk bloklu; her bloğun İLK görseli o
rengin tüm varyantlarına kapak (renk daireleri bu görseli kullanır); SEO alanları
(seo.title ≤60, seo.description, ALT metinleri) dolu; renk-* etiketleri akıllı
koleksiyonları besler; ürün tüm satış kanallarına yayınlanır.
"""
import logging

from .gorsel import _graphql

logger = logging.getLogger(__name__)

VENDOR = "Güllü Shoes"

_TR_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ ", "cgiosucgiosu-")


def _slug(metin: str) -> str:
    s = (metin or "").translate(_TR_ASCII).lower()
    return "".join(c for c in s if c.isalnum() or c == "-").strip("-")


def _konum_id() -> str:
    d = _graphql("query { locations(first: 1) { nodes { id } } }", {})
    dugumler = d["locations"]["nodes"]
    if not dugumler:
        raise RuntimeError("Shopify lokasyonu bulunamadı.")
    return dugumler[0]["id"]


def _yayin_kanallari() -> list[str]:
    d = _graphql("query { publications(first: 10) { nodes { id } } }", {})
    return [n["id"] for n in d["publications"]["nodes"]]


def urun_ac(taslak: dict, form: dict, renk_gorselleri: dict) -> dict:
    """
    Taslaktan Shopify ürünü oluşturur. renk_gorselleri: {renk: [cdn_url, ...]}.
    Döner: {"product_id", "handle", "url"}
    """
    sh = taslak.get("shopify") or {}
    renkler = list(taslak["renkler"].keys())
    bedenler = taslak["bedenler"]
    model = taslak["model_kodu"]
    urun_tipi = (form.get("kategori_yolu") or "").split(" > ")[-1] or "Ayakkabı"
    konum = _konum_id()

    handle = f"{model}-{_slug(sh.get('h1') or form.get('urun_turu') or urun_tipi)}"[:255]
    etiketler = ["Kadın", urun_tipi] + [f"renk-{_slug(r)}" for r in renkler]

    dosyalar, varyantlar = [], []
    for renk in renkler:
        urller = renk_gorselleri.get(renk) or []
        for i, url in enumerate(urller, 1):
            dosyalar.append({"originalSource": url, "contentType": "IMAGE",
                             "alt": f"{renk} {sh.get('h1') or urun_tipi} {i}"})
        blok = taslak["renkler"][renk]["barkodlar"]
        for beden, barkod in zip(bedenler, blok):
            varyantlar.append({
                "optionValues": [{"optionName": "Renk", "name": renk},
                                 {"optionName": "Beden", "name": beden}],
                "sku": f"{model}-{beden} {renk}",
                "barcode": barkod,
                "price": f"{float(form['satis_fiyat']):.2f}",
                "compareAtPrice": f"{float(form['liste_fiyat']):.2f}",
                "inventoryQuantities": [{"locationId": konum, "name": "available",
                                         "quantity": int(form.get("stok", 5))}],
            })

    girdi = {
        "title": sh.get("h1") or form.get("urun_turu") or urun_tipi,
        "handle": handle,
        "descriptionHtml": sh.get("aciklama") or "",
        "seo": {"title": sh.get("seo_baslik") or "", "description": sh.get("seo_aciklama") or ""},
        "vendor": VENDOR,
        "productType": urun_tipi,
        "status": "ACTIVE",
        "tags": etiketler,
        "productOptions": [
            {"name": "Renk", "position": 1, "values": [{"name": r} for r in renkler]},
            {"name": "Beden", "position": 2, "values": [{"name": b} for b in bedenler]},
        ],
        "files": dosyalar,
        "variants": varyantlar,
    }
    d = _graphql("""
        mutation urunAc($input: ProductSetInput!) {
          productSet(synchronous: true, input: $input) {
            product {
              id handle
              media(first: 50) { nodes { id alt } }
              variants(first: 50) { nodes { id title } }
            }
            userErrors { code field message }
          }
        }""", {"input": girdi},
        timeout=300)  # senkron productSet çok varyant/görselde 60 sn'yi aşabilir
    hatalar = d["productSet"]["userErrors"]
    if hatalar:
        raise RuntimeError(f"Shopify productSet: {hatalar}")
    urun = d["productSet"]["product"]

    _kapaklari_ata(urun, renkler, renk_gorselleri)
    _yayinla(urun["id"])

    return {"product_id": urun["id"], "handle": urun["handle"],
            "url": f"https://www.gullushoes.com/products/{urun['handle']}"}


def _kapaklari_ata(urun: dict, renkler: list[str], renk_gorselleri: dict) -> None:
    """
    Her rengin İLK görselini o rengin tüm varyantlarına kapak yap (swatch görseli).
    Eşleme SIRAYLA yapılır: productSet files sırası korunur, blok başlangıçları
    renk başına görsel sayısından hesaplanır (ad/önek tahmini yok — "Bej"/"Bej Rugan"
    gibi önek çakışan renk adlarında bile şaşmaz).
    """
    medya = urun["media"]["nodes"]
    kapaklar, konum = {}, 0
    for renk in renkler:
        adet = len(renk_gorselleri.get(renk) or [])
        if adet and konum < len(medya):
            kapaklar[renk] = medya[konum]["id"]
        konum += adet
    atama = []
    for v in urun["variants"]["nodes"]:
        renk = (v.get("title") or "").split(" / ")[0]
        if kapaklar.get(renk):
            atama.append({"variantId": v["id"], "mediaIds": [kapaklar[renk]]})
    if not atama:
        logger.warning("[SHOPIFY-URUN] kapak ataması boş kaldı (%s)", urun.get("handle"))
        return
    d = _graphql("""
        mutation kapak($productId: ID!, $variantMedia: [ProductVariantAppendMediaInput!]!) {
          productVariantAppendMedia(productId: $productId, variantMedia: $variantMedia) {
            userErrors { field message }
          }
        }""", {"productId": urun["id"], "variantMedia": atama})
    hatalar = d["productVariantAppendMedia"]["userErrors"]
    if hatalar:
        logger.warning("[SHOPIFY-URUN] kapak atama uyarısı: %s", hatalar)


def _yayinla(product_id: str) -> None:
    kanallar = _yayin_kanallari()
    d = _graphql("""
        mutation yayinla($id: ID!, $input: [PublicationInput!]!) {
          publishablePublish(id: $id, input: $input) { userErrors { field message } }
        }""", {"id": product_id,
               "input": [{"publicationId": k} for k in kanallar]})
    hatalar = d["publishablePublish"]["userErrors"]
    if hatalar:
        logger.warning("[SHOPIFY-URUN] yayınlama uyarısı: %s", hatalar)
