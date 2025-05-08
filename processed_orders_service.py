from flask import Blueprint, render_template, request
from models import db, OrderPicking  # Artık Order yerine OrderPicking
from math import ceil  # veya "import math" da kullanabilirsiniz

processed_orders_service_bp = Blueprint('processed_orders_service', __name__)

@processed_orders_service_bp.route('/order-list/processed', methods=['GET'])
def get_processed_orders():
    """
    "İşleme Alındı" statüsündeki siparişler için,
    artık OrderPicking tablosunu kullandığımız senaryo.
    """
    page = int(request.args.get('page', 1))
    per_page = 50

    # OrderPicking tablosundan verileri çek; en güncel tarih en üstte
    orders_query = OrderPicking.query.order_by(OrderPicking.order_date.desc())

    # Flask-SQLAlchemy'nin paginate fonksiyonunu kullanarak sayfalama yapalım
    paginated_orders = orders_query.paginate(page=page, per_page=per_page, error_out=False)

    orders = paginated_orders.items
    total_orders_count = paginated_orders.total
    total_pages = paginated_orders.pages

    # (Opsiyonel) merchant_sku ve product_barcode'u detaylı gösterim için ayrıştır
    for order in orders:
        skus = order.merchant_sku.split(', ') if order.merchant_sku else []
        barcodes = order.product_barcode.split(', ') if order.product_barcode else []

        max_length = max(len(skus), len(barcodes))
        # Eksik elemanlar için boş string ekleyelim
        skus += [''] * (max_length - len(skus))
        barcodes += [''] * (max_length - len(barcodes))

        # 'order.details' öznitelik adı, template'te kolay döngü kurmak için
        order.details = [{'sku': s, 'barcode': b} for s, b in zip(skus, barcodes)]

    return render_template(
        'order_list.html',
        orders=orders,
        page=page,
        total_pages=total_pages,
        total_orders_count=total_orders_count
    )
