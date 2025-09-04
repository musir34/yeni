from flask import Blueprint, render_template, current_app
from sqlalchemy import func, cast, String, and_
from datetime import datetime
from zoneinfo import ZoneInfo
from models import db, CentralStock, OrderCreated, OrderPicking, OrderShipped, Return, Degisim
try:
    from models import OrderDelivered
except ImportError:
    from models import orders_delivered as OrderDelivered

# --- JSON & satır okuma helper'ları ---
import json

# ── Ayarlar
LIVE_REFRESH_SECONDS = 150  # 2,5 dk. İstersen 120-180 arası ver
USE_MONTH_WINDOW = False    # True yaparsan sadece içinde bulunulan ayı sayar

# --- Görünüm ---
home_bp = Blueprint("home", __name__)
IST = ZoneInfo("Europe/Istanbul")
ASSUME_DB_UTC = True  # DB timestamp'ları UTC ise True kalsın, yerel tutuluyorsa False yap

# Kolon adayları
ID_CANDS   = ["order_number", "order_id", "id"]
DATE_CANDS = ["order_date", "created_at", "created", "ts", "created_ts", "create_date_time", "delivered_at"]
AMT_CANDS  = ["amount", "total_amount", "order_amount", "grand_total", "total", "sum", "paid_amount", "payablePrice", "totalPrice"]
DISC_CANDS = ["discount", "order_discount", "discount_amount", "indirim", "indirim_tutari"]

# Satır anahtarları
ITEM_QTY_CANDS   = ["quantity","qty","adet","miktar","count","units","piece","quantityOrdered"]
ITEM_PRICE_CANDS = ["payablePrice","payable_price","totalPrice","total_price",
                    "unitPrice","unit_price","price","salePrice","sale_price",
                    "lineTotal","line_total","lineNet","line_total_net"]


@home_bp.route("/", endpoint="home")
@home_bp.route("/home", endpoint="home")
@home_bp.route("/anasayfa", endpoint="home")
def index():
    # Toplam stok
    toplam_stok = db.session.query(func.sum(CentralStock.qty)).scalar() or 0

    # Ay aralığı (IST)
    now = datetime.now(IST)
    ay_basi, sonraki_ay = _month_range_ist(now)

    # **GÜN aralığı (IST)**
    gun_basi = datetime(now.year, now.month, now.day, tzinfo=IST)
    gun_sonu = datetime(now.year, now.month, now.day, tzinfo=IST).replace(hour=23, minute=59, second=59, microsecond=999000)

    # 1) Birleşik sipariş kümesi
    best_rows = _collect_month_orders_unified(ay_basi, sonraki_ay)

    # 2) Toplam sipariş
    aylik_toplam_siparis = len(best_rows)

    # 3) Ortalama sipariş tutarı
    ortalama_siparis_tutari, _total_net, _order_cnt = _monthly_aov_from_unified_rows(best_rows)

    # Created ve Picking sayıları
    created_count = db.session.query(func.count()).select_from(OrderCreated).scalar() or 0
    picking_count = db.session.query(func.count()).select_from(OrderPicking).scalar() or 0

    # İadeler (ilgili ay)
    iade_adedi = (
        db.session.query(func.coalesce(func.sum(Return.quantity), 0))
        .filter(Return.create_date >= ay_basi, Return.create_date < sonraki_ay)
        .scalar()
    )

    # **DEĞİŞİM: Günlük ve Aylık**
    degisim_gunluk = (
        db.session.query(func.count(Degisim.id))
        .filter(_ist_between(Degisim.degisim_tarihi, gun_basi, gun_sonu))
        .scalar()
    ) or 0

    degisim_aylik = (
        db.session.query(func.count(Degisim.id))
        .filter(_ist_between(Degisim.degisim_tarihi, ay_basi, sonraki_ay))
        .scalar()
    ) or 0

    stats = {
        "toplam_siparis": aylik_toplam_siparis,
        "created": created_count,
        "picking": picking_count,
        "hazirlanan": 0,
        "iade": iade_adedi,
        "kritik_stok": 0,
        # ↓ yeni alanlar
        "degisim_gunluk": degisim_gunluk,
        "degisim_aylik": degisim_aylik,
    }

    return render_template(
        "home.html",
        stats=stats,
        toplam_stok=toplam_stok,
        ay_adi=["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"][now.month-1],
        ortalama_siparis_tutari=ortalama_siparis_tutari
    )



def _json_parse(obj):
    if isinstance(obj, (dict, list)): return obj
    if isinstance(obj, str):
        try: return json.loads(obj)
        except Exception: return None
    return None

def _pick_first(d, keys, default=None):
    if not isinstance(d, dict): return default
    for k in keys:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return default

def _to_number(x, default=None):
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

def _iter_items_once(blob):
    root = _json_parse(blob)
    if root is None: 
        return
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


def _pick_col(Model, names):
    for n in names:
        c = getattr(Model, n, None)
        if c is not None:
            return c
    raise AttributeError(f"{Model.__name__}: beklenen kolon yok -> {names}")

def _month_range_ist(now):
    start = datetime(now.year, now.month, 1, tzinfo=IST)
    end   = datetime(now.year + (now.month == 12), (now.month % 12) + 1, 1, tzinfo=IST)
    return start, end

def _ist_between(ts_col, start_ist, end_ist):
    if ASSUME_DB_UTC:
        loc = func.timezone('Europe/Istanbul', ts_col)
        return and_(loc >= start_ist, loc < end_ist)
    else:
        return and_(ts_col >= start_ist, ts_col < end_ist)

def _ids_in_month(Model, start_ist, end_ist):
    id_col   = _pick_col(Model, ID_CANDS)
    date_col = _pick_col(Model, DATE_CANDS)
    q = (
        db.session.query(cast(id_col, String))
        .filter(_ist_between(date_col, start_ist, end_ist))
        .distinct()
    )
    return {r[0] for r in q.all()}


def _collect_month_orders_unified(start_ist, end_ist):
    """
    [start,end) IST penceresinde 4 tabloda görünen siparişleri TEK kümeye indirger.
    Öncelik: Delivered > Shipped > Picking > Created. (İlk gören kazanır)
    DÖNÜŞ: dict[order_id] = row
    """
    priority = [OrderDelivered, OrderShipped, OrderPicking, OrderCreated]
    best = {}
    for M in priority:
        try:
            id_col   = _pick_col(M, ID_CANDS)
            date_col = _pick_col(M, DATE_CANDS)
        except Exception:
            continue
        rows = db.session.query(M).filter(_ist_between(date_col, start_ist, end_ist)).all()
        for r in rows:
            oid = (getattr(r, str(id_col).split(".")[-1], None)
                   or getattr(r, "order_number", None)
                   or getattr(r, "order_id", None)
                   or getattr(r, "id", None))
            if oid is None:
                continue
            oid = str(oid)
            if oid not in best:
                best[oid] = r
    return best


def _monthly_aov_from_unified_rows(best_rows: dict):
    """
    Panel mantığı:
      - Satırda fiyat varsa: sum(line_price * qty)
      - Yoksa: amount - discount  (kargo/kupon düşmeyiz; panelle bire bir)
    DÖNÜŞ: (avg_net, total_net, order_count)
    """
    total_net = 0.0
    order_count = 0

    for r in best_rows.values():
        # details
        details = None
        for k in ("details","items","lines","order_lines","orderItems","raw_json","order_json","json"):
            if hasattr(r, k):
                details = getattr(r, k)
                if details not in (None, "", []):
                    break

        # satırdan hesap
        any_price = False
        sum_from_lines = 0.0
        for it in _iter_items_once(details) or []:
            qty = int(_to_number(_pick_first(it, ITEM_QTY_CANDS, 1), 1) or 1)
            pr  = _to_number(_pick_first(it, ITEM_PRICE_CANDS, None), None)
            if qty <= 0:
                continue
            if pr is not None:
                any_price = True
                sum_from_lines += float(pr) * float(qty)

        if any_price:
            order_net = sum_from_lines
        else:
            # fallback: amount - discount
            amount = None
            for n in AMT_CANDS:
                if hasattr(r, n) and getattr(r, n) is not None:
                    amount = getattr(r, n); break
            discount = 0.0
            for n in ("discount","order_discount","discount_amount","totalDiscount","total_discount",
                      "indirim","indirim_tutari"):
                if hasattr(r, n) and getattr(r, n) is not None:
                    discount = getattr(r, n); break
            amt_f  = _to_number(amount, None)
            disc_f = _to_number(discount, 0.0) or 0.0
            order_net = (float(amt_f) - float(disc_f)) if amt_f is not None else None

        if order_net is not None:
            total_net += float(order_net)
            order_count += 1

    avg_net = (total_net / order_count) if order_count > 0 else 0.0
    return avg_net, total_net, order_count




def _monthly_aov_like_panel(start_ist, end_ist):
    """
    Panel ile aynı NET hesap:
      - order_net = sum(line.price*qty)  (satır fiyatı varsa)
      - aksi halde order_net = amount - discount  (kargo/kupon düşülmez)
    Öncelik: Delivered > Shipped > Picking > Created
    DÖNÜŞ: float (avg)
    """
    sources = [OrderDelivered, OrderShipped, OrderPicking, OrderCreated]
    seen_orders = set()
    total_net = 0.0
    order_count = 0

    for M in sources:
        try:
            id_col   = _pick_col(M, ID_CANDS)
            date_col = _pick_col(M, DATE_CANDS)
        except Exception:
            continue

        rows = db.session.query(M).filter(_ist_between(date_col, start_ist, end_ist)).all()
        for r in rows:
            oid = (getattr(r, str(id_col).split(".")[-1], None)
                   or getattr(r, "order_number", None)
                   or getattr(r, "order_id", None)
                   or getattr(r, "id", None))
            oid = str(oid) if oid is not None else None
            if not oid or oid in seen_orders:
                continue

            # Satırları oku
            details = None
            for k in ("details","items","lines","order_lines","orderItems","raw_json","order_json","json"):
                if hasattr(r, k):
                    details = getattr(r, k)
                    if details not in (None, "", []): break

            items = []
            any_price = False
            total_qty = 0
            sum_from_lines = 0.0

            for it in _iter_items_once(details) or []:
                qty = int(_to_number(_pick_first(it, ITEM_QTY_CANDS, 1), 1) or 1)
                pr  = _to_number(_pick_first(it, ITEM_PRICE_CANDS, None), None)
                if qty <= 0: 
                    continue
                total_qty += qty
                if pr is not None:
                    any_price = True
                    sum_from_lines += float(pr) * float(qty)

            if any_price:
                order_net = sum_from_lines
            else:
                # Satırdan fiyat yoksa amount - discount
                amount = None
                for n in AMT_CANDS:
                    if hasattr(r, n) and getattr(r, n) is not None:
                        amount = getattr(r, n); break
                discount = 0.0
                for n in ("discount","order_discount","discount_amount","totalDiscount","total_discount","indirim","indirim_tutari"):
                    if hasattr(r, n) and getattr(r, n) is not None:
                        discount = getattr(r, n); break
                amt_f  = _to_number(amount, None)
                disc_f = _to_number(discount, 0.0) or 0.0
                order_net = (float(amt_f) - float(disc_f)) if amt_f is not None else None

            if order_net is not None:
                total_net += float(order_net)
                order_count += 1
                seen_orders.add(oid)

    return (total_net / order_count) if order_count > 0 else 0.0


def _collect_month_orders_unified(start_ist, end_ist):
    """
    [start,end) IST penceresinde 4 tabloda görünen siparişleri TEK kümeye indirger.
    Her order_id için statü önceliği: Delivered > Shipped > Picking > Created.
    DÖNÜŞ: dict[order_id] = row (seçilen tablo kaydı)
    """
    priority = [("Delivered", OrderDelivered),
                ("Shipped",   OrderShipped),
                ("Picking",   OrderPicking),
                ("Created",   OrderCreated)]
    best = {}  # oid -> row
    for _, M in priority:
        try:
            id_col   = _pick_col(M, ID_CANDS)
            date_col = _pick_col(M, DATE_CANDS)
        except Exception:
            continue
        rows = db.session.query(M).filter(_ist_between(date_col, start_ist, end_ist)).all()
        for r in rows:
            oid = (getattr(r, str(id_col).split(".")[-1], None)
                   or getattr(r, "order_number", None)
                   or getattr(r, "order_id", None)
                   or getattr(r, "id", None))
            if oid is None: 
                continue
            oid = str(oid)
            # daha yüksek öncelikli tablo şimdiki turda; önce gelen kazanır
            if oid not in best:
                best[oid] = r
    return best  # birleştirilmiş ve önceliklenmiş tek küme


def _status_counts_now():
    """
    Created ve Picking adetlerini döner.
    USE_MONTH_WINDOW=True ise içinde bulunulan ay penceresinde sayar.
    """
    if USE_MONTH_WINDOW:
        now = datetime.now(IST)
        start_ist, end_ist = _month_range_ist(now)

        def _count_in_window(Model):
            date_col = _pick_col(Model, DATE_CANDS)
            return (
                db.session.query(func.count())
                .select_from(Model)
                .filter(_ist_between(date_col, start_ist, end_ist))
                .scalar()
            ) or 0
        created = _count_in_window(OrderCreated)
        picking = _count_in_window(OrderPicking)
    else:
        created = (db.session.query(func.count()).select_from(OrderCreated).scalar() or 0)
        picking = (db.session.query(func.count()).select_from(OrderPicking).scalar() or 0)

    return {"created": int(created), "picking": int(picking)}


@home_bp.route("/api/home/status-counts")
def api_status_counts():
    """AJAX/Fetch için hafif JSON endpoint."""
    return _status_counts_now()