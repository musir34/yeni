"""
Shopify Admin API JSON route'ları.
"""

from functools import wraps

from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required

from .shopify_config import ShopifyConfig
from .shopify_service import shopify_service
from .shopify_stock_service import shopify_stock_service


shopify_bp = Blueprint("shopify", __name__, url_prefix="/shopify")


def check_shopify_config(func):
    @wraps(func)
    def decorated(*args, **kwargs):
        if not ShopifyConfig.is_configured():
            return jsonify({
                "success": False,
                "message": "Shopify API ayarları eksik. SHOPIFY_STORE_DOMAIN ve SHOPIFY_ACCESS_TOKEN gerekli.",
            }), 500
        return func(*args, **kwargs)

    return decorated


@shopify_bp.route("/health")
def health():
    return jsonify({
        "success": True,
        "configured": ShopifyConfig.is_configured(),
        "store_domain": ShopifyConfig.normalized_store_domain() if ShopifyConfig.STORE_DOMAIN else None,
        "api_version": ShopifyConfig.API_VERSION,
    })


@shopify_bp.route("/api/test-connection")
@check_shopify_config
def test_connection():
    result = shopify_service.test_connection()
    status_code = 200 if result.get("success") else 502
    return jsonify(result), status_code


@shopify_bp.route("/api/shop")
@check_shopify_config
def shop_info():
    result = shopify_service.test_connection()
    status_code = 200 if result.get("success") else 502
    return jsonify(result), status_code


@shopify_bp.route("/orders")
@login_required
def orders_dashboard():
    """Shopify siparis yonetim sayfasi."""
    configured = ShopifyConfig.is_configured()
    return render_template("shopify/orders.html", configured=configured)


@shopify_bp.route("/api/orders")
@check_shopify_config
def orders():
    limit = request.args.get("limit", 20, type=int)
    query_filter = request.args.get("query")
    after = request.args.get("after")
    result = shopify_service.get_orders(limit=limit, query_filter=query_filter, after=after)
    status_code = 200 if result.get("success") else 502
    return jsonify(result), status_code


@shopify_bp.route("/api/orders/count")
@check_shopify_config
def orders_count():
    query_filter = request.args.get("query")
    result = shopify_service.get_orders_count(query_filter=query_filter)
    status_code = 200 if result.get("success") else 502
    return jsonify(result), status_code


@shopify_bp.route("/api/orders/<order_id>")
@check_shopify_config
def order_detail(order_id):
    result = shopify_service.get_order(order_id)
    status_code = 200 if result.get("success") else 404
    return jsonify(result), status_code


@shopify_bp.route("/api/orders/<order_id>/cancel", methods=["POST"])
@login_required
@check_shopify_config
def cancel_order(order_id):
    payload = request.get_json(silent=True) or {}
    result = shopify_service.cancel_order(
        order_id=order_id,
        reason=payload.get("reason", "CUSTOMER"),
        refund=bool(payload.get("refund", False)),
        restock=bool(payload.get("restock", False)),
        note=payload.get("note"),
    )
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@shopify_bp.route("/api/orders/<order_id>/fulfill", methods=["POST"])
@login_required
@check_shopify_config
def fulfill_order(order_id):
    """Siparisi karsila (fulfillment olustur)."""
    payload = request.get_json(silent=True) or {}
    result = shopify_service.create_fulfillment(
        order_id=order_id,
        tracking_number=payload.get("tracking_number"),
        tracking_company=payload.get("tracking_company"),
        tracking_url=payload.get("tracking_url"),
        notify_customer=bool(payload.get("notify_customer", True)),
    )
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@shopify_bp.route("/api/orders/<order_id>/note", methods=["POST"])
@login_required
@check_shopify_config
def update_order_note(order_id):
    """Siparis notunu guncelle."""
    payload = request.get_json(silent=True) or {}
    note = payload.get("note", "")
    result = shopify_service.add_order_note(order_id=order_id, note=note)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@shopify_bp.route("/api/orders/<order_id>/tags", methods=["POST"])
@login_required
@check_shopify_config
def add_order_tags(order_id):
    """Siparise etiket ekle."""
    payload = request.get_json(silent=True) or {}
    tags = payload.get("tags", [])
    if not tags:
        return jsonify({"success": False, "error": "En az bir etiket gerekli."}), 400
    result = shopify_service.add_order_tags(order_id=order_id, tags=tags)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@shopify_bp.route("/api/products")
@check_shopify_config
def products():
    limit = request.args.get("limit", 20, type=int)
    query_filter = request.args.get("query")
    result = shopify_service.get_products(limit=limit, query_filter=query_filter)
    status_code = 200 if result.get("success") else 502
    return jsonify(result), status_code


@shopify_bp.route("/api/products/<product_id>")
@check_shopify_config
def product_detail(product_id):
    result = shopify_service.get_product(product_id)
    status_code = 200 if result.get("success") else 404
    return jsonify(result), status_code


@shopify_bp.route("/api/locations")
@check_shopify_config
def locations():
    limit = request.args.get("limit", 20, type=int)
    result = shopify_service.get_locations(limit=limit)
    status_code = 200 if result.get("success") else 502
    return jsonify(result), status_code


@shopify_bp.route("/api/inventory/adjust", methods=["POST"])
@check_shopify_config
def adjust_inventory():
    payload = request.get_json(silent=True) or {}
    inventory_item_id = payload.get("inventory_item_id")
    location_id = payload.get("location_id")
    delta = payload.get("delta")

    if inventory_item_id in (None, "") or location_id in (None, "") or delta is None:
        return jsonify({
            "success": False,
            "message": "inventory_item_id, location_id ve delta zorunludur.",
        }), 400

    result = shopify_service.adjust_inventory(
        inventory_item_id=inventory_item_id,
        location_id=location_id,
        delta=int(delta),
        reason=payload.get("reason", "correction"),
    )
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@shopify_bp.route("/api/graphql", methods=["POST"])
@check_shopify_config
def graphql_proxy():
    payload = request.get_json(silent=True) or {}
    query = payload.get("query")
    variables = payload.get("variables")

    if not query:
        return jsonify({
            "success": False,
            "message": "query alanı zorunludur.",
        }), 400

    result = shopify_service.run_graphql(query=query, variables=variables)
    status_code = 200 if result.get("success") else 502
    return jsonify(result), status_code


# ════════════════════════════════════════════════════════════════════
# SHOPIFY STOK SENKRONİZASYON ROUTE'LARI
# ════════════════════════════════════════════════════════════════════

@shopify_bp.route("/stock")
@login_required
def stock_sync_dashboard():
    """Shopify stok senkronizasyon sayfası."""
    configured = ShopifyConfig.is_configured()
    stats = shopify_stock_service.get_stats() if configured else {}
    return render_template("shopify/stock_sync.html", configured=configured, stats=stats)


@shopify_bp.route("/api/match-barcodes", methods=["POST"])
@login_required
@check_shopify_config
def match_barcodes():
    """Shopify barkodlarını panel barkodlarıyla eşleştir."""
    try:
        result = shopify_stock_service.match_barcodes()
        return jsonify(result)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@shopify_bp.route("/api/push-stock", methods=["POST"])
@login_required
@check_shopify_config
def push_stock():
    """Stokları Shopify'a gönder."""
    try:
        payload = request.get_json(silent=True) or {}
        barcodes = payload.get("barcodes")  # None ise tümü gönderilir
        result = shopify_stock_service.push_stock(barcodes=barcodes)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@shopify_bp.route("/api/mappings")
@login_required
@check_shopify_config
def get_mappings():
    """Eşleştirme listesini döndür."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    search = request.args.get("search", "").strip()
    result = shopify_stock_service.get_mappings(page=page, per_page=per_page, search=search)
    return jsonify(result)


@shopify_bp.route("/api/stats")
@login_required
@check_shopify_config
def get_stats():
    """Dashboard istatistikleri."""
    stats = shopify_stock_service.get_stats()
    return jsonify(stats)


@shopify_bp.route("/api/unmatched-csv")
@login_required
@check_shopify_config
def unmatched_csv():
    """Eşleşmeyen ürünleri CSV olarak indir."""
    from flask import Response
    import csv
    import io

    items = shopify_stock_service.get_unmatched_items()
    if not items:
        return jsonify({"success": False, "error": "Önce barkod eşleştirmesi yapın."}), 400

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Ürün Adı", "Varyant", "SKU", "Barkod", "Variant ID"])
    for item in items:
        writer.writerow([
            item.get("product_title", ""),
            item.get("variant_title", ""),
            item.get("sku", ""),
            item.get("barcode", ""),
            item.get("variant_id", ""),
        ])

    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=shopify_unmatched.csv"},
    )