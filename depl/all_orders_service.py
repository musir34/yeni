# all_orders_service.py
from flask import Blueprint, render_template, request
from sqlalchemy import union_all, select, literal
from models import db, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled

all_orders_service_bp = Blueprint('all_orders_service', __name__)

def all_orders_union():
    """
    Tüm statü tablolarını ortak kolonlarda UNION ALL yaparak tek sorgu döndürüyor.
    Kolon isimlerini aynı label ile seçiyoruz ki birleştirme sorunsuz olsun.
    """

    # 1) Her tablo için seçilecek kolonlar
    c = db.session.query(
        OrderCreated.order_number.label('order_number'),
        OrderCreated.order_date.label('order_date'),
        OrderCreated.merchant_sku.label('merchant_sku'),
        OrderCreated.product_barcode.label('product_barcode'),
        literal('Created').label('tablo')
    )

    p = db.session.query(
        OrderPicking.order_number.label('order_number'),
        OrderPicking.order_date.label('order_date'),
        OrderPicking.merchant_sku.label('merchant_sku'),
        OrderPicking.product_barcode.label('product_barcode'),
        literal('Picking').label('tablo')
    )

    s = db.session.query(
        OrderShipped.order_number.label('order_number'),
        OrderShipped.order_date.label('order_date'),
        OrderShipped.merchant_sku.label('merchant_sku'),
        OrderShipped.product_barcode.label('product_barcode'),
        literal('Shipped').label('tablo')
    )

    d = db.session.query(
        OrderDelivered.order_number.label('order_number'),
        OrderDelivered.order_date.label('order_date'),
        OrderDelivered.merchant_sku.label('merchant_sku'),
        OrderDelivered.product_barcode.label('product_barcode'),
        literal('Delivered').label('tablo')
    )

    x = db.session.query(
        OrderCancelled.order_number.label('order_number'),
        OrderCancelled.order_date.label('order_date'),
        OrderCancelled.merchant_sku.label('merchant_sku'),
        OrderCancelled.product_barcode.label('product_barcode'),
        literal('Cancelled').label('tablo')
    )

    # 2) UNION ALL
    union_query = c.union_all(p, s, d, x)

    return union_query
