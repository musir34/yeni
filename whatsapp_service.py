"""
WhatsApp Cloud API bildirim servisi — mail_service'in ikizi.

Çalışanlara olay bazlı WhatsApp bildirimi gönderir. Abonelik kaynağı
mail ile AYNIDIR: users.notify_events (kullanıcı yönetimi → Bildirimler).
Kullanıcının whatsapp_no alanı doluysa mail'e EK olarak WhatsApp gider.

Meta kuralı: işletmenin başlattığı mesaj onaylı ŞABLON olmak zorundadır.
Tek genel şablon kullanılır (iki gövde parametresi: başlık + detay);
şablon adı/dili .env'den ayarlanır. Config eksikse servis sessizce
devre dışıdır (is_configured() False) — mail akışı hiç etkilenmez.

Kimlik kaynağı ve öncelik: Coexistence bağlantısı (/whatsapp-baglanti) token +
phone_number_id'yi PlatformConfig('whatsapp_ayar') içine yazar. Token'da .env
WHATSAPP_TOKEN öncelikli (elle alınmış kalıcı sistem-kullanıcısı anahtarı
buradan geçersiz kılınabilir), yoksa DB; numara kimliğinde DB öncelikli,
yoksa .env WHATSAPP_PHONE_NUMBER_ID.

.env anahtarları:
  WHATSAPP_TOKEN            Cloud API kalıcı erişim anahtarı (opsiyonel, DB'yi ezer)
  WHATSAPP_PHONE_NUMBER_ID  Gönderen numaranın phone_number_id'si (DB yoksa)
  WHATSAPP_TEMPLATE_NAME    Onaylı şablon adı (varsayılan: gullu_bildirim)
  WHATSAPP_TEMPLATE_LANG    Şablon dili (varsayılan: tr)
  WHATSAPP_API_VERSION      Graph API sürümü (varsayılan: v21.0)
"""
import os
import threading

import requests

TIMEOUT = 15


def _db_ayar() -> dict:
    """PlatformConfig('whatsapp_ayar').extra_config — hata halinde boş sözlük."""
    try:
        from models import PlatformConfig
        kayit = PlatformConfig.query.filter_by(platform="whatsapp_ayar").first()
        return dict(kayit.extra_config or {}) if kayit else {}
    except Exception:
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        return {}


def _kimlikler() -> tuple[str | None, str | None]:
    """(token, phone_number_id) — docstring'deki öncelik sırasıyla."""
    ayar = _db_ayar()
    token = os.environ.get("WHATSAPP_TOKEN") or ayar.get("token")
    phone_number_id = ayar.get("phone_number_id") or os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    return token, phone_number_id


def is_configured() -> bool:
    """Cloud API kimlik bilgileri (.env ya da bağlantı sayfası) tanımlı mı?"""
    token, phone_number_id = _kimlikler()
    return bool(token and phone_number_id)


def normalize_whatsapp_no(raw: str) -> str | None:
    """Numarayı Cloud API biçimine çevirir: 905xxxxxxxxx (E.164, + işaretsiz).
    Kabul edilen girişler: 05xx..., 5xx..., 905xx..., +905xx... (boşluk/tire serbest).
    Geçersizse None döner."""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if digits.startswith("0090"):
        digits = digits[4:]
    if digits.startswith("90") and len(digits) == 12:
        pass
    elif digits.startswith("0") and len(digits) == 11:
        digits = "9" + digits
    elif digits.startswith("5") and len(digits) == 10:
        digits = "90" + digits
    else:
        return None
    if not digits.startswith("905"):
        return None
    return digits


def _get_wa_recipients_for_event(event: str) -> list[str]:
    """Belirli bir olay için bildirim açık VE WhatsApp numarası dolu
    kullanıcıların numaralarını döner (desen: _get_recipients_for_event)."""
    try:
        from models import User
        users = User.query.filter_by(status='active').all()
        recipients = []
        for u in users:
            if u.notify_events and event in u.notify_events.split(','):
                if getattr(u, 'whatsapp_no', None):
                    recipients.append(u.whatsapp_no)
        return recipients
    except Exception as e:
        print(f"WhatsApp alıcıları alınamadı: {e}")
        return []


def _temiz_parametre(text: str) -> str:
    """Meta şablon parametrelerinde yeni satır/sekme yasak — düzleştirir."""
    tek_satir = " ".join(str(text or "").split())
    return tek_satir[:900]  # şablon parametre uzunluk sınırına tampon


def _post_message(payload: dict, to_number: str) -> bool:
    token, phone_number_id = _kimlikler()
    version = os.environ.get("WHATSAPP_API_VERSION", "v21.0")
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=TIMEOUT,
        )
        if resp.status_code >= 400:
            print(f"WhatsApp gönderme hatası ({to_number}): {resp.status_code} {resp.text[:300]}")
            return False
        return True
    except Exception as e:
        print(f"WhatsApp gönderme hatası ({to_number}): {e}")
        return False


def send_whatsapp_template(to_number: str, baslik: str, detay: str) -> bool:
    """Onaylı şablonla mesaj gönderir (işletme başlatan mesaj — ücretli).
    Şablon gövdesi iki parametre bekler: {{1}}=başlık, {{2}}=detay."""
    if not is_configured():
        return False
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": os.environ.get("WHATSAPP_TEMPLATE_NAME", "gullu_bildirim"),
            "language": {"code": os.environ.get("WHATSAPP_TEMPLATE_LANG", "tr")},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": _temiz_parametre(baslik)},
                    {"type": "text", "text": _temiz_parametre(detay)},
                ],
            }],
        },
    }
    return _post_message(payload, to_number)


def send_whatsapp_text(to_number: str, text: str) -> bool:
    """Serbest metin gönderir — YALNIZCA 24 saatlik müşteri hizmetleri
    penceresi açıksa ulaşır (alıcı son 24 saatte numaraya yazdıysa).
    Kurulum testi için kullanışlıdır."""
    if not is_configured():
        return False
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": str(text or "")[:4000]},
    }
    return _post_message(payload, to_number)


def notify_whatsapp(event: str, baslik: str, detay: str) -> None:
    """
    Belirli bir olay için WhatsApp bildirimi gönderir (arka planda).
    Sadece o olayı seçmiş VE numarası kayıtlı kullanıcılara gider.
    Config yoksa hiçbir şey yapmaz (desen: mail_service.notify).
    """
    if not is_configured():
        return
    from app import app

    def _send():
        with app.app_context():
            for numara in _get_wa_recipients_for_event(event):
                send_whatsapp_template(numara, baslik, detay)

    thread = threading.Thread(target=_send)
    thread.daemon = True
    thread.start()
