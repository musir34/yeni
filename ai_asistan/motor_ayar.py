"""
AI motoru seçimi (claude | codex) — panelden anlık değiştirilebilir ayar.

Saklama: yeni tablo açmamak için mevcut PlatformConfig 'ayar torbası' deseni
kullanılır (order_list_service'teki platform='order_pull' kaydıyla aynı fikir):
platform='ai_motor' satırının extra_config JSON'unda alan başına motor tutulur.
Migration GEREKMEZ.

Kayıt yoksa veya değer geçersizse .env'deki AI_MOTOR'a düşülür → panelde hiç
dokunulmamış kurulumlarda davranış bugünküyle birebir aynı kalır.
"""
import logging

from models import db, PlatformConfig

logger = logging.getLogger(__name__)

PLATFORM_ANAHTAR = "ai_motor"
GECERLI_MOTORLAR = ("claude", "codex")
# Motor seçimi olan alanlar: panel sohbeti ve Trendyol Q&A taslakları.
GECERLI_ALANLAR = ("asistan", "qna")


def _kayit(olustur: bool = False) -> PlatformConfig | None:
    kayit = PlatformConfig.query.filter_by(platform=PLATFORM_ANAHTAR).first()
    if kayit is None and olustur:
        kayit = PlatformConfig(platform=PLATFORM_ANAHTAR, is_active=True, extra_config={})
        db.session.add(kayit)
        db.session.flush()
    return kayit


def aktif_motor(alan: str) -> str:
    """
    İlgili alanın motoru: DB ayarı > .env AI_MOTOR > 'claude'.
    DB'ye erişilemezse (tablo yok, bağlantı hatası) sessizce env'e düşer —
    ayar okunamadı diye asistan çalışmaz duruma gelmesin.
    """
    from ai_asistan.blueprint import AI_MOTOR

    try:
        kayit = _kayit()
        if kayit is not None:
            secim = (kayit.extra_config or {}).get(alan)
            if secim in GECERLI_MOTORLAR:
                return secim
    except Exception:
        logger.warning("[AI-MOTOR] ayar okunamadı, AI_MOTOR env'ine düşülüyor", exc_info=True)
        db.session.rollback()

    return AI_MOTOR if AI_MOTOR in GECERLI_MOTORLAR else "claude"


def motorlari_getir() -> dict:
    """Tüm alanların aktif motoru — UI'da seçili değeri göstermek için."""
    return {alan: aktif_motor(alan) for alan in GECERLI_ALANLAR}


def motor_ayarla(alan: str, motor: str) -> None:
    """
    Alanın motorunu kalıcı olarak değiştir. Geçersiz alan/motor → ValueError.
    extra_config JSON sütunu yerinde değiştirilirse SQLAlchemy değişikliği
    algılamaz; bu yüzden yeni bir sözlük atanır.
    """
    if alan not in GECERLI_ALANLAR:
        raise ValueError(f"Geçersiz alan: {alan}")
    if motor not in GECERLI_MOTORLAR:
        raise ValueError(f"Geçersiz motor: {motor}")

    kayit = _kayit(olustur=True)
    kayit.extra_config = {**(kayit.extra_config or {}), alan: motor}
    db.session.commit()
