from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for
from flask_login import login_required, current_user
from models import Product, db
from datetime import datetime
import json
import logging
import os
from werkzeug.utils import secure_filename
import uuid
from login_logout import login_required, roles_required

# Logger ayarları
logger = logging.getLogger(__name__)

# Blueprint oluştur
product_create_bp = Blueprint('product_create', __name__)

# Görsel yükleme için izin verilen dosya formatları
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@product_create_bp.route('/product_create')
@login_required
@roles_required('admin', 'user')
def product_create_page():
    """Ürün oluşturma sayfasını render et"""
    return render_template('product_create_new.html')

@product_create_bp.route('/api/create_product', methods=['POST'])
@login_required
@roles_required('admin', 'user')
def create_product():
    """Yeni ürün oluştur"""
    try:
        data = request.get_json()
        
        # Zorunlu alanları kontrol et
        required_fields = ['barcode', 'title', 'product_main_id', 'brand', 'category_id', 
                         'size', 'color', 'sale_price', 'list_price', 'quantity']
        
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'message': f'{field} alanı zorunludur.'
                }), 400
        
        # Barkodun benzersiz olduğunu kontrol et
        existing_product = Product.query.filter_by(barcode=data['barcode']).first()
        if existing_product:
            return jsonify({
                'success': False,
                'message': 'Bu barkod zaten mevcut.'
            }), 400
        
        # Yeni ürünü oluştur
        new_product = Product(
            barcode=data['barcode'],
            title=data['title'],
            product_main_id=data['product_main_id'],
            brand=data.get('brand'),
            category_id=data.get('category_id'),
            category_name=data.get('category_name'),
            size=data['size'],
            color=data['color'],
            sale_price=float(data['sale_price']),
            list_price=float(data['list_price']),
            quantity=int(data['quantity']),
            description=data.get('description', ''),
            attributes=data.get('attributes', {}),
            cargo_company=data.get('cargo_company'),
            delivery_duration=data.get('delivery_duration'),
            stock_code=data.get('stock_code'),
            dimension_weight=float(data.get('dimension_weight', 0)) if data.get('dimension_weight') else None,
            dimension_length=float(data.get('dimension_length', 0)) if data.get('dimension_length') else None,
            dimension_width=float(data.get('dimension_width', 0)) if data.get('dimension_width') else None,
            dimension_height=float(data.get('dimension_height', 0)) if data.get('dimension_height') else None,
            vat_rate=int(data.get('vat_rate', 20)),
            gender=data.get('gender'),
            images=data.get('images', ''),
            variants=json.dumps([]),
            archived=False,
            locked=False,
            on_sale=True,
            reject_reason='',
            currency_type='TRY',
            marketplace_status={'created': True, 'trendyol': 'pending'}
        )
        
        # Veritabanına ekle
        db.session.add(new_product)
        db.session.commit()
        
        logger.info(f"Yeni ürün oluşturuldu: {new_product.barcode} - {new_product.title}")
        
        return jsonify({
            'success': True,
            'message': 'Ürün başarıyla oluşturuldu.',
            'product': {
                'barcode': new_product.barcode,
                'title': new_product.title,
                'product_main_id': new_product.product_main_id
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ürün oluşturma hatası: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Ürün oluşturulurken hata oluştu: {str(e)}'
        }), 500

@product_create_bp.route('/api/upload_product_image', methods=['POST'])
@login_required
@roles_required('admin', 'user')
def upload_product_image():
    """Ürün görseli yükle"""
    try:
        if 'image' not in request.files:
            return jsonify({
                'success': False,
                'message': 'Görsel dosyası bulunamadı.'
            }), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({
                'success': False,
                'message': 'Dosya seçilmedi.'
            }), 400
        
        if file and file.filename and allowed_file(file.filename):
            # Benzersiz dosya adı oluştur
            file_ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4()}.{file_ext}"
            
            # Görselleri kaydetmek için klasör
            upload_folder = os.path.join('static', 'images', 'products')
            os.makedirs(upload_folder, exist_ok=True)
            
            # Dosyayı kaydet
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            
            # URL'i döndür
            image_url = f"/static/images/products/{filename}"
            
            return jsonify({
                'success': True,
                'message': 'Görsel başarıyla yüklendi.',
                'image_url': image_url
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Geçersiz dosya formatı. Sadece PNG, JPG, JPEG, GIF ve WEBP formatları kabul edilir.'
            }), 400
            
    except Exception as e:
        logger.error(f"Görsel yükleme hatası: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Görsel yüklenirken hata oluştu: {str(e)}'
        }), 500

@product_create_bp.route('/api/get_trendyol_categories', methods=['GET'])
@login_required
def get_trendyol_categories():
    """Trendyol kategori listesini döndür (örnek veriler)"""
    # Gerçek uygulamada bu veriler Trendyol API'den çekilecek
    categories = [
        {"id": 387, "name": "Ayakkabı > Erkek > Günlük Ayakkabı"},
        {"id": 388, "name": "Ayakkabı > Erkek > Spor Ayakkabı"},
        {"id": 389, "name": "Ayakkabı > Erkek > Bot"},
        {"id": 390, "name": "Ayakkabı > Kadın > Günlük Ayakkabı"},
        {"id": 391, "name": "Ayakkabı > Kadın > Topuklu Ayakkabı"},
        {"id": 392, "name": "Ayakkabı > Kadın > Bot"},
        {"id": 393, "name": "Ayakkabı > Çocuk > Spor Ayakkabı"},
        {"id": 394, "name": "Ayakkabı > Çocuk > Günlük Ayakkabı"},
    ]
    
    return jsonify({
        'success': True,
        'categories': categories
    })

@product_create_bp.route('/api/send_to_marketplace', methods=['POST'])
@login_required
@roles_required('admin', 'user')
def send_to_marketplace():
    """Ürünü seçilen pazaryerine gönder"""
    try:
        data = request.get_json()
        barcode = data.get('barcode')
        marketplace = data.get('marketplace', 'trendyol')
        
        if not barcode:
            return jsonify({
                'success': False,
                'message': 'Barkod bilgisi gerekli.'
            }), 400
        
        # Ürünü bul
        product = Product.query.filter_by(barcode=barcode).first()
        if not product:
            return jsonify({
                'success': False,
                'message': 'Ürün bulunamadı.'
            }), 404
        
        # Pazaryeri durumunu güncelle
        if not product.marketplace_status:
            product.marketplace_status = {}
        
        product.marketplace_status[marketplace] = 'sending'
        
        # Burada gerçek API entegrasyonu yapılacak
        # Örnek: Trendyol API'ye ürün gönderme
        
        # Başarılı gönderim sonrası durumu güncelle
        product.marketplace_status[marketplace] = 'pending_approval'
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Ürün {marketplace} platformuna gönderildi.',
            'status': product.marketplace_status
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Pazaryerine gönderme hatası: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Ürün gönderilirken hata oluştu: {str(e)}'
        }), 500

@product_create_bp.route('/api/create_product_with_variants', methods=['POST'])
@login_required
@roles_required('admin', 'user')
def create_product_with_variants():
    """Varyantlı ürün oluştur"""
    try:
        data = request.get_json()
        
        # Ana ürün bilgilerini al
        product_main_id = data.get('product_main_id')
        brand = data.get('brand')
        category_id = data.get('category_id')
        category_name = data.get('category_name')
        title = data.get('title')
        description = data.get('description', '')
        gender = data.get('gender')
        cargo_company = data.get('cargo_company')
        delivery_duration = data.get('delivery_duration')
        dimension_weight = float(data.get('dimension_weight', 0)) if data.get('dimension_weight') else None
        dimension_length = float(data.get('dimension_length', 0)) if data.get('dimension_length') else None
        dimension_width = float(data.get('dimension_width', 0)) if data.get('dimension_width') else None
        dimension_height = float(data.get('dimension_height', 0)) if data.get('dimension_height') else None
        vat_rate = int(data.get('vat_rate', 20))
        images = data.get('images', [])
        
        # Attributes
        attributes = {}
        for key, value in data.items():
            if key.startswith('attributes[') and key.endswith(']'):
                attr_name = key[11:-1]  # Extract attribute name
                if value:  # Only add non-empty attributes
                    attributes[attr_name] = value
        
        # Varyantları işle
        variants = data.get('variants', [])
        if not variants:
            return jsonify({
                'success': False,
                'message': 'En az bir varyant eklemelisiniz.'
            }), 400
        
        created_products = []
        
        # Her varyant için ayrı bir ürün oluştur
        for variant in variants:
            # Barkodun benzersiz olduğunu kontrol et
            existing_product = Product.query.filter_by(barcode=variant['barcode']).first()
            if existing_product:
                return jsonify({
                    'success': False,
                    'message': f'Bu barkod zaten mevcut: {variant["barcode"]}'
                }), 400
            
            # Yeni ürünü oluştur
            new_product = Product(
                barcode=variant['barcode'],
                title=f"{title} - {variant['color']} - Beden {variant['size']}",
                product_main_id=product_main_id,
                brand=brand,
                category_id=category_id,
                category_name=category_name,
                size=str(variant['size']),
                color=variant['color'],
                sale_price=float(variant['price']),
                list_price=float(variant['price']),  # İlk başta satış fiyatıyla aynı
                quantity=int(variant['stock']),
                stock_code=variant.get('stock_code', ''),
                description=description,
                attributes=attributes,
                cargo_company=cargo_company,
                delivery_duration=delivery_duration,
                dimension_weight=dimension_weight,
                dimension_length=dimension_length,
                dimension_width=dimension_width,
                dimension_height=dimension_height,
                vat_rate=vat_rate,
                gender=gender,
                images=','.join(images) if images else '',
                variants=json.dumps([]),
                archived=False,
                locked=False,
                on_sale=True,
                reject_reason='',
                currency_type='TRY',
                marketplace_status={'created': True, 'trendyol': 'pending'}
            )
            
            db.session.add(new_product)
            created_products.append({
                'barcode': new_product.barcode,
                'title': new_product.title,
                'size': new_product.size,
                'color': new_product.color
            })
        
        # Veritabanına kaydet
        db.session.commit()
        
        logger.info(f"Yeni ürün grubu oluşturuldu: {product_main_id} - {len(created_products)} varyant")
        
        return jsonify({
            'success': True,
            'message': f'{len(created_products)} adet varyant başarıyla oluşturuldu.',
            'products': created_products
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Varyantlı ürün oluşturma hatası: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Hata: {str(e)}'
        }), 500