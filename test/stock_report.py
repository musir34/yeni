
from flask import Blueprint, render_template
from models import Product
from sqlalchemy import func

stock_report_bp = Blueprint('stock_report', __name__)

@stock_report_bp.route('/stock-report')
def stock_report():
    # Stok durumunu grupla ve hesapla
    stock_stats = Product.query.with_entities(
        Product.product_main_id,
        Product.color,
        Product.size,
        func.sum(Product.quantity).label('total_stock')
    ).group_by(
        Product.product_main_id,
        Product.color,
        Product.size
    ).all()
    
    return render_template('stock_report.html', stock_stats=stock_stats)
