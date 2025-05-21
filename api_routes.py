from flask import Blueprint, jsonify, request
from models import Product

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/product', methods=['GET'])
def get_product():
    """
    Barkod numarasına göre ürün bilgilerini döndürür
    """
    barcode = request.args.get('barcode')
    if not barcode:
        return jsonify({"success": False, "message": "Barkod parametresi gerekli"}), 400
    
    product = Product.query.filter_by(barcode=barcode).first()
    if not product:
        return jsonify({"success": False, "message": "Ürün bulunamadı"}), 404
    
    # Ürün bilgilerini döndür
    return jsonify({
        "success": True,
        "product": {
            "id": product.id,
            "barcode": product.barcode,
            "product_main_id": product.product_main_id,
            "color": product.color,
            "size": product.size,
            "price_try": product.price_try,
            "stock": product.stock,
            "image_path": product.image_path if product.image_path else "/static/images/default-product.jpg"
        }
    })

@api_bp.route('/products/search', methods=['GET'])
def search_products():
    """
    Ürünleri arama (barkod, model, renk, beden)
    """
    barcode = request.args.get('barcode')
    model = request.args.get('model')
    color = request.args.get('color')
    size = request.args.get('size')
    
    query = Product.query
    
    if barcode:
        query = query.filter(Product.barcode.ilike(f'%{barcode}%'))
    if model:
        query = query.filter(Product.product_main_id.ilike(f'%{model}%'))
    if color:
        query = query.filter(Product.color.ilike(f'%{color}%'))
    if size:
        query = query.filter(Product.size.ilike(f'%{size}%'))
    
    # Sonuçları sınırla
    products = query.limit(50).all()
    
    return jsonify({
        "success": True,
        "products": [{
            "id": p.id,
            "barcode": p.barcode,
            "product_main_id": p.product_main_id,
            "color": p.color,
            "size": p.size,
            "price_try": p.price_try,
            "stock": p.stock
        } for p in products]
    })