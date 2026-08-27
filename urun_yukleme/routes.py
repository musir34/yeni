# -*- coding: utf-8 -*-
"""
/urun-yukleme — panelden AI destekli Trendyol ürün açma.

Akış: form → AI taslak (başlık 95-100 + açıklama) → önizleme/elle düzeltme →
ONAY → görsellerin CDN'e taşınması + v2 gönderim + batch sonucu.
Onaysız hiçbir şey Trendyol'a gitmez (Soru-Cevap'taki insan-onayı ilkesi).

Uzun süren işler (AI üretimi, CDN, Trendyol batch) istek içinde BEKLETİLMEZ:
ai_asistan'daki kanıtlanmış desenle arka plan iş parçacığında koşar, ilerleme
taslak.json'a yazılır, ön yüz /api/taslak-durum ucundan sorgular — gunicorn
worker zaman aşımı (502) yaşanmaz.

Kod tahsisi TASLAK anında rezerve edilir: AI üretimi + insan onayı dakikalar
sürebilir; rezerv beklemeseydi eşzamanlı iki taslağa aynı barkod bloğu önerilirdi.
"""
import json
import logging
import re
import threading
import time
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from login_logout import roles_required
from . import katalog
from . import shopify_urun
from .ai_metin import metin_uret, aciklama_kur, shopify_aciklama_kur
from .gorsel import cdn_yukle

GECERLI_HEDEFLER = ("trendyol", "shopify")

logger = logging.getLogger(__name__)

urun_yukleme_bp = Blueprint("urun_yukleme", __name__)

KOK = Path(__file__).resolve().parent.parent
TASLAK_DIR = KOK / "uploads" / "urun_yukleme"
IZINLI_UZANTILAR = {".jpg", ".jpeg", ".png"}
MAKS_GORSEL = 8   # Trendyol sınırı: barkod başına en fazla 8 görsel


def _taslak_yolu(taslak_id: str) -> Path:
    guvenli = secure_filename(taslak_id)
    if not guvenli:
        raise ValueError("Geçersiz taslak kimliği")
    return TASLAK_DIR / guvenli


def _taslak_kaydet(taslak_id: str, veri: dict) -> None:
    yol = _taslak_yolu(taslak_id)
    yol.mkdir(parents=True, exist_ok=True)
    (yol / "taslak.json").write_text(json.dumps(veri, ensure_ascii=False, indent=1),
                                     encoding="utf-8")


def _taslak_oku(taslak_id: str) -> dict:
    dosya = _taslak_yolu(taslak_id) / "taslak.json"
    if not dosya.exists():
        raise ValueError("Taslak bulunamadı")
    return json.loads(dosya.read_text(encoding="utf-8"))


def _hata_yaz(taslak_id: str, asama: str, e: Exception) -> None:
    logger.error("[URUN] %s hatası (%s): %s", asama, taslak_id, e, exc_info=True)
    try:
        taslak = _taslak_oku(taslak_id)
    except Exception:
        taslak = {"taslak_id": taslak_id}
    # Admin+2FA korumalı panel: kök sebep aksiyon almak için gerekir, kırpılmış verilir.
    taslak.update({"durum": "hata", "hata": f"{asama}: {str(e)[:300]}"})
    _taslak_kaydet(taslak_id, taslak)


@urun_yukleme_bp.route("/urun-yukleme")
@roles_required("admin")
def sayfa():
    return render_template("urun_yukleme.html")


@urun_yukleme_bp.route("/urun-yukleme/api/kategori-ara")
@roles_required("admin")
def kategori_ara():
    try:
        return jsonify({"success": True, "kategoriler": katalog.kategori_ara(request.args.get("q", ""))})
    except Exception as e:
        logger.error("[URUN] kategori arama: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Kategori listesi alınamadı."}), 500


# Mağazanın fiilen sattığı kategoriler (panel ürünleri + gullushoes koleksiyonlarından):
# spor/tenis/krampon/ev terliği gibi alakasızlar listeye girmez (kullanıcı emri).
KULLANILAN_KATEGORILER = {
    "Abiye Ayakkabı", "Dolgu Topuklu Ayakkabı", "Klasik Topuklu Ayakkabı", "Stiletto",
    "Sandalet", "Terlik",
    "Babet", "Casual Ayakkabı", "Loafer Ayakkabı",
    "Bot & Bootie", "Çizme",
}


@urun_yukleme_bp.route("/urun-yukleme/api/kategoriler")
@roles_required("admin")
def kategoriler():
    """
    Seçim kutusu için yaprak kategoriler. Varsayılan: yalnızca mağazanın
    kullandığı Ayakkabı kategorileri (KULLANILAN_KATEGORILER beyaz listesi).
    ?hepsi=1 → tam ağaç (yeni bir kategoriye girilecekse).
    """
    try:
        yapraklar = katalog.kategori_yapraklari()
        if request.args.get("hepsi") != "1":
            yapraklar = [k for k in yapraklar
                         if k["yol"].split(" > ")[0] == "Ayakkabı"
                         and k["ad"] in KULLANILAN_KATEGORILER]
        return jsonify({"success": True, "kategoriler": yapraklar})
    except Exception as e:
        logger.error("[URUN] kategori listesi: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Kategori listesi alınamadı."}), 500


@urun_yukleme_bp.route("/urun-yukleme/api/ozellikler")
@roles_required("admin")
def ozellikler():
    try:
        cid = int(request.args.get("cid", "0"))
        return jsonify({"success": True, "ozellikler": katalog.kategori_ozellikleri(cid)})
    except Exception as e:
        logger.error("[URUN] özellik listesi: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Özellik listesi alınamadı."}), 500


@urun_yukleme_bp.route("/urun-yukleme/api/ozellik-degerleri")
@roles_required("admin")
def ozellik_degerleri():
    try:
        cid, aid = int(request.args.get("cid", "0")), int(request.args.get("aid", "0"))
        q = (request.args.get("q") or "").strip().lower()
        degerler = katalog.ozellik_degerleri(cid, aid)
        toplam = len(degerler)
        if q:
            degerler = [v for v in degerler if q in str(v["ad"]).lower()]
        # Kırpma YOK: Beden gibi 300+ değerli listelerde "35" ilk 100'e girmeyip
        # beden eşlemesi boş kalıyordu; dropdown'lar da tam listeyi kaldırır.
        return jsonify({"success": True, "degerler": degerler, "toplam": toplam})
    except Exception as e:
        logger.error("[URUN] özellik değerleri: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Değer listesi alınamadı."}), 500


@urun_yukleme_bp.route("/urun-yukleme/api/onek-oner")
@roles_required("admin")
def onek_oner():
    """Seçilen kategorinin barkod öneki (mevcut ürünlerden öğrenilir)."""
    try:
        return jsonify({"success": True,
                        **katalog.onek_oner(request.args.get("kategori", ""))})
    except Exception as e:
        logger.error("[URUN] önek önerisi: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Önek önerisi alınamadı."}), 500


@urun_yukleme_bp.route("/urun-yukleme/api/gorsel", methods=["POST"])
@roles_required("admin")
def gorsel_yukle():
    """Renk başına görselleri sunucuya alır; taslak klasöründe saklar."""
    try:
        taslak_id = request.form.get("taslak_id") or uuid.uuid4().hex[:12]
        renk = secure_filename(request.form.get("renk") or "renk")
        dosyalar = request.files.getlist("gorseller")
        if not dosyalar:
            return jsonify({"success": False, "error": "Görsel seçilmedi."}), 400
        hedef = _taslak_yolu(taslak_id) / "gorsel" / renk
        hedef.mkdir(parents=True, exist_ok=True)
        mevcut = len(list(hedef.glob("*")))
        kayitli = []
        for f in dosyalar:
            uzanti = Path(f.filename or "").suffix.lower()
            if uzanti not in IZINLI_UZANTILAR:
                return jsonify({"success": False,
                                "error": f"Desteklenmeyen dosya türü: {uzanti or '(uzantısız)'} — jpg/png yükleyin."}), 400
            if mevcut + len(kayitli) >= MAKS_GORSEL:
                break
            sira = mevcut + len(kayitli) + 1
            ad = f"{sira}{uzanti}"
            f.save(hedef / ad)
            kayitli.append(str(hedef / ad))
        return jsonify({"success": True, "taslak_id": taslak_id, "renk": renk,
                        "kayitli": len(kayitli), "toplam": mevcut + len(kayitli)})
    except Exception as e:
        logger.error("[URUN] görsel yükleme: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Görsel kaydedilemedi."}), 500


@urun_yukleme_bp.route("/urun-yukleme/api/gorsel-liste")
@roles_required("admin")
def gorsel_liste():
    """Rengin sunucudaki görsel dosya adlarını döner (önizleme şeridi için)."""
    try:
        taslak_id = secure_filename(request.args.get("taslak_id") or "")
        renk = secure_filename(request.args.get("renk") or "")
        if not (taslak_id and renk):
            return jsonify({"success": False, "error": "taslak_id ve renk gerekli."}), 400
        klasor = _taslak_yolu(taslak_id) / "gorsel" / renk
        adlar = sorted(p.name for p in klasor.glob("*")) if klasor.exists() else []
        return jsonify({"success": True, "adlar": adlar})
    except Exception as e:
        logger.error("[URUN] görsel listesi: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Görsel listesi alınamadı."}), 500


@urun_yukleme_bp.route("/urun-yukleme/api/gorsel-onizle")
@roles_required("admin")
def gorsel_onizle():
    """Taslak klasöründeki tek görseli servis eder (secure_filename ile sınırlı)."""
    taslak_id = secure_filename(request.args.get("taslak_id") or "")
    renk = secure_filename(request.args.get("renk") or "")
    ad = secure_filename(request.args.get("ad") or "")
    yol = _taslak_yolu(taslak_id) / "gorsel" / renk / ad
    if not (taslak_id and renk and ad and yol.is_file()):
        return jsonify({"success": False, "error": "Görsel bulunamadı."}), 404
    return send_file(yol, max_age=3600)


# ------------------------------------------------------------- taslak üretimi

_GEREKSIZ_OZELLIK = re.compile(r"ithalatçı|üretici|analiz testi", re.I)


def _ozellik_katalogu(cid: int) -> tuple[dict, dict]:
    """
    AI'nın seçim yapacağı özellik kataloğu.
    Döner: ({"secmeli": {ad: [değerler ≤80]}, "serbest": [adlar]},
            {ad_lower: {"attr": ozellik, "degerler": {ad_lower: id}}})
    Değer listeleri paralel çekilir (kategori başına ilk seferde N ayrı uç çağrısı).
    """
    from concurrent.futures import ThreadPoolExecutor

    adaylar = [o for o in katalog.kategori_ozellikleri(cid)
               if not o.get("varyant") and (o.get("ad") or "") != "Renk"
               and not _GEREKSIZ_OZELLIK.search(o.get("ad") or "")]
    with ThreadPoolExecutor(max_workers=6) as havuz:
        deger_listeleri = list(havuz.map(lambda o: katalog.ozellik_degerleri(cid, o["id"]), adaylar))

    katalog_ai, harita = {"secmeli": {}, "serbest": []}, {}
    for o, degerler in zip(adaylar, deger_listeleri):
        ad = o.get("ad") or ""
        if degerler:
            katalog_ai["secmeli"][ad] = [str(v["ad"]) for v in degerler[:80]]
        elif o.get("serbest"):
            katalog_ai["serbest"].append(ad)
        else:
            continue
        harita[ad.lower()] = {"attr": o,
                              "degerler": {str(v["ad"]).strip().lower(): v["id"] for v in degerler}}
    return katalog_ai, harita


def _ozellik_onerileri(ai_secimleri: dict, harita: dict) -> list[dict]:
    """AI'nın ad→değer seçimlerini Trendyol attribute kimliklerine çevirir."""
    oneriler = []
    for ad, deger in (ai_secimleri or {}).items():
        kayit = harita.get(str(ad).strip().lower())
        if not kayit:
            continue
        deger = str(deger).strip()
        deger_id = kayit["degerler"].get(deger.lower())
        if deger_id:
            oneriler.append({"attributeId": kayit["attr"]["id"], "attributeValueId": deger_id,
                             "ad": kayit["attr"]["ad"], "deger": deger})
        elif (kayit["attr"].get("serbest") and deger
              and not deger.startswith("(")):  # yer tutucu/parantezli cevapları eleme
            oneriler.append({"attributeId": kayit["attr"]["id"],
                             "customAttributeValue": deger[:100],
                             "ad": kayit["attr"]["ad"], "deger": deger})
    return oneriler


def _taslak_worker(app, taslak_id: str, f: dict, bilgi: dict,
                   renkler: list[str], bedenler: list[str],
                   mevcut: dict | None = None) -> None:
    try:
        with app.app_context():
            hedefler = bilgi.get("hedefler") or ["trendyol"]

            ozel = (f.get("ozel_model_kodu") or "").strip()
            mevcut_renkler: list[str] = []
            if mevcut and mevcut.get("model_kodu"):
                # REVİZYON: kodlar korunur, yeniden tahsis/rezerv YAPILMAZ
                kodlar = {"model_kodu": mevcut["model_kodu"],
                          "renk_bloklari": [mevcut["renkler"][r]["barkodlar"] for r in renkler]}
                mevcut_renkler = list(mevcut.get("mevcut_renkler") or [])
            elif ozel and (harita := katalog.mevcut_renk_haritasi(ozel)):
                # MEVCUT MODEL: eşleşen renkler Trendyol'daki barkodları AYNEN kullanır
                # (Shopify/Trendyol tutarlılığı); YENİ renklere aynı serinin devamından
                # blok tahsis edilir — "mevcut modele yeni renk" yolu.
                eslesen = {r: [harita[r][b] for b in bedenler] for r in renkler
                           if all(b in (harita.get(r) or {}) for b in bedenler)}
                kismi = [r for r in renkler if r not in eslesen and harita.get(r)]
                if kismi:
                    raise ValueError(
                        f"{ozel} modelinde {', '.join(kismi)} renginin beden seti "
                        "formdakiyle uyuşmuyor (Trendyol'da eksik/farklı bedenler var). "
                        "Beden listesini Trendyol'daki mevcut bedenlerle eşitleyin.")
                # Site hedefliyse modelin TÜM mevcut renkleri formda olmalı:
                # productSet tam seti yeniden yazar, eksik renk siteden SİLİNİR.
                disarida = [r for r in harita if r not in renkler]
                if disarida and "shopify" in hedefler:
                    raise ValueError(
                        f"{ozel} modelinin Trendyol'daki {', '.join(disarida)} "
                        "renkleri formda yok. Site tek-ürün kuralı gereği tüm "
                        "renkler birlikte gönderilmeli — modeli 'Trendyol'dan "
                        "Aktar' ile doldurup yeni rengi listeye ekleyin.")
                yeni_renkler = [r for r in renkler if r not in eslesen]
                yeni_bloklar: list[list[str]] = []
                if yeni_renkler:
                    ornek_bc = next(iter(next(iter(harita.values())).values()))
                    onek = (f.get("barkod_onek") or "").strip() or ornek_bc[:6]
                    yeni = katalog.kod_oner(onek, len(yeni_renkler), len(bedenler),
                                            ozel_model=ozel, model_dolu_ok=True)
                    yeni_bloklar = yeni["renk_bloklari"]
                    katalog.rezerv_ekle(ozel, [b for blok in yeni_bloklar for b in blok])
                sirali = iter(yeni_bloklar)
                kodlar = {"model_kodu": ozel,
                          "renk_bloklari": [eslesen[r] if r in eslesen else next(sirali)
                                            for r in renkler]}
                mevcut_renkler = [r for r in renkler if r in eslesen]
            else:
                # Kod tahsisi + ANINDA rezerv — barkod/model kodu HER hedefte ortak
                # standarttır (Shopify SKU/barkodları Trendyol'la aynı havuzdan gelir).
                kategori_ad = (f.get("kategori_yolu") or "").split(" > ")[-1]
                kodlar = katalog.kod_oner(
                    f["barkod_onek"], len(renkler), len(bedenler),
                    model_onek=katalog.model_onek_oner(kategori_ad),
                    ozel_model=ozel or None)
                tum_barkodlar = [b for blok in kodlar["renk_bloklari"] for b in blok]
                katalog.rezerv_ekle(kodlar["model_kodu"], tum_barkodlar)

            # Trendyol özellik kataloğu yalnız Trendyol hedefliyken gerekir
            harita = {}
            if "trendyol" in hedefler:
                try:
                    bilgi["ozellik_katalogu"], harita = _ozellik_katalogu(int(f["kategori_id"]))
                except Exception:
                    logger.warning("[URUN] özellik kataloğu kurulamadı, AI seçimi atlanıyor", exc_info=True)

            metin = metin_uret(bilgi)
            oneriler = _ozellik_onerileri(metin.get("ozellikler"), harita)

            renk_taslaklari, uyarilar = {}, []
            for i, renk in enumerate(renkler):
                icerik = (metin.get("renkler") or {}).get(renk) or {}
                baslik = (icerik.get("baslik") or "").strip()
                kayit = {"barkodlar": kodlar["renk_bloklari"][i]}
                if "trendyol" in hedefler:
                    hata = katalog.baslik_denetle(baslik)
                    if hata:
                        uyarilar.append(f"{renk}: {hata}")
                    aciklama = aciklama_kur(renk, icerik, bilgi, metin.get("renk_secenekleri", ""))
                    yasak = katalog.yasak_tara(aciklama)
                    if yasak:
                        uyarilar.append(f"{renk} açıklamasında yasaklı ifade: {', '.join(yasak)}")
                    kayit.update({"baslik": baslik, "aciklama": aciklama})
                renk_taslaklari[renk] = kayit

            # Site (Shopify) içeriği: renk-nötr tek ürün (tema renk kuralı)
            shopify = None
            if "shopify" in hedefler:
                genel = metin.get("genel") or {}
                seo_baslik = (genel.get("seo_baslik") or "").strip()
                if not genel.get("h1"):
                    uyarilar.append("Site: H1 üretilemedi — önizlemede elle doldurun.")
                if seo_baslik and not 40 <= len(seo_baslik) <= 60:
                    uyarilar.append(f"Site SEO başlığı {len(seo_baslik)} karakter — 50-60 hedeflenir.")
                shopify = {
                    "h1": (genel.get("h1") or "").strip(),
                    "seo_baslik": seo_baslik,
                    "seo_aciklama": (genel.get("seo_aciklama") or "").strip(),
                    "aciklama": shopify_aciklama_kur(genel, bilgi, renkler,
                                                     metin.get("renk_secenekleri", "")),
                }
                yasak = katalog.yasak_tara(shopify["aciklama"], shopify["h1"])
                if yasak:
                    uyarilar.append(f"Site açıklamasında yasaklı ifade: {', '.join(yasak)}")

            taslak = {"taslak_id": taslak_id, "form": f, "model_kodu": kodlar["model_kodu"],
                      "hedefler": hedefler, "mevcut_renkler": mevcut_renkler,
                      "renkler": renk_taslaklari, "bedenler": bedenler,
                      "shopify": shopify,
                      "ozellik_onerileri": oneriler,
                      "uyarilar": uyarilar, "durum": "hazir"}
            _taslak_kaydet(taslak_id, taslak)
    except Exception as e:
        _hata_yaz(taslak_id, "Taslak üretimi", e)


def _bilgi_kur(taslak_id: str, f: dict, renkler: list[str], bedenler: list[str],
               hedefler: list[str]) -> dict:
    gorsel_yollari = []
    for renk in renkler:
        klasor = _taslak_yolu(taslak_id) / "gorsel" / secure_filename(renk)
        ilk = sorted(klasor.glob("*"))[:1] if klasor.exists() else []
        gorsel_yollari += [str(p) for p in ilk]
    return {
        "kategori_yolu": f.get("kategori_yolu", ""),
        "urun_turu": f.get("urun_turu", ""),
        "renkler": renkler,
        "beden_araligi": f"{bedenler[0]}-{bedenler[-1]}" if len(bedenler) > 1 else bedenler[0],
        "teknik": f.get("teknik") or [],
        "not": f.get("not", ""),
        "gorsel_yollari": gorsel_yollari,
        "genel_talimat": katalog.talimat_getir(),
        "hedefler": hedefler,
        "trendyol_aciklama": f.get("trendyol_aciklama", ""),
    }


@urun_yukleme_bp.route("/urun-yukleme/api/taslak", methods=["POST"])
@roles_required("admin")
def taslak_uret():
    """AI taslağını ARKA PLANDA başlatır; sonuç /api/taslak-durum'dan sorgulanır."""
    try:
        f = request.json or {}
        taslak_id = f.get("taslak_id") or uuid.uuid4().hex[:12]
        renkler = [r.strip() for r in (f.get("renkler") or []) if r.strip()]
        bedenler = [b.strip() for b in (f.get("bedenler") or []) if b.strip()]
        hedefler = [h for h in (f.get("hedefler") or ["trendyol"]) if h in GECERLI_HEDEFLER]
        if not hedefler:
            return jsonify({"success": False, "error": "Hedef seçin: Trendyol, Shopify veya ikisi."}), 400
        if not renkler or not bedenler:
            return jsonify({"success": False, "error": "En az bir renk ve beden gerekli."}), 400
        if not (f.get("barkod_onek") or "").strip():
            return jsonify({"success": False,
                            "error": "Barkod öneki boş — kategori seçince otomatik dolar, bulunamadıysa elle girin."}), 400

        bilgi = _bilgi_kur(taslak_id, f, renkler, bedenler, hedefler)
        _taslak_kaydet(taslak_id, {"taslak_id": taslak_id, "form": f, "durum": "uretiliyor"})
        app = current_app._get_current_object()
        threading.Thread(target=_taslak_worker, daemon=True,
                         args=(app, taslak_id, f, bilgi, renkler, bedenler)).start()
        return jsonify({"success": True, "taslak_id": taslak_id, "durum": "uretiliyor"})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("[URUN] taslak başlatma: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Taslak başlatılamadı."}), 500


@urun_yukleme_bp.route("/urun-yukleme/api/taslak-duzelt", methods=["POST"])
@roles_required("admin")
def taslak_duzelt():
    """Q&A'daki 'Düzelttir' deseni: talimatla yeniden üretim — kodlar KORUNUR."""
    try:
        f = request.json or {}
        talimat = (f.get("talimat") or "").strip()
        if not talimat:
            return jsonify({"success": False, "error": "Düzeltme talimatı boş."}), 400
        taslak = _taslak_oku(f.get("taslak_id") or "")
        if taslak.get("durum") not in ("hazir", "hata"):
            return jsonify({"success": False,
                            "error": f"Taslak düzeltmeye uygun durumda değil: {taslak.get('durum')}"}), 400
        form = taslak["form"]
        renkler = list(taslak["renkler"].keys())
        bedenler = taslak["bedenler"]
        hedefler = taslak.get("hedefler") or ["trendyol"]

        bilgi = _bilgi_kur(taslak["taslak_id"], form, renkler, bedenler, hedefler)
        bilgi["duzeltme_talimati"] = talimat
        bilgi["onceki_metin"] = {
            "renkler": {r: {k: v for k, v in taslak["renkler"][r].items() if k != "barkodlar"}
                        for r in renkler},
            "shopify": taslak.get("shopify"),
        }
        taslak["durum"] = "uretiliyor"
        _taslak_kaydet(taslak["taslak_id"], taslak)
        app = current_app._get_current_object()
        threading.Thread(target=_taslak_worker, daemon=True,
                         args=(app, taslak["taslak_id"], form, bilgi, renkler, bedenler, taslak)).start()
        return jsonify({"success": True, "taslak_id": taslak["taslak_id"], "durum": "uretiliyor"})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("[URUN] taslak düzeltme: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Düzeltme başlatılamadı."}), 500


@urun_yukleme_bp.route("/urun-yukleme/api/trendyol-getir", methods=["POST"])
@roles_required("admin")
def trendyol_getir():
    """
    Trendyol'daki mevcut ürünü tek tıkla aktarım için hazırlar: paketi çözer,
    görselleri sunucuya indirir, formu dolduracak veriyi döndürür.
    Barkod/model kodu AYNEN korunur (platformlar arası tutarlılık kuralı).
    """
    import requests as _requests
    try:
        model = ((request.json or {}).get("model") or "").strip()
        if not model:
            return jsonify({"success": False, "error": "Model kodu girin."}), 400
        paket = katalog.trendyol_urun_paketi(model)

        taslak_id = uuid.uuid4().hex[:12]
        gorsel_sayilari = {}
        for renk, urller in paket["gorseller"].items():
            hedef = _taslak_yolu(taslak_id) / "gorsel" / secure_filename(renk)
            hedef.mkdir(parents=True, exist_ok=True)
            for i, url in enumerate(urller, 1):
                try:
                    r = _requests.get(url, timeout=30)
                    r.raise_for_status()
                    uzanti = ".png" if url.lower().endswith(".png") else ".jpg"
                    (hedef / f"{i}{uzanti}").write_bytes(r.content)
                except Exception:
                    logger.warning("[URUN] Trendyol görseli indirilemedi: %s", url)
            gorsel_sayilari[renk] = len(list(hedef.glob("*")))
        if not any(gorsel_sayilari.values()):
            return jsonify({"success": False, "error": "Ürün görselleri indirilemedi."}), 502

        return jsonify({"success": True, "taslak_id": taslak_id,
                        "paket": {k: v for k, v in paket.items() if k != "gorseller"},
                        "gorsel_sayilari": gorsel_sayilari})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("[URUN] Trendyol getir: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Ürün Trendyol'dan çekilemedi."}), 500


@urun_yukleme_bp.route("/urun-yukleme/api/son-taslak")
@roles_required("admin")
def son_taslak():
    """Sayfa yenilense de kayıp yok: sunucudaki en güncel taslağı döndürür."""
    try:
        dosyalar = sorted(TASLAK_DIR.glob("*/taslak.json"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        for p in dosyalar[:5]:
            try:
                t = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if t.get("durum") in ("hazir", "hata", "uretiliyor", "yukleniyor", "gonderiliyor"):
                gorseller = {}
                for renk_dizin in sorted((p.parent / "gorsel").glob("*")) if (p.parent / "gorsel").exists() else []:
                    gorseller[renk_dizin.name] = len(list(renk_dizin.glob("*")))
                t["gorsel_sayilari"] = gorseller
                return jsonify({"success": True, "taslak": t})
        return jsonify({"success": True, "taslak": None})
    except Exception as e:
        logger.error("[URUN] son taslak: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Son taslak okunamadı."}), 500


@urun_yukleme_bp.route("/urun-yukleme/api/taslak-durum")
@roles_required("admin")
def taslak_durum():
    try:
        return jsonify({"success": True, "taslak": _taslak_oku(request.args.get("taslak_id") or "")})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        logger.error("[URUN] taslak durumu: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Durum okunamadı."}), 500


# ------------------------------------------------------------------ yükleme

def _trendyol_gonder(taslak: dict, form: dict, renk_gorselleri: dict) -> dict:
    bedenler = taslak["bedenler"]
    beden_deger = form.get("beden_degerleri") or {}
    ortak_ozellikler = form.get("ozellik_secimleri") or []
    beden_attr_id = form.get("beden_attr_id")

    # Zorunlu özellik güvencesi: eksikler otomatik tamamlanır (Web Color renk
    # bazlı eşlenir); tamamlanamayan kalırsa batch'e gitmeden hata verilir.
    ortak_ek, renk_web_color, eksikler = katalog.zorunlu_tamamla(
        int(form["kategori_id"]), ortak_ozellikler, list(taslak["renkler"].keys()))
    if eksikler:
        raise ValueError("Şu zorunlu özellikler eşlenemedi, Adım 1'den seçin: "
                         + ", ".join(eksikler))

    # Zaten Trendyol'da olan renkler YENİDEN gönderilmez (çift barkod hatası olur);
    # "mevcut modele yeni renk" yolunda yalnız yeni renkler batch'e girer.
    zaten_var = set(taslak.get("mevcut_renkler") or [])
    items = []
    for renk, r in taslak["renkler"].items():
        if renk in zaten_var:
            continue
        renk_ozel = [renk_web_color[renk]] if renk_web_color.get(renk) else []
        for beden, barkod in zip(bedenler, r["barkodlar"]):
            if len(barkod) != katalog.BARKOD_UZUNLUK:
                raise ValueError(f"Barkod {katalog.BARKOD_UZUNLUK} hane değil: {barkod}")
            items.append({
                "barcode": barkod,
                "title": r["baslik"],
                "productMainId": taslak["model_kodu"],
                "brandId": katalog.MARKA_ID,
                "categoryId": int(form["kategori_id"]),
                "quantity": int(form.get("stok", 5)),
                "stockCode": f"{taslak['model_kodu']}-{beden} {renk}",
                "description": r["aciklama"],
                "currencyType": "TRY",
                "listPrice": float(form["liste_fiyat"]),
                "salePrice": float(form["satis_fiyat"]),
                "vatRate": int(form.get("kdv", 10)),
                "images": [{"url": u} for u in renk_gorselleri[renk]],
                "attributes": [{"attributeId": 47, "customAttributeValue": renk}]
                              + ortak_ozellikler + ortak_ek + renk_ozel
                              + [{"attributeId": int(beden_attr_id),
                                  "attributeValueId": int(beden_deger[beden])}],
            })

    if not items:
        return {"varyant": 0,
                "mesaj": "Tüm renkler zaten Trendyol'da — yeni gönderim gerekmedi."}

    batch_id = katalog.urun_gonder(items)
    sonuc = {"batch_id": batch_id, "varyant": len(items)}
    for _ in range(9):
        time.sleep(10)
        durum = katalog.batch_durum(batch_id)
        sonuc.update(durum)
        if durum.get("durum") == "COMPLETED":
            break
    return sonuc


def _yukle_worker(app, taslak_id: str) -> None:
    try:
        with app.app_context():
            taslak = _taslak_oku(taslak_id)
            form = taslak["form"]
            hedefler = taslak.get("hedefler") or ["trendyol"]

            # Görselleri CDN'e taşı (iki hedef de aynı HTTPS adresleri kullanır)
            renk_gorselleri = taslak.get("cdn") or {}
            if not renk_gorselleri:
                for renk in taslak["renkler"]:
                    klasor = _taslak_yolu(taslak_id) / "gorsel" / secure_filename(renk)
                    yerel = sorted(klasor.glob("*"))[:MAKS_GORSEL] if klasor.exists() else []
                    if not yerel:
                        raise ValueError(f"{renk} için görsel yüklenmemiş.")
                    adlar = [(f"{taslak['model_kodu']}-{secure_filename(renk).lower()}-{i+1}{p.suffix.lower()}", str(p))
                             for i, p in enumerate(yerel)]
                    renk_gorselleri[renk] = cdn_yukle(adlar)
                taslak["cdn"] = renk_gorselleri
                _taslak_kaydet(taslak_id, taslak)

            # Hedefler bağımsız ve İDEMPOTENT denenir: daha önce başarılmış hedef
            # yeniden gönderilmez (tekrar denemede çift batch / çift ürün oluşmaz).
            hatalar = []
            trendyol_tamam = bool(taslak.get("batch_sonuc")) and not taslak["batch_sonuc"].get("hata")
            if "trendyol" in hedefler and not trendyol_tamam:
                taslak["durum"] = "gonderiliyor"
                _taslak_kaydet(taslak_id, taslak)
                try:
                    taslak["batch_sonuc"] = _trendyol_gonder(taslak, form, renk_gorselleri)
                except Exception as e:
                    logger.error("[URUN] Trendyol gönderimi: %s", e, exc_info=True)
                    taslak["batch_sonuc"] = {"hata": str(e)[:300]}
                    hatalar.append("Trendyol")
                _taslak_kaydet(taslak_id, taslak)

            shopify_tamam = bool((taslak.get("shopify_sonuc") or {}).get("product_id"))
            if "shopify" in hedefler and not shopify_tamam:
                try:
                    taslak["shopify_sonuc"] = shopify_urun.urun_ac(taslak, form, renk_gorselleri)
                except Exception as e:
                    logger.error("[URUN] Shopify gönderimi: %s", e, exc_info=True)
                    taslak["shopify_sonuc"] = {"hata": str(e)[:300]}
                    hatalar.append("Shopify")
                _taslak_kaydet(taslak_id, taslak)

            # HERHANGİ bir hedef başarısızsa durum "hata" kalır → "Onayla ve Yükle"
            # tekrar çalışır; başarılan hedefler yukarıdaki kontrollerle atlanır.
            taslak["durum"] = "hata" if hatalar else "gonderildi"
            if hatalar:
                taslak["hata"] = (f"Şu hedefler başarısız: {', '.join(hatalar)} — "
                                  "düzeltip tekrar 'Onayla ve Yükle' diyebilirsiniz; "
                                  "başarılan hedefler yeniden gönderilmez.")
            else:
                taslak.pop("hata", None)
            _taslak_kaydet(taslak_id, taslak)
    except Exception as e:
        _hata_yaz(taslak_id, "Yükleme", e)


@urun_yukleme_bp.route("/urun-yukleme/api/yukle", methods=["POST"])
@roles_required("admin")
def yukle():
    """ONAY sonrası yükleme: hızlı denetimler burada, uzun işler arka planda."""
    try:
        f = request.json or {}
        taslak_id = f.get("taslak_id") or ""
        taslak = _taslak_oku(taslak_id)
        if taslak.get("durum") not in ("hazir", "hata"):
            return jsonify({"success": False,
                            "error": f"Taslak yüklemeye uygun durumda değil: {taslak.get('durum')}"}), 400
        if isinstance(f.get("form"), dict):  # fiyat/özellik seçimleri yükleme anında gelir
            taslak["form"].update(f["form"])
        if f.get("renkler"):  # önizlemede elle düzeltilmiş metinler
            for renk, duzeltme in f["renkler"].items():
                if renk in taslak["renkler"]:
                    taslak["renkler"][renk].update(
                        {k: duzeltme[k] for k in ("baslik", "aciklama") if duzeltme.get(k)})
        if isinstance(f.get("shopify"), dict) and taslak.get("shopify"):
            taslak["shopify"].update({k: f["shopify"][k]
                                      for k in ("h1", "seo_baslik", "seo_aciklama", "aciklama")
                                      if f["shopify"].get(k)})

        # Yükleme anındaki hedef seçimi esastır (taslak sonrasında değiştirilebilir)
        if f.get("hedefler"):
            secilen = [h for h in f["hedefler"] if h in GECERLI_HEDEFLER]
            if secilen:
                taslak["hedefler"] = secilen

        form = taslak["form"]
        hedefler = taslak.get("hedefler") or ["trendyol"]
        for alan, ad in (("kategori_id", "Kategori"), ("satis_fiyat", "Satış fiyatı"),
                         ("liste_fiyat", "Liste fiyatı")):
            if not form.get(alan):
                return jsonify({"success": False, "error": f"{ad} eksik."}), 400

        if "trendyol" in hedefler:
            if not form.get("beden_attr_id"):
                return jsonify({"success": False, "error": "Beden (varyant) özelliği seçilmemiş."}), 400
            beden_deger = form.get("beden_degerleri") or {}
            eksik = [b for b in taslak["bedenler"] if not beden_deger.get(b)]
            if eksik:
                return jsonify({"success": False,
                                "error": f"Şu bedenlerin Trendyol değeri eşlenmemiş: {', '.join(eksik)}"}), 400
            # Son denetim: başlık sınırı + yasaklı ifadeler (elle düzeltme sonrası hali)
            for renk, r in taslak["renkler"].items():
                hata = katalog.baslik_denetle(r.get("baslik", ""))
                yasak = katalog.yasak_tara(r.get("aciklama", ""))
                if hata or yasak:
                    sebep = hata or f"açıklamada yasaklı ifade: {', '.join(yasak)}"
                    return jsonify({"success": False, "error": f"{renk}: {sebep}"}), 400

        if "shopify" in hedefler:
            sh = taslak.get("shopify") or {}
            if not sh.get("h1") or not sh.get("aciklama"):
                return jsonify({"success": False, "error": "Site içeriği (H1/açıklama) eksik."}), 400
            if sh.get("seo_baslik") and len(sh["seo_baslik"]) > 60:
                return jsonify({"success": False,
                                "error": f"Site SEO başlığı {len(sh['seo_baslik'])} karakter — en fazla 60."}), 400
            yasak = katalog.yasak_tara(sh.get("aciklama", ""), sh.get("h1", ""))
            if yasak:
                return jsonify({"success": False,
                                "error": f"Site açıklamasında yasaklı ifade: {', '.join(yasak)}"}), 400

        taslak["durum"] = "yukleniyor"
        _taslak_kaydet(taslak_id, taslak)
        app = current_app._get_current_object()
        threading.Thread(target=_yukle_worker, daemon=True, args=(app, taslak_id)).start()
        return jsonify({"success": True, "taslak_id": taslak_id, "durum": "yukleniyor",
                        "model_kodu": taslak["model_kodu"]})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("[URUN] yükleme başlatma: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Yükleme başlatılamadı."}), 500


@urun_yukleme_bp.route("/urun-yukleme/api/motor", methods=["GET", "POST"])
@roles_required("admin")
def motor():
    """Ürün yükleme AI motoru + model seçimi (motor_ayar 'urun' alanı)."""
    from ai_asistan.motor_ayar import (aktif_motor, motor_ayarla,
                                       codex_model, codex_model_ayarla)
    try:
        if request.method == "POST":
            f = request.json or {}
            if f.get("motor"):
                motor_ayarla("urun", f["motor"])
            if "claude_model" in f:
                katalog.claude_model_kaydet(f["claude_model"])
            if "codex_model" in f:
                codex_model_ayarla("urun", f["codex_model"])
        return jsonify({"success": True, "motor": aktif_motor("urun"),
                        "claude_model": katalog.claude_model_getir(),
                        "codex_model": codex_model("urun")})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("[URUN] motor ayarı: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Motor ayarı kaydedilemedi/okunamadı."}), 500


@urun_yukleme_bp.route("/urun-yukleme/api/talimat", methods=["GET", "POST"])
@roles_required("admin")
def talimat():
    """Kalıcı özel talimatlar — her AI taslağında prompta eklenir."""
    try:
        if request.method == "POST":
            katalog.talimat_kaydet((request.json or {}).get("talimat", ""))
        return jsonify({"success": True, "talimat": katalog.talimat_getir()})
    except Exception as e:
        logger.error("[URUN] talimat: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Talimat kaydedilemedi/okunamadı."}), 500


@urun_yukleme_bp.route("/urun-yukleme/api/durum")
@roles_required("admin")
def durum():
    try:
        model = (request.args.get("model") or "").strip()
        if not model:
            return jsonify({"success": False, "error": "model parametresi gerekli"}), 400
        return jsonify({"success": True, "durum": katalog.onay_durumu(model)})
    except Exception as e:
        logger.error("[URUN] durum sorgusu: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Durum alınamadı."}), 500
