"""
WhatsApp Coexistence bağlantı sayfası (/whatsapp-baglanti).

Şirket hattını (WhatsApp Business uygulamasındaki numarayı) Meta Embedded
Signup ile Cloud API'ye bağlar — telefondaki uygulama kullanımı BOZULMAZ.

Akış: sayfadaki "Bağla" düğmesi Meta'nın Embedded Signup penceresini açar
(featureType=whatsapp_business_app_onboarding). Yönetici numarayı seçip
telefondaki WhatsApp Business uygulamasıyla onaylar. Meta'nın döndürdüğü
code sunucuda erişim anahtarına çevrilir; WABA/numara kimlikleriyle birlikte
PlatformConfig('whatsapp_ayar').extra_config içine yazılır. whatsapp_service
bu ayarı okur (bkz. oradaki öncelik notu). Anahtar ~60 günde bir dolar;
yenilemek için bu sayfadan akışı tekrar çalıştırmak yeterlidir.

Güvenlik kalkanı deseni: uretim_routes (2FA + fetch başlığı) + admin rolü.
"""
import logging
import os

import requests
from flask import Blueprint, jsonify, render_template, request, session

logger = logging.getLogger(__name__)

whatsapp_baglanti_bp = Blueprint("whatsapp_baglanti", __name__,
                                 url_prefix="/whatsapp-baglanti")

# Uygulama kimlikleri gizli değildir; sır olan yalnızca FB_APP_SECRET'tır (.env).
FB_APP_ID = os.environ.get("FB_APP_ID", "1365245268503883")
ES_CONFIG_ID = os.environ.get("WHATSAPP_ES_CONFIG_ID", "4433252376929907")
GRAPH_VERSION = os.environ.get("WHATSAPP_API_VERSION", "v21.0")
TIMEOUT = 20


@whatsapp_baglanti_bp.before_request
def _guvenlik_kalkani():
    from flask import abort
    from flask_login import current_user
    try:
        dogrulanmis = (current_user.is_authenticated
                       and session.get("totp_verified")
                       and getattr(current_user, "role", "") == "admin")
    except Exception:
        dogrulanmis = False
    if not dogrulanmis:
        abort(403)
    if request.method == "POST" and request.headers.get("X-Requested-With") != "fetch":
        abort(403)


def _ayar_oku() -> dict:
    """PlatformConfig('whatsapp_ayar').extra_config sözlüğünü döner."""
    try:
        from models import PlatformConfig
        kayit = PlatformConfig.query.filter_by(platform="whatsapp_ayar").first()
        return dict(kayit.extra_config or {}) if kayit else {}
    except Exception:
        from models import db
        db.session.rollback()
        logger.exception("[WA-BAGLANTI] ayar okunamadı")
        return {}


def _ayar_yaz(yeni: dict) -> None:
    """Ayar torbasını uretim_modu deseniyle (yeni dict, in-place mutasyon yok) yazar."""
    from models import db, PlatformConfig
    kayit = PlatformConfig.query.filter_by(platform="whatsapp_ayar").first()
    if kayit is None:
        kayit = PlatformConfig(platform="whatsapp_ayar", is_active=True, extra_config={})
        db.session.add(kayit)
        db.session.flush()
    kayit.extra_config = {**(kayit.extra_config or {}), **yeni}
    db.session.commit()


@whatsapp_baglanti_bp.route("", methods=["GET"])
@whatsapp_baglanti_bp.route("/", methods=["GET"])
def sayfa():
    ayar = _ayar_oku()
    return render_template(
        "whatsapp_baglanti.html",
        fb_app_id=FB_APP_ID,
        es_config_id=ES_CONFIG_ID,
        graph_version=GRAPH_VERSION,
        app_secret_hazir=bool(os.environ.get("FB_APP_SECRET")),
        mevcut={
            "waba_id": ayar.get("waba_id") or "",
            "phone_number_id": ayar.get("phone_number_id") or "",
            "baglandi_at": ayar.get("baglandi_at") or "",
            "token_var": bool(ayar.get("token")),
        },
    )


@whatsapp_baglanti_bp.route("/api/tamamla", methods=["POST"])
def tamamla():
    """Embedded Signup dönüşü: code'u erişim anahtarına çevirir ve kaydeder."""
    veri = request.get_json(silent=True) or {}
    code = (veri.get("code") or "").strip()
    waba_id = str(veri.get("waba_id") or "").strip()
    phone_number_id = str(veri.get("phone_number_id") or "").strip()
    if not code:
        return jsonify({"success": False, "message": "code eksik."}), 400

    app_secret = os.environ.get("FB_APP_SECRET")
    if not app_secret:
        return jsonify({"success": False,
                        "message": ".env'de FB_APP_SECRET tanımlı değil."}), 500

    try:
        resp = requests.get(
            f"https://graph.facebook.com/{GRAPH_VERSION}/oauth/access_token",
            params={"client_id": FB_APP_ID, "client_secret": app_secret, "code": code},
            timeout=TIMEOUT,
        )
        gövde = resp.json() if resp.content else {}
        token = gövde.get("access_token")
        if resp.status_code >= 400 or not token:
            logger.warning(f"[WA-BAGLANTI] token değişimi hatası: {resp.status_code} {str(gövde)[:300]}")
            return jsonify({"success": False,
                            "message": f"Meta token değişimi başarısız: {gövde.get('error', {}).get('message', resp.status_code)}"}), 502
    except Exception as e:
        logger.exception("[WA-BAGLANTI] token değişimi isteği hatası")
        return jsonify({"success": False, "message": f"Meta'ya ulaşılamadı: {e}"}), 502

    # WABA'yı uygulamaya abone et (mesaj gönderimi için gerekli; hata ölümcül değil).
    abone_ok = False
    if waba_id:
        try:
            r2 = requests.post(
                f"https://graph.facebook.com/{GRAPH_VERSION}/{waba_id}/subscribed_apps",
                headers={"Authorization": f"Bearer {token}"},
                timeout=TIMEOUT,
            )
            abone_ok = r2.status_code < 400
            if not abone_ok:
                logger.warning(f"[WA-BAGLANTI] subscribed_apps hatası: {r2.status_code} {r2.text[:300]}")
        except Exception:
            logger.exception("[WA-BAGLANTI] subscribed_apps isteği hatası")

    # Bildirim şablonunu onaya gönder (WABA uygulama-tarafındayken WhatsApp
    # Manager'dan yapılamıyor; bağlantı sonrası API'den açılır). Idempotent:
    # şablon zaten varsa Meta hata döner, akışı bozmaz.
    sablon_ok = False
    if waba_id:
        try:
            r3 = requests.post(
                f"https://graph.facebook.com/{GRAPH_VERSION}/{waba_id}/message_templates",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "name": os.environ.get("WHATSAPP_TEMPLATE_NAME", "gullu_bildirim"),
                    "language": "tr",
                    "category": "UTILITY",
                    "components": [{
                        "type": "BODY",
                        "text": ("Güllü Panel bildirimi: {{1}}\n"
                                 "Detay: {{2}}\n"
                                 "Bu bildirim Güllü Panel sipariş sistemi tarafından "
                                 "otomatik olarak gönderilmiştir. Sorularınız için "
                                 "lütfen mağaza yönetimiyle iletişime geçin."),
                        "example": {"body_text": [[
                            "Üretim siparişi 123456789 sisteme düştü",
                            "Model 0121 | Adet 2 | Üretimi planlayın",
                        ]]},
                    }],
                },
                timeout=TIMEOUT,
            )
            sablon_ok = r3.status_code < 400
            if not sablon_ok:
                logger.warning(f"[WA-BAGLANTI] şablon oluşturma: {r3.status_code} {r3.text[:300]}")
        except Exception:
            logger.exception("[WA-BAGLANTI] şablon oluşturma isteği hatası")

    from datetime import datetime
    _ayar_yaz({
        "token": token,
        "waba_id": waba_id,
        "phone_number_id": phone_number_id,
        "baglandi_at": datetime.utcnow().isoformat(timespec="seconds"),
        "subscribed": abone_ok,
        "template_submitted": sablon_ok,
    })
    logger.info(f"[WA-BAGLANTI] ✅ bağlantı kaydedildi (waba={waba_id}, phone={phone_number_id}, abone={abone_ok})")
    return jsonify({"success": True, "waba_id": waba_id,
                    "phone_number_id": phone_number_id, "subscribed": abone_ok})


@whatsapp_baglanti_bp.route("/api/test", methods=["POST"])
def test_gonder():
    """Kayıtlı yapılandırmayla tek numaraya şablon mesajı dener."""
    veri = request.get_json(silent=True) or {}
    from whatsapp_service import normalize_whatsapp_no, send_whatsapp_template
    numara = normalize_whatsapp_no(veri.get("numara") or "")
    if not numara:
        return jsonify({"success": False, "message": "Geçersiz numara."}), 400
    ok = send_whatsapp_template(numara, "Güllü Panel test bildirimi",
                                "Coexistence bağlantısı çalışıyor ✅")
    return jsonify({"success": ok,
                    "message": "Gönderildi." if ok else "Gönderilemedi — sunucu loguna bakın (şablon onayı/kayıt eksik olabilir)."})
