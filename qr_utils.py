from flask import Blueprint, render_template, request, jsonify
import qrcode
import os

qr_utils_bp = Blueprint('qr_utils', __name__)

@qr_utils_bp.route('/generate_qr', methods=['GET'])
def generate_qr():
    """
    Trendyol'dan gelen barkod ile QR kod oluştur ve döndür.
    """
    barcode = request.args.get('barcode', '').strip()
    if not barcode:
        return jsonify({'success': False, 'message': 'Barkod eksik!'})

    # QR kod oluşturma
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=7,
        border=3,
    )
    qr.add_data(barcode)
    qr.make(fit=True)

    # QR kodu kaydet
    qr_dir = os.path.join('static', 'qr_codes')
    os.makedirs(qr_dir, exist_ok=True)
    qr_path = os.path.join(qr_dir, f"{barcode}.png")
    qr.make_image(fill_color="black", back_color="white").save(qr_path)

    # QR kod görselinin göreli yolunu döndür
    return jsonify({'success': True, 'qr_code_path': f"/static/qr_codes/{barcode}.png"})
