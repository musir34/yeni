"""
AI asistan ayarları — sohbet cevapları için kalıcı genel talimat.

Saklama: motor_ayar.py / trendyol_qna/qna_ayar.py ile aynı PlatformConfig
'ayar torbası' deseni; platform='asistan_ayar' satırının extra_config JSON'unda
tutulur. Migration GEREKMEZ. Talimat boşsa sohbet bugünkü davranışıyla aynı kalır.
"""
import logging

from models import db, PlatformConfig

logger = logging.getLogger(__name__)

PLATFORM_ANAHTAR = "asistan_ayar"
TALIMAT_MAX = 2000


def _kayit(olustur: bool = False) -> PlatformConfig | None:
    kayit = PlatformConfig.query.filter_by(platform=PLATFORM_ANAHTAR).first()
    if kayit is None and olustur:
        kayit = PlatformConfig(platform=PLATFORM_ANAHTAR, is_active=True, extra_config={})
        db.session.add(kayit)
        db.session.flush()
    return kayit


def genel_talimat() -> str:
    """
    Kayıtlı genel talimat ('' = yok). DB'ye erişilemezse sessizce '' döner —
    ayar okunamadı diye asistan durmasın.
    """
    try:
        kayit = _kayit()
        if kayit is not None:
            talimat = (kayit.extra_config or {}).get("genel_talimat")
            if isinstance(talimat, str):
                return talimat.strip()
    except Exception:
        logger.warning("[ASISTAN-AYAR] genel talimat okunamadı", exc_info=True)
        db.session.rollback()
    return ""


def genel_talimat_ayarla(metin: str) -> None:
    """Genel talimatı kalıcı olarak değiştir ('' = talimatı kaldır)."""
    metin = (metin or "").strip()[:TALIMAT_MAX]
    kayit = _kayit(olustur=True)
    kayit.extra_config = {**(kayit.extra_config or {}), "genel_talimat": metin}
    db.session.commit()
