# new_orders_service.py
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, send_file
from models import db, OrderCreated, RafUrun, Product
import json
import traceback
import io
from datetime import datetime
from qr_utils import qr_utils_bp  # routes/__init__.py bu modülden export ediyor

new_orders_service_bp = Blueprint('new_orders_service', __name__)


def _parse_details(order):
    """OrderCreated.details alanını güvenli şekilde liste olarak döndürür."""
    if not order.details:
        return []
    try:
        items = json.loads(order.details) if isinstance(order.details, str) else order.details
        return items if isinstance(items, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _build_shelf_groups():
    """
    Yeni (OrderCreated) statüsündeki TÜM tek ürünlü siparişleri raf bazında gruplar.
    Dönüş: [(raf_kodu, [{'order_number', 'model_code', 'color', 'size', 'barcode'}, ...]), ...]
            Alfabetik raf sırasına göre.
    """
    new_orders = OrderCreated.query.order_by(OrderCreated.order_date.asc()).all()

    # Önce tüm barkodları toplayıp Product'ları tek sorguda çekelim
    all_barcodes = set()
    order_items = []  # [(order, item_dict)]

    for order in new_orders:
        details = _parse_details(order)
        # Sadece TEK ürünlü siparişler
        if len(details) != 1:
            continue
        item = details[0]
        barcode = item.get('barcode', '')
        if barcode:
            all_barcodes.add(barcode)
        order_items.append((order, item, barcode))

    # Ürün bilgilerini toplu çek
    products_dict = {}
    if all_barcodes:
        products = Product.query.filter(Product.barcode.in_(list(all_barcodes))).all()
        products_dict = {p.barcode: p for p in products}

    # Raf bilgilerini toplu çek (en çok stoklu raf önce)
    raf_dict = {}  # barcode -> raf_kodu
    if all_barcodes:
        rafs = (RafUrun.query
                .filter(RafUrun.urun_barkodu.in_(list(all_barcodes)))
                .filter(RafUrun.adet > 0)
                .order_by(RafUrun.raf_kodu.asc(), RafUrun.adet.desc())
                .all())
        # Her barkod için ilk (en fazla stoklu) rafı tut
        for raf in rafs:
            if raf.urun_barkodu not in raf_dict:
                raf_dict[raf.urun_barkodu] = raf.raf_kodu

    # Grup oluştur
    shelf_groups = {}  # {raf_kodu: [item_dict, ...]}

    for order, item, barcode in order_items:
        product = products_dict.get(barcode)
        model_code = (product.product_main_id if product and product.product_main_id
                      else item.get('sku', 'N/A'))
        color = product.color if product and product.color else item.get('color', 'N/A')
        size = product.size if product and product.size else item.get('size', 'N/A')

        raf_kodu = raf_dict.get(barcode, 'RAF YOK')

        if raf_kodu not in shelf_groups:
            shelf_groups[raf_kodu] = []

        shelf_groups[raf_kodu].append({
            'order_number': order.order_number,
            'model_code': model_code,
            'color': color,
            'size': size,
            'barcode': barcode,
        })

    # Alfabetik raf sırası
    return sorted(shelf_groups.items(), key=lambda x: x[0])


@new_orders_service_bp.route('/prepare-new-orders', methods=['GET'])
def prepare_new_orders():
    """
    Yeni statüsündeki tek ürünlü siparişleri raf bazında gruplar ve ekranda gösterir.
    """
    try:
        sorted_shelves = _build_shelf_groups()
        total_orders = sum(len(items) for _, items in sorted_shelves)
        return render_template(
            'bulk_order_prepare.html',
            sorted_shelves=sorted_shelves,
            total_orders=total_orders,
        )
    except Exception as e:
        traceback.print_exc()
        return f"Bir hata oluştu: {e}", 500


@new_orders_service_bp.route('/prepare-new-orders/excel', methods=['GET'])
def prepare_new_orders_excel():
    """
    Yeni statüsündeki tek ürünlü siparişleri xlsx olarak indirir.
    Sütunlar: Model Kodu | Renk | Beden | Sipariş No
    Raf sırasına (alfabetik) göre sıralanmış.
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment

        sorted_shelves = _build_shelf_groups()

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Raf Toplama Listesi"

        # Başlık satırı (A1'den itibaren, boş satır/sütun yok)
        headers = ["Model Kodu", "Renk", "Beden", "Sipariş No"]
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="B76E79", end_color="B76E79", fill_type="solid")

        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        row_num = 2
        for raf_kodu, items in sorted_shelves:
            for item in items:
                ws.cell(row=row_num, column=1, value=item['model_code'])
                ws.cell(row=row_num, column=2, value=item['color'])
                ws.cell(row=row_num, column=3, value=item['size'])
                ws.cell(row=row_num, column=4, value=item['order_number'])
                row_num += 1
                if row_num > 2001:  # max 2000 veri satırı
                    break
            if row_num > 2001:
                break

        # Sütun genişliklerini otomatik ayarla
        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                try:
                    if cell.value:
                        max_len = max(max_len, len(str(cell.value)))
                except Exception:
                    pass
            ws.column_dimensions[col_letter].width = max(12, max_len + 2)

        # Belleğe kaydet
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"raf_toplama_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    except Exception as e:
        traceback.print_exc()
        return f"Excel oluşturulurken hata oluştu: {e}", 500
