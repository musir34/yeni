from __future__ import annotations
import math, datetime as dt
from flask import Blueprint, render_template, request, jsonify
from models import (
    db, Product,
    OrderCreated, OrderPicking, OrderShipped, OrderDelivered,
)

SALES_TABLES = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered]
BASE_DAYS    = 3   # “şu anki stok 3 gün yetsin” eşiği
TOP_N_SELLERS = 7 # Grafikte gösterilecek en çok satan ürün sayısı (isteğe göre ayarla)

blueprint = Blueprint(
    "intelligent_stock",
    __name__,
    url_prefix="/intelligent-stock",
    template_folder="templates",
    static_folder="static",
)

# ------------------------------------------------------------------ #
def _sales(barcode: str, days: int) -> int:
    """Barkodın son *days* gündeki toplam satışı."""
    end, start = dt.datetime.utcnow(), dt.datetime.utcnow() - dt.timedelta(days=days)
    total = 0
    for Tbl in SALES_TABLES:
        q = (db.session.query(db.func.sum(Tbl.quantity))
             .filter(Tbl.product_barcode == barcode,
                     Tbl.created_at >= start,
                     Tbl.created_at <  end)
             .scalar()) or 0
        total += int(q)
    return total


def _msg(stock: int, daily: float, coverage: int) -> str:
    """
    Konuşkan mesaj:
    • stok 3 gün yeter mi?
    • coverage (kullanıcının istediği hedef) için gerekirse ek stok öner.
    """
    today = dt.date.today()
    if daily == 0:
        return f"Son dönemde satışı olmayan {stock} çift ürün elinde görünüyor. Durumu değerlendirmekte fayda var. 🤔"

    cov  = stock / daily
    if cov >= BASE_DAYS:
        need = max(0, math.ceil(daily * coverage - stock))
        if need == 0:
            return (f"Eldeki {stock} çift ürünle, hedeflediğin {coverage} günü rahatlıkla karşılarsın. Stok durumu gayet iyi! 🎉")
        till = today + dt.timedelta(days=coverage)
        return (f"Eldeki {stock} çift ürün {BASE_DAYS} günü rahat çıkarır. Hedeflediğin {till:%d %b} tarihine kadar tam yetmesi için ≈{need} çift daha ekleyebilirsin. 👍")
    else:
        need = math.ceil(daily * BASE_DAYS - stock)
        return (f"Stok kritik seviyede! {stock} çift ürün ≈{cov:.1f} gün yetebilir. En azından {BASE_DAYS} gün rahatlamak için ≈{need} çift takviye yapmalısın. 🚨")

# ------------------------------------------------------------------ #

def get_sort_keys(product: Product):
    """Ürünleri renk ve bedene göre sıralamak için anahtar üretir."""
    color = (product.color or "DİĞER").upper() # Renkleri büyük harfe çevirerek tutarlı sıralama
    size_val = -1 # Varsayılan değer, sayısal olmayan veya geçersiz bedenler için
    try:
        size_str = str(product.size).strip()
        if size_str and size_str != '-' and size_str.isdigit(): # Sadece rakamlardan oluşuyorsa
            size_val = int(size_str)
    except (ValueError, TypeError):
        pass # size_val -1 olarak kalır
    return (color, -size_val) # Renk A-Z (DİĞER en sonda gibi davranır), beden büyükten küçüğe


@blueprint.route("/", methods=["GET"])
def dashboard():
    models = [r[0] for r in
              db.session.query(Product.product_main_id)
                        .filter(Product.product_main_id != None)
                        .distinct().order_by(Product.product_main_id)]
    return render_template("intelligent_stock_dashboard.html", model_codes=models)


@blueprint.route("/forecast", methods=["POST"])
def forecast():
    data          = request.get_json(silent=True) or {}
    model_code    = data.get("model_code")
    history_days  = int(data.get("history_days", 7))
    coverage_days = int(data.get("coverage_days", 7))

    if not model_code:
        return jsonify({"error": "Model kodu gerekli."}), 400

    prods_query = Product.query.filter_by(product_main_id=model_code)
    prods = prods_query.all()

    if not prods:
        return jsonify({"error": f"'{model_code}' kodlu model için ürün bulunamadı."}), 404

    prods.sort(key=get_sort_keys)

    all_barcodes_sales_info = []
    color_grouped_results = []

    if prods:
        # İlk ürünün rengini veya "Diğer"i alarak başla
        current_color_name_for_group = prods[0].color if prods[0].color else "Diğer"
        current_products_for_color = []

        for p_idx, p_product in enumerate(prods):
            sales = _sales(p_product.barcode, history_days)
            daily = sales / history_days if sales and history_days > 0 else 0
            text_message = _msg(p_product.quantity or 0, daily, coverage_days)

            all_barcodes_sales_info.append({
                "barcode": p_product.barcode,
                "sales_count": sales
            })

            product_data = {
                "barcode": p_product.barcode,
                "size": p_product.size or '-',
                "message": text_message,
                "current_stock": p_product.quantity or 0,
                "daily_avg": round(daily, 2) if daily else 0,
                "sales_in_period": sales
            }

            product_actual_color_display = p_product.color if p_product.color else "Diğer"

            if product_actual_color_display != current_color_name_for_group and current_products_for_color:
                color_grouped_results.append({
                    "color_name": current_color_name_for_group,
                    "products": current_products_for_color
                })
                current_color_name_for_group = product_actual_color_display
                current_products_for_color = []

            current_products_for_color.append(product_data)

            if p_idx == len(prods) - 1 and current_products_for_color: # Son ürünü de ekle
                color_grouped_results.append({
                    "color_name": current_color_name_for_group,
                    "products": current_products_for_color
                })

    top_sellers_for_graph = sorted(all_barcodes_sales_info, key=lambda x: x['sales_count'], reverse=True)[:TOP_N_SELLERS]

    return jsonify({
        "model_code_processed": model_code,
        "color_grouped_results": color_grouped_results,
        "top_sellers_data": top_sellers_for_graph
    }), 200