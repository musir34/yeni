from flask import Blueprint, render_template_string, request
from models import Product

woo_preview_bp = Blueprint('woo_preview', __name__)

TEMPLATE = '''
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Woo Barcode Preview</title>
<style>table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:8px}</style>
</head>
<body>
<h2>Woo Product Barcode Preview</h2>
<p>Showing first {{limit}} products (use ?limit=N)</p>
<table>
  <tr><th>#</th><th>barcode</th><th>product_title</th><th>product_id (woo_product_id)</th><th>woo_barcode</th></tr>
  {% for p in products %}
  <tr>
    <td>{{loop.index}}</td>
    <td>{{p.barcode}}</td>
    <td>{{p.title}}</td>
    <td>{{p.woo_product_id or ''}}</td>
    <td>{{p.woo_barcode or ''}}</td>
  </tr>
  {% endfor %}
</table>
</body>
</html>
'''

@woo_preview_bp.route('/site/woo-barcodes')
def preview():
    try:
        limit = int(request.args.get('limit', 200))
    except ValueError:
        limit = 200
    products = Product.query.order_by(Product.barcode).limit(limit).all()
    return render_template_string(TEMPLATE, products=products, limit=limit)
