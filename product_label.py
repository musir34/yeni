"""
product_label.py
Ürün barkod + bilgi etiketi üretimi (PNG olarak indirme).

Blueprint: product_label_bp
GET  → form
POST → etiket üret ve indir
"""

from __future__ import annotations

import io
import os

import barcode
from barcode.writer import ImageWriter
from flask import (
    Blueprint,
    abort,
    current_app,
    render_template,
    request,
    send_file,
)
from PIL import Image, ImageDraw, ImageFont

from models import Product  # db’ye ihtiyaç yok, sadece sorgu

# --------------------------------------------------------------------------- #
# Blueprint
# --------------------------------------------------------------------------- #

product_label_bp = Blueprint(
    "product_label_bp",
    __name__,
    url_prefix="/product_label",  # → /product_label/ …
)

# --------------------------------------------------------------------------- #
# Yardımcı – metin ölçümü (Pillow 9 & 10 uyumlu)
# --------------------------------------------------------------------------- #


def _multiline_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont):
    """Pillow 10+ için multiline_textbbox, önceki sürümler için multiline_textsize."""
    try:  # Pillow ≥10
        bbox = draw.multiline_textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        return width, height
    except AttributeError:  # Pillow <10
        return draw.multiline_textsize(text, font=font)


# --------------------------------------------------------------------------- #
# Route
# --------------------------------------------------------------------------- #


@product_label_bp.route("/", methods=["GET", "POST"])
def generate_product_label():
    # ------------------------------ GET ------------------------------ #
    if request.method == "GET":
        # Eğer print_option parametresi varsa doğrudan yazdırma yapacağız
        if request.args.get('print_option', '') == 'custom':
            barcode_number = request.args.get('barcode', '').strip()
            template_id = request.args.get('template', 'etiket_67x41')
            layout_id = request.args.get('layout', 'standart')
            
            if not barcode_number:
                abort(400, description="Barkod numarası gerekli.")
                
            product = Product.query.filter_by(barcode=barcode_number).first()
            if product is None:
                abort(404, description="Ürün bulunamadı.")
                
            # Barkod bilgilerini hazırla
            barcodes = [{
                "barcode": barcode_number,
                "model": product.product_main_id or "Model Bilinmiyor",
                "color": product.color or "Renk Bilinmiyor",
                "size": product.size or "Beden Bilinmiyor",
                "qr_path": generate_and_save_qr_code(barcode_number),
                "print_count": 1,
                "is_printed": False
            }]
            
            # Barcode_print_service'ın print endpoint'ini kullanarak yazdır
            from barcode_print_service import generate_single_barcode_html, LABEL_TEMPLATES
            template = LABEL_TEMPLATES.get(template_id, LABEL_TEMPLATES['etiket_67x41'])
            html_content = generate_single_barcode_html(barcodes[0], template, layout_id)
            
            return html_content
        else:
            # Yazdırma ayarları sayfasını göster
            barcode = request.args.get('barcode', '').strip()
            model = request.args.get('model', '').strip()
            color = request.args.get('color', '').strip()
            size = request.args.get('size', '').strip()
            
            # Barkod yazdırma ayarları sayfasını göster
            from barcode_print_service import LABEL_TEMPLATES, LAYOUT_TEMPLATES
            return render_template("product_label_settings.html", 
                                 barcode=barcode,
                                 model=model,
                                 color=color,
                                 size=size,
                                 templates=LABEL_TEMPLATES,
                                 layouts=LAYOUT_TEMPLATES)

    # ------------------------------ POST ----------------------------- #
    barcode_number: str = (request.form.get("barcode") or "").strip()
    if not barcode_number:
        abort(400, description="Barkod numarası gerekli.")

    product: Product | None = Product.query.filter_by(barcode=barcode_number).first()
    if product is None:
        abort(404, description="Ürün bulunamadı.")

    # Ürün bilgileri
    model_code = product.product_main_id or "Model Bilinmiyor"
    color = product.color or "Renk Bilinmiyor"
    size = product.size or "Beden Bilinmiyor"

    # -------------------- Barkod görselini oluştur ------------------- #
    try:
        barcode_cls = barcode.get_barcode_class("code128")
        tmp = io.BytesIO()
        barcode_cls(barcode_number, writer=ImageWriter()).write(tmp)
        tmp.seek(0)
        barcode_img = Image.open(tmp)
    except Exception as exc:  # pragma: no cover
        abort(500, description=f"Barkod üretilemedi: {exc}")

    # ----------------------------- Font ------------------------------ #
    font_path = os.path.join(current_app.root_path, "static", "fonts", "arial.ttf")
    try:
        font = ImageFont.truetype(font_path, 14)
    except IOError:
        font = ImageFont.load_default()

    product_info = f"Model: {model_code}\nRenk: {color}\nBeden: {size}"

    # -------------------- Tuval boyutunu hesapla --------------------- #
    draw_tmp = ImageDraw.Draw(barcode_img)
    text_w, text_h = _multiline_size(draw_tmp, product_info, font)

    padding = 20  # üst-alt toplam
    canvas_w = max(barcode_img.width, text_w + 20)
    canvas_h = barcode_img.height + text_h + padding

    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
    # Barkodu ortala
    barcode_x = (canvas_w - barcode_img.width) // 2
    canvas.paste(barcode_img, (barcode_x, 0))

    # Metni çiz
    draw = ImageDraw.Draw(canvas)
    text_x = 10
    text_y = barcode_img.height + 10
    draw.multiline_text((text_x, text_y), product_info, font=font, fill="black")

    # ------------------------- PNG’ye kaydet ------------------------- #
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    out.seek(0)

    filename = f"{barcode_number}_label.png"
    return send_file(
        out,
        mimetype="image/png",
        as_attachment=True,
        download_name=filename,  # Flask ≥2.0
    )
