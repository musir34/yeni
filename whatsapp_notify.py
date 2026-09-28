"""Çalışanlara WhatsApp bildirimi gönderir (Meta Cloud API, test numarası).

whatsapp_service'ten (şirket hattı / Coexistence, alıcılar kullanıcı
yönetiminden) BAĞIMSIZDIR: ayarlarını ayrı WHATSAPP_STAFF_* anahtarlarından
okur, böylece iki hat birbirinin anahtarını/numarasını ezmez.

.env anahtarları:
  WHATSAPP_STAFF_TOKEN            Kalıcı erişim anahtarı (sistem kullanıcısı)
  WHATSAPP_STAFF_PHONE_NUMBER_ID  Gönderen (test) numaranın phone_number_id'si
  WHATSAPP_STAFF_NUMBERS          Alıcılar: 905xxxxxxxxx,905yyyyyyyyy (yalnız rakam)
  WHATSAPP_STAFF_TEMPLATE_NAME    Onaylı şablon adı (varsayılan: gullu_bildirim)
  WHATSAPP_STAFF_TEMPLATE_LANG    Şablon dili (varsayılan: en)
  WHATSAPP_STAFF_API_VERSION      Graph API sürümü (varsayılan: v25.0)
"""
import logging
import os
import threading

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10
MAX_PARAM_LENGTH = 200


class WhatsAppConfigError(RuntimeError):
    """Zorunlu ayar eksik."""


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise WhatsAppConfigError(f"Eksik ortam değişkeni: {name}")
    return value


def _api_url() -> str:
    version = os.environ.get("WHATSAPP_STAFF_API_VERSION", "v25.0")
    phone_id = _require_env("WHATSAPP_STAFF_PHONE_NUMBER_ID")
    return f"https://graph.facebook.com/{version}/{phone_id}/messages"


def _staff_numbers() -> list[str]:
    raw = _require_env("WHATSAPP_STAFF_NUMBERS")
    return [n.strip() for n in raw.split(",") if n.strip().isdigit()]


def _clean_param(value: str) -> str:
    """Şablon değişkeninde satır sonu, sekme ve 4+ boşluk yasak."""
    single_line = " ".join(str(value).split())
    return single_line[:MAX_PARAM_LENGTH] or "-"


def _post(payload: dict) -> dict:
    headers = {
        "Authorization": f"Bearer {_require_env('WHATSAPP_STAFF_TOKEN')}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        _api_url(), json=payload, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
    )
    body = response.json() if response.content else {}
    if response.status_code != 200:
        error = body.get("error", {})
        return {
            "ok": False,
            "code": error.get("code"),
            "message": error.get("message", f"HTTP {response.status_code}"),
        }
    return {"ok": True, "message_id": body.get("messages", [{}])[0].get("id")}


def _template_payload(to: str, event_type: str, summary: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": {
            "name": os.environ.get("WHATSAPP_STAFF_TEMPLATE_NAME", "gullu_bildirim"),
            "language": {"code": os.environ.get("WHATSAPP_STAFF_TEMPLATE_LANG", "en")},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": _clean_param(event_type)},
                        {"type": "text", "text": _clean_param(summary)},
                    ],
                }
            ],
        },
    }


def _send_one(to: str, event_type: str, summary: str) -> dict:
    """Her zaman onaylı şablonla gönderir. Serbest metin KULLANILMAZ: Meta,
    24 saat penceresi kapalıyken de isteği 200 ile kabul edip mesajı sonradan
    (yalnız webhook'a bildirerek, hata 131047) düşürüyor; yani "önce metin,
    olmazsa şablon" geçişi hiç tetiklenmiyor ve mesaj sessizce kayboluyor."""
    return {**_post(_template_payload(to, event_type, summary)), "via": "template"}


def is_configured() -> bool:
    """Gönderim için zorunlu üç anahtar da tanımlı mı?"""
    return all(
        os.environ.get(name, "").strip()
        for name in ("WHATSAPP_STAFF_TOKEN", "WHATSAPP_STAFF_PHONE_NUMBER_ID",
                     "WHATSAPP_STAFF_NUMBERS")
    )


def staff_last4() -> list[str]:
    """Alıcı listesinin yalnız son 4 haneleri (arayüzde seçim için)."""
    try:
        return [n[-4:] for n in _staff_numbers()]
    except WhatsAppConfigError:
        return []


def notify_staff(event_type: str, summary: str,
                 only_last4: list[str] | None = None) -> list[dict]:
    """Tüm çalışanlara bildirim gönderir. Asla istisna fırlatmaz:
    bildirim hatası asıl işlemi (soru kaydı, sipariş vb.) bozmamalı.
    only_last4 verilirse yalnız son 4 hanesi listede olan alıcılara gider."""
    results = []
    try:
        numbers = _staff_numbers()
    except WhatsAppConfigError as exc:
        logger.error("WhatsApp bildirimi atlandı: %s", exc)
        return results
    if only_last4 is not None:
        numbers = [n for n in numbers if n[-4:] in only_last4]

    for number in numbers:
        try:
            result = _send_one(number, event_type, summary)
        except (requests.RequestException, WhatsAppConfigError, ValueError) as exc:
            result = {"ok": False, "code": None, "message": str(exc)}
        if not result["ok"]:
            logger.error(
                "WhatsApp bildirimi gitmedi (…%s): %s %s",
                number[-4:], result.get("code"), result.get("message"),
            )
        results.append({"to_last4": number[-4:], **result})
    return results


def notify_staff_async(event_type: str, summary: str) -> None:
    """notify_staff'ı arka planda çalıştırır (isteği/poll turunu bekletmez).
    Ayarlar girilmemişse sessizce hiçbir şey yapmaz."""
    if not is_configured():
        return
    threading.Thread(
        target=notify_staff, args=(event_type, summary), daemon=True
    ).start()
