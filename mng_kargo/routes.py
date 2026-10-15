"""/kargo-gonderi — MNG giden gönderi listesi ve elle müdahale.

Otomatik akış çalışırken insan burada görür: hangi değişim/manuel/Shopify siparişine
hangi takip no açıldı, kurye aldı mı, teslim oldu mu, kapıda ödeme tahsil edildi mi,
API hatası varsa ne. Düğmeler: Sorgula (anlık MNG), Yeniden Dene (bekliyor/hata),
İptal, ZPL etiket indirme, il/ilçe düzeltme.
"""
from __future__ import annotations

import logging
from datetime import datetime

from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, url_for

from login_logout import login_required, roles_required
from models import KargoGonderi, db
from user_logs import log_user_action

from .adres import tr_upper
from .durum import ETIKETLER, SIPARIS_ACILDI
from .etiket import png_kirp, zpl_png
from .servis import (
    DURUM_BEKLIYOR, DURUM_HATA, _api_ile_ac, barkod_al, gonderi_haritasi, kaydi_sorgula, kayit_iptal,
    otomatik_acik,
)

logger = logging.getLogger(__name__)

kargo_gonderi_bp = Blueprint("kargo_gonderi", __name__)

ROZET = {
    "bekliyor": "warning text-dark", "hata": "danger", "siparis_acildi": "light text-dark border",
    "hazirlandi": "secondary", "kargoda": "primary",
    "dagitimda": "info text-dark", "teslim": "success", "teslim_edilemedi": "danger", "geri": "warning text-dark",
    "destek": "danger", "iptal": "dark", "bilinmiyor": "secondary",
}
KAYNAK_AD = {"degisim": "Değişim", "manuel": "Manuel Sipariş", "shopify": "Site Siparişi"}
LISTE_LIMIT = 300


def rozet(durum: str) -> str:
    return ROZET.get(durum or "", "secondary")


def etiket(durum: str) -> str:
    return {DURUM_BEKLIYOR: "Bekliyor (API)", DURUM_HATA: "Hata"}.get(durum) or ETIKETLER.get(durum, durum or "-")


@kargo_gonderi_bp.app_template_global("mng_rozet")
def _tpl_rozet(durum: str) -> str:
    """Jinja: değişim / manuel sipariş kartlarındaki MNG rozeti için renk."""
    return rozet(durum)


@kargo_gonderi_bp.app_template_global("mng_etiket")
def _tpl_etiket(durum: str) -> str:
    return etiket(durum)


def _kayit(gonderi_id):
    return KargoGonderi.query.get_or_404(gonderi_id)


@kargo_gonderi_bp.route("/kargo-gonderi")
@login_required
@roles_required("admin", "manager")
def liste():
    kaynak = (request.args.get("kaynak") or "").strip()
    durum = (request.args.get("durum") or "").strip()
    aranan = (request.args.get("q") or "").strip()
    sorgu = KargoGonderi.query
    if kaynak:
        sorgu = sorgu.filter(KargoGonderi.kaynak == kaynak)
    if durum == "acik":
        sorgu = sorgu.filter(~KargoGonderi.durum.in_(("teslim", "iptal")))
    elif durum:
        sorgu = sorgu.filter(KargoGonderi.durum == durum)
    if aranan:
        kalip = f"%{aranan}%"
        sorgu = sorgu.filter((KargoGonderi.referans.ilike(kalip)) | (KargoGonderi.shipment_id.ilike(kalip))
                             | (KargoGonderi.kaynak_ad.ilike(kalip)) | (KargoGonderi.alici_ad.ilike(kalip)))
    kayitlar = sorgu.order_by(KargoGonderi.id.desc()).limit(LISTE_LIMIT).all()
    sayac = {d: 0 for d in ("bekliyor", "hata", "siparis_acildi", "hazirlandi", "kargoda", "dagitimda", "teslim")}
    for k in KargoGonderi.query.with_entities(KargoGonderi.durum, db.func.count()).group_by(KargoGonderi.durum).all():
        if k[0] in sayac:
            sayac[k[0]] = k[1]
    return render_template(
        "kargo_gonderi.html", kayitlar=kayitlar, sayac=sayac, rozet=rozet, etiket=etiket, kaynak_ad=KAYNAK_AD,
        filtre={"kaynak": kaynak, "durum": durum, "q": aranan}, otomatik=otomatik_acik(),
    )


@kargo_gonderi_bp.route("/kargo-gonderi/<int:gonderi_id>/sorgula", methods=["POST"])
@login_required
@roles_required("admin", "manager")
def sorgula(gonderi_id):
    kayit = _kayit(gonderi_id)
    if kayit.durum in (DURUM_BEKLIYOR, DURUM_HATA, "iptal"):
        flash("Bu gönderi MNG'de açık değil; önce Yeniden Dene.", "warning")
    elif kayit.durum == SIPARIS_ACILDI:
        basarili = barkod_al(kayit, bekle=True)
        db.session.commit()
        flash(f"{kayit.referans}: " + (f"barkod alındı, takip {kayit.shipment_id}" if basarili else (kayit.hata or "barkod henüz alınamadı")),
              "success" if basarili else "warning")
    else:
        degisti = kaydi_sorgula(kayit)
        flash(f"{kayit.referans}: {etiket(kayit.durum)}" + (" (güncellendi)" if degisti else ""), "info")
    return redirect(url_for("kargo_gonderi.liste"))


@kargo_gonderi_bp.route("/kargo-gonderi/<int:gonderi_id>/etiket")
@login_required
def etiket_sayfasi(gonderi_id):
    """MNG'nin ürettiği etiket (ZPL → PNG) yazdırma sayfası. Barkod henüz yoksa anlık alır."""
    kayit = _kayit(gonderi_id)
    if kayit.durum == SIPARIS_ACILDI:
        barkod_al(kayit, bekle=True)
        db.session.commit()
    if not kayit.zpl:
        flash(f"{kayit.referans}: MNG etiketi henüz yok ({kayit.hata or etiket(kayit.durum)}).", "warning")
        return redirect(url_for("kargo_gonderi.liste"))
    png = zpl_png(kayit.zpl)
    if not png:
        flash("Etiket görüntüsü üretilemedi (Labelary erişilemedi). ZPL dosyasını indirip Zebra'ya gönderebilirsiniz.", "danger")
        return redirect(url_for("kargo_gonderi.liste"))
    import base64
    png = png_kirp(png)          # boş kenarları at → 100x100 ruloya sığar (order_label ile aynı sayfa)
    try:
        log_user_action("PRINT", {"işlem_açıklaması": f"MNG kargo etiketi yazdırıldı — {kayit.kaynak_ad} ({kayit.referans})",
                                  "sayfa": "Kargo Gönderileri", "takip_no": kayit.shipment_id})
    except Exception:
        logger.warning("MNG etiket PRINT hareketi loglanamadı", exc_info=True)
    return render_template("kargo_gonderi_etiket.html", kayit=kayit, png_b64=base64.b64encode(png).decode("ascii"))


@kargo_gonderi_bp.route("/kargo-gonderi/<int:gonderi_id>/yeniden-dene", methods=["POST"])
@login_required
@roles_required("admin", "manager")
def yeniden_dene(gonderi_id):
    kayit = _kayit(gonderi_id)
    il = (request.form.get("il") or "").strip()
    ilce = (request.form.get("ilce") or "").strip()
    if il:
        kayit.il = tr_upper(il)[:40]
    if ilce:
        kayit.ilce = tr_upper(ilce)[:40]
    if kayit.durum not in (DURUM_BEKLIYOR, DURUM_HATA):
        flash("Yalnız bekleyen/hatalı gönderi yeniden denenir.", "warning")
        return redirect(url_for("kargo_gonderi.liste"))
    kayit.deneme = 0
    basarili = _api_ile_ac(kayit)
    db.session.commit()
    log_user_action("UPDATE", {"işlem_açıklaması": f"MNG gönderi yeniden denendi — {kayit.referans} ({'açıldı' if basarili else 'hata'})",
                               "sayfa": "Kargo Gönderileri", "referans": kayit.referans})
    flash(f"{kayit.referans}: " + (f"açıldı, takip {kayit.shipment_id}" if basarili else f"hata: {kayit.hata}"),
          "success" if basarili else "danger")
    return redirect(url_for("kargo_gonderi.liste"))


@kargo_gonderi_bp.route("/kargo-gonderi/<int:gonderi_id>/iptal", methods=["POST"])
@login_required
@roles_required("admin", "manager")
def iptal(gonderi_id):
    kayit = _kayit(gonderi_id)
    basarili = kayit_iptal(kayit)
    log_user_action("UPDATE", {"işlem_açıklaması": f"MNG gönderi iptal — {kayit.referans} ({'tamam' if basarili else 'olmadı'})",
                               "sayfa": "Kargo Gönderileri", "referans": kayit.referans})
    flash(f"{kayit.referans} iptal edildi." if basarili else f"İptal olmadı: {kayit.hata or kayit.durum}",
          "success" if basarili else "danger")
    return redirect(url_for("kargo_gonderi.liste"))


@kargo_gonderi_bp.route("/kargo-gonderi/<int:gonderi_id>/zpl")
@login_required
def zpl(gonderi_id):
    kayit = _kayit(gonderi_id)
    if not kayit.zpl:
        return Response("Bu gönderi için ZPL etiket yok.", status=404, mimetype="text/plain")
    return Response(kayit.zpl, mimetype="text/plain",
                    headers={"Content-Disposition": f"attachment; filename={kayit.referans}.zpl"})


@kargo_gonderi_bp.route("/kargo-gonderi/durumlar")
@login_required
def durumlar():
    """Kartlar için: ?kaynak=degisim&ref=a&ref=b → {ref: {...}} (sayfa yenilemeden rozet)."""
    kaynak = (request.args.get("kaynak") or "").strip()
    refler = request.args.getlist("ref")
    if not kaynak or not refler:
        return jsonify(success=False, mesaj="kaynak ve ref gerekli"), 400
    harita = gonderi_haritasi(kaynak, refler[:200])
    return jsonify(success=True, durumlar={
        ref: {"id": k.id, "referans": k.referans, "takip_no": k.shipment_id, "barkod": k.barkod,
              "durum": k.durum, "etiket": etiket(k.durum), "rozet": rozet(k.durum), "takip_url": k.takip_url,
              "kapida_odeme": float(k.kapida_odeme_tutari) if k.kapida_odeme_tutari else None,
              "tahsil_edildi": bool(k.tahsil_edildi), "hata": k.hata,
              "guncellendi": k.guncellendi_at.isoformat() if isinstance(k.guncellendi_at, datetime) else None}
        for ref, k in harita.items()
    })
