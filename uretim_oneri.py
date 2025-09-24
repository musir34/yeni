# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify, render_template
from sqlalchemy import func, literal
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from models import UretimOneriDefaults, UretimPlan
import json
from models import db, Product, CentralStock, UretimOneriWatch, OrderCreated, OrderPicking, OrderShipped
try:
    from models import OrderDelivered
except Exception:
    from models import orders_delivered as OrderDelivered

from sqlalchemy.inspection import inspect as sqla_inspect
import json, hashlib

# ------------------------------------------------------------------------------
# Blueprint
# ------------------------------------------------------------------------------
uretim_oneri_bp = Blueprint("uretim_oneri", __name__)

# ------------------------------------------------------------------------------
# Ortak yardımcılar
# ------------------------------------------------------------------------------
def _json_parse(x):
    if isinstance(x, (dict, list)): return x
    if isinstance(x, str):
        try: return json.loads(x)
        except: return None
    return None

def _resolve_col(model, candidates):
    """Modelde var olan ilk kolonu döndür (SQLAlchemy column objesi)."""
    cols = {c.key for c in sqla_inspect(model).mapper.column_attrs}
    for name in candidates:
        if name in cols: return getattr(model, name)
    raise AttributeError(f"{model.__name__} içinde bu aday kolonlar yok: {candidates}")

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

def _content_signature(items, src_name, row_id):
    parts = []
    for it in items:
        bc = str(it.get("bc") or "").strip()
        sz = str(it.get("size") or "").strip()
        qt = int(it.get("qty") or 0)
        parts.append(f"{bc}|{sz}|{qt}")
    sig = "|".join(sorted(parts)) or f"{src_name}:{row_id}"
    return "SIG:" + hashlib.md5(sig.encode("utf-8")).hexdigest()

# ------------------------------------------------------------------------------
# Satış toplama (son X gün) – farklı tablo isimleri/alanları için esnek okuyucu
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

BARCODE_CANDS = [
    "barcode","barkod","urun_barkod","product_barcode","productBarcode",
    "sku","stock_code","stok_kodu","gtin","ean","ean13","upc","model_barcode"
]
ITEM_QTY_CANDS   = ["quantity","qty","adet","miktar","count","units","piece","quantityOrdered","adet_sayisi"]
ITEM_PRICE_CANDS = ["unitPrice","unit_price","price","salePrice","sale_price","amount","line_total","total","lineTotal","totalPrice","total_price","payablePrice"]
ITEM_SIZE_CANDS  = ["size","beden","number","numara","shoe_size","beden_no"]

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

def _extract_order_id_from_row_or_payload(row, payload):
    for n in ORD_ID_CANDS:
        if hasattr(row, n):
            v = getattr(row, n)
            if v not in (None,""): return str(v)
    root = _json_parse(payload)
    if isinstance(root, dict):
        for n in ORD_ID_CANDS:
            v = root.get(n)
            if v not in (None,""): return str(v)
    return None

def _collect_orders_between_strict_generic(start_ist, end_ist):
    """barcode→qty / barcode→NET_tutar"""
    qty_map, amt_map = {}, {}
    sources = [("Created",OrderCreated), ("Picking",OrderPicking), ("Shipped",OrderShipped), ("Delivered",OrderDelivered)]
    def add(bc, q, a):
        if not bc or q <= 0: return
        s = str(bc).strip()
        qty_map[s] = qty_map.get(s, 0) + int(q)
        if a is not None:
            amt_map[s] = amt_map.get(s, 0.0) + float(a)

    for name, cls in sources:
        ts_col, _, _   = _col(cls, ORD_TS_CANDS, "ts")
        amt_col, _, A  = _col(cls, ORD_AMT_CANDS,  "amount")
        disc_col,_, D  = _col(cls, ORD_DISC_CANDS, "discount")
        det_name = next((n for n in ORD_DTL_CANDS if hasattr(cls, n)), None)
        if ts_col is None: continue

        q = db.session.query(cls).filter(
            func.timezone('Europe/Istanbul', ts_col) >= start_ist,
            func.timezone('Europe/Istanbul', ts_col) <  end_ist
        )
        for row in q.all():
            payload = getattr(row, det_name) if (det_name and hasattr(row, det_name)) else None
            if payload in (None,"",[]):
                for alt in ["raw_json","raw","order_json","json"]:
                    if hasattr(row, alt):
                        payload = getattr(row, alt)
                        if payload not in (None,"",[]): break

            amount_gross   = _to_number(getattr(row, A, None), None) if (A and hasattr(row, A)) else None
            discount_total = _to_number(getattr(row, D, None), 0.0)  if (D and hasattr(row, D)) else 0.0
            amount_net     = None
            if amount_gross is not None:
                try: amount_net = float(amount_gross) - float(discount_total or 0.0)
                except: amount_net = amount_gross

            items, total_qty = [], 0
            for it in _iter_items_once(payload) or []:
                bc = _pick(it, BARCODE_CANDS)
                qt = _to_number(_pick(it, ITEM_QTY_CANDS, 1), 0) or 0
                pr = _to_number(_pick(it, ITEM_PRICE_CANDS, None), None)
                if not bc or int(qt) <= 0: continue
                items.append({"bc": bc, "qty": int(qt), "price": pr})
                total_qty += int(qt)

            per_unit_net = (amount_net/float(total_qty)) if (amount_net is not None and total_qty>0) else None
            for it in items:
                line_amt_net = (per_unit_net*it["qty"]) if per_unit_net is not None else ((it["price"]*it["qty"]) if it["price"] is not None else None)
                add(it["bc"], it["qty"], line_amt_net)

    return qty_map, amt_map

# ------------------------------------------------------------------------------
# WATCHLIST + EXPLICIT (barkod/model) ÖNERİ
# ------------------------------------------------------------------------------
def _sum_sales_for_barcode(barcode, days=30):
    since = datetime.utcnow() - timedelta(days=days)
    total = 0
    order_models = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered]
    json_candidates = ["items","order_lines","lines","products","payload"]
    date_field_candidates = ["create_date","created_at","order_date","date"]
    for M in order_models:
        q = M.query
        for df in date_field_candidates:
            if hasattr(M, df):
                q = q.filter(getattr(M, df) >= since)
                break
        for row in q:
            data = None
            for cand in json_candidates:
                if hasattr(row, cand):
                    data = _json_parse(getattr(row, cand))
                    if data: break
            if not data: continue
            lines = data if isinstance(data, list) else _pick(data, json_candidates, [])
            if not isinstance(lines, list): continue
            for it in lines:
                b = _pick(it, ["barcode","barkod","sku","gtin"])
                if b and str(b).strip() == barcode:
                    qty = _pick(it, ["quantity","qty","adet"], 0) or 0
                    try: total += float(qty)
                    except: pass
    return total

def _stock_for(barcode):
    col = _resolve_col(
        CentralStock,
        ["product_barcode", "barcode", "product_code", "sku", "productBarcode"]
    )
    cs = CentralStock.query.filter(col == str(barcode)).first()
    return int(getattr(cs, "quantity", 0) or 0)

@uretim_oneri_bp.route("/uretim-oneri")
def uretim_oneri_page():
    return render_template("uretim_oneri.html")

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

# ---- gelişmiş suggestions: watch (default) / explicit; renk/beden/only_positive
def _wk_to_list_for_endpoint(val):
    return _to_list(val)

def _expand_barcodes_from_main_ids(main_ids):
    if not main_ids: return []
    qs = Product.query.with_entities(Product.barcode).filter(Product.product_main_id.in_(main_ids)).all()
    return [b for (b,) in qs if b]

def _filter_items(items, colors=None, sizes=None, only_positive=False):
    colors = set([c.lower() for c in (colors or [])])
    sizes  = set([s.lower() for s in (sizes or [])])
    out = []
    for x in items:
        if colors and (str(x.get("color") or "").lower() not in colors): continue
        if sizes and (str(x.get("size") or "").lower() not in sizes): continue
        if only_positive and x.get("suggest_qty", 0) <= 0: continue
        out.append(x)
    return out

@uretim_oneri_bp.route("/api/uretim-oneri/suggestions", methods=["GET","POST"])
def suggestions_grouped():
    # Parametreler
    data = request.get_json(silent=True) or {}
    qs = request.args
    mode = (data.get("mode") or qs.get("mode") or "watch").strip().lower()
    days = int(data.get("days") or qs.get("days") or 30)

    barcodes = _wk_to_list_for_endpoint(data.get("barcodes") or qs.get("barcodes"))
    main_ids = _wk_to_list_for_endpoint(data.get("product_main_ids") or qs.get("product_main_ids"))
    colors   = _wk_to_list_for_endpoint(data.get("colors") or qs.get("colors"))
    sizes    = _wk_to_list_for_endpoint(data.get("sizes") or qs.get("sizes"))
    only_positive = str(data.get("only_positive") or qs.get("only_positive") or "0") in ("1","true","True")

    # hangi barkodlar?
    selected_barcodes = set()
    if mode == "explicit":
        selected_barcodes.update(barcodes)
        selected_barcodes.update(_expand_barcodes_from_main_ids(main_ids))
        selected_barcodes = {b for b in selected_barcodes if b}
        if not selected_barcodes:
            return jsonify({"ok": True, "mode": mode, "days": days, "groups": []})
        watch_like = [{"product_barcode": b, "min_cover_days": 14, "safety_factor": 0.1, "product_main_id": None} for b in selected_barcodes]
    else:
        watch = UretimOneriWatch.query.filter_by(is_active=True).all()
        if not watch:
            return jsonify({"ok": True, "mode": "watch", "days": days, "groups": []})
        watch_like = watch
        selected_barcodes = {w.product_barcode for w in watch_like}

    # product cache
    prods = Product.query.filter(Product.barcode.in_(selected_barcodes)).all()
    pm = {p.barcode: p for p in prods}

    items = []
    for w in watch_like:
        bc = getattr(w, "product_barcode", None) or w.get("product_barcode")
        if not bc: continue
        sold = _sum_sales_for_barcode(bc, days=days)
        avg  = sold / float(days) if days > 0 else 0.0
        stock= _stock_for(bc)
        days_left = (stock / avg) if avg > 0 else None
        min_cover_days = getattr(w, "min_cover_days", None) or w.get("min_cover_days") or 14
        safety_factor  = getattr(w, "safety_factor", None)  or w.get("safety_factor")  or 0.1
        target  = max(0.0, (min_cover_days * avg) - stock)
        suggest = int(round(target * (1 + (safety_factor or 0.0))))

        p = pm.get(bc)
        img = None
        if p and getattr(p, "images", None):
            img = (p.images.split(",")[0] or "").strip()

        items.append({
            "barcode": bc,
            "product_main_id": (getattr(w, "product_main_id", None) or (p.product_main_id if p else None)),
            "title": getattr(p, "title", None),
            "color": getattr(p, "color", None),
            "size":  getattr(p, "size",  None),
            "image": img,
            "stock": stock,
            "sold_last_days": int(sold),
            "avg_daily": round(avg, 3),
            "days_left": (round(days_left, 1) if days_left is not None else None),
            "min_cover_days": min_cover_days,
            "safety_factor": safety_factor,
            "suggest_qty": max(suggest, 0),
        })

    items = _filter_items(items, colors=colors, sizes=sizes, only_positive=only_positive)

    # product_main_id altında renk -> satırlar
    groups_dict = {}
    for x in items:
        key = x["product_main_id"] or "_UNGROUPED_"
        g = groups_dict.setdefault(key, {"product_main_id": key, "title": None, "image": None, "colors": {}})
        if not g["title"] and x["title"]: g["title"] = x["title"]
        if not g["image"] and x["image"]: g["image"] = x["image"]
        ckey = x["color"] or "Renk Yok"
        g["colors"].setdefault(ckey, []).append(x)

    groups = []
    for _, g in groups_dict.items():
        colors_out = [{"color": c, "items": rows} for c, rows in g["colors"].items()]
        total_suggest = sum(r["suggest_qty"] for rows in g["colors"].values() for r in rows)
        groups.append({
            "product_main_id": g["product_main_id"],
            "title": g["title"],
            "image": g["image"],
            "total_suggest": total_suggest,
            "colors": colors_out
        })

    groups.sort(key=lambda g: g["total_suggest"], reverse=True)
    return jsonify({"ok": True, "mode": mode, "days": days, "groups": groups})

# ------------------------------------------------------------------------------
# HAFTALIK ÜRETİM ÖNERİSİ (SEÇİLEN MODELLER) – Ayrı sayfa + API
# Kaynak satış: canli_panel._collect_orders_between_strict (import edemezsen üstteki generic kullanılır)
# ------------------------------------------------------------------------------
IST = ZoneInfo("Europe/Istanbul")
try:
    from canli_panel import _collect_orders_between_strict as _collect_orders_between_strict_ref
except Exception:
    _collect_orders_between_strict_ref = _collect_orders_between_strict_generic

# LAZY kolons for Product / CentralStock
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

@uretim_oneri_bp.route("/uretim-oneri-haftalik")
def uretim_oneri_haftalik_page():
    _bind_columns_once()
    return render_template("uretim_oneri_haftalik.html")

@uretim_oneri_bp.route("/api/uretim-oneri-haftalik", methods=["GET","POST"])
def uretim_oneri_haftalik_api():
    """
    Param:
      - models: CSV/JSON list (product_main_id)
      - days: int (default 7)
      - min_cover_days: float (default 14)
      - safety_factor: float (default 0.1)
      - only_positive: 1/0 (default 1)
    """
    _bind_columns_once()
    body = request.get_json(silent=True) or {}
    args = request.args

    model_ids     = _to_list(body.get("models") or args.get("models"))
    days          = int(body.get("days") or args.get("days") or 7)
    min_cover     = float(body.get("min_cover_days") or args.get("min_cover_days") or 14)
    safety_factor = float(body.get("safety_factor") or args.get("safety_factor") or 0.10)
    only_positive = str(body.get("only_positive") or args.get("only_positive") or "1") in ("1","true","True")

    if not model_ids:
        return jsonify({"ok": True, "days": days, "groups": [], "note": "models boş"}), 200

    now = datetime.now(IST)
    start_ist = datetime.combine((now - timedelta(days=days-1)).date(), datetime.min.time(), IST)
    end_ist   = datetime.combine((now + timedelta(days=1)).date(), datetime.min.time(), IST)

    # satış (adet + NET):
    qty_map, _ = _collect_orders_between_strict_ref(start_ist, end_ist)

    sel_barcodes = _expand_barcodes_for_models(model_ids)
    barcodes = set(k for k in qty_map.keys() if k in sel_barcodes)

    sdict = _fetch_stock_for_barcodes(barcodes)
    pinfo = _fetch_product_info_for_barcodes(barcodes)

    rows = []
    for bc in barcodes:
        sold = int(qty_map.get(bc, 0))
        avg  = sold / float(days) if days > 0 else 0.0
        st   = int(sdict.get(bc, 0))
        days_left = (st / avg) if avg > 0 else None
        target = max(0.0, (min_cover * avg) - st)
        suggest = int(round(target * (1 + safety_factor)))

        info = pinfo.get(bc, {"model":"Bilinmiyor","renk":"Bilinmiyor","beden":"—","image":None})
        rec = {
            "barcode": bc, "model": info["model"], "renk": info["renk"], "beden": info["beden"],
            "image": info.get("image"),
            "stok": st, "sold_last_days": sold, "avg_daily": round(avg, 3),
            "days_left": (round(days_left, 1) if days_left is not None else None),
            "min_cover_days": min_cover, "safety_factor": safety_factor,
            "suggest_qty": max(suggest, 0),
        }
        if (not only_positive) or rec["suggest_qty"] > 0:
            rows.append(rec)

    # model > renk grupla
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
        "models": model_ids,
        "groups": groups
    })



# ---------- Varsayılanları getir ----------
@uretim_oneri_bp.route("/api/uretim-oneri/defaults", methods=["GET"])
def get_defaults():
    row = UretimOneriDefaults.query.order_by(UretimOneriDefaults.id.asc()).first()
    if not row:
        # yoksa fabrika ayarı
        return jsonify({"models": [], "days": 7, "min_cover_days": 14.0, "safety_factor": 0.10, "only_positive": True})
    return jsonify({
        "models": json.loads(row.models_json or "[]"),
        "days": row.days,
        "min_cover_days": row.min_cover_days,
        "safety_factor": row.safety_factor,
        "only_positive": bool(row.only_positive)
    })

# ---------- Varsayılanları kaydet ----------
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

# ---------- Plan oluştur (snapshot + yazdır linki döner) ----------
@uretim_oneri_bp.route("/api/uretim-oneri/plan", methods=["POST"])
def create_plan():
    """
    Body:
      - models: [..] ya da "gll012,gll088"
      - days, min_cover_days, safety_factor, only_positive
      - title (opsiyonel)
    Çalışma:
      1) /api/uretim-oneri-haftalik ile hesaplar (snapshot)
      2) uretim_plan'a kaydeder (status=calisacak, created_at=now)
    """
    body = request.get_json(silent=True) or {}
    # 1) Paramları toparla
    models = body.get("models") or []
    if isinstance(models, str):
        models = [m.strip() for m in models.split(",") if m.strip()]
    if not models:
        # defaults’tan al
        d = UretimOneriDefaults.query.first()
        models = json.loads(d.models_json) if d else []
    if not models:
        return jsonify({"ok": False, "error": "models boş"}), 400

    days = int(body.get("days") or 0) or (UretimOneriDefaults.query.first().days if UretimOneriDefaults.query.first() else 7)
    min_cover_days = float(body.get("min_cover_days") or (UretimOneriDefaults.query.first().min_cover_days if UretimOneriDefaults.query.first() else 14))
    safety_factor = float(body.get("safety_factor") or (UretimOneriDefaults.query.first().safety_factor if UretimOneriDefaults.query.first() else 0.10))
    only_positive = bool(body.get("only_positive") if body.get("only_positive") is not None else (UretimOneriDefaults.query.first().only_positive if UretimOneriDefaults.query.first() else True))

    # 2) Haftalık API'yi çağır (internal)
    with uretim_oneri_bp.test_request_context(
        f"/api/uretim-oneri-haftalik?models={','.join(models)}&days={days}&min_cover_days={min_cover_days}&safety_factor={safety_factor}&only_positive={'1' if only_positive else '0'}"
    ):
        resp = uretim_oneri_haftalik_api()
        data = resp.get_json()

    # 3) top.öneri
    total_suggest = 0
    for g in data.get("groups", []):
        total_suggest += int(g.get("total_suggest", 0))

    # 4) kaydet
    title = body.get("title") or f"Haftalık Plan {datetime.now(ZoneInfo('Europe/Istanbul')).strftime('%Y-%m-%d %H:%M')}"
    plan = UretimPlan(
        title=title,
        models_json=json.dumps(models, ensure_ascii=False),
        params_json=json.dumps({
            "days": data.get("days"),
            "min_cover_days": data.get("min_cover_days"),
            "safety_factor": data.get("safety_factor"),
            "only_positive": data.get("only_positive")
        }, ensure_ascii=False),
        snapshot_json=json.dumps(data, ensure_ascii=False),
        total_suggest=total_suggest,
        status="calisacak"
    )
    db.session.add(plan)
    db.session.commit()

    return jsonify({"ok": True, "plan_id": plan.id, "print_url": f"/uretim-oneri/plan/{plan.id}/yazdir"})

# ---------- Plan listesi ----------
@uretim_oneri_bp.route("/api/uretim-oneri/planlar", methods=["GET"])
def list_plans():
    qs = UretimPlan.query.order_by(UretimPlan.id.desc()).limit(200).all()
    out = []
    for p in qs:
        out.append({
            "id": p.id,
            "title": p.title,
            "status": p.status,
            "total_suggest": p.total_suggest,
            "created_at": p.created_at.strftime("%Y-%m-%d %H:%M")
        })
    return jsonify({"ok": True, "plans": out})

# ---------- Plan durumu güncelle ----------
@uretim_oneri_bp.route("/api/uretim-oneri/plan/<int:pid>/status", methods=["POST"])
def update_plan_status(pid):
    body = request.get_json(silent=True) or {}
    status = (body.get("status") or "").strip().lower()
    if status not in ("calisacak", "tamamlandi", "iptal"):
        return jsonify({"ok": False, "error": "geçersiz status"}), 400
    p = UretimPlan.query.get(pid)
    if not p: return jsonify({"ok": False, "error":"plan bulunamadı"}), 404
    p.status = status
    db.session.commit()
    return jsonify({"ok": True})

# ---------- Plan detay (JSON) ----------
@uretim_oneri_bp.route("/api/uretim-oneri/plan/<int:pid>", methods=["GET"])
def get_plan(pid):
    p = UretimPlan.query.get(pid)
    if not p: return jsonify({"ok": False, "error":"plan bulunamadı"}), 404
    return jsonify({
        "id": p.id, "title": p.title, "status": p.status,
        "created_at": p.created_at.strftime("%Y-%m-%d %H:%M"),
        "snapshot": json.loads(p.snapshot_json or "{}")
    })

# ---------- Yazdırılabilir görünüm ----------
@uretim_oneri_bp.route("/uretim-oneri/plan/<int:pid>/yazdir")
def print_plan(pid):
    p = UretimPlan.query.get(pid)
    if not p: return "Plan bulunamadı", 404
    snap = json.loads(p.snapshot_json or "{}")
    return render_template("uretim_plan_print.html", plan=p, data=snap)


# --- Model seçimi: kalıcı listeyi getir / toggle / bulk ---
from models import UretimOneriDefaults

def _get_or_create_defaults():
    row = UretimOneriDefaults.query.order_by(UretimOneriDefaults.id.asc()).first()
    if not row:
        row = UretimOneriDefaults(models_json="[]", days=7, min_cover_days=14.0, safety_factor=0.10, only_positive=True)
        db.session.add(row); db.session.commit()
    return row

@uretim_oneri_bp.route("/api/uretim-oneri/models", methods=["GET"])
def get_selected_models():
    row = _get_or_create_defaults()
    import json
    return jsonify({"ok": True, "models": json.loads(row.models_json or "[]")})

@uretim_oneri_bp.route("/api/uretim-oneri/models/toggle", methods=["POST"])
def toggle_selected_model():
    data = request.get_json(silent=True) or {}
    model_id = (data.get("model_id") or "").strip()
    if not model_id:
        return jsonify({"ok": False, "error": "model_id boş"}), 400

    import json
    row = _get_or_create_defaults()
    lst = json.loads(row.models_json or "[]")
    if model_id in lst:
        lst = [m for m in lst if m != model_id]
        active = False
    else:
        lst.append(model_id)
        active = True
    row.models_json = json.dumps(lst, ensure_ascii=False)
    db.session.commit()
    return jsonify({"ok": True, "active": active, "models": lst})

@uretim_oneri_bp.route("/api/uretim-oneri/models/bulk", methods=["POST"])
def bulk_add_models():
    """Açık listedeki birden fazla modeli tek seferde eklemek için (opsiyonel)."""
    data = request.get_json(silent=True) or {}
    models = data.get("models") or []
    if isinstance(models, str):
        models = [m.strip() for m in models.split(",") if m.strip()]
    import json
    row = _get_or_create_defaults()
    lst = set(json.loads(row.models_json or "[]"))
    for m in models: 
        if m: lst.add(m)
    row.models_json = json.dumps(sorted(lst), ensure_ascii=False)
    db.session.commit()
    return jsonify({"ok": True, "models": json.loads(row.models_json)})
