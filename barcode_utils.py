from flask import Blueprint
import os
import traceback
from barcode import Code128
from barcode.writer import ImageWriter
import re


barcode_utils_bp = Blueprint('barcode_utils', __name__)

def generate_barcode(shipping_barcode, width_mm=80, height_mm=20, dpi=300):
    """
    Barkod PNG dosyasını üretir. Ölçüler mm cinsindendir.
    """
    if not shipping_barcode:
        print("❌ [generate_barcode] Barkod değeri boş!")
        return None

    try:
        # Barkod adını güvenli hale getir
        clean_code = re.sub(r'[^a-zA-Z0-9_-]', '_', shipping_barcode)
        print(f"📦 Barkod değeri: {shipping_barcode} → Temiz: {clean_code}")

        # Kayıt klasörü
        barcode_dir = os.path.join('static', 'barcodes')
        os.makedirs(barcode_dir, exist_ok=True)
        print(f"📁 Barkod dizini oluşturuldu: {barcode_dir}")

        # mm → pixel dönüşüm (inch = mm / 25.4)
        width_px = int((width_mm / 25.4) * dpi)
        height_px = int((height_mm / 25.4) * dpi)

        # Barkod yazıcı ayarları
        writer_options = {
            'module_width': 0.35,          # Çizgi kalınlığı
            'module_height': 15.0,  # Çizgi yüksekliği (inch)
            'font_size': 10,
            'text_distance': 5,           # Barkod ile yazı arası
            'quiet_zone': 4.0,            # Sağ/sol boşluk (inch)
            'dpi': dpi,
            'write_text': True,
            'format': 'PNG'
        }

        barcode_obj = Code128(clean_code, writer=ImageWriter())
        full_path = os.path.join(barcode_dir, clean_code)
        saved_path = barcode_obj.save(full_path, options=writer_options)

        print(f"✅ Barkod başarıyla kaydedildi: {saved_path}")
        return f"barcodes/{clean_code}.png"

    except Exception as e:
        print(f"🔥 [generate_barcode] Barkod oluşturma hatası: {e}")
        traceback.print_exc()
        return None