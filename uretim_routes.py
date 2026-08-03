# uretim_routes.py
"""
Üretim Modu sayfası + JSON API'leri.

Tüm route'lar /uretim altında — app.py'deki check_authentication kalkanı
kapsamındadır (login zorunlu; /api/ öneki bilinçli olarak KULLANILMADI çünkü
o önek auth'tan muaf). Güvenlik kalkanı deseni: trendyol_qna/qna_routes.py.
"""
import json
import logging
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, session

from models import db, UretimSiparis

logger = logging.getLogger(__name__)

uretim_bp = Blueprint("uretim", __name__, url_prefix="/uretim")


@uretim_bp.before_request
def _guvenlik_kalkani():
    """
    1) 2FA kalkanı (derinlemesine savunma): app-level check_authentication
       zaten yönlendiriyor; global kalkanda gedik açılsa bile bu blueprint
       2FA doğrulanmadan çalışmaz.
    2) Hafif CSRF koruması: state değiştiren istekler yalnızca fetch'in
       ekleyebildiği özel başlıkla kabul edilir.
    """
    from flask import abort
    from flask_login import current_user
    try:
        dogrulanmis = current_user.is_authenticated and session.get("totp_verified")
    except Exception:
        dogrulanmis = False
    if not dogrulanmis:
        abort(403)
    if request.method == "POST" and request.headers.get("X-Requested-With") != "fetch":
        abort(403)


def _to_dict(r: UretimSiparis, urun_map: dict | None = None) -> dict:
    from time_utils import fmt_ist
    try:
        detaylar = json.loads(r.details) if r.details else []
    except (json.JSONDecodeError, TypeError):
        detaylar = []
    # Ürün özellikleri: barkod → görsel/başlık (sipariş listesindeki detay paneliyle aynı veri)
    if urun_map:
        for d in detaylar:
            p = urun_map.get(str(d.get("barcode") or ""))
            if p is not None:
                d["image_url"] = (p.images or "").split(",")[0].strip() if p.images else ""
                d["title"] = p.title or ""
                d["model_code"] = p.product_main_id or ""
    return {
        "id": r.id,
        "order_number": r.order_number,
        "package_number": r.package_number,
        "product_main_id": r.product_main_id,
        "details": detaylar,
        "customer_name": r.customer_name,
        "order_date": fmt_ist(r.order_date, "%d.%m.%Y %H:%M"),
        "uretildi": r.uretildi,
        "uretildi_at": fmt_ist(r.uretildi_at, "%d.%m.%Y %H:%M"),
        "isleme_alindi": bool(getattr(r, "isleme_alindi", False)),
        "isleme_alindi_at": fmt_ist(r.isleme_alindi_at, "%d.%m.%Y %H:%M"),
        "mail_sent": bool(r.mail_sent_at),
        "created_at": fmt_ist(r.created_at, "%d.%m.%Y %H:%M"),
    }


@uretim_bp.route("/", methods=["GET"])
def index():
    return render_template("uretim.html")


@uretim_bp.route("/api/liste", methods=["GET"])
def liste():
    durum = (request.args.get("durum") or "bekleyen").strip()
    q = UretimSiparis.query
    if durum in ("uretildi", "tamamlanan"):
        q = q.filter_by(uretildi=True)
    elif durum == "islemde":
        q = q.filter_by(uretildi=False, isleme_alindi=True)
    else:  # bekleyen
        q = q.filter_by(uretildi=False, isleme_alindi=False)
    # Sıralama sipariş tarihine göre: aktif kuyruklarda en eski üstte (FIFO),
    # tamamlananlarda en yeni üstte. order_date boşsa sona düşer.
    if durum == "tamamlanan":
        siralama = UretimSiparis.order_date.desc().nullslast()
    else:
        siralama = UretimSiparis.order_date.asc().nullslast()
    rows = (q.order_by(siralama, UretimSiparis.created_at.desc())
            .limit(500)
            .all())
    # Tamamlanan = üretildi + kargoya verildi (Shipped/Delivered/Arşiv'de canlı
    # kontrol — ayrı kolon yok, sipariş kargolanınca kendiliğinden taşınır).
    # Hata → boş set: tamamlanan boş kalır, üretilenler eski davranışla tümünü gösterir.
    if durum in ("uretildi", "tamamlanan") and rows:
        kargolanan = set()
        try:
            from models import OrderShipped, OrderDelivered, OrderArchived
            nolar = [r.order_number for r in rows]
            for M in (OrderShipped, OrderDelivered, OrderArchived):
                kargolanan |= {o.order_number for o in
                               M.query.filter(M.order_number.in_(nolar))
                               .with_entities(M.order_number)}
        except Exception:
            db.session.rollback()
            logger.warning("[URETIM] kargolanan kontrolü yapılamadı", exc_info=True)
        rows = [r for r in rows
                if (r.order_number in kargolanan) == (durum == "tamamlanan")]
    # Pazaryerinde iptal edilen sipariş üretim sayfasında GÖSTERİLMEZ (kafa
    # karışıklığı olmasın) — kayıt silinmez (iz kalır), sipariş normal iptal
    # sayfasında görünür; aboneler 'uretim_iptal' mailiyle haberdar edilir.
    iptaller = set()
    if rows:
        try:
            from models import OrderCancelled
            nolar = [r.order_number for r in rows]
            iptaller = {o.order_number for o in
                        OrderCancelled.query
                        .filter(OrderCancelled.order_number.in_(nolar))
                        .with_entities(OrderCancelled.order_number)}
        except Exception:
            db.session.rollback()
            logger.warning("[URETIM] iptal kontrolü yapılamadı", exc_info=True)
        rows = [r for r in rows if r.order_number not in iptaller]
    # Kargo çıktısı + TAM sipariş içeriği için canlı sipariş verisi —
    # cargo_tracking_number sipariş daha Yeni'yken Trendyol'dan gelir, statü şartı yok.
    # Karma siparişlerde (üretim + raftan kalemler birlikte) paketlemede eksik
    # ürün kalmasın diye siparişin TÜM kalemleri de buradan okunur (detay_map).
    from barcode_alias_helper import normalize_barcode
    kargo_map = {}
    detay_map = {}  # order_number → siparişin tam kalem listesi (ham details)
    if rows:
        try:
            from models import (OrderCreated, OrderHazirlaniyor, OrderPicking,
                                OrderShipped, OrderDelivered, OrderArchived)
            nolar = [r.order_number for r in rows]
            for M in (OrderCreated, OrderHazirlaniyor, OrderPicking,
                      OrderShipped, OrderDelivered, OrderArchived):
                # with_entities: tam entity ÇEKME — prod'da orders_archived'ın
                # kolon adları model ile birebir değil (stockCode/stockcode),
                # tam select UndefinedColumn ile patlıyor. Gereken kolonlar yeter.
                satirlar = (M.query.filter(M.order_number.in_(nolar))
                            .with_entities(M.order_number, M.cargo_tracking_number,
                                           M.cargo_provider_name, M.customer_name,
                                           M.customer_surname, M.customer_address,
                                           M.details)
                            .all())
                for o in satirlar:
                    kargo_map.setdefault(o.order_number, {
                        "shipping_barcode": o.cargo_tracking_number or "",
                        "cargo_provider": o.cargo_provider_name or "",
                        "customer_name": o.customer_name or "",
                        "customer_surname": o.customer_surname or "",
                        "customer_address": o.customer_address or "",
                    })
                    if o.order_number not in detay_map and o.details:
                        try:
                            det = json.loads(o.details) if isinstance(o.details, str) else o.details
                            if isinstance(det, list) and det:
                                detay_map[o.order_number] = det
                        except (json.JSONDecodeError, TypeError):
                            pass
        except Exception:
            db.session.rollback()
            logger.warning("[URETIM] kargo/sipariş içeriği okunamadı", exc_info=True)
    # Ürün özellikleri için Product haritası (görsel/başlık/model) — tek sorgu
    urun_map = {}
    if rows:
        try:
            from models import Product
            barkodlar = set()
            for r in rows:
                try:
                    det = json.loads(r.details) if r.details else []
                except (json.JSONDecodeError, TypeError):
                    det = []
                for d in det:
                    bc = str(d.get("barcode") or "").strip()
                    if bc:
                        barkodlar.add(bc)
            for det in detay_map.values():
                for item in det:
                    bc = normalize_barcode(str(item.get("barcode", "") or "").strip())
                    if bc:
                        barkodlar.add(bc)
            if barkodlar:
                urun_map = {p.barcode: p for p in Product.query.filter(Product.barcode.in_(barkodlar))}
        except Exception:
            db.session.rollback()
            logger.warning("[URETIM] ürün özellikleri okunamadı", exc_info=True)
    # Raftan toplanacak kalemler için raf bilgisi (adet>0, çoktan aza)
    raf_map = {}
    if detay_map:
        try:
            from models import RafUrun
            bcs = {normalize_barcode(str(item.get("barcode", "") or "").strip())
                   for det in detay_map.values() for item in det}
            bcs.discard("")
            if bcs:
                for ru in (RafUrun.query
                           .filter(RafUrun.urun_barkodu.in_(bcs), RafUrun.adet > 0)
                           .order_by(RafUrun.adet.desc())):
                    raf_map.setdefault(ru.urun_barkodu, []).append(f"{ru.raf_kodu} ({ru.adet})")
        except Exception:
            db.session.rollback()
            logger.warning("[URETIM] raf bilgisi okunamadı", exc_info=True)
    # Raf okutma durumu: hangi kalemler okutulmuş (ledger pick anahtarı) — tek sorgu
    okutulan_keys = set()
    if detay_map:
        try:
            from models import StockMovement
            from uretim_modu import pick_key
            keys = []
            for r in rows:
                for item in (detay_map.get(r.order_number) or []):
                    bc = normalize_barcode(str(item.get("barcode", "") or "").strip())
                    if bc:
                        keys.append(pick_key(r.order_number, bc))
            if keys:
                okutulan_keys = {k for (k,) in
                                 db.session.query(StockMovement.idempotency_key)
                                 .filter(StockMovement.idempotency_key.in_(keys))}
        except Exception:
            db.session.rollback()
            logger.warning("[URETIM] raf okutma durumu okunamadı", exc_info=True)
    sonuc = []
    for r in rows:
        d = _to_dict(r, urun_map)
        d["iptal"] = r.order_number in iptaller
        d["kargo"] = kargo_map.get(r.order_number)
        # Siparişin tam içeriği: her kalem üretilecek mi, raftan mı (raf kodlarıyla)
        tam = detay_map.get(r.order_number)
        if tam:
            from uretim_modu import pick_key
            uretim_bcs = {str(k.get("barcode") or "") for k in d["details"]}
            kalemler = []
            for item in tam:
                bc = normalize_barcode(str(item.get("barcode", "") or "").strip())
                p = urun_map.get(bc)
                kalemler.append({
                    "barcode": bc,
                    "sku": item.get("sku") or "",
                    "color": item.get("color") or "",
                    "size": item.get("size") or "",
                    "quantity": int(item.get("quantity", 1) or 1),
                    "uretim": bc in uretim_bcs,
                    "raflar": raf_map.get(bc, []),
                    "toplandi": pick_key(r.order_number, bc) in okutulan_keys,
                    "image_url": ((p.images or "").split(",")[0].strip() if (p and p.images) else ""),
                    "title": (p.title or "") if p else "",
                    "model_code": (p.product_main_id or "") if p else "",
                })
            d["siparis_detay"] = kalemler
            # Etiket kilidi: tüm RAFTAN kalemler okutulmuş mu?
            d["raf_tamam"] = all(k["toplandi"] for k in kalemler if not k["uretim"])
        else:
            d["raf_tamam"] = True  # içerik bilinmiyorsa kilitleme (eski kayıt)
        sonuc.append(d)
    return jsonify({"success": True, "rows": sonuc})


@uretim_bp.route("/api/uretildi/<int:kayit_id>", methods=["POST"])
def uretildi_isaretle(kayit_id: int):
    kayit = db.session.get(UretimSiparis, kayit_id)
    if not kayit:
        return jsonify({"success": False, "message": "Kayıt bulunamadı"}), 404
    geri_al = bool((request.get_json(silent=True) or {}).get("geri_al"))
    kayit.uretildi = not geri_al
    kayit.uretildi_at = None if geri_al else datetime.utcnow()
    db.session.commit()
    mesaj = "Üretildi işareti geri alındı" if geri_al else "Üretildi olarak işaretlendi — sipariş normal akışına devam edecek"
    logger.info(f"[URETIM] {kayit.order_number}: {mesaj}")
    return jsonify({"success": True, "message": mesaj})


@uretim_bp.route("/api/isleme-al/<int:kayit_id>", methods=["POST"])
def isleme_al(kayit_id: int):
    kayit = db.session.get(UretimSiparis, kayit_id)
    if not kayit:
        return jsonify({"success": False, "message": "Kayıt bulunamadı"}), 404
    geri_al = bool((request.get_json(silent=True) or {}).get("geri_al"))
    kayit.isleme_alindi = not geri_al
    kayit.isleme_alindi_at = None if geri_al else datetime.utcnow()
    db.session.commit()
    mesaj = "Bekleyenlere geri alındı" if geri_al else "İşleme alındı — üretim başladı"
    logger.info(f"[URETIM] {kayit.order_number}: {mesaj}")
    return jsonify({"success": True, "message": mesaj})


@uretim_bp.route("/api/raf-okut/<int:kayit_id>", methods=["POST"])
def raf_okut(kayit_id: int):
    """Karma siparişin RAFTAN kalemini üretim ekranından okut: okutulan raftan
    fiziksel düşüm + pack_out ledger (picking_service ile aynı idempotency
    anahtarı → sipariş hazırla ile çift düşüm imkânsız). Tüm raf kalemleri
    okutulunca sipariş 'toplandı' damgalanır."""
    from barcode_alias_helper import normalize_barcode
    from picking_service import _norm_raf
    from stock_ledger import record_movement, has_movement, REASON_PACK_OUT
    from stock_management import sync_central_stock
    from uretim_modu import raftan_kalemler, pick_key
    from models import RafUrun

    kayit = db.session.get(UretimSiparis, kayit_id)
    if not kayit:
        return jsonify({"success": False, "message": "Kayıt bulunamadı"}), 404
    data = request.get_json(silent=True) or {}
    bc = normalize_barcode(str(data.get("barcode") or "").strip())
    raf_kodu = str(data.get("raf_kodu") or "").strip()
    if not bc or not raf_kodu:
        return jsonify({"success": False, "message": "Ürün barkodu ve raf kodu gerekli."}), 400

    kalemler = raftan_kalemler(kayit)
    kalem = next((k for k in kalemler if k["barcode"] == bc), None)
    if kalem is None:
        return jsonify({"success": False,
                        "message": "Okutulan ürün bu siparişin raftan toplanacak kalemlerinden değil."}), 400

    key = pick_key(kayit.order_number, bc)
    if not has_movement(key):
        qty = kalem["quantity"]
        raf_hedef = _norm_raf(raf_kodu)
        rec = next(
            (r for r in (RafUrun.query
                         .filter(RafUrun.urun_barkodu == bc, RafUrun.adet > 0)
                         .with_for_update()
                         .all())
             if _norm_raf(r.raf_kodu) == raf_hedef),
            None,
        )
        if not rec or (rec.adet or 0) < qty:
            mevcut = (rec.adet or 0) if rec else 0
            db.session.rollback()
            return jsonify({"success": False,
                            "message": f"{raf_kodu} rafında {bc} ürününden yeterli yok (var: {mevcut}, gerekli: {qty})."}), 400
        try:
            rec.adet = (rec.adet or 0) - qty
            db.session.flush()
            record_movement(
                barcode=bc, delta=-qty, reason=REASON_PACK_OUT, shelf_code=rec.raf_kodu,
                order_number=kayit.order_number, idempotency_key=key,
                source="USER", note="uretim ekranı raf okutma",
                mutate_shelf=False, commit=False,
            )
            sync_central_stock(bc, commit=False)
            db.session.commit()
            logger.info(f"[URETIM] 📦 {kayit.order_number} · {rec.raf_kodu} rafından {bc} × {qty} okutuldu/düşüldü")
        except Exception:
            db.session.rollback()
            logger.exception("[URETIM] raf okutma düşümü hatası")
            return jsonify({"success": False, "message": "Düşüm sırasında hata oluştu."}), 500

    kalan = [k["barcode"] for k in kalemler
             if not has_movement(pick_key(kayit.order_number, k["barcode"]))]
    raf_tamam = not kalan
    # Tümü okutulduysa 'toplandı' damgası — sipariş hazırla ekranı aynı siparişi
    # ikinci kez okutup düşmesin (picking_service idempotency'si damgaya bakar).
    if raf_tamam:
        try:
            from models import OrderCreated, OrderHazirlaniyor, OrderPicking
            for M in (OrderCreated, OrderHazirlaniyor, OrderPicking):
                o = M.query.filter_by(order_number=kayit.order_number).first()
                if o:
                    if not getattr(o, "toplandi_at", None):
                        o.toplandi_at = datetime.utcnow()
                        o.toplandi_raf = raf_kodu
                        db.session.commit()
                    break
        except Exception:
            db.session.rollback()
            logger.warning("[URETIM] toplandı damgası yazılamadı", exc_info=True)
    mesaj = ("Tüm raf ürünleri okutuldu — etiket alınabilir." if raf_tamam
             else f"Okutuldu. Kalan raf ürünü: {len(kalan)}")
    return jsonify({"success": True, "raf_tamam": raf_tamam, "kalan": kalan, "message": mesaj})


@uretim_bp.route("/api/ayar", methods=["GET"])
def ayar():
    # Mail alıcıları kullanıcı yönetiminden ('uretim_siparis' bildirimi) yönetilir;
    # burada yalnız model listesi döner.
    from uretim_modu import get_uretim_ayar
    return jsonify({"success": True, "ayar": get_uretim_ayar()})


@uretim_bp.route("/api/model-toggle", methods=["POST"])
def model_toggle():
    from uretim_modu import toggle_model, URETIM_SABIT_ADET
    data = request.get_json(silent=True) or {}
    model_id = str(data.get("model") or "").strip()
    if not model_id:
        return jsonify({"success": False, "message": "Model kodu boş"}), 400
    try:
        acik = toggle_model(model_id)
    except Exception:
        db.session.rollback()
        logger.exception("[URETIM] model toggle hatası")
        return jsonify({"success": False, "message": "Kaydedilemedi"}), 500
    mesaj = (f"{model_id} üretim moduna ALINDI — Trendyol'a sabit {URETIM_SABIT_ADET} stok gidecek"
             if acik else f"{model_id} üretim modundan çıkarıldı — ilk senkronla gerçek stok gider")
    logger.info(f"[URETIM] {mesaj}")
    return jsonify({"success": True, "acik": acik, "message": mesaj})
