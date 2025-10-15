import json, time, hashlib
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from flask import Blueprint, Response, jsonify, request, stream_with_context, render_template, redirect, url_for
from sqlalchemy import func, literal, text, and_, or_
from models import db, Product, CentralStock
from models import OrderCreated, OrderPicking, OrderShipped, Archive, ReturnOrder, ReturnProduct
try:
    from models import OrderDelivered
except ImportError:
    from models import orders_delivered as OrderDelivered

import logging, traceback, time as _pytime
from flask import current_app
from datetime import timezone  # <-- eklendi




canli_panel_bp = Blueprint("canli_panel", __name__)

# ── Ayarlar
IST = ZoneInfo("Europe/Istanbul")
DUSUK_STOK_ESIK = 5
AKIS_ARALIGI_SANIYE = 300
PING_INTERVAL = 10
IADE_UYARI_ORAN = 0.25

# ▼▼ BUNU EKLE ▼▼
ASSUME_DB_UTC = True  # Naive timestamp'lar UTC kabul edilip IST'ye çevrilsin
# ▲▲ BUNU EKLE ▲▲


logger = logging.getLogger("canli_panel")
if not logger.handlers:
    h = logging.StreamHandler()
    fmt = logging.Formatter('%(asctime)s - %(levelname)s - [canli_panel] %(message)s')
    h.setFormatter(fmt)
    logger.addHandler(h)
logger.setLevel(logging.INFO)

def _t0(): return _pytime.perf_counter()
def _dt_ms(t): return int((_pytime.perf_counter()-t)*1000)
def _info(msg, **kw): 
    try: logger.info(msg + (" | " + ", ".join(f"{k}={v}" for k,v in kw.items()) if kw else ""))
    except Exception: logger.info(msg)

def _exc(msg):
    logger.error(msg + "\n" + traceback.format_exc())


    
def _to_ist_aware(dt):
    """dt -> Europe/Istanbul (tz-aware). Naive ise ASSUME_DB_UTC'ye göre tz eklenir."""
    if dt is None:
        return None
    if not isinstance(dt, datetime):
        return None
    # tz yoksa ekle
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt = dt.replace(tzinfo=(timezone.utc if ASSUME_DB_UTC else IST))
    # IST'ye çevir
    return dt.astimezone(IST)
    

def _collect_returns_by_order_created_between(start_ist: datetime, end_ist: datetime):
    """
    Sadece seçilen aralıkta OLUŞTURULAN siparişlere ait iadeleri toplar.
    Döner: {barcode: toplam_iade_adedi}
    """
    ret_qty = {}
    # 1) Aralıkta oluşturulan sipariş numaralarını al
    ord_nos = _order_numbers_created_between(start_ist, end_ist)
    if not ord_nos:
        _info("returns(by order-created): no orders in range"); 
        return ret_qty

    # 2) Sadece bu order_number’lara ait iade satırlarını grupla
    rows = (db.session.query(ReturnProduct.barcode,
                             func.coalesce(func.sum(ReturnProduct.quantity), 0))
            .join(ReturnOrder, ReturnProduct.return_order_id == ReturnOrder.id)
            .filter(ReturnOrder.order_number.in_(list(ord_nos)))
            .group_by(ReturnProduct.barcode)
            .all())
    for bc, q in rows:
        if bc and q:
            ret_qty[str(bc).strip()] = int(q or 0)

    _info("returns(by order-created): done", orders=len(ord_nos), uniq=len(ret_qty), rows=len(rows))
    return ret_qty




def _parse_yyyy_mm_dd(s: str):
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except Exception:
        return None

def _tr_range_from_params(args):
    t0=_t0()
    try:
        preset = (args.get("preset") or "").lower().strip()
        s = _parse_yyyy_mm_dd(args.get("start") or "")
        e = _parse_yyyy_mm_dd(args.get("end") or "")

        now = datetime.now(IST)
        today = now.date()

        if s and e:
            start = datetime.combine(s, datetime.min.time(), IST)
            end   = datetime.combine(e + timedelta(days=1), datetime.min.time(), IST)
            _info("range from params (custom)", preset=preset, start=str(start), end=str(end), ms=_dt_ms(t0))
            return start, end

        if preset in ("today", ""):
            start = datetime.combine(today, datetime.min.time(), IST); end = start + timedelta(days=1)
        elif preset == "yesterday":
            start = datetime.combine(today - timedelta(days=1), datetime.min.time(), IST); end = start + timedelta(days=1)
        elif preset == "this_week":
            week_start = today - timedelta(days=today.weekday())
            start = datetime.combine(week_start, datetime.min.time(), IST); end = start + timedelta(days=7)
        elif preset == "last_7d":
            start = datetime.combine(today - timedelta(days=6), datetime.min.time(), IST)
            end   = datetime.combine(today + timedelta(days=1), datetime.min.time(), IST)
        elif preset == "this_month":
            first = today.replace(day=1); start = datetime.combine(first, datetime.min.time(), IST)
            next_first = date(first.year + 1, 1, 1) if first.month==12 else date(first.year, first.month+1, 1)
            end = datetime.combine(next_first, datetime.min.time(), IST)
        elif preset == "last_30d":
            start = datetime.combine(today - timedelta(days=29), datetime.min.time(), IST)
            end   = datetime.combine(today + timedelta(days=1), datetime.min.time(), IST)
        else:
            start = datetime.combine(today, datetime.min.time(), IST); end = start + timedelta(days=1)

        _info("range from params", preset=preset or "today", start=str(start), end=str(end), ms=_dt_ms(t0))
        return start, end
    except Exception:
        _exc("range parse failed")
        # güvenli fallback
        start = datetime.combine(datetime.now(IST).date(), datetime.min.time(), IST)
        return start, start + timedelta(days=1)


def _count_orders_between_distinct(start_ist, end_ist):
    sources = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered]
    ids = set()
    for cls in sources:
        ts_col, _, _ = _col(cls, ORD_TS_CANDS, "ts")
        det_name = next((n for n in ORD_DTL_CANDS if hasattr(cls, n)), None)
        if ts_col is None: continue
        q = db.session.query(cls).filter(
            or_(
                and_(func.timezone('Europe/Istanbul', ts_col) >= start_ist,
                     func.timezone('Europe/Istanbul', ts_col) <  end_ist),
                and_(ts_col >= start_ist, ts_col < end_ist)
            )
        )
        for row in q.all():
            payload = getattr(row, det_name) if (det_name and hasattr(row, det_name)) else None
            oid = _extract_order_id_from_row_or_payload(row, payload) or _content_signature([], cls.__name__, getattr(row,"id",None))
            ids.add(str(oid))
    return len(ids)


def _order_numbers_created_between(start_ist: datetime, end_ist: datetime) -> set[str]:
    """
    Created/Picking/Shipped/Delivered/Archive tablolarında
    Europe/Istanbul aralığı [start,end) için order_number seti döner.
    """
    order_nos = set()
    sources = [("Created", OrderCreated),
               ("Picking", OrderPicking),
               ("Shipped", OrderShipped),
               ("Delivered", OrderDelivered),
               ("Archive",  Archive)]
    for name, cls in sources:
        # order_number kolon yoksa atla
        if not hasattr(cls, "order_number"):
            continue
        ts_col, _, _ = _col(cls, ORD_TS_CANDS, "ts")
        if ts_col is None:
            _info("order_nos: skip (no ts)", table=name); 
            continue
        q = (db.session.query(getattr(cls, "order_number"))
             .filter(or_(
                 and_(func.timezone('Europe/Istanbul', ts_col) >= start_ist,
                      func.timezone('Europe/Istanbul', ts_col) <  end_ist),
                 and_(ts_col >= start_ist, ts_col < end_ist)
             )))
        rows = [r[0] for r in q.all() if r and r[0]]
        if rows:
            order_nos.update(map(str, rows))
        _info("order_nos: table fetched", table=name, rows=len(rows))
    _info("order_nos: aggregated", count=len(order_nos))
    return order_nos



def _collect_orders_between_strict(start_ist: datetime, end_ist: datetime):
    t0=_t0()
    qty_map, amt_map = {}, {}   # amt_map artık NET tutar olacak
    _info("orders: collecting", start=str(start_ist), end=str(end_ist))

    def add(bc, q, a):
        if not bc or q <= 0: return
        s = str(bc).strip()
        qty_map[s] = qty_map.get(s, 0) + int(q)
        if a is not None:
            amt_map[s] = amt_map.get(s, 0.0) + float(a)

    sources = [("Created",OrderCreated), ("Picking",OrderPicking), ("Shipped",OrderShipped), ("Delivered",OrderDelivered), ("Archive",Archive)]
    if "order_date" not in ORD_TS_CANDS: ORD_TS_CANDS.insert(0, "order_date")

    for name, cls in sources:
        t1=_t0()
        try:
            ts_col, _, _   = _col(cls, ORD_TS_CANDS, "ts")
            amt_col, _, A  = _col(cls, ORD_AMT_CANDS,  "amount")
            disc_col,_, D  = _col(cls, ORD_DISC_CANDS, "discount")  # ← indirim
            det_name = next((n for n in ORD_DTL_CANDS if hasattr(cls, n)), None)
            if ts_col is None:
                _info("orders: skip (no ts)", table=name)
                continue

            q = db.session.query(cls).filter(
                or_(
                    and_(func.timezone('Europe/Istanbul', ts_col) >= start_ist,
                         func.timezone('Europe/Istanbul', ts_col) <  end_ist),
                    and_(ts_col >= start_ist, ts_col < end_ist)
                )
            )
            rows = q.all()
            _info("orders: table fetched", table=name, rows=len(rows), ms=_dt_ms(t1))
            for row in rows:
                payload = getattr(row, det_name) if (det_name and hasattr(row, det_name)) else None
                if payload in (None,"",[]):
                    for alt in ["raw_json","raw","order_json","json"]:
                        if hasattr(row, alt):
                            payload = getattr(row, alt)
                            if payload not in (None,"",[]): break

                # ---- BRÜT ve İNDİRİM ----
                amount_gross   = _to_number(getattr(row, A, None), None) if (A and hasattr(row, A)) else None
                discount_total = _to_number(getattr(row, D, None), 0.0)  if (D and hasattr(row, D)) else 0.0
                amount_net     = None
                if amount_gross is not None:
                    try:
                        amount_net = float(amount_gross) - float(discount_total or 0.0)
                    except Exception:
                        amount_net = amount_gross

                # ---- KALEMLER ----
                items, total_qty = [], 0
                for it in _iter_items_once(payload) or []:
                    bc = _pick_first(it, BARCODE_CANDS, None)
                    qt = _to_number(_pick_first(it, ITEM_QTY_CANDS, 1), 0) or 0
                    pr = _to_number(_pick_first(it, ITEM_PRICE_CANDS, None), None)  # satır fiyatı (brüt/net bilinmeyebilir)
                    if not bc or int(qt) <= 0: continue
                    items.append({"bc": bc, "qty": int(qt), "price": pr})
                    total_qty += int(qt)

                # ---- NET PAYLAŞIM ----
                per_unit_net = (amount_net/float(total_qty)) if (amount_net is not None and total_qty>0) else None
                for it in items:
                    # öncelik NET toplamı paylaştırmak; fallback olarak satır fiyatını kullan
                    line_amt_net = (per_unit_net*it["qty"]) if per_unit_net is not None else ((it["price"]*it["qty"]) if it["price"] is not None else None)
                    add(it["bc"], it["qty"], line_amt_net)

        except Exception:
            _exc(f"orders: table failed ({name})")

    _info("orders: aggregated", uniq_barcodes=len(qty_map), ms=_dt_ms(t0))
    return qty_map, amt_map



def now_tr_str():
    return datetime.now(IST).strftime("%d/%m/%Y %H:%M")

# ── Esnek kolon bulucu
def _col(model_cls, candidates, label=None):
    for name in candidates:
        col = getattr(model_cls, name, None)
        if col is not None:
            return col, (col.label(label) if label else col), name
    return None, (literal(None).label(label) if label else None), None

def _log(title, mapping):
    print("🧭 [CANLI PANEL]", title)
    for k, v in mapping.items():
        print(f"   - {k}: {v}")

# ── Aday listeleri
BARCODE_CANDS = [
    "barcode","barkod","urun_barkod","product_barcode","productBarcode",
    "sku","stock_code","stok_kodu","gtin","ean","ean13","upc","model_barcode"
]
MODEL_CANDS   = ["product_main_id"]  # sadece model kodu
COLOR_CANDS   = ["color","renk","colour","color_name","urun_renk"]
SIZE_CANDS    = ["size","beden","number","numara","shoe_size","beden_no"]
IMG_CANDS     = ["image_url","image","image1","main_image","cover_image","img","photo","img_url","thumb_url","picture","primary_image","image_urls","images"]

CS_QTY_CANDS  = ["quantity","qty","adet","available","stock","onhand","miktar","mevcut"]
ORD_DISC_CANDS = ["discount","order_discount","discount_amount","indirim","indirim_tutari"]

ORD_TS_CANDS = [
    "order_date", "delivered_at",  # ← eklendi
    "created_at","created","order_created_at","timestamp",
    "createdDate","create_date_time","date","olusturma_tarihi","shipped_at"
]
ORD_DTL_CANDS  = ["details","items","lines","order_lines","orderItems","kalemler","urunler","json_items","raw_json"]
ORD_AMT_CANDS  = ["amount","total_amount","order_amount","grand_total","total","line_total","price_total","sum","paid_amount"]
ORD_ID_CANDS   = ["order_number","orderNumber","orderNo","order_id","orderId","trendyol_order_id","platform_order_id"]

ITEM_QTY_CANDS   = ["quantity","qty","adet","miktar","count","units","piece","quantityOrdered","adet_sayisi"]
ITEM_PRICE_CANDS = ["unitPrice","unit_price","price","salePrice","sale_price","amount","line_total","total","lineTotal","totalPrice","total_price","payablePrice"]
ITEM_SIZE_CANDS  = ["size","beden","number","numara","shoe_size","beden_no"]

# EKLE: siparişin ilk oluşturulma zamanını bul
ORDER_CREATED_PREF = [
    "created_at","created","order_created_at","timestamp",
    "createdDate","create_date_time","order_date","date","olusturma_tarihi"
]

# ── Product/Stock kolon eşleşmeleri
PROD_MODEL_RAW, PROD_MODEL, PROD_MODEL_NAME = _col(Product, MODEL_CANDS, "model")
PROD_COLOR_RAW, PROD_COLOR, PROD_COLOR_NAME = _col(Product, COLOR_CANDS, "renk")
PROD_SIZE_RAW,  PROD_SIZE,  PROD_SIZE_NAME  = _col(Product, SIZE_CANDS,  "beden")
PROD_BAR_RAW,   PROD_BAR,   PROD_BAR_NAME   = _col(Product, BARCODE_CANDS, "product_barcode")
PROD_IMG_RAW,   PROD_IMG,   PROD_IMG_NAME   = _col(Product, IMG_CANDS, "image_url")

CS_BAR_RAW,     CS_BAR,     CS_BAR_NAME     = _col(CentralStock, BARCODE_CANDS, "product_barcode")
CS_QTY_RAW,     CS_QTY,     CS_QTY_NAME     = _col(CentralStock, CS_QTY_CANDS, "stok")

missing = []
if PROD_BAR_RAW is None: missing.append("Product.barcode")
if CS_BAR_RAW   is None: missing.append("CentralStock.barcode")
if missing: raise RuntimeError("Barcode kolonları eksik: " + ", ".join(missing))
if CS_QTY_RAW is None: CS_QTY = literal(0).label("stok")

_log("Seçilen kolonlar (Product/Stock)", {
    "Product.product_main_id":  PROD_MODEL_NAME,
    "Product.color":            PROD_COLOR_NAME,
    "Product.size":             PROD_SIZE_NAME,
    "Product.barcode":          PROD_BAR_NAME,
    "Product.image":            PROD_IMG_NAME,
    "CentralStock.barcode":     CS_BAR_NAME,
    "CentralStock.qty":         CS_QTY_NAME,
})



def _get_order_created_ts(order_number):
    if not order_number:
        return None
    for cls_name, cls in [("Created",OrderCreated),("Picking",OrderPicking),
                          ("Shipped",OrderShipped),("Delivered",OrderDelivered),
                          ("Archive",Archive)]:
        try:
            # order_number kolonu yoksa getattr None döner → filtre atlanır
            if not hasattr(cls, "order_number"):
                continue
            row = db.session.query(cls).filter(cls.order_number == order_number).first()
            if not row:
                continue
            for k in ORDER_CREATED_PREF:
                if hasattr(cls, k):
                    val = getattr(row, k)
                    if val:
                        return _to_ist_aware(val)
        except Exception:
            _exc(f"_get_order_created_ts failed on {cls_name}")
            continue
    _info("_get_order_created_ts: not found", order_number=order_number)
    return None




# ── TR gün penceresi (DB)
def tr_today_bounds_sql():
    start_tr = func.date_trunc('day', func.timezone('Europe/Istanbul', func.now()))
    end_tr   = start_tr + text("interval '1 day'")
    return start_tr, end_tr

# ── yardımcılar
def _pick_first(d: dict, keys, default=None):
    for k in keys:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return default

def _to_number(x, default=None):
    """ None/'None'/'null'/boş → default; '₺1.234,56 TL' → 1234.56; '1,234.56' → 1234.56 """
    if x is None: return default
    s = str(x).strip()
    if s == "" or s.lower() in ("none","null","nan","-"): return default
    s = (s.replace("₺","").replace("TL","").replace("TRY","").replace("\xa0","").replace(" ",""))
    if "," in s and "." in s:
        s = s.replace(".","").replace(",",".")
    else:
        if "," in s: s = s.replace(",",".")
    try: return float(s)
    except Exception: return default

def _json_parse(obj):
    if isinstance(obj, (dict, list)): return obj
    if isinstance(obj, str):
        try: return json.loads(obj)
        except Exception: return None
    return None

def _iter_items_once(blob):
    """Aynı listeyi iki kez saymayı engelle (tek anahtar)."""
    root = _json_parse(blob)
    if root is None: return
    if isinstance(root, list):
        for it in root:
            if isinstance(it, dict): yield it
        return
    if isinstance(root, dict):
        for key in ["details","items","lines","order_lines","orderItems","kalemler","urunler","json_items"]:
            arr = root.get(key)
            if isinstance(arr, list):
                for it in arr:
                    if isinstance(it, dict): yield it
                return
        for v in root.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                for it in v: yield it
                return

def _extract_order_id_from_row_or_payload(row, payload):
    # tablo kolonu
    for n in ORD_ID_CANDS:
        if hasattr(row, n):
            v = getattr(row, n)
            if v not in (None,""): return str(v)
    # payload kökü
    root = _json_parse(payload)
    if isinstance(root, dict):
        for n in ORD_ID_CANDS:
            v = root.get(n)
            if v not in (None,""): return str(v)
    return None

def _content_signature(items, src_name, row_id):
    """OrderId yoksa, içerik imzası (barcode|size|qty) ile stabil kimlik üret."""
    parts = []
    for it in items:
        bc = str(it.get("bc") or "").strip()
        sz = str(it.get("size") or "").strip()
        qt = int(it.get("qty") or 0)
        parts.append(f"{bc}|{sz}|{qt}")
    sig = "|".join(sorted(parts)) or f"{src_name}:{row_id}"
    return "SIG:" + hashlib.md5(sig.encode("utf-8")).hexdigest()

# ── BUGÜN OLUŞTURULAN SİPARİŞ SETİ (YALNIZ OrderCreated)
def _collect_today_order_ids_by_created():
    start_tr, end_tr = tr_today_bounds_sql()
    ts_raw, _, _ = _col(OrderCreated, ["created_at","created","order_created_at","timestamp","createdDate","create_date_time","date","olusturma_tarihi"], "ts")

    q = db.session.query(OrderCreated)
    if ts_raw is not None:
        q = q.filter(
            func.timezone('Europe/Istanbul', ts_raw) >= start_tr,
            func.timezone('Europe/Istanbul', ts_raw) <  end_tr
        )

    today_ids = set()
    for row in q.all():
        payload = None
        # details/raw json (kimlik kökünden de gelebilir)
        for cand in ["details","raw_json","order_json","json","items","lines","order_lines","orderItems"]:
            if hasattr(row, cand):
                payload = getattr(row, cand)
                if payload not in (None,"",[]): break

        # item'lar sadece imza fallback için okunuyor
        items = []
        for it in _iter_items_once(payload) or []:
            bc = _pick_first(it, BARCODE_CANDS, None)
            qt = _to_number(_pick_first(it, ITEM_QTY_CANDS, 1), 0) or 0
            sz = _pick_first(it, ITEM_SIZE_CANDS, "")
            if not bc or int(qt) <= 0: 
                continue
            items.append({"bc": bc, "qty": int(qt), "size": sz})

        oid = _extract_order_id_from_row_or_payload(row, payload)
        if not oid:
            oid = _content_signature(items, "Created", getattr(row,"id",None))
        today_ids.add(oid)
    return today_ids

# ── Sipariş satırlarını çıkarma — SADECE "bugün oluşturulan" siparişler
def _collect_orders_today():
    """
    00:00–23:59 TR → Created + Picking + Shipped + Archive
    - Dahil edilecek siparişler: sadece OrderCreated'a göre bugün oluşturulanlar
    - Order-bazlı DEDUP: Archive > Shipped > Picking > Created
    Döner: barcode → qty  ve barcode → amount_toplam
    """
    today_order_ids = _collect_today_order_ids_by_created()

    qty_map, amt_map = {}, {}
    seen_orders = set()  # order_id (Created/… tüm tablolarda aynı olacak)

    sources = [
    ("Created",   OrderCreated),
    ("Picking",   OrderPicking),
    ("Shipped",   OrderShipped),
    ("Delivered", OrderDelivered),  # ← eklendi
    ("Archive",   Archive)          # ← geçmiş gün
]
    start_tr, end_tr = tr_today_bounds_sql()  # sadece log/debug için

    for src_name, cls in sources:
        ts_raw, _, ts_name   = _col(cls, ORD_TS_CANDS, "ts")
        amt_raw, _, amt_name = _col(cls, ORD_AMT_CANDS, "amount")
        det_name = None
        for n in ORD_DTL_CANDS:
            if hasattr(cls, n): det_name = n; break

        _log(f"{src_name} kolonları", {"ts": ts_name, "amount": amt_name, "details": det_name})

        q = db.session.query(cls)
        # NOT: Bu tablolarda tarih filtresi uygulamıyoruz; yalnızca "bugün oluşturulan" order_id setine göre alıyoruz.
        rows = q.all()

        for row in rows:
            payload = getattr(row, det_name) if (det_name and hasattr(row, det_name)) else None
            if payload in (None,"",[]):
                for alt in ["raw_json","raw","order_json","json"]:
                    if hasattr(row, alt):
                        payload = getattr(row, alt)
                        if payload not in (None,"",[]): break

            # item'ları oku (size imza için)
            items = []
            total_qty_in_order = 0
            for it in _iter_items_once(payload) or []:
                bc = _pick_first(it, BARCODE_CANDS, None)
                qt = _to_number(_pick_first(it, ITEM_QTY_CANDS, 1), 0) or 0
                sz = _pick_first(it, ITEM_SIZE_CANDS, "")
                pr = _to_number(_pick_first(it, ITEM_PRICE_CANDS, None), None)
                if not bc or int(qt) <= 0: 
                    continue
                items.append({"bc": bc, "qty": int(qt), "size": sz, "price": pr})
                total_qty_in_order += int(qt)

            # sipariş kimliği (Created setine göre dahil/haric)
            order_id = _extract_order_id_from_row_or_payload(row, payload)
            if not order_id:
                order_id = _content_signature(items, src_name, getattr(row,"id",None))

            if order_id not in today_order_ids:
                continue  # BUGÜN oluşturulmamış → atla

            if order_id in seen_orders:
                continue  # DEDUP order bazında
            seen_orders.add(order_id)

            # sipariş toplamı (opsiyonel)
            order_amount_total = _to_number(getattr(row, amt_name, None), None) if (amt_name and hasattr(row, amt_name)) else None
            per_unit = (float(order_amount_total) / float(total_qty_in_order)) if (order_amount_total is not None and total_qty_in_order > 0) else None

            # topla
            for it in items:
                bc, qt, pr = it["bc"], it["qty"], it["price"]
                line_amount = pr * qt if pr is not None else (per_unit * qt if per_unit is not None else None)
                bc_s = str(bc).strip()
                qty_map[bc_s] = qty_map.get(bc_s, 0) + qt
                if line_amount is not None:
                    amt_map[bc_s] = amt_map.get(bc_s, 0.0) + float(line_amount)

    return qty_map, amt_map

# ── Ürün / stok
def _parse_first_image(val):
    if not val: return None
    if isinstance(val, str):
        s = val.strip()
        if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
            try:
                j = json.loads(s)
                if isinstance(j, list) and j:
                    v = j[0]
                    if isinstance(v, str): return v
                    if isinstance(v, dict):
                        for k in ["url","image","src","href"]:
                            if v.get(k): return v[k]
                if isinstance(j, dict):
                    for k in ["url","image","src","main","cover","0"]:
                        if j.get(k):
                            vv = j[k]
                            if isinstance(vv, list) and vv:
                                return vv[0] if isinstance(vv[0], str) else vv[0].get("url")
                            if isinstance(vv, str): return vv
            except Exception:
                pass
        if "," in s: return s.split(",")[0].strip()
        return s
    if isinstance(val, list) and val:
        v = val[0]
        if isinstance(v, str): return v
        if isinstance(v, dict):
            for k in ["url","image","src","href"]:
                if v.get(k): return v[k]
    if isinstance(val, dict):
        for k in ["url","image","src","main","cover"]:
            if val.get(k): return val[k]
    return None

def _fetch_product_info_for_barcodes(barcodes):
    if not barcodes: return {}
    cols = [PROD_BAR_RAW, PROD_MODEL, PROD_COLOR, PROD_SIZE]
    if PROD_IMG is not None: cols.append(PROD_IMG)
    rows = db.session.query(*cols).filter(PROD_BAR_RAW.in_(list(barcodes))).all()
    info = {}
    for r in rows:
        bc = str(r[0]).strip()
        model = r[1] if r[1] not in (None, "") else "Bilinmiyor"
        renk  = r[2] if r[2] not in (None, "") else "Bilinmiyor"
        beden = r[3] if r[3] not in (None, "") else "—"
        img   = _parse_first_image(r[4]) if len(r) > 4 else None
        info[bc] = {"model": model, "renk": renk, "beden": beden, "image": img}
    return info

def _fetch_stock_for_barcodes(barcodes):
    if not barcodes: return {}
    rows = (
        db.session.query(CS_BAR_RAW, func.coalesce(func.sum(CS_QTY), 0))
        .filter(CS_BAR_RAW.in_(list(barcodes)))
        .group_by(CS_BAR_RAW).all()
    )
    return {str(bc).strip(): int(st or 0) for bc, st in rows}

# ── Kart üretimi + toplam satış + ortalama fiyat
def _build_cards_from_orders():
    qty_map, amt_map = _collect_orders_today_strict()
    barcodes = set(qty_map.keys()) | set(amt_map.keys())
    pinfo = _fetch_product_info_for_barcodes(barcodes)
    sdict = _fetch_stock_for_barcodes(barcodes)

    grp = {}
    rep_image = {}  # (model,renk) → image

    for bc in barcodes:
        qty = int(qty_map.get(bc, 0))
        amt = _to_number(amt_map.get(bc, None), None)
        info = pinfo.get(bc, {"model":"Bilinmiyor","renk":"Bilinmiyor","beden":"—","image":None})
        key = (info["model"], info["renk"])
        if key not in rep_image and info.get("image"):
            rep_image[key] = info["image"]
        d = grp.setdefault(key, {})
        b = info["beden"]
        rec = d.setdefault(b, {"siparis":0, "stok":0, "tutar":0.0, "tutarli_adet":0})
        rec["siparis"] += qty
        rec["stok"] += int(sdict.get(bc, 0))
        if amt is not None:
            rec["tutar"] += float(amt)
            rec["tutarli_adet"] += qty

    now_tr = datetime.now(IST)
    hours = max(1.0, now_tr.hour + now_tr.minute/60.0)

    kartlar = []
    total_sold = 0

    def _beden_key(b):
        try: return (0, float(str(b).replace(',','.')))
        except: return (1, str(b))

    for (model, renk), beden_map in grp.items():
        detay = []
        toplam_sip = 0
        toplam_stok = 0
        toplam_tutar = 0.0
        toplam_tutarli_adet = 0

        for beden in sorted(beden_map.keys(), key=_beden_key):
            s = int(beden_map[beden]["siparis"])
            k = int(beden_map[beden]["stok"])
            a = float(beden_map[beden]["tutar"])
            qa = int(beden_map[beden]["tutarli_adet"])
            toplam_sip += s
            toplam_stok += k
            toplam_tutar += a
            toplam_tutarli_adet += qa
            detay.append({"beden": beden, "siparis": s, "stok": k})

        total_sold += toplam_sip
        ort_fiyat = (toplam_tutar / toplam_tutarli_adet) if toplam_tutarli_adet > 0 else 0.0

        kartlar.append({
            "model": model,  # product_main_id
            "renk": renk,
            "image": rep_image.get((model, renk)),
            "toplam_siparis_bugun": toplam_sip,
            "toplam_stok": toplam_stok,
            "ortalama_fiyat": round(ort_fiyat, 2),
            "saatlik_hiz": round(toplam_sip / hours, 2),
            "dusuk_stok": toplam_stok < DUSUK_STOK_ESIK,
            "detay": detay
        })

    kartlar.sort(key=lambda k: (k["toplam_siparis_bugun"], k["toplam_stok"]), reverse=True)
    return kartlar, total_sold

# ── API’ler
@canli_panel_bp.route("/api/canli/ozet")
def ozet_json():
    t0=_t0()
    try:
        accept = request.headers.get("Accept","")
        if "text/html" in accept and "application/json" not in accept:
            _info("ozet_json: redirect to page")
            return redirect(url_for("canli_panel.canli_panel_sayfa"))

        # 1) aralık
        start_ist, end_ist = _tr_range_from_params(request.args)
        _info("ozet_json: start", start=str(start_ist), end=str(end_ist))

        # 2) satış (adet + NET tutar) — barcode→qty / barcode→net_tutar
        t1=_t0()
        qty_map, net_map = _collect_orders_between_strict(start_ist, end_ist)   # ← net_map = amount - discount
        _info("ozet_json: orders done", qty=len(qty_map), net=len(net_map), ms=_dt_ms(t1))

        # 3) sadece gösterilen siparişlerin iadeleri
        t2=_t0()
        ord_nos = _order_numbers_created_between(start_ist, end_ist)
        ret_qty_map, returned_orders = _collect_returns_for_order_numbers(ord_nos)
        _info("ozet_json: returns done", ret=len(ret_qty_map), returned=len(returned_orders), ms=_dt_ms(t2))

        # 4) ürün/stok
        barcodes = set(qty_map.keys()) | set(net_map.keys()) | set(ret_qty_map.keys())
        pinfo = _fetch_product_info_for_barcodes(barcodes)
        sdict = _fetch_stock_for_barcodes(barcodes)

        # 5) gruplama: default MODEL+RENK, ?group=barcode ise barkod
        group_by_barcode = _want_group_by_barcode()
        tek_model = (request.args.get("model") or "").strip() or None

        grp, rep_image = {}, {}
        for bc in barcodes:
            sat = int(qty_map.get(bc, 0))
            iad = int(ret_qty_map.get(bc, 0))
            net = _to_number(net_map.get(bc, None), None)   # NET tutar
            info = pinfo.get(bc, {"model":"Bilinmiyor","renk":"Bilinmiyor","beden":"—","image":None})

            if group_by_barcode:
                rec = grp.setdefault(bc, {
                    "model": info["model"], "renk": info["renk"], "beden": info["beden"],
                    "image": info.get("image"),
                    "siparis":0, "iade":0, "net_adet":0, "stok":0,
                    "net_tutar":0.0, "tutarli_adet":0
                })
                rec["siparis"]  += sat
                rec["iade"]     += iad
                rec["net_adet"] += max(0, sat - iad)
                rec["stok"]     += int(sdict.get(bc, 0))
                if net is not None and sat > 0:
                    rec["net_tutar"]   += float(net)
                    rec["tutarli_adet"]+= sat
            else:
                key = (info["model"], info["renk"])
                if key not in rep_image and info.get("image"): rep_image[key] = info["image"]
                d = grp.setdefault(key, {})
                b = info["beden"]
                rec = d.setdefault(b, {"siparis":0,"iade":0,"net_adet":0,"stok":0,"net_tutar":0.0,"tutarli_adet":0})
                rec["siparis"]  += sat
                rec["iade"]     += iad
                rec["net_adet"] += max(0, sat - iad)
                rec["stok"]     += int(sdict.get(bc, 0))
                if net is not None and sat > 0:
                    rec["net_tutar"]   += float(net)
                    rec["tutarli_adet"]+= sat

        # 6) kartlar
        now_tr = datetime.now(IST)
        hours  = max(1.0, now_tr.hour + now_tr.minute/60.0)
        kartlar = []
        toplam_net_satis = 0
        toplam_net_tutar_all, toplam_adet_all = 0.0, 0

        if group_by_barcode:
            for bc, rec in grp.items():
                model, renk, beden = rec["model"], rec["renk"], rec["beden"]
                if tek_model and str(model) != tek_model: continue
                s = rec["siparis"]; r = rec["iade"]; n_adet = rec["net_adet"]
                k = rec["stok"];    nt = rec["net_tutar"]; qa = rec["tutarli_adet"]

                toplam_net_satis      += n_adet
                toplam_net_tutar_all  += nt
                toplam_adet_all       += qa

                iade_oran  = (r/s) if s>0 else 0.0
                ort_net    = (nt/qa) if qa>0 else 0.0
                iade_uyari = (iade_oran >= IADE_UYARI_ORAN)

                kartlar.append({
                    "barcode": bc, "model": model, "renk": renk, "image": rec.get("image"),
                    "toplam_siparis_bugun": s, "toplam_iade": r,
                    "toplam_net_satis": n_adet, "iade_orani": round(iade_oran,2), "iade_uyari": iade_uyari,
                    "toplam_stok": k, "ortalama_fiyat": round(ort_net, 2),   # NET ortalama
                    "saatlik_hiz": round(n_adet / hours, 2), "dusuk_stok": k < DUSUK_STOK_ESIK,
                    "detay": [{"beden": beden, "siparis": s, "iade": r, "net": n_adet, "stok": k}]
                })
        else:
            def _beden_key(b):
                try: return (0, float(str(b).replace(',','.')))
                except: return (1, str(b))
            for (model, renk), beden_map in grp.items():
                if tek_model and str(model) != tek_model: continue
                detay=[]; top_sat=top_iade=top_net_adet=top_stok=0; top_net_tutar=0.0; top_tutarli_adet=0
                for beden in sorted(beden_map.keys(), key=_beden_key):
                    s = beden_map[beden]["siparis"]; r = beden_map[beden]["iade"]; n_adet = beden_map[beden]["net_adet"]
                    k = beden_map[beden]["stok"];    nt= beden_map[beden]["net_tutar"]; qa     = beden_map[beden]["tutarli_adet"]
                    top_sat+=s; top_iade+=r; top_net_adet+=n_adet; top_stok+=k; top_net_tutar+=nt; top_tutarli_adet+=qa
                    detay.append({"beden":beden,"siparis":s,"iade":r,"net":n_adet,"stok":k})
                toplam_net_satis     += top_net_adet
                toplam_net_tutar_all += top_net_tutar
                toplam_adet_all      += top_tutarli_adet

                iade_oran  = (top_iade/top_sat) if top_sat>0 else 0.0
                ort_net    = (top_net_tutar/top_tutarli_adet) if top_tutarli_adet>0 else 0.0
                iade_uyari = (iade_oran >= IADE_UYARI_ORAN)

                kartlar.append({
                    "model":model,"renk":renk,"image":rep_image.get((model,renk)),
                    "toplam_siparis_bugun":top_sat,"toplam_iade":top_iade,"toplam_net_satis":top_net_adet,
                    "iade_orani":round(iade_oran,2),"iade_uyari":iade_uyari,
                    "toplam_stok":top_stok,"ortalama_fiyat":round(ort_net,2),   # NET ortalama
                    "saatlik_hiz":round(top_net_adet/hours,2),"dusuk_stok":top_stok < DUSUK_STOK_ESIK,
                    "detay":detay
                })

        kartlar.sort(key=lambda k:(k.get("iade_uyari",False), k.get("toplam_iade",0), k.get("toplam_net_satis",0)), reverse=True)
        genel_ortalama_fiyat = round((toplam_net_tutar_all / toplam_adet_all), 2) if toplam_adet_all > 0 else 0.0
        toplam_ciro = round(toplam_net_tutar_all, 2)  # Toplam NET ciro

        _info("ozet_json: done", cards=len(kartlar), ms=_dt_ms(t0))
        return jsonify({
            "guncellendi": now_tr.strftime("%d/%m/%Y %H:%M"),
            "range": {"start": start_ist.strftime("%Y-%m-%d"), "end_exclusive": end_ist.strftime("%Y-%m-%d")},
            "group": ("barcode" if group_by_barcode else "model"),
            "toplam_net_satis": toplam_net_satis,
            "toplam_siparis_sayisi": _count_orders_between_distinct(start_ist, end_ist),
            "genel_ortalama_fiyat": genel_ortalama_fiyat,        # NET
            "toplam_ciro": toplam_ciro,                          # Toplam NET ciro
            "kartlar": kartlar
        })
    except Exception:
        _exc("ozet_json: failed")
        return jsonify({"error":"internal_error"}), 500




@canli_panel_bp.route("/api/canli/akis")
def akis_sse():
    def _gen():
        conn_t0=_t0()
        _info("SSE: client connected", ip=request.remote_addr)
        try:
            while True:
                loop_t0=_t0()
                try:
                    start_ist, end_ist = _tr_range_from_params(request.args)
                    _info("SSE: loop start", start=str(start_ist), end=str(end_ist))

                    # satış (adet + NET tutar)
                    qty_map, net_map = _collect_orders_between_strict(start_ist, end_ist)
                    # sadece gösterilen siparişlerin iadeleri
                    ord_nos = _order_numbers_created_between(start_ist, end_ist)
                    ret_qty_map, returned_orders = _collect_returns_for_order_numbers(ord_nos)

                    barcodes = set(qty_map.keys()) | set(net_map.keys()) | set(ret_qty_map.keys())
                    pinfo = _fetch_product_info_for_barcodes(barcodes)
                    sdict = _fetch_stock_for_barcodes(barcodes)

                    group_by_barcode = _want_group_by_barcode()
                    tek_model = (request.args.get("model") or "").strip() or None

                    grp, rep_image = {}, {}
                    for bc in barcodes:
                        sat=int(qty_map.get(bc,0))
                        iad=int(ret_qty_map.get(bc,0))
                        net=_to_number(net_map.get(bc,None), None)
                        info = pinfo.get(bc, {"model":"Bilinmiyor","renk":"Bilinmiyor","beden":"—","image":None})

                        if group_by_barcode:
                            rec = grp.setdefault(bc, {
                                "model":info["model"],"renk":info["renk"],"beden":info["beden"],"image":info.get("image"),
                                "siparis":0,"iade":0,"net_adet":0,"stok":0,"net_tutar":0.0,"tutarli_adet":0
                            })
                            rec["siparis"]+=sat; rec["iade"]+=iad; rec["net_adet"]+=max(0,sat-iad); rec["stok"]+=int(sdict.get(bc,0))
                            if net is not None and sat>0: rec["net_tutar"]+=float(net); rec["tutarli_adet"]+=sat
                        else:
                            key=(info["model"],info["renk"])
                            if key not in rep_image and info.get("image"): rep_image[key]=info["image"]
                            d=grp.setdefault(key,{})
                            b=info["beden"]
                            rec=d.setdefault(b,{"siparis":0,"iade":0,"net_adet":0,"stok":0,"net_tutar":0.0,"tutarli_adet":0})
                            rec["siparis"]+=sat; rec["iade"]+=iad; rec["net_adet"]+=max(0,sat-iad); rec["stok"]+=int(sdict.get(bc,0))
                            if net is not None and sat>0: rec["net_tutar"]+=float(net); rec["tutarli_adet"]+=sat

                    now_tr=datetime.now(IST); hours=max(1.0, now_tr.hour + now_tr.minute/60.0)
                    kartlar=[]; toplam_net_satis=0; toplam_net_tutar_sse=0.0

                    if group_by_barcode:
                        for bc, rec in grp.items():
                            model,renk,beden = rec["model"], rec["renk"], rec["beden"]
                            if tek_model and str(model) != tek_model: continue
                            s=rec["siparis"]; r=rec["iade"]; n_adet=rec["net_adet"]
                            k=rec["stok"];    nt=rec["net_tutar"]; qa=rec["tutarli_adet"]
                            toplam_net_satis += n_adet
                            toplam_net_tutar_sse += nt
                            iade_oran=(r/s) if s>0 else 0.0
                            ort_net=(nt/qa) if qa>0 else 0.0
                            iade_uyari=(iade_oran>=IADE_UYARI_ORAN)
                            kartlar.append({
                                "barcode": bc, "model": model, "renk": renk, "image": rec.get("image"),
                                "toplam_siparis_bugun": s, "toplam_iade": r,
                                "toplam_net_satis": n_adet, "iade_orani": round(iade_oran,2), "iade_uyari": iade_uyari,
                                "toplam_stok": k, "ortalama_fiyat": round(ort_net,2),
                                "saatlik_hiz": round(n_adet / hours, 2), "dusuk_stok": k < DUSUK_STOK_ESIK,
                                "detay": [{"beden": beden, "siparis": s, "iade": r, "net": n_adet, "stok": k}]
                            })
                    else:
                        def _beden_key(b):
                            try: return (0, float(str(b).replace(',','.')))
                            except: return (1, str(b))
                        for (model,renk), beden_map in grp.items():
                            if tek_model and str(model) != tek_model: continue
                            detay=[]; top_sat=top_iade=top_net_adet=top_stok=0; top_net_tutar=0.0; top_tutarli_adet=0
                            for beden in sorted(beden_map.keys(), key=_beden_key):
                                s=beden_map[beden]["siparis"]; r=beden_map[beden]["iade"]; n_adet=beden_map[beden]["net_adet"]
                                k=beden_map[beden]["stok"];    nt=beden_map[beden]["net_tutar"]; qa=beden_map[beden]["tutarli_adet"]
                                top_sat+=s; top_iade+=r; top_net_adet+=n_adet; top_stok+=k; top_net_tutar+=nt; top_tutarli_adet+=qa
                                detay.append({"beden":beden,"siparis":s,"iade":r,"net":n_adet,"stok":k})
                            toplam_net_satis+=top_net_adet
                            toplam_net_tutar_sse+=top_net_tutar
                            iade_oran=(top_iade/top_sat) if top_sat>0 else 0.0
                            ort_net=(top_net_tutar/top_tutarli_adet) if top_tutarli_adet>0 else 0.0
                            iade_uyari=(iade_oran>=IADE_UYARI_ORAN)
                            kartlar.append({
                                "model":model,"renk":renk,"image":rep_image.get((model,renk)),
                                "toplam_siparis_bugun":top_sat,"toplam_iade":top_iade,"toplam_net_satis":top_net_adet,
                                "iade_orani":round(iade_oran,2),"iade_uyari":iade_uyari,
                                "toplam_stok":top_stok,"ortalama_fiyat":round(ort_net,2),
                                "saatlik_hiz":round(top_net_adet/hours,2),"dusuk_stok":top_stok < DUSUK_STOK_ESIK,
                                "detay":detay
                            })

                    kartlar.sort(key=lambda k:(k.get("iade_uyari",False),k.get("toplam_iade",0),k.get("toplam_net_satis",0)), reverse=True)
                    toplam_ciro_sse = round(toplam_net_tutar_sse, 2)
                    payload={
                        "guncellendi": now_tr_str(),
                        "group": ("barcode" if group_by_barcode else "model"),
                        "toplam_net_satis": toplam_net_satis,
                        "toplam_siparis_sayisi": _count_orders_between_distinct(start_ist,end_ist),
                        "toplam_ciro": toplam_ciro_sse,
                        "kartlar": kartlar
                    }
                    _info("SSE: loop done", cards=len(kartlar), net=toplam_net_satis, uniq=len(barcodes), ms=_dt_ms(loop_t0))

                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                except GeneratorExit:
                    _info("SSE: client disconnected"); return
                except Exception:
                    _exc("SSE: loop error")
                    yield "event: error\ndata: {\"error\":\"internal_error\"}\n\n"

                # heartbeat
                yield "event: ping\ndata: {}\n\n"
                _pytime.sleep(AKIS_ARALIGI_SANIYE)
        finally:
            _info("SSE: connection closed", alive_ms=_dt_ms(conn_t0))

    headers = {"Content-Type":"text/event-stream","Cache-Control":"no-cache","Connection":"keep-alive"}
    return Response(stream_with_context(_gen()), headers=headers)



# ── HTML panel sayfası
@canli_panel_bp.route("/canli-panel")
def canli_panel_sayfa():
    return render_template("canli_panel.html")


def _collect_orders_today_strict():
    start_tr, end_tr = tr_today_bounds_sql()
    qty_map, amt_map = {}, {}   # amt_map = NET

    def add(bc, q, a):
        if not bc or q <= 0: return
        s = str(bc).strip()
        qty_map[s] = qty_map.get(s, 0) + int(q)
        if a is not None:
            amt_map[s] = amt_map.get(s, 0.0) + float(a)

    sources = [
        ("Created",   OrderCreated),
        ("Picking",   OrderPicking),
        ("Shipped",   OrderShipped),
        ("Delivered", OrderDelivered),
        ("Archive",   Archive)
    ]
    for name, cls in sources:
        ts_col, _, ts_name   = _col(cls, ORD_TS_CANDS,  "ts")
        amt_col,_, amt_name  = _col(cls, ORD_AMT_CANDS, "amount")
        disc_col,_, disc_name= _col(cls, ORD_DISC_CANDS,"discount")
        det_name = next((n for n in ORD_DTL_CANDS if hasattr(cls, n)), None)

        if ts_col is None:
            print(f"[CANLI PANEL] UYARI: {name} için tarih kolonu bulunamadı, tablo atlandı.")
            continue

        q = db.session.query(cls).filter(
            or_(
                and_(func.timezone('Europe/Istanbul', ts_col) >= start_tr,
                     func.timezone('Europe/Istanbul', ts_col) <  end_tr),
                and_(ts_col >= start_tr, ts_col < end_tr)
            )
        )

        for row in q.all():
            payload = getattr(row, det_name) if (det_name and hasattr(row, det_name)) else None
            if payload in (None,"",[]):
                for alt in ["raw_json","raw","order_json","json"]:
                    if hasattr(row, alt):
                        payload = getattr(row, alt)
                        if payload not in (None,"",[]): break

            # ---- BRÜT ve İNDİRİM ----
            amount_gross   = _to_number(getattr(row, amt_name,  None), None) if (amt_name  and hasattr(row, amt_name))  else None
            discount_total = _to_number(getattr(row, disc_name, None), 0.0)  if (disc_name and hasattr(row, disc_name)) else 0.0
            amount_net     = None
            if amount_gross is not None:
                try:
                    amount_net = float(amount_gross) - float(discount_total or 0.0)
                except Exception:
                    amount_net = amount_gross

            # ---- KALEMLER ----
            items, total_qty = [], 0
            for it in _iter_items_once(payload) or []:
                bc = _pick_first(it, BARCODE_CANDS, None)
                qt = _to_number(_pick_first(it, ITEM_QTY_CANDS, 1), 0) or 0
                pr = _to_number(_pick_first(it, ITEM_PRICE_CANDS, None), None)
                if not bc or int(qt) <= 0: 
                    continue
                items.append({"bc": bc, "qty": int(qt), "price": pr})
                total_qty += int(qt)

            per_unit_net = (amount_net/float(total_qty)) if (amount_net is not None and total_qty>0) else None
            for it in items:
                line_amt_net = (per_unit_net*it["qty"]) if per_unit_net is not None else ((it["price"]*it["qty"]) if it["price"] is not None else None)
                add(it["bc"], it["qty"], line_amt_net)

    return qty_map, amt_map




def _count_orders_today_distinct():
    start_tr, end_tr = tr_today_bounds_sql()
    sources = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered]
    ids = set()
    for cls in sources:
        ts_col, _, _ = _col(cls, ORD_TS_CANDS, "ts")
        # details kolonu (order_id fallback için)
        det_name = None
        for n in ORD_DTL_CANDS:
            if hasattr(cls, n): det_name = n; break
        if ts_col is None:
            continue
        q = db.session.query(cls).filter(
            or_(
                and_(func.timezone('Europe/Istanbul', ts_col) >= start_tr,
                     func.timezone('Europe/Istanbul', ts_col) <  end_tr),
                and_(ts_col >= start_tr, ts_col < end_tr)  # ts_col tz'siz ise
            )
        )
        for row in q.all():
            payload = getattr(row, det_name) if (det_name and hasattr(row, det_name)) else None
            oid = _extract_order_id_from_row_or_payload(row, payload)
            if not oid:
                # içerik imzası fallback
                items = []
                for it in _iter_items_once(payload) or []:
                    bc = _pick_first(it, BARCODE_CANDS, None)
                    qt = _to_number(_pick_first(it, ITEM_QTY_CANDS, 1), 0) or 0
                    sz = _pick_first(it, ITEM_SIZE_CANDS, "")
                    if bc and int(qt) > 0:
                        items.append({"bc": bc, "qty": int(qt), "size": sz})
                oid = _content_signature(items, cls.__name__, getattr(row, "id", None))
            ids.add(str(oid))
    return len(ids)


def _build_cards_between(start_ist, end_ist):
    # 1) Veriyi topla (tarih aralığına göre)
    qty_map, amt_map = _collect_orders_between_strict(start_ist, end_ist)

    # 2) Ürün ve stok bilgilerini çek
    barcodes = set(qty_map.keys()) | set(amt_map.keys())
    pinfo = _fetch_product_info_for_barcodes(barcodes)
    sdict = _fetch_stock_for_barcodes(barcodes)

    # 3) Model-Renk → Beden bazında grupla
    grp, rep_image = {}, {}
    for bc in barcodes:
        qty = int(qty_map.get(bc, 0))
        amt = _to_number(amt_map.get(bc, None), None)
        info = pinfo.get(bc, {"model":"Bilinmiyor","renk":"Bilinmiyor","beden":"—","image":None})
        key = (info["model"], info["renk"])
        if key not in rep_image and info.get("image"):
            rep_image[key] = info["image"]
        d = grp.setdefault(key, {})
        b = info["beden"]
        rec = d.setdefault(b, {"siparis":0, "stok":0, "tutar":0.0, "tutarli_adet":0})
        rec["siparis"] += qty
        rec["stok"]    += int(sdict.get(bc, 0))
        if amt is not None:
            rec["tutar"]        += float(amt)
            rec["tutarli_adet"] += qty

    # 4) Kart listesi + toplam satış + ortalama
    now_tr = datetime.now(IST)
    hours = max(1.0, now_tr.hour + now_tr.minute/60.0)

    def _beden_key(b):
        try: return (0, float(str(b).replace(',','.')))
        except: return (1, str(b))

    kartlar, total_sold = [], 0
    for (model, renk), beden_map in grp.items():
        detay = []
        toplam_sip = 0
        toplam_stok = 0
        toplam_tutar = 0.0
        toplam_tutarli_adet = 0

        for beden in sorted(beden_map.keys(), key=_beden_key):
            s  = int(beden_map[beden]["siparis"])
            k  = int(beden_map[beden]["stok"])
            a  = float(beden_map[beden]["tutar"])
            qa = int(beden_map[beden]["tutarli_adet"])
            toplam_sip += s
            toplam_stok += k
            toplam_tutar += a
            toplam_tutarli_adet += qa
            detay.append({"beden": beden, "siparis": s, "stok": k})

        total_sold += toplam_sip
        ort_fiyat = (toplam_tutar / toplam_tutarli_adet) if toplam_tutarli_adet > 0 else 0.0

        kartlar.append({
            "model": model,
            "renk": renk,
            "image": rep_image.get((model, renk)),
            "toplam_siparis_bugun": toplam_sip,
            "toplam_stok": toplam_stok,
            "ortalama_fiyat": round(ort_fiyat, 2),
            "saatlik_hiz": round(toplam_sip / hours, 2),
            "dusuk_stok": toplam_stok < DUSUK_STOK_ESIK,
            "detay": detay
        })

    kartlar.sort(key=lambda k: (k["toplam_siparis_bugun"], k["toplam_stok"]), reverse=True)
    return kartlar, total_sold, qty_map, amt_map



def _want_group_by_barcode() -> bool:
    g = (request.args.get("group") or "").strip().lower()
    # default = MODEL grubu; sadece ?group=barcode|barkod gelirse barkod kartı
    return g in ("barcode", "barkod")

def _collect_returns_for_order_numbers(order_nos: set[str]):
    """
    Verilen order_number kümesi için iade satırlarını barkod bazında toplar.
    Döner: (ret_qty_map: {barcode: iade_adedi}, returned_order_nos: set(order_number))
    """
    ret_qty, returned_orders = {}, set()
    if not order_nos:
        _info("returns(for orders): empty order set"); 
        return ret_qty, returned_orders

    rows = (db.session.query(ReturnOrder.order_number,
                             ReturnProduct.barcode,
                             func.coalesce(func.sum(ReturnProduct.quantity), 0))
            .join(ReturnProduct, ReturnProduct.return_order_id == ReturnOrder.id)
            .filter(ReturnOrder.order_number.in_(list(order_nos)))
            .group_by(ReturnOrder.order_number, ReturnProduct.barcode)
            .all())

    for ord_no, bc, q in rows:
        if not bc or not q: 
            continue
        bc_s = str(bc).strip()
        ret_qty[bc_s] = ret_qty.get(bc_s, 0) + int(q or 0)
        returned_orders.add(str(ord_no))

    _info("returns(for orders): done", orders=len(order_nos), returned=len(returned_orders), uniq=len(ret_qty))
    return ret_qty, returned_orders
