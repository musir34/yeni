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

from flask import Blueprint, current_app, jsonify, render_template, request
from werkzeug.utils import secure_filename

from login_logout import roles_required
from . import katalog
from .ai_metin import metin_uret, aciklama_kur
from .gorsel import cdn_yukle

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
        if q:
            degerler = [v for v in degerler if q in str(v["ad"]).lower()]
        return jsonify({"success": True, "degerler": degerler[:100], "toplam": len(degerler)})
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
                   renkler: list[str], bedenler: list[str]) -> None:
    try:
        with app.app_context():
            # Kod tahsisi + ANINDA rezerv (eşzamanlı taslaklara aynı blok gitmesin)
            kodlar = katalog.kod_oner(f["barkod_onek"], len(renkler), len(bedenler))
            tum_barkodlar = [b for blok in kodlar["renk_bloklari"] for b in blok]
            katalog.rezerv_ekle(kodlar["model_kodu"], tum_barkodlar)

            # Özellik kataloğu: AI hepsini doldursun (kullanıcı önizlemede değiştirir)
            harita = {}
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
                hata = katalog.baslik_denetle(baslik)
                if hata:
                    uyarilar.append(f"{renk}: {hata}")
                aciklama = aciklama_kur(renk, icerik, bilgi, metin.get("renk_secenekleri", ""))
                yasak = katalog.yasak_tara(aciklama)
                if yasak:
                    uyarilar.append(f"{renk} açıklamasında yasaklı ifade: {', '.join(yasak)}")
                renk_taslaklari[renk] = {"baslik": baslik, "aciklama": aciklama,
                                         "barkodlar": kodlar["renk_bloklari"][i]}

            taslak = {"taslak_id": taslak_id, "form": f, "model_kodu": kodlar["model_kodu"],
                      "renkler": renk_taslaklari, "bedenler": bedenler,
                      "ozellik_onerileri": oneriler,
                      "uyarilar": uyarilar, "durum": "hazir"}
            _taslak_kaydet(taslak_id, taslak)
    except Exception as e:
        _hata_yaz(taslak_id, "Taslak üretimi", e)


@urun_yukleme_bp.route("/urun-yukleme/api/taslak", methods=["POST"])
@roles_required("admin")
def taslak_uret():
    """AI taslağını ARKA PLANDA başlatır; sonuç /api/taslak-durum'dan sorgulanır."""
    try:
        f = request.json or {}
        taslak_id = f.get("taslak_id") or uuid.uuid4().hex[:12]
        renkler = [r.strip() for r in (f.get("renkler") or []) if r.strip()]
        bedenler = [b.strip() for b in (f.get("bedenler") or []) if b.strip()]
        if not renkler or not bedenler:
            return jsonify({"success": False, "error": "En az bir renk ve beden gerekli."}), 400
        if not (f.get("barkod_onek") or "").strip():
            return jsonify({"success": False,
                            "error": "Barkod öneki boş — kategori seçince otomatik dolar, bulunamadıysa elle girin."}), 400

        gorsel_yollari = []
        for renk in renkler:
            klasor = _taslak_yolu(taslak_id) / "gorsel" / secure_filename(renk)
            ilk = sorted(klasor.glob("*"))[:1] if klasor.exists() else []
            gorsel_yollari += [str(p) for p in ilk]

        bilgi = {
            "kategori_yolu": f.get("kategori_yolu", ""),
            "urun_turu": f.get("urun_turu", ""),
            "renkler": renkler,
            "beden_araligi": f"{bedenler[0]}-{bedenler[-1]}" if len(bedenler) > 1 else bedenler[0],
            "teknik": f.get("teknik") or [],
            "not": f.get("not", ""),
            "gorsel_yollari": gorsel_yollari,
            "genel_talimat": katalog.talimat_getir(),
        }
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

def _yukle_worker(app, taslak_id: str) -> None:
    try:
        with app.app_context():
            taslak = _taslak_oku(taslak_id)
            form = taslak["form"]
            bedenler = taslak["bedenler"]
            beden_deger = form.get("beden_degerleri") or {}
            ortak_ozellikler = form.get("ozellik_secimleri") or []
            beden_attr_id = form.get("beden_attr_id")

            # Görselleri CDN'e taşı
            renk_gorselleri = {}
            for renk in taslak["renkler"]:
                klasor = _taslak_yolu(taslak_id) / "gorsel" / secure_filename(renk)
                yerel = sorted(klasor.glob("*"))[:MAKS_GORSEL] if klasor.exists() else []
                if not yerel:
                    raise ValueError(f"{renk} için görsel yüklenmemiş.")
                adlar = [(f"{taslak['model_kodu']}-{secure_filename(renk).lower()}-{i+1}{p.suffix.lower()}", str(p))
                         for i, p in enumerate(yerel)]
                renk_gorselleri[renk] = cdn_yukle(adlar)

            items = []
            for renk, r in taslak["renkler"].items():
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
                                      + ortak_ozellikler
                                      + [{"attributeId": int(beden_attr_id),
                                          "attributeValueId": int(beden_deger[beden])}],
                    })

            batch_id = katalog.urun_gonder(items)
            taslak.update({"durum": "gonderiliyor", "batch_id": batch_id,
                           "gonderilen_varyant": len(items)})
            _taslak_kaydet(taslak_id, taslak)

            sonuc = {}
            for _ in range(9):
                time.sleep(10)
                sonuc = katalog.batch_durum(batch_id)
                if sonuc.get("durum") == "COMPLETED":
                    break
            taslak.update({"durum": "gonderildi", "batch_sonuc": sonuc})
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

        form = taslak["form"]
        for alan, ad in (("kategori_id", "Kategori"), ("satis_fiyat", "Satış fiyatı"),
                         ("liste_fiyat", "Liste fiyatı")):
            if not form.get(alan):
                return jsonify({"success": False, "error": f"{ad} eksik."}), 400
        if not form.get("beden_attr_id"):
            return jsonify({"success": False, "error": "Beden (varyant) özelliği seçilmemiş."}), 400
        beden_deger = form.get("beden_degerleri") or {}
        eksik = [b for b in taslak["bedenler"] if not beden_deger.get(b)]
        if eksik:
            return jsonify({"success": False,
                            "error": f"Şu bedenlerin Trendyol değeri eşlenmemiş: {', '.join(eksik)}"}), 400

        # Son denetim: başlık sınırı + yasaklı ifadeler (elle düzeltme sonrası hali)
        for renk, r in taslak["renkler"].items():
            hata = katalog.baslik_denetle(r["baslik"])
            yasak = katalog.yasak_tara(r["aciklama"])
            if hata or yasak:
                sebep = hata or f"açıklamada yasaklı ifade: {', '.join(yasak)}"
                return jsonify({"success": False, "error": f"{renk}: {sebep}"}), 400

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
