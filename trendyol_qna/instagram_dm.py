"""
Instagram DM entegrasyonu — müşteri mesajları /soru-cevap ekranına düşer.

- Public endpoint: GET/POST /api/instagram/webhook — Meta buraya bildirim atar.
  `/api/` öneki app.py'deki check_authentication'dan bilinçli olarak muaf;
  koruma GET'te doğrulama anahtarı, POST'ta X-Hub-Signature-256 imzasıdır
  (uygulama sırrı tanımlı değilse POST kabul edilmez).
- Yol: "Instagram API with Instagram Login" (graph.instagram.com, Facebook
  sayfası gerekmez). Kendi hesabımız için standart erişim yeterlidir.
- Cevap kuralı: müşterinin SON mesajından itibaren 24 saat içinde yazılabilir.
- Panel tarafı (listeleme + cevaplama) qna_routes.py'den bu modülü çağırır.

Ayarlar (.env):
  INSTAGRAM_APP_SECRET     Meta uygulama sırrı (webhook imzası)
  INSTAGRAM_VERIFY_TOKEN   Webhook kurulumunda Meta paneline yazılan anahtar
  INSTAGRAM_ACCESS_TOKEN   Uzun ömürlü (60 gün) Instagram kullanıcı anahtarı;
                           panel süresi dolmadan yeniler ve yenisini DB'de tutar
  INSTAGRAM_ACCOUNT_ID     (opsiyonel) Instagram hesap ID'si; yoksa /me kullanılır
  INSTAGRAM_API_VERSION    (opsiyonel) ör. v23.0; boşsa sürümsüz çağrılır
  INSTAGRAM_POLL=1         (opsiyonel) webhook yerine/yanında dakikada bir
                           konuşmaları çekerek mesajları al
  INSTAGRAM_COMMENTS=1     (opsiyonel) gönderi yorumlarını 2 dakikada bir çek;
                           anahtarda instagram_business_manage_comments izni gerekir
"""
import hashlib
import hmac
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from models import db, InstagramComment, InstagramConversation, InstagramMessage, PlatformConfig

logger = logging.getLogger(__name__)

instagram_bp = Blueprint("instagram_dm", __name__)

GRAPH_URL = "https://graph.instagram.com"
PLATFORM_ANAHTAR = "instagram_dm"
CEVAP_PENCERESI = timedelta(hours=24)
TEXT_MAX = 1000                      # Instagram metin mesajı üst sınırı
WEBHOOK_MAX_BYTES = 1024 * 1024
TOKEN_YENILEME_ESIGI = timedelta(days=15)
SENKRON_GERIYE = timedelta(days=2)   # yoklamada bundan eski konuşmalar atlanır
PENCERE_DISI_ALT_KOD = 2534022       # Meta: 24 saat penceresi dışında gönderim

DESTEKLENMEYEN_METIN = "[Desteklenmeyen mesaj türü — Instagram uygulamasından bakın]"
EK_METIN = "[Ek gönderildi — Instagram uygulamasından bakın]"


class InstagramHatasi(Exception):
    """Instagram API çağrısı tamamlanamadığında kullanılır."""

    def __init__(self, message: str, code=None, subcode=None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode


# ── Ayarlar / erişim anahtarı ────────────────────────────────────────────────

def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite timezone=True kolonları naive döndürür; UTC varsay."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


def _torba(olustur: bool = False) -> PlatformConfig | None:
    kayit = PlatformConfig.query.filter_by(platform=PLATFORM_ANAHTAR).first()
    if kayit is None and olustur:
        kayit = PlatformConfig(platform=PLATFORM_ANAHTAR, is_active=True, extra_config={})
        db.session.add(kayit)
        db.session.flush()
    return kayit


def _tohum_izi(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def access_token() -> str:
    """Geçerli erişim anahtarı ('' = tanımsız).

    .env'deki anahtar tohumdur; panel onu yeniledikçe yenisini DB'de tutar.
    .env'e yeni bir anahtar yazılırsa (iz değişir) DB'deki eski anahtar
    bırakılır ve .env'deki kullanılır.
    """
    tohum = _env("INSTAGRAM_ACCESS_TOKEN")
    try:
        kayit = _torba()
        ayar = (kayit.extra_config or {}) if kayit is not None else {}
        kayitli = ayar.get("access_token")
        if kayitli and (not tohum or ayar.get("tohum_izi") == _tohum_izi(tohum)):
            return kayitli
    except Exception:
        logger.warning("[INSTAGRAM] kayıtlı erişim anahtarı okunamadı", exc_info=True)
        db.session.rollback()
    return tohum


def configured() -> bool:
    return bool(access_token())


def _api(method: str, path: str, *, params: dict | None = None,
         json_body: dict | None = None, timeout: int = 15) -> dict:
    token = access_token()
    if not token:
        raise InstagramHatasi("Instagram erişim anahtarı tanımlı değil.")
    url = "/".join(p for p in (GRAPH_URL, _env("INSTAGRAM_API_VERSION"), path.lstrip("/")) if p)
    try:
        response = requests.request(
            method, url, params=params, json=json_body,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=(5, timeout),
        )
    except requests.RequestException as exc:
        raise InstagramHatasi("Instagram'a şu anda ulaşılamıyor.") from exc
    try:
        data = response.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    hata = data.get("error")
    if response.status_code >= 400 or hata:
        hata = hata if isinstance(hata, dict) else {}
        raise InstagramHatasi(
            hata.get("message") or f"Instagram HTTP {response.status_code}",
            code=hata.get("code"), subcode=hata.get("error_subcode"),
        )
    return data


def refresh_token_if_needed(force: bool = False) -> bool:
    """Uzun ömürlü anahtarı süresi dolmadan yenile (günlük job). Yenilendiyse True."""
    token = access_token()
    if not token:
        return False
    kayit = _torba()
    ayar = dict((kayit.extra_config or {}) if kayit is not None else {})
    bitis = None
    if ayar.get("access_token") == token and ayar.get("bitis"):
        try:
            bitis = _aware(datetime.fromisoformat(ayar["bitis"]))
        except (TypeError, ValueError):
            bitis = None
    if not force and bitis and bitis - _simdi() > TOKEN_YENILEME_ESIGI:
        return False

    try:
        response = requests.get(
            f"{GRAPH_URL}/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": token},
            timeout=(5, 15),
        )
        data = response.json()
    except (requests.RequestException, ValueError):
        logger.warning("[INSTAGRAM] erişim anahtarı yenilenemedi (bağlantı)")
        return False
    yeni = data.get("access_token") if isinstance(data, dict) else None
    if response.status_code >= 400 or not yeni:
        mesaj = ((data.get("error") or {}).get("message") if isinstance(data, dict) else None)
        logger.warning("[INSTAGRAM] erişim anahtarı yenilenemedi: %s", mesaj or response.status_code)
        return False

    try:
        sure = int(data.get("expires_in") or 0)
    except (TypeError, ValueError):
        sure = 0
    tohum = _env("INSTAGRAM_ACCESS_TOKEN")
    kayit = _torba(olustur=True)
    kayit.extra_config = {
        **(kayit.extra_config or {}),
        "access_token": yeni,
        "tohum_izi": _tohum_izi(tohum) if tohum else "",
        "bitis": (_simdi() + timedelta(seconds=sure)).isoformat() if sure else "",
    }
    db.session.commit()
    logger.info("[INSTAGRAM] erişim anahtarı yenilendi (%s gün geçerli)", sure // 86400)
    return True


_ben_kilit = threading.Lock()
_ben: dict | None = None


def _hesap() -> dict:
    """Kendi hesabımızın kimlikleri (giden/gelen ayrımı için), süreç boyunca saklanır."""
    global _ben
    with _ben_kilit:
        if _ben is not None:
            return _ben
    data = _api("GET", "me", params={"fields": "user_id,username"})
    ben = {
        "idler": {str(v) for v in (data.get("id"), data.get("user_id"), _env("INSTAGRAM_ACCOUNT_ID")) if v},
        "username": (data.get("username") or "").lower(),
    }
    with _ben_kilit:
        _ben = ben
    return ben


# ── Mesaj kaydı ──────────────────────────────────────────────────────────────

def _https(url) -> str:
    """Yalnızca https linki sakla — panelde href/src olarak basılır."""
    url = (url or "").strip() if isinstance(url, str) else ""
    return url if url.lower().startswith("https://") else ""


def kaydet_mesaj(igsid: str, mid: str, direction: str, text: str, created_at: datetime,
                 attachment_type: str = "", attachment_url: str = "",
                 sent_by: str | None = None, username: str = "") -> tuple[InstagramConversation | None, bool, bool]:
    """Mesajı (yoksa) kaydet ve konuşma durumunu güncelle.

    Dönen: (konuşma, eklendi, bekleyene_döndü). mid tekilleştirme anahtarıdır;
    aynı mesaj webhook + yoklama + Meta tekrar denemesiyle birden çok kez
    gelebilir, yalnızca ilki yazılır.
    """
    igsid, mid = str(igsid or "").strip(), str(mid or "").strip()
    if not igsid or not mid or direction not in ("in", "out"):
        return None, False, False
    created_at = _aware(created_at) or _simdi()

    mevcut = InstagramMessage.query.filter_by(mid=mid).first()
    if mevcut is not None:
        conv = db.session.get(InstagramConversation, mevcut.conversation_id)
        if sent_by and not mevcut.sent_by:
            # Echo, panelden gönderim kaydından önce düşmüş: göndereni tamamla
            mevcut.sent_by = sent_by
            if conv is not None and conv.status == "answered":
                conv.answered_by = sent_by
            db.session.commit()
        return conv, False, False

    conv = InstagramConversation.query.filter_by(igsid=igsid).first()
    if conv is None:
        conv = InstagramConversation(igsid=igsid, status="answered", created_at=_simdi())
        db.session.add(conv)
        db.session.flush()
    if username and not conv.username:
        conv.username = username[:120]

    db.session.add(InstagramMessage(
        conversation_id=conv.id, mid=mid[:400], direction=direction,
        text=(text or "")[:4000], attachment_type=(attachment_type or "")[:40],
        attachment_url=_https(attachment_url), sent_by=sent_by, created_at=created_at,
    ))

    onceki_durum = conv.status
    son = _aware(conv.last_message_at)
    en_yeni = son is None or created_at >= son
    if en_yeni:
        conv.last_message_at = created_at
    if direction == "in":
        son_musteri = _aware(conv.last_customer_at)
        if son_musteri is None or created_at > son_musteri:
            conv.last_customer_at = created_at
        if en_yeni:
            conv.status = "new"
            if conv.ai_draft_status != "pending":
                # Eski taslak yeni mesajı görmedi; yenisi üretilecek
                conv.ai_draft, conv.ai_draft_status = None, "none"
    elif en_yeni:
        conv.status = "answered"
        conv.answered_at = created_at
        conv.answered_by = sent_by or "Instagram uygulaması"

    try:
        db.session.commit()
    except IntegrityError:
        # Aynı mesaj eşzamanlı ikinci bir yoldan yazıldı
        db.session.rollback()
        return InstagramConversation.query.filter_by(igsid=igsid).first(), False, False
    return conv, True, (conv.status == "new" and onceki_durum != "new")


# ── Webhook ──────────────────────────────────────────────────────────────────

def _imza_gecerli(govde: bytes, baslik: str | None) -> bool:
    sir = _env("INSTAGRAM_APP_SECRET")
    if not sir or not baslik or not baslik.startswith("sha256="):
        return False
    beklenen = hmac.new(sir.encode("utf-8"), govde, hashlib.sha256).hexdigest()
    return hmac.compare_digest(beklenen, baslik[len("sha256="):])


def _olaylar(payload: dict):
    """Bildirimdeki mesaj olaylarını üret (Meta iki biçimde gönderebiliyor)."""
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        for olay in entry.get("messaging") or []:
            if isinstance(olay, dict):
                yield olay
        for degisim in entry.get("changes") or []:
            if isinstance(degisim, dict) and degisim.get("field") == "messages" \
                    and isinstance(degisim.get("value"), dict):
                yield degisim["value"]


def _olay_isle(olay: dict) -> tuple[InstagramConversation | None, bool, bool]:
    mesaj = olay.get("message")
    if not isinstance(mesaj, dict) or mesaj.get("is_deleted"):
        return None, False, False   # okundu/tepki/silinme olayları soru değildir
    gonderen = str((olay.get("sender") or {}).get("id") or "")
    alici = str((olay.get("recipient") or {}).get("id") or "")
    echo = bool(mesaj.get("is_echo"))
    igsid = alici if echo else gonderen

    try:
        zaman = datetime.fromtimestamp(int(olay.get("timestamp")) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        zaman = _simdi()

    text = mesaj.get("text") if isinstance(mesaj.get("text"), str) else ""
    ek_tipi, ek_url = "", ""
    ekler = mesaj.get("attachments")
    if isinstance(ekler, list) and ekler and isinstance(ekler[0], dict):
        ek_tipi = str(ekler[0].get("type") or "ek")
        ek_url = (ekler[0].get("payload") or {}).get("url") if isinstance(ekler[0].get("payload"), dict) else ""
    hikaye = (mesaj.get("reply_to") or {}).get("story") if isinstance(mesaj.get("reply_to"), dict) else None
    if isinstance(hikaye, dict) and not ek_tipi:
        ek_tipi, ek_url = "story_reply", hikaye.get("url") or ""
    if mesaj.get("is_unsupported"):
        text = text or DESTEKLENMEYEN_METIN
    elif not text and not ek_tipi:
        text = EK_METIN

    return kaydet_mesaj(igsid, mesaj.get("mid"), "out" if echo else "in", text, zaman,
                        attachment_type=ek_tipi, attachment_url=ek_url)


@instagram_bp.route("/api/instagram/webhook", methods=["GET", "POST"])
def instagram_webhook():
    if request.method == "GET":
        anahtar = _env("INSTAGRAM_VERIFY_TOKEN")
        gelen = request.args.get("hub.verify_token") or ""
        if (anahtar and request.args.get("hub.mode") == "subscribe"
                and hmac.compare_digest(anahtar.encode("utf-8"), gelen.encode("utf-8"))):
            return (request.args.get("hub.challenge") or ""), 200, {"Content-Type": "text/plain"}
        return jsonify({"ok": False}), 403

    if (request.content_length or 0) > WEBHOOK_MAX_BYTES:
        return jsonify({"ok": False}), 413
    govde = request.get_data(cache=True)
    if not _imza_gecerli(govde, request.headers.get("X-Hub-Signature-256")):
        logger.warning("[INSTAGRAM] webhook imzası doğrulanamadı")
        return jsonify({"ok": False}), 403

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("object") != "instagram":
        return jsonify({"ok": True})

    bekleyenler: set[int] = set()
    try:
        for olay in _olaylar(payload):
            conv, eklendi, _dondu = _olay_isle(olay)
            if conv is not None and eklendi and conv.status == "new":
                bekleyenler.add(conv.id)
    except Exception:
        # 200 dışı cevapta Meta tekrar dener; mid tekilleştirmesi tekrarı güvenli kılar
        db.session.rollback()
        logger.exception("[INSTAGRAM] webhook işlenemedi")
        return jsonify({"ok": False}), 500

    sonrasi_async(sorted(bekleyenler))
    return jsonify({"ok": True})


# ── Yeni mesaj sonrası: profil + bildirim + AI taslak ────────────────────────

def _profil_tamamla(conv: InstagramConversation) -> None:
    if conv.username:
        return
    try:
        data = _api("GET", conv.igsid, params={"fields": "name,username"})
    except InstagramHatasi as exc:
        logger.warning("[INSTAGRAM] profil alınamadı (%s): %s", conv.id, exc)
        return
    conv.username = (data.get("username") or "")[:120]
    conv.name = (data.get("name") or "")[:160]
    db.session.commit()


def _bildir(conv: InstagramConversation, soru: str) -> None:
    """Trendyol/site sorularıyla aynı 'yeni_soru' abonelerine haber ver."""
    kim = conv.name or (f"@{conv.username}" if conv.username else "Müşteri")
    try:
        from mail_service import notify
        notify(
            "yeni_soru",
            "Instagram: 1 yeni müşteri mesajı",
            "Instagram'dan yeni bir müşteri mesajı geldi:\n\n"
            f"- {kim}: {soru[:200]}"
            "\n\nPanel: /soru-cevap",
        )
    except Exception:
        logger.exception("[INSTAGRAM] yeni mesaj bildirimi gönderilemedi")
    try:
        from whatsapp_alici import alicilar
        from whatsapp_notify import notify_staff_template_async
        ozet = f"{kim}: {soru[:120]}"
        notify_staff_template_async(
            "musteri_sorusu",
            ["Instagram", "Direkt mesaj", ozet],
            fallback=("Instagram mesajı", ozet),
            only_last4=alicilar("soru"),
        )
    except Exception:
        logger.exception("[INSTAGRAM] WhatsApp bildirimi gönderilemedi")


def sonrasi(conv_ids: list[int], bildirilecekler: set[int] | None = None) -> None:
    """Yeni müşteri mesajı düşen konuşmalar için ağır işleri yap (app context içinde)."""
    from trendyol_qna.qna_ai import generate_instagram_draft
    for conv_id in conv_ids:
        try:
            conv = db.session.get(InstagramConversation, conv_id)
            if conv is None or conv.status != "new":
                continue
            _profil_tamamla(conv)
            if bildirilecekler is None or conv_id in bildirilecekler:
                son = (InstagramMessage.query.filter_by(conversation_id=conv.id, direction="in")
                       .order_by(InstagramMessage.created_at.desc()).first())
                _bildir(conv, (son.text if son else "") or EK_METIN)
            generate_instagram_draft(conv_id)
        except Exception:
            db.session.rollback()
            logger.exception("[INSTAGRAM] mesaj sonrası işler tamamlanamadı (konuşma %s)", conv_id)


_bildirim_kilit = threading.Lock()
_son_bildirim: dict[int, datetime] = {}
BILDIRIM_ARALIGI = timedelta(minutes=10)   # art arda yazan müşteri için tek bildirim


def sonrasi_async(conv_ids: list[int]) -> None:
    if not conv_ids:
        return
    simdi = _simdi()
    with _bildirim_kilit:
        bildirilecekler = {c for c in conv_ids
                           if simdi - _son_bildirim.get(c, datetime.min.replace(tzinfo=timezone.utc)) > BILDIRIM_ARALIGI}
        for c in bildirilecekler:
            _son_bildirim[c] = simdi

    def _worker():
        from app import app
        with app.app_context():
            sonrasi(conv_ids, bildirilecekler)

    threading.Thread(target=_worker, name="instagram-dm-sonrasi", daemon=True).start()


# ── Panel tarafı: cevaplama ──────────────────────────────────────────────────

def pencere_bitisi(conv: InstagramConversation) -> datetime | None:
    son = _aware(conv.last_customer_at)
    return son + CEVAP_PENCERESI if son else None


def pencere_acik(conv: InstagramConversation) -> bool:
    bitis = pencere_bitisi(conv)
    return bool(bitis and _simdi() < bitis)


PENCERE_HATASI = ("Müşterinin son mesajının üzerinden 24 saat geçti; Instagram bu "
                  "konuşmaya panelden cevap yazılmasına izin vermiyor.")


def answer_conversation(conv_id: int, text: str, username: str | None = None) -> dict:
    """Cevabı Instagram'dan müşteriye gönder. Dönen: {'ok': bool, 'hata': str|None}"""
    text = (text or "").strip()
    conv = db.session.get(InstagramConversation, conv_id)
    if not conv:
        return {"ok": False, "hata": "Konuşma bulunamadı."}
    if not text:
        return {"ok": False, "hata": "Cevap boş olamaz."}
    if len(text) > TEXT_MAX:
        return {"ok": False, "hata": f"Instagram mesajı en fazla {TEXT_MAX} karakter olabilir."}
    if not pencere_acik(conv):
        return {"ok": False, "hata": PENCERE_HATASI}

    try:
        data = _api(
            "POST", f"{_env('INSTAGRAM_ACCOUNT_ID') or 'me'}/messages",
            json_body={"recipient": {"id": conv.igsid}, "message": {"text": text}},
            timeout=20,
        )
    except InstagramHatasi as exc:
        logger.warning("[INSTAGRAM] cevap gönderilemedi (konuşma %s): %s", conv_id, exc)
        if exc.subcode == PENCERE_DISI_ALT_KOD:
            return {"ok": False, "hata": PENCERE_HATASI}
        return {"ok": False, "hata": f"Instagram cevabı kabul etmedi: {exc}"}

    mid = data.get("message_id") or f"panel-{uuid.uuid4().hex}"
    try:
        kaydet_mesaj(conv.igsid, mid, "out", text, _simdi(), sent_by=username or "panel")
    except Exception:
        # Mesaj müşteriye GİTTİ; yerel kayıt echo/yoklama ile sonradan tamamlanır
        db.session.rollback()
        logger.exception("[INSTAGRAM] gönderilen cevap kaydedilemedi (konuşma %s)", conv_id)
    logger.info("[INSTAGRAM] konuşma %s cevaplandı (%s)", conv_id, username)
    return {"ok": True, "hata": None}


def new_count() -> int:
    """Cevap bekleyen Instagram konuşması sayısı (rozet için)."""
    try:
        return db.session.query(InstagramConversation).filter_by(status="new").count()
    except Exception:
        db.session.rollback()
        logger.exception("[INSTAGRAM] bekleyen sayısı okunamadı")
        return 0


# ── Yoklama (webhook'un yedeği) ──────────────────────────────────────────────

def _zaman_coz(deger) -> datetime | None:
    try:
        return datetime.strptime(str(deger), "%Y-%m-%dT%H:%M:%S%z")
    except (TypeError, ValueError):
        return None


_gorulen_kilit = threading.Lock()
_gorulen: dict[str, str] = {}   # konuşma API ID'si → son işlenen updated_time


def sync_conversations(limit: int = 25) -> int:
    """Son konuşmaları Instagram'dan çekip eksik mesajları kaydet. Dönen: yeni mesaj sayısı.

    Webhook çalışmıyorsa ana yol, çalışıyorsa kaçan mesajlar için yedektir.
    Konuşma başına yalnız son 20 mesajın ayrıntısı alınabilir (Meta sınırı).
    """
    if not configured():
        return 0
    ben = _hesap()
    liste = _api("GET", "me/conversations",
                 params={"platform": "instagram", "fields": "id,updated_time", "limit": limit})
    esik = _simdi() - SENKRON_GERIYE
    eklenen = 0
    bekleyenler: set[int] = set()
    for konusma in liste.get("data") or []:
        kid, guncel = str(konusma.get("id") or ""), str(konusma.get("updated_time") or "")
        zaman = _zaman_coz(guncel)
        if not kid or (zaman and zaman < esik):
            continue
        with _gorulen_kilit:
            if _gorulen.get(kid) == guncel:
                continue
        ayrinti = _api("GET", kid,
                       params={"fields": "messages.limit(20){id,created_time,from,to,message}"})
        mesajlar = ((ayrinti.get("messages") or {}).get("data")) or []
        for m in reversed(mesajlar):   # API yeniden eskiye verir; eskiden yeniye yaz
            gonderen = m.get("from") or {}
            giden = (str(gonderen.get("id") or "") in ben["idler"]
                     or (gonderen.get("username") or "").lower() == ben["username"])
            alicilar_ = ((m.get("to") or {}).get("data")) or []
            musteri = (alicilar_[0] if alicilar_ else {}) if giden else gonderen
            conv, eklendi, _dondu = kaydet_mesaj(
                musteri.get("id"), m.get("id"), "out" if giden else "in",
                m.get("message") or EK_METIN, _zaman_coz(m.get("created_time")) or _simdi(),
                username=musteri.get("username") or "",
            )
            if eklendi:
                eklenen += 1
                if conv is not None and conv.status == "new" and pencere_acik(conv):
                    bekleyenler.add(conv.id)
        with _gorulen_kilit:
            _gorulen[kid] = guncel
    sonrasi_async(sorted(bekleyenler))
    return eklenen


# ── Gönderi yorumları ────────────────────────────────────────────────────────
# Yorum bildirimi (webhook) Meta incelemesi ister; incelemesiz yol son
# gönderilerin yorumlarını aralıklı çekmektir.

YORUM_GONDERI_SAYISI = 20
YORUM_ILK_GORUS = timedelta(days=3)        # ilk görüşte bundan eski yorum içeri alınmaz
OZEL_YANIT_PENCERESI = timedelta(days=7)   # Meta: yoruma özel yanıt süresi
YORUM_NOTU_MAX = 300
YORUM_NOTU_VARSAYILAN = "Merhaba, sorunuzu özelden (DM) yanıtladık 🌹"
BEKLEYEN_YOKLAMA_TURU = 5                  # bekleyen yorumlu gönderi kaç turda bir yeniden bakılır

_yorum_kilit = threading.Lock()
_yorum_sayilari: dict[str, int] = {}       # gönderi ID'si → son görülen yorum sayısı
_yorum_turu = 0


def _gonderi_yorumlari(media_id: str) -> list[dict]:
    alanlar = "id,text,username,timestamp,from"
    try:
        data = _api("GET", f"{media_id}/comments",
                    params={"fields": alanlar + ",replies{id,username,from,timestamp}", "limit": 50})
    except InstagramHatasi:
        # İç içe yanıt alanı desteklenmiyorsa yalnız ana yorumlarla devam et
        data = _api("GET", f"{media_id}/comments", params={"fields": alanlar, "limit": 50})
    return [y for y in (data.get("data") or []) if isinstance(y, dict)]


def _bizden_mi(kayit: dict, ben: dict) -> bool:
    gonderen = kayit.get("from") if isinstance(kayit.get("from"), dict) else {}
    return (str(gonderen.get("id") or "") in ben["idler"]
            or (kayit.get("username") or gonderen.get("username") or "").lower() == ben["username"])


def sync_comments() -> int:
    """Son gönderilerin yorumlarını çekip yenilerini kaydet. Dönen: yeni bekleyen yorum sayısı.

    Yorumu Instagram uygulamasından yanıtladıysak (altında bizim yanıtımız
    varsa) kart kendiliğinden 'answered' olur.
    """
    global _yorum_turu
    if not configured():
        return 0
    ben = _hesap()
    with _yorum_kilit:
        _yorum_turu += 1
        tur = _yorum_turu
    liste = _api("GET", "me/media", params={
        "fields": "id,caption,permalink,media_type,media_url,thumbnail_url,comments_count",
        "limit": YORUM_GONDERI_SAYISI})
    simdi = _simdi()
    yeni = 0
    for gonderi in liste.get("data") or []:
        mid = str(gonderi.get("id") or "")
        try:
            sayi = int(gonderi.get("comments_count") or 0)
        except (TypeError, ValueError):
            sayi = 0
        if not mid or sayi <= 0:
            continue
        with _yorum_kilit:
            degisti = _yorum_sayilari.get(mid) != sayi
        if not degisti:
            bekleyen_var = (tur % BEKLEYEN_YOKLAMA_TURU == 0 and db.session.query(InstagramComment.id)
                            .filter_by(media_id=mid, status="new").first() is not None)
            if not bekleyen_var:
                continue

        gorsel = gonderi.get("thumbnail_url") if gonderi.get("media_type") == "VIDEO" else gonderi.get("media_url")
        for yorum in _gonderi_yorumlari(mid):
            cid = str(yorum.get("id") or "")
            if not cid or _bizden_mi(yorum, ben):
                continue
            yanitlar = ((yorum.get("replies") or {}).get("data")) or []
            yanitladik = any(isinstance(y, dict) and _bizden_mi(y, ben) for y in yanitlar)
            satir = InstagramComment.query.filter_by(comment_id=cid).first()
            if satir is not None:
                if yanitladik and satir.status == "new":
                    satir.status = "answered"
                    satir.answered_by = "Instagram uygulaması"
                    satir.answered_at = simdi
                continue
            zaman = _zaman_coz(yorum.get("timestamp")) or simdi
            if simdi - zaman > YORUM_ILK_GORUS:
                continue
            gonderen = yorum.get("from") if isinstance(yorum.get("from"), dict) else {}
            db.session.add(InstagramComment(
                comment_id=cid, media_id=mid,
                media_caption=(gonderi.get("caption") or "")[:2000],
                media_permalink=_https(gonderi.get("permalink"))[:500],
                media_thumb=_https(gonderi.get("thumbnail_url") or gorsel),
                username=(yorum.get("username") or gonderen.get("username") or "")[:120],
                text=(yorum.get("text") or "")[:4000],
                status="answered" if yanitladik else "new",
                answered_by="Instagram uygulaması" if yanitladik else None,
                answered_at=simdi if yanitladik else None,
                created_at=zaman,
            ))
            if not yanitladik:
                yeni += 1
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()   # aynı yorum eşzamanlı ikinci bir turda yazıldı
            continue
        with _yorum_kilit:
            _yorum_sayilari[mid] = sayi
    return yeni


def ozel_yanit_bitisi(yorum: InstagramComment) -> datetime | None:
    zaman = _aware(yorum.created_at)
    return zaman + OZEL_YANIT_PENCERESI if zaman else None


def answer_comment(yorum_id: int, text: str, public_note: str = "",
                   username: str | None = None) -> dict:
    """Yorumu iki mesajla cevapla: önce özelden (DM) asıl cevap, sonra yorumun altına not.

    DM gitmezse hiçbir şey yayınlanmaz. DM gidip not yayınlanamazsa yorum
    yine cevaplanmış sayılır ve 'uyari' döner.
    Dönen: {'ok': bool, 'hata': str|None, 'uyari': str|None}
    """
    text, public_note = (text or "").strip(), (public_note or "").strip()
    yorum = db.session.get(InstagramComment, yorum_id)
    if not yorum:
        return {"ok": False, "hata": "Yorum bulunamadı.", "uyari": None}
    if yorum.status != "new":
        return {"ok": False, "hata": "Bu yorum zaten kapatılmış.", "uyari": None}
    if not text:
        return {"ok": False, "hata": "Cevap boş olamaz.", "uyari": None}
    if len(text) > TEXT_MAX:
        return {"ok": False, "hata": f"Instagram mesajı en fazla {TEXT_MAX} karakter olabilir.", "uyari": None}
    if len(public_note) > YORUM_NOTU_MAX:
        return {"ok": False, "hata": f"Yorum notu en fazla {YORUM_NOTU_MAX} karakter olabilir.", "uyari": None}
    bitis = ozel_yanit_bitisi(yorum)
    if not bitis or _simdi() >= bitis:
        return {"ok": False, "uyari": None,
                "hata": "Yorumun üzerinden 7 gün geçti; Instagram özelden yanıta izin vermiyor. "
                        "Instagram uygulamasından yanıtlayın ya da yorumu yoksayın."}

    try:
        dm = _api("POST", f"{_env('INSTAGRAM_ACCOUNT_ID') or 'me'}/messages",
                  json_body={"recipient": {"comment_id": yorum.comment_id}, "message": {"text": text}},
                  timeout=20)
    except InstagramHatasi as exc:
        logger.warning("[INSTAGRAM] yoruma özel yanıt gönderilemedi (yorum %s): %s", yorum_id, exc)
        return {"ok": False, "hata": f"Instagram özel yanıtı kabul etmedi: {exc}", "uyari": None}

    uyari = None
    if public_note:
        try:
            _api("POST", f"{yorum.comment_id}/replies", params={"message": public_note}, timeout=20)
        except InstagramHatasi as exc:
            logger.warning("[INSTAGRAM] yorum notu yayınlanamadı (yorum %s): %s", yorum_id, exc)
            public_note = ""
            uyari = f"Özel mesaj gitti ama yorumun altına not yazılamadı: {exc}"

    yorum.status = "answered"
    yorum.answer = text
    yorum.public_note = public_note
    yorum.answered_by = username or "panel"
    yorum.answered_at = _simdi()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("[INSTAGRAM] yorum cevabı kaydedilemedi (yorum %s)", yorum_id)
    # Giden DM konuşma geçmişine de yazılır; müşteri cevap verirse aynı kartta sürer
    try:
        if dm.get("recipient_id") and dm.get("message_id"):
            kaydet_mesaj(dm["recipient_id"], dm["message_id"], "out", text, _simdi(),
                         sent_by=username or "panel", username=yorum.username or "")
    except Exception:
        db.session.rollback()
        logger.exception("[INSTAGRAM] özel yanıt konuşmaya yazılamadı (yorum %s)", yorum_id)
    logger.info("[INSTAGRAM] yorum %s cevaplandı (%s)", yorum_id, username)
    return {"ok": True, "hata": None, "uyari": uyari}


def ignore_comment(yorum_id: int, username: str | None = None) -> dict:
    """Cevap gerektirmeyen yorumu listeden düşür (Instagram'a hiçbir şey gönderilmez)."""
    yorum = db.session.get(InstagramComment, yorum_id)
    if not yorum:
        return {"ok": False, "hata": "Yorum bulunamadı."}
    if yorum.status == "new":
        yorum.status = "ignored"
        yorum.answered_by = username
        yorum.answered_at = _simdi()
        db.session.commit()
    return {"ok": True, "hata": None}


def new_comment_count() -> int:
    """Cevap bekleyen Instagram yorumu sayısı (rozet için)."""
    try:
        return db.session.query(InstagramComment).filter_by(status="new").count()
    except Exception:
        db.session.rollback()
        logger.exception("[INSTAGRAM] bekleyen yorum sayısı okunamadı")
        return 0


def ensure_table_exists() -> None:
    """Tablolar yoksa oluştur (prod'da alembic yok — ShopifyQuestion deseni)."""
    for model in (InstagramConversation, InstagramMessage, InstagramComment):
        try:
            model.__table__.create(bind=db.engine, checkfirst=True)
        except Exception:
            logger.exception("[INSTAGRAM] tablo oluşturma hatası (%s)", model.__tablename__)
