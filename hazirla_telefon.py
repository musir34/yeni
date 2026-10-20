"""Sipariş Hazırla — Telefon Eşlik.

PC'deki sipariş hazırla ekranı "Telefonu Bağla" der → tek kullanımlık QR üretilir → telefon
/hazirla-telefon sayfasında QR'ı okutur → eşleşme "bağlı" olur. Bundan sonra:

  * PC sayfası ~1 sn'de bir /pc/senkron'a kendi ekran görüntüsünü (aktif sipariş + kalemler +
    kutuların okutulma durumu) yazar ve telefondan gelen okutmaları çeker.
  * Telefon ~1 sn'de bir /telefon/senkron'dan aynı görüntüyü alır (yalnız sürüm değişince yeniden
    çizer) ve okuttuğu raf/ürün barkodunu /telefon/okut ile olay olarak yazar.
  * PC gelen okutmayı KENDİ kutusuna yazar; mevcut raf doğrulaması ve /confirm_packing hiç
    değişmeden çalışır. Telefon stok düşürmez, "kablosuz okuyucu + ekran"dır.

Kurallar:
  * QR jetonu tek kullanımlık, QR_GECERLILIK_SN içinde okutulmalı.
  * Telefon ile PC aynı kullanıcı ise her rol bağlanır; farklı kullanıcı ise yalnız yönetim
    (admin/manager) ve sahip bağlanır — worker başkasının ekranına bağlanamaz.
  * HAREKETSIZLIK_SN boyunca okutma/sipariş değişimi olmazsa eşleşme sunucuda kapanır,
    sonraki okutmalar reddedilir. PC sayfası PC_KAYIP_SN boyunca sormazsa (sekme kapandı) kapanır.
  * Cihaz anahtarı: QR üretilirken PC'ye, QR okutulurken telefona rastgele anahtar verilir; her
    istek hesap + anahtar ile doğrulanır → eşleşme yalnız QR'ı üreten sekme ve okutan telefona aittir.

Zaman damgaları naive UTC (datetime.utcnow) — modeller ile aynı konvansiyon.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, abort, jsonify, render_template, request, session, url_for
from flask_login import current_user

from models import db, HazirlaEslesme, HazirlaOkutma

logger = logging.getLogger(__name__)

hazirla_telefon_bp = Blueprint("hazirla_telefon", __name__, url_prefix="/hazirla-telefon")

QR_GECERLILIK_SN = 120      # QR üretildikten sonra okutulması için süre
HAREKETSIZLIK_SN = 600      # 10 dk işlem yoksa eşleşme kapanır
PC_KAYIP_SN = 60            # PC sayfası bu kadar süre sormazsa (kapandı) eşleşme kapanır
YONETIM_ROLLERI = ("admin", "manager")
AKTIF_DURUMLAR = ("bekliyor", "bagli")
OKUTMA_TIPLERI = ("raf", "urun")


def _simdi() -> datetime:
    return datetime.utcnow()


def _kullanici_adi(user) -> str:
    if not user:
        return ""
    ad = f"{getattr(user, 'first_name', '') or ''} {getattr(user, 'last_name', '') or ''}".strip()
    return ad or getattr(user, "username", "") or ""


def _log(action: str, details: dict) -> None:
    try:
        from user_logs import log_user_action
        log_user_action(action, {"sayfa": "Sipariş Hazırla — Telefon", **details})
    except Exception:  # loglama ana akışı asla kırmasın
        logger.debug("[HAZIRLA-TEL] log yazılamadı", exc_info=True)


# ─────────────────────────── Saf kural (DB yok) ───────────────────────────

def baglanabilir_mi(pc_user, telefon_user) -> tuple[bool, str]:
    """Telefon kullanıcısı bu PC ekranına bağlanabilir mi?

    Aynı hesap → her rol. Farklı hesap → yalnız yönetim (admin/manager) ya da sahip.
    """
    if pc_user is None or telefon_user is None:
        return False, "Kullanıcı bulunamadı."
    if pc_user.id == telefon_user.id:
        return True, ""
    if getattr(telefon_user, "is_owner", False) or telefon_user.role in YONETIM_ROLLERI:
        return True, ""
    return False, "Bu ekrana yalnız kendi hesabınla bağlanabilirsin."


# ─────────────────────────── Eşleşme servisi ───────────────────────────

def eslesme_olustur(pc_user_id: int, eski_eslesme_id: int | None = None,
                    eski_anahtar: str | None = None) -> HazirlaEslesme:
    """Yeni QR oturumu. Aynı sekmenin önceki oturumu (kimlik + anahtar tutarsa) 'yeni_qr' ile kapanır."""
    if eski_eslesme_id:
        eski = HazirlaEslesme.query.get(eski_eslesme_id)
        if (eski and eski.pc_user_id == pc_user_id and eski.durum in AKTIF_DURUMLAR
                and eski.pc_anahtar and eski_anahtar
                and secrets.compare_digest(str(eski.pc_anahtar), str(eski_anahtar))):
            _kapat(eski, "yeni_qr")
    e = HazirlaEslesme(
        token=secrets.token_urlsafe(8),
        pc_user_id=pc_user_id,
        pc_anahtar=secrets.token_urlsafe(24),
        durum="bekliyor",
        created_at=_simdi(),
        pc_son_gorulme_at=_simdi(),
    )
    db.session.add(e)
    db.session.commit()
    return e


def _kapat(e: HazirlaEslesme, sebep: str) -> None:
    if e.durum == "suresi_doldu" or e.durum == "kapandi":
        return
    e.durum = "suresi_doldu" if sebep == "hareketsizlik" else "kapandi"
    e.kapanma_sebebi = sebep
    e.kapandi_at = _simdi()


def eslesme_kapat(e: HazirlaEslesme, sebep: str) -> HazirlaEslesme:
    _kapat(e, sebep)
    db.session.commit()
    return e


def zaman_asimi_denetle(e: HazirlaEslesme) -> HazirlaEslesme:
    """Her istekte: QR süresi, hareketsizlik ve PC kaybı sunucuda denetlenir."""
    now = _simdi()
    if e.durum == "bekliyor":
        if e.created_at and now - e.created_at > timedelta(seconds=QR_GECERLILIK_SN):
            _kapat(e, "qr_suresi")
            db.session.commit()
    elif e.durum == "bagli":
        if e.son_islem_at and now - e.son_islem_at > timedelta(seconds=HAREKETSIZLIK_SN):
            _kapat(e, "hareketsizlik")
            db.session.commit()
            logger.info("[HAZIRLA-TEL] eşleşme %s hareketsizlikten kapandı", e.id)
        elif e.pc_son_gorulme_at and now - e.pc_son_gorulme_at > timedelta(seconds=PC_KAYIP_SN):
            _kapat(e, "pc_kapandi")
            db.session.commit()
            logger.info("[HAZIRLA-TEL] eşleşme %s PC kaybından kapandı", e.id)
    return e


def eslesme_bagla(token: str, telefon_user) -> tuple[HazirlaEslesme | None, str]:
    """QR jetonu ile bağlan. Tek kullanımlık: 'bekliyor' dışındaki her durum reddedilir."""
    token = (token or "").strip()
    if not token:
        return None, "QR kodu okunamadı."
    e = HazirlaEslesme.query.filter_by(token=token).first()
    if not e:
        return None, "Geçersiz QR kodu."
    zaman_asimi_denetle(e)
    if e.durum != "bekliyor":
        return None, "Bu QR kodunun süresi dolmuş ya da kullanılmış. PC'de yeni QR üret."
    ok, hata = baglanabilir_mi(e.pc_user, telefon_user)
    if not ok:
        return None, hata
    now = _simdi()
    e.durum = "bagli"
    e.telefon_user_id = telefon_user.id
    e.telefon_anahtar = secrets.token_urlsafe(24)
    e.bagli_at = now
    e.son_islem_at = now
    db.session.commit()
    return e, ""


def kalan_sn(e: HazirlaEslesme) -> int:
    if e.durum != "bagli" or not e.son_islem_at:
        return 0
    gecen = (_simdi() - e.son_islem_at).total_seconds()
    return max(0, int(HAREKETSIZLIK_SN - gecen))


def pc_senkron(e: HazirlaEslesme, payload: dict | None, son_okutma_id: int) -> list[dict]:
    """PC'nin tur isteği: görüntüyü yaz (değiştiyse sürüm artar = etkinlik), yeni okutmaları çek."""
    now = _simdi()
    e.pc_son_gorulme_at = now
    if payload is not None:
        metin = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if metin != (e.aktif_payload or ""):
            e.aktif_payload = metin
            e.aktif_order_number = (payload.get("order_number") or None)
            e.surum = (e.surum or 0) + 1
            if e.durum == "bagli":
                e.son_islem_at = now
    okutmalar: list[dict] = []
    if e.durum == "bagli":
        q = (HazirlaOkutma.query
             .filter(HazirlaOkutma.eslesme_id == e.id, HazirlaOkutma.id > int(son_okutma_id or 0))
             .order_by(HazirlaOkutma.id.asc()))
        for o in q.all():
            o.islendi_at = now
            okutmalar.append({"id": o.id, "tip": o.tip, "kalem": o.kalem, "adet": o.adet, "deger": o.deger})
    db.session.commit()
    return okutmalar


def telefon_okut(e: HazirlaEslesme, tip: str, kalem: int, adet: int, deger: str) -> tuple[HazirlaOkutma | None, str]:
    if e.durum != "bagli":
        return None, "Bağlantı kapalı. PC'de yeni QR üretip tekrar bağlan."
    if tip not in OKUTMA_TIPLERI:
        return None, "Geçersiz okutma türü."
    deger = (deger or "").strip()
    if not deger:
        return None, "Boş okutma."
    o = HazirlaOkutma(eslesme_id=e.id, tip=tip, kalem=int(kalem or 0), adet=int(adet or 0),
                      deger=deger[:128], created_at=_simdi())
    e.son_islem_at = _simdi()
    db.session.add(o)
    db.session.commit()
    return o, ""


def telefon_durum(e: HazirlaEslesme) -> dict:
    now = _simdi()
    pc_canli = bool(e.pc_son_gorulme_at and (now - e.pc_son_gorulme_at).total_seconds() < 10)
    payload = None
    if e.aktif_payload:
        try:
            payload = json.loads(e.aktif_payload)
        except ValueError:
            payload = None
    return {
        "eslesme_id": e.id,
        "durum": e.durum,
        "kapanma_sebebi": e.kapanma_sebebi,
        "surum": e.surum or 0,
        "payload": payload,
        "pc_kullanici": _kullanici_adi(e.pc_user),
        "pc_canli": pc_canli,
        "kalan_sn": kalan_sn(e),
    }


def qr_data_uri(metin: str) -> str:
    import qrcode
    img = qrcode.make(metin)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# ─────────────────────────── Rotalar ───────────────────────────

@hazirla_telefon_bp.before_request
def _guvenlik_kalkani():
    """Giriş + 2FA şart (app.py kapısının yedeği). JSON POST'lar yalnız fetch ile."""
    try:
        dogrulanmis = current_user.is_authenticated and session.get("totp_verified")
    except Exception:
        dogrulanmis = False
    if not dogrulanmis:
        abort(403)
    if request.method == "POST" and request.headers.get("X-Requested-With") != "fetch":
        abort(403)


def _json() -> dict:
    return request.get_json(silent=True) or {}


def _eslesme_getir(eslesme_id, taraf: str, anahtar) -> HazirlaEslesme | None:
    """Eşleşme + sahiplik: hesap VE cihaz anahtarı birlikte tutmalı.
    PC rotaları PC kullanıcısı + pc_anahtar, telefon rotaları telefon kullanıcısı + telefon_anahtar."""
    try:
        e = HazirlaEslesme.query.get(int(eslesme_id or 0))
    except (TypeError, ValueError):
        return None
    if not e:
        return None
    sahip_id = e.pc_user_id if taraf == "pc" else e.telefon_user_id
    beklenen = e.pc_anahtar if taraf == "pc" else e.telefon_anahtar
    if sahip_id != current_user.id:
        return None
    if not beklenen or not anahtar or not secrets.compare_digest(str(beklenen), str(anahtar)):
        return None
    return zaman_asimi_denetle(e)


@hazirla_telefon_bp.route("/", methods=["GET"], endpoint="sayfa")
def sayfa():
    """Telefon sayfası. ?t=JETON ile açılırsa (QR'ı kamera uygulamasıyla okutma) otomatik bağlanır."""
    return render_template("hazirla_telefon.html", oto_token=(request.args.get("t") or "").strip())


@hazirla_telefon_bp.route("/bagla", methods=["POST"])
def bagla():
    token = (_json().get("token") or "").strip()
    e, hata = eslesme_bagla(token, current_user)
    if not e:
        _log("LOGIN: hazirla_telefon", {"sonuc": "ret", "neden": hata})
        return jsonify({"success": False, "error": hata}), 400
    _log("LOGIN: hazirla_telefon", {"sonuc": "bağlandı", "eslesme": e.id,
                                     "pc_kullanici": _kullanici_adi(e.pc_user)})
    return jsonify({"success": True, "anahtar": e.telefon_anahtar, **telefon_durum(e)})


@hazirla_telefon_bp.route("/telefon/senkron", methods=["POST"])
def telefon_senkron():
    d = _json()
    e = _eslesme_getir(d.get("eslesme_id"), "telefon", d.get("anahtar"))
    if not e:
        return jsonify({"success": False, "durum": "yok", "error": "Eşleşme bulunamadı."}), 404
    return jsonify({"success": True, **telefon_durum(e)})


@hazirla_telefon_bp.route("/telefon/okut", methods=["POST"])
def telefon_okut_rota():
    d = _json()
    e = _eslesme_getir(d.get("eslesme_id"), "telefon", d.get("anahtar"))
    if not e:
        return jsonify({"success": False, "durum": "yok", "error": "Eşleşme bulunamadı."}), 404
    o, hata = telefon_okut(e, d.get("tip"), d.get("kalem"), d.get("adet"), d.get("deger"))
    if not o:
        return jsonify({"success": False, "durum": e.durum, "error": hata}), 400
    return jsonify({"success": True, "okutma_id": o.id, "durum": e.durum, "kalan_sn": kalan_sn(e)})


@hazirla_telefon_bp.route("/telefon/kes", methods=["POST"])
def telefon_kes():
    d = _json()
    e = _eslesme_getir(d.get("eslesme_id"), "telefon", d.get("anahtar"))
    if e and e.durum in AKTIF_DURUMLAR:
        eslesme_kapat(e, "telefon_kes")
        _log("LOGOUT: hazirla_telefon", {"eslesme": e.id, "taraf": "telefon"})
    return jsonify({"success": True})


@hazirla_telefon_bp.route("/pc/baslat", methods=["POST"])
def pc_baslat():
    d = _json()
    e = eslesme_olustur(current_user.id, d.get("eski_eslesme_id"), d.get("eski_anahtar"))
    url = url_for("hazirla_telefon.sayfa", t=e.token, _external=True)
    if request.headers.get("X-Forwarded-Proto", "").lower() == "https" and url.startswith("http://"):
        url = "https://" + url[len("http://"):]   # ters vekil arkasında QR adresi https kalsın
    _log("CREATE: hazirla_telefon", {"eslesme": e.id, "islem": "QR üretildi"})
    return jsonify({"success": True, "eslesme_id": e.id, "anahtar": e.pc_anahtar, "token": e.token,
                    "url": url, "qr": qr_data_uri(url), "gecerlilik_sn": QR_GECERLILIK_SN})


@hazirla_telefon_bp.route("/pc/senkron", methods=["POST"])
def pc_senkron_rota():
    d = _json()
    e = _eslesme_getir(d.get("eslesme_id"), "pc", d.get("anahtar"))
    if not e:
        return jsonify({"success": False, "durum": "yok"}), 404
    payload = d.get("payload") if isinstance(d.get("payload"), dict) else None
    okutmalar = pc_senkron(e, payload, d.get("son_okutma_id") or 0)
    return jsonify({
        "success": True,
        "durum": e.durum,
        "kapanma_sebebi": e.kapanma_sebebi,
        "telefon_kullanici": _kullanici_adi(e.telefon_user),
        "surum": e.surum or 0,
        "okutmalar": okutmalar,
        "kalan_sn": kalan_sn(e),
    })


@hazirla_telefon_bp.route("/pc/kes", methods=["POST"])
def pc_kes():
    d = _json()
    e = _eslesme_getir(d.get("eslesme_id"), "pc", d.get("anahtar"))
    if e and e.durum in AKTIF_DURUMLAR:
        eslesme_kapat(e, "pc_kes")
        _log("LOGOUT: hazirla_telefon", {"eslesme": e.id, "taraf": "pc"})
    return jsonify({"success": True})
