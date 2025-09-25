# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify, render_template, current_app
from sqlalchemy import func, literal, text
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
import json, hashlib, os, re, time
from sqlalchemy.inspection import inspect as sqla_inspect
from sqlalchemy import text

from dotenv import load_dotenv
load_dotenv()

# ------------------ Modeller ------------------
from models import (
    db,
    Product, CentralStock,
    UretimOneriDefaults, UretimPlan, UretimOneriWatch,
    OrderCreated, OrderPicking, OrderShipped,
)
try:
    from models import OrderDelivered
except Exception:
    from models import orders_delivered as OrderDelivered

# Daily cache modelleri (models.py'ye ekledin)
from models import DailySales, DailySalesStatus

# ------------------ OpenAI / Prophet ------------------
from openai import OpenAI

# NumPy 2 uyumluluk (Prophet için)
import numpy as np
if not hasattr(np, "float_"): np.float_ = np.float64
if not hasattr(np, "int_"):   np.int_   = np.int64

try:
    from prophet import Prophet  # cmdstanpy backend ile
except Exception:
    Prophet = None

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Basit AI cache (1 saat)
_AI_CACHE = {}
_AI_TTL_SEC = 3600

# ------------------------------------------------------------------------------
# Blueprint
# ------------------------------------------------------------------------------
uretim_oneri_bp = Blueprint("uretim_oneri", __name__)
IST = ZoneInfo("Europe/Istanbul")

# ------------------------------------------------------------------------------
# Esnek okuyucu (eski sistem yardımcıları gerektiği kadar duruyor)
# ------------------------------------------------------------------------------
ORD_TS_CANDS = [
    "order_date", "delivered_at",
    "created_at","created","order_created_at","timestamp",
    "createdDate","create_date_time","date","olusturma_tarihi","shipped_at"
]
ORD_DTL_CANDS  = ["details","items","lines","order_lines","orderItems","kalemler","urunler","json_items","raw_json"]
ORD_AMT_CANDS  = ["amount","total_amount","order_amount","grand_total","total","line_total","price_total","sum","paid_amount"]
ORD_DISC_CANDS = ["discount","order_discount","discount_amount","indirim","indirim_tutari"]
ORD_ID_CANDS   = ["order_number","orderNumber","orderNo","order_id","orderId","trendyol_order_id","platform_order_id"]
BARCODE_CANDS  = ["barcode","barkod","urun_barkod","product_barcode","productBarcode","sku","stock_code","stok_kodu","gtin","ean","ean13","upc","model_barcode"]
ITEM_QTY_CANDS = ["quantity","qty","adet","miktar","count","units","piece","quantityOrdered","adet_sayisi"]

def _json_parse(x):
    if isinstance(x, (dict, list)): return x
    if isinstance(x, str):
        try: return json.loads(x)
        except: return None
    return None

def _pick(d, keys, default=None):
    if not isinstance(d, dict): return default
    for k in keys:
        if k in d and d[k] not in (None, "", []): return d[k]
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

def _to_list(val):
    if val is None: return []
    if isinstance(val, list): return [str(x).strip() for x in val if str(x).strip()]
    s = str(val).strip()
    if not s: return []
    if s.startswith("[") and s.endswith("]"):
        try: return [str(x).strip() for x in json.loads(s) if str(x).strip()]
        except: pass
    return [x.strip() for x in s.split(",") if x.strip()]

def _col(model_cls, candidates, label=None):
    for name in candidates:
        col = getattr(model_cls, name, None)
        if col is not None:
            return col, (col.label(label) if label else col), name
    return None, (literal(None).label(label) if label else None), None

def _iter_items_once(blob):
    root = _json_parse(blob)
    if root is None: return
    if isinstance(root, list):
        for it in root:
            if isinstance(it, dict): yield it
        return
    if isinstance(root, dict):
        for key in ORD_DTL_CANDS:
            arr = root.get(key)
            if isinstance(arr, list):
                for it in arr:
                    if isinstance(it, dict): yield it
                return
        for v in root.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                for it in v: yield it
                return

# ------------------------------------------------------------------------------
# Product / CentralStock kolon bağlama
# ------------------------------------------------------------------------------
_BAR_CANDS2 = ["barcode","barkod","product_barcode","productBarcode","sku","gtin","ean","stock_code","model_barcode"]
_MOD_CANDS2 = ["product_main_id","model","model_code"]
_CLR_CANDS2 = ["color","renk","colour","color_name"]
_SZ_CANDS2  = ["size","beden","number","numara","shoe_size","beden_no"]
_IMG_CANDS2 = ["image_url","image","image1","main_image","cover_image","images","image_urls","img","photo","thumb_url","primary_image"]
_QTY_CANDS2 = ["quantity","qty","adet","available","stock","onhand","miktar","mevcut"]

P_BAR = P_MOD = P_CLR = P_SZ = P_IMG = None
C_BAR = C_QTY = None

def _bind_columns_once():
    global P_BAR, P_MOD, P_CLR, P_SZ, P_IMG, C_BAR, C_QTY
    if P_BAR is not None: return
    P_BAR,_,_ = _col(Product,      _BAR_CANDS2, "barcode")
    P_MOD,_,_ = _col(Product,      _MOD_CANDS2, "model")
    P_CLR,_,_ = _col(Product,      _CLR_CANDS2, "renk")
    P_SZ, _,_ = _col(Product,      _SZ_CANDS2,  "beden")
    P_IMG,_,_ = _col(Product,      _IMG_CANDS2, "image")
    C_BAR,_,_ = _col(CentralStock, _BAR_CANDS2, "barcode")
    C_QTY,_,_ = _col(CentralStock, _QTY_CANDS2, "qty")
    if P_BAR is None or C_BAR is None:
        raise RuntimeError("Barcode kolonları bulunamadı (Product/CentralStock).")

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

# ------------------------------------------------------------------------------
# DailySales: upsert & incremental update (webhooklardan çağır)
# ------------------------------------------------------------------------------
def upsert_daily_sales(barcode: str, d: date, delta: int):
    sql = text("""
        INSERT INTO daily_sales (barcode, date, qty)
        VALUES (:bc, :dt, :dq)
        ON CONFLICT (barcode, date)
        DO UPDATE SET qty = daily_sales.qty + EXCLUDED.qty
    """)
    db.session.execute(sql, {"bc": str(barcode).strip(), "dt": d, "dq": int(delta)})
    # qty negatif olur ise 0'a sabitle (opsiyonel güvenlik)
    db.session.execute(text("""
        UPDATE daily_sales SET qty = 0
        WHERE barcode = :bc AND date = :dt AND qty < 0
    """), {"bc": str(barcode).strip(), "dt": d})

def update_daily_from_event(event_type: str, ts: datetime, items: list):
    """
    event_type: 'create' | 'cancel' | 'return'
    ts: event timestamp (Europe/Istanbul tavsiye)
    items: [{'barcode': '...', 'quantity': 2}, ...]
    """
    sign = 1 if event_type == "create" else -1
    d = (ts.astimezone(IST) if ts.tzinfo else ts.replace(tzinfo=IST)).date()
    for it in items or []:
        bc = str(it.get("barcode") or "").strip()
        q  = int(it.get("quantity", 1) or 1)
        if not bc or q <= 0: continue
        upsert_daily_sales(bc, d, sign * q)
    db.session.commit()

# ------------------------------------------------------------------------------
# DailySales: toplu yeniden kur (gece güvenlik senkronu)
# ------------------------------------------------------------------------------
def rebuild_daily_sales(days: int = 30):
    """
    Geçmiş 'days' gününü baştan hesaplar ve o aralığı daily_sales'ta yeniler.
    Progress için DailySalesStatus güncellenir.
    """
    end_ist = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    start_ist = end_ist - timedelta(days=days)
    total_days = days
    # status row (tek satır mantığı)
    st = DailySalesStatus.query.order_by(DailySalesStatus.id.asc()).first()
    if not st:
        st = DailySalesStatus(status="idle", processed_days=0, total_days=0)
        db.session.add(st); db.session.commit()

    st.last_run_start = datetime.now(IST)
    st.status = "running"
    st.processed_days = 0
    st.total_days = total_days
    st.updated_at = datetime.now(IST)
    db.session.commit()

    # seçilen aralığı temizle
    cutoff = (end_ist.date() - timedelta(days=days))
    db.session.query(DailySales).filter(DailySales.date >= cutoff).delete()
    db.session.flush()

    # gün gün ilerle (hafif RAM tüketimi)
    for i in range(days):
        day_start = (start_ist + timedelta(days=i))
        day_end   = day_start + timedelta(days=1)
        bucket = {}  # barcode -> qty

        def _scan(cls):
            ts_col, _, TS = _col(cls, ORD_TS_CANDS, "ts")
            if ts_col is None: return
            det_name = next((n for n in ORD_DTL_CANDS if hasattr(cls, n)), None)
            q = db.session.query(cls).filter(
                func.timezone('Europe/Istanbul', ts_col) >= day_start,
                func.timezone('Europe/Istanbul', ts_col) <  day_end
            )
            for row in q:
                payload = getattr(row, det_name) if (det_name and hasattr(row, det_name)) else None
                ts_val = getattr(row, TS, None)
                if not ts_val: continue
                for it in _iter_items_once(payload) or []:
                    bc = _pick(it, BARCODE_CANDS)
                    qt = int(_to_number(_pick(it, ITEM_QTY_CANDS, 0), 0) or 0)
                    if not bc or qt <= 0: continue
                    s = str(bc).strip()
                    bucket[s] = bucket.get(s, 0) + qt

        for cls in (OrderCreated, OrderPicking, OrderShipped, OrderDelivered):
            _scan(cls)

        if bucket:
            rows = [DailySales(barcode=bc, date=day_start.date(), qty=qty) for bc, qty in bucket.items()]
            db.session.bulk_save_objects(rows)
            db.session.flush()

        # progress
        st.processed_days = i + 1
        st.updated_at = datetime.now(IST)
        db.session.commit()

    st.last_run_end = datetime.now(IST)
    st.status = "done"
    st.updated_at = datetime.now(IST)
    db.session.commit()

# ------------------------------------------------------------------------------
# DailySales: hızlı okuma yardımcıları
# ------------------------------------------------------------------------------
def _daily_series_from_cache(bc: str, days: int, end_day: date):
    start_day = end_day - timedelta(days=days - 1)
    rows = (db.session.query(DailySales.date, DailySales.qty)
            .filter(
                DailySales.barcode == str(bc).strip(),
                DailySales.date >= start_day,
                DailySales.date <= end_day
            ).all())
    by_day = {d.isoformat(): int(q or 0) for d, q in rows}
    series, cur = [], start_day
    for _ in range(days):
        iso = cur.isoformat()
        series.append({"date": iso, "qty": by_day.get(iso, 0)})
        cur += timedelta(days=1)
    return series

def _fetch_sales_totals_from_cache(barcodes, start_day: date, end_day: date):
    if not barcodes: return {}
    rows = (db.session.query(DailySales.barcode, func.coalesce(func.sum(DailySales.qty), 0))
            .filter(DailySales.barcode.in_(list(barcodes)),
                    DailySales.date >= start_day,
                    DailySales.date <= end_day)
            .group_by(DailySales.barcode).all())
    return {str(b): int(s or 0) for b, s in rows}

def _moving_average(series, window):
    if not series: return 0.0
    qty = [int(x.get("qty",0) or 0) for x in series][-window:]
    return (sum(qty) / float(window)) if window > 0 else 0.0

# ------------------------------------------------------------------------------
# AI / Prophet tahminleyiciler
# ------------------------------------------------------------------------------
def ai_forecast_sales(barcode, sales_series, horizon=14):
    if not openai_client:
        return None
    prompt = f"""
    Sen bir satış analisti gibi davran.
    Elinde aşağıdaki günlük satış serisi var (JSON formatında):
    {sales_series}
    Bu ürünün (barkod: {barcode}) önümüzdeki {horizon} gün için beklenen günlük satış ortalamasını tahmin et.
    Lütfen sadece bir sayı döndür (örn: 12.3) başka açıklama yazma.
    """
    try:
        key = (str(barcode), str(sales_series[0]["date"] if sales_series else ""), str(sales_series[-1]["date"] if sales_series else ""), int(horizon), hash(json.dumps(sales_series, sort_keys=True)))
        now_ts = time.time()
        hit = _AI_CACHE.get(key)
        if hit and (now_ts - hit[0] <= _AI_TTL_SEC):
            return hit[1]
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.choices[0].message.content.strip()
        m = re.search(r"[-+]?\d*\.?\d+", raw)
        if m:
            val = float(m.group())
            _AI_CACHE[key] = (now_ts, val)
            return val
        return None
    except Exception as e:
        try: current_app.logger.warning(f"AI forecast hata: {e}")
        except Exception: pass
        return None

def prophet_forecast(series, horizon_days):
    if not Prophet:
        return None
    try:
        import pandas as pd
        df = pd.DataFrame([{"ds": s["date"], "y": float(s["qty"])} for s in series])
        if df.empty:
            return None
        m = Prophet(daily_seasonality=True, weekly_seasonality=True, yearly_seasonality=False)
        m.fit(df)
        future = m.make_future_dataframe(periods=horizon_days, freq="D", include_history=False)
        fcst = m.predict(future)
        yhat_mean = float(fcst["yhat"].mean())
        return max(0.0, yhat_mean)
    except Exception as e:
        try: current_app.logger.warning(f"Prophet fallback (hata: {e})")
        except Exception: pass
        return None

# ------------------------------------------------------------------------------
# Genel yardımcılar
# ------------------------------------------------------------------------------
def _expand_barcodes_for_models(model_ids):
    _bind_columns_once()
    if not model_ids: return set()
    rows = db.session.query(P_BAR).filter(P_MOD.in_(model_ids)).all()
    return {str(r[0]).strip() for r in rows if r and r[0]}

def _fetch_product_info_for_barcodes(barcodes):
    _bind_columns_once()
    if not barcodes: return {}
    cols = [P_BAR, P_MOD, P_CLR, P_SZ]
    if P_IMG is not None: cols.append(P_IMG)
    rows = db.session.query(*cols).filter(P_BAR.in_(list(barcodes))).all()
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
    _bind_columns_once()
    if not barcodes: return {}
    if C_QTY is None: return {str(b).strip(): 0 for b in barcodes}
    rows = (db.session.query(C_BAR, func.coalesce(func.sum(C_QTY), 0))
            .filter(C_BAR.in_(list(barcodes)))
            .group_by(C_BAR).all())
    return {str(b).strip(): int(st or 0) for b, st in rows}

# ------------------------------------------------------------------------------
# Sayfalar
# ------------------------------------------------------------------------------
@uretim_oneri_bp.route("/uretim-oneri")
def uretim_oneri_page():
    return render_template("uretim_oneri.html")

@uretim_oneri_bp.route("/uretim-oneri-haftalik")
def uretim_oneri_haftalik_page():
    _bind_columns_once()
    return render_template("uretim_oneri_haftalik.html")

# ------------------------------------------------------------------------------
# DailySales status & rebuild
# ------------------------------------------------------------------------------
@uretim_oneri_bp.route("/api/daily-sales/status", methods=["GET"])
def daily_sales_status():
    st = DailySalesStatus.query.order_by(DailySalesStatus.id.asc()).first()
    if not st:
        return jsonify({"status":"idle","processed_days":0,"total_days":0,"updated_at":None,"last_run_start":None,"last_run_end":None})
    return jsonify({
        "status": st.status,
        "processed_days": st.processed_days,
        "total_days": st.total_days,
        "last_run_start": st.last_run_start.isoformat() if st.last_run_start else None,
        "last_run_end": st.last_run_end.isoformat() if st.last_run_end else None,
        "updated_at": st.updated_at.isoformat() if st.updated_at else None
    })

@uretim_oneri_bp.route("/api/daily-sales/rebuild", methods=["POST"])
def daily_sales_rebuild():
    days = int((request.get_json(silent=True) or {}).get("days") or request.args.get("days") or 30)
    rebuild_daily_sales(days=days)
    return jsonify({"ok": True, "days": days})

# ------------------------------------------------------------------------------
# Watchlist basit API (değişmedi)
# ------------------------------------------------------------------------------
@uretim_oneri_bp.route("/api/uretim-oneri/watchlist/toggle", methods=["POST"])
def toggle_watch():
    data = request.get_json(silent=True) or {}
    barcode = str(data.get("barcode", "")).strip()
    if not barcode: return jsonify({"ok": False, "error": "barcode boş"}), 400
    if len(barcode) > 64: barcode = barcode[:64]

    row = UretimOneriWatch.query.filter_by(product_barcode=barcode).first()
    if row:
        row.is_active = not bool(row.is_active)
        db.session.commit()
        return jsonify({"ok": True, "active": row.is_active})

    p = Product.query.get(barcode)
    row = UretimOneriWatch(
        product_barcode=barcode,
        product_main_id=(p.product_main_id if p else None),
    )
    db.session.add(row)
    db.session.commit()
    return jsonify({"ok": True, "active": True})

# ------------------------------------------------------------------------------
# Haftalık üretim önerisi – DailySales cache üzerinden ultra hızlı
# ------------------------------------------------------------------------------
@uretim_oneri_bp.route("/api/uretim-oneri-haftalik", methods=["GET","POST"])
def uretim_oneri_haftalik_api():
    """
    Hızlı: cache kullanır. Parametreler:
      - models: [...], days (7/14/30), min_cover_days, safety_factor, only_positive, target_qty
      - use_cache (default true), force_compute (default false)
      - quick, max_items, ai_max_items (fallback hesap yolu için)
    """
    _bind_columns_once()
    body = request.get_json(silent=True) or {}
    args = request.args

    model_ids       = _to_list(body.get("models") or args.get("models"))
    days            = int(body.get("days") or args.get("days") or 7)
    min_cover       = float(body.get("min_cover_days") or args.get("min_cover_days") or 14)
    safety_factor   = float(body.get("safety_factor") or args.get("safety_factor") or 0.10)
    only_positive   = str(body.get("only_positive") or args.get("only_positive") or "1").lower() in ("1","true","yes")
    target_qty      = int(body.get("target_qty") or args.get("target_qty") or 0)

    # cache kontrol
    use_cache       = str(body.get("use_cache") or args.get("use_cache") or "true").lower() in ("1","true","yes")
    force_compute   = str(body.get("force_compute") or args.get("force_compute") or "false").lower() in ("1","true","yes")

    # fallback hesap (gerekirse)
    use_ai          = str(body.get("use_ai") or args.get("use_ai") or "false").lower() in ("1","true","yes")
    use_prophet     = str(body.get("use_prophet") or args.get("use_prophet") or "false").lower() in ("1","true","yes")
    blend_weight_ai = float(body.get("blend_weight_ai") or args.get("blend_weight_ai") or 0.30)
    blend_weight_ai = max(0.0, min(1.0, blend_weight_ai))
    quick           = str(body.get("quick") or args.get("quick") or "1").lower() in ("1","true","yes")
    max_items       = int(body.get("max_items") or args.get("max_items") or 0)
    ai_max_items    = int(body.get("ai_max_items") or args.get("ai_max_items") or 0)

    if not model_ids:
        return jsonify({"ok": True, "days": days, "groups": [], "note": "models boş"}), 200

    now = datetime.now(IST)
    start_day = (now - timedelta(days=days - 1)).date()
    end_day   = now.date()

    # Seçili modellerin barkodları
    sel_barcodes = list(_expand_barcodes_for_models(model_ids))
    if not sel_barcodes:
        return jsonify({"ok": True, "days": days, "groups": []})

    # Satış toplamları (daily_sales'tan) sıralama için
    totals_map = _fetch_sales_totals_from_cache(sel_barcodes, start_day, end_day)
    sel_barcodes.sort(key=lambda b: int(totals_map.get(b, 0)), reverse=True)

    # stok + ürün info
    sdict = _fetch_stock_for_barcodes(sel_barcodes)
    pinfo = _fetch_product_info_for_barcodes(sel_barcodes)

    # ---- 1) CACHE'TEN ÇEK ----
    cache_map = {}
    if use_cache and not force_compute:
        try:
            from models import ForecastCache
            fc_rows = (db.session.query(ForecastCache)
                       .filter(ForecastCache.days == days,
                               ForecastCache.barcode.in_(sel_barcodes))
                       .all())
            for r in fc_rows:
                cache_map[r.barcode] = {
                    "avg_final":  float(r.avg_final),
                    "avg_base":   float(r.avg_base or 0.0),
                    "avg_prophet": (float(r.avg_prophet) if r.avg_prophet is not None else None),
                    "avg_ai_used":(float(r.avg_ai_used) if r.avg_ai_used is not None else None),
                }
        except Exception as e:
            current_app.logger.warning(f"FCACHE read fail: {e}")

    # Prophet/AI bucket (sadece cache yoksa ve force_compute=True ise anlamlı)
    prophet_bucket = set(sel_barcodes[:max_items]) if (use_prophet and not quick and (force_compute or not use_cache)) else set()
    ai_bucket      = set(sel_barcodes[:ai_max_items]) if (use_ai and not quick and (force_compute or not use_cache)) else set()

    rows = []
    for bc in sel_barcodes:
        # günlük seri (satış sütunları için lazım)
        series = _daily_series_from_cache(bc, days, end_day)
        sold = sum(int(r["qty"]) for r in series)

        # 1) cache varsa direk kullan
        if bc in cache_map and not force_compute:
            avg_final   = cache_map[bc]["avg_final"]
            avg_base    = cache_map[bc]["avg_base"]
            avg_prophet = cache_map[bc]["avg_prophet"]
            avg_ai_used = cache_map[bc]["avg_ai_used"]
        else:
            # 2) fallback: hızlı base (quick default), istenirse sınırlı Prophet/AI
            avg_base = _moving_average(series, days)
            if quick:
                avg_prophet = None
                avg_ai_used = None
                avg_final   = avg_base
            else:
                nonzero_days = sum(1 for r in series if (r.get("qty") or 0) > 0)
                use_prophet_local = (bc in prophet_bucket) and (nonzero_days >= 3) and (avg_base > 0 or sold > 0)
                avg_prophet = prophet_forecast(series, horizon_days=days) if use_prophet_local else None

                avg_ai_raw = ai_forecast_sales(bc, series, horizon=days) if (bc in ai_bucket) else None
                band_low  = max(0.1 * avg_base, 0.1)
                band_high = 5.0 * max(avg_base, 0.01)
                avg_ai_used = None if avg_ai_raw is None else min(max(avg_ai_raw, band_low), band_high)

                if avg_prophet is not None:
                    w_ai = blend_weight_ai if (avg_ai_used is not None) else 0.0
                    avg_final = (1.0 - w_ai) * avg_prophet + (w_ai * (avg_ai_used or 0.0))
                else:
                    avg_final = avg_base

        st = int(sdict.get(bc, 0))
        days_left = (st / avg_final) if avg_final > 0 else None
        target = max(0.0, (min_cover * avg_final) - st)
        suggest = int(round(target * (1 + safety_factor)))

        info = pinfo.get(bc, {"model":"Bilinmiyor","renk":"Bilinmiyor","beden":"—","image":None})
        rec = {
            "barcode": bc,
            "model": info["model"], "renk": info["renk"], "beden": info["beden"],
            "image": info.get("image"),
            "stok": st, "sold_last_days": int(sold),
            "avg_daily": round(avg_final, 3),
            "avg_base": round(avg_base, 3),
            "avg_prophet": (round(avg_prophet, 3) if avg_prophet is not None else None),
            "avg_ai_used": (round(avg_ai_used, 3) if avg_ai_used is not None else None),
            "avg_final": round(avg_final, 3),
            "blend_weight_ai": round(blend_weight_ai, 3),
            "days_left": (round(days_left, 1) if days_left is not None else None),
            "min_cover_days": min_cover, "safety_factor": safety_factor,
            "suggest_qty": max(suggest, 0),
        }
        if (not only_positive) or rec["suggest_qty"] > 0:
            rows.append(rec)

    # hedef toplam normalize
    if target_qty > 0 and rows:
        total = sum(r["suggest_qty"] for r in rows)
        if total > 0:
            scale = float(target_qty) / float(total)
            for r in rows:
                r["suggest_qty"] = max(0, int(round(r["suggest_qty"] * scale)))

    # model > renk grup
    groups_dict = {}
    for x in rows:
        key = x["model"] or "_UNGROUPED_"
        g = groups_dict.setdefault(key, {"model": key, "image": None, "colors": {}})
        if not g["image"] and x.get("image"): g["image"] = x["image"]
        ckey = x["renk"] or "Renk Yok"
        g["colors"].setdefault(ckey, []).append(x)

    groups = []
    for _, g in groups_dict.items():
        colors = [{"renk": c, "items": lst} for c, lst in g["colors"].items()]
        total_suggest = sum(it["suggest_qty"] for lst in g["colors"].values() for it in lst)
        groups.append({"model": g["model"], "image": g["image"], "total_suggest": total_suggest, "colors": colors})
    groups.sort(key=lambda x: x["total_suggest"], reverse=True)

    return jsonify({
        "ok": True,
        "days": days,
        "min_cover_days": min_cover,
        "safety_factor": safety_factor,
        "only_positive": only_positive,
        "target_qty": target_qty,
        "use_cache": use_cache,
        "force_compute": force_compute,
        "use_ai": use_ai,
        "use_prophet": use_prophet,
        "blend_weight_ai": blend_weight_ai,
        "quick": quick,
        "max_items": max_items,
        "ai_max_items": ai_max_items,
        "models": model_ids,
        "groups": groups
    })


# ------------------------------------------------------------------------------
# Defaults / Plan / Models (mevcut davranış korunur)
# ------------------------------------------------------------------------------
@uretim_oneri_bp.route("/api/uretim-oneri/defaults", methods=["GET"])
def get_defaults():
    row = UretimOneriDefaults.query.order_by(UretimOneriDefaults.id.asc()).first()
    if not row:
        return jsonify({"models": [], "days": 7, "min_cover_days": 14.0, "safety_factor": 0.10, "only_positive": True})
    return jsonify({
        "models": json.loads(row.models_json or "[]"),
        "days": row.days,
        "min_cover_days": row.min_cover_days,
        "safety_factor": row.safety_factor,
        "only_positive": bool(row.only_positive)
    })

@uretim_oneri_bp.route("/api/uretim-oneri/defaults", methods=["POST"])
def save_defaults():
    data = request.get_json(silent=True) or {}
    models = data.get("models") or []
    if isinstance(models, str):
        models = [m.strip() for m in models.split(",") if m.strip()]
    days = int(data.get("days") or 7)
    min_cover_days = float(data.get("min_cover_days") or 14)
    safety_factor = float(data.get("safety_factor") or 0.10)
    only_positive = bool(data.get("only_positive") if data.get("only_positive") is not None else True)

    row = UretimOneriDefaults.query.order_by(UretimOneriDefaults.id.asc()).first()
    if not row:
        row = UretimOneriDefaults()
        db.session.add(row)
    row.models_json = json.dumps(models, ensure_ascii=False)
    row.days = days
    row.min_cover_days = min_cover_days
    row.safety_factor = safety_factor
    row.only_positive = only_positive
    db.session.commit()
    return jsonify({"ok": True})

@uretim_oneri_bp.route("/api/uretim-oneri/plan", methods=["POST"])
def create_plan():
    body = request.get_json(silent=True) or {}
    models = body.get("models") or []
    if isinstance(models, str):
        models = [m.strip() for m in models.split(",") if m.strip()]
    if not models:
        d = UretimOneriDefaults.query.first()
        models = json.loads(d.models_json) if d else []
    if not models:
        return jsonify({"ok": False, "error": "models boş"}), 400

    defaults = UretimOneriDefaults.query.first()
    days = int(body.get("days") or 0) or (defaults.days if defaults else 7)
    min_cover_days = float(body.get("min_cover_days") or (defaults.min_cover_days if defaults else 14))
    safety_factor = float(body.get("safety_factor") or (defaults.safety_factor if defaults else 0.10))
    only_positive = bool(body.get("only_positive") if body.get("only_positive") is not None else (defaults.only_positive if defaults else True))

    use_ai          = str(body.get("use_ai") or "true").lower() in ("1","true","yes")
    use_prophet     = str(body.get("use_prophet") or "true").lower() in ("1","true","yes")
    blend_weight_ai = float(body.get("blend_weight_ai") or 0.30)
    blend_weight_ai = max(0.0, min(1.0, blend_weight_ai))

    with current_app.test_request_context(
        f"/api/uretim-oneri-haftalik?models={','.join(models)}"
        f"&days={days}&min_cover_days={min_cover_days}&safety_factor={safety_factor}"
        f"&only_positive={'1' if only_positive else '0'}"
        f"&use_ai={'1' if use_ai else '0'}&use_prophet={'1' if use_prophet else '0'}"
        f"&blend_weight_ai={blend_weight_ai}"
    ):
        resp = uretim_oneri_haftalik_api()
        data = resp.get_json()

    total_suggest = sum(int(g.get("total_suggest", 0)) for g in data.get("groups", []))
    title = body.get("title") or f"Haftalık Plan {datetime.now(IST).strftime('%Y-%m-%d %H:%M')}"

    plan = UretimPlan(
        title=title,
        models_json=json.dumps(models, ensure_ascii=False),
        params_json=json.dumps({
            "days": data.get("days"),
            "min_cover_days": data.get("min_cover_days"),
            "safety_factor": data.get("safety_factor"),
            "only_positive": data.get("only_positive"),
            "use_ai": data.get("use_ai"),
            "use_prophet": data.get("use_prophet"),
            "blend_weight_ai": data.get("blend_weight_ai"),
        }, ensure_ascii=False),
        snapshot_json=json.dumps(data, ensure_ascii=False),
        total_suggest=total_suggest,
        status="calisacak"
    )
    db.session.add(plan); db.session.commit()

    return jsonify({"ok": True, "plan_id": plan.id, "print_url": f"/uretim-oneri/plan/{plan.id}/yazdir"})

@uretim_oneri_bp.route("/api/uretim-oneri/planlar", methods=["GET"])
def list_plans():
    page     = int(request.args.get("page", 1) or 1)
    per_page = min(int(request.args.get("per_page", 50) or 50), 200)
    status   = (request.args.get("status") or "").strip().lower()
    qtext    = (request.args.get("q") or "").strip()
    df       = (request.args.get("date_from") or "").strip()
    dt       = (request.args.get("date_to") or "").strip()

    qry = UretimPlan.query
    if status in ("calisacak","tamamlandi","iptal"):
        qry = qry.filter(UretimPlan.status == status)
    if qtext:
        qry = qry.filter(UretimPlan.title.ilike(f"%{qtext}%"))

    def _pd(s):
        try: return datetime.strptime(s, "%Y-%m-%d")
        except Exception: return None
    dfp = _pd(df); dtp = _pd(dt)
    if dfp: qry = qry.filter(UretimPlan.created_at >= dfp)
    if dtp: qry = qry.filter(UretimPlan.created_at < (dtp + timedelta(days=1)))

    qry = qry.order_by(UretimPlan.id.desc())
    pagination = qry.paginate(page=page, per_page=per_page, error_out=False)
    items = [{
        "id": p.id, "title": p.title, "status": p.status,
        "total_suggest": p.total_suggest, "created_at": p.created_at.strftime("%Y-%m-%d %H:%M")
    } for p in pagination.items]
    return jsonify({"ok": True, "page": page, "per_page": per_page, "total": pagination.total, "pages": pagination.pages, "plans": items})

@uretim_oneri_bp.route("/api/uretim-oneri/plan/<int:pid>", methods=["DELETE"])
def delete_plan(pid):
    p = UretimPlan.query.get(pid)
    if not p:
        return jsonify({"ok": False, "error": "plan bulunamadı"}), 404
    db.session.delete(p); db.session.commit()
    return jsonify({"ok": True, "deleted_id": pid})

@uretim_oneri_bp.route("/api/uretim-oneri/plan/<int:pid>/delete", methods=["POST"])
def delete_plan_via_post(pid):
    return delete_plan(pid)

@uretim_oneri_bp.route("/api/uretim-oneri/planlar/delete", methods=["POST"])
def bulk_delete_plans():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    if isinstance(ids, str):
        ids = [x.strip() for x in ids.split(",") if x.strip()]
    ids = [int(x) for x in ids if str(x).isdigit()]
    if not ids:
        return jsonify({"ok": False, "error": "ids boş"}), 400

    found = UretimPlan.query.filter(UretimPlan.id.in_(ids)).all()
    for p in found:
        db.session.delete(p)
    db.session.commit()
    return jsonify({"ok": True, "deleted_ids": [p.id for p in found], "requested": ids})

@uretim_oneri_bp.route("/api/uretim-oneri/plan/<int:pid>/status", methods=["POST"])
def update_plan_status(pid):
    body = request.get_json(silent=True) or {}
    status = (body.get("status") or "").strip().lower()
    if status not in ("calisacak", "tamamlandi", "iptal"):
        return jsonify({"ok": False, "error": "geçersiz status"}), 400
    p = UretimPlan.query.get(pid)
    if not p: return jsonify({"ok": False, "error":"plan bulunamadı"}), 404
    p.status = status; db.session.commit()
    return jsonify({"ok": True})

@uretim_oneri_bp.route("/api/uretim-oneri/plan/<int:pid>", methods=["GET"])
def get_plan(pid):
    p = UretimPlan.query.get(pid)
    if not p:
        return jsonify({"ok": False, "error":"plan bulunamadı"}), 404
    return jsonify({
        "ok": True,
        "id": p.id, "title": p.title, "status": p.status,
        "created_at": p.created_at.strftime("%Y-%m-%d %H:%M"),
        "snapshot": json.loads(p.snapshot_json or "{}")
    })

@uretim_oneri_bp.route("/uretim-oneri/plan/<int:pid>/yazdir")
def print_plan(pid):
    p = UretimPlan.query.get(pid)
    if not p: return "Plan bulunamadı", 404
    snap = json.loads(p.snapshot_json or "{}")
    return render_template("uretim_plan_print.html", plan=p, data=snap)

# --- Model seçimi ---
def _get_or_create_defaults():
    row = UretimOneriDefaults.query.order_by(UretimOneriDefaults.id.asc()).first()
    if not row:
        row = UretimOneriDefaults(models_json="[]", days=7, min_cover_days=14.0, safety_factor=0.10, only_positive=True)
        db.session.add(row); db.session.commit()
    return row

@uretim_oneri_bp.route("/api/uretim-oneri/models", methods=["GET"])
def get_selected_models():
    row = _get_or_create_defaults()
    return jsonify({"ok": True, "models": json.loads(row.models_json or "[]")})

@uretim_oneri_bp.route("/api/uretim-oneri/models/toggle", methods=["POST"])
def toggle_selected_model():
    data = request.get_json(silent=True) or {}
    model_id = (data.get("model_id") or "").strip()
    if not model_id:
        return jsonify({"ok": False, "error": "model_id boş"}), 400
    row = _get_or_create_defaults()
    lst = set(json.loads(row.models_json or "[]"))
    active = None
    if model_id in lst:
        lst.remove(model_id); active = False
    else:
        lst.add(model_id); active = True
    row.models_json = json.dumps(sorted(lst), ensure_ascii=False)
    db.session.commit()
    return jsonify({"ok": True, "active": active, "models": list(sorted(lst))})

@uretim_oneri_bp.route("/api/uretim-oneri/models/bulk", methods=["POST"])
def bulk_add_models():
    data = request.get_json(silent=True) or {}
    models = data.get("models") or []
    if isinstance(models, str):
        models = [m.strip() for m in models.split(",") if m.strip()]
    row = _get_or_create_defaults()
    lst = set(json.loads(row.models_json or "[]"))
    for m in models:
        if m: lst.add(m)
    row.models_json = json.dumps(sorted(lst), ensure_ascii=False)
    db.session.commit()
    return jsonify({"ok": True, "models": json.loads(row.models_json)})



def mark_forecast_dirty(barcode:str, reason:str="event"):
    sql = text("""
      INSERT INTO forecast_dirty (barcode, reason)
      VALUES (:bc, :rs)
      ON CONFLICT (barcode) DO UPDATE SET reason = EXCLUDED.reason
    """)
    db.session.execute(sql, {"bc": barcode.strip(), "rs": reason})
    db.session.commit()


def pop_dirty_batch(n=50):
    rows = db.session.execute(text("""
      DELETE FROM forecast_dirty
      WHERE barcode IN (
        SELECT barcode FROM forecast_dirty ORDER BY created_at ASC LIMIT :n FOR UPDATE SKIP LOCKED
      )
      RETURNING barcode
    """), {"n": n}).fetchall()
    db.session.commit()
    return [r[0] for r in rows]

def build_cache_for_barcode(barcode:str, days:int=14):
    end_day = datetime.now(IST).date()
    series  = _daily_series_from_cache(barcode, days, end_day)   # daily_sales’tan
    avg_base = _moving_average(series, days)

    # hafif koşullar (hız)
    nonzero = sum(1 for r in series if (r.get("qty") or 0)>0)
    use_prophet_local = (nonzero>=5 and avg_base>0)
    avg_prophet = prophet_forecast(series, days) if use_prophet_local else None

    avg_ai_used = None  # ister ekle: ai_forecast_sales(...) + band clip
    avg_final = avg_prophet if (avg_prophet is not None) else avg_base

    db.session.execute(text("""
      INSERT INTO forecast_cache (barcode, days, avg_base, avg_prophet, avg_ai_used, avg_final, updated_at)
      VALUES (:bc, :dy, :ab, :pp, :ai, :af, NOW())
      ON CONFLICT (barcode, days)
      DO UPDATE SET avg_base=:ab, avg_prophet=:pp, avg_ai_used=:ai, avg_final=:af, updated_at=NOW()
    """), {"bc": barcode.strip(), "dy": days, "ab": avg_base, "pp": avg_prophet, "ai": avg_ai_used, "af": avg_final})
    db.session.commit()

def forecast_worker_loop(days:int=14, batch:int=50):
    barcodes = pop_dirty_batch(batch)
    for bc in barcodes:
        try: build_cache_for_barcode(bc, days=days)
        except Exception as e:
            current_app.logger.warning(f"FCACHE fail {bc}: {e}")
