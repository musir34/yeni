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

# --- Hava Durumu Servisi ---
from weather_service import get_weather_info, get_istanbul_time

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
    # WooCommerce modelini import et
    from woocommerce_site.models import WooOrder
    
    # Toplam stok
    toplam_stok = db.session.query(func.sum(CentralStock.qty)).scalar() or 0

    # Hava durumu bilgisi
    weather_info = get_weather_info()

    # Ay aralığı (IST) - İstanbul saati
    now = get_istanbul_time()
    ay_basi, sonraki_ay = _month_range_ist(now)

    # **GÜN aralığı (IST)**
    gun_basi = datetime(now.year, now.month, now.day, tzinfo=IST)
    gun_sonu = datetime(now.year, now.month, now.day, tzinfo=IST).replace(hour=23, minute=59, second=59, microsecond=999000)

    # 1) Birleşik sipariş kümesi (CANLI PANEL MANTIĞIyla) - Trendyol
    best_rows = _collect_month_orders_unified(ay_basi, sonraki_ay)

    # 2) Toplam sipariş sayısı (benzersiz order_id) - Trendyol
    aylik_trendyol_siparis = len(best_rows)
    
    # 🛒 WooCommerce siparişlerini say (aylık)
    aylik_woo_siparis = (
        db.session.query(func.count(WooOrder.id))
        .filter(_ist_between(WooOrder.date_created, ay_basi, sonraki_ay))
        .scalar()
    ) or 0
    
    # Toplam sipariş = Trendyol + WooCommerce
    aylik_toplam_siparis = aylik_trendyol_siparis + aylik_woo_siparis

    # 3) Ortalama sipariş tutarı (CANLI PANEL MANTIĞIyla - sipariş başına NET)
    # avg_per_order, total_net_ciro, order_count
    ortalama_siparis_tutari, toplam_ciro, siparis_sayisi = _monthly_aov_from_unified_rows(best_rows)

    # Created ve Picking sayıları - Trendyol
    created_count = db.session.query(func.count()).select_from(OrderCreated).scalar() or 0
    picking_count = db.session.query(func.count()).select_from(OrderPicking).scalar() or 0
    
    # 🛒 WooCommerce siparişlerini say (on-hold = beklemede)
    woo_onhold_count = (
        db.session.query(func.count(WooOrder.id))
        .filter(WooOrder.status == 'on-hold')
        .scalar()
    ) or 0
    
    # 🛒 WooCommerce siparişlerini say (processing = işlemde)
    woo_processing_count = (
        db.session.query(func.count(WooOrder.id))
        .filter(WooOrder.status == 'processing')
        .scalar()
    ) or 0

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
        "trendyol_siparis": aylik_trendyol_siparis,  # 🔥 Yeni: Trendyol ayrı
        "woo_siparis": aylik_woo_siparis,            # 🔥 Yeni: WooCommerce ayrı
        "created": created_count,
        "picking": picking_count,
        "woo_onhold": woo_onhold_count,              # 🔥 Yeni: WooCommerce beklemede
        "woo_processing": woo_processing_count,      # 🔥 Yeni: WooCommerce işlemde
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
        ortalama_siparis_tutari=ortalama_siparis_tutari,
        weather=weather_info,
        current_time=now
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


def _monthly_aov_from_unified_rows(best_rows: dict):
    """
    CANLI PANEL ile BİREBİR AYNI MANTIK:
    Canlı paneldeki _collect_orders_between_strict fonksiyonunun TAMAMEN aynısı.
    
    1. Her sipariş için BARCODE bazında qty ve NET tutar toplar
    2. BARCODE bazında: toplam_net_tutar / toplam_qty = ortalama birim fiyat
    3. Sonuç: ÜRÜN BAŞINA ortalama fiyat (sipariş başına değil!)
    
    DÖNÜŞ: (ortalama_birim_fiyat, toplam_net_ciro, toplam_adet)
    """
    # BARCODE bazında toplama (canlı paneldeki qty_map ve net_map mantığı)
    qty_map = {}  # barcode -> toplam qty
    net_map = {}  # barcode -> toplam NET tutar

    for r in best_rows.values():
        # ---- DETAILS ----
        details = None
        for k in ("details","items","lines","order_lines","orderItems","raw_json","order_json","json"):
            if hasattr(r, k):
                details = getattr(r, k)
                if details not in (None, "", []):
                    break
        
        # Alternatif details kolonları
        if details in (None, "", []):
            for alt in ["raw_json","raw","order_json","json"]:
                if hasattr(r, alt):
                    details = getattr(r, alt)
                    if details not in (None, "", []):
                        break

        # ---- BRÜT TUTAR ----
        amount_gross = None
        for n in AMT_CANDS:
            if hasattr(r, n) and getattr(r, n) is not None:
                amount_gross = getattr(r, n)
                break
        
        # ---- İNDİRİM ----
        discount_total = 0.0
        for n in DISC_CANDS:
            if hasattr(r, n) and getattr(r, n) is not None:
                discount_total = getattr(r, n)
                break
        
        # Sayıya çevir
        amount_gross_val = _to_number(amount_gross, None)
        discount_val = _to_number(discount_total, 0.0) or 0.0
        
        # NET tutar hesabı
        amount_net = None
        if amount_gross_val is not None:
            try:
                amount_net = float(amount_gross_val) - float(discount_val)
            except Exception:
                amount_net = amount_gross_val

        # ---- KALEMLER ----
        items = []
        total_qty = 0
        for it in _iter_items_once(details) or []:
            bc = _pick_first(it, ["barcode","barkod","sku"], None)
            qt = _to_number(_pick_first(it, ITEM_QTY_CANDS, 1), 0) or 0
            pr = _to_number(_pick_first(it, ITEM_PRICE_CANDS, None), None)
            if not bc or int(qt) <= 0:
                continue
            items.append({"bc": bc, "qty": int(qt), "price": pr})
            total_qty += int(qt)

        # ---- NET PAYLAŞIM (paneldeki mantık BİREBİR) ----
        per_unit_net = (amount_net / float(total_qty)) if (amount_net is not None and total_qty > 0) else None
        
        # BARCODE bazında topla (paneldeki add() fonksiyonu mantığı)
        for it in items:
            bc = it["bc"]
            qt = it["qty"]
            
            # Paneldeki mantık: öncelik per_unit_net, fallback satır fiyatı
            line_amt_net = (per_unit_net * qt) if per_unit_net is not None else (
                (it["price"] * qt) if it["price"] is not None else None
            )
            
            # BARCODE bazında topla
            bc_str = str(bc).strip()
            qty_map[bc_str] = qty_map.get(bc_str, 0) + qt
            if line_amt_net is not None:
                net_map[bc_str] = net_map.get(bc_str, 0.0) + float(line_amt_net)

    # TOPLAM NET CIRO ve TOPLAM ADET (paneldeki toplam_net_tutar_all ve toplam_adet_all)
    toplam_net_tutar = 0.0
    toplam_adet = 0
    
    for bc in qty_map.keys():
        qty = qty_map.get(bc, 0)
        net = net_map.get(bc, 0.0)
        
        if net > 0 and qty > 0:  # Paneldeki "if net is not None and sat > 0" mantığı
            toplam_net_tutar += float(net)
            toplam_adet += int(qty)
    
    # ÜRÜN BAŞINA ORTALAMA (canlı paneldeki genel_ortalama_fiyat)
    ortalama_birim_fiyat = (toplam_net_tutar / toplam_adet) if toplam_adet > 0 else 0.0
    
    return round(ortalama_birim_fiyat, 2), round(toplam_net_tutar, 2), toplam_adet




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