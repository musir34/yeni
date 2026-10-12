# kargo_degistir.py
"""
🚚 Kargo Firması Değiştirme — Trendyol changeCargoProvider.

Paket kargoya verilmeden önce (Created / Picking) kargo firması Trendyol API ile
değiştirilebilir:
    PUT /integration/order/sellers/{sellerId}/shipment-packages/{packageId}/cargo-providers
    {"cargoProvider": "YKMP"}

Kullanım yerleri:
  • Üretim Siparişleri → Üretilen / Paketlenen sekmeleri (toplu seçim)
  • Sipariş Listesi (toplu seçim)
  • Mini kargo rozeti (kargo_firma_tespit / kargo_rozet): takip no ön eki 733→TEX, 728→DHL

Kurallar (Trendyol dokümanı):
  • Aynı paket için 5 dakikada yalnızca 1 değişiklik.
  • TEX kotası doluysa TEXMP isteği reddedilir.
  • Değişiklik sonrası paket yeniden çekilip doğrulanmalı — burada tek siparişi
    orderNumber ile çekip kargo firması + yeni takip numarasını yerel tabloya yazarız.
    (Kargo değişince Trendyol YENİ kargo takip numarası üretir; eski etiket geçersizdir.)

Route güvenliği uretim_routes ile birebir: 2FA kalkanı + fetch başlığı CSRF'i.
"""
import base64
import logging
import time

import requests
from flask import Blueprint, jsonify, request, session

from models import db, OrderCreated, OrderHazirlaniyor, OrderPicking, OrderShipped, UretimSiparis
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID

logger = logging.getLogger(__name__)

kargo_degistir_bp = Blueprint("kargo_degistir", __name__, url_prefix="/kargo-firmasi")

TRENDYOL_ORDER_BASE = f"https://apigw.trendyol.com/integration/order/sellers/{SUPPLIER_ID}"

# Trendyol kabul ettiği kodlar → ekranda gösterilecek ad. Sıra: en sık kullanılanlar üstte.
# Sendeo kaldırıldı (Kolay Gelsin'e geçildi). CEVATEDARIK yalnız referansta geçiyor,
# özel tedarik akışı olduğundan listeye alınmadı.
KARGO_FIRMALARI: list[tuple[str, str]] = [
    ("YKMP", "Yurtiçi Kargo"),
    ("ARASMP", "Aras Kargo"),
    ("SURATMP", "Sürat Kargo"),
    ("PTTMP", "PTT Kargo"),
    ("TEXMP", "Trendyol Express"),
    ("HOROZMP", "Horoz Lojistik"),
    ("DHLECOMMP", "DHL eCommerce"),
    ("CEVAMP", "Ceva Lojistik"),
    ("KOLAYGELSINMP", "Kolay Gelsin"),
]
KARGO_KOD_AD = dict(KARGO_FIRMALARI)

# Yerel tablodaki cargo_provider_name (Trendyol "… Marketplace") → kod eşlemesi için
# anahtar kelimeler; "zaten bu firmada" tespiti ve yeniden çekme başarısızsa yerel ad.
_AD_ANAHTAR = {
    "YKMP": ("yurtiçi", "yurtici"),
    "ARASMP": ("aras",),
    "SURATMP": ("sürat", "surat"),
    "PTTMP": ("ptt",),
    "TEXMP": ("trendyol express", "tex"),
    "HOROZMP": ("horoz",),
    "DHLECOMMP": ("dhl",),
    "CEVAMP": ("ceva",),
    "KOLAYGELSINMP": ("kolay gelsin", "kolaygelsin"),
    "MNGMP": ("mng",),  # yalnız rozet tespiti için; değiştirme listesinde yok
}

# Yalnız bu tablolardaki (kargoya verilmemiş) paketler değiştirilebilir.
AKTIF_TABLOLAR = (OrderCreated, OrderHazirlaniyor, OrderPicking)
MAKS_TOPLU = 50
# Değişiklik sonrası yeni takip numarası için yeniden çekme: deneme sayısı ve aralık (sn)
YENIDEN_CEKME_DENEME = 3
YENIDEN_CEKME_BEKLEME_SN = 2.0

# ── Mini kargo rozeti ─────────────────────────────────────────────────────────
# Kargo takip numarasının ÖN EKİ firmayı söyler (kod değişince rozet de değişir):
#   733… → Trendyol Express, 728… → DHL eCommerce. Ön ek bilinmiyorsa kargo adına bakılır.
TAKIP_ONEKLERI: tuple[tuple[str, str], ...] = (
    ("733", "TEXMP"),
    ("728", "DHLECOMMP"),
)
# Marka renkleriyle kısa rozet (logo dosyası yok; CSS rozet). fg/bg hex.
KARGO_ROZET: dict[str, dict] = {
    "TEXMP":         {"kisa": "TEX",          "ad": "Trendyol Express", "bg": "#f27a1a", "fg": "#ffffff"},
    "DHLECOMMP":     {"kisa": "DHL",          "ad": "DHL eCommerce",    "bg": "#ffcc00", "fg": "#d40511"},
    "YKMP":          {"kisa": "YURTİÇİ",      "ad": "Yurtiçi Kargo",    "bg": "#0b3d91", "fg": "#ffffff"},
    "ARASMP":        {"kisa": "ARAS",         "ad": "Aras Kargo",       "bg": "#e2001a", "fg": "#ffffff"},
    "SURATMP":       {"kisa": "SÜRAT",        "ad": "Sürat Kargo",      "bg": "#1b4f9c", "fg": "#ffffff"},
    "PTTMP":         {"kisa": "PTT",          "ad": "PTT Kargo",        "bg": "#ffd200", "fg": "#1a1a1a"},
    "HOROZMP":       {"kisa": "HOROZ",        "ad": "Horoz Lojistik",   "bg": "#c8102e", "fg": "#ffffff"},
    "CEVAMP":        {"kisa": "CEVA",         "ad": "Ceva Lojistik",    "bg": "#e30613", "fg": "#ffffff"},
    "KOLAYGELSINMP": {"kisa": "KOLAY GELSİN", "ad": "Kolay Gelsin",     "bg": "#6c2bd9", "fg": "#ffffff"},
    "MNGMP":         {"kisa": "MNG",          "ad": "MNG Kargo",        "bg": "#f58220", "fg": "#ffffff"},
}


def kargo_firma_tespit(takip_no: str | None, kargo_adi: str | None = None) -> dict | None:
    """Takip numarası ön eki → firma; yoksa kargo adından tahmin. Rozet sözlüğü döner
    ({"kod","kisa","ad","bg","fg"}) ya da None."""
    takip = (takip_no or "").strip()
    kod = None
    for onek, k in TAKIP_ONEKLERI:
        if takip.startswith(onek):
            kod = k
            break
    if kod is None:
        kod = kod_tahmin(kargo_adi)
    if kod is None or kod not in KARGO_ROZET:
        return None
    return {"kod": kod, **KARGO_ROZET[kod]}


@kargo_degistir_bp.app_template_global("kargo_rozet")
def kargo_rozet_html(takip_no, kargo_adi=None):
    """Jinja: {{ kargo_rozet(order.cargo_tracking_number, order.cargo_provider_name) }} —
    static/js/kargo-rozet.js ile birebir aynı işaretleme (sınıf: kargo-rozet)."""
    from markupsafe import Markup, escape
    f = kargo_firma_tespit(takip_no, kargo_adi)
    if not f:
        return Markup("")
    return Markup(
        f'<span class="kargo-rozet" data-kargo-kod="{escape(f["kod"])}" title="{escape(f["ad"])}" '
        f'style="background:{escape(f["bg"])};color:{escape(f["fg"])}">{escape(f["kisa"])}</span>'
    )


@kargo_degistir_bp.before_request
def _guvenlik_kalkani():
    from flask import abort
    from flask_login import current_user
    try:
        dogrulanmis = current_user.is_authenticated and session.get("totp_verified")
    except Exception:
        dogrulanmis = False
    if not dogrulanmis:
        abort(403)
    if request.method == "POST" and request.headers.get("X-Requested-With") != "fetch":
        abort(403)


def _headers() -> dict:
    token = base64.b64encode(f"{API_KEY}:{API_SECRET}".encode("utf-8")).decode("utf-8")
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "User-Agent": f"{SUPPLIER_ID} - SelfIntegration",
    }


def kod_tahmin(cargo_provider_name: str) -> str | None:
    """Yerel kargo adından ('Yurtiçi Kargo Marketplace') Trendyol kodunu tahmin eder."""
    ad = (cargo_provider_name or "").strip().lower()
    if not ad:
        return None
    for kod, anahtarlar in _AD_ANAHTAR.items():
        if any(a in ad for a in anahtarlar):
            return kod
    return None


def trendyol_kargo_degistir(package_id: str, kargo_kodu: str) -> tuple[bool, str]:
    """Tek paket için Trendyol'a PUT atar. (başarı, mesaj) döner — istisna fırlatmaz."""
    url = f"{TRENDYOL_ORDER_BASE}/shipment-packages/{package_id}/cargo-providers"
    try:
        r = requests.put(url, headers=_headers(), json={"cargoProvider": kargo_kodu}, timeout=30)
    except requests.RequestException as e:
        logger.error("[KARGO] %s PUT bağlantı hatası: %s", package_id, e)
        return False, "Trendyol'a ulaşılamadı."
    if r.status_code == 200:
        return True, "Kargo firması değiştirildi."
    govde = (r.text or "").strip()
    try:
        j = r.json()
        # Trendyol hata gövdesi: {"errors":[{"message": "..."}]} ya da {"message": "..."}
        if isinstance(j, dict):
            if j.get("errors"):
                govde = "; ".join(str(e.get("message") or e) for e in j["errors"])
            elif j.get("message"):
                govde = str(j["message"])
    except ValueError:
        pass
    logger.warning("[KARGO] %s PUT %s: %s", package_id, r.status_code, govde[:300])
    if r.status_code == 401:
        return False, "Trendyol API yetkisi reddedildi (401)."
    return False, f"Trendyol reddetti ({r.status_code}): {govde[:200] or 'açıklama yok'}"


def trendyol_paket_cek(order_number: str, package_id: str) -> dict | None:
    """Değişiklik sonrası paketi yeniden çeker — yeni kargo adı + takip numarası için."""
    url = f"{TRENDYOL_ORDER_BASE}/v2/orders"  # order_service ile aynı uç nokta
    try:
        r = requests.get(url, headers=_headers(), params={"orderNumber": order_number}, timeout=30)
        if r.status_code != 200:
            logger.warning("[KARGO] %s yeniden çekme HTTP %s", order_number, r.status_code)
            return None
        icerik = (r.json() or {}).get("content") or []
    except (requests.RequestException, ValueError) as e:
        logger.warning("[KARGO] %s yeniden çekme hatası: %s", order_number, e)
        return None
    for p in icerik:
        pid = str(p.get("shipmentPackageId") or p.get("id") or "")
        if pid == str(package_id):
            return p
    return icerik[0] if len(icerik) == 1 else None


def _aktif_satirlar(order_number: str):
    """Siparişin kargoya verilmemiş satırlarını (aynı order_number'lı tüm satırlar) döner."""
    for M in AKTIF_TABLOLAR:
        satirlar = M.query.filter_by(order_number=order_number).all()
        if satirlar:
            return satirlar
    return []


def siparis_kargo_degistir(order_number: str, kargo_kodu: str) -> dict:
    """Tek siparişin kargo firmasını değiştirir; sonucu sözlük olarak döner.
    {"order_number", "success", "message", "cargo_provider_name", "cargo_tracking_number", "skipped"}"""
    sonuc = {"order_number": order_number, "success": False, "skipped": False,
             "message": "", "cargo_provider_name": None, "cargo_tracking_number": None,
             "firma": None}
    order_number = (order_number or "").strip()
    if not order_number:
        sonuc["message"] = "Sipariş numarası boş."
        return sonuc
    if order_number.startswith("SH-") or order_number.startswith("DG-"):
        sonuc.update(skipped=True, message="Trendyol siparişi değil (site/değişim) — atlandı.")
        return sonuc

    satirlar = _aktif_satirlar(order_number)
    if not satirlar:
        if OrderShipped.query.filter_by(order_number=order_number).first():
            sonuc["message"] = "Sipariş kargoya verilmiş — kargo firması artık değiştirilemez."
        else:
            sonuc["message"] = "Sipariş aktif tablolarda bulunamadı."
        return sonuc

    ilk = satirlar[0]
    package_id = (getattr(ilk, "shipment_package_id", None) or getattr(ilk, "package_number", None) or "").strip()
    if not package_id:
        sonuc["message"] = "Paket numarası yok — Trendyol'dan yeniden çekin."
        return sonuc

    # "Zaten aynı firma" kararı YEREL kayda değil Trendyol'daki canlı pakete göre verilir —
    # yerel ad bayat olabilir (panelden değiştirilmiş vb.). Canlı veri okunamazsa PUT atılır.
    canli = trendyol_paket_cek(order_number, package_id)
    if canli and kod_tahmin(canli.get("cargoProviderName", "")) == kargo_kodu:
        canli_ad = canli.get("cargoProviderName") or KARGO_KOD_AD.get(kargo_kodu, kargo_kodu)
        canli_takip = canli.get("cargoTrackingNumber") or None
        try:  # yerel kaydı canlıyla hizala
            for s in satirlar:
                s.cargo_provider_name = canli_ad
                if canli_takip:
                    s.cargo_tracking_number = canli_takip
            db.session.commit()
        except Exception:
            db.session.rollback()
        sonuc.update(skipped=True, success=True,
                     message=f"Trendyol'da zaten {KARGO_KOD_AD.get(kargo_kodu, kargo_kodu)} — atlandı.",
                     cargo_provider_name=canli_ad, cargo_tracking_number=canli_takip,
                     firma=kargo_firma_tespit(canli_takip, canli_ad))
        return sonuc

    ok, mesaj = trendyol_kargo_degistir(package_id, kargo_kodu)
    if not ok:
        sonuc["message"] = mesaj
        return sonuc

    # Doğrulama + yeni takip numarası: paketi yeniden çek. Trendyol yeni kodu anında
    # üretmeyebilir → kısa aralıkla birkaç deneme. Yine gelmezse ESKİ KOD SİLİNİR:
    # kargo değişince eski kod geçersizdir; yerelde kalırsa eski etiket basılır ve
    # rozet (takip no ön eki) eski firmayı gösterir. Yeni kod sonraki senkronla gelir.
    eski_takip = (getattr(ilk, "cargo_tracking_number", "") or "").strip()
    yeni_ad = KARGO_KOD_AD.get(kargo_kodu, kargo_kodu)
    yeni_takip = None
    paket = None
    for deneme in range(YENIDEN_CEKME_DENEME):
        if deneme:
            time.sleep(YENIDEN_CEKME_BEKLEME_SN)
        paket = trendyol_paket_cek(order_number, package_id)
        if paket and kod_tahmin(paket.get("cargoProviderName", "")) == kargo_kodu:
            yeni_ad = paket.get("cargoProviderName") or yeni_ad
            t = (paket.get("cargoTrackingNumber") or "").strip()
            if t and t != eski_takip:
                yeni_takip = t
                break
    if not yeni_takip:
        logger.info("[KARGO] %s yeni takip numarası henüz oluşmadı — eski kod (%s) temizlendi",
                    order_number, eski_takip or "-")
    try:
        for s in satirlar:
            s.cargo_provider_name = yeni_ad
            s.cargo_tracking_number = yeni_takip or ""
            if hasattr(s, "cargo_tracking_link"):
                s.cargo_tracking_link = (paket.get("cargoTrackingLink") or "") if (yeni_takip and paket) else ""
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.error("[KARGO] %s yerel kayıt güncellenemedi", order_number, exc_info=True)
        sonuc.update(success=True,
                     message="Trendyol'da değişti ama yerel kayıt güncellenemedi — Siparişleri Güncelle'ye basın.")
        return sonuc

    try:
        from user_logs import log_user_action
        log_user_action("UPDATE", {
            "işlem_açıklaması": f"Kargo firması değiştirildi — {order_number} → {yeni_ad}",
            "sayfa": "Kargo Firması Değiştir",
            "sipariş_no": order_number,
            "kargo_firması": yeni_ad,
        })
    except Exception:
        logger.warning("[KARGO] kullanıcı hareketi loglanamadı", exc_info=True)

    sonuc.update(success=True, cargo_provider_name=yeni_ad, cargo_tracking_number=yeni_takip,
                 firma=kargo_firma_tespit(yeni_takip, yeni_ad),
                 message=("Değiştirildi — yeni kargo kodu alındı." if yeni_takip
                          else "Değiştirildi — yeni kargo kodu henüz oluşmadı; eski kod silindi, "
                               "yenisi Siparişleri Güncelle ile gelir."))
    return sonuc


def toplu_kargo_degistir(order_numbers: list[str], kargo_kodu: str) -> dict:
    sonuclar = [siparis_kargo_degistir(no, kargo_kodu) for no in order_numbers]
    basarili = sum(1 for s in sonuclar if s["success"] and not s["skipped"])
    atlanan = sum(1 for s in sonuclar if s["skipped"])
    hatali = sum(1 for s in sonuclar if not s["success"] and not s["skipped"])  # atlanan hata değildir
    return {"success": hatali == 0, "basarili": basarili, "atlanan": atlanan,
            "hatali": hatali, "sonuclar": sonuclar,
            "message": f"{basarili} değişti, {atlanan} atlandı, {hatali} hata."}


@kargo_degistir_bp.route("/api/liste", methods=["GET"])
def liste():
    return jsonify({"success": True,
                    "firmalar": [{"kod": k, "ad": a} for k, a in KARGO_FIRMALARI]})


@kargo_degistir_bp.route("/api/degistir", methods=["POST"])
def degistir():
    """Gövde: {"kargo_kodu": "YKMP", "order_numbers": [...]} veya
             {"kargo_kodu": "YKMP", "kayit_ids": [UretimSiparis.id, ...]} (üretim ekranı)."""
    veri = request.get_json(silent=True) or {}
    kargo_kodu = str(veri.get("kargo_kodu") or "").strip().upper()
    if kargo_kodu not in KARGO_KOD_AD:
        return jsonify({"success": False, "message": "Geçersiz kargo firması kodu."}), 400

    order_numbers = [str(n).strip() for n in (veri.get("order_numbers") or []) if str(n).strip()]
    kayit_ids = veri.get("kayit_ids") or []
    if kayit_ids:
        try:
            ids = [int(i) for i in kayit_ids]
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "Geçersiz kayıt kimliği."}), 400
        kayitlar = UretimSiparis.query.filter(UretimSiparis.id.in_(ids)).all()
        order_numbers += [k.order_number for k in kayitlar]
    # Sıra korunarak tekille
    order_numbers = list(dict.fromkeys(order_numbers))
    if not order_numbers:
        return jsonify({"success": False, "message": "Sipariş seçilmedi."}), 400
    if len(order_numbers) > MAKS_TOPLU:
        return jsonify({"success": False,
                        "message": f"Tek seferde en fazla {MAKS_TOPLU} sipariş değiştirilebilir."}), 400

    return jsonify(toplu_kargo_degistir(order_numbers, kargo_kodu))
