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
import qrcode

import barcode
from barcode.writer import ImageWriter
from flask import (
    Blueprint,
    abort,
    current_app,
    render_template,
    request,
    send_file,
    jsonify
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
        return render_template("product_label.html")

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

    canvas = Image.new("RGB", (int(canvas_w), int(canvas_h)), "white")
    # Barkodu ortala
    barcode_x = int((canvas_w - barcode_img.width) // 2)
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
    
# --------------------------------------------------------------------------- #
# QR Kod Oluşturma
# --------------------------------------------------------------------------- #

@product_label_bp.route("/generate_qr")
def generate_qr():
    """
    QR kod görselini PNG olarak döndür
    Parametre: data (URL ile geçilir)
    """
    data = request.args.get("data")
    if not data:
        abort(400, description="QR kodu için veri gerekli.")
    
    # QR kodu oluştur
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    # QR görselini PNG olarak oluştur
    img = qr.make_image(fill_color="black", back_color="white")
    
    # PNG dosyasını bellekte oluştur
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    
    return send_file(
        buffer,
        mimetype="image/png"
    )

# --------------------------------------------------------------------------- #
# Model Ürün Arama
# --------------------------------------------------------------------------- #

@product_label_bp.route("/get_product_details/<model_code>")
def get_product_details(model_code):
    """
    Model koduna göre renk ve beden-barkod eşleştirmelerini döndürür
    """
    products = Product.query.filter_by(product_main_id=model_code).all()
    
    if not products:
        return jsonify({"success": False, "message": "Ürün bulunamadı"})
    
    # Modele ait tüm benzersiz renkleri al
    colors = list(set(p.color for p in products if p.color))
    
    # Renk ve beden-barkod eşleştirmelerini yap
    product_data = {}
    for color in colors:
        product_data[color] = {}
        color_products = [p for p in products if p.color == color]
        for product in color_products:
            # Bedenleri string olarak kaydet (JSON'da keyler string olmalı)
            if product.size and product.barcode:
                try:
                    # Bedeni float'a çevirip sonra int'e çevirerek .0 kısmını at
                    size_key = str(int(float(product.size)))
                    product_data[color][size_key] = product.barcode
                except (ValueError, TypeError):
                    # Eğer beden numerik değilse, olduğu gibi string olarak kaydet
                    product_data[color][str(product.size)] = product.barcode
    
    return jsonify({"success": True, "data": product_data})
