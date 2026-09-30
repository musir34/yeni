# uretim_modu.py
"""
Üretim Modu (ön sipariş) servisi.

- Ayarlar: PlatformConfig 'ayar torbası' deseni (platform='uretim_ayar') —
  extra_config = {"models": ["0172", ...]}. Migration GEREKMEZ
  (desen: trendyol_qna/qna_ayar.py).
- Üretim modundaki modellerin barkodları Trendyol'a daima URETIM_SABIT_ADET
  olarak gider (stock_sync/service.py bu modülden get_uretim_barcodes çağırır).
- Yeni sipariş ingest'inde eşleşen siparişler uretim_siparis tablosuna yazılır
  ve 'uretim_siparis' olayına abone kullanıcılara anında mail gider
  (kullanıcı yönetimi → Bildirimler; mail_service.notify aboneliği).

Tüm okuma fonksiyonları hata durumunda boş/etkisiz döner — stok senkronu ve
sipariş akışı üretim modu yüzünden ASLA durmaz (sözleşme:
stock_sync/listing_policy.get_extra_buffer_map ile aynı).
"""
import json
import logging
import os
from datetime import datetime

from models import db, PlatformConfig, Product, UretimSiparis

logger = logging.getLogger(__name__)

PLATFORM_ANAHTAR = "uretim_ayar"
URETIM_SABIT_ADET = 10  # Trendyol'a gönderilen sabit stok adedi


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
            return {"models": [str(m).strip() for m in models if str(m).strip()]}
    except Exception:
        logger.warning("[URETIM] ayar okunamadı", exc_info=True)
        db.session.rollback()
    return {"models": []}


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


def uretim_ekranindaki_siparisler() -> set[str]:
    """Üretim ekranında işi bitmemiş (paketlendi=False) üretim kayıtlarının
    sipariş numaraları. Sipariş hazırla bu SİTE siparişlerini paketleyene sunmaz:
    üretim + raf okutma + etiket üretim ekranından yürür, 'Paketlendi' ile
    Shopify'da Hazirlaniyor'a geçer. Hata → boş set (hiçbir sipariş gizlenmez)."""
    try:
        return {r.order_number for r in
                UretimSiparis.query.filter_by(paketlendi=False)
                .with_entities(UretimSiparis.order_number)}
    except Exception:
        logger.warning("[URETIM] üretim ekranındaki siparişler okunamadı", exc_info=True)
        db.session.rollback()
        return set()


SHOPIFY_ONBELLEK_SN = 300
_shopify_onbellek: dict[str, tuple[float, object]] = {}


def shopify_siparis(order_number: str):
    """Site siparişinin canlı hali (siparis_hazirla'nın sahte sipariş nesnesi:
    details panel barkodlarıyla, müşteri/adres, kapıda ödeme). Site siparişleri
    panel tablolarına inmediği için üretim ekranı içeriği buradan okur.
    SHOPIFY_ONBELLEK_SN saniye önbelleklenir. Hata/bulunamadı → None."""
    import time
    simdi = time.monotonic()
    kayit = _shopify_onbellek.get(order_number)
    if kayit and simdi - kayit[0] < SHOPIFY_ONBELLEK_SN:
        return kayit[1]
    try:
        from shopify_site.shopify_service import shopify_service
        from siparis_hazirla import _shopify_order_to_hazirla_format
        sonuc = shopify_service.get_order(order_number.replace("SH-", "", 1))
        if not (sonuc.get("success") and sonuc.get("order")):
            return None
        raw = sonuc["order"]
        raw["line_items"] = raw.get("line_items") or []
        siparis, _ = _shopify_order_to_hazirla_format(raw)
    except Exception:
        logger.warning("[URETIM] site siparişi okunamadı: %s", order_number, exc_info=True)
        db.session.rollback()
        return None
    _shopify_onbellek[order_number] = (simdi, siparis)
    return siparis


def _raf_stok_haritasi(barkodlar: list[str]) -> dict[str, int]:
    """Barkod → rafta toplam adet. Hata → boş harita (raf önceliği devre
    dışı kalır, kalemler eski davranışla üretime yazılır)."""
    try:
        from models import RafUrun
        rows = (db.session.query(RafUrun.urun_barkodu, db.func.sum(RafUrun.adet))
                .filter(RafUrun.urun_barkodu.in_(barkodlar), RafUrun.adet > 0)
                .group_by(RafUrun.urun_barkodu)
                .all())
        return {bc: int(toplam or 0) for bc, toplam in rows}
    except Exception:
        logger.warning("[URETIM] raf stok haritası okunamadı", exc_info=True)
        db.session.rollback()
        return {}


def _acik_raf_talepleri(barkod_seti: set[str]) -> list[dict]:
    """Rafı bekleyen açık talepler: Yeni + Hazırlanıyor (toplanmamış) siparişlerin
    üretim modundaki barkodlu kalemleri —
    [{"order_number", "order_date", "barcode", "quantity"}].
    Üretim kaydına yazılmış kalem (raftan alınmayacak) ve rafı zaten okutulmuş
    kalem (raf stoğundan düşülmüş) talep sayılmaz. Hata → boş liste (rezerv
    düşülmez, eski iyimser davranış)."""
    try:
        from barcode_alias_helper import normalize_barcode
        from models import OrderCreated, OrderHazirlaniyor, StockMovement
        rows = (db.session.query(OrderCreated.order_number, OrderCreated.order_date,
                                 OrderCreated.details).all()
                + db.session.query(OrderHazirlaniyor.order_number,
                                   OrderHazirlaniyor.order_date,
                                   OrderHazirlaniyor.details)
                    .filter(OrderHazirlaniyor.toplandi_at.is_(None)).all())
        talepler = []
        for order_number, order_date, details_str in rows:
            try:
                det = json.loads(details_str) if isinstance(details_str, str) else details_str
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(det, list):
                continue
            for item in det:
                bc = normalize_barcode(str(item.get('barcode', '') or '').strip())
                if bc and bc in barkod_seti:
                    talepler.append({
                        'order_number': str(order_number),
                        'order_date': order_date,
                        'barcode': bc,
                        'quantity': int(item.get('quantity', 1) or 1),
                    })
        if not talepler:
            return []
        siparisler = list({t['order_number'] for t in talepler})
        uretimde = set()
        for k in (UretimSiparis.query
                  .filter(UretimSiparis.order_number.in_(siparisler))
                  .with_entities(UretimSiparis.order_number, UretimSiparis.details)
                  .all()):
            for u in uretim_kalemleri(k):
                uretimde.add((k.order_number, u['barcode']))
        anahtarlar = [pick_key(t['order_number'], t['barcode']) for t in talepler]
        okutulan = {r[0] for r in
                    db.session.query(StockMovement.idempotency_key)
                    .filter(StockMovement.idempotency_key.in_(anahtarlar))
                    .all()}
        return [t for t in talepler
                if (t['order_number'], t['barcode']) not in uretimde
                and pick_key(t['order_number'], t['barcode']) not in okutulan]
    except Exception:
        logger.warning("[URETIM] açık raf talepleri okunamadı", exc_info=True)
        db.session.rollback()
        return []


def _oncelikli_rezerv(talepler: list[dict], order_number: str, order_date) -> dict[str, int]:
    """Bu siparişten ÖNCE gelmiş açık taleplerin barkod → adet toplamı (FIFO):
    raftaki adet önce eski siparişin hakkıdır. Tarihi bilinmeyen/karşılaştırılamayan
    talep önce gelmiş sayılır (güvenli taraf: kalem üretime yazılır)."""
    rezerv: dict[str, int] = {}
    for t in talepler:
        if t['order_number'] == order_number:
            continue
        try:
            once = (t['order_date'] is None or order_date is None
                    or t['order_date'] <= order_date)
        except TypeError:
            once = True
        if once:
            rezerv[t['barcode']] = rezerv.get(t['barcode'], 0) + t['quantity']
    return rezerv


def _siparis_tam_detay(order_number: str) -> list[dict]:
    """Siparişin TAM kalem listesi — aktif→arşiv sipariş tablolarında ilk bulunan.
    with_entities: prod'da orders_archived kolon adları model ile birebir değil,
    tam entity select patlar. Hata/bulunamadı → boş liste."""
    from models import (OrderCreated, OrderHazirlaniyor, OrderPicking,
                        OrderShipped, OrderDelivered, OrderArchived)
    for M in (OrderCreated, OrderHazirlaniyor, OrderPicking,
              OrderShipped, OrderDelivered, OrderArchived):
        row = (M.query.filter_by(order_number=order_number)
               .with_entities(M.details).first())
        if row and row.details:
            try:
                det = json.loads(row.details) if isinstance(row.details, str) else row.details
                if isinstance(det, list):
                    return det
            except (json.JSONDecodeError, TypeError):
                pass
    # 🛍️ Site siparişi panel tablolarında yok — içerik Shopify'dan.
    if str(order_number).startswith("SH-"):
        siparis = shopify_siparis(order_number)
        try:
            det = json.loads(siparis.details) if siparis else []
            if isinstance(det, list):
                return det
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def raftan_kalemler(kayit) -> list[dict]:
    """Üretim kaydındaki siparişin RAFTAN toplanacak kalemleri:
    [{"barcode", "quantity"}] — tam sipariş içeriğinden üretim kalemleri çıkarılır."""
    from barcode_alias_helper import normalize_barcode
    try:
        uretim_bcs = {normalize_barcode(str(u.get("barcode") or "").strip())
                      for u in (json.loads(kayit.details) if kayit.details else [])}
    except (json.JSONDecodeError, TypeError):
        uretim_bcs = set()
    kalemler = []
    for item in _siparis_tam_detay(kayit.order_number):
        bc = normalize_barcode(str(item.get("barcode", "") or "").strip())
        if bc and bc not in uretim_bcs:
            kalemler.append({"barcode": bc, "quantity": int(item.get("quantity", 1) or 1)})
    return kalemler


def uretim_kalemleri(kayit) -> list[dict]:
    """Üretim kaydının ÜRETİLECEK kalemleri: [{"barcode","quantity"}] —
    kayit.details'ten okunur (canlı sipariş tablosu gerekmez), barkod bazında
    adetler toplanır. Hata → boş liste."""
    from barcode_alias_helper import normalize_barcode
    toplam: dict[str, int] = {}
    try:
        for u in (json.loads(kayit.details) if kayit.details else []):
            bc = normalize_barcode(str(u.get("barcode") or "").strip())
            if bc:
                toplam[bc] = toplam.get(bc, 0) + int(u.get("quantity", 1) or 1)
    except (json.JSONDecodeError, TypeError):
        return []
    return [{"barcode": b, "quantity": q} for b, q in toplam.items()]


def dogrulama_sayilari(order_number: str) -> dict[str, int]:
    """Üretim kalemi doğrulama okutmaları: barkod → okutulan adet. Hata → boş
    (boş = okutulmamış sayılır → etiket kilitli kalır, güvenli taraf)."""
    from models import UretimDogrulama
    try:
        rows = (db.session.query(UretimDogrulama.barcode, db.func.count())
                .filter(UretimDogrulama.order_number == order_number)
                .group_by(UretimDogrulama.barcode)
                .all())
        return {b: int(c) for b, c in rows}
    except Exception:
        logger.warning("[URETIM] doğrulama sayıları okunamadı", exc_info=True)
        db.session.rollback()
        return {}


def eksik_uretim_dogrulamalar(kayit) -> list[str]:
    """Henüz gereken adedi okutulmamış ÜRETİM kalemi barkodları."""
    sayilar = dogrulama_sayilari(kayit.order_number)
    return [k["barcode"] for k in uretim_kalemleri(kayit)
            if sayilar.get(k["barcode"], 0) < k["quantity"]]


def pick_key(order_number: str, barcode: str) -> str:
    """Raf okutma ledger idempotency anahtarı — picking_service ile BİREBİR aynı
    format: iki ekrandan hangisi okutursa okutsun ikinci düşüm engellenir."""
    return f"{order_number}:pick:{barcode}"


def kargoda_raftan_dusulmeyecekler(order_number: str, barkodlar: list[str]) -> set[str]:
    """Üretim kaydı olan sipariş kargolanırken (ledger ship_out) raftan
    DÜŞÜLMEYECEK barkodlar: üretimden gelen kalemler (rafa hiç girmedi — düşülürse
    raftaki iade sistemden silinir) + üretim ekranında rafı okutulmuş kalemler
    (zaten düşüldü — tekrar düşülürse çift düşüm). Kayıt yok / hata → boş küme
    (ledger eski davranışıyla devam eder)."""
    try:
        order_number = str(order_number or "").strip()
        kayit = UretimSiparis.query.filter_by(order_number=order_number).first()
        if not kayit:
            return set()
        from stock_ledger import has_movement
        atla = {k["barcode"] for k in uretim_kalemleri(kayit)}
        atla |= {bc for bc in barkodlar if has_movement(pick_key(order_number, bc))}
        return atla
    except Exception:
        logger.warning("[URETIM] kargoda düşülmeyecek kalemler okunamadı", exc_info=True)
        db.session.rollback()
        return set()


def raftan_karsilandi_bildir(kayit, kalemler: list[dict], raf_kodu: str) -> None:
    """Üretilecek kalem sonradan rafa giren stoktan karşılandı → üretici boşuna
    üretmesin. 'uretim_iptal' abonelerine mail + WhatsApp (ayrı abonelik olayı
    açılmadı: alıcı kitlesi aynı — üretimi durdurması gerekenler). Her hata yutulur."""
    urun, adet = _wa_urun_ozeti(kalemler)
    try:
        from mail_service import notify, build_alert_email_html
        govde = build_alert_email_html(
            'uretim_raftan',
            headline=f"{kayit.order_number} numaralı siparişin ürünü RAFTAN karşılandı.",
            summary_rows=[
                ("Sipariş No", kayit.order_number),
                ("Müşteri", kayit.customer_name or "-"),
                ("Model", kayit.product_main_id or "-"),
                ("Raftan alınan", _urun_satirlari_html(kalemler) or "-"),
                ("Raf", raf_kodu or "-"),
            ],
            action_hint="Bu kalemi ÜRETMEYİN — ürün rafta bulundu ve siparişe ayrıldı.",
        )
        notify('uretim_iptal',
               subject=f"📦 Raftan karşılandı, ÜRETMEYİN — {kayit.order_number} ({kayit.product_main_id})",
               body=govde)
    except Exception:
        logger.exception("[URETIM] raftan karşılama mail bildirimi hatası (yutuldu)")
    detay = (f"Sipariş: {kayit.order_number} | Ürün: {urun} | Adet: {adet} | "
             f"Raf: {raf_kodu or '-'} | Bu kalemi ÜRETMEYİN.")
    try:
        from whatsapp_service import notify_whatsapp
        notify_whatsapp('uretim_iptal',
                        f"📦 Raftan karşılandı — {kayit.order_number}", detay)
    except Exception:
        logger.exception("[URETIM] raftan karşılama whatsapp bildirimi hatası (yutuldu)")
    try:
        from whatsapp_alici import alicilar
        from whatsapp_notify import notify_staff_async
        kime = alicilar("uretim_iptal")
        if kime:
            notify_staff_async("Raftan karşılandı — ÜRETMEYİN", detay, only_last4=kime)
    except Exception:
        logger.exception("[URETIM] raftan karşılama personel bildirimi hatası (yutuldu)")


def eksik_raf_okutmalar(order_number: str) -> list[str]:
    """Kargo etiketi kilidi: üretim kaydı olan siparişte henüz okutulmamış
    kalem barkodları — RAFTAN kalemler (raf okutması) VE ÜRETİLEN kalemler
    (adet adet doğrulama okutması). Kayıt yok / sipariş zaten kargolanmış /
    hata → [] (engel yok — normal akış asla durmaz)."""
    try:
        order_number = str(order_number or "").strip()
        if not order_number:
            return []
        kayit = UretimSiparis.query.filter_by(order_number=order_number).first()
        if not kayit:
            return []
        # Kargolanmış siparişin etiketini tekrar basmak engellenmez.
        from models import OrderShipped, OrderDelivered, OrderArchived
        for M in (OrderShipped, OrderDelivered, OrderArchived):
            if (M.query.filter_by(order_number=order_number)
                    .with_entities(M.order_number).first()):
                return []
        from stock_ledger import has_movement
        eksik = [k["barcode"] for k in raftan_kalemler(kayit)
                 if not has_movement(pick_key(order_number, k["barcode"]))]
        # Üretilen kalemler de okutulmadan etiket YOK (yanlış ürün gitmesin).
        eksik += [b for b in eksik_uretim_dogrulamalar(kayit) if b not in eksik]
        return eksik
    except Exception:
        logger.warning("[URETIM] raf okutma kontrolü yapılamadı", exc_info=True)
        db.session.rollback()
        return []


def _urun_satirlari_html(eslesen: list[dict]) -> str:
    """Mail için üretilecek kalem satırları — ürün görselli. Görsel Product.images
    ilk URL'den gelir; mutlak (http) değilse mail istemcisi erişemeyeceği için
    görsel basılmaz. Hata → görselsiz satırlar (mail yine gider)."""
    gorsel_map: dict[str, str] = {}
    try:
        barkodlar = [str(u.get("barcode") or "").strip() for u in eslesen]
        barkodlar = [b for b in barkodlar if b]
        if barkodlar:
            rows = (Product.query
                    .filter(Product.barcode.in_(barkodlar))
                    .with_entities(Product.barcode, Product.images)
                    .all())
            for bc, images in rows:
                url = (images or "").split(",")[0].strip()
                if url.startswith("http"):
                    gorsel_map[bc] = url
    except Exception:
        logger.warning("[URETIM] mail görselleri okunamadı", exc_info=True)
        db.session.rollback()
    satirlar = []
    for u in eslesen:
        url = gorsel_map.get(str(u.get("barcode") or "").strip())
        img = (f'<img src="{url}" width="52" height="52" alt="" '
               f'style="border-radius:8px;object-fit:cover;vertical-align:middle;'
               f'margin-right:10px;border:1px solid #eee;">' if url else "")
        satirlar.append(
            f'<div style="margin:4px 0;display:flex;align-items:center;">{img}'
            f'<span>{u.get("sku") or "-"} <span style="color:#888;">({u.get("barcode")})</span> '
            f'{u.get("color") or ""} {u.get("size") or ""} × {u.get("quantity", 1)}</span></div>'
        )
    return "".join(satirlar)


def _wa_urun_ozeti(eslesen: list[dict]) -> tuple[str, str]:
    """WhatsApp şablonu için (ürün metni, toplam adet). Çok kalemde ilk kalem
    yazılır, kalanlar "(+N kalem daha)" ile belirtilir."""
    if not eslesen:
        return "-", "-"
    ilk = eslesen[0]
    urun = " ".join(str(x) for x in (ilk.get("sku"), ilk.get("color"), ilk.get("size")) if x) or "-"
    if len(eslesen) > 1:
        urun += f" (+{len(eslesen) - 1} kalem daha)"
    adet = 0
    for u in eslesen:
        try:
            adet += int(u.get("quantity", 1) or 0)
        except (TypeError, ValueError):
            adet += 1
    return urun, str(adet)


def _wa_gorsel_adresi(ham: str) -> str | None:
    """Ham görsel değerini Meta'nın indirebileceği adrese çevirir: herkese açık
    https + JPG/PNG. Panelin /static yolu girişsiz açıktır; göreli yol panel
    adresiyle tamamlanır. Uygun değilse None."""
    url = (ham or "").strip()
    if not url:
        return None
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    elif not url.startswith("https://"):
        taban = os.environ.get("PANEL_BASE_URL", "https://gullupanel.com").rstrip("/")
        url = f"{taban}/{url.lstrip('/')}"
    yol = url.split("?", 1)[0].lower()
    return url if yol.endswith((".jpg", ".jpeg", ".png")) else None


def _wa_urun_gorseli(eslesen: list[dict]) -> str | None:
    """İlk kalemin ürün görseli: Product.images ilk değeri, yoksa panelde
    barkod adıyla yüklü dosya (static/images/<barkod>.jpg|png). Yoksa/hata → None."""
    barkod = str((eslesen[0] if eslesen else {}).get("barcode") or "").strip()
    if not barkod:
        return None
    try:
        row = (Product.query.filter(Product.barcode == barkod)
               .with_entities(Product.images).first())
        ham = ((row[0] if row else "") or "").split(",")[0]
    except Exception:
        logger.warning("[URETIM] whatsapp görseli okunamadı", exc_info=True)
        db.session.rollback()
        ham = ""
    adres = _wa_gorsel_adresi(ham)
    if adres:
        return adres
    for uzanti in (".jpg", ".jpeg", ".png"):
        if os.path.exists(os.path.join("static", "images", f"{barkod}{uzanti}")):
            return _wa_gorsel_adresi(f"/static/images/{barkod}{uzanti}")
    logger.info(f"[URETIM] whatsapp görseli bulunamadı (barkod {barkod}, kayıtlı değer: {ham.strip()[:80]!r})")
    return None


def _wa_personel_bildirimi(olay: str, order_number: str, model_kodlari: str,
                           eslesen: list[dict]) -> None:
    """Çalışan WhatsApp bildirimi (whatsapp_notify hattı, olay şablonlarıyla).
    Alıcılar /whatsapp-duyuru'daki dağılımdan gelir. uretim_siparisi şablonu
    görsel ZORUNLU tuttuğu için görseli olmayan üründe genel şablon kullanılır."""
    from whatsapp_alici import alicilar
    from whatsapp_notify import notify_staff_async, notify_staff_template_async

    kime = alicilar(olay)
    if not kime:
        return
    urun, adet = _wa_urun_ozeti(eslesen)
    params = [order_number, urun, adet]
    detay = f"Sipariş: {order_number} | Model: {model_kodlari or '-'} | Ürün: {urun} | Adet: {adet}"
    if olay == "uretim_iptal":
        notify_staff_template_async("uretim_iptal", params,
                                    fallback=("Üretim siparişi İPTAL", detay),
                                    only_last4=kime)
        return
    gorsel = _wa_urun_gorseli(eslesen)
    if gorsel:
        notify_staff_template_async("uretim_siparisi", params, image_url=gorsel,
                                    fallback=("Yeni üretim siparişi", detay),
                                    only_last4=kime)
    else:
        logger.info(f"[URETIM] {order_number}: görsel yok, WhatsApp bildirimi genel şablonla gidiyor")
        notify_staff_async("Yeni üretim siparişi", detay, only_last4=kime)


def _mail_govdesi(order_number: str, musteri: str, model_kodlari: str,
                  eslesen: list[dict]) -> str:
    from mail_service import build_alert_email_html
    urun_satirlari = _urun_satirlari_html(eslesen)
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


def isle_iptal_bildirimleri() -> int:
    """Üretim bekleyen/işlemdeki sipariş pazaryerinde iptal edildiyse
    (OrderCancelled'a düştüyse) 'uretim_iptal' abonelerine mail atar —
    üretici boşuna üretmesin. iptal_mail_at ile tek sefer (dedupe).
    Sipariş sync'i sonrası çağrılır; her hata yutulur, akış durmaz.
    Dönüş: mail atılan kayıt sayısı."""
    try:
        from models import OrderCancelled
        adaylar = (UretimSiparis.query
                   .filter_by(uretildi=False)
                   .filter(UretimSiparis.iptal_mail_at.is_(None))
                   .all())
        if not adaylar:
            return 0
        nolar = [k.order_number for k in adaylar]
        iptaller = {o.order_number for o in
                    OrderCancelled.query
                    .filter(OrderCancelled.order_number.in_(nolar))
                    .with_entities(OrderCancelled.order_number)}
        if not iptaller:
            return 0
        from mail_service import notify, build_alert_email_html
        sayi = 0
        for kayit in adaylar:
            if kayit.order_number not in iptaller:
                continue
            try:
                try:
                    eslesen = json.loads(kayit.details) if kayit.details else []
                except (json.JSONDecodeError, TypeError):
                    eslesen = []
                govde = build_alert_email_html(
                    'uretim_iptal',
                    headline=f"{kayit.order_number} numaralı üretim siparişi pazaryerinde İPTAL edildi.",
                    summary_rows=[
                        ("Sipariş No", kayit.order_number),
                        ("Müşteri", kayit.customer_name or "-"),
                        ("Model", kayit.product_main_id or "-"),
                        ("Ürünler", _urun_satirlari_html(eslesen) or "-"),
                    ],
                    action_hint=("Bu siparişin üretimini DURDURUN. Sipariş üretim sayfasından "
                                 "kaldırıldı; iptal edilen siparişler sayfasında görülebilir."),
                )
                notify('uretim_iptal',
                       subject=f"🛑 Üretim siparişi İPTAL — {kayit.order_number} ({kayit.product_main_id})",
                       body=govde)
                # WhatsApp bildirimi (mail'in ikizi, aynı abonelik olayı ve
                # aynı iptal_mail_at dedupe'u). Config yoksa sessizce atlanır.
                try:
                    from whatsapp_service import notify_whatsapp
                    notify_whatsapp('uretim_iptal',
                                    f"🛑 Üretim siparişi İPTAL — {kayit.order_number}",
                                    f"Model: {kayit.product_main_id or '-'} | "
                                    f"Müşteri: {kayit.customer_name or '-'} | Üretimi DURDURUN.")
                except Exception:
                    logger.exception("[URETIM] whatsapp iptal bildirimi hatası (yutuldu)")
                try:
                    _wa_personel_bildirimi("uretim_iptal", kayit.order_number,
                                           kayit.product_main_id or "", eslesen)
                except Exception:
                    logger.exception("[URETIM] whatsapp personel iptal bildirimi hatası (yutuldu)")
                kayit.iptal_mail_at = datetime.utcnow()
                db.session.commit()
                sayi += 1
                logger.info(f"[URETIM] 🛑 İptal bildirimi gönderildi: {kayit.order_number}")
            except Exception:
                db.session.rollback()
                logger.exception(f"[URETIM] iptal bildirimi hatası (yutuldu): {kayit.order_number}")
        return sayi
    except Exception:
        db.session.rollback()
        logger.warning("[URETIM] isle_iptal_bildirimleri hatası (yutuldu)", exc_info=True)
        return 0


def isle_shopify_siparisler() -> int:
    """
    Web sitesi (Shopify) siparişlerinde üretim modundaki modelleri yakalar.
    Trendyol'un aksine site siparişleri panele tablo olarak inmez (siparis_hazirla
    canlı çeker), dolayısıyla order_service'teki üretim yakalama onları hiç
    görmüyordu → site siparişinde mail gitmiyordu. Bu fonksiyon beklemedeki site
    siparişlerini API'den çekip isle_yeni_siparisler'e verir — kayıt + mail +
    raf önceliği + resync dedupe'u aynı akıştan gelir. app.py'de zamanlanmış
    job olarak koşar; her hata yutulur, 0 döner (akış durmaz).
    """
    try:
        if not get_uretim_barcodes():
            return 0
        from siparis_hazirla import (_fetch_shopify_beklemede_orders,
                                     _shopify_order_to_hazirla_format)
        order_dicts = []
        for raw in _fetch_shopify_beklemede_orders(limit=20):
            raw["line_items"] = raw.get("line_items") or []
            fake, _ = _shopify_order_to_hazirla_format(raw)
            order_date = fake.order_date
            if order_date is not None and order_date.tzinfo is not None:
                # Kolon naive-UTC saklar (| ist ile gösterim) — tz düşürülür.
                from datetime import timezone
                order_date = order_date.astimezone(timezone.utc).replace(tzinfo=None)
            order_dicts.append({
                'order_number': fake.order_number,
                'package_number': None,
                'customer_name': fake.customer_name,
                'customer_surname': fake.customer_surname,
                'order_date': order_date,
                'details': fake.details,
            })
        return isle_yeni_siparisler(order_dicts)
    except Exception:
        db.session.rollback()
        logger.warning("[URETIM] isle_shopify_siparisler hatası (yutuldu)", exc_info=True)
        return 0


def isle_sahipsiz_siparisler() -> int:
    """
    Sahipsiz sipariş taraması: 'Yeni' statüsündeki, üretim modunda barkodu olan
    ve üretim kaydı açılmamış siparişleri isle_yeni_siparisler'den YENİDEN
    geçirir. Yakalama tek seferlik olduğu için, indiği an rafta görünen adet
    sonradan başka siparişe gidince sipariş ne rafta ne üretimde kalıyordu.
    Rafı hâlâ karşılanan sipariş yine yazılmaz; kayıt + mail + dedupe aynı
    akıştan gelir. Her hata yutulur, 0 döner (akış durmaz).
    """
    try:
        barkod_seti = get_uretim_barcodes()
        if not barkod_seti:
            return 0
        from barcode_alias_helper import normalize_barcode
        from models import OrderCreated
        from stock_ledger import has_movement
        rows = (OrderCreated.query
                .with_entities(OrderCreated.order_number, OrderCreated.package_number,
                               OrderCreated.customer_name, OrderCreated.customer_surname,
                               OrderCreated.order_date, OrderCreated.details)
                .order_by(OrderCreated.order_date.asc().nullslast())
                .all())
        adaylar = []
        for r in rows:
            try:
                det = json.loads(r.details) if isinstance(r.details, str) else r.details
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(det, list):
                continue
            order_number = str(r.order_number or '').strip()
            # Rafı zaten okutulmuş kalem raftan düşülmüştür — üretime yazılmaz.
            kalan = [item for item in det
                     if not has_movement(pick_key(
                         order_number,
                         normalize_barcode(str(item.get('barcode', '') or '').strip())))]
            if any(normalize_barcode(str(item.get('barcode', '') or '').strip()) in barkod_seti
                   for item in kalan):
                adaylar.append({
                    'order_number': order_number,
                    'package_number': r.package_number,
                    'customer_name': r.customer_name,
                    'customer_surname': r.customer_surname,
                    'order_date': r.order_date,
                    'details': kalan,
                })
        if not adaylar:
            return 0
        kayitli = {k.order_number for k in
                   UretimSiparis.query
                   .filter(UretimSiparis.order_number.in_([a['order_number'] for a in adaylar]))
                   .with_entities(UretimSiparis.order_number)
                   .all()}
        return isle_yeni_siparisler([a for a in adaylar
                                     if a['order_number'] not in kayitli])
    except Exception:
        db.session.rollback()
        logger.warning("[URETIM] isle_sahipsiz_siparisler hatası (yutuldu)", exc_info=True)
        return 0


def isle_yeni_siparisler(new_order_dicts: list[dict]) -> int:
    """
    Yeni gelen Trendyol siparişlerinde üretim modundaki modelleri yakalar:
    uretim_siparis kaydı açar + 'uretim_siparis' olayına abone kullanıcılara
    mail atar. Sipariş commit'inden SONRA çağrılmalıdır (kendi commit'ini
    yapar). Dönüş: eklenen kayıt sayısı.
    """
    try:
        barkod_seti = get_uretim_barcodes()
        if not barkod_seti or not new_order_dicts:
            return 0
        from barcode_alias_helper import normalize_barcode
        talepler = _acik_raf_talepleri(barkod_seti)
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
                # 📦 Raf önceliği: barkodun rafta yeterli stoğu varsa o kalem
                # üretime YAZILMAZ — sipariş normal akışta raftan toplanır.
                # Yalnız raf stoğu yetmeyen kalemler üretim kaydına girer.
                raf_stok = _raf_stok_haritasi([u['barcode'] for u in eslesen])
                # Rezerv: raftaki adet önce eski siparişlerin hakkı — onların
                # talebi düşülür, yoksa aynı tek adede birden çok sipariş yaslanır.
                rezerv = _oncelikli_rezerv(talepler, order_number,
                                           order_dict.get('order_date'))
                raf_stok = {bc: max(0, adet - rezerv.get(bc, 0))
                            for bc, adet in raf_stok.items()}
                rafta_karsilanan = [u for u in eslesen
                                    if raf_stok.get(u['barcode'], 0) >= u['quantity']]
                if rafta_karsilanan:
                    eslesen = [u for u in eslesen
                               if raf_stok.get(u['barcode'], 0) < u['quantity']]
                    logger.info(
                        f"[URETIM] 📦 {order_number}: raf önceliği — "
                        + ", ".join(f"{u['barcode']} (rafta {raf_stok.get(u['barcode'], 0)})"
                                    for u in rafta_karsilanan)
                        + " rafta mevcut, üretime yazılmadı"
                    )
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
                # Üretime yazılan kalem artık raf talebi değil — sonraki siparişe rezerv sayılmasın.
                yazilan = {u['barcode'] for u in eslesen}
                talepler = [t for t in talepler
                            if not (t['order_number'] == order_number
                                    and t['barcode'] in yazilan)]

                # Abonelik bazlı bildirim (kullanıcı yönetimi → Bildirimler).
                # notify fire-and-forget; işaret dedupe içindir (desen: stok_yok_mail_at).
                try:
                    from mail_service import notify
                    notify('uretim_siparis',
                           subject=f"🏭 Üretim siparişi — {order_number} ({model_kodlari})",
                           body=_mail_govdesi(order_number, musteri, model_kodlari, eslesen))
                    kayit.mail_sent_at = datetime.utcnow()
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    logger.exception("[URETIM] mail bildirimi hatası (yutuldu)")
                # WhatsApp bildirimi (mail'in ikizi, aynı abonelik olayı).
                # Config yoksa notify_whatsapp sessizce hiçbir şey yapmaz.
                try:
                    from whatsapp_service import notify_whatsapp
                    notify_whatsapp('uretim_siparis',
                                    f"🏭 Üretim siparişi — {order_number}",
                                    f"Model: {model_kodlari or '-'} | Müşteri: {musteri or '-'} | "
                                    f"Üretimi planlayın; detay /uretim sayfasında.")
                except Exception:
                    logger.exception("[URETIM] whatsapp bildirimi hatası (yutuldu)")
                try:
                    _wa_personel_bildirimi("uretim_siparis", order_number,
                                           model_kodlari, eslesen)
                except Exception:
                    logger.exception("[URETIM] whatsapp personel bildirimi hatası (yutuldu)")
            except Exception:
                db.session.rollback()
                logger.exception(f"[URETIM] sipariş işlenemedi (yutuldu): {order_dict.get('order_number')}")
        return eklenen
    except Exception:
        db.session.rollback()
        logger.exception("[URETIM] isle_yeni_siparisler hatası (yutuldu)")
        return 0
