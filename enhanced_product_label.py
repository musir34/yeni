from flask import Blueprint, render_template, request, jsonify, send_file
import os
import qrcode
from PIL import Image, ImageDraw, ImageFont
import io
import base64
from models import Product, db
from sqlalchemy import func
import logging

enhanced_label_bp = Blueprint('enhanced_label', __name__)

logger = logging.getLogger(__name__)

def find_product_image(model_id, color):
    """
    Ürün görselini bul: model_renk.png/jpg formatında
    """
    images_folder = os.path.join('static', 'images')
    
    # Farklı formatları dene
    possible_names = [
        f"{model_id}_{color.lower()}.png",
        f"{model_id}_{color.lower()}.jpg",
        f"{model_id}_{color}.png",
        f"{model_id}_{color}.jpg"
    ]
    
    for name in possible_names:
        full_path = os.path.join(images_folder, name)
        if os.path.exists(full_path):
            return f"images/{name}"
    
    # Varsayılan görsel
    return "images/default_product.png"

def create_qr_with_logo(data, logo_path=None, size=200):
    """
    Logo içeren QR kod oluştur
    """
    # QR kod oluştur
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # Yüksek hata düzeltme
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    # QR kodu PIL Image olarak oluştur
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    qr_img = qr_img.resize((size, size), Image.Resampling.LANCZOS)
    
    # Logo varsa ortaya ekle
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path)
            
            # Logo boyutunu QR kodun 1/5'i kadar yap
            logo_size = size // 5
            logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            
            # Logo pozisyonu (ortada)
            logo_pos = ((size - logo_size) // 2, (size - logo_size) // 2)
            
            # Logoyu QR kodun üzerine yapıştır
            qr_img.paste(logo, logo_pos)
            
        except Exception as e:
            logger.warning(f"Logo eklenirken hata: {e}")
    
    return qr_img

def create_product_label(barcode, model_id, color, size, label_width=100, label_height=50):
    """
    Ürün etiketi oluştur
    """
    # Etiket boyutları (mm'den pixel'e çevir, 300 DPI)
    dpi = 300
    width_px = int((label_width / 25.4) * dpi)
    height_px = int((label_height / 25.4) * dpi)
    
    # Boş etiket oluştur
    label = Image.new('RGB', (width_px, height_px), 'white')
    draw = ImageDraw.Draw(label)
    
    # Font ayarları
    try:
        title_font = ImageFont.truetype("static/fonts/DejaVuSans-Bold.ttf", 24)
        info_font = ImageFont.truetype("static/fonts/DejaVuSans.ttf", 18)
        small_font = ImageFont.truetype("static/fonts/DejaVuSans.ttf", 14)
    except:
        title_font = ImageFont.load_default()
        info_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # "GÜLLÜ" başlığını en üste yaz
    title_text = "GÜLLÜ"
    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    title_x = (width_px - title_width) // 2
    draw.text((title_x, 10), title_text, fill='black', font=title_font)
    
    # Ana içerik alanı (başlık altında)
    content_y = 50
    content_height = height_px - content_y - 10
    
    # Sol taraf: Ürün görseli
    left_width = width_px // 2
    product_image_path = find_product_image(model_id, color)
    
    try:
        if os.path.exists(product_image_path):
            product_img = Image.open(product_image_path)
            # Görseli sol tarafa sığdır
            img_size = min(left_width - 20, content_height - 60)
            product_img = product_img.resize((img_size, img_size), Image.Resampling.LANCZOS)
            img_x = 10
            img_y = content_y + 10
            label.paste(product_img, (img_x, img_y))
            
            # Renk bilgisini görsel altına yaz
            color_y = img_y + img_size + 5
            draw.text((img_x, color_y), f"Renk", fill='black', font=small_font)
            draw.text((img_x, color_y + 15), color, fill='black', font=info_font)
            
    except Exception as e:
        logger.warning(f"Ürün görseli yüklenirken hata: {e}")
    
    # Sağ taraf: QR kod ve bilgiler
    right_x = width_px // 2 + 10
    right_width = width_px // 2 - 20
    
    # QR kod oluştur
    logo_path = os.path.join('static', 'logos', 'gullu_logo.png')
    qr_size = min(right_width, content_height // 2)
    qr_img = create_qr_with_logo(barcode, logo_path if os.path.exists(logo_path) else None, qr_size)
    
    qr_x = right_x
    qr_y = content_y + 10
    label.paste(qr_img, (qr_x, qr_y))
    
    # Model ve Beden bilgileri QR kod altında
    info_y = qr_y + qr_size + 10
    
    draw.text((qr_x, info_y), "Model", fill='black', font=small_font)
    draw.text((qr_x, info_y + 15), model_id, fill='black', font=info_font)
    
    draw.text((qr_x, info_y + 40), "Beden", fill='black', font=small_font)
    draw.text((qr_x, info_y + 55), size, fill='black', font=info_font)
    
    return label

@enhanced_label_bp.route('/enhanced_product_label')
def enhanced_product_label():
    """Ana etiket sayfası"""
    # URL parametrelerinden ürün bilgilerini al
    barcode = request.args.get('barcode')
    model = request.args.get('model')
    color = request.args.get('color')
    size = request.args.get('size')
    
    return render_template('enhanced_product_label.html', 
                         initial_barcode=barcode,
                         initial_model=model,
                         initial_color=color,
                         initial_size=size)

@enhanced_label_bp.route('/api/search_products_for_label', methods=['GET'])
def search_products_for_label():
    """Etiket için ürün arama"""
    search_type = request.args.get('search_type', 'model')
    query = request.args.get('query', '').strip()
    
    if not query:
        return jsonify({'success': False, 'message': 'Arama sorgusu gerekli'})
    
    try:
        if search_type == 'model':
            products = Product.query.filter(
                func.lower(Product.product_main_id) == query.lower()
            ).all()
        elif search_type == 'barcode':
            products = Product.query.filter(Product.barcode == query).all()
        else:
            return jsonify({'success': False, 'message': 'Geçersiz arama tipi'})
        
        if not products:
            return jsonify({'success': False, 'message': 'Ürün bulunamadı'})
        
        # Ürünleri model ve renge göre grupla
        grouped = {}
        for product in products:
            key = f"{product.product_main_id}_{product.color}"
            if key not in grouped:
                grouped[key] = {
                    'model_id': product.product_main_id,
                    'color': product.color,
                    'variants': []
                }
            grouped[key]['variants'].append({
                'barcode': product.barcode,
                'size': product.size,
                'quantity': product.quantity or 0
            })
        
        return jsonify({'success': True, 'products': list(grouped.values())})
        
    except Exception as e:
        logger.error(f"Ürün arama hatası: {e}")
        return jsonify({'success': False, 'message': 'Arama sırasında hata oluştu'})

@enhanced_label_bp.route('/api/generate_label_preview', methods=['POST'])
def generate_label_preview():
    """Etiket önizlemesi oluştur"""
    try:
        data = request.get_json()
        barcode = data.get('barcode')
        model_id = data.get('model_id')
        color = data.get('color')
        size = data.get('size')
        label_width = data.get('label_width', 100)
        label_height = data.get('label_height', 50)
        
        if not all([barcode, model_id, color, size]):
            return jsonify({'success': False, 'message': 'Eksik veri'})
        
        # Etiket oluştur
        label_img = create_product_label(
            barcode, model_id, color, size, 
            label_width, label_height
        )
        
        # Base64'e çevir
        buffer = io.BytesIO()
        label_img.save(buffer, format='PNG')
        buffer.seek(0)
        
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'image': f"data:image/png;base64,{img_base64}"
        })
        
    except Exception as e:
        logger.error(f"Etiket önizleme hatası: {e}")
        return jsonify({'success': False, 'message': 'Önizleme oluşturulamadı'})

@enhanced_label_bp.route('/api/print_labels', methods=['POST'])
def print_labels():
    """Etiketleri yazdırma için hazırla"""
    try:
        data = request.get_json()
        labels = data.get('labels', [])
        paper_size = data.get('paper_size', 'a4')
        labels_per_row = data.get('labels_per_row', 3)
        labels_per_col = data.get('labels_per_col', 7)
        label_width = data.get('label_width', 100)
        label_height = data.get('label_height', 50)
        
        if not labels:
            return jsonify({'success': False, 'message': 'Yazdırılacak etiket yok'})
        
        # A4 boyutları (mm)
        if paper_size == 'a4':
            page_width, page_height = 210, 297
        else:
            page_width, page_height = 210, 297  # Varsayılan A4
        
        # DPI ayarı
        dpi = 300
        page_width_px = int((page_width / 25.4) * dpi)
        page_height_px = int((page_height / 25.4) * dpi)
        
        # Sayfa oluştur
        page = Image.new('RGB', (page_width_px, page_height_px), 'white')
        
        # Etiket boyutları pixel
        label_width_px = int((label_width / 25.4) * dpi)
        label_height_px = int((label_height / 25.4) * dpi)
        
        # Kenar boşlukları
        margin_x = int((10 / 25.4) * dpi)  # 10mm kenar boşluğu
        margin_y = int((10 / 25.4) * dpi)
        
        # Etiketler arası boşluk
        gap_x = int((5 / 25.4) * dpi)  # 5mm boşluk
        gap_y = int((5 / 25.4) * dpi)
        
        # Etiketleri yerleştir
        for i, label_data in enumerate(labels):
            if i >= labels_per_row * labels_per_col:
                break  # Sayfaya sığmayan etiketleri atla
            
            row = i // labels_per_row
            col = i % labels_per_row
            
            # Etiket pozisyonu
            x = margin_x + col * (label_width_px + gap_x)
            y = margin_y + row * (label_height_px + gap_y)
            
            # Etiket oluştur
            label_img = create_product_label(
                label_data['barcode'],
                label_data['model_id'],
                label_data['color'],
                label_data['size'],
                label_width,
                label_height
            )
            
            # Sayfaya yapıştır
            page.paste(label_img, (x, y))
        
        # Base64'e çevir
        buffer = io.BytesIO()
        page.save(buffer, format='PNG', dpi=(dpi, dpi))
        buffer.seek(0)
        
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'image': f"data:image/png;base64,{img_base64}"
        })
        
    except Exception as e:
        logger.error(f"Yazdırma hazırlığı hatası: {e}")
        return jsonify({'success': False, 'message': 'Yazdırma hazırlanırken hata oluştu'})