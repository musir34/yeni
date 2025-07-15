from flask import Blueprint
import os
import traceback
from barcode import get_barcode_class
from barcode.writer import ImageWriter
import re

barcode_utils_bp = Blueprint('barcode_utils', __name__)

def generate_barcode(shipping_barcode, width_mm=95, height_mm=24, dpi=300):
    if not shipping_barcode or not isinstance(shipping_barcode, str):
        print("❌ [generate_barcode] Barkod değeri boş veya geçersiz!")
        return None

    try:
        clean_code = re.sub(r'[^a-zA-Z0-9_-]', '_', shipping_barcode)
        print(f"📦 Barkod değeri: {shipping_barcode} → Temiz: {clean_code}")

        barcode_dir = os.path.join('static', 'barcodes')
        os.makedirs(barcode_dir, exist_ok=True)

        width_px = int((width_mm / 25.4) * dpi)
        height_px = int((height_mm / 25.4) * dpi)

        writer_options = {
            'module_width': 0.4,
            'module_height': height_mm,
            'font_size': 12,
            'text_distance': 5,
            'quiet_zone': 1.0,
            'dpi': dpi,
            'write_text': True,
            'format': 'PNG'
        }

        BarcodeClass = get_barcode_class('code128')
        barcode_obj = BarcodeClass(clean_code, writer=ImageWriter())
        full_path = os.path.join(barcode_dir, clean_code)
        saved_path = barcode_obj.save(full_path, options=writer_options)

        print(f"✅ Barkod oluşturuldu: {saved_path}")
        return f"barcodes/{clean_code}.png"

    except Exception as e:
        print(f"🔥 [generate_barcode] HATA: {e}")
        traceback.print_exc()
        return None
