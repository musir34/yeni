from __future__ import annotations
import math, datetime as dt
from flask import Blueprint, render_template, request, jsonify
from models import (
    db, Product,
    OrderCreated, OrderPicking, OrderShipped, OrderDelivered,
)

SALES_TABLES = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered]

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

def _msg(stock: int, daily: float, coverage_target_days: int, base_threshold_days: int) -> str:
    """
    Konuşkan mesajlar, daha sade ve emojili.
    """
    # today = dt.date.today() # Şimdilik tarihe gerek yok mesajlarda

    if daily == 0:
        if stock > 0:
            return f"Satış yok, eldeki {stock} çift şimdilik yeterli. 👍"
        else:
            return f"Satış yok, stok da sıfır. Giriş yapmayı düşünebilirsin. 🤔"

    # daily > 0 ise devam et
    current_coverage_days = stock / daily

    # Temel eşik için gereken (negatifse 0 yap)
    needed_for_base = max(0, math.ceil(daily * base_threshold_days - stock))
    # Hedef için gereken (negatifse 0 yap)
    needed_for_target = max(0, math.ceil(daily * coverage_target_days - stock))

    # Durum 1: Stok tamamen bitmişse (En kritik)
    if stock == 0:
        return f"Stok sıfır! {base_threshold_days} günlük temel ihtiyaç için en az {needed_for_base} çift gir. 🚨"

    # Durum 2: Stok var ama temel eşiğin altında (Kritik)
    if current_coverage_days < base_threshold_days:
        return (f"Stok kritik ({stock} çift, ≈{current_coverage_days:.1f} gün)! "
                f"{base_threshold_days} günlük temel eşik için {needed_for_base} çift takviye şart. 🆘")

    # Durum 3: Temel eşik tamam, ama hedef için ek gerek (Planlama/Fırsat)
    if needed_for_target > 0: # current_coverage_days >= base_threshold_days zaten bu durumda sağlanmış olur
        return (f"Temel stok ({base_threshold_days} gün) tamam ({stock} çift, ≈{current_coverage_days:.1f} gün). "
                f"{coverage_target_days} günlük hedefin için {needed_for_target} çift daha ekleyebilirsin. ✨")

    # Durum 4: Her şey yolunda, hedef de tamam (Rahat)
    # Bu durum, needed_for_target <= 0 (yani 0) ise ve current_coverage_days >= base_threshold_days ise geçerli
    return (f"Stok harika ({stock} çift, ≈{current_coverage_days:.1f} gün)! "
            f"{coverage_target_days} günlük hedefini karşılıyor. ✅")


# ------------------------------------------------------------------ #
@blueprint.route("/", methods=["GET"])
def dashboard():
    models = [r[0] for r in
              db.session.query(Product.product_main_id)
                       .filter(Product.product_main_id != None)
                       .distinct().order_by(Product.product_main_id)]
    return render_template("intelligent_stock_dashboard.html", model_codes=models)


@blueprint.route("/forecast", methods=["POST"])
def forecast():
    data = request.get_json(silent=True) or {}
    model_code = data.get("model_code")

    try:
        history_days = int(data.get("history_days", 7))
        coverage_days = int(data.get("coverage_days", 7)) # Bu JS'e de gidecek stok barı için
        base_days = int(data.get("base_days", 3))
    except ValueError:
        return jsonify({"error": "history_days, coverage_days ve base_days sayı olmalı."}), 400

    if not model_code:
        return jsonify({"error": "model_code gerekli"}), 400

    if history_days <= 0 or coverage_days <= 0 or base_days <= 0: # coverage_days de pozitif olmalı stok barı için
        return jsonify({"error": "history_days, coverage_days, ve base_days pozitif olmalı."}), 400

    prods = Product.query.filter_by(product_main_id=model_code).order_by(Product.color, Product.size).all()

    if not prods:
        return jsonify({"error": f"{model_code} kodlu model bulunamadı"}), 404

    results = []
    for p in prods:
        current_stock = p.quantity or 0
        sales_in_period = _sales(p.barcode, history_days)
        daily_avg_sales = sales_in_period / history_days if sales_in_period > 0 and history_days > 0 else 0

        days_of_stock_left = 0
        if daily_avg_sales > 0:
            days_of_stock_left = current_stock / daily_avg_sales

        message_text = _msg(current_stock, daily_avg_sales, coverage_days, base_days)

        needed_for_base = 0
        if daily_avg_sales > 0 and current_stock / daily_avg_sales < base_days : # Sadece temel eşik altındaysa hesapla
             needed_for_base = max(0, math.ceil(daily_avg_sales * base_days - current_stock))


        needed_for_coverage = 0
        # Hedef için eksik, sadece günlük satış varsa ve stok hedefin altındaysa anlamlı
        if daily_avg_sales > 0 and (current_stock / daily_avg_sales < coverage_days):
             needed_for_coverage = max(0, math.ceil(daily_avg_sales * coverage_days - current_stock))
        elif daily_avg_sales == 0 and current_stock == 0: # Satış yok, stok da yoksa, hedef için hedef kadar lazım gibi düşünebiliriz veya 0
            pass # Bu durumu _msg hallediyor, burada özel bir eksik hesaplamaya gerek yok.
                 # Ya da hedeflenen gün * 1 (min günlük satış varsayımı) gibi bir şey yapılabilir. Şimdilik 0 kalsın.

        product_data = {
            "barkod": p.barcode,
            "model_kodu": model_code,
            "renk": p.color or '-',
            "beden": p.size or '-',
            "mevcut_stok": current_stock,
            "gunluk_ortalama_satis": round(daily_avg_sales, 2),
            "mevcut_stok_kac_gun_yeter": days_of_stock_left, # JS'de formatlanacak
            "temel_stok_icin_eksik": needed_for_base, # JS'de renklendirme için kullanılabilir
            "hedef_stok_icin_eksik": needed_for_coverage,
            "mesaj": message_text, # Yenilenmiş mesaj
            # JS'in stok barı ve bazı kararlar için coverage_days ve base_days'e ihtiyacı var.
            # Bunları her item için göndermek yerine, genel yanıtta bir kere gönderebiliriz.
        }
        results.append(product_data)

    # coverage_days ve base_days değerlerini de yanıta ekleyelim ki JS kullanabilsin
    return jsonify({
        "results": results,
        "query_params": {
            "coverage_days_target": coverage_days, # Hedeflenen yeterlilik (stok barı için)
            "base_days_threshold": base_days # Temel eşik (renklendirme için)
        }
    }), 200