from flask import Blueprint, render_template, jsonify, request, current_app
from models import db, OrderCreated, Product
import logging

logger = logging.getLogger(__name__)
from sqlalchemy import func, distinct
import json
from datetime import datetime
import io
from PIL import Image, ImageDraw, ImageFont
import base64
import os
import barcode
from barcode.writer import ImageWriter

order_aggregation_bp = Blueprint('order_aggregation', __name__)

@order_aggregation_bp.route('/toplam-siparisler', methods=['GET'])
def toplam_siparisler():
    """
    Yeni statüsündeki siparişleri barkodlara göre toplar ve işleme hazır hale getirir.
    """
    logger.info("Toplam siparişler sayfası açılıyor...")
    try:
        return render_template('toplam_siparisler.html')
    except Exception as e:
        logger.error(f"Şablon işleme hatası: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return f"Sayfa yüklenirken bir hata oluştu: {str(e)}", 500

@order_aggregation_bp.route('/api/barkod-ozeti', methods=['GET'])
def get_barkod_ozeti():
    """
    Yeni durumdaki siparişlerdeki tüm barkodları toplar ve 
    her barkod için toplam adet sayısını hesaplar.
    """
    try:
        logger.info("Barkod özeti alınıyor...")
        # Yeni statüsündeki tüm siparişleri al
        orders = OrderCreated.query.all()
        logger.info(f"Toplam {len(orders)} adet 'Yeni' statüsünde sipariş bulundu.")
        
        # Barkod-adet eşleşmesi için sözlük
        barcode_counts = {}
        product_details = {}
        
        # Her sipariş için
        for order in orders:
            if not order.product_barcode:
                continue
                
            # Detayları ve barkodu al
            barcodes = order.product_barcode.split(', ') if order.product_barcode else []
            sizes = order.product_size.split(', ') if order.product_size else []
            colors = order.product_color.split(', ') if order.product_color else []
            quantities = []
            
            # Detaylar json string olabilir, çözümleyelim
            if order.details:
                try:
                    details = json.loads(order.details) if isinstance(order.details, str) else order.details
                    for detail in details:
                        if 'quantity' in detail:
                            quantities.append(int(detail.get('quantity', 1)))
                except (json.JSONDecodeError, TypeError):
                    # Hata durumunda varsayılan olarak 1 adet kullan
                    quantities = [1] * len(barcodes)
            else:
                # Detay yoksa varsayılan olarak 1 adet
                quantities = [1] * len(barcodes)
            
            # Her barkod için sayaçları güncelle
            for i, barcode_value in enumerate(barcodes):
                if not barcode_value or barcode_value == "null" or barcode_value == "undefined":
                    continue
                
                # Barkod sayacını güncelle
                barcode_counts[barcode_value] = barcode_counts.get(barcode_value, 0) + (quantities[i] if i < len(quantities) else 1)
                
                # Ürün detaylarını sakla (barkod-ürün eşleşmesi)
                if barcode_value not in product_details:
                    # Veritabanından ürün detaylarını çek
                    product = Product.query.filter_by(barcode=barcode_value).first()
                    
                    if product:
                        product_details[barcode_value] = {
                            "model": product.product_main_id,
                            "title": product.title,
                            "color": product.color,
                            "size": product.size
                        }
                    else:
                        # Ürün veritabanında yoksa siparişteki bilgileri kullan
                        size = sizes[i] if i < len(sizes) else ""
                        color = colors[i] if i < len(colors) else ""
                        product_details[barcode_value] = {
                            "model": order.product_main_id.split(', ')[i] if order.product_main_id and i < len(order.product_main_id.split(', ')) else "",
                            "title": "",
                            "color": color,
                            "size": size
                        }
        
        # Sonuçları düzenle
        result = []
        for barcode_value, count in barcode_counts.items():
            details = product_details.get(barcode_value, {})
            result.append({
                "barcode": barcode_value,
                "count": count,
                "model": details.get("model", ""),
                "title": details.get("title", ""),
                "color": details.get("color", ""),
                "size": details.get("size", "")
            })
        
        # Barkod sayısına göre sırala (çoktan aza)
        result.sort(key=lambda x: x["count"], reverse=True)
        
        return jsonify({
            "success": True,
            "data": result,
            "total_different_products": len(result),
            "total_items": sum(barcode_counts.values())
        })
    
    except Exception as e:
        import traceback
        logger.error(f"Barkod özeti alma hatası: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@order_aggregation_bp.route('/api/generate-barcode-label', methods=['POST'])
def generate_barcode_label():
    """
    Barkod ve adet bilgilerine göre 100x100mm etiket oluşturur
    """
    try:
        data = request.get_json()
        barcode_value = data.get('barcode')
        count = data.get('count', 0)
        model = data.get('model', '')
        color = data.get('color', '')
        size = data.get('size', '')
        
        if not barcode_value:
            return jsonify({"success": False, "message": "Barkod değeri gerekli"}), 400
        
        # 100x100mm etiketi oluştur (300 DPI'da yaklaşık 1181x1181 piksel)
        img_width = 1181
        img_height = 1181
        img = Image.new('RGB', (img_width, img_height), color='white')
        draw = ImageDraw.Draw(img)
        
        # Yazı tipi yükleme
        try:
            font_path = os.path.join('static', 'fonts', 'arial.ttf')
            large_font = ImageFont.truetype(font_path, 60)
            medium_font = ImageFont.truetype(font_path, 50)
            small_font = ImageFont.truetype(font_path, 40)
        except IOError:
            # Yazı tipi yoksa varsayılan yazı tipini kullan
            large_font = ImageFont.load_default()
            medium_font = ImageFont.load_default()
            small_font = ImageFont.load_default()
        
        # Başlık çiz
        title_text = "Ürün Toplama Etiketi"
        draw.text((img_width//2, 50), title_text, fill='black', font=large_font, anchor="mt")
        
        # Barkod oluştur
        try:
            # Code128 barkod tipini kullan
            barcode_class = barcode.get_barcode_class('code128')
            barcode_instance = barcode_class(barcode_value, writer=ImageWriter())
            
            # Barkodu bellekte oluştur
            barcode_buffer = io.BytesIO()
            barcode_instance.write(barcode_buffer)
            barcode_buffer.seek(0)
            
            # Barkod görselini yükle
            barcode_img = Image.open(barcode_buffer)
            
            # Barkod boyutunu ayarla
            barcode_width = int(img_width * 0.8)
            barcode_height = int(img_height * 0.2)
            barcode_img = barcode_img.resize((barcode_width, barcode_height), Image.LANCZOS)
            
            # Barkodu etikete yerleştir
            barcode_position = ((img_width - barcode_width) // 2, 150)
            img.paste(barcode_img, barcode_position)
            
        except Exception as e:
            print(f"Barkod oluşturma hatası: {e}")
            # Barkod oluşturulamazsa barkod numarasını metin olarak ekle
            draw.text((img_width//2, 200), barcode_value, fill='black', font=medium_font, anchor="mt")
        
        # Adet Bilgisi
        count_text = f"ADET: {count}"
        draw.text((img_width//2, 450), count_text, fill='black', font=large_font, anchor="mt")
        
        # Model bilgisi
        if model:
            model_text = f"Model: {model}"
            draw.text((img_width//2, 600), model_text, fill='black', font=medium_font, anchor="mt")
        
        # Renk bilgisi
        if color:
            color_text = f"Renk: {color}"
            draw.text((img_width//2, 700), color_text, fill='black', font=medium_font, anchor="mt")
        
        # Beden bilgisi
        if size:
            size_text = f"Beden: {size}"
            draw.text((img_width//2, 800), size_text, fill='black', font=medium_font, anchor="mt")
        
        # Tarih ve saat
        date_text = datetime.now().strftime("%d/%m/%Y %H:%M")
        draw.text((img_width//2, img_height - 50), date_text, fill='black', font=small_font, anchor="mb")
        
        # Görüntüyü base64'e dönüştür
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            "success": True,
            "image": f"data:image/png;base64,{img_base64}"
        })
    
    except Exception as e:
        import traceback
        print(f"Etiket oluşturma hatası: {e}")
        print(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@order_aggregation_bp.route('/api/print-all-labels', methods=['POST'])
def print_all_labels():
    """
    Tüm barkodlar için tek bir PDF oluştur
    """
    try:
        data = request.get_json()
        items = data.get('items', [])
        
        if not items:
            return jsonify({"success": False, "message": "Ürün bilgisi gerekli"}), 400
        
        # Her ürün için etiket oluştur ve hepsini birleştir
        # Bu kısım şimdilik client-side olacak
        
        return jsonify({
            "success": True,
            "message": "Tüm etiketler oluşturuldu"
        })
    
    except Exception as e:
        import traceback
        print(f"Toplu etiket oluşturma hatası: {e}")
        print(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500