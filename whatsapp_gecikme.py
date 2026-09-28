"""
Gecikme WhatsApp bildirimleri: kargoya verilme süresi dolmak üzere olan ve
dolmuş siparişleri çalışanlara bildirir (şablonlar: gecikme_uyarisi, geciken_siparis).

Saat başı çalışır; her sipariş her tür için YALNIZ BİR KEZ bildirilir. Bildirilenler
PlatformConfig('whatsapp_gecikme_kayit').extra_config içinde tutulur (migration yok):
    {"uyari": {"<order_number>": "<iso utc>"}, "geciken": {...}}

Gecikme tanımı panelle aynıdır (overdue_orders): Yeni / Hazırlanıyor / İşleme
Alındı statüsündeki siparişin teslim son tarihi, datetime.utcnow() ile karşılaştırılır.
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

PLATFORM = "whatsapp_gecikme_kayit"
UYARI_ESIK_SAAT = 4
LISTE_MAX = 12          # şablon değişkeni 200 karakterde kesilir; ~12 sipariş no sığar
KAYIT_SAKLAMA_GUN = 30  # bildirildi kayıtları bu süreden sonra budanır


def _adaylar(now: datetime) -> tuple[list[str], list[str]]:
    """(uyarı, geciken) sipariş numaraları — son tarihe göre en acil önce."""
    from models import db
    from overdue_orders import OVERDUE_STATUSES, deadline_expr

    sinir = now + timedelta(hours=UYARI_ESIK_SAAT)
    satirlar = []
    for _key, model, _label in OVERDUE_STATUSES:
        d = deadline_expr(model)
        satirlar.extend(
            db.session.query(model.order_number, d)
            .filter(d.isnot(None), d < sinir)
            .all()
        )
    en_erken: dict[str, datetime] = {}
    for no, son_tarih in satirlar:
        no = str(no or "").strip()
        if no and (no not in en_erken or son_tarih < en_erken[no]):
            en_erken[no] = son_tarih
    sirali = sorted(en_erken.items(), key=lambda kv: kv[1])
    geciken = [no for no, t in sirali if t < now]
    uyari = [no for no, t in sirali if t >= now]
    return uyari, geciken


def _liste_metni(nolar: list[str]) -> str:
    metin = ", ".join(nolar[:LISTE_MAX])
    if len(nolar) > LISTE_MAX:
        metin += f" (+{len(nolar) - LISTE_MAX} sipariş daha)"
    return metin


def _kayit_oku() -> dict:
    from models import PlatformConfig
    kayit = PlatformConfig.query.filter_by(platform=PLATFORM).first()
    veri = dict(kayit.extra_config or {}) if kayit else {}
    return {"uyari": dict(veri.get("uyari") or {}), "geciken": dict(veri.get("geciken") or {})}


def _kayit_yaz(veri: dict, now: datetime) -> None:
    from models import db, PlatformConfig
    esik = (now - timedelta(days=KAYIT_SAKLAMA_GUN)).isoformat(timespec="seconds")
    budanmis = {tur: {no: t for no, t in kayitlar.items() if t >= esik}
                for tur, kayitlar in veri.items()}
    kayit = PlatformConfig.query.filter_by(platform=PLATFORM).first()
    if kayit is None:
        kayit = PlatformConfig(platform=PLATFORM, is_active=True, extra_config={})
        db.session.add(kayit)
        db.session.flush()
    kayit.extra_config = budanmis
    db.session.commit()


def _gonder(tur: str, nolar: list[str]) -> bool:
    """Bildirimi gönderir; en az bir alıcıda Meta kabul ettiyse True."""
    from whatsapp_alici import alicilar
    from whatsapp_notify import notify_staff_template

    sayi, liste = str(len(nolar)), _liste_metni(nolar)
    if tur == "uyari":
        kime = alicilar("gecikme_uyarisi")
        sablon, params = "gecikme_uyarisi", [sayi, f"{UYARI_ESIK_SAAT} saatten az", liste]
        yedek = ("Gecikme uyarısı", f"{sayi} siparişin süresi dolmak üzere: {liste}")
    else:
        kime = alicilar("geciken_siparis")
        sablon, params = "geciken_siparis", [sayi, liste]
        yedek = ("Geciken sipariş", f"{sayi} siparişin süresi geçti: {liste}")
    if not kime:
        return False
    sonuclar = notify_staff_template(sablon, params, fallback=yedek, only_last4=kime)
    return any(s.get("ok") for s in sonuclar)


def gecikme_bildir(now: datetime | None = None) -> dict:
    """Yeni uyarı/gecikme siparişlerini bildirir. Asla istisna fırlatmaz.
    Dönen: {"uyari": gönderilen sipariş sayısı, "geciken": ...}"""
    from whatsapp_notify import is_configured

    ozet = {"uyari": 0, "geciken": 0}
    if not is_configured():
        return ozet
    now = now or datetime.utcnow()
    try:
        uyari, geciken = _adaylar(now)
        kayit = _kayit_oku()
        damga = now.isoformat(timespec="seconds")
        degisti = False
        # Doğrudan gecikmiş yakalanan sipariş için "dolmak üzere" uyarısı anlamsızdır.
        for tur, nolar in (("uyari", uyari), ("geciken", geciken)):
            yeni = [no for no in nolar if no not in kayit[tur]]
            if not yeni or not _gonder(tur, yeni):
                continue
            kayit = {**kayit, tur: {**kayit[tur], **{no: damga for no in yeni}}}
            ozet[tur] = len(yeni)
            degisti = True
        if degisti:
            _kayit_yaz(kayit, now)
            logger.info(f"[WA-GECIKME] bildirildi: {ozet}")
    except Exception:
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        logger.exception("[WA-GECIKME] gecikme bildirimi hatası (yutuldu)")
    return ozet
