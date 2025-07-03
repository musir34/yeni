from flask import Blueprint, render_template, request, jsonify, send_file
import os
import json
import qrcode
from PIL import Image, ImageDraw, ImageFont
import io
import base64

from werkzeug.wrappers import response
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
        f"{model_id}_{color.lower()}.jpg", f"{model_id}_{color.lower()}.png",
        f"{model_id}_{color.lower()}.jpeg", f"{model_id}_{color}.jpg",
        f"{model_id}_{color}.png", f"{model_id}_{color}.jpeg"
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
    try:
        import qrcode
        print(f"QR kod oluşturuluyor: data='{data}', size={size}")

        # QR kod oluştur - basit yaklaşım
        qr = qrcode.QRCode(
            version=1,
            box_size=10,
            border=4,
        )
        qr.add_data(str(data))  # String'e çevir
        qr.make(fit=True)

        # QR kodu PIL Image olarak oluştur
        qr_img = qr.make_image(fill_color="black", back_color="white")
        print(f"QR base image oluşturuldu: mode={qr_img.mode}, size={qr_img.size}")

        # RGB'ye çevir
        if qr_img.mode != 'RGB':
            qr_img = qr_img.convert('RGB')
            print(f"QR RGB'ye çevrildi: mode={qr_img.mode}")

        # Boyutlandır
        qr_img = qr_img.resize((size, size), Image.Resampling.LANCZOS)
        print(f"QR kod boyutlandırıldı: {qr_img.size}")

        # Logo varsa ortaya ekle
        if logo_path and os.path.exists(logo_path):
            try:
                print(f"Logo ekleniyor: {logo_path}")
                logo = Image.open(logo_path)

                # Logo boyutunu QR kodun 1/5'i kadar yap
                logo_size = size // 5
                logo = logo.resize((logo_size, logo_size),
                                   Image.Resampling.LANCZOS)

                # Logo pozisyonu (ortada)
                logo_pos = ((size - logo_size) // 2, (size - logo_size) // 2)

                # Logoyu QR kodun üzerine yapıştır
                qr_img.paste(logo, logo_pos)
                logger.info(
                    f"Logo eklendi: {logo_size}x{logo_size} at {logo_pos}")

            except Exception as e:
                logger.warning(f"Logo eklenirken hata: {e}")
        else:
            logger.info(
                f"Logo yok: path={logo_path}, exists={os.path.exists(logo_path) if logo_path else False}"
            )

        # Final kontrol
        logger.info(
            f"QR kod tamamlandı: mode={qr_img.mode}, size={qr_img.size}")
        return qr_img

    except Exception as e:
        logger.error(f"QR kod oluşturma hatası: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None


def create_product_label(barcode,
                         model_id,
                         color,
                         size,
                         label_width=100,
                         label_height=50,
                         settings=None):
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
        'qr_position_y': 'relative',
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
        title_font = ImageFont.truetype("static/fonts/DejaVuSans-Bold.ttf",
                                        settings['title_font_size'])
        info_font = ImageFont.truetype("static/fonts/DejaVuSans.ttf",
                                       settings['info_font_size'])
        small_font = ImageFont.truetype("static/fonts/DejaVuSans.ttf",
                                        settings['small_font_size'])
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
                background = Image.new('RGB', product_img.size,
                                       (255, 255, 255))
                background.paste(product_img,
                                 mask=product_img.split()[-1]
                                 if product_img.mode == 'RGBA' else None)
                product_img = background

            # Görseli ayarlanan boyutta yeniden boyutlandır
            product_img = product_img.resize((img_size, img_size),
                                             Image.Resampling.LANCZOS)
            label.paste(product_img, (img_x, img_y))
        else:
            # Placeholder çiz
            draw.rectangle([img_x, img_y, img_x + img_size, img_y + img_size],
                           outline='#bdc3c7',
                           fill='#ecf0f1',
                           width=2)
            no_image_text = "Görsel\nYok"
            text_bbox = draw.textbbox((0, 0), no_image_text, font=info_font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            text_x = img_x + (img_size - text_width) // 2
            text_y = img_y + (img_size - text_height) // 2
            draw.multiline_text((text_x, text_y),
                                no_image_text,
                                fill='#7f8c8d',
                                font=info_font,
                                align='center')
    except Exception as e:
        logger.error(f"Ürün görseli yüklenirken hata: {e}")
        draw.rectangle([img_x, img_y, img_x + img_size, img_y + img_size],
                       outline='#e74c3c',
                       fill='#fadbd8',
                       width=2)

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
    qr_img = create_qr_with_logo(
        barcode, logo_path if os.path.exists(logo_path) else None, qr_size)
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

    return render_template('enhanced_product_label_simple.html')


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
                func.lower(Product.product_main_id) == query.lower()).all()
        elif search_type == 'barcode':
            products = Product.query.filter(Product.barcode == query).all()
        else:
            return jsonify({
                'success': False,
                'message': 'Geçersiz arama tipi'
            })

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
        return jsonify({
            'success': False,
            'message': 'Arama sırasında hata oluştu'
        })


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
        label_img = create_product_label(barcode, model_id, color, size,
                                         label_width, label_height, settings)

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
        return jsonify({
            'success': False,
            'message': 'Önizleme oluşturulamadı'
        })


@enhanced_label_bp.route('/api/generate_advanced_label_preview',
                         methods=['POST'])
def generate_advanced_label_preview():
    """Gelişmiş editörden gelen tasarımı işle ve önizleme oluştur"""
    try:
        data = request.get_json()
        label_width = int(data.get('width', 100))
        label_height = int(data.get('height', 50))
        elements = data.get('elements', [])

        # A4 ile tutarlılık için etiket boyutlarını kontrol et
        product_data = data.get('product_data', {})
        is_a4_preview = data.get('is_a4_preview', False)  # A4 önizlemesi mi?

        # Eğer A4 önizlemesi ise A4 boyutlarını kullan
        if is_a4_preview:
            # A4 sabit boyutları (Product Label ile aynı)
            label_width = 64.67  # A4_FIXED_CONFIG boyutları
            label_height = 37.92
            logger.info(
                f"A4 önizleme modu: boyutlar {label_width}x{label_height}mm")

        # Etiket boyutları (mm'den pixel'e çevir, 300 DPI)
        dpi = 300
        width_px = int((label_width / 25.4) * dpi)
        height_px = int((label_height / 25.4) * dpi)

        # QR kodları için canvas genişliği hesapla
        max_required_width = width_px
        for element in elements:
            if element.get('type') == 'qr':
                editor_x_mm = element.get('x', 0) / 4  # 4px = 1mm editörde
                if editor_x_mm > label_width:  # QR kod etiket dışında
                    qr_size_px = element.get('properties',
                                             {}).get('size',
                                                     50)  # editörde pixel
                    qr_size_mm = qr_size_px / 4  # 4px = 1mm dönüşümü
                    required_width_mm = editor_x_mm + qr_size_mm + 5  # QR + 5mm boşluk
                    required_width_px = int((required_width_mm / 25.4) * dpi)
                    max_required_width = max(max_required_width,
                                             required_width_px)

        # Gerekli genişlikte etiket oluştur
        label = Image.new('RGB', (max_required_width, height_px), 'white')
        draw = ImageDraw.Draw(label)

        # Etiket sınırlarını çiz (gerçek etiket boyutları)
        actual_label_width_px = int((label_width / 25.4) * dpi)
        actual_label_height_px = int((label_height / 25.4) * dpi)

        # Sınır çizgisi çiz (açık gri, ince çizgi)
        border_color = (200, 200, 200)  # Açık gri
        draw.rectangle(
            [0, 0, actual_label_width_px - 1, actual_label_height_px - 1],
            outline=border_color,
            width=2)

        # Eğer canvas gerçek etiket boyutundan büyükse, kesikli çizgi ile genişletilmiş alanı göster
        if max_required_width > actual_label_width_px:
            # Kesikli dikey çizgi çiz
            for y in range(0, actual_label_height_px, 10):
                draw.line([
                    actual_label_width_px, y, actual_label_width_px,
                    min(y + 5, actual_label_height_px)
                ],
                          fill=(150, 150, 150),
                          width=1)

        # Font ayarları
        try:
            default_font = ImageFont.truetype("static/fonts/DejaVuSans.ttf",
                                              18)
            bold_font = ImageFont.truetype("static/fonts/DejaVuSans-Bold.ttf",
                                           18)
        except:
            default_font = ImageFont.load_default()
            bold_font = ImageFont.load_default()

        # A4 ölçeklendirme hesaplaması (A4 yazdırma ile tutarlılık için)
        editor_default_width = 100  # mm - editör varsayılan boyutu
        editor_default_height = 50  # mm

        # Ölçeklendirme oranları hesapla (sadece A4 önizlemesi için)
        if is_a4_preview:
            scale_x = label_width / editor_default_width
            scale_y = label_height / editor_default_height
            logger.info(
                f"Önizleme A4 ölçeklendirme: x={scale_x:.2f}, y={scale_y:.2f}")
        else:
            scale_x = 1.0  # Normal önizleme için ölçeklendirme yok
            scale_y = 1.0

        # Elementleri çiz
        for element in elements:
            element_type = element.get('type')

            # Editörden gelen koordinatları mm'ye çevir
            # Editörde canvas boyutu: width*4 px = width mm
            # Yani 100mm etiket için 400px canvas, 1px = 0.25mm
            editor_x_mm = element.get('x',
                                      0) / 4  # px'i mm'ye çevir (4px = 1mm)
            editor_y_mm = element.get('y', 0) / 4

            # A4 modunda ölçeklendirme uygula
            if is_a4_preview:
                scaled_x_mm = editor_x_mm * scale_x
                scaled_y_mm = editor_y_mm * scale_y
            else:
                scaled_x_mm = editor_x_mm
                scaled_y_mm = editor_y_mm

            # mm'yi DPI'ya çevir
            x = int((scaled_x_mm / 25.4) * dpi)
            y = int((scaled_y_mm / 25.4) * dpi)

            properties = element.get('properties', {})

            if element_type in ['title', 'text']:
                text = properties.get('text', 'Text')
                # Font boyutu editörden pixel cinsinden alıp DPI'ya ölçekle (tutarlılık için)
                font_size_px = properties.get('fontSize',
                                              14)  # editörde pixel cinsinden
                font_size = int(font_size_px *
                                (dpi / 96))  # 96 DPI -> 300 DPI ölçekleme
                color = properties.get('color', '#000000')
                font_weight = properties.get('fontWeight', 'normal')

                try:
                    if font_weight == 'bold':
                        font = ImageFont.truetype(
                            "static/fonts/DejaVuSans-Bold.ttf", font_size)
                    else:
                        font = ImageFont.truetype(
                            "static/fonts/DejaVuSans.ttf", font_size)
                except:
                    font = default_font

                draw.text((x, y), text, fill=color, font=font)

            elif element_type == 'qr':
                # QR boyutu editörden pixel cinsinden alıp mm'ye çevirip ölçeklendir
                qr_size_px = properties.get('size',
                                            50)  # editörde pixel cinsinden
                qr_size_mm = qr_size_px / 4  # 4px = 1mm

                # A4 modunda QR boyutunu da ölçeklendir
                if is_a4_preview:
                    scale_factor = min(scale_x,
                                       scale_y)  # Aspect ratio korunur
                    scaled_qr_size_mm = qr_size_mm * scale_factor
                else:
                    scaled_qr_size_mm = qr_size_mm

                qr_size = int(
                    (scaled_qr_size_mm / 25.4) * dpi)  # mm'yi DPI'ya çevir
                # QR verisi - önce editörden, yoksa gerçek ürün barkodu
                qr_data = properties.get('data', 'sample')

                # Gerçek ürün barkodunu al
                real_barcode = product_data.get('barcode', '0138523709823')

                # Eğer sample/placeholder verisi ise gerçek barkod kullan
                if qr_data in ['sample_barcode', 'sample', 'placeholder']:
                    qr_data = real_barcode  # Gerçek ürün barkodu

                logger.info(f"QR veri kaynağı: {qr_data}")

                # Debug bilgisi
                logger.info(
                    f"QR Debug (func1): px={qr_size_px}, mm={qr_size_mm}, final_size={qr_size}, pos=({x},{y})"
                )

                # Minimum QR boyutu kontrolü - daha büyük minimum
                if qr_size < 100:  # 100 pixel minimum
                    qr_size = 100
                    logger.warning(f"QR boyutu çok küçük, 100px'e yükseltildi")

                # QR kod oluştur - canvas genişliği zaten başta hesaplandı
                logo_path = os.path.join('static', 'logos', 'gullu_logo.png')
                qr_img = create_qr_with_logo(
                    qr_data, logo_path if os.path.exists(logo_path) else None,
                    qr_size)

                if qr_img:
                    label.paste(qr_img, (x, y))
                    logger.info(
                        f"QR kod başarıyla yapıştırıldı (func1): boyut={qr_size}, pos=({x},{y})"
                    )
                else:
                    logger.error("QR kod oluşturulamadı (func1)!")

            elif element_type == 'image':
                # Image boyutları editörden pixel cinsinden alıp mm'ye çevirip DPI'ya ölçekle
                img_width_px = properties.get('width',
                                              60)  # editörde pixel cinsinden
                img_height_px = properties.get('height', 60)
                img_width_mm = img_width_px / 4  # 4px = 1mm
                img_height_mm = img_height_px / 4
                img_width = int(
                    (img_width_mm / 25.4) * dpi)  # mm'yi DPI'ya çevir
                img_height = int((img_height_mm / 25.4) * dpi)

                # Placeholder için basit bir kare çiz
                draw.rectangle([x, y, x + img_width, y + img_height],
                               outline='#bdc3c7',
                               fill='#ecf0f1',
                               width=2)

                # "IMG" yazısı
                try:
                    img_font = ImageFont.truetype(
                        "static/fonts/DejaVuSans.ttf", 12)
                except:
                    img_font = default_font

                text_bbox = draw.textbbox((0, 0), "IMG", font=img_font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                text_x = x + (img_width - text_width) // 2
                text_y = y + (img_height - text_height) // 2
                draw.text((text_x, text_y),
                          "IMG",
                          fill='#7f8c8d',
                          font=img_font)

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
        return jsonify({
            'success': False,
            'message': 'Önizleme oluşturulamadı'
        })


@enhanced_label_bp.route(
    '/enhanced_product_label/api/generate_advanced_label_preview',
    methods=['POST'])
@enhanced_label_bp.route('/api/generate_advanced_label_preview',
                         methods=['POST'])
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
                color,  # Orijinal
                color.lower(),  # küçük harf
                color.upper(),  # BÜYÜK HARF  
                color.capitalize()  # İlk harf büyük
            ]

            for color_var in color_variations:
                for ext in possible_extensions:
                    potential_path = f"static/images/{model_code}_{color_var}{ext}"
                    if os.path.exists(potential_path):
                        image_path = potential_path
                        logger.info(
                            f"Önizleme görseli bulundu: {potential_path}")
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

        # QR kodları için canvas genişliği hesapla
        max_required_width = width_px
        for element in elements:
            if element.get('type') == 'qr':
                editor_x_mm = element.get('x', 0) / 4  # 4px = 1mm editörde
                if editor_x_mm > label_width:  # QR kod etiket dışında
                    properties = element.get('properties', {})
                    qr_size_px = properties.get('size',
                                                50)  # properties'ten al
                    qr_size_mm = qr_size_px / 4  # 4px = 1mm dönüşümü
                    required_width_mm = editor_x_mm + qr_size_mm + 5  # QR + 5mm boşluk
                    required_width_px = int((required_width_mm / 25.4) * dpi)
                    max_required_width = max(max_required_width,
                                             required_width_px)

        # Gerekli genişlikte etiket oluştur
        label = Image.new('RGB', (max_required_width, height_px), 'white')
        draw = ImageDraw.Draw(label)

        # Etiket sınırlarını çiz (gerçek etiket boyutları)
        actual_label_width_px = int((label_width / 25.4) * dpi)
        actual_label_height_px = int((label_height / 25.4) * dpi)

        # Sınır çizgisi çiz (açık gri, ince çizgi)
        border_color = (200, 200, 200)  # Açık gri
        draw.rectangle(
            [0, 0, actual_label_width_px - 1, actual_label_height_px - 1],
            outline=border_color,
            width=2)

        # Eğer canvas gerçek etiket boyutundan büyükse, kesikli çizgi ile genişletilmiş alanı göster
        if max_required_width > actual_label_width_px:
            # Kesikli dikey çizgi çiz
            for y in range(0, actual_label_height_px, 10):
                draw.line([
                    actual_label_width_px, y, actual_label_width_px,
                    min(y + 5, actual_label_height_px)
                ],
                          fill=(150, 150, 150),
                          width=1)

        # Font ayarları
        try:
            default_font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
            bold_font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        except:
            default_font = ImageFont.load_default()
            bold_font = ImageFont.load_default()

        # Elementleri çiz - Tutarlı koordinat sistemi
        for element in elements:
            element_type = element.get('type')

            # Editörden gelen koordinatları mm'ye çevir
            # Editörde canvas boyutu: width*4 px = width mm
            # Yani 100mm etiket için 400px canvas, 1px = 0.25mm
            editor_x_mm = element.get('x',
                                      0) / 4  # px'i mm'ye çevir (4px = 1mm)
            editor_y_mm = element.get('y', 0) / 4

            # Debug: koordinat dönüşümünü kontrol et
            logger.info(
                f"Element {element_type}: editör=({element.get('x', 0)},{element.get('y', 0)})px -> mm=({editor_x_mm:.1f},{editor_y_mm:.1f})mm"
            )

            # mm'yi DPI'ya çevir
            x = int((editor_x_mm / 25.4) * dpi)
            y = int((editor_y_mm / 25.4) * dpi)

            # Ürün-spesifik alanlar - properties yapısını kullan
            properties = element.get('properties', {})

            if element_type == 'title':
                html_content = element.get('html', 'GÜLLÜ SHOES')
                # Font boyutu properties'ten al, editör formatına uygun
                font_size_px = properties.get('fontSize',
                                              18)  # properties'te sayı olarak
                if isinstance(font_size_px, str):
                    font_size_px = int(font_size_px.replace('px', ''))
                font_size = int(font_size_px * (dpi / 96))

                try:
                    if 'strong' in html_content:
                        font = ImageFont.truetype(
                            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                            font_size)
                    else:
                        font = ImageFont.truetype(
                            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                            font_size)
                except:
                    font = default_font

                # HTML etiketlerini temizle
                import re
                clean_text = re.sub('<[^<]+?>', '', html_content)
                draw.text((x, y), clean_text, fill='black', font=font)

            elif element_type == 'model_code':
                html_content = element.get('html', '[MODEL KODU]')
                # Font boyutu properties'ten al, editör formatına uygun
                font_size_px = properties.get('fontSize',
                                              14)  # properties'te sayı olarak
                if isinstance(font_size_px, str):
                    font_size_px = int(font_size_px.replace('px', ''))
                font_size = int(font_size_px * (dpi / 96))

                try:
                    if 'strong' in html_content:
                        font = ImageFont.truetype(
                            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                            font_size)
                    else:
                        font = ImageFont.truetype(
                            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                            font_size)
                except:
                    font = default_font

                draw.text((x, y),
                          sample_product['model_code'],
                          fill='black',
                          font=font)

            elif element_type == 'color':
                html_content = element.get('html', '[RENK]')
                # Font boyutu properties'ten al, editör formatına uygun
                font_size_px = properties.get('fontSize',
                                              14)  # properties'te sayı olarak
                if isinstance(font_size_px, str):
                    font_size_px = int(font_size_px.replace('px', ''))
                font_size = int(font_size_px * (dpi / 96))

                try:
                    font = ImageFont.truetype(
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                        font_size)
                except:
                    font = default_font

                draw.text((x, y),
                          sample_product['color'],
                          fill='black',
                          font=font)

            elif element_type == 'size':
                html_content = element.get('html', '[BEDEN]')
                # Font boyutu properties'ten al, editör formatına uygun
                font_size_px = properties.get('fontSize',
                                              14)  # properties'te sayı olarak
                if isinstance(font_size_px, str):
                    font_size_px = int(font_size_px.replace('px', ''))
                font_size = int(font_size_px * (dpi / 96))

                try:
                    font = ImageFont.truetype(
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                        font_size)
                except:
                    font = default_font

                draw.text((x, y),
                          sample_product['size'],
                          fill='black',
                          font=font)

            elif element_type == 'qr':
                # QR boyutu editörden properties'ten al - tutarlı veri kaynağı
                properties = element.get('properties', {})
                qr_size_px = properties.get(
                    'size', 50)  # editörde pixel cinsinden (properties'ten)
                qr_size_mm = qr_size_px / 4  # 4px = 1mm
                qr_size = int((qr_size_mm / 25.4) * dpi)  # mm'yi DPI'ya çevir

                # Debug bilgisi
                logger.info(
                    f"QR Debug: px={qr_size_px}, mm={qr_size_mm}, final_size={qr_size}, pos=({x},{y})"
                )

                # QR kod her etiket için unique barkod kullanmalı
                # product_data'dan gerçek barkodu al (çoklu etiket desteği)
                if product_data and 'barcode' in product_data:
                    qr_data = product_data['barcode']  # Her etiket için farklı barkod
                    print(f"DEBUG QR: Etiket için unique barkod: {qr_data}")
                else:
                    qr_data = sample_product['barcode']  # Fallback
                    print(f"DEBUG QR: Fallback barkod kullanılıyor: {qr_data}")

                # Minimum QR boyutu kontrolü - daha büyük minimum
                if qr_size < 100:  # 100 pixel minimum
                    qr_size = 100
                    logger.warning(f"QR boyutu çok küçük, 100px'e yükseltildi")

                # QR kod oluştur - canvas genişliği zaten başta hesaplandı
                logo_path = os.path.join('static', 'logos', 'gullu_logo.png')
                qr_img = create_qr_with_logo(
                    qr_data, logo_path if os.path.exists(logo_path) else None,
                    qr_size)

                # QR kod başarıyla oluştu mu kontrol et
                if qr_img:
                    label.paste(qr_img, (x, y))
                    logger.info(
                        f"QR kod başarıyla yapıştırıldı: boyut={qr_size}, pos=({x},{y})"
                    )
                else:
                    logger.error("QR kod oluşturulamadı!")

            elif element_type == 'barcode':
                # Barkod her etiket için unique data kullanmalı
                if product_data and 'barcode' in product_data:
                    barcode_data = product_data['barcode']  # Her etiket için farklı barkod
                    print(f"DEBUG BARCODE: Etiket için unique barkod: {barcode_data}")
                else:
                    barcode_data = sample_product['barcode']  # Fallback
                    print(f"DEBUG BARCODE: Fallback barkod kullanılıyor: {barcode_data}")
                # Font boyutu properties'ten al, editör formatına uygun
                font_size_px = properties.get('fontSize',
                                              12)  # properties'te sayı olarak
                if isinstance(font_size_px, str):
                    font_size_px = int(font_size_px.replace('px', ''))
                font_size = int(font_size_px * (dpi / 96))

                try:
                    font = ImageFont.truetype(
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                        font_size)
                except:
                    font = default_font

                # Sadece barkod rakamını yazı olarak göster
                draw.text((x, y), barcode_data, fill='black', font=font)

            elif element_type == 'product_image':
                # Image boyutları editörden pixel cinsinden alıp mm'ye çevirip DPI'ya ölçekle
                img_width_px = element.get('width',
                                           50)  # editörde pixel cinsinden
                img_height_px = element.get('height', 50)
                img_width_mm = img_width_px / 4  # 4px = 1mm
                img_height_mm = img_height_px / 4
                img_width = int(
                    (img_width_mm / 25.4) * dpi)  # mm'yi DPI'ya çevir
                img_height = int((img_height_mm / 25.4) * dpi)

                # Gerçek ürün görseli varsa kullan, yoksa placeholder
                image_loaded = False
                try:
                    if sample_product['image_path'] and os.path.exists(
                            sample_product['image_path']):
                        product_img = Image.open(sample_product['image_path'])
                        # RGBA moduna dönüştür eğer gerekirse
                        if product_img.mode != 'RGB':
                            product_img = product_img.convert('RGB')
                        product_img = product_img.resize(
                            (img_width, img_height), Image.Resampling.LANCZOS)
                        label.paste(product_img, (x, y))
                        image_loaded = True
                        logger.info(
                            f"Ürün görseli yüklendi: {sample_product['image_path']}"
                        )
                except Exception as img_error:
                    logger.error(f"Ürün görseli yükleme hatası: {img_error}")

                # Görsel yüklenemedi ise placeholder göster
                if not image_loaded:
                    draw.rectangle([x, y, x + img_width, y + img_height],
                                   outline='#3498db',
                                   fill='#e3f2fd',
                                   width=2)

                    try:
                        img_font = ImageFont.truetype(
                            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                            10)
                    except:
                        img_font = default_font

                    text = f"{sample_product['model_code']}\n{sample_product['color']}"
                    text_bbox = draw.textbbox((0, 0), text, font=img_font)
                    text_height = text_bbox[3] - text_bbox[1]
                    text_x = x + 5
                    text_y = y + (img_height - text_height) // 2
                    draw.text((text_x, text_y),
                              text,
                              fill='#2196f3',
                              font=img_font)

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
        return jsonify({
            'success': False,
            'message': f'Önizleme oluşturulamadı: {str(e)}'
        })


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


@enhanced_label_bp.route('/enhanced_product_label/api/print_multiple_labels',
                         methods=['POST'])
@enhanced_label_bp.route('/api/print_multiple_labels', methods=['POST'])
def print_multiple_labels():
    """Çoklu etiket yazdırma için sayfa hazırla"""
    try:
        data = request.get_json()
        print(f"DEBUG API: Gelen tüm veri: {data}")
        
        # Veri türlerini kontrol et ve parse et
        labels = data.get('labels', [])
        design = data.get('design', {})
        
        print(f"DEBUG API: Raw data types - labels: {type(labels)}, design: {type(design)}")
        
        # Design JSON string ise parse et
        if isinstance(design, str):
            try:
                design = json.loads(design)
                print(f"DEBUG API: Design JSON parsed successfully")
            except Exception as parse_error:
                print(f"DEBUG API: Design JSON parse hatası: {parse_error}")
                design = {}
        
        # Labels JSON string ise parse et        
        if isinstance(labels, str):
            try:
                labels = json.loads(labels)
                print(f"DEBUG API: Labels JSON parsed successfully")
            except Exception as parse_error:
                print(f"DEBUG API: Labels JSON parse hatası: {parse_error}")
                labels = []
                
        print(f"DEBUG API: Final parsed - labels count: {len(labels)}, design elements: {len(design.get('elements', []))}")
        
        paper_size = data.get('paper_size', 'a4')
        page_orientation = data.get('page_orientation', 'portrait')
        labels_per_row = data.get('labels_per_row', 2)
        labels_per_col = data.get('labels_per_col', 5)

        # Debug: Gelen tasarım verisini logla
        logger.info(f"A4 Yazdırma başladı - Etiket sayısı: {len(labels)}")
        logger.info(
            f"A4 Tasarım elementi sayısı: {len(design.get('elements', []))}")
        logger.info(
            f"A4 Etiket boyutları: {data.get('label_width', 'N/A')}x{data.get('label_height', 'N/A')}mm"
        )

        for i, element in enumerate(design.get('elements', [])):
            logger.info(
                f"A4 Element {i}: type={element.get('type')}, x={element.get('x')}, y={element.get('y')}, props={element.get('properties', {})}"
            )

        # A4 Sayfa Başı Yapılandırma - Margin ve gap sıfır, sayfa başından başla
        A4_FIXED_CONFIG = {
            'PAGE_WIDTH': 210,
            'MARGIN_LEFT': 0,      # Sayfa başından başla
            'MARGIN_RIGHT': 0,     # Sayfa başından başla
            'COLUMN_GAP': 0,       # Etiketler arası boşluk yok
            'COLUMNS': 3,
            'PAGE_HEIGHT': 297,
            'MARGIN_TOP': 0,       # Sayfa başından başla
            'MARGIN_BOTTOM': 0,    # Sayfa başından başla
            'ROW_GAP': 0,          # Etiketler arası boşluk yok
            'ROWS': 7,
            'LABELS_PER_PAGE': 21,
            'QR_SIZE_MM': 18,
            'LABEL_WIDTH_APPROX': (210 / 3),     # Sayfa genişliği / sütun sayısı
            'LABEL_HEIGHT_APPROX': (297 / 7)     # Sayfa yüksekliği / satır sayısı
        }

        # Etiket boyutu kontrolü - Product Label A4 sistemiyle uyumlu
        label_size = data.get('label_size', 'custom')
        if label_size == 'a4-standard':
            # Product Label A4_FIXED_CONFIG değerlerini kullan
            label_width = A4_FIXED_CONFIG['LABEL_WIDTH_APPROX']
            label_height = A4_FIXED_CONFIG['LABEL_HEIGHT_APPROX']
            top_margin = A4_FIXED_CONFIG['MARGIN_TOP']
            left_margin = A4_FIXED_CONFIG['MARGIN_LEFT']
            horizontal_gap = A4_FIXED_CONFIG['COLUMN_GAP']
            vertical_gap = A4_FIXED_CONFIG['ROW_GAP']
            # Sütun/satır sayısını da zorla uygula - A4 Standard: 3 sütun, 7 satır
            labels_per_row = A4_FIXED_CONFIG['COLUMNS']  # 3 sütun (yatay)
            labels_per_col = A4_FIXED_CONFIG['ROWS']  # 7 satır (dikey)
        else:
            label_width = data.get('label_width', 100)
            label_height = data.get('label_height', 50)
            top_margin = data.get('top_margin', 10)
            left_margin = data.get('left_margin', 10)
            horizontal_gap = data.get('horizontal_gap', 5)
            vertical_gap = data.get('vertical_gap', 5)
        print_quality = data.get('print_quality', 300)

        if not labels:
            return jsonify({
                'success': False,
                'message': 'Yazdırılacak etiket yok'
            })

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
        elif paper_size == 'custom':
            # Custom boyut - etiket boyutuna göre sayfa oluştur
            # Etiket boyutuna kenar boşlukları ekleyerek sayfa boyutunu hesapla
            page_width = label_width + (left_margin *
                                        2) + 10  # 10mm extra margin
            page_height = label_height + (top_margin *
                                          2) + 10  # 10mm extra margin
        else:
            page_width, page_height = 210, 297  # Varsayılan A4 dikey

        # DPI ayarı
        dpi = print_quality
        page_width_px = int((page_width / 25.4) * dpi)
        page_height_px = int((page_height / 25.4) * dpi)

        # Sayfa oluştur
        page = Image.new('RGB', (page_width_px, page_height_px), 'white')

        # SAYFA BAŞI SİSTEMİ: Etiket boyutlarını sayfa boyutuna göre hesapla
        # Sayfa genişliği / sütun sayısı = etiket genişliği (pixel)
        # Sayfa yüksekliği / satır sayısı = etiket yüksekliği (pixel)
        label_width_px = page_width_px // max(1, labels_per_row)
        label_height_px = page_height_px // max(1, labels_per_col)
        
        print(f"DEBUG: SAYFA BAŞI - Sayfa boyutu: {page_width_px}x{page_height_px} px")
        print(f"DEBUG: SAYFA BAŞI - Grid: {labels_per_row}x{labels_per_col}")
        print(f"DEBUG: SAYFA BAŞI - Etiket boyutu: {label_width_px}x{label_height_px} px")

        # SAYFA BAŞI SİSTEMİ: Margin ve gap kullanmıyoruz - sayfa başından başla
        margin_x = 0  # Kenar boşluğu yok
        margin_y = 0  # Kenar boşluğu yok
        gap_x = 0     # Etiketler arası boşluk yok  
        gap_y = 0     # Etiketler arası boşluk yok
        
        print(f"DEBUG: SAYFA BAŞI - Margin ve gap sıfırlandı: margin_x={margin_x}, margin_y={margin_y}, gap_x={gap_x}, gap_y={gap_y}")

        # Kullanıcının belirlediği sütun/satır sayısını zorla uygula
        # Sayfa boyutuna sığıp sığmadığına bakmadan kullanıcı ayarlarını kullan
        max_labels_per_row = labels_per_row
        max_labels_per_col = labels_per_col

        # Minimum 1 etiket garantisi
        max_labels_per_row = max(1, max_labels_per_row)
        max_labels_per_col = max(1, max_labels_per_col)

        # Çoklu sayfa desteği
        labels_per_page = max_labels_per_row * max_labels_per_col
        total_pages = (len(labels) + labels_per_page - 1) // labels_per_page

        # Etiketleri sayfanın tam başından itibaren yerleştir - kenar boşluklarını yok say
        start_x = 0
        start_y = 0
        
        print(f"DEBUG: Etiketler sayfanın tam başından itibaren yerleştirilecek - start_x: {start_x}, start_y: {start_y}")

        all_pages = []

        for page_num in range(total_pages):
            # Her sayfa için yeni sayfa oluştur
            current_page = Image.new('RGB', (page_width_px, page_height_px),
                                     'white')

            start_idx = page_num * labels_per_page
            end_idx = min(start_idx + labels_per_page, len(labels))
            page_labels = labels[start_idx:end_idx]

            # Bu sayfadaki etiketleri yerleştir
            for i, label_data in enumerate(page_labels):
                row = i // max_labels_per_row
                col = i % max_labels_per_row

                # Sayfa başından itibaren bitişik etiket pozisyonu (gap yok)
                x = start_x + col * label_width_px
                y = start_y + row * label_height_px
                
                print(f"DEBUG: Etiket {i} - row: {row}, col: {col}, x: {x}, y: {y} (px)")

                # Tasarım kullanarak etiket oluştur - A4 modu aktif
                label_img = create_label_with_design(
                    label_data,
                    design,
                    label_width,
                    label_height,
                    is_a4_mode=True  # A4 yazdırma modu
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
                'success':
                True,
                'image_url':
                f"/static/generated/{filename}",
                'total_pages':
                1,
                'message':
                f'{len(labels)} etiket yazdırma için hazırlandı'
            })
        else:
            # Çoklu sayfa - PDF oluştur
            filename = f"print_labels_{timestamp}.pdf"
            filepath = os.path.join('static', 'generated', filename)

            all_pages[0].save(filepath,
                              'PDF',
                              resolution=dpi,
                              save_all=True,
                              append_images=all_pages[1:])

            return jsonify({
                'success':
                True,
                'image_url':
                f"/static/generated/{filename}",
                'total_pages':
                len(all_pages),
                'message':
                f'{len(labels)} etiket {len(all_pages)} sayfada yazdırma için hazırlandı'
            })

    except Exception as e:
        logger.error(f"Çoklu etiket yazdırma hatası: {e}")
        return jsonify({
            'success':
            False,
            'message':
            f'Yazdırma hazırlanırken hata oluştu: {str(e)}'
        })


def create_label_with_design(product_data,
                             design,
                             label_width,
                             label_height,
                             is_a4_mode=False):
    print(f"DEBUG: create_label_with_design called with product: {product_data}, design: {design.get('name', 'No name')}, is_a4_mode: {is_a4_mode}")
    """Tasarım kullanarak tek etiket oluştur"""
    try:
        # Etiket boyutları (mm'den pixel'e çevir, 300 DPI)
        dpi = 300
        width_px = int((label_width / 25.4) * dpi)
        height_px = int((label_height / 25.4) * dpi)

        # Boş etiket oluştur
        label = Image.new('RGB', (width_px, height_px), 'white')
        draw = ImageDraw.Draw(label)

        # Etiket kenarları (hayali çizgiler) - çok ince açık gri
        border_color = (220, 220, 220)  # Çok açık gri
        border_width = 1  # 1 pixel ince kenar
        draw.rectangle([0, 0, width_px - 1, height_px - 1],
                       outline=border_color,
                       width=border_width)

        # Font ayarları
        try:
            default_font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        except:
            default_font = ImageFont.load_default()

        # Ürün bilgileri
        barcode = product_data.get('barcode', 'N/A')
        model_code = product_data.get('model_code', 'N/A')
        color = product_data.get('color', 'N/A')
        size = product_data.get('size', 'N/A')

        # Ürün görseli yolu - büyük/küçük harf duyarsız arama
        possible_extensions = ['.jpg', '.jpeg', '.png', '.webp']
        image_path = None

        # Farklı harf kombinasyonlarını dene
        color_variations = [
            color,  # Orijinal
            color.lower(),  # küçük harf
            color.upper(),  # BÜYÜK HARF  
            color.capitalize()  # İlk harf büyük
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

        # Koordinat sistemi düzeltmesi - A4 modu varsa önizleme ile aynı ölçeklendirme
        if is_a4_mode:
            # A4 modunda önizleme ile aynı ölçeklendirme oranlarını kullan
            editor_default_width = 100  # mm
            editor_default_height = 50  # mm

            # A4'te kullanılan gerçek etiket boyutları
            actual_label_width = label_width  # A4'te hesaplanan boyut
            actual_label_height = label_height

            # Önizleme ile aynı ölçeklendirme oranları
            scale_x = actual_label_width / editor_default_width
            scale_y = actual_label_height / editor_default_height

            logger.info(
                f"A4 Print Ölçeklendirme: editör={editor_default_width}x{editor_default_height}mm, A4={actual_label_width:.1f}x{actual_label_height:.1f}mm"
            )
            logger.info(
                f"A4 Print ölçeklendirme oranları: x={scale_x:.2f}, y={scale_y:.2f}"
            )
        else:
            # Normal modu - ölçeklendirme yok
            scale_x = 1.0
            scale_y = 1.0
            logger.info(f"Normal mod: ölçeklendirme yok")

        # Çakışma kontrolü için ürün görseli pozisyonunu tespit et
        product_image_area = None
        for element in elements:
            if element.get('type') == 'product_image':
                img_x_px = element.get('x', 0)
                img_y_px = element.get('y', 0) 
                img_width = element.get('width', 62)
                img_height = element.get('height', 62)
                
                # Ürün görseli alanını mm cinsinden hesapla
                img_x_mm = img_x_px / 4
                img_y_mm = img_y_px / 4  
                img_w_mm = img_width / 4
                img_h_mm = img_height / 4
                
                product_image_area = {
                    'x': img_x_mm, 'y': img_y_mm, 
                    'width': img_w_mm, 'height': img_h_mm
                }
                print(f"Ürün görseli alanı: ({img_x_mm:.1f}, {img_y_mm:.1f}) boyut: {img_w_mm:.1f}x{img_h_mm:.1f}mm")
                break

        for element in elements:
            element_type = element.get('type')

            # Editör koordinatlarını direkt al
            editor_x_px = element.get('x', 0)
            editor_y_px = element.get('y', 0)
            
            print(f"Element {element_type}: editör_koordinatları=({editor_x_px}, {editor_y_px})")

            # Editör koordinat sistemi: 4px = 1mm (doğrudan dönüştürme)
            editor_x_mm = editor_x_px / 4
            editor_y_mm = editor_y_px / 4

            # Çakışma kontrolü - yazı elementleri için
            if element_type in ['model_code', 'color', 'size', 'title'] and product_image_area:
                # Yazının ürün görseli ile çakışıp çakışmadığını kontrol et
                text_width_mm = 20  # Yaklaşık yazı genişliği
                text_height_mm = 5  # Yaklaşık yazı yüksekliği
                
                # Çakışma kontrolü
                if (editor_x_mm < product_image_area['x'] + product_image_area['width'] and
                    editor_x_mm + text_width_mm > product_image_area['x'] and
                    editor_y_mm < product_image_area['y'] + product_image_area['height'] and
                    editor_y_mm + text_height_mm > product_image_area['y']):
                    
                    # Çakışma var - yazıyı ürün görseli yanına kaydır
                    editor_x_mm = product_image_area['x'] + product_image_area['width'] + 2  # 2mm boşluk
                    print(f"ÇAKIŞMA DÜZELTME: {element_type} kaydırıldı -> ({editor_x_mm:.1f}, {editor_y_mm:.1f})mm")

            # A4 etiket boyutlarına ölçeklendir
            scaled_x_mm = editor_x_mm * scale_x
            scaled_y_mm = editor_y_mm * scale_y

            # mm'yi A4 DPI'sına çevir
            x = int((scaled_x_mm / 25.4) * dpi)
            y = int((scaled_y_mm / 25.4) * dpi)
            
            print(f"Element {element_type}: mm=({editor_x_mm:.1f}, {editor_y_mm:.1f}), scaled_mm=({scaled_x_mm:.1f}, {scaled_y_mm:.1f}), final_px=({x}, {y})")

            if element_type == 'title':
                html_content = element.get('html', 'GÜLLÜ SHOES')
                # Font boyutu alma - properties kontrol et
                font_size = 18
                if 'properties' in element and 'fontSize' in element[
                        'properties']:
                    font_size = int(element['properties']['fontSize'])
                elif 'fontSize' in element:
                    font_size_str = element.get('fontSize', '18px')
                    if isinstance(font_size_str, str):
                        font_size = int(font_size_str.replace('px', ''))
                    else:
                        font_size = int(font_size_str)

                # Font boyutunu DPI'ya göre ölçeklendir (96->300 DPI)
                font_size = int(font_size * (dpi / 96))

                try:
                    font = ImageFont.truetype(
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                        font_size)
                except:
                    font = default_font

                # HTML etiketlerini temizle
                import re
                clean_text = re.sub('<[^<]+?>', '', html_content)
                draw.text((x, y), clean_text, fill='black', font=font)

            elif element_type == 'model_code':
                # Font boyutu alma - properties öncelikli
                font_size = 14
                if 'properties' in element and 'fontSize' in element[
                        'properties']:
                    font_size = int(element['properties']['fontSize'])
                elif 'fontSize' in element:
                    font_size_str = element.get('fontSize', '14px')
                    if isinstance(font_size_str, str):
                        font_size = int(font_size_str.replace('px', ''))
                    else:
                        font_size = int(
                            font_size_str)  # Hata durumunda varsayılan boyut

                font_size = int(font_size * (dpi / 96))

                try:
                    font = ImageFont.truetype(
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                        font_size)
                except:
                    font = default_font

                draw.text((x, y), model_code, fill='black', font=font)

            elif element_type == 'color':
                # Font boyutu alma - properties öncelikli
                font_size = 14
                if 'properties' in element and 'fontSize' in element[
                        'properties']:
                    font_size = int(element['properties']['fontSize'])
                elif 'fontSize' in element:
                    font_size_str = element.get('fontSize', '14px')
                    if isinstance(font_size_str, str):
                        font_size = int(font_size_str.replace('px', ''))
                    else:
                        font_size = int(font_size_str)

                font_size = int(font_size * (dpi / 96))

                try:
                    font = ImageFont.truetype(
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                        font_size)
                except:
                    font = default_font

                draw.text((x, y), color, fill='black', font=font)

            elif element_type == 'size':
                # Font boyutu alma - properties öncelikli
                font_size = 14
                if 'properties' in element and 'fontSize' in element[
                        'properties']:
                    font_size = int(element['properties']['fontSize'])
                elif 'fontSize' in element:
                    font_size_str = element.get('fontSize', '14px')
                    if isinstance(font_size_str, str):
                        font_size = int(font_size_str.replace('px', ''))
                    else:
                        font_size = int(font_size_str)

                font_size = int(font_size * (dpi / 96))

                try:
                    font = ImageFont.truetype(
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                        font_size)
                except:
                    font = default_font

                draw.text((x, y), size, fill='black', font=font)

            elif element_type == 'qr':
                # QR boyutu properties'den al, yoksa element'den, yoksa varsayılan
                qr_size = 50  # Varsayılan boyut

                # Properties'den boyut alma (öncelikli) - pixel cinsinden
                if 'properties' in element and 'size' in element['properties']:
                    qr_size_px = int(element['properties']['size'])
                elif 'size' in element:
                    qr_size_px = int(element['size'])
                elif 'width' in element:
                    qr_size_px = int(element['width'])
                else:
                    qr_size_px = 200  # Varsayılan 200px = 50mm

                # Editör boyutunu mm'ye çevir (4px = 1mm) sonra A4 boyutlarına ölçeklendir
                qr_size_mm = qr_size_px / 4  # 4px = 1mm

                # QR boyutunu da A4 etiket boyutlarına ölçeklendir
                # En küçük ölçeklendirme oranını kullan (aspect ratio korunur)
                scale_factor = min(scale_x, scale_y)
                scaled_qr_size_mm = qr_size_mm * scale_factor

                qr_size = int(
                    (scaled_qr_size_mm / 25.4) * dpi)  # mm'den DPI'ya

                # Minimum boyut kontrolü - önizleme ile aynı
                if qr_size < 100:  # 100 pixel minimum (önizleme ile aynı)
                    qr_size = 100
                    logger.info(
                        f"A4 QR boyutu minimum sınırına yükseltildi: {qr_size}px"
                    )

                # QR verisi - önizleme ile aynı kaynak kullan
                properties = element.get('properties', {})
                qr_data = properties.get(
                    'data', barcode)  # Önce editörden, yoksa ürün barkodu

                # Eğer sample/placeholder verisi ise gerçek barkod kullan
                if qr_data in ['sample_barcode', 'sample', 'placeholder']:
                    qr_data = barcode  # Gerçek ürün barkodu

                print(f"A4 QR veri kaynağı: {qr_data}")
                print(f"A4 QR Debug: element_size_px={qr_size_px}, mm={qr_size_mm:.1f}, scaled_mm={scaled_qr_size_mm:.1f}, final_dpi_size={qr_size}, data={qr_data}")

                logo_path = os.path.join('static', 'logos', 'gullu_logo.png')
                print(f"A4 QR Logo path: {logo_path}, exists: {os.path.exists(logo_path)}")
                
                qr_img = create_qr_with_logo(
                    qr_data, logo_path if os.path.exists(logo_path) else None,
                    qr_size)
                
                print(f"A4 QR Image created: {qr_img is not None}, size: {qr_img.size if qr_img else 'None'}")

                if qr_img:
                    # Etiket boyutlarını kontrol et
                    label_size = label.size
                    logger.info(f"A4 etiket boyutu: {label_size}")
                    logger.info(
                        f"A4 QR pozisyon kontrolü: ({x},{y}) + {qr_img.size} etiket içinde mi?"
                    )

                    # QR kodu belirtilen koordinatlara yerleştir
                    label.paste(qr_img, (x, y))
                    logger.info(f"A4 QR kod yerleştirildi: ({x},{y})")
                else:
                    logger.error("A4 QR kod oluşturulamadı")

            elif element_type == 'barcode':
                # Barkod elementi - sadece rakam olarak göster
                font_size = 12
                if 'properties' in element and 'fontSize' in element[
                        'properties']:
                    font_size = int(element['properties']['fontSize'])
                elif 'fontSize' in element:
                    font_size_str = element.get('fontSize', '12px')
                    if isinstance(font_size_str, str):
                        font_size = int(font_size_str.replace('px', ''))
                    else:
                        font_size = int(font_size_str)

                font_size = int(font_size * (dpi / 96))

                try:
                    font = ImageFont.truetype(
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                        font_size)
                except:
                    font = default_font

                # Sadece barkod rakamını yazı olarak göster
                draw.text((x, y), barcode, fill='black', font=font)

            elif element_type == 'product_image':
                # Görsel boyutu doğrudan ölçeklendirme
                img_width = int(element.get('width', 50))
                img_height = int(element.get('height', 50))
                img_width = int(img_width * (dpi / 96))
                img_height = int(img_height * (dpi / 96))

                # Ürün görseli yükle
                print(f"A4 Product image: path={image_path}, exists={os.path.exists(image_path) if image_path else 'No path'}")
                image_loaded = False
                try:
                    if image_path and os.path.exists(image_path):
                        product_img = Image.open(image_path)
                        if product_img.mode != 'RGB':
                            product_img = product_img.convert('RGB')
                        product_img = product_img.resize(
                            (img_width, img_height), Image.Resampling.LANCZOS)
                        label.paste(product_img, (x, y))
                        image_loaded = True
                        print(f"A4 Product image loaded successfully: {image_path}")
                except Exception as e:
                    print(f"A4 Product image load failed: {e}")
                    pass

                # Placeholder
                if not image_loaded:
                    draw.rectangle([x, y, x + img_width, y + img_height],
                                   outline='#3498db',
                                   fill='#e3f2fd',
                                   width=2)

                    try:
                        img_font = ImageFont.truetype(
                            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                            10)
                    except:
                        img_font = default_font

                    text = f"{model_code}\n{color}"
                    text_x = x + 5
                    text_y = y + 5
                    draw.text((text_x, text_y),
                              text,
                              fill='#2196f3',
                              font=img_font)

        return label

    except Exception as e:
        logger.error(f"Etiket oluşturma hatası: {e}")
        # Basit fallback etiket - boyutları yeniden tanımla
        fallback_dpi = 300
        fallback_width_px = int((label_width / 25.4) * fallback_dpi)
        fallback_height_px = int((label_height / 25.4) * fallback_dpi)
        fallback_label = Image.new('RGB',
                                   (fallback_width_px, fallback_height_px),
                                   'white')
        fallback_draw = ImageDraw.Draw(fallback_label)
        fallback_draw.text(
            (10, 10),
            f"{product_data.get('model_code', 'N/A')} - {product_data.get('color', 'N/A')}",
            fill='black')
        return fallback_label
