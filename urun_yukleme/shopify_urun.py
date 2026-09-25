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


def _beden_anahtar(b: str) -> tuple[int, float, str]:
    """Sayısal sıralama: '35,5' → 35.5 (35 < 35,5 < 36); sayı olmayanlar sona."""
    try:
        return (0, float(str(b).strip().replace(",", ".")), "")
    except ValueError:
        return (1, 0.0, str(b))


def bedenleri_sirala(bedenler: list[str]) -> list[str]:
    """Sitede beden sırası seçenek değerlerinin sırasıdır: 35, 35,5, 36, 36,5 ...
    (kullanıcı emri — önce tamlar sonra buçuklar dizilimi yanlış)."""
    return sorted(bedenler, key=_beden_anahtar)


def _beden_secenegini_sirala(pid: str, beden_opt: dict, degerler: list[str]) -> None:
    """Sitedeki Beden seçeneğinin değerlerini sayısal sıraya koyar (productOptionsReorder)."""
    sirali = bedenleri_sirala(degerler)
    if sirali == list(degerler):
        return
    d = _graphql("""
        mutation bedenSirala($productId: ID!, $options: [OptionReorderInput!]!) {
          productOptionsReorder(productId: $productId, options: $options) {
            userErrors { field message code }
          }
        }""", {"productId": pid,
               "options": [{"id": beden_opt["id"], "values": [{"name": b} for b in sirali]}]})
    hatalar = d["productOptionsReorder"]["userErrors"]
    if hatalar:
        logger.warning("[SHOPIFY-URUN] beden sıralama uyarısı: %s", hatalar)


def gorsel_alt(taslak: dict, renk: str, i: int, varsayilan: str) -> str:
    """
    Görselin ALT metni: AI'nın görsele bakarak yazdığı metin (taslak.renkler[renk].alt,
    önizlemede düzeltilebilir) varsa o; yoksa şablon. Google Görseller ALT'ı okur —
    her görselde benzersiz, açıklayıcı metin SEO için şarttır (kullanıcı emri).
    """
    altlar = (taslak.get("renkler") or {}).get(renk, {}).get("alt") or []
    if i - 1 < len(altlar) and str(altlar[i - 1]).strip():
        return str(altlar[i - 1]).strip()[:512]
    return varsayilan


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
                             "alt": gorsel_alt(taslak, renk, i,
                                               f"{renk} {sh.get('h1') or urun_tipi} {i}")})
        blok = taslak["renkler"][renk]["barkodlar"]
        for beden, barkod in zip(bedenler, blok):
            if not barkod:
                continue  # Trendyol'da olmayan ikili (yalnız-site taslağı) — siteye de açılmaz
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

    # Aynı barkod Shopify'da zaten bir üründeyse KOPYA AÇMA — o ürünü güncelle.
    # HER rengin ilk barkoduna bakılır: mevcut modele yeni renk eklenirken ilk
    # renk yeni (Shopify'da yok) olabilir, eski renklerin barkodu ürünü bulur.
    mevcut_pid = None
    for renk in renkler:
        ilk_barkod = (taslak["renkler"][renk]["barkodlar"] or [""])[0]
        mevcut_pid = _barkodla_urun_bul(ilk_barkod)
        if mevcut_pid:
            logger.info("[SHOPIFY-URUN] %s barkodu mevcut üründe (%s) — güncelleme yapılacak",
                        ilk_barkod, mevcut_pid)
            break

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
            {"name": "Beden", "position": 2, "values": [{"name": b} for b in bedenleri_sirala(bedenler)]},
        ],
        "files": dosyalar,
        "variants": varyantlar,
    }
    if mevcut_pid:
        girdi["id"] = mevcut_pid
        girdi.pop("handle", None)  # mevcut ürünün adresi korunur
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


def _barkodla_urun_bul(barkod: str) -> str | None:
    """Barkod Shopify'da kayıtlıysa ürün gid'ini döndürür (kopya ürünü önler)."""
    if not barkod:
        return None
    d = _graphql("""
        query bul($q: String!) {
          productVariants(first: 1, query: $q) { nodes { product { id } } }
        }""", {"q": f"barcode:{barkod}"})
    dugumler = d["productVariants"]["nodes"]
    return dugumler[0]["product"]["id"] if dugumler else None


def sitedeki_barkodlar(barkodlar: list[str]) -> dict:
    """
    Barkod listesinin Shopify'daki karşılığı (eksik tamamlama modunun temeli):
    {"pid": ürün gid|None, "handle", "title", "barkodlar": {barkod: ürün gid}}.
    Eşleşme YALNIZ barkodla yapılır (ad/SKU tahmini yok). Barkodlar birden çok
    ürüne dağılmışsa en çok barkodu taşıyan ürün esas alınır ve uyarı loglanır.
    """
    bulunan: dict[str, dict] = {}
    temiz = [b for b in dict.fromkeys(barkodlar) if b]
    for i in range(0, len(temiz), 40):  # arama dizgisi çok uzamasın
        parca = temiz[i:i + 40]
        q = " OR ".join(f"barcode:{b}" for b in parca)
        d = _graphql("""
            query bul($q: String!) {
              productVariants(first: 250, query: $q) {
                nodes { barcode product { id title handle } }
              }
            }""", {"q": q})
        for v in d["productVariants"]["nodes"]:
            bc = str(v.get("barcode") or "")
            if bc in parca:  # arama gevşek eşleyebilir — birebir doğrula
                bulunan[bc] = v["product"]
    if not bulunan:
        return {"pid": None, "handle": "", "title": "", "barkodlar": {}}
    sayim: dict[str, int] = {}
    for u in bulunan.values():
        sayim[u["id"]] = sayim.get(u["id"], 0) + 1
    pid = max(sayim, key=sayim.get)
    if len(sayim) > 1:
        logger.warning("[SHOPIFY-URUN] barkodlar %d ayrı üründe: %s — %s esas alındı",
                       len(sayim), sayim, pid)
    urun = next(u for u in bulunan.values() if u["id"] == pid)
    return {"pid": pid, "handle": urun.get("handle") or "", "title": urun.get("title") or "",
            "barkodlar": {bc: u["id"] for bc, u in bulunan.items()}}


def site_kapaksiz_renkler(pid: str) -> list[str]:
    """
    Sitedeki üründe hiçbir varyantına görsel bağlanmamış renkler (vitrin bu
    renklerde ürünün ilk görselini gösterir — 011'de tüm renkler siyah çıkıyordu).
    Eksik tamamlama modunda bu renklere yüklenen görsel kapak olarak atanır.
    """
    d = _graphql("""
        query kapaksiz($id: ID!) {
          product(id: $id) {
            options { name }
            variants(first: 250) {
              nodes { selectedOptions { name value } media(first: 1) { nodes { id } } }
            }
          }
        }""", {"id": pid})
    urun = d.get("product") or {}
    secenekler = [o["name"] for o in urun.get("options") or []]
    renk_ad = "Renk" if "Renk" in secenekler else (secenekler[0] if secenekler else "")
    kapakli, hepsi = set(), []
    for v in (urun.get("variants") or {}).get("nodes") or []:
        renk = next((o["value"] for o in v.get("selectedOptions") or [] if o["name"] == renk_ad), "")
        if not renk:
            continue
        if renk not in hepsi:
            hepsi.append(renk)
        if (v.get("media") or {}).get("nodes"):
            kapakli.add(renk)
    return [r for r in hepsi if r not in kapakli]


def _medya_bekle(kimlikler: list[str]) -> None:
    """Yeni eklenen ürün medyası READY olana dek bekler (kapak ataması için şart)."""
    import time
    for _ in range(20):
        d = _graphql("""
            query medyaDurum($ids: [ID!]!) {
              nodes(ids: $ids) { ... on MediaImage { id status } }
            }""", {"ids": kimlikler})
        dugumler = [n for n in d["nodes"] if n]
        if dugumler and all(n.get("status") == "READY" for n in dugumler):
            return
        if any(n.get("status") == "FAILED" for n in dugumler):
            raise RuntimeError("Shopify ürün medyası FAILED döndü.")
        time.sleep(3)
    logger.warning("[SHOPIFY-URUN] medya zamanında READY olmadı, kapak ataması denenecek")


def eksik_tamamla(taslak: dict, form: dict, renk_gorselleri: dict) -> dict:
    """
    EKSİK TAMAMLAMA MODU: model sitede zaten varken yalnız sitede OLMAYAN
    (renk, beden) varyantlarını ekler. Mevcut varyant, medya, stok, başlık,
    açıklama ve SEO alanlarına DOKUNULMAZ (productSet tam-set yazımı yerine
    additive uçlar: productOptionUpdate + productUpdate(media) +
    productVariantsBulkCreate + productVariantAppendMedia).
    - Fark canlı barkod listesinden hesaplanır (taslak eskimiş olsa da güvenli).
    - Fiyat: sitedeki kardeş varyanttan (kullanıcı kararı), formdan değil.
    - Yeni renk: görselleri AI ALT'larıyla galeriye eklenir, ilk görsel kapak.
    - Mevcut renge yeni beden: görsel eklenmez, rengin mevcut kapağı bağlanır.
    Döner: {"product_id","handle","url","varyant","yeni_renkler","yeni_bedenler"}
    """
    pid = (taslak.get("shopify") or {}).get("mevcut_pid")
    if not pid:
        raise RuntimeError("Eksik tamamlama: sitedeki ürün kimliği taslakta yok.")
    d = _graphql("""
        query mevcut($id: ID!) {
          product(id: $id) {
            id title handle
            options { id name optionValues { id name } }
            media(first: 250) { nodes { id alt } }
            variants(first: 250) {
              nodes { id title barcode price compareAtPrice
                      selectedOptions { name value } media(first: 1) { nodes { id } } }
            }
          }
        }""", {"id": pid})
    urun = d["product"]
    if not urun:
        raise RuntimeError(f"Sitedeki ürün bulunamadı: {pid}")
    url = f"https://www.gullushoes.com/products/{urun['handle']}"
    mevcut_vs = urun["variants"]["nodes"]
    mevcut_bc = {str(v.get("barcode") or ""): v for v in mevcut_vs}

    def _secenek(v: dict, ad: str) -> str:
        return next((o["value"] for o in v.get("selectedOptions") or [] if o["name"] == ad), "")

    secenekler = {o["name"]: o for o in urun["options"]}
    renk_opt = secenekler.get("Renk") or (urun["options"][0] if urun["options"] else None)
    beden_opt = secenekler.get("Beden") or (urun["options"][1] if len(urun["options"]) > 1 else None)
    if not (renk_opt and beden_opt):
        raise RuntimeError("Sitedeki üründe Renk/Beden seçenekleri bulunamadı — elle kontrol edin.")
    renk_ad, beden_ad = renk_opt["name"], beden_opt["name"]
    sitedeki_renkler = {_secenek(v, renk_ad) for v in mevcut_vs}

    # Fark: sitede olmayan barkodlar (bire bir barkod eşlemesi)
    yeni = [(renk, beden, bc)
            for renk, r in taslak["renkler"].items()
            for beden, bc in zip(taslak["bedenler"], r["barkodlar"])
            if bc and bc not in mevcut_bc]

    # Mevcut renklerin kapağı: o rengin ilk varyantının medyası (canlı)
    kapaklar: dict[str, str] = {}
    for v in mevcut_vs:
        renk = _secenek(v, renk_ad)
        medya = (v.get("media") or {}).get("nodes") or []
        if renk and medya and renk not in kapaklar:
            kapaklar[renk] = medya[0]["id"]
    # KAPAKSIZ mevcut renkler: görsel yüklendiyse galeriye eklenip kapak yapılır
    # (canlıda hâlâ kapaksızsa; metne/varyanta dokunulmaz)
    kapak_renkleri = [r for r in (taslak.get("shopify") or {}).get("kapaksiz_renkler") or []
                      if r in sitedeki_renkler and r not in kapaklar and renk_gorselleri.get(r)]

    if not yeni and not kapak_renkleri:
        return {"product_id": pid, "handle": urun["handle"], "url": url, "varyant": 0,
                "mesaj": "Sitede tüm renk/beden varyantları zaten var — yeni gönderim gerekmedi."}
    # "Yeni renk" = sitede hiç VARYANTI olmayan renk (görselleriyle açılır).
    # Seçenek DEĞERİ ekleme ise mevcut değer listesine göre süzülür: yarım kalmış
    # bir denemede (medya eklendi, varyant düştü) tekrar yüklemede aynı değer
    # ikinci kez eklenmeye çalışılıp hata vermesin (idempotent tekrar).
    yeni_renkler = [r for r in dict.fromkeys(x[0] for x in yeni) if r not in sitedeki_renkler]
    renk_degerleri = {o["name"] for o in renk_opt["optionValues"]}
    yeni_renk_degerleri = [r for r in yeni_renkler if r not in renk_degerleri]
    yeni_bedenler = [b for b in dict.fromkeys(x[1] for x in yeni)
                     if b not in {o["name"] for o in beden_opt["optionValues"]}]

    # Fiyat kardeş varyanttan (siteyle tutarlı); site boşsa form
    if not mevcut_vs:
        raise RuntimeError("Sitedeki üründe varyant bulunamadı — fiyat devralınamaz, elle kontrol edin.")
    kardes = mevcut_vs[0]
    fiyat = kardes.get("price") or f"{float(form['satis_fiyat']):.2f}"
    liste = kardes.get("compareAtPrice") or f"{float(form['liste_fiyat']):.2f}"

    # 1) Seçenek değerleri (yeni renk / yeni beden) — mevcut değerlere dokunulmaz
    for opt, degerler in ((renk_opt, yeni_renk_degerleri), (beden_opt, yeni_bedenler)):
        if not degerler:
            continue
        d = _graphql("""
            mutation secenekEkle($productId: ID!, $option: OptionUpdateInput!,
                                 $optionValuesToAdd: [OptionValueCreateInput!]) {
              productOptionUpdate(productId: $productId, option: $option,
                                  optionValuesToAdd: $optionValuesToAdd) {
                userErrors { field message code }
              }
            }""", {"productId": pid, "option": {"id": opt["id"]},
                   "optionValuesToAdd": [{"name": x} for x in degerler]})
        hatalar = d["productOptionUpdate"]["userErrors"]
        if hatalar:
            raise RuntimeError(f"Shopify seçenek ekleme ({opt['name']}): {hatalar}")
    # Yeni beden sona eklenir (35..41 sonra 35,5..) → tüm listeyi sayısal sıraya koy
    if yeni_bedenler:
        _beden_secenegini_sirala(
            pid, beden_opt, [o["name"] for o in beden_opt["optionValues"]] + yeni_bedenler)

    # 2) Yeni renklerin + kapaksız mevcut renklerin görselleri galeriye (AI ALT
    #    ile); her bloğun ilk görseli o rengin kapağı
    # Yarım kalmış denemede aynı görsel (aynı ALT ile) galeride zaten varsa
    # yeniden yüklenmez; kapak o mevcut medya olur (çift galeri görseli olmaz).
    mevcut_alt = {}
    for m in urun["media"]["nodes"]:
        if m.get("alt") and m["alt"] not in mevcut_alt:
            mevcut_alt[m["alt"]] = m["id"]
    medya_girdi, blok_sira = [], []   # blok_sira: (renk, yeni yüklenen adet)
    urun_adi = urun.get("title") or form.get("urun_turu") or ""
    for renk in yeni_renkler + kapak_renkleri:
        urller = renk_gorselleri.get(renk) or []
        if not urller:
            raise RuntimeError(f"{renk} için görsel yok — yeni renk sitede görselsiz açılamaz.")
        adet = 0
        for i, u in enumerate(urller, 1):
            alt = gorsel_alt(taslak, renk, i, f"{renk} {urun_adi} {i}")
            if alt in mevcut_alt:
                if i == 1:
                    kapaklar[renk] = mevcut_alt[alt]
                continue
            medya_girdi.append({"originalSource": u, "mediaContentType": "IMAGE", "alt": alt})
            adet += 1
        blok_sira.append((renk, adet))
    if medya_girdi:
        onceki = {m["id"] for m in urun["media"]["nodes"]}
        d = _graphql("""
            mutation medyaEkle($product: ProductUpdateInput!, $media: [CreateMediaInput!]) {
              productUpdate(product: $product, media: $media) {
                product { media(first: 250) { nodes { id } } }
                userErrors { field message }
              }
            }""", {"product": {"id": pid}, "media": medya_girdi}, timeout=180)
        hatalar = d["productUpdate"]["userErrors"]
        if hatalar:
            raise RuntimeError(f"Shopify medya ekleme: {hatalar}")
        # Yeni medya, ürün galerisine girdi SIRASIYLA eklenir (productSet ile aynı
        # varsayım — _kapaklari_ata); blok başlangıçları görsel sayısından bulunur.
        yeni_medya = [m["id"] for m in d["productUpdate"]["product"]["media"]["nodes"]
                      if m["id"] not in onceki]
        if len(yeni_medya) != len(medya_girdi):
            logger.warning("[SHOPIFY-URUN] eklenen medya sayısı beklenenden farklı (%d/%d)",
                           len(yeni_medya), len(medya_girdi))
        konum = 0
        for renk, adet in blok_sira:
            if adet and konum < len(yeni_medya) and renk not in kapaklar:
                kapaklar[renk] = yeni_medya[konum]
            konum += adet
        _medya_bekle(yeni_medya)

    # 3) Yalnız yeni varyantlar (SKU/barkod Trendyol standardı, stok formdan;
    #    stok senkron sonraki turda kendi değerine çeker)
    olusan: list[dict] = []
    if yeni:
        konum_id = _konum_id()
        model = taslak["model_kodu"]
        girdiler = [{
            "optionValues": [{"optionName": renk_ad, "name": renk},
                             {"optionName": beden_ad, "name": beden}],
            "barcode": bc,
            "price": fiyat,
            "compareAtPrice": liste,
            "inventoryItem": {"sku": f"{model}-{beden} {renk}", "tracked": True},
            "inventoryQuantities": [{"locationId": konum_id,
                                     "availableQuantity": int(form.get("stok", 5))}],
        } for renk, beden, bc in yeni]
        d = _graphql("""
            mutation varyantEkle($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
              productVariantsBulkCreate(productId: $productId, variants: $variants, strategy: DEFAULT) {
                productVariants { id title barcode }
                userErrors { field message code }
              }
            }""", {"productId": pid, "variants": girdiler}, timeout=180)
        hatalar = d["productVariantsBulkCreate"]["userErrors"]
        if hatalar:
            raise RuntimeError(f"Shopify varyant ekleme: {hatalar}")
        olusan = d["productVariantsBulkCreate"]["productVariants"]

    # 4) Kapak: yeni varyant → renginin kapağı (yeni renk: yeni blok ilk görseli;
    #    mevcut renk: rengin mevcut kapağı); kapaksız mevcut renklerin TÜM
    #    varyantları → yeni yüklenen bloğun ilk görseli
    bc_renk = {bc: renk for renk, _, bc in yeni}
    atama = [{"variantId": v["id"], "mediaIds": [kapaklar[bc_renk[v["barcode"]]]]}
             for v in olusan if kapaklar.get(bc_renk.get(str(v.get("barcode") or ""), ""))]
    atama += [{"variantId": v["id"], "mediaIds": [kapaklar[_secenek(v, renk_ad)]]}
              for v in mevcut_vs
              if _secenek(v, renk_ad) in kapak_renkleri and kapaklar.get(_secenek(v, renk_ad))]
    if atama:
        d = _graphql("""
            mutation kapak($productId: ID!, $variantMedia: [ProductVariantAppendMediaInput!]!) {
              productVariantAppendMedia(productId: $productId, variantMedia: $variantMedia) {
                userErrors { field message }
              }
            }""", {"productId": pid, "variantMedia": atama})
        hatalar = d["productVariantAppendMedia"]["userErrors"]
        if hatalar:
            logger.warning("[SHOPIFY-URUN] eksik-tamamlama kapak uyarısı: %s", hatalar)
    else:
        logger.warning("[SHOPIFY-URUN] eksik-tamamlama kapak ataması boş (%s)", urun["handle"])

    logger.info("[SHOPIFY-URUN] %s: %d varyant eklendi (yeni renk: %s, yeni beden: %s, kapak: %s)",
                urun["handle"], len(olusan), yeni_renkler, yeni_bedenler, kapak_renkleri)
    return {"product_id": pid, "handle": urun["handle"], "url": url,
            "varyant": len(olusan), "yeni_renkler": yeni_renkler, "yeni_bedenler": yeni_bedenler,
            "kapak_renkleri": kapak_renkleri}


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
