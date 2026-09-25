"""Ürün yükleme — Shopify EKSİK TAMAMLAMA modu + görsel ALT kanıt testi.

Senaryo (Komutan tarifi, 2026-09-25):
  * Model sitede kısmen var (Kırmızı 35-36). Trendyol'dan gelen tam set:
    Kırmızı 35-36-37 + Bej 35-36-37.
  * Motor barkodları Shopify'da tarar; olmayanları ayırır:
    - Bej = eksik RENK → görselleri (AI ALT'larıyla) galeriye eklenir, ilk görsel kapak
    - Kırmızı 37 = eksik BEDEN → görselsiz, rengin mevcut kapağı bağlanır
  * Mevcut varyant/medya/metne dokunulmaz; fiyat kardeş varyanttan alınır.
Shopify çağrıları sahtedir (ağa çıkılmaz).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from urun_yukleme import shopify_urun  # noqa: E402
from urun_yukleme.ai_metin import alt_sablon, shopify_aciklama_kur  # noqa: E402

PID = "gid://shopify/Product/1"
MEDYA_KIRMIZI = "gid://shopify/MediaImage/100"


def _taslak() -> dict:
    return {
        "model_kodu": "0122",
        "bedenler": ["35", "36", "37"],
        "shopify": {"mod": "eksik", "mevcut_pid": PID},
        "renkler": {
            "Kırmızı": {"barkodlar": ["079950000001", "079950000002", "079950000003"]},
            "Bej": {"barkodlar": ["079950000011", "079950000012", "079950000013"],
                    "alt": ["Bej topuklu sandalet önden fiyonk tokalı görünüm",
                            "Bej topuklu sandalet yandan kadeh topuk detayı"]},
        },
    }


class SahteShopify:
    """Sorgu metnine göre cevap veren sahte GraphQL; mutasyonları kaydeder."""

    def __init__(self):
        self.cagrilar: list[tuple[str, dict]] = []

    def __call__(self, query: str, variables: dict, timeout: int = 60) -> dict:
        self.cagrilar.append((query, variables))
        if "locations(first: 1)" in query:
            return {"locations": {"nodes": [{"id": "gid://shopify/Location/1"}]}}
        if "productVariants(first: 250, query" in query:
            # Yalnız Kırmızı 35-36 sitede
            return {"productVariants": {"nodes": [
                {"barcode": "079950000001", "product": {"id": PID, "title": "Rugan Sandalet", "handle": "0122-rugan"}},
                {"barcode": "079950000002", "product": {"id": PID, "title": "Rugan Sandalet", "handle": "0122-rugan"}},
            ]}}
        if "product(id: $id)" in query:
            return {"product": {
                "id": PID, "title": "Rugan Sandalet", "handle": "0122-rugan",
                "options": [
                    {"id": "opt-renk", "name": "Renk", "optionValues": [{"id": "v1", "name": "Kırmızı"}]},
                    {"id": "opt-beden", "name": "Beden", "optionValues": [{"id": "v2", "name": "35"}, {"id": "v3", "name": "36"}]},
                ],
                "media": {"nodes": [{"id": MEDYA_KIRMIZI}]},
                "variants": {"nodes": [
                    {"id": "var-1", "title": "Kırmızı / 35", "barcode": "079950000001",
                     "price": "1699.90", "compareAtPrice": "1999.90",
                     "selectedOptions": [{"name": "Renk", "value": "Kırmızı"}, {"name": "Beden", "value": "35"}],
                     "media": {"nodes": [{"id": MEDYA_KIRMIZI}]}},
                    {"id": "var-2", "title": "Kırmızı / 36", "barcode": "079950000002",
                     "price": "1699.90", "compareAtPrice": "1999.90",
                     "selectedOptions": [{"name": "Renk", "value": "Kırmızı"}, {"name": "Beden", "value": "36"}],
                     "media": {"nodes": [{"id": MEDYA_KIRMIZI}]}},
                ]},
            }}
        if "productOptionUpdate" in query:
            return {"productOptionUpdate": {"userErrors": []}}
        if "productUpdate(product" in query:
            yeni = [{"id": f"gid://shopify/MediaImage/2{i:02d}"} for i in range(len(variables["media"]))]
            return {"productUpdate": {"product": {"media": {"nodes": [{"id": MEDYA_KIRMIZI}] + yeni}},
                                      "userErrors": []}}
        if "medyaDurum" in query:
            return {"nodes": [{"id": i, "status": "READY"} for i in variables["ids"]]}
        if "productVariantsBulkCreate" in query:
            return {"productVariantsBulkCreate": {
                "productVariants": [{"id": f"var-yeni-{i}", "title": "", "barcode": v["barcode"]}
                                    for i, v in enumerate(variables["variants"])],
                "userErrors": []}}
        if "productVariantAppendMedia" in query:
            return {"productVariantAppendMedia": {"userErrors": []}}
        raise AssertionError(f"beklenmeyen sorgu: {query[:80]}")

    def bul(self, parca: str) -> list[dict]:
        return [v for q, v in self.cagrilar if parca in q]


@pytest.fixture
def sahte(monkeypatch):
    s = SahteShopify()
    monkeypatch.setattr(shopify_urun, "_graphql", s)
    return s


def test_sitedeki_barkodlar_yalniz_barkodla_esler(sahte):
    sonuc = shopify_urun.sitedeki_barkodlar(["079950000001", "079950000002", "079950000003"])
    assert sonuc["pid"] == PID
    assert sonuc["handle"] == "0122-rugan"
    assert set(sonuc["barkodlar"]) == {"079950000001", "079950000002"}


def test_eksik_tamamla_yalniz_eksikleri_ekler(sahte):
    form = {"satis_fiyat": "999", "liste_fiyat": "1299", "stok": 5, "urun_turu": "Sandalet"}
    renk_gorselleri = {"Bej": ["https://cdn/bej-1.jpg", "https://cdn/bej-2.jpg"],
                       "Kırmızı": ["https://cdn/kirmizi-1.jpg"]}

    sonuc = shopify_urun.eksik_tamamla(_taslak(), form, renk_gorselleri)

    assert sonuc["varyant"] == 4                # Kırmızı 37 + Bej 35/36/37
    assert sonuc["yeni_renkler"] == ["Bej"]
    assert sonuc["yeni_bedenler"] == ["37"]

    # 1) Seçenek değerleri: Renk'e Bej, Beden'e 37 — mevcut değerler silinmez
    secenek = sahte.bul("productOptionUpdate")
    assert {(v["option"]["id"], v["optionValuesToAdd"][0]["name"]) for v in secenek} == {
        ("opt-renk", "Bej"), ("opt-beden", "37")}
    assert all("optionValuesToDelete" not in v for v in secenek)

    # 2) Galeriye YALNIZ Bej görselleri, AI ALT'larıyla (Kırmızı yeniden yüklenmez)
    medya = sahte.bul("productUpdate(product")
    assert len(medya) == 1
    assert [m["originalSource"] for m in medya[0]["media"]] == renk_gorselleri["Bej"]
    assert medya[0]["media"][0]["alt"] == "Bej topuklu sandalet önden fiyonk tokalı görünüm"
    assert medya[0]["media"][1]["alt"] == "Bej topuklu sandalet yandan kadeh topuk detayı"
    assert "title" not in medya[0]["product"]   # metne dokunulmaz

    # 3) Yalnız yeni varyantlar; fiyat KARDEŞ varyanttan (formdaki 999 değil)
    varyantlar = sahte.bul("productVariantsBulkCreate")[0]["variants"]
    assert {v["barcode"] for v in varyantlar} == {
        "079950000003", "079950000011", "079950000012", "079950000013"}
    assert {v["price"] for v in varyantlar} == {"1699.90"}
    assert {v["compareAtPrice"] for v in varyantlar} == {"1999.90"}
    kirmizi37 = next(v for v in varyantlar if v["barcode"] == "079950000003")
    assert kirmizi37["inventoryItem"]["sku"] == "0122-37 Kırmızı"
    assert kirmizi37["optionValues"] == [{"optionName": "Renk", "name": "Kırmızı"},
                                         {"optionName": "Beden", "name": "37"}]

    # 4) Kapak: Bej → yeni bloğun İLK görseli; Kırmızı 37 → rengin MEVCUT kapağı
    atama = sahte.bul("productVariantAppendMedia")[0]["variantMedia"]
    kapak = {a["variantId"]: a["mediaIds"][0] for a in atama}
    assert kapak["var-yeni-0"] == MEDYA_KIRMIZI           # Kırmızı 37
    assert kapak["var-yeni-1"] == "gid://shopify/MediaImage/200"  # Bej 35
    assert kapak["var-yeni-3"] == "gid://shopify/MediaImage/200"  # Bej 37


def test_eksik_tamamla_fark_yoksa_gondermez(sahte):
    taslak = _taslak()
    taslak["bedenler"] = ["35", "36"]
    taslak["renkler"] = {"Kırmızı": {"barkodlar": ["079950000001", "079950000002"]}}
    sonuc = shopify_urun.eksik_tamamla(taslak, {"satis_fiyat": "1", "liste_fiyat": "1"}, {})
    assert sonuc["varyant"] == 0
    assert not sahte.bul("productVariantsBulkCreate")
    assert not sahte.bul("productUpdate(product")


def test_gorsel_alt_ai_metni_yoksa_sablona_duser():
    taslak = _taslak()
    assert shopify_urun.gorsel_alt(taslak, "Bej", 1, "x") == "Bej topuklu sandalet önden fiyonk tokalı görünüm"
    assert shopify_urun.gorsel_alt(taslak, "Bej", 3, "Bej Sandalet 3") == "Bej Sandalet 3"   # 3. ALT yok
    assert shopify_urun.gorsel_alt(taslak, "Kırmızı", 1, "Kırmızı Sandalet 1") == "Kırmızı Sandalet 1"


def test_alt_sablon_her_gorselde_farkli():
    altlar = alt_sablon("Bej", "Rugan Topuklu Sandalet", 4)
    assert len(altlar) == 4 and len(set(altlar)) == 4
    assert all(a.startswith("Bej Rugan Topuklu Sandalet") for a in altlar)
    assert all(len(a) <= 125 for a in altlar)


def test_site_aciklamasi_renk_basina_bolum_icerir():
    html = shopify_aciklama_kur(
        {"vurgu": "v", "neden": "n", "kombin": "k", "maddeler": []},
        {"teknik": [], "beden_araligi": "35-41"},
        ["Kırmızı", "Bej"], "Renkler: Kırmızı, Bej",
        {"Kırmızı": "Kırmızı paragrafı", "Bej": "Bej paragrafı"})
    assert "<h4>Kırmızı</h4>" in html and "Kırmızı paragrafı" in html
    assert "<h4>Bej</h4>" in html and "Bej paragrafı" in html
    assert html.index("<h4>Kırmızı</h4>") < html.index("<h4>Bej</h4>")


def test_eksik_tamamla_yarim_kalan_deneme_tekrarinda_cift_eklemez(sahte, monkeypatch):
    """Önceki denemede 'Bej' değeri ve 1. görsel eklenmiş, varyant adımı düşmüş olsun:
    tekrar yüklemede Bej değeri yeniden eklenmez, 1. görsel yeniden yüklenmez,
    kapak mevcut medyadır; yalnız 2. görsel + varyantlar gider."""
    orijinal = sahte.__call__

    def yarim(query, variables, timeout=60):
        d = orijinal(query, variables, timeout)
        if "product(id: $id)" in query:
            d["product"]["options"][0]["optionValues"].append({"id": "v9", "name": "Bej"})
            d["product"]["media"]["nodes"].append(
                {"id": "gid://shopify/MediaImage/777",
                 "alt": "Bej topuklu sandalet önden fiyonk tokalı görünüm"})
        return d

    monkeypatch.setattr(shopify_urun, "_graphql", yarim)
    form = {"satis_fiyat": "999", "liste_fiyat": "1299", "stok": 5}
    sonuc = shopify_urun.eksik_tamamla(
        _taslak(), form, {"Bej": ["https://cdn/bej-1.jpg", "https://cdn/bej-2.jpg"]})

    assert sonuc["varyant"] == 4
    secenek = sahte.bul("productOptionUpdate")
    assert [v["option"]["id"] for v in secenek] == ["opt-beden"]        # Renk'e tekrar eklenmedi
    medya = sahte.bul("productUpdate(product")[0]["media"]
    assert [m["originalSource"] for m in medya] == ["https://cdn/bej-2.jpg"]  # 1. görsel atlandı
    kapak = {a["variantId"]: a["mediaIds"][0]
             for a in sahte.bul("productVariantAppendMedia")[0]["variantMedia"]}
    assert kapak["var-yeni-1"] == "gid://shopify/MediaImage/777"          # mevcut kapak
