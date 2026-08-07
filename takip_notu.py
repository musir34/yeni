# takip_notu.py
"""
📌 Takip Notları — ürün listesindeki açılır-kapanır model not paneli.

Kullanıcının unutmamak için kenara yazdığı modeller: model bazlı serbest not,
renk kapsamı (tüm renkler ya da seçili renkler) ve renk bazlı serbest notlar.
Üretim modundaki modeller listeye CANLI bağla otomatik girer (kopya değil —
üretim modundan çıkınca panelden de düşer; elle eklenenler ayrı durur).

Veri PlatformConfig 'takip_notu' ayar torbasında (uretim_modu ile aynı desen,
migration YOK):
    extra_config = {"models": [
        {"model": "0172", "colors": [], "note": "...", "color_notes": {"Siyah": "..."}}
    ]}
colors boş liste = tüm renkler.

Route güvenliği uretim_routes ile birebir: 2FA kalkanı + fetch başlığı CSRF'i.
"""
import logging

from flask import Blueprint, jsonify, request, session

from models import db, PlatformConfig, Product

logger = logging.getLogger(__name__)

PLATFORM_ANAHTAR = "takip_notu"

takip_bp = Blueprint("takip_notu", __name__, url_prefix="/takip-notu")


@takip_bp.before_request
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


def _kayit(olustur: bool = False) -> PlatformConfig | None:
    kayit = PlatformConfig.query.filter_by(platform=PLATFORM_ANAHTAR).first()
    if kayit is None and olustur:
        kayit = PlatformConfig(platform=PLATFORM_ANAHTAR, is_active=True, extra_config={})
        db.session.add(kayit)
        db.session.flush()
    return kayit


def _normalize_entry(e: dict) -> dict | None:
    model = str((e or {}).get("model") or "").strip()
    if not model:
        return None
    colors = [str(c).strip() for c in (e.get("colors") or []) if str(c).strip()]
    color_notes = {str(k).strip(): str(v).strip()
                   for k, v in (e.get("color_notes") or {}).items()
                   if str(k).strip() and str(v).strip()}
    return {"model": model, "colors": colors,
            "note": str(e.get("note") or "").strip(), "color_notes": color_notes}


def get_takip_entries() -> list[dict]:
    """Elle eklenen takip kayıtları. Hata → boş liste (akış durmaz)."""
    try:
        kayit = _kayit()
        if kayit is not None:
            entries = (kayit.extra_config or {}).get("models") or []
            return [n for n in (_normalize_entry(e) for e in entries) if n]
    except Exception:
        logger.warning("[TAKIP] ayar okunamadı", exc_info=True)
        db.session.rollback()
    return []


def get_takip_models() -> set[str]:
    """Elle takibe alınmış model kodları (kart menüsü durum etiketi için)."""
    return {e["model"] for e in get_takip_entries()}


def _entries_yaz(entries: list[dict]) -> None:
    kayit = _kayit(olustur=True)
    # JSON kolonunda in-place mutasyon algılanmaz — sözlük yeniden atanır
    kayit.extra_config = {**(kayit.extra_config or {}), "models": entries}
    db.session.commit()


def kaydet_model(entry: dict) -> None:
    """Kaydı ekle/güncelle (model koduna göre upsert, sıra korunur)."""
    yeni = _normalize_entry(entry)
    if yeni is None:
        raise ValueError("model boş olamaz")
    entries = get_takip_entries()
    if any(e["model"] == yeni["model"] for e in entries):
        entries = [yeni if e["model"] == yeni["model"] else e for e in entries]
    else:
        entries = entries + [yeni]
    _entries_yaz(entries)


def sil_model(model: str) -> None:
    model = str(model or "").strip()
    _entries_yaz([e for e in get_takip_entries() if e["model"] != model])


@takip_bp.route("/api/liste", methods=["GET"])
def liste():
    """Elle eklenenler + üretim modundakiler (canlı bağ) — görsel/başlık/renklerle."""
    entries = get_takip_entries()
    manuel = {e["model"] for e in entries}
    try:
        from uretim_modu import get_uretim_models
        uretim = get_uretim_models()
    except Exception:
        uretim = set()
    # Üretim modundaki modeller otomatik listeye girer (kaydı yoksa boş notla)
    rows = list(entries) + [{"model": m, "colors": [], "note": "", "color_notes": {}}
                            for m in sorted(uretim - manuel)]
    # Ürün bilgisi: görsel/başlık + mevcut renkler (tek sorgu)
    urun_map, renk_map = {}, {}
    modeller = [r["model"] for r in rows]
    if modeller:
        try:
            satirlar = (Product.query
                        .filter(Product.product_main_id.in_(modeller))
                        .with_entities(Product.product_main_id, Product.title,
                                       Product.images, Product.color)
                        .all())
            for m, title, images, color in satirlar:
                if m not in urun_map:
                    urun_map[m] = {
                        "title": title or "",
                        "image_url": (images or "").split(",")[0].strip() if images else "",
                    }
                if color and str(color).strip():
                    renk_map.setdefault(m, set()).add(str(color).strip())
        except Exception:
            db.session.rollback()
            logger.warning("[TAKIP] ürün bilgisi okunamadı", exc_info=True)
    sonuc = []
    for r in rows:
        p = urun_map.get(r["model"], {})
        sonuc.append({
            **r,
            "uretim": r["model"] in uretim,
            "manuel": r["model"] in manuel,
            "title": p.get("title", ""),
            "image_url": p.get("image_url", ""),
            "mevcut_renkler": sorted(renk_map.get(r["model"], set())),
        })
    return jsonify({"success": True, "rows": sonuc})


@takip_bp.route("/api/kaydet", methods=["POST"])
def kaydet():
    data = request.get_json(silent=True) or {}
    model = str(data.get("model") or "").strip()
    if not model:
        return jsonify({"success": False, "message": "Model kodu boş"}), 400
    # Yeni eklemede yazım hatasına karşı model doğrulanır; mevcut kayıt güncellenirken
    # doğrulama atlanır (ürünü silinmiş model notu yine düzenlenebilsin).
    if model not in get_takip_models():
        var_mi = Product.query.filter_by(product_main_id=model).first()
        if var_mi is None:
            return jsonify({"success": False,
                            "message": f"'{model}' model kodlu ürün bulunamadı."}), 404
    try:
        kaydet_model(data)
    except Exception:
        db.session.rollback()
        logger.exception("[TAKIP] kaydetme hatası")
        return jsonify({"success": False, "message": "Kaydedilemedi"}), 500
    return jsonify({"success": True, "message": f"{model} takip notu kaydedildi"})


@takip_bp.route("/api/toggle", methods=["POST"])
def toggle():
    """Kart ⋮ menüsünden hızlı ekle/çıkar (varsayılan: tüm renkler, notsuz)."""
    data = request.get_json(silent=True) or {}
    model = str(data.get("model") or "").strip()
    if not model:
        return jsonify({"success": False, "message": "Model kodu boş"}), 400
    try:
        if model in get_takip_models():
            sil_model(model)
            return jsonify({"success": True, "takipte": False,
                            "message": f"{model} takip notundan çıkarıldı"})
        kaydet_model({"model": model})
        return jsonify({"success": True, "takipte": True,
                        "message": f"{model} takip notuna eklendi"})
    except Exception:
        db.session.rollback()
        logger.exception("[TAKIP] toggle hatası")
        return jsonify({"success": False, "message": "Kaydedilemedi"}), 500


@takip_bp.route("/api/sil", methods=["POST"])
def sil():
    data = request.get_json(silent=True) or {}
    model = str(data.get("model") or "").strip()
    if not model:
        return jsonify({"success": False, "message": "Model kodu boş"}), 400
    try:
        sil_model(model)
    except Exception:
        db.session.rollback()
        logger.exception("[TAKIP] silme hatası")
        return jsonify({"success": False, "message": "Silinemedi"}), 500
    return jsonify({"success": True, "message": f"{model} takip notundan çıkarıldı"})
