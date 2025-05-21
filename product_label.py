"""
product_label.py
Çok fonksiyonlu ürün etiket üretimi (PNG/PDF olarak indirme).

Blueprint: product_label_bp
GET  → form
POST → etiket üret ve indir

Özellikler:
- Tek, çift veya çoklu etiket oluşturma
- Özel etiket boyutu ayarlama
- A4, A5, Letter ve özel kağıt boyutları
- PNG veya PDF çıktı formatı
"""

from __future__ import annotations

import io
import math
import os
from typing import List, Optional, Tuple, Dict, Any

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
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5, LETTER, portrait
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from models import Product  # db'ye ihtiyaç yok, sadece sorgu

# --------------------------------------------------------------------------- #
# Blueprint
# --------------------------------------------------------------------------- #

product_label_bp = Blueprint(
    "product_label_bp",
    __name__,
    url_prefix="/product_label",  # → /product_label/ …
)

# --------------------------------------------------------------------------- #
# Yardımcı fonksiyonlar ve sabitler
# --------------------------------------------------------------------------- #

# Standart kağıt boyutları (mm)
PAPER_SIZES = {
    "a4": (210, 297),  # A4
    "a5": (148, 210),  # A5
    "letter": (216, 279),  # Letter
}

# DPI değeri (çözünürlük)
DEFAULT_DPI = 300


def _multiline_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont):
    """Pillow 10+ için multiline_textbbox, önceki sürümler için multiline_textsize."""
    try:  # Pillow ≥10
        bbox = draw.multiline_textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        return width, height
    except AttributeError:  # Pillow <10
        return draw.multiline_textsize(text, font=font)


def mm_to_px(mm_val: float, dpi: int = DEFAULT_DPI) -> int:
    """Milimetreyi piksel'e çevirir."""
    return int(mm_val * dpi / 25.4)


def get_page_size(paper_size: str) -> Optional[Tuple[float, float]]:
    """Kağıt boyutunu döndürür (genişlik, yükseklik) mm cinsinden."""
    return PAPER_SIZES.get(paper_size.lower())


def get_reportlab_pagesize(paper_size: str) -> Tuple[float, float]:
    """ReportLab için sayfa boyutunu döndürür."""
    if paper_size.lower() == "a4":
        return A4
    elif paper_size.lower() == "a5":
        return A5
    elif paper_size.lower() == "letter":
        return LETTER
    else:
        # Özel boyutlar için mm'yi ReportLab ölçülerine çevir
        width_mm, height_mm = paper_size.split("x")
        return float(width_mm) * mm, float(height_mm) * mm


# --------------------------------------------------------------------------- #
# Etiket oluşturma fonksiyonları
# --------------------------------------------------------------------------- #


def create_single_label_image(
    product: Product,
    label_width_mm: float,
    label_height_mm: float,
    margin_mm: float,
    font_size: int,
    include_price: bool,
    dpi: int = DEFAULT_DPI,
) -> Image.Image:
    """Tek bir ürün etiketi görselini oluşturur."""
    # Ürün bilgileri
    barcode_number = product.barcode
    model_code = product.product_main_id or "Model Bilinmiyor"
    color = product.color or "Renk Bilinmiyor"
    size = product.size or "Beden Bilinmiyor"
    price = getattr(product, "price", None)

    # Piksel cinsinden boyutlar
    label_width_px = mm_to_px(label_width_mm, dpi)
    label_height_px = mm_to_px(label_height_mm, dpi)
    margin_px = mm_to_px(margin_mm, dpi)

    # Tuval oluştur
    canvas_img = Image.new("RGB", (label_width_px, label_height_px), "white")
    draw = ImageDraw.Draw(canvas_img)

    # Barkod görselini oluştur
    try:
        barcode_cls = barcode.get_barcode_class("code128")
        tmp = io.BytesIO()
        barcode_options = {
            'module_width': 0.2,
            'module_height': 6.0,
            'quiet_zone': 1.0,
            'font_size': 8,
            'text_distance': 1.0,
        }
        barcode_cls(barcode_number, writer=ImageWriter()).write(tmp, options=barcode_options)
        tmp.seek(0)
        barcode_img = Image.open(tmp)
    except Exception as exc:  # pragma: no cover
        abort(500, description=f"Barkod üretilemedi: {exc}")

    # Barkod görselini ölçeklendir
    barcode_height = int(label_height_px * 0.35)  # Etiketin %35'i kadar yükseklik
    barcode_ratio = barcode_img.width / barcode_img.height
    barcode_width = int(barcode_height * barcode_ratio)
    
    # Eğer barkod genişliği etiket genişliğini aşıyorsa, genişliğe göre ölçeklendir
    max_barcode_width = label_width_px - 2 * margin_px
    if barcode_width > max_barcode_width:
        barcode_width = max_barcode_width
        barcode_height = int(barcode_width / barcode_ratio)
    
    barcode_img = barcode_img.resize((barcode_width, barcode_height), Image.LANCZOS)

    # Barkodu ortala ve yerleştir
    barcode_x = (label_width_px - barcode_width) // 2
    barcode_y = margin_px
    canvas_img.paste(barcode_img, (barcode_x, barcode_y))

    # Font
    font_path = os.path.join(current_app.root_path, "static", "fonts", "arial.ttf")
    try:
        font = ImageFont.truetype(font_path, font_size)
        small_font = ImageFont.truetype(font_path, font_size - 2)
    except IOError:
        font = ImageFont.load_default()
        small_font = font

    # Ürün bilgileri metni
    product_info = []
    product_info.append(f"Model: {model_code}")
    product_info.append(f"Renk: {color}")
    product_info.append(f"Beden: {size}")
    
    if include_price and price:
        product_info.append(f"Fiyat: {price:,.2f} ₺")
    
    # Metni yerleştir
    text_y = barcode_y + barcode_height + margin_px
    line_height = font_size + 4  # 4 piksel boşluk
    
    for line in product_info:
        text_w, text_h = draw.textsize(line, font=font)
        text_x = (label_width_px - text_w) // 2
        draw.text((text_x, text_y), line, font=font, fill="black")
        text_y += line_height
    
    # Barkod numarasını ekle
    barcode_text_w, barcode_text_h = draw.textsize(barcode_number, font=small_font)
    barcode_text_x = (label_width_px - barcode_text_w) // 2
    barcode_text_y = label_height_px - barcode_text_h - margin_px
    draw.text((barcode_text_x, barcode_text_y), barcode_number, font=small_font, fill="black")

    return canvas_img


def create_label_pdf(
    product: Product,
    paper_size: str,
    layout_type: str,
    label_width_mm: float,
    label_height_mm: float,
    margin_mm: float,
    font_size: int,
    include_price: bool,
    columns: int = 2,
    rows: int = 4,
) -> io.BytesIO:
    """PDF formatında etiket sayfası oluşturur."""
    # Sayfa boyutunu belirle
    if paper_size in PAPER_SIZES:
        page_width_mm, page_height_mm = PAPER_SIZES[paper_size]
        page_size = get_reportlab_pagesize(paper_size)
    else:
        # Özel boyut - etiket ve düzen tipine göre ayarla
        if layout_type == "single":
            page_width_mm = label_width_mm + 2 * margin_mm
            page_height_mm = label_height_mm + 2 * margin_mm
        elif layout_type == "double":
            page_width_mm = 2 * label_width_mm + 3 * margin_mm
            page_height_mm = label_height_mm + 2 * margin_mm
        else:  # multi
            page_width_mm = columns * label_width_mm + (columns + 1) * margin_mm
            page_height_mm = rows * label_height_mm + (rows + 1) * margin_mm
        
        page_size = (page_width_mm * mm, page_height_mm * mm)
    
    # PDF oluştur
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=page_size)
    
    # Ürün bilgileri
    barcode_number = product.barcode
    model_code = product.product_main_id or "Model Bilinmiyor"
    color = product.color or "Renk Bilinmiyor"
    size = product.size or "Beden Bilinmiyor"
    price = getattr(product, "price", None)
    
    # Etiket sayısını belirle
    if layout_type == "single":
        label_count = 1
    elif layout_type == "double":
        label_count = 2
    else:  # multi
        label_count = columns * rows
    
    # Barkod nesnesi
    barcode_cls = barcode.get_barcode_class("code128")
    
    # Etiketleri yerleştir
    for i in range(label_count):
        # Satır ve sütun pozisyonunu hesapla
        if layout_type == "single":
            col, row = 0, 0
        elif layout_type == "double":
            col, row = i % 2, 0
        else:  # multi
            col, row = i % columns, i // columns
        
        # Etiketin pozisyonunu hesapla (sol alt köşe)
        x = margin_mm * mm + col * (label_width_mm * mm + margin_mm * mm)
        y = page_height_mm * mm - margin_mm * mm - (row + 1) * label_height_mm * mm - row * margin_mm * mm
        
        # Etiket çerçevesi
        pdf.rect(x, y, label_width_mm * mm, label_height_mm * mm, stroke=1, fill=0)
        
        # Barkod için geçici BytesIO
        barcode_buffer = io.BytesIO()
        barcode_writer = ImageWriter()
        barcode_options = {
            'module_width': 0.2,
            'module_height': 6.0,
            'quiet_zone': 1.0,
            'font_size': 0,  # Barcode altındaki yazıyı devre dışı bırak
            'text_distance': 1.0,
            'write_text': False,
        }
        barcode_cls(barcode_number, writer=barcode_writer).write(barcode_buffer, options=barcode_options)
        barcode_buffer.seek(0)
        
        # Barkodu yerleştir
        barcode_width = label_width_mm * mm * 0.8  # Genişliğin %80'i
        barcode_height = label_height_mm * mm * 0.3  # Yüksekliğin %30'u
        barcode_x = x + (label_width_mm * mm - barcode_width) / 2
        barcode_y = y + label_height_mm * mm - margin_mm * mm - barcode_height
        
        pdf.drawImage(
            barcode_buffer,
            barcode_x,
            barcode_y,
            width=barcode_width,
            height=barcode_height,
            preserveAspectRatio=True,
            anchor='c',
            mask='auto',
        )
        
        # Font ayarları
        pdf.setFont("Helvetica", font_size)
        
        # Ürün bilgilerini yaz
        text_y = y + label_height_mm * mm * 0.5  # Orta nokta
        line_height = font_size * 0.5  # Satır aralığı
        
        # Başlangıç Y pozisyonu hesapla - orta noktadan satır sayısını düşerek
        info_lines = 3  # Model, Renk, Beden
        if include_price and price:
            info_lines += 1
        
        text_y = text_y - (info_lines * line_height) / 2
        
        # Metinleri yerleştir
        pdf.drawCentredString(x + label_width_mm * mm / 2, text_y, f"Model: {model_code}")
        text_y += line_height
        pdf.drawCentredString(x + label_width_mm * mm / 2, text_y, f"Renk: {color}")
        text_y += line_height
        pdf.drawCentredString(x + label_width_mm * mm / 2, text_y, f"Beden: {size}")
        
        if include_price and price:
            text_y += line_height
            pdf.drawCentredString(x + label_width_mm * mm / 2, text_y, f"Fiyat: {price:,.2f} ₺")
        
        # Barkod numarasını ekle
        pdf.setFont("Helvetica", font_size - 2)
        pdf.drawCentredString(
            x + label_width_mm * mm / 2, 
            y + margin_mm * mm, 
            barcode_number
        )
    
    pdf.save()
    buffer.seek(0)
    return buffer


# --------------------------------------------------------------------------- #
# Route
# --------------------------------------------------------------------------- #


@product_label_bp.route("/", methods=["GET", "POST"])
def generate_product_label():
    # ------------------------------ GET ------------------------------ #
    if request.method == "GET":
        return render_template("product_label_form.html")

    # ------------------------------ POST ----------------------------- #
    barcode_number: str = (request.form.get("barcode") or "").strip()
    if not barcode_number:
        abort(400, description="Barkod numarası gerekli.")

    product: Product | None = Product.query.filter_by(barcode=barcode_number).first()
    if product is None:
        abort(404, description="Ürün bulunamadı.")

    # Form parametrelerini al
    paper_size = request.form.get("paper_size", "custom")
    layout_type = request.form.get("layout_type", "single")
    label_width_mm = float(request.form.get("label_width", 80))
    label_height_mm = float(request.form.get("label_height", 40))
    margin_mm = float(request.form.get("margin", 5))
    font_size = int(request.form.get("font_size", 12))
    include_price = request.form.get("include_price") == "on"
    
    # Çoklu etiket parametreleri
    columns = int(request.form.get("columns", 2))
    rows = int(request.form.get("rows", 4))

    # Tek etiket için PNG oluştur (özel boyut ve tek etiket seçiliyse)
    if layout_type == "single" and paper_size == "custom":
        label_image = create_single_label_image(
            product,
            label_width_mm,
            label_height_mm,
            margin_mm,
            font_size,
            include_price,
        )
        
        out = io.BytesIO()
        label_image.save(out, format="PNG")
        out.seek(0)

        filename = f"{barcode_number}_label.png"
        return send_file(
            out,
            mimetype="image/png",
            as_attachment=True,
            download_name=filename,
        )
    
    # Diğer tüm durumlar için PDF oluştur
    else:
        buffer = create_label_pdf(
            product,
            paper_size,
            layout_type,
            label_width_mm,
            label_height_mm,
            margin_mm,
            font_size,
            include_price,
            columns,
            rows,
        )
        
        filename = f"{barcode_number}_labels.pdf"
        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )