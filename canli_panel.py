# canli_panel.py
# Canlı Satış & Stok Paneli (İstanbul 00:00–23:59, "sipariş oluşturma zamanı"na göre)
# - Kaynaklar: OrderCreated + OrderPicking + OrderShipped + Archive
# - Gün penceresi: YALNIZ OrderCreated.created_at (TR) baz alınır
# - Diğer tablolar: sadece bu "bugün oluşturulan" siparişler (order_id eşleşmesi) dahil
# - Order-bazlı DEDUP: Archive > Shipped > Picking > Created (aynı sipariş bir kez)
# - Model: SADECE product_main_id + renk (ürün adı yok)
# - Ortalama fiyat: tutarı olan adetlerle (Created/Picking/Shipped)
# - Saat metni: gg/aa/yyyy ss:dd

import json, time, hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Blueprint, Response, jsonify, request, stream_with_context, render_template, redirect, url_for
from sqlalchemy import func, literal, text
from sqlalchemy import func, literal, text, and_, or_
from models import db, Product, CentralStock
from models import OrderCreated, OrderPicking, OrderShipped, Archive

canli_panel_bp = Blueprint("canli_panel", __name__)

# ── Ayarlar
IST = ZoneInfo("Europe/Istanbul")
DUSUK_STOK_ESIK = 5
AKIS_ARALIGI_SANIYE = 5

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

ORD_TS_CANDS   = ["order_date","created_at","created","order_created_at","timestamp","createdDate","create_date_time","date","olusturma_tarihi","shipped_at"]
ORD_DTL_CANDS  = ["details","items","lines","order_lines","orderItems","kalemler","urunler","json_items","raw_json"]
ORD_AMT_CANDS  = ["amount","total_amount","order_amount","grand_total","total","line_total","price_total","sum","paid_amount"]
ORD_ID_CANDS   = ["order_number","orderNumber","orderNo","order_id","orderId","trendyol_order_id","platform_order_id"]

ITEM_QTY_CANDS   = ["quantity","qty","adet","miktar","count","units","piece","quantityOrdered","adet_sayisi"]
ITEM_PRICE_CANDS = ["unitPrice","unit_price","price","salePrice","sale_price","amount","line_total","total","lineTotal","totalPrice","total_price","payablePrice"]
ITEM_SIZE_CANDS  = ["size","beden","number","numara","shoe_size","beden_no"]

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
        ("Archive", Archive),
        ("Shipped", OrderShipped),
        ("Picking", OrderPicking),
        ("Created", OrderCreated),
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
    # Tarayıcı HTML isterse panele yönlendir
    accept = request.headers.get("Accept","")
    if "text/html" in accept and "application/json" not in accept:
        return redirect(url_for("canli_panel.canli_panel_sayfa"))

    tek_model = (request.args.get("model") or "").strip() or None

    # 1) 3 tabloyu TR 00:00–23:59'a göre AYRI AYRI filtreleyip topla
    qty_map, amt_map = _collect_orders_today_strict()  # ← Created + Picking + Shipped

    # 2) Ürün ve stok bilgisi
    barcodes = set(qty_map.keys()) | set(amt_map.keys())
    pinfo = _fetch_product_info_for_barcodes(barcodes)
    sdict = _fetch_stock_for_barcodes(barcodes)

    # 3) (model, renk) → beden kırılımı
    grp = {}
    rep_image = {}
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

    # 4) Kartlar
    now_tr = datetime.now(ZoneInfo("Europe/Istanbul"))
    hours = max(1.0, now_tr.hour + now_tr.minute/60.0)
    kartlar, total_sold = [], 0

    def _beden_key(b):
        try: return (0, float(str(b).replace(',','.')))
        except: return (1, str(b))

    for (model, renk), beden_map in grp.items():
        if tek_model and str(model) != tek_model:
            continue
        detay, toplam_sip, toplam_stok, toplam_tutar, toplam_tutarli_adet = [], 0, 0, 0.0, 0
        for beden in sorted(beden_map.keys(), key=_beden_key):
            s = int(beden_map[beden]["siparis"])
            k = int(beden_map[beden]["stok"])
            a = float(beden_map[beden]["tutar"])
            qa = int(beden_map[beden]["tutarli_adet"])
            toplam_sip += s; toplam_stok += k; toplam_tutar += a; toplam_tutarli_adet += qa
            detay.append({"beden": beden, "siparis": s, "stok": k})
        total_sold += toplam_sip
        ort_fiyat = (toplam_tutar / toplam_tutarli_adet) if toplam_tutarli_adet > 0 else 0.0
        kartlar.append({
            "model": model, "renk": renk, "image": rep_image.get((model, renk)),
            "toplam_siparis_bugun": toplam_sip, "toplam_stok": toplam_stok,
            "ortalama_fiyat": round(ort_fiyat, 2),
            "saatlik_hiz": round(toplam_sip / hours, 2),
            "dusuk_stok": toplam_stok < DUSUK_STOK_ESIK,
            "detay": detay
        })

    kartlar.sort(key=lambda k: (k["toplam_siparis_bugun"], k["toplam_stok"]), reverse=True)
    return jsonify({"guncellendi": now_tr_str(), "toplam_satis": total_sold, "kartlar": kartlar})


@canli_panel_bp.route("/api/canli/akis")
def akis_sse():
    tek_model = (request.args.get("model") or "").strip() or None
    def _gen():
        while True:
            kartlar, total_sold = _build_cards_from_orders()
            if tek_model:
                kartlar = [k for k in kartlar if str(k["model"]) == tek_model]
            payload = {"guncellendi": now_tr_str(), "toplam_satis": total_sold, "kartlar": kartlar}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            time.sleep(AKIS_ARALIGI_SANIYE)
    headers = {"Content-Type":"text/event-stream","Cache-Control":"no-cache","Connection":"keep-alive"}
    return Response(stream_with_context(_gen()), headers=headers)

# ── HTML panel sayfası
@canli_panel_bp.route("/canli-panel")
def canli_panel_sayfa():
    return render_template("canli_panel.html")


def _collect_orders_today_strict():
    """
    Europe/Istanbul gün penceresi [00:00, 24:00) ile
    orders_created, orders_picking, orders_shipped tablolarını AYRI AYRI filtreler,
    item’ları toplar. (Tabloda tarih kolonu bulunamazsa o tablo ATLAnır.)
    Döner: (barcode→qty, barcode→amount_toplam)
    """
    start_tr, end_tr = tr_today_bounds_sql()
    qty_map, amt_map = {}, {}

    def add(bc, q, a):
        if not bc or q <= 0: return
        s = str(bc).strip()
        qty_map[s] = qty_map.get(s, 0) + int(q)
        if a is not None:
            amt_map[s] = amt_map.get(s, 0.0) + float(a)

    sources = [
        ("Created", OrderCreated),
        ("Picking", OrderPicking),
        ("Shipped", OrderShipped),
    ]
    for name, cls in sources:
        ts_col, _, ts_name   = _col(cls, ORD_TS_CANDS, "ts")
        amt_col, _, amt_name = _col(cls, ORD_AMT_CANDS, "amount")
        # details kolonu
        det_name = None
        for n in ORD_DTL_CANDS:
            if hasattr(cls, n): det_name = n; break

        if ts_col is None:
            print(f"[CANLI PANEL] UYARI: {name} için tarih kolonu bulunamadı, tablo atlandı.")
            continue

        q = db.session.query(cls).filter(
    or_(
        and_(func.timezone('Europe/Istanbul', ts_col) >= start_tr,
             func.timezone('Europe/Istanbul', ts_col) <  end_tr),
        and_(ts_col >= start_tr, ts_col < end_tr)  # ts_col TR yerel saat olarak tutulmuşsa
    )
)

        for row in q.all():
            payload = getattr(row, det_name) if (det_name and hasattr(row, det_name)) else None
            if payload in (None,"",[]):
                for alt in ["raw_json","raw","order_json","json"]:
                    if hasattr(row, alt):
                        payload = getattr(row, alt)
                        if payload not in (None,"",[]): break

            # sipariş toplam tutarı (opsiyonel)
            order_amount_total = _to_number(getattr(row, amt_name, None), None) if (amt_name and hasattr(row, amt_name)) else None

            items, total_qty = [], 0
            for it in _iter_items_once(payload) or []:
                bc = _pick_first(it, BARCODE_CANDS, None)
                qt = _to_number(_pick_first(it, ITEM_QTY_CANDS, 1), 0) or 0
                pr = _to_number(_pick_first(it, ITEM_PRICE_CANDS, None), None)
                if not bc or int(qt) <= 0: 
                    continue
                items.append({"bc": bc, "qty": int(qt), "price": pr})
                total_qty += int(qt)

            per_unit = (float(order_amount_total)/float(total_qty)) if (order_amount_total is not None and total_qty>0) else None

            for it in items:
                line_amt = it["price"]*it["qty"] if it["price"] is not None else (per_unit*it["qty"] if per_unit is not None else None)
                add(it["bc"], it["qty"], line_amt)

    return qty_map, amt_map
