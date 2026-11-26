# tek_adet_teyit_routes.py
"""
🔎 Tek Adet Teyit — merkezi stoğu tam 1 olan barkodların raf kontrolü.

Kayıtta 1 görünen ama rafta olmayan ürün satılıp "tedarik edilemedi" oluyordu.
qty == 1 barkod, personel rafa bakıp "Var" diyene kadar platformlara 0 gider
(kural: stock_sync/tek_adet_teyit.py). "Yok" → raf stoğu ledger üzerinden 0'a iner.
Üretim Modu barkodları kuralın dışında olduğu için listede yer almaz.

POST uçları siparis_notu deseninde: oturum + fetch başlığı (CSRF kalkanı).
Tablo additive: scripts/create_stok_teyit_table.py.
"""
import logging
from datetime import datetime

from flask import Blueprint, abort, jsonify, render_template, request

from login_logout import login_required
from models import db, CentralStock, Product, RafUrun, StokTeyit
from stock_sync.tek_adet_teyit import teyit_gecerli
from time_utils import fmt_ist
from user_logs import log_user_action

logger = logging.getLogger(__name__)

tek_adet_teyit_bp = Blueprint("tek_adet_teyit", __name__, url_prefix="/tek-adet-teyit")

TARIH_FMT = "%d.%m.%Y %H:%M"
DURUMLAR = ("bekleyen", "teyitli", "hepsi")


@tek_adet_teyit_bp.before_request
def _csrf_kalkani():
    if request.method == "POST" and request.headers.get("X-Requested-With") != "fetch":
        abort(403)


def _satirlar() -> list[dict]:
    """qty == 1 ve üretim modunda olmayan barkodlar, raf koduna göre sıralı."""
    from uretim_modu import get_uretim_barcodes
    uretim = get_uretim_barcodes()
    rows = (db.session.query(CentralStock.barcode, CentralStock.updated_at,
                             Product.product_main_id, Product.color, Product.size, Product.images,
                             StokTeyit.teyit_at, StokTeyit.teyit_by)
            .outerjoin(Product, Product.barcode == CentralStock.barcode)
            .outerjoin(StokTeyit, StokTeyit.barcode == CentralStock.barcode)
            .filter(CentralStock.qty == 1)
            .all())
    rows = [r for r in rows if r.barcode not in uretim]
    raf_map: dict[str, list[str]] = {}
    if rows:
        for bc, kod in (RafUrun.query
                        .filter(RafUrun.urun_barkodu.in_([r.barcode for r in rows]), RafUrun.adet > 0)
                        .with_entities(RafUrun.urun_barkodu, RafUrun.raf_kodu).all()):
            raf_map.setdefault(bc, []).append(kod)
    out = []
    for r in rows:
        teyitli = teyit_gecerli(1, r.updated_at, r.teyit_at)
        out.append({
            "barcode": r.barcode,
            "raf": ", ".join(sorted(raf_map.get(r.barcode, []))),
            "model": r.product_main_id or "",
            "renk": r.color or "",
            "beden": r.size or "",
            "image_url": (r.images or "").split(",")[0].strip() if r.images else "",
            "teyitli": teyitli,
            "teyit_by": (r.teyit_by or "") if teyitli else "",
            "teyit_at": fmt_ist(r.teyit_at, TARIH_FMT) if teyitli else "",
        })
    out.sort(key=lambda s: (s["raf"] == "", s["raf"], s["model"], s["renk"], s["beden"]))
    return out


@tek_adet_teyit_bp.route("/", methods=["GET"])
@login_required
def sayfa():
    durum = request.args.get("durum", "bekleyen")
    if durum not in DURUMLAR:
        durum = "bekleyen"
    q = (request.args.get("q") or "").strip()
    try:
        tumu = _satirlar()
    except Exception:
        db.session.rollback()
        logger.exception("[TEK-ADET] liste okunamadı")
        tumu = []
    sayac = {"bekleyen": sum(1 for s in tumu if not s["teyitli"]),
             "teyitli": sum(1 for s in tumu if s["teyitli"])}
    satirlar = [s for s in tumu
                if (durum == "hepsi" or s["teyitli"] == (durum == "teyitli"))
                and (not q or q.lower() in s["raf"].lower() or q.lower() in s["model"].lower())]
    return render_template("tek_adet_teyit.html", satirlar=satirlar, sayac=sayac, durum=durum, q=q)


def _barkod_ve_stok():
    """İstekten barkodu al, stoğun hâlâ tam 1 olduğunu doğrula. (cs, hata_yaniti)"""
    barcode = str((request.get_json(silent=True) or {}).get("barcode") or "").strip()
    if not barcode:
        return None, (jsonify({"success": False, "message": "Barkod boş"}), 400)
    cs = db.session.get(CentralStock, barcode)
    if cs is None or cs.qty != 1:
        simdi = cs.qty if cs else 0
        return None, (jsonify({"success": False,
                               "message": f"Stok artık 1 değil (şu an {simdi}) — sayfayı yenileyin"}), 409)
    return cs, None


@tek_adet_teyit_bp.route("/api/var", methods=["POST"])
@login_required
def var():
    """Rafta var: teyit kaydını yazar/günceller → bu adet platformlara gidebilir."""
    from flask_login import current_user
    try:
        cs, hata = _barkod_ve_stok()
        if hata:
            return hata
        teyit_at = datetime.utcnow()
        # updated_at saat kayması yüzünden ileride görünürse teyit hemen geçersiz kalmasın
        if cs.updated_at and cs.updated_at > teyit_at:
            teyit_at = cs.updated_at
        kullanici = getattr(current_user, "username", None) or ""
        kayit = db.session.get(StokTeyit, cs.barcode)
        if kayit is None:
            db.session.add(StokTeyit(barcode=cs.barcode, teyit_at=teyit_at, teyit_by=kullanici))
        else:
            kayit.teyit_at = teyit_at
            kayit.teyit_by = kullanici
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("[TEK-ADET] teyit kaydedilemedi")
        return jsonify({"success": False, "message": "Kaydedilemedi"}), 500
    log_user_action("UPDATE: tek_adet_teyit", {"sayfa": "Tek Adet Teyit", "barkod": cs.barcode,
                                               "sonuç": "Rafta var (teyit edildi)"})
    return jsonify({"success": True, "teyit_by": kullanici, "teyit_at": fmt_ist(teyit_at, TARIH_FMT)})


@tek_adet_teyit_bp.route("/api/yok", methods=["POST"])
@login_required
def yok():
    """Rafta yok: raf stoğunu hareket defteri üzerinden 0'a indirir (tek düşüm)."""
    from stock_ledger import record_movement, REASON_MANUAL
    try:
        cs, hata = _barkod_ve_stok()
        if hata:
            return hata
        barcode = cs.barcode
        if not RafUrun.query.filter(RafUrun.urun_barkodu == barcode, RafUrun.adet > 0).first():
            return jsonify({"success": False, "message": "Rafta bu barkoda ait kayıt bulunamadı, stok düşülmedi"}), 409
        sonuc = record_movement(barcode=barcode, delta=-1, reason=REASON_MANUAL,
                                source="TEK_ADET_TEYIT", note="tek adet teyit: rafta yok",
                                mutate_shelf=True, commit=True)
    except Exception:
        db.session.rollback()
        logger.exception("[TEK-ADET] rafta yok düşümü başarısız")
        return jsonify({"success": False, "message": "Stok düşülemedi"}), 500
    if sonuc.delta == 0:
        return jsonify({"success": False, "message": "Rafta bu barkoda ait kayıt bulunamadı, stok düşülmedi"}), 409
    log_user_action("STOCK_UPDATE: tek_adet_teyit", {"sayfa": "Tek Adet Teyit", "barkod": barcode,
                                                     "sonuç": "Rafta yok — stok 0'a indirildi"})
    return jsonify({"success": True})
