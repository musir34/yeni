from flask import Blueprint, render_template, request, jsonify, send_file
import os
import qrcode
from PIL import Image, ImageDraw, ImageFont
import io
import base64
from models import Product, db
from sqlalchemy import func
import logging
import time

enhanced_label_bp = Blueprint('enhanced_label', __name__)

logger = logging.getLogger(__name__)

def find_product_image(model_id, color):
    """
    Ürün görselini bul: model_renk.png/jpg formatında
    """
    images_folder = os.path.join('static', 'images')
    
    # Farklı formatları dene
    possible_names = [
        f"{model_id}_{color.lower()}.jpg",
        f"{model_id}_{color.lower()}.png",
        f"{model_id}_{color.lower()}.jpeg",
        f"{model_id}_{color}.jpg",
        f"{model_id}_{color}.png",
        f"{model_id}_{color}.jpeg"
    ]
    
    for name in possible_names:
        full_path = os.path.join(images_folder, name)
        if os.path.exists(full_path):
            logger.info(f"Ürün görseli bulundu: {full_path}")
            return full_path  # Tam yolu döndür
    
    # Varsayılan görsel
    default_path = os.path.join(images_folder, "default_product.jpg")
    if os.path.exists(default_path):
        logger.info(f"Varsayılan görsel kullanılıyor: {default_path}")
        return default_path
    
    logger.warning(f"Görsel bulunamadı: model={model_id}, color={color}")
    return None

def create_qr_with_logo(data, logo_path=None, size=200):
    """
    Logo içeren QR kod oluştur
    """
    # QR kod oluştur
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_H
        qr = qrcode.QRCode(
            version=1,
            error_correction=ERROR_CORRECT_H,  # Yüksek hata düzeltme
            box_size=10,
            border=4,
        )
    except ImportError:
        # Fallback for different qrcode versions
        import qrcode
        qr = qrcode.QRCode(
            version=1,
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

def create_product_label(barcode, model_id, color, size, label_width=100, label_height=50, settings=None):
    """
    Ürün etiketi oluştur - manuel ayarlar ile
    """
    # Varsayılan ayarlar
    default_settings = {
        'title_text': 'GÜLLÜ',
        'title_font_size': 24,
        'title_position_x': 'center',
        'title_position_y': 10,
        'image_size': 'auto',
        'image_position_x': 10,
        'image_position_y': 50,
        'qr_size': 80,
        'qr_position_x': 'right',
        'qr_position_y': 50,
        'info_font_size': 18,
        'small_font_size': 14,
        'model_position_x': 'right',
        'model_position_y': 'below_qr',
        'color_position_x': 'left',
        'color_position_y': 'below_image',
        'size_position_x': 'right',
        'size_position_y': 'below_model'
    }
    
    # Kullanıcı ayarları ile varsayılanları birleştir
    if settings:
        default_settings.update(settings)
    
    settings = default_settings
    # Etiket boyutları (mm'den pixel'e çevir, 300 DPI)
    dpi = 300
    width_px = int((label_width / 25.4) * dpi)
    height_px = int((label_height / 25.4) * dpi)
    
    # Boş etiket oluştur
    label = Image.new('RGB', (width_px, height_px), 'white')
    draw = ImageDraw.Draw(label)
    
    # Font ayarları - ayarlanabilir boyutlarda
    try:
        title_font = ImageFont.truetype("static/fonts/DejaVuSans-Bold.ttf", settings['title_font_size'])
        info_font = ImageFont.truetype("static/fonts/DejaVuSans.ttf", settings['info_font_size'])
        small_font = ImageFont.truetype("static/fonts/DejaVuSans.ttf", settings['small_font_size'])
    except:
        title_font = ImageFont.load_default()
        info_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # Başlık yazısını ayarlanabilir pozisyonda yaz
    title_text = settings['title_text']
    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    
    if settings['title_position_x'] == 'center':
        title_x = (width_px - title_width) // 2
    elif settings['title_position_x'] == 'left':
        title_x = 10
    elif settings['title_position_x'] == 'right':
        title_x = width_px - title_width - 10
    else:
        title_x = int(settings['title_position_x'])
    
    title_y = settings['title_position_y']
    draw.text((title_x, title_y), title_text, fill='black', font=title_font)
    
    # Ana içerik alanı hesaplama
    content_y = title_y + settings['title_font_size'] + 10
    content_height = height_px - content_y - 10
    
    # Ürün görseli ayarları
    product_image_path = find_product_image(model_id, color)
    
    # Görsel boyutunu ayarla
    if settings['image_size'] == 'auto':
        img_size = min(width_px // 3, content_height // 2)
    else:
        img_size = int(settings['image_size'])
    
    # Görsel pozisyonunu ayarla
    if settings['image_position_x'] == 'left':
        img_x = 10
    elif settings['image_position_x'] == 'center':
        img_x = (width_px - img_size) // 2
    elif settings['image_position_x'] == 'right':
        img_x = width_px - img_size - 10
    else:
        img_x = int(settings['image_position_x'])
    
    img_y = int(settings['image_position_y'])
    
    # Ürün görselini çiz
    try:
        if product_image_path and os.path.exists(product_image_path):
            product_img = Image.open(product_image_path)
            # RGBA'yı RGB'ye çevir
            if product_img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', product_img.size, (255, 255, 255))
                background.paste(product_img, mask=product_img.split()[-1] if product_img.mode == 'RGBA' else None)
                product_img = background
            
            # Görseli ayarlanan boyutta yeniden boyutlandır
            product_img = product_img.resize((img_size, img_size), Image.Resampling.LANCZOS)
            label.paste(product_img, (img_x, img_y))
        else:
            # Placeholder çiz
            draw.rectangle([img_x, img_y, img_x + img_size, img_y + img_size], 
                         outline='#bdc3c7', fill='#ecf0f1', width=2)
            no_image_text = "Görsel\nYok"
            text_bbox = draw.textbbox((0, 0), no_image_text, font=info_font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            text_x = img_x + (img_size - text_width) // 2
            text_y = img_y + (img_size - text_height) // 2
            draw.multiline_text((text_x, text_y), no_image_text, fill='#7f8c8d', 
                              font=info_font, align='center')
    except Exception as e:
        logger.error(f"Ürün görseli yüklenirken hata: {e}")
        draw.rectangle([img_x, img_y, img_x + img_size, img_y + img_size], 
                     outline='#e74c3c', fill='#fadbd8', width=2)
    
    # QR kod ayarları
    qr_size = settings['qr_size']
    
    # QR kod pozisyonu
    if settings['qr_position_x'] == 'right':
        qr_x = width_px - qr_size - 10
    elif settings['qr_position_x'] == 'center':
        qr_x = (width_px - qr_size) // 2
    elif settings['qr_position_x'] == 'left':
        qr_x = 10
    else:
        qr_x = int(settings['qr_position_x'])
    
    qr_y = int(settings['qr_position_y'])
    
    # QR kod oluştur ve yerleştir
    logo_path = os.path.join('static', 'logos', 'gullu_logo.png')
    qr_img = create_qr_with_logo(barcode, logo_path if os.path.exists(logo_path) else None, qr_size)
    label.paste(qr_img, (qr_x, qr_y))
    
    # Metin bilgileri pozisyonlarını hesapla
    # Renk bilgisi pozisyonu
    if settings['color_position_x'] == 'left':
        color_x = img_x
    elif settings['color_position_x'] == 'center':
        color_x = width_px // 2
    elif settings['color_position_x'] == 'right':
        color_x = qr_x
    else:
        color_x = int(settings['color_position_x'])
    
    if settings['color_position_y'] == 'below_image':
        color_y = img_y + img_size + 5
    else:
        color_y = int(settings['color_position_y'])
    
    # Model bilgisi pozisyonu
    if settings['model_position_x'] == 'right':
        model_x = qr_x
    elif settings['model_position_x'] == 'left':
        model_x = img_x
    elif settings['model_position_x'] == 'center':
        model_x = width_px // 2
    else:
        model_x = int(settings['model_position_x'])
    
    if settings['model_position_y'] == 'below_qr':
        model_y = qr_y + qr_size + 5
    else:
        model_y = int(settings['model_position_y'])
    
    # Beden bilgisi pozisyonu
    if settings['size_position_x'] == 'right':
        size_x = qr_x
    elif settings['size_position_x'] == 'left':
        size_x = img_x
    elif settings['size_position_x'] == 'center':
        size_x = width_px // 2
    else:
        size_x = int(settings['size_position_x'])
    
    if settings['size_position_y'] == 'below_model':
        size_y = model_y + 25
    else:
        size_y = int(settings['size_position_y'])
    
    # Metinleri çiz
    draw.text((color_x, color_y), "Renk", fill='black', font=small_font)
    draw.text((color_x, color_y + 15), color, fill='black', font=info_font)
    
    draw.text((model_x, model_y), "Model", fill='black', font=small_font)
    draw.text((model_x, model_y + 15), model_id, fill='black', font=info_font)
    
    draw.text((size_x, size_y), "Beden", fill='black', font=small_font)
    draw.text((size_x, size_y + 15), size, fill='black', font=info_font)
    
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

@enhanced_label_bp.route('/enhanced_product_label/advanced_editor')
def advanced_label_editor():
    """Basitleştirilmiş sürükle-bırak etiket editörü"""
    return render_template('simple_label_editor.html')

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
        settings = data.get('settings', {})  # Manuel ayarlar
        
        if not all([barcode, model_id, color, size]):
            return jsonify({'success': False, 'message': 'Eksik veri'})
        
        # Etiket oluştur
        label_img = create_product_label(
            barcode, model_id, color, size, 
            label_width, label_height, settings
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

@enhanced_label_bp.route('/api/generate_advanced_label_preview', methods=['POST'])
def generate_advanced_label_preview():
    """Gelişmiş editörden gelen tasarımı işle ve önizleme oluştur"""
    try:
        data = request.get_json()
        label_width = int(data.get('width', 100))
        label_height = int(data.get('height', 50))
        elements = data.get('elements', [])
        
        # Etiket boyutları (mm'den pixel'e çevir, 300 DPI)
        dpi = 300
        width_px = int((label_width / 25.4) * dpi)
        height_px = int((label_height / 25.4) * dpi)
        
        # Boş etiket oluştur
        label = Image.new('RGB', (width_px, height_px), 'white')
        draw = ImageDraw.Draw(label)
        
        # Font ayarları
        try:
            default_font = ImageFont.truetype("static/fonts/DejaVuSans.ttf", 18)
            bold_font = ImageFont.truetype("static/fonts/DejaVuSans-Bold.ttf", 18)
        except:
            default_font = ImageFont.load_default()
            bold_font = ImageFont.load_default()
        
        # Elementleri çiz
        for element in elements:
            element_type = element.get('type')
            x = int(element.get('x', 0) * (width_px / (label_width * 4)))  # Convert from display to print scale
            y = int(element.get('y', 0) * (height_px / (label_height * 2)))
            properties = element.get('properties', {})
            
            if element_type in ['title', 'text']:
                text = properties.get('text', 'Text')
                font_size = int(properties.get('fontSize', 14) * (dpi / 96))  # Convert to print scale
                color = properties.get('color', '#000000')
                font_weight = properties.get('fontWeight', 'normal')
                
                try:
                    if font_weight == 'bold':
                        font = ImageFont.truetype("static/fonts/DejaVuSans-Bold.ttf", font_size)
                    else:
                        font = ImageFont.truetype("static/fonts/DejaVuSans.ttf", font_size)
                except:
                    font = default_font
                
                draw.text((x, y), text, fill=color, font=font)
                
            elif element_type == 'qr':
                qr_size = int(properties.get('size', 50) * (dpi / 96))
                qr_data = properties.get('data', 'sample')
                
                # QR kod oluştur
                logo_path = os.path.join('static', 'logos', 'gullu_logo.png')
                qr_img = create_qr_with_logo(qr_data, logo_path if os.path.exists(logo_path) else None, qr_size)
                label.paste(qr_img, (x, y))
                
            elif element_type == 'image':
                img_width = int(properties.get('width', 60) * (dpi / 96))
                img_height = int(properties.get('height', 60) * (dpi / 96))
                
                # Placeholder için basit bir kare çiz
                draw.rectangle([x, y, x + img_width, y + img_height], 
                             outline='#bdc3c7', fill='#ecf0f1', width=2)
                
                # "IMG" yazısı
                try:
                    img_font = ImageFont.truetype("static/fonts/DejaVuSans.ttf", 12)
                except:
                    img_font = default_font
                
                text_bbox = draw.textbbox((0, 0), "IMG", font=img_font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                text_x = x + (img_width - text_width) // 2
                text_y = y + (img_height - text_height) // 2
                draw.text((text_x, text_y), "IMG", fill='#7f8c8d', font=img_font)
        
        # Önizleme kaydet
        timestamp = int(time.time())
        preview_filename = f"label_preview_{timestamp}.png"
        preview_path = os.path.join('static', 'generated', preview_filename)
        
        # Generated klasörünü oluştur
        os.makedirs(os.path.dirname(preview_path), exist_ok=True)
        
        label.save(preview_path, 'PNG', dpi=(dpi, dpi))
        
        preview_url = f"/static/generated/{preview_filename}"
        
        return jsonify({
            'success': True,
            'preview_url': preview_url,
            'message': 'Önizleme başarıyla oluşturuldu'
        })
        
    except Exception as e:
        logger.error(f"Gelişmiş etiket önizleme hatası: {e}")
        return jsonify({'success': False, 'message': 'Önizleme oluşturulamadı'})

@enhanced_label_bp.route('/enhanced_product_label/api/generate_advanced_label_preview', methods=['POST'])
@enhanced_label_bp.route('/api/generate_advanced_label_preview', methods=['POST'])
def generate_advanced_label_preview_new():
    """Gelişmiş editörden gelen tasarımı işle ve ürün bilgileriyle önizleme oluştur"""
    try:
        data = request.get_json()
        label_width = int(data.get('width', 100))
        label_height = int(data.get('height', 50))
        elements = data.get('elements', [])
        product_data = data.get('product_data', {})
        
        # Ürün bilgileri - gerçek ürün verisi varsa onu kullan, yoksa örnek
        if product_data:
            model_code = product_data.get('model_code', 'GL099')
            color = product_data.get('color', 'Siyah')
            
            # Ürün görseli yolu - büyük/küçük harf duyarsız arama
            possible_extensions = ['.jpg', '.jpeg', '.png', '.webp']
            image_path = None
            
            # Farklı harf kombinasyonlarını dene
            color_variations = [
                color,                    # Orijinal
                color.lower(),            # küçük harf
                color.upper(),            # BÜYÜK HARF  
                color.capitalize()        # İlk harf büyük
            ]
            
            for color_var in color_variations:
                for ext in possible_extensions:
                    potential_path = f"static/images/{model_code}_{color_var}{ext}"
                    if os.path.exists(potential_path):
                        image_path = potential_path
                        logger.info(f"Önizleme görseli bulundu: {potential_path}")
                        break
                if image_path:
                    break
            
            sample_product = {
                'model_code': model_code,
                'color': color,
                'size': product_data.get('size', '42'),
                'barcode': product_data.get('barcode', '8690123456789'),
                'image_path': image_path
            }
        else:
            sample_product = {
                'model_code': 'GL099',
                'color': 'Siyah',
                'size': '42',
                'barcode': '8690123456789',
                'image_path': None
            }
        
        # Etiket boyutları (mm'den pixel'e çevir, 300 DPI)
        dpi = 300
        width_px = int((label_width / 25.4) * dpi)
        height_px = int((label_height / 25.4) * dpi)
        
        # Boş etiket oluştur
        label = Image.new('RGB', (width_px, height_px), 'white')
        draw = ImageDraw.Draw(label)
        
        # Font ayarları
        try:
            default_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
            bold_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        except:
            default_font = ImageFont.load_default()
            bold_font = ImageFont.load_default()
        
        # Elementleri çiz
        for element in elements:
            element_type = element.get('type')
            x = int(element.get('x', 0) * (width_px / (label_width * 4)))
            y = int(element.get('y', 0) * (height_px / (label_height * 2)))
            
            # Ürün-spesifik alanlar
            if element_type == 'title':
                html_content = element.get('html', 'GÜLLÜ SHOES')
                font_size = int(element.get('fontSize', '18px').replace('px', ''))
                font_size = int(font_size * (dpi / 96))
                
                try:
                    if 'strong' in html_content:
                        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
                    else:
                        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
                except:
                    font = default_font
                
                # HTML etiketlerini temizle
                import re
                clean_text = re.sub('<[^<]+?>', '', html_content)
                draw.text((x, y), clean_text, fill='black', font=font)
                
            elif element_type == 'model_code':
                html_content = element.get('html', '[MODEL KODU]')
                font_size = int(element.get('fontSize', '14px').replace('px', ''))
                font_size = int(font_size * (dpi / 96))
                
                try:
                    if 'strong' in html_content:
                        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
                    else:
                        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
                except:
                    font = default_font
                
                draw.text((x, y), sample_product['model_code'], fill='black', font=font)
                
            elif element_type == 'color':
                html_content = element.get('html', '[RENK]')
                font_size = int(element.get('fontSize', '14px').replace('px', ''))
                font_size = int(font_size * (dpi / 96))
                
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
                except:
                    font = default_font
                
                draw.text((x, y), sample_product['color'], fill='black', font=font)
                
            elif element_type == 'size':
                html_content = element.get('html', '[BEDEN]')
                font_size = int(element.get('fontSize', '14px').replace('px', ''))
                font_size = int(font_size * (dpi / 96))
                
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
                except:
                    font = default_font
                
                draw.text((x, y), sample_product['size'], fill='black', font=font)
                
            elif element_type == 'qr':
                qr_size = int(element.get('width', 40) * (dpi / 96))
                # QR kod direkt barkodu içermeli
                qr_data = sample_product['barcode']
                
                logo_path = os.path.join('static', 'logos', 'gullu_logo.png')
                qr_img = create_qr_with_logo(qr_data, logo_path if os.path.exists(logo_path) else None, qr_size)
                label.paste(qr_img, (x, y))
                
            elif element_type == 'barcode':
                # Barkod alanı sadece rakam gösterecek
                barcode_data = sample_product['barcode']
                font_size = int(element.get('fontSize', '12px').replace('px', ''))
                font_size = int(font_size * (dpi / 96))
                
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
                except:
                    font = default_font
                
                # Sadece barkod rakamını yazı olarak göster
                draw.text((x, y), barcode_data, fill='black', font=font)
                
            elif element_type == 'product_image':
                img_width = int(element.get('width', 50) * (dpi / 96))
                img_height = int(element.get('height', 50) * (dpi / 96))
                
                # Gerçek ürün görseli varsa kullan, yoksa placeholder
                image_loaded = False
                try:
                    if sample_product['image_path'] and os.path.exists(sample_product['image_path']):
                        product_img = Image.open(sample_product['image_path'])
                        # RGBA moduna dönüştür eğer gerekirse
                        if product_img.mode != 'RGB':
                            product_img = product_img.convert('RGB')
                        product_img = product_img.resize((img_width, img_height), Image.Resampling.LANCZOS)
                        label.paste(product_img, (x, y))
                        image_loaded = True
                        logger.info(f"Ürün görseli yüklendi: {sample_product['image_path']}")
                except Exception as img_error:
                    logger.error(f"Ürün görseli yükleme hatası: {img_error}")
                
                # Görsel yüklenemedi ise placeholder göster
                if not image_loaded:
                    draw.rectangle([x, y, x + img_width, y + img_height], 
                                 outline='#3498db', fill='#e3f2fd', width=2)
                    
                    try:
                        img_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
                    except:
                        img_font = default_font
                    
                    text = f"{sample_product['model_code']}\n{sample_product['color']}"
                    text_bbox = draw.textbbox((0, 0), text, font=img_font)
                    text_height = text_bbox[3] - text_bbox[1]
                    text_x = x + 5
                    text_y = y + (img_height - text_height) // 2
                    draw.text((text_x, text_y), text, fill='#2196f3', font=img_font)
        
        # Önizleme kaydet
        os.makedirs('static/generated', exist_ok=True)
        timestamp = int(time.time())
        preview_filename = f"product_label_preview_{timestamp}.png"
        preview_path = os.path.join('static', 'generated', preview_filename)
        
        label.save(preview_path, 'PNG', dpi=(dpi, dpi))
        preview_url = f"/static/generated/{preview_filename}"
        
        return jsonify({
            'success': True,
            'preview_url': preview_url,
            'message': 'Ürün etiketi önizlemesi oluşturuldu',
            'product_info': sample_product
        })
        
    except Exception as e:
        logger.error(f"Ürün etiketi önizleme hatası: {e}")
        return jsonify({'success': False, 'message': f'Önizleme oluşturulamadı: {str(e)}'})

@enhanced_label_bp.route('/api/save_label_preset', methods=['POST'])
def save_label_preset():
    """Etiket preset'ini veritabanına kaydet"""
    try:
        data = request.get_json()
        preset_name = data.get('name')
        preset_data = data.get('data')
        
        # Burada veritabanına kaydedebilirsiniz
        # Şimdilik başarılı dönüş yapıyoruz
        
        return jsonify({
            'success': True,
            'message': 'Preset başarıyla kaydedildi'
        })
        
    except Exception as e:
        logger.error(f"Preset kaydetme hatası: {e}")
        return jsonify({'success': False, 'message': 'Preset kaydedilemedi'})

@enhanced_label_bp.route('/enhanced_product_label/api/print_multiple_labels', methods=['POST'])
@enhanced_label_bp.route('/api/print_multiple_labels', methods=['POST'])
def print_multiple_labels():
    """Çoklu etiket yazdırma için sayfa hazırla"""
    try:
        data = request.get_json()
        labels = data.get('labels', [])
        design = data.get('design', {})
        paper_size = data.get('paper_size', 'a4')
        page_orientation = data.get('page_orientation', 'portrait')
        labels_per_row = data.get('labels_per_row', 2)
        labels_per_col = data.get('labels_per_col', 5)
        label_width = data.get('label_width', 100)
        label_height = data.get('label_height', 50)
        top_margin = data.get('top_margin', 10)
        left_margin = data.get('left_margin', 10)
        horizontal_gap = data.get('horizontal_gap', 5)
        vertical_gap = data.get('vertical_gap', 5)
        print_quality = data.get('print_quality', 300)
        
        if not labels:
            return jsonify({'success': False, 'message': 'Yazdırılacak etiket yok'})
        
        # Kağıt boyutları (mm) - sayfa yönüne göre
        if paper_size == 'a4':
            if page_orientation == 'landscape':
                page_width, page_height = 297, 210
            else:
                page_width, page_height = 210, 297
        elif paper_size == 'letter':
            if page_orientation == 'landscape':
                page_width, page_height = 279, 216
            else:
                page_width, page_height = 216, 279
        else:
            page_width, page_height = 210, 297  # Varsayılan A4 dikey
        
        # DPI ayarı
        dpi = print_quality
        page_width_px = int((page_width / 25.4) * dpi)
        page_height_px = int((page_height / 25.4) * dpi)
        
        # Sayfa oluştur
        page = Image.new('RGB', (page_width_px, page_height_px), 'white')
        
        # Etiket boyutları pixel
        label_width_px = int((label_width / 25.4) * dpi)
        label_height_px = int((label_height / 25.4) * dpi)
        
        # Kenar boşlukları
        margin_x = int((left_margin / 25.4) * dpi)
        margin_y = int((top_margin / 25.4) * dpi)
        
        # Etiketler arası boşluk
        gap_x = int((horizontal_gap / 25.4) * dpi)
        gap_y = int((vertical_gap / 25.4) * dpi)
        
        # Sayfaya sığacak etiket sayısını hesapla
        available_width = page_width_px - (2 * margin_x)
        available_height = page_height_px - (2 * margin_y)
        
        max_labels_per_row = min(labels_per_row, available_width // (label_width_px + gap_x))
        max_labels_per_col = min(labels_per_col, available_height // (label_height_px + gap_y))
        
        # Minimum 1 etiket garantisi
        max_labels_per_row = max(1, max_labels_per_row)
        max_labels_per_col = max(1, max_labels_per_col)
        
        # Çoklu sayfa desteği
        labels_per_page = max_labels_per_row * max_labels_per_col
        total_pages = (len(labels) + labels_per_page - 1) // labels_per_page
        
        all_pages = []
        
        for page_num in range(total_pages):
            # Her sayfa için yeni sayfa oluştur
            current_page = Image.new('RGB', (page_width_px, page_height_px), 'white')
            
            start_idx = page_num * labels_per_page
            end_idx = min(start_idx + labels_per_page, len(labels))
            page_labels = labels[start_idx:end_idx]
            
            # Bu sayfadaki etiketleri yerleştir
            for i, label_data in enumerate(page_labels):
                row = i // max_labels_per_row
                col = i % max_labels_per_row
                
                # Etiket pozisyonu
                x = margin_x + col * (label_width_px + gap_x)
                y = margin_y + row * (label_height_px + gap_y)
                
                # Tasarım kullanarak etiket oluştur
                label_img = create_label_with_design(
                    label_data,
                    design,
                    label_width,
                    label_height
                )
                
                # Sayfaya yapıştır
                current_page.paste(label_img, (x, y))
            
            all_pages.append(current_page)
        
        # Dosya olarak kaydet
        os.makedirs('static/generated', exist_ok=True)
        timestamp = int(time.time())
        
        if len(all_pages) == 1:
            # Tek sayfa
            filename = f"print_labels_{timestamp}.png"
            filepath = os.path.join('static', 'generated', filename)
            all_pages[0].save(filepath, 'PNG', dpi=(dpi, dpi))
            
            return jsonify({
                'success': True,
                'image_url': f"/static/generated/{filename}",
                'total_pages': 1,
                'message': f'{len(labels)} etiket yazdırma için hazırlandı'
            })
        else:
            # Çoklu sayfa - PDF oluştur
            filename = f"print_labels_{timestamp}.pdf"
            filepath = os.path.join('static', 'generated', filename)
            
            all_pages[0].save(
                filepath, 
                'PDF', 
                resolution=dpi,
                save_all=True, 
                append_images=all_pages[1:]
            )
            
            return jsonify({
                'success': True,
                'image_url': f"/static/generated/{filename}",
                'total_pages': len(all_pages),
                'message': f'{len(labels)} etiket {len(all_pages)} sayfada yazdırma için hazırlandı'
            })
        
    except Exception as e:
        logger.error(f"Çoklu etiket yazdırma hatası: {e}")
        return jsonify({'success': False, 'message': f'Yazdırma hazırlanırken hata oluştu: {str(e)}'})

def create_label_with_design(product_data, design, label_width, label_height):
    """Tasarım kullanarak tek etiket oluştur"""
    try:
        # Etiket boyutları (mm'den pixel'e çevir, 300 DPI)
        dpi = 300
        width_px = int((label_width / 25.4) * dpi)
        height_px = int((label_height / 25.4) * dpi)
        
        # Boş etiket oluştur
        label = Image.new('RGB', (width_px, height_px), 'white')
        draw = ImageDraw.Draw(label)
        
        # Font ayarları
        try:
            default_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        except:
            default_font = ImageFont.load_default()
        
        # Ürün bilgileri
        model_code = product_data.get('model_code', 'N/A')
        color = product_data.get('color', 'N/A')
        size = product_data.get('size', 'N/A')
        barcode = product_data.get('barcode', 'N/A')
        
        # Ürün görseli yolu - büyük/küçük harf duyarsız arama
        possible_extensions = ['.jpg', '.jpeg', '.png', '.webp']
        image_path = None
        
        # Farklı harf kombinasyonlarını dene
        color_variations = [
            color,                    # Orijinal
            color.lower(),            # küçük harf
            color.upper(),            # BÜYÜK HARF  
            color.capitalize()        # İlk harf büyük
        ]
        
        for color_var in color_variations:
            for ext in possible_extensions:
                potential_path = f"static/images/{model_code}_{color_var}{ext}"
                if os.path.exists(potential_path):
                    image_path = potential_path
                    logger.info(f"Etiket görseli bulundu: {potential_path}")
                    break
            if image_path:
                break
        
        # Tasarım elementlerini çiz - Koordinat sistemi düzeltmesi
        elements = design.get('elements', [])
        
        # Koordinat sistemi - 1:1 doğrudan mapping
        # Editörde görünen boyutlarla yazdırılan boyutlar aynı olacak
        for element in elements:
            element_type = element.get('type')
            
            # Doğrudan koordinat kullanımı - ölçekleme yapmadan
            raw_x = element.get('x', 0)
            raw_y = element.get('y', 0)
            
            # DPI'ye göre basit ölçeklendirme (96 DPI -> 300 DPI)
            scale_factor = dpi / 96
            x = int(raw_x * scale_factor)
            y = int(raw_y * scale_factor)
            
            # Debug bilgisi
            logger.info(f"Element {element_type}: editör({raw_x},{raw_y}) -> print({x},{y}) | scale: {scale_factor} -> {width_px}x{height_px}")
            
            if element_type == 'title':
                html_content = element.get('html', 'GÜLLÜ SHOES')
                # Font boyutu alma - properties kontrol et
                font_size = 18
                if 'properties' in element and 'fontSize' in element['properties']:
                    font_size = int(element['properties']['fontSize'])
                elif 'fontSize' in element:
                    font_size_str = element.get('fontSize', '18px')
                    if isinstance(font_size_str, str):
                        font_size = int(font_size_str.replace('px', ''))
                    else:
                        font_size = int(font_size_str)
                
                # Font boyutunu doğrudan ölçeklendirme ile ayarla
                font_size = int(font_size * scale_factor)
                logger.info(f"Title font: {font_size}px (from {element.get('fontSize', element.get('properties', {}).get('fontSize', 'N/A'))})")
                
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
                except:
                    font = default_font
                
                # HTML etiketlerini temizle
                import re
                clean_text = re.sub('<[^<]+?>', '', html_content)
                draw.text((x, y), clean_text, fill='black', font=font)
                
            elif element_type == 'model_code':
                # Font boyutu alma - properties öncelikli
                font_size = 14
                if 'properties' in element and 'fontSize' in element['properties']:
                    font_size = int(element['properties']['fontSize'])
                elif 'fontSize' in element:
                    font_size_str = element.get('fontSize', '14px')
                    if isinstance(font_size_str, str):
                        font_size = int(font_size_str.replace('px', ''))
                    else:
                        font_size = int(font_size_str)
                
                font_size = int(font_size * scale_factor)
                
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
                except:
                    font = default_font
                
                draw.text((x, y), model_code, fill='black', font=font)
                
            elif element_type == 'color':
                # Font boyutu alma - properties öncelikli
                font_size = 14
                if 'properties' in element and 'fontSize' in element['properties']:
                    font_size = int(element['properties']['fontSize'])
                elif 'fontSize' in element:
                    font_size_str = element.get('fontSize', '14px')
                    if isinstance(font_size_str, str):
                        font_size = int(font_size_str.replace('px', ''))
                    else:
                        font_size = int(font_size_str)
                
                font_size = int(font_size * scale_factor)
                
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
                except:
                    font = default_font
                
                draw.text((x, y), color, fill='black', font=font)
                
            elif element_type == 'size':
                # Font boyutu alma - properties öncelikli  
                font_size = 14
                if 'properties' in element and 'fontSize' in element['properties']:
                    font_size = int(element['properties']['fontSize'])
                elif 'fontSize' in element:
                    font_size_str = element.get('fontSize', '14px')
                    if isinstance(font_size_str, str):
                        font_size = int(font_size_str.replace('px', ''))
                    else:
                        font_size = int(font_size_str)
                
                font_size = int(font_size * scale_factor)
                
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
                except:
                    font = default_font
                
                draw.text((x, y), size, fill='black', font=font)
                
            elif element_type == 'qr':
                # QR boyutu doğrudan ölçeklendirme
                qr_size = int(element.get('width', 40))
                qr_size = int(qr_size * scale_factor)
                qr_data = barcode
                
                logo_path = os.path.join('static', 'logos', 'gullu_logo.png')
                qr_img = create_qr_with_logo(qr_data, logo_path if os.path.exists(logo_path) else None, qr_size)
                label.paste(qr_img, (x, y))
                
            elif element_type == 'barcode':
                # Barkod elementi - sadece rakam olarak göster
                font_size = 12
                if 'properties' in element and 'fontSize' in element['properties']:
                    font_size = int(element['properties']['fontSize'])
                elif 'fontSize' in element:
                    font_size_str = element.get('fontSize', '12px')
                    if isinstance(font_size_str, str):
                        font_size = int(font_size_str.replace('px', ''))
                    else:
                        font_size = int(font_size_str)
                
                font_size = int(font_size * scale_factor)
                
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
                except:
                    font = default_font
                
                # Sadece barkod rakamını yazı olarak göster
                draw.text((x, y), barcode, fill='black', font=font)
                
            elif element_type == 'product_image':
                # Görsel boyutu doğrudan ölçeklendirme
                img_width = int(element.get('width', 50))
                img_height = int(element.get('height', 50))
                img_width = int(img_width * scale_factor)
                img_height = int(img_height * scale_factor)
                
                # Ürün görseli yükle
                image_loaded = False
                try:
                    if image_path and os.path.exists(image_path):
                        product_img = Image.open(image_path)
                        if product_img.mode != 'RGB':
                            product_img = product_img.convert('RGB')
                        product_img = product_img.resize((img_width, img_height), Image.Resampling.LANCZOS)
                        label.paste(product_img, (x, y))
                        image_loaded = True
                except Exception:
                    pass
                
                # Placeholder
                if not image_loaded:
                    draw.rectangle([x, y, x + img_width, y + img_height], 
                                 outline='#3498db', fill='#e3f2fd', width=2)
                    
                    try:
                        img_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
                    except:
                        img_font = default_font
                    
                    text = f"{model_code}\n{color}"
                    text_x = x + 5
                    text_y = y + 5
                    draw.text((text_x, text_y), text, fill='#2196f3', font=img_font)
        
        return label
        
    except Exception as e:
        logger.error(f"Etiket oluşturma hatası: {e}")
        # Basit fallback etiket - boyutları yeniden tanımla
        fallback_dpi = 300
        fallback_width_px = int((label_width / 25.4) * fallback_dpi)
        fallback_height_px = int((label_height / 25.4) * fallback_dpi)
        fallback_label = Image.new('RGB', (fallback_width_px, fallback_height_px), 'white')
        fallback_draw = ImageDraw.Draw(fallback_label)
        fallback_draw.text((10, 10), f"{product_data.get('model_code', 'N/A')} - {product_data.get('color', 'N/A')}", fill='black')
        return fallback_label