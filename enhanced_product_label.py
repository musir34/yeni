from flask import Blueprint, render_template, request, jsonify
import os
import qrcode
from PIL import Image, ImageDraw, ImageFont
from models import Product, db
from sqlalchemy import func
import logging
import time

# --- Blueprint ve Logger Kurulumu ---
enhanced_label_bp = Blueprint('enhanced_label', __name__)
logger = logging.getLogger(__name__)

# --- Genel Ayarlar ve Sabitler ---
DPI = 300
FONT_PATH = "static/fonts/DejaVuSans.ttf"
FONT_BOLD_PATH = "static/fonts/DejaVuSans-Bold.ttf"
LOGO_PATH = os.path.join('static', 'logos', 'gullu_logo.png')

# --- Yardımcı Fonksiyonlar ---

def find_product_image(model_id, color):
    """Ürün görselini model ve renge göre arar, büyük/küçük harf duyarsız."""
    images_folder = os.path.join('static', 'images')
    color_variations = [color, color.lower(), color.upper(), color.capitalize()]
    for c_var in color_variations:
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            path = os.path.join(images_folder, f"{model_id}_{c_var}{ext}")
            if os.path.exists(path):
                return path
    default_path = os.path.join(images_folder, "default_product.jpg")
    if os.path.exists(default_path):
        logger.warning(f"Görsel bulunamadı: {model_id}/{color}. Varsayılan kullanılıyor.")
        return default_path
    return None

def create_qr_with_logo(data, logo_path=None, size_px=200):
    """Verilen data ve opsiyonel logo ile bir QR kod PIL Image nesnesi oluşturur."""
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(str(data))
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGBA')
        if logo_path and os.path.exists(logo_path):
            with Image.open(logo_path) as logo:
                logo = logo.convert("RGBA")
                logo_size_ratio = 0.25
                logo.thumbnail((int(qr_img.width * logo_size_ratio), int(qr_img.height * logo_size_ratio)), Image.Resampling.LANCZOS)
                bg_w, bg_h = logo.width + 6, logo.height + 6
                background = Image.new('RGBA', (bg_w, bg_h), (255, 255, 255, 255))
                bg_pos = ((bg_w - logo.width) // 2, (bg_h - logo.height) // 2)
                background.paste(logo, bg_pos, logo)
                paste_pos = ((qr_img.width - bg_w) // 2, (qr_img.height - bg_h) // 2)
                qr_img.paste(background, paste_pos, background)
        return qr_img.convert('RGB').resize((size_px, size_px), Image.Resampling.LANCZOS)
    except Exception as e:
        logger.error(f"QR kod oluşturma hatası: {e}", exc_info=True)
        return None

def create_fixed_label(product_data, width_mm, height_mm, dpi=DPI):
    """
    Verilen ürün bilgileriyle, sabit tasarımlı bir etiket oluşturur.
    """
    try:
        width_px = int((width_mm / 25.4) * dpi)
        height_px = int((height_mm / 25.4) * dpi)
        label = Image.new('RGB', (width_px, height_px), 'white')
        draw = ImageDraw.Draw(label)

        # Fontları yükle (boyutlar etiket yüksekliğine göre orantılı)
        try:
            font_regular = ImageFont.truetype(FONT_PATH, size=int(0.12 * height_px))
            font_bold = ImageFont.truetype(FONT_BOLD_PATH, size=int(0.14 * height_px))
        except IOError:
            font_regular = ImageFont.load_default()
            font_bold = ImageFont.load_default()

        # 1. Ürün Görseli (Solda)
        img_size = int(height_px * 0.9)
        img_x = int(width_px * 0.05)
        img_y = (height_px - img_size) // 2
        image_path = find_product_image(product_data.get('model_code'), product_data.get('color'))
        if image_path:
            try:
                with Image.open(image_path) as product_img:
                    product_img = product_img.convert("RGB").resize((img_size, img_size), Image.Resampling.LANCZOS)
                    label.paste(product_img, (img_x, img_y))
            except Exception as img_error:
                logger.error(f"Ürün resmi işlenemedi: {image_path}, Hata: {img_error}")

        # 2. QR Kod (Sağda)
        qr_size = int(height_px * 0.85)
        qr_x = width_px - qr_size - int(width_px * 0.05)
        qr_y = (height_px - qr_size) // 2
        qr_img = create_qr_with_logo(product_data.get('barcode', 'N/A'), LOGO_PATH, qr_size)
        if qr_img:
            label.paste(qr_img, (qr_x, qr_y))

        # 3. Metinler (Ortada)
        text_area_start_x = img_x + img_size
        text_area_width = qr_x - text_area_start_x

        y_positions = [height_px * 0.15, height_px * 0.38, height_px * 0.61]

        texts_to_draw = [
            (str(product_data.get('model_code', '')), font_bold),
            (str(product_data.get('color', '')), font_regular),
            (str(product_data.get('size', '')), font_regular)
        ]

        for i, (text, font) in enumerate(texts_to_draw):
            text_bbox = draw.textbbox((0, 0), text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_x = text_area_start_x + (text_area_width - text_width) // 2
            draw.text((text_x, y_positions[i]), text, fill='black', font=font)

        return label
    except Exception as e:
        logger.error(f"Sabit etiket oluşturma hatası: {e}", exc_info=True)
        return Image.new('RGB', (100, 100), 'red')

# --- Rotalar ---

@enhanced_label_bp.route('/enhanced_product_label')
def main_label_page():
    """Ana etiket arama ve yazdırma sayfası."""
    return render_template('enhanced_product_label_simple.html')

@enhanced_label_bp.route('/api/search_products_for_label', methods=['GET'])
def search_products_for_label():
    """Ürünleri model koduna göre arar."""
    query = request.args.get('query', '').strip()
    if not query:
        return jsonify({'success': False, 'message': 'Arama sorgusu gerekli'}), 400
    try:
        products = Product.query.filter(Product.product_main_id.ilike(f'%{query}%')).all()
        if not products:
            return jsonify({'success': False, 'message': 'Bu modele ait ürün bulunamadı'}), 404

        grouped = {}
        for p in products:
            key = f"{p.product_main_id}_{p.color}"
            if key not in grouped:
                grouped[key] = {'model_id': p.product_main_id, 'color': p.color, 'variants': []}
            grouped[key]['variants'].append({'barcode': p.barcode, 'size': p.size, 'quantity': p.quantity or 0})

        return jsonify({'success': True, 'products': list(grouped.values())})
    except Exception as e:
        logger.error(f"Ürün arama hatası: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Sunucu hatası oluştu'}), 500

@enhanced_label_bp.route('/api/print_labels', methods=['POST'])
def print_labels():
    """
    Seçilen ürünleri, sabit 60x40mm tasarımla A4 kağıdına 21 adet sığacak şekilde PDF olarak basar.
    """
    try:
        data = request.get_json()
        labels_to_print = data.get('labels')
        if not labels_to_print:
            return jsonify({'success': False, 'message': 'Yazdırılacak etiket seçilmedi.'}), 400

        logger.info(f"{len(labels_to_print)} adet etiket için yazdırma işlemi başlatıldı.")

        # Kurallar: A4, 3x7=21 etiket, her etiket 60x40mm
        cols, rows = 3, 7
        label_width_mm, label_height_mm = 60, 40
        page_width_mm, page_height_mm = 210, 297

        # Kenar boşluklarını, etiketlerin sayfaya tam sığması için hesapla
        gap_x_mm, gap_y_mm = 2, 1 # Sütun ve satır arası boşluklar
        margin_x_total = page_width_mm - (cols * label_width_mm) - ((cols - 1) * gap_x_mm)
        margin_left_mm = margin_x_total / 2
        margin_y_total = page_height_mm - (rows * label_height_mm) - ((rows - 1) * gap_y_mm)
        margin_top_mm = margin_y_total / 2

        if margin_left_mm < 0 or margin_top_mm < 0:
            return jsonify({'success': False, 'message': '60x40mm etiketler bu düzende A4\'e sığmıyor.'}), 500

        page_width_px = int((page_width_mm / 25.4) * DPI)
        page_height_px = int((page_height_mm / 25.4) * DPI)

        all_pages = []
        labels_per_page = cols * rows
        total_pages = (len(labels_to_print) + labels_per_page - 1) // labels_per_page

        for page_num in range(total_pages):
            current_page = Image.new('RGB', (page_width_px, page_height_px), 'white')
            start_idx = page_num * labels_per_page
            page_labels_data = labels_to_print[start_idx : start_idx + labels_per_page]

            for i, product_data in enumerate(page_labels_data):
                label_img = create_fixed_label(product_data, label_width_mm, label_height_mm)

                row_num, col_num = divmod(i, cols)
                margin_x_px = int((margin_left_mm / 25.4) * DPI)
                margin_y_px = int((margin_top_mm / 25.4) * DPI)
                gap_x_px = int((gap_x_mm / 25.4) * DPI)
                gap_y_px = int((gap_y_mm / 25.4) * DPI)

                x = margin_x_px + col_num * (label_img.width + gap_x_px)
                y = margin_y_px + row_num * (label_img.height + gap_y_px)

                current_page.paste(label_img, (x, y))

            all_pages.append(current_page)

        os.makedirs('static/generated', exist_ok=True)
        filename = f"etiketler_{int(time.time())}.pdf"
        filepath = os.path.join('static', 'generated', filename)

        if all_pages:
            all_pages[0].save(filepath, "PDF", resolution=DPI, save_all=True, append_images=all_pages[1:])
            return jsonify({'success': True, 'image_url': f"/static/generated/{filename}"})
        else:
            return jsonify({'success': False, 'message': 'Yazdırılacak sayfa oluşturulamadı.'}), 500

    except Exception as e:
        logger.error(f"Çoklu etiket yazdırma hatası: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Yazdırma hatası: {e}'}), 500