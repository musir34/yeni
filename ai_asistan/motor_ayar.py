"""
AI motoru seçimi (claude | codex) — panelden anlık değiştirilebilir ayar.

Saklama: yeni tablo açmamak için mevcut PlatformConfig 'ayar torbası' deseni
kullanılır (order_list_service'teki platform='order_pull' kaydıyla aynı fikir):
platform='ai_motor' satırının extra_config JSON'unda alan başına motor tutulur.
Migration GEREKMEZ.

Kayıt yoksa veya değer geçersizse .env'deki AI_MOTOR'a düşülür → panelde hiç
dokunulmamış kurulumlarda davranış bugünküyle birebir aynı kalır.

Codex model seçimi de aynı torbada tutulur ('<alan>_codex_model' anahtarı):
kayıt yoksa .env'deki CODEX_MODEL, o da boşsa codex'in kendi varsayılanı geçerli.
"""
import logging
import re

from models import db, PlatformConfig

logger = logging.getLogger(__name__)

PLATFORM_ANAHTAR = "ai_motor"
GECERLI_MOTORLAR = ("claude", "codex")
# Motor seçimi olan alanlar: panel sohbeti ve Trendyol Q&A taslakları.
GECERLI_ALANLAR = ("asistan", "qna")
# UI'da hazır sunulan Codex modelleri; serbest girişle başka model de yazılabilir.
CODEX_HAZIR_MODELLER = ("gpt-5.2", "gpt-5.1-codex-max", "gpt-5.1-codex-mini")
# Model adı doğrulaması: alt sürece argüman gidiyor, keyfi metin kabul edilmez.
_MODEL_DESENI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


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


def codex_model(alan: str) -> str:
    """
    İlgili alanın Codex modeli: DB ayarı > .env CODEX_MODEL. Boş dize codex'in
    kendi yapılandırmasındaki varsayılan model demektir (bilinçli seçim olabilir).
    DB'ye erişilemezse aktif_motor ile aynı sebepten sessizce env'e düşer.
    """
    from ai_asistan.blueprint import CODEX_MODEL

    try:
        kayit = _kayit()
        if kayit is not None:
            secim = (kayit.extra_config or {}).get(f"{alan}_codex_model")
            if isinstance(secim, str):
                return secim
    except Exception:
        logger.warning("[AI-MOTOR] codex model ayarı okunamadı, CODEX_MODEL env'ine düşülüyor", exc_info=True)
        db.session.rollback()

    return CODEX_MODEL


def codex_modelleri_getir() -> dict:
    """Tüm alanların Codex modeli — UI'da seçili değeri göstermek için."""
    return {alan: codex_model(alan) for alan in GECERLI_ALANLAR}


def codex_model_ayarla(alan: str, model: str) -> None:
    """
    Alanın Codex modelini kalıcı olarak değiştir. Boş dize = codex varsayılanı.
    Geçersiz alan veya desene uymayan model adı → ValueError.
    """
    if alan not in GECERLI_ALANLAR:
        raise ValueError(f"Geçersiz alan: {alan}")
    model = (model or "").strip()
    if model and not _MODEL_DESENI.match(model):
        raise ValueError(f"Geçersiz model adı: {model}")

    kayit = _kayit(olustur=True)
    kayit.extra_config = {**(kayit.extra_config or {}), f"{alan}_codex_model": model}
    db.session.commit()
