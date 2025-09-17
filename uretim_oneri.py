# uretim_oneri.py
# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify, render_template
from sqlalchemy import cast, String
from datetime import datetime, timedelta
from models import db, Product, CentralStock, UretimOneriWatch, OrderCreated, OrderPicking, OrderShipped
try:
    from models import OrderDelivered
except:
    from models import orders_delivered as OrderDelivered

from sqlalchemy.inspection import inspect as sqla_inspect



uretim_oneri_bp = Blueprint("uretim_oneri", __name__)

# ---- Helpers ----
import json, math
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
        if name in cols:
            return getattr(model, name)
    raise AttributeError(f"{model.__name__} içinde bu aday kolonlar yok: {candidates}")


def _pick(d, keys, default=None):
    if not isinstance(d, dict): return default
    for k in keys:
        if k in d and d[k] not in (None, "", []): return d[k]
    return default

def _sum_sales_for_barcode(barcode, days=30):
    since = datetime.utcnow() - timedelta(days=days)
    total = 0
    order_models = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered]
    json_candidates = ["items","order_lines","lines","products","payload"]
    date_field_candidates = ["create_date","created_at","order_date","date"]

    for M in order_models:
        q = M.query
        # kaba tarih filtresi (alan adı farklı olabilir)
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
    # CentralStock'ta kolon adı neyse ona göre filtremizi kur
    col = _resolve_col(
        CentralStock,
        ["product_barcode", "barcode", "product_code", "sku", "productBarcode"]
    )
    cs = CentralStock.query.filter(col == str(barcode)).first()
    return int(getattr(cs, "quantity", 0) or 0)


# ---- ROUTES ----
@uretim_oneri_bp.route("/uretim-oneri")
def uretim_oneri_page():
    return render_template("uretim_oneri.html")  # sade sayfa, JS ile dolduruyoruz

@uretim_oneri_bp.route("/api/uretim-oneri/watchlist/toggle", methods=["POST"])
def toggle_watch():
    data = request.get_json(silent=True) or {}
    barcode = str(data.get("barcode", "")).strip()
    if not barcode:
        return jsonify({"ok": False, "error": "barcode boş"}), 400
    if len(barcode) > 64:
        barcode = barcode[:64]

    row = UretimOneriWatch.query.filter_by(product_barcode=barcode).first()
    if row:
        row.is_active = not bool(row.is_active)
        db.session.commit()
        return jsonify({"ok": True, "active": row.is_active})

    # Product PK = barcode -> doğrudan get()
    p = Product.query.get(barcode)
    row = UretimOneriWatch(
        product_barcode=barcode,
        product_main_id=(p.product_main_id if p else None),
    )
    db.session.add(row)
    db.session.commit()
    return jsonify({"ok": True, "active": True})

@uretim_oneri_bp.route("/api/uretim-oneri/suggestions", methods=["GET"])
def suggestions_grouped():
    days = int(request.args.get("days", 30))
    watch = UretimOneriWatch.query.filter_by(is_active=True).all()
    if not watch:
        return jsonify({"ok": True, "days": days, "groups": []})

    barcodes = [w.product_barcode for w in watch]
    # İzlenen ürünleri çek (PK=barcode)
    prods = Product.query.filter(Product.barcode.in_(barcodes)).all()
    pm = {p.barcode: p for p in prods}
    # ürün yoksa da satış/stock hesaplanacak (yine barcode üzerinden)

    items = []
    for w in watch:
        bc = w.product_barcode
        sold = _sum_sales_for_barcode(bc, days=days)
        avg = sold / float(days) if days > 0 else 0.0
        stock = _stock_for(bc)
        days_left = (stock / avg) if avg > 0 else None
        target = max(0.0, (w.min_cover_days * avg) - stock)
        suggest = int(round(target * (1 + (w.safety_factor or 0.0))))

        p = pm.get(bc)
        # images: ilk görseli seç
        img = None
        if p and p.images:
            img = (p.images.split(",")[0] or "").strip()
        items.append({
            "barcode": bc,
            "product_main_id": (w.product_main_id or (p.product_main_id if p else None)),
            "title": getattr(p, "title", None),
            "color": getattr(p, "color", None),
            "size": getattr(p, "size", None),
            "image": img,
            "stock": stock,
            "sold_last_days": int(sold),
            "avg_daily": round(avg, 3),
            "days_left": (round(days_left, 1) if days_left is not None else None),
            "min_cover_days": w.min_cover_days,
            "safety_factor": w.safety_factor,
            "suggest_qty": max(suggest, 0),
        })

    # product_main_id altında renk -> satırlar şeklinde grupla
    groups_dict = {}
    for x in items:
        key = x["product_main_id"] or "_UNGROUPED_"
        g = groups_dict.setdefault(key, {"product_main_id": key, "title": None, "image": None, "colors": {}})
        # başlık ve kapak görseli
        if not g["title"] and x["title"]:
            g["title"] = x["title"]
        if not g["image"] and x["image"]:
            g["image"] = x["image"]
        # renk
        ckey = x["color"] or "Renk Yok"
        g["colors"].setdefault(ckey, []).append(x)

    # response formatı: colors dict -> list
    groups = []
    for _, g in groups_dict.items():
        colors = [{"color": c, "items": rows} for c, rows in g["colors"].items()]
        # toplam öneri (grup üstü sum)
        total_suggest = sum(r["suggest_qty"] for rows in g["colors"].values() for r in rows)
        groups.append({
            "product_main_id": g["product_main_id"],
            "title": g["title"],
            "image": g["image"],
            "total_suggest": total_suggest,
            "colors": colors
        })

    # büyükten küçüğe öneri
    groups.sort(key=lambda g: g["total_suggest"], reverse=True)
    return jsonify({"ok": True, "days": days, "groups": groups})
