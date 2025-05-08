from flask import Blueprint, render_template, request, send_file
from flask_sqlalchemy import SQLAlchemy
from PIL import Image, ImageDraw, ImageFont
import barcode
from barcode.writer import ImageWriter
import os
import io



product_label_bp = Blueprint('product_label', __name__)


@product_label_bp.route('/product_label', methods=['GET', 'POST'])
def generate_product_label():
    if request.method == 'POST':
        barcode_number = request.form.get('barcode')
        if not barcode_number:
            return "Barkod numarası gerekli.", 400

        # Veritabanından ürünü çek
        product = Product.query.filter_by(barcode=barcode_number).first()
        if not product:
            return "Ürün bulunamadı.", 404

        # Ürün bilgileri
        model_code = product.product_main_id or 'Model Bilinmiyor'
        color = product.color or 'Renk Bilinmiyor'
        size = product.size or 'Beden Bilinmiyor'

        # Barkod türünü seç (örneğin Code128)
        barcode_type = 'code128'

        # Barkodu oluştur
        barcode_class = barcode.get_barcode_class(barcode_type)
        barcode_instance = barcode_class(barcode_number, writer=ImageWriter())

        # Barkodu hafızada tutmak için BytesIO kullan
        barcode_bytes = io.BytesIO()
        barcode_instance.write(barcode_bytes)
        barcode_bytes.seek(0)
        barcode_image = Image.open(barcode_bytes)

        # Barkodun altına ürün bilgilerini ekle
        draw = ImageDraw.Draw(barcode_image)

        # Yazı tipi ve boyutu
        try:
            font_path = os.path.join('static', 'fonts', 'arial.ttf')
            font = ImageFont.truetype(font_path, 14)
        except IOError:
            font = ImageFont.load_default()

        # Ürün bilgisini hazırlama
        product_info = f"Model: {model_code}\nRenk: {color}\nBeden: {size}"

        # Metnin boyutunu al
        text_width, text_height = draw.multiline_textsize(product_info, font=font)

        # Yeni bir görüntü oluştur (barkod + metin)
        total_height = barcode_image.height + text_height + 10  # 10 piksel boşluk
        total_width = max(barcode_image.width, text_width)
        combined_image = Image.new('RGB', (total_width, total_height), 'white')

        # Barkod görüntüsünü yeni görüntüye yapıştır
        combined_image.paste(barcode_image, (0, 0))

        # Metni yeni görüntüye çiz
        text_position = (10, barcode_image.height + 5)  # 5 piksel boşluk
        draw = ImageDraw.Draw(combined_image)
        draw.multiline_text(text_position, product_info, font=font, fill="black")

        # Görüntüyü hafızada tutmak için BytesIO kullan
        output = io.BytesIO()
        combined_image.save(output, format='PNG')
        output.seek(0)

        return send_file(output, mimetype='image/png', as_attachment=True, attachment_filename=f'{barcode_number}_label.png')

    # GET isteği için formu render et
    return render_template('product_label_form.html')
