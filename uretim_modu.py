# uretim_modu.py
"""
Üretim Modu (ön sipariş) servisi.

- Ayarlar: PlatformConfig 'ayar torbası' deseni (platform='uretim_ayar') —
  extra_config = {"models": ["0172", ...], "mail_to": "kisi@ornek.com"}.
  Migration GEREKMEZ (desen: trendyol_qna/qna_ayar.py).
- Üretim modundaki modellerin barkodları Trendyol'a daima URETIM_SABIT_ADET
  olarak gider (stock_sync/service.py bu modülden get_uretim_barcodes çağırır).
- Yeni sipariş ingest'inde eşleşen siparişler uretim_siparis tablosuna yazılır
  ve ayarlanan tek adrese anında mail gider (isle_yeni_siparisler).

Tüm okuma fonksiyonları hata durumunda boş/etkisiz döner — stok senkronu ve
sipariş akışı üretim modu yüzünden ASLA durmaz (sözleşme:
stock_sync/listing_policy.get_extra_buffer_map ile aynı).
"""
import json
import logging
import threading
from datetime import datetime

from models import db, PlatformConfig, Product, UretimSiparis

logger = logging.getLogger(__name__)

PLATFORM_ANAHTAR = "uretim_ayar"
URETIM_SABIT_ADET = 5  # Trendyol'a gönderilen sabit stok adedi


def _kayit(olustur: bool = False) -> PlatformConfig | None:
    kayit = PlatformConfig.query.filter_by(platform=PLATFORM_ANAHTAR).first()
    if kayit is None and olustur:
        kayit = PlatformConfig(platform=PLATFORM_ANAHTAR, is_active=True, extra_config={})
        db.session.add(kayit)
        db.session.flush()
    return kayit


def get_uretim_ayar() -> dict:
    """Kayıtlı ayarlar. DB'ye erişilemezse boş ayar döner — akış durmasın."""
    try:
        kayit = _kayit()
        if kayit is not None:
            cfg = kayit.extra_config or {}
            models = cfg.get("models") or []
            mail_to = cfg.get("mail_to") or ""
            return {
                "models": [str(m).strip() for m in models if str(m).strip()],
                "mail_to": str(mail_to).strip(),
            }
    except Exception:
        logger.warning("[URETIM] ayar okunamadı", exc_info=True)
        db.session.rollback()
    return {"models": [], "mail_to": ""}


def set_mail_to(email: str) -> None:
    """Bildirim mail adresini kalıcı olarak değiştir ('' = mail kapalı)."""
    email = (email or "").strip()[:255]
    kayit = _kayit(olustur=True)
    kayit.extra_config = {**(kayit.extra_config or {}), "mail_to": email}
    db.session.commit()


def toggle_model(model_id: str) -> bool:
    """Modeli üretim moduna al/çıkar. Dönüş: yeni durum (True = üretim modunda)."""
    model_id = str(model_id or "").strip()
    if not model_id:
        raise ValueError("model_id boş olamaz")
    kayit = _kayit(olustur=True)
    models = [str(m).strip() for m in (kayit.extra_config or {}).get("models") or []]
    if model_id in models:
        models = [m for m in models if m != model_id]
        acik = False
    else:
        models = models + [model_id]
        acik = True
    kayit.extra_config = {**(kayit.extra_config or {}), "models": models}
    db.session.commit()
    return acik


def get_uretim_models() -> set[str]:
    """Üretim modundaki model kodları (product_main_id). Hata → boş set."""
    return set(get_uretim_ayar()["models"])


def get_uretim_barcodes() -> set[str]:
    """
    Üretim modundaki modellerin TÜM barkodları. Stok senkronunda bu barkodlar
    Trendyol'a daima URETIM_SABIT_ADET olarak gider. Her hata → boş set
    (senkron eski davranışıyla devam eder).
    """
    try:
        models = get_uretim_models()
        if not models:
            return set()
        rows = (Product.query
                .filter(Product.product_main_id.in_(models))
                .with_entities(Product.barcode)
                .all())
        return {r.barcode for r in rows if r.barcode}
    except Exception:
        logger.warning("[URETIM] barkod seti okunamadı", exc_info=True)
        db.session.rollback()
        return set()


def _mail_gonder_async(siparis_id: int, subject: str, body: str, mail_to: str) -> None:
    """Fire-and-forget mail (desen: mail_service.notify). Başarılıysa mail_sent_at yazar."""
    from app import app

    def _send():
        with app.app_context():
            try:
                from mail_service import send_email
                if send_email(subject, body, [mail_to]):
                    kayit = db.session.get(UretimSiparis, siparis_id)
                    if kayit and not kayit.mail_sent_at:
                        kayit.mail_sent_at = datetime.utcnow()
                        db.session.commit()
            except Exception:
                db.session.rollback()
                logger.exception("[URETIM] mail gönderme hatası (yutuldu)")

    thread = threading.Thread(target=_send)
    thread.daemon = True
    thread.start()


def _mail_govdesi(order_number: str, musteri: str, model_kodlari: str,
                  eslesen: list[dict]) -> str:
    from mail_service import build_alert_email_html
    urun_satirlari = "<br>".join(
        f"{u.get('sku') or '-'} <span style=\"color:#888;\">({u.get('barcode')})</span> "
        f"{u.get('color') or ''} {u.get('size') or ''} × {u.get('quantity', 1)}"
        for u in eslesen
    )
    return build_alert_email_html(
        'uretim_siparis',
        headline=f"{order_number} numaralı sipariş üretim modundaki bir modele geldi.",
        summary_rows=[
            ("Sipariş No", order_number),
            ("Müşteri", musteri or "-"),
            ("Model", model_kodlari or "-"),
            ("Ürünler", urun_satirlari or "-"),
        ],
        action_hint=("Üretimi planlayın; ürün rafa girilip /uretim sayfasında "
                     "'Üretildi' işaretlenince sipariş normal akışına devam eder."),
    )


def isle_yeni_siparisler(new_order_dicts: list[dict]) -> int:
    """
    Yeni gelen Trendyol siparişlerinde üretim modundaki modelleri yakalar:
    uretim_siparis kaydı açar + ayarlı adrese mail atar. Sipariş commit'inden
    SONRA çağrılmalıdır (kendi commit'ini yapar). Dönüş: eklenen kayıt sayısı.
    """
    try:
        barkod_seti = get_uretim_barcodes()
        if not barkod_seti or not new_order_dicts:
            return 0
        from barcode_alias_helper import normalize_barcode
        ayar = get_uretim_ayar()
        eklenen = 0
        for order_dict in new_order_dicts:
            try:
                order_number = str(order_dict.get('order_number') or '').strip()
                if not order_number:
                    continue
                details_json = order_dict.get('details')
                details = json.loads(details_json) if isinstance(details_json, str) else (details_json or [])
                if not isinstance(details, list):
                    continue
                eslesen = []
                for item in details:
                    bc = normalize_barcode(str(item.get('barcode', '') or '').strip())
                    if bc and bc in barkod_seti:
                        eslesen.append({
                            'barcode': bc,
                            'sku': item.get('sku') or '',
                            'color': item.get('color') or '',
                            'size': item.get('size') or '',
                            'quantity': int(item.get('quantity', 1) or 1),
                        })
                if not eslesen:
                    continue
                # Resync koruması: aynı sipariş için ikinci kayıt açılmaz.
                if UretimSiparis.query.filter_by(order_number=order_number).first():
                    continue

                # Model kodları details'ten DEĞİL Product'tan alınır — details'teki
                # product_main_id Trendyol contentId'dir, panel model kodu değildir.
                model_rows = (Product.query
                              .filter(Product.barcode.in_([u['barcode'] for u in eslesen]))
                              .with_entities(Product.product_main_id)
                              .all())
                model_kodlari = ",".join(sorted({r.product_main_id for r in model_rows if r.product_main_id}))
                musteri = f"{order_dict.get('customer_name', '')} {order_dict.get('customer_surname', '')}".strip()

                kayit = UretimSiparis(
                    order_number=order_number,
                    package_number=order_dict.get('package_number'),
                    product_main_id=model_kodlari,
                    details=json.dumps(eslesen, ensure_ascii=False),
                    customer_name=musteri,
                    order_date=order_dict.get('order_date'),
                )
                db.session.add(kayit)
                db.session.commit()
                eklenen += 1
                logger.info(f"[URETIM] 🏭 Üretim siparişi kaydedildi: {order_number} (model: {model_kodlari})")

                if ayar["mail_to"]:
                    _mail_gonder_async(
                        kayit.id,
                        subject=f"🏭 Üretim siparişi — {order_number} ({model_kodlari})",
                        body=_mail_govdesi(order_number, musteri, model_kodlari, eslesen),
                        mail_to=ayar["mail_to"],
                    )
            except Exception:
                db.session.rollback()
                logger.exception(f"[URETIM] sipariş işlenemedi (yutuldu): {order_dict.get('order_number')}")
        return eklenen
    except Exception:
        db.session.rollback()
        logger.exception("[URETIM] isle_yeni_siparisler hatası (yutuldu)")
        return 0
