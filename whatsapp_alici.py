"""
WhatsApp bildirim alıcı dağılımı: hangi bildirim türü hangi numaraya gider.

Numaraların kendisi .env'de (WHATSAPP_STAFF_NUMBERS) durur; burada yalnız son
4 hane anahtarıyla ad + abone olunan olaylar tutulur:
PlatformConfig('whatsapp_alici_ayar').extra_config =
    {"alicilar": {"0953": {"ad": "Mağaza", "olaylar": ["soru", ...]}, ...}}

Kayıt yoksa ILK_DAGILIM geçerlidir; orada da olmayan numara tüm olayları alır.
"""
import logging

logger = logging.getLogger(__name__)

PLATFORM = "whatsapp_alici_ayar"
AD_MAX = 30

# (anahtar, ekranda görünen ad) — sütun sırası budur
OLAYLAR = (
    ("uretim_siparis", "Üretim"),
    ("uretim_iptal", "İptal"),
    ("soru", "Soru"),
    ("gecikme_uyarisi", "Gecikme"),
    ("geciken_siparis", "Geciken"),
    ("duyuru", "Duyuru"),
)
OLAY_ANAHTARLARI = tuple(k for k, _ in OLAYLAR)

# Komutanın 2026-09-28 kararı: üretim Ahmet'e, diğerleri mağaza hattına.
ILK_DAGILIM = {
    "0953": {"ad": "Mağaza", "olaylar": ["soru", "gecikme_uyarisi", "geciken_siparis", "duyuru"]},
    "0104": {"ad": "Ahmet", "olaylar": ["uretim_siparis", "uretim_iptal", "duyuru"]},
}


def _kayitli() -> dict | None:
    """DB'deki dağılım; kayıt yoksa None. DB hatası çağırana fırlar."""
    from models import PlatformConfig
    kayit = PlatformConfig.query.filter_by(platform=PLATFORM).first()
    if kayit is None:
        return None
    return dict((kayit.extra_config or {}).get("alicilar") or {})


def dagilim() -> list[dict]:
    """Ekran için: .env'deki her numaranın adı ve olayları (sıra .env sırası)."""
    from whatsapp_notify import staff_last4
    try:
        kayitli = _kayitli()
    except Exception:
        _rollback()
        logger.exception("[WA-ALICI] dağılım okunamadı")
        kayitli = None
    kaynak = ILK_DAGILIM if kayitli is None else kayitli
    satirlar = []
    for son4 in staff_last4():
        ayar = kaynak.get(son4)
        if ayar is None:
            ayar = ILK_DAGILIM.get(son4) or {"ad": "", "olaylar": list(OLAY_ANAHTARLARI)}
        satirlar.append({
            "son4": son4,
            "ad": str(ayar.get("ad") or ""),
            "olaylar": [o for o in OLAY_ANAHTARLARI if o in (ayar.get("olaylar") or [])],
        })
    return satirlar


def alicilar(olay: str) -> list[str]:
    """Olaya abone numaraların son 4 haneleri (notify_* only_last4 için).
    Dağılım okunamazsa bildirim kaybolmasın diye tüm numaralar döner."""
    try:
        return [s["son4"] for s in dagilim() if olay in s["olaylar"]]
    except Exception:
        logger.exception("[WA-ALICI] alıcılar çözülemedi, herkese gönderilecek")
        from whatsapp_notify import staff_last4
        return staff_last4()


def kaydet(satirlar: list[dict]) -> None:
    """Dağılımı yazar. Yalnız .env'deki numaralar ve bilinen olaylar kabul edilir."""
    from models import db, PlatformConfig
    from whatsapp_notify import staff_last4

    gecerli = set(staff_last4())
    yeni = {}
    for s in satirlar:
        son4 = str(s.get("son4") or "")
        if son4 not in gecerli:
            raise ValueError(f"Bilinmeyen alıcı: …{son4}")
        secilen = s.get("olaylar")
        if not isinstance(secilen, list):
            raise ValueError("Olay listesi geçersiz.")
        yeni[son4] = {
            "ad": " ".join(str(s.get("ad") or "").split())[:AD_MAX],
            "olaylar": [o for o in OLAY_ANAHTARLARI if o in secilen],
        }

    kayit = PlatformConfig.query.filter_by(platform=PLATFORM).first()
    if kayit is None:
        kayit = PlatformConfig(platform=PLATFORM, is_active=True, extra_config={})
        db.session.add(kayit)
        db.session.flush()
    kayit.extra_config = {**(kayit.extra_config or {}), "alicilar": yeni}
    db.session.commit()


def _rollback() -> None:
    try:
        from models import db
        db.session.rollback()
    except Exception:
        pass
