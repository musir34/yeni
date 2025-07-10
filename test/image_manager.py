from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
import os
from werkzeug.utils import secure_filename
from PIL import Image
import uuid
from models import db
import logging

image_manager_bp = Blueprint('image_manager', __name__)
logger = logging.getLogger(__name__)

# İzin verilen dosya formatları
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
UPLOAD_FOLDER = 'static/images'
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

def allowed_file(filename):
    """Dosya formatının izin verilen formatlarda olup olmadığını kontrol et"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def optimize_image(image_path, max_width=800, max_height=600, quality=85):
    """Görsel optimizasyonu - boyut ve kalite ayarı"""
    try:
        with Image.open(image_path) as img:
            # RGBA'yı RGB'ye çevir (PNG için)
            if img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            
            # Boyut optimizasyonu
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            # Dosyayı JPEG olarak kaydet (daha küçük dosya boyutu)
            base_name = os.path.splitext(image_path)[0]
            optimized_path = f"{base_name}.jpg"
            
            img.save(optimized_path, 'JPEG', quality=quality, optimize=True)
            
            # Orijinal dosyayı sil (eğer farklıysa)
            if image_path != optimized_path and os.path.exists(image_path):
                os.remove(image_path)
            
            return optimized_path
    except Exception as e:
        logger.error(f"Görsel optimizasyon hatası: {e}")
        return image_path

@image_manager_bp.route('/image_manager')
def image_manager():
    """Görsel yönetim ana sayfası"""
    # Mevcut görselleri listele
    images_folder = os.path.join('static', 'images')
    existing_images = []
    
    if os.path.exists(images_folder):
        for filename in os.listdir(images_folder):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                # Dosya adından model ve renk bilgisini çıkarmaya çalış
                name_parts = filename.rsplit('.', 1)[0].split('_')
                if len(name_parts) >= 2:
                    model = '_'.join(name_parts[:-1])
                    color = name_parts[-1]
                else:
                    model = filename.rsplit('.', 1)[0]
                    color = 'Bilinmiyor'
                
                file_size = os.path.getsize(os.path.join(images_folder, filename))
                existing_images.append({
                    'filename': filename,
                    'model': model,
                    'color': color,
                    'path': f'images/{filename}',
                    'size': round(file_size / 1024, 1)  # KB cinsinden
                })
    
    # Model ve renge göre sırala
    existing_images.sort(key=lambda x: (x['model'], x['color']))
    
    return render_template('image_manager.html', existing_images=existing_images)

@image_manager_bp.route('/api/upload_product_image', methods=['POST'])
def upload_product_image():
    """Ürün görseli yükleme API'si"""
    try:
        # Form verilerini al
        model_code = request.form.get('model_code', '').strip()
        color = request.form.get('color', '').strip()
        
        if not model_code or not color:
            return jsonify({'success': False, 'message': 'Model kodu ve renk bilgisi gereklidir'})
        
        # Dosya kontrolü
        if 'image_file' not in request.files:
            return jsonify({'success': False, 'message': 'Görsel dosyası seçilmedi'})
        
        file = request.files['image_file']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'Dosya seçilmedi'})
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'message': 'Desteklenmeyen dosya formatı. PNG, JPG, JPEG, GIF, WEBP desteklenir.'})
        
        # Güvenli dosya adı oluştur
        model_clean = secure_filename(model_code)
        color_clean = secure_filename(color.lower())
        filename = f"{model_clean}_{color_clean}.jpg"
        
        # Upload klasörünü oluştur
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        
        # Dosya yolunu oluştur
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        
        # Eğer aynı isimde dosya varsa eskisini yedekle
        if os.path.exists(file_path):
            backup_name = f"{model_clean}_{color_clean}_backup_{uuid.uuid4().hex[:8]}.jpg"
            backup_path = os.path.join(UPLOAD_FOLDER, backup_name)
            os.rename(file_path, backup_path)
            logger.info(f"Eski dosya yedeklendi: {backup_name}")
        
        # Dosyayı geçici olarak kaydet
        temp_path = os.path.join(UPLOAD_FOLDER, f"temp_{uuid.uuid4().hex}.tmp")
        file.save(temp_path)
        
        # Dosya boyutu kontrolü
        file_size = os.path.getsize(temp_path)
        if file_size > MAX_FILE_SIZE:
            os.remove(temp_path)
            return jsonify({'success': False, 'message': f'Dosya boyutu çok büyük. Maksimum {MAX_FILE_SIZE // (1024*1024)}MB olmalıdır.'})
        
        # Görseli optimize et ve kaydet
        try:
            optimized_path = optimize_image(temp_path)
            
            # Optimize edilmiş görseli hedef konuma taşı
            if optimized_path != file_path:
                os.rename(optimized_path, file_path)
            
            # Geçici dosyayı temizle
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
        except Exception as e:
            # Optimizasyon başarısızsa orijinal dosyayı kullan
            logger.warning(f"Optimizasyon başarısız, orijinal dosya kullanılıyor: {e}")
            os.rename(temp_path, file_path)
        
        # Başarı mesajı
        final_size = os.path.getsize(file_path)
        return jsonify({
            'success': True, 
            'message': f'Görsel başarıyla yüklendi: {filename}',
            'filename': filename,
            'size': round(final_size / 1024, 1),
            'path': f'images/{filename}'
        })
        
    except Exception as e:
        logger.error(f"Görsel yükleme hatası: {e}")
        return jsonify({'success': False, 'message': f'Yükleme sırasında hata oluştu: {str(e)}'})

@image_manager_bp.route('/api/delete_product_image', methods=['POST'])
def delete_product_image():
    """Ürün görseli silme API'si"""
    try:
        filename = request.json.get('filename')
        if not filename:
            return jsonify({'success': False, 'message': 'Dosya adı gereklidir'})
        
        # Güvenlik kontrolü - sadece images klasöründeki dosyalar
        safe_filename = secure_filename(filename)
        file_path = os.path.join(UPLOAD_FOLDER, safe_filename)
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'Dosya bulunamadı'})
        
        # Dosyayı sil
        os.remove(file_path)
        
        return jsonify({'success': True, 'message': f'Görsel silindi: {filename}'})
        
    except Exception as e:
        logger.error(f"Görsel silme hatası: {e}")
        return jsonify({'success': False, 'message': f'Silme sırasında hata oluştu: {str(e)}'})

@image_manager_bp.route('/api/rename_product_image', methods=['POST'])
def rename_product_image():
    """Ürün görseli yeniden adlandırma API'si"""
    try:
        data = request.json
        old_filename = data.get('old_filename')
        new_model = data.get('new_model', '').strip()
        new_color = data.get('new_color', '').strip()
        
        if not all([old_filename, new_model, new_color]):
            return jsonify({'success': False, 'message': 'Tüm alanlar gereklidir'})
        
        # Güvenli dosya adları
        old_safe = secure_filename(old_filename)
        new_model_clean = secure_filename(new_model)
        new_color_clean = secure_filename(new_color.lower())
        
        old_path = os.path.join(UPLOAD_FOLDER, old_safe)
        
        if not os.path.exists(old_path):
            return jsonify({'success': False, 'message': 'Eski dosya bulunamadı'})
        
        # Dosya uzantısını koru
        file_ext = old_filename.rsplit('.', 1)[1] if '.' in old_filename else 'jpg'
        new_filename = f"{new_model_clean}_{new_color_clean}.{file_ext}"
        new_path = os.path.join(UPLOAD_FOLDER, new_filename)
        
        # Hedef dosya zaten varsa hata ver
        if os.path.exists(new_path) and old_path != new_path:
            return jsonify({'success': False, 'message': 'Bu isimde bir dosya zaten var'})
        
        # Dosyayı yeniden adlandır
        os.rename(old_path, new_path)
        
        return jsonify({
            'success': True, 
            'message': f'Dosya yeniden adlandırıldı: {new_filename}',
            'new_filename': new_filename,
            'new_path': f'images/{new_filename}'
        })
        
    except Exception as e:
        logger.error(f"Görsel yeniden adlandırma hatası: {e}")
        return jsonify({'success': False, 'message': f'Yeniden adlandırma sırasında hata oluştu: {str(e)}'})

@image_manager_bp.route('/api/get_product_image', methods=['GET'])
def get_product_image():
    """Model kodu ve renge göre ürün görseli getir"""
    model_code = request.args.get('model_code', '').strip()
    color = request.args.get('color', '').strip()
    
    if not model_code or not color:
        return jsonify({'success': False, 'message': 'Model kodu ve renk gereklidir'})
    
    # Olası dosya adlarını dene
    possible_names = [
        f"{model_code}_{color.lower()}.jpg",
        f"{model_code}_{color.lower()}.png", 
        f"{model_code}_{color.lower()}.jpeg",
        f"{model_code}_{color}.jpg",
        f"{model_code}_{color}.png"
    ]
    
    for name in possible_names:
        file_path = os.path.join(UPLOAD_FOLDER, name)
        if os.path.exists(file_path):
            return jsonify({
                'success': True,
                'found': True,
                'filename': name,
                'path': f'images/{name}',
                'size': round(os.path.getsize(file_path) / 1024, 1)
            })
    
    return jsonify({
        'success': True,
        'found': False,
        'message': 'Bu model ve renk için görsel bulunamadı'
    })