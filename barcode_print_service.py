from flask import Blueprint, render_template, request, jsonify, current_app
import os
import json
import io
import qrcode
from PIL import Image, ImageDraw, ImageFont
import barcode
from barcode.writer import ImageWriter
import re

# Blueprint oluştur
barcode_print_bp = Blueprint('barcode_print_bp', __name__, url_prefix='/barcode_print')

# Etiket şablonları - bu sözlüğü genişletebilirsiniz
LABEL_TEMPLATES = {
    'etiket_67x41': {
        'name': 'Standart Etiket (67mm x 41mm)',
        'width_mm': 67,
        'height_mm': 41,
        'page_size': 'custom',
        'margin_top_mm': 0,
        'margin_bottom_mm': 0,
        'margin_left_mm': 0,
        'margin_right_mm': 0
    },
    'etiket_50x25': {
        'name': 'Küçük Etiket (50mm x 25mm)',
        'width_mm': 50,
        'height_mm': 25,
        'page_size': 'custom',
        'margin_top_mm': 0,
        'margin_bottom_mm': 0,
        'margin_left_mm': 0,
        'margin_right_mm': 0
    },
    'etiket_100x50': {
        'name': 'Büyük Etiket (100mm x 50mm)',
        'width_mm': 100,
        'height_mm': 50,
        'page_size': 'custom',
        'margin_top_mm': 0,
        'margin_bottom_mm': 0,
        'margin_left_mm': 0,
        'margin_right_mm': 0
    },
    'a4_3x7': {
        'name': 'A4 Düzeni (3x7)',
        'width_mm': 210,
        'height_mm': 297,
        'page_size': 'A4',
        'margin_top_mm': 15,
        'margin_bottom_mm': 15,
        'margin_left_mm': 8,
        'margin_right_mm': 8,
        'columns': 3,
        'rows': 7,
        'gap_column_mm': 2,
        'gap_row_mm': 1
    },
    'a4_2x5': {
        'name': 'A4 Düzeni (2x5) - Büyük Etiketler',
        'width_mm': 210,
        'height_mm': 297,
        'page_size': 'A4',
        'margin_top_mm': 15,
        'margin_bottom_mm': 15,
        'margin_left_mm': 10,
        'margin_right_mm': 10,
        'columns': 2,
        'rows': 5,
        'gap_column_mm': 5,
        'gap_row_mm': 5
    }
}

# Düzen şablonları - farklı tiplerde etiket görünümleri
LAYOUT_TEMPLATES = {
    'standart': {
        'name': 'Standart (Yan Yana)',
        'description': 'QR kod ve ürün bilgileri yan yana görünür'
    },
    'ustuste': {
        'name': 'Üst Üste',
        'description': 'QR kod üstte, ürün bilgileri altta görünür'
    },
    'sadece_qr': {
        'name': 'Sadece QR Kod',
        'description': 'Yalnızca QR kod ve barkod numarası'
    },
    'buyuk_bilgi': {
        'name': 'Büyük Bilgi',
        'description': 'Daha büyük yazı tipi ile ürün bilgileri'
    }
}

@barcode_print_bp.route('/', methods=['GET'])
def barcode_print_home():
    """Barkod yazdırma ana sayfası"""
    return render_template('barcode_print.html', 
                          templates=LABEL_TEMPLATES,
                          layouts=LAYOUT_TEMPLATES)

@barcode_print_bp.route('/preview', methods=['POST'])
def preview_barcode():
    """Barkod önizleme için JSON döndürür"""
    try:
        data = request.get_json()
        barcode_value = data.get('barcode', '123456789012')
        template_id = data.get('template', 'etiket_67x41')
        layout_id = data.get('layout', 'standart')
        
        # Şablonu al
        template = LABEL_TEMPLATES.get(template_id, LABEL_TEMPLATES['etiket_67x41'])
        
        # QR kod oluştur (geçici olarak)
        qr_code_path = generate_qr_code(barcode_value)
        
        # Ürün bilgileri (örnek)
        product_info = {
            'model': 'Örnek Model',
            'color': 'Siyah',
            'size': '40'
        }
        
        # HTML şablonu oluştur
        html_template = generate_barcode_html(
            barcode_value, 
            product_info, 
            qr_code_path, 
            template, 
            layout_id
        )
        
        return jsonify({
            'success': True,
            'html': html_template,
            'template': template,
            'layout': LAYOUT_TEMPLATES.get(layout_id, LAYOUT_TEMPLATES['standart'])
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@barcode_print_bp.route('/print', methods=['POST'])
def print_barcodes():
    """Barkodları yazdırma sayfasını oluşturur"""
    try:
        data = request.get_json()
        barcodes = data.get('barcodes', [])
        template_id = data.get('template', 'etiket_67x41')
        layout_id = data.get('layout', 'standart')
        
        # Şablonu al
        template = LABEL_TEMPLATES.get(template_id, LABEL_TEMPLATES['etiket_67x41'])
        
        # A4 düzeni için sayfa oluştur
        if template.get('page_size') == 'A4':
            html_content = generate_a4_layout(barcodes, template, layout_id)
        else:
            # Tek etiket için HTML oluştur
            html_content = generate_single_barcode_html(barcodes[0], template, layout_id)
        
        return jsonify({
            'success': True,
            'html': html_content
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def generate_qr_code(data, size=200):
    """QR kod oluşturur ve statik dosya yolunu döndürür"""
    try:
        # QR kod klasörü
        static_folder = current_app.static_folder if current_app.static_folder else 'static'
        qr_dir = os.path.join(static_folder, 'qrcodes')
        os.makedirs(qr_dir, exist_ok=True)
        
        # Güvenli dosya adı oluştur
        filename = re.sub(r'[^a-zA-Z0-9_-]', '_', data)
        filepath = os.path.join(qr_dir, f"{filename}.png")
        
        # Varolan QR kodu kontrol et
        if os.path.exists(filepath):
            return f"/static/qrcodes/{filename}.png"
        
        # QR kod oluştur
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(filepath)
        
        return f"/static/qrcodes/{filename}.png"
    except Exception as e:
        print(f"QR kod oluşturma hatası: {e}")
        return None

def generate_barcode_html(barcode_value, product_info, qr_path, template, layout_id):
    """Barkod HTML şablonu oluşturur"""
    # Şablon değerlerini al
    width_mm = template['width_mm']
    height_mm = template['height_mm']
    
    # Layout seçeneğine göre farklı HTML oluştur
    if layout_id == 'standart':
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
          <title>Barkod: {barcode_value}</title>
          <style>
            @page {{
              size: {width_mm}mm {height_mm}mm;
              margin: 0;
            }}
            body {{
              margin: 0;
              padding: 0;
              width: {width_mm}mm;
              height: {height_mm}mm;
              font-family: Arial, sans-serif;
            }}
            .label {{
              display: flex;
              width: 100%;
              height: 100%;
            }}
            .left {{
              width: 50%;
              display: flex;
              flex-direction: column;
              align-items: center;
              justify-content: center;
              padding: 2mm;
              box-sizing: border-box;
            }}
            .right {{
              width: 50%;
              display: flex;
              flex-direction: column;
              justify-content: center;
              text-align: center;
              padding: 2mm;
              box-sizing: border-box;
            }}
            img {{
              max-width: {width_mm * 0.3}mm;
              max-height: {height_mm * 0.5}mm;
              margin-bottom: 2mm;
            }}
            .barcode-text {{
              font-size: {9.5 * width_mm / 67}pt;
              text-align: center;
              font-weight: bold;
              word-break: break-all;
            }}
            .info {{
              margin-bottom: 3mm;
              font-size: {10 * width_mm / 67}pt;
              font-weight: 600;
            }}
          </style>
        </head>
        <body>
          <div class="label">
            <div class="left">
              <img src="{qr_path}" alt="QR Kod">
              <div class="barcode-text">{barcode_value}</div>
            </div>
            <div class="right">
              <div class="info">Model: {product_info.get('model', '')}</div>
              <div class="info">Renk: {product_info.get('color', '')}</div>
              <div class="info">Beden: {product_info.get('size', '')}</div>
            </div>
          </div>
        </body>
        </html>
        """
    elif layout_id == 'ustuste':
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
          <title>Barkod: {barcode_value}</title>
          <style>
            @page {{
              size: {width_mm}mm {height_mm}mm;
              margin: 0;
            }}
            body {{
              margin: 0;
              padding: 0;
              width: {width_mm}mm;
              height: {height_mm}mm;
              font-family: Arial, sans-serif;
            }}
            .label {{
              display: flex;
              flex-direction: column;
              align-items: center;
              width: 100%;
              height: 100%;
              padding: 2mm;
              box-sizing: border-box;
            }}
            .top {{
              display: flex;
              flex-direction: column;
              align-items: center;
              justify-content: center;
              margin-bottom: 2mm;
            }}
            .bottom {{
              display: flex;
              flex-direction: column;
              justify-content: center;
              text-align: center;
            }}
            img {{
              max-width: {width_mm * 0.4}mm;
              max-height: {height_mm * 0.4}mm;
              margin-bottom: 1mm;
            }}
            .barcode-text {{
              font-size: {9 * width_mm / 67}pt;
              text-align: center;
              font-weight: bold;
              word-break: break-all;
            }}
            .info {{
              margin-bottom: 1mm;
              font-size: {9 * width_mm / 67}pt;
              font-weight: 600;
            }}
          </style>
        </head>
        <body>
          <div class="label">
            <div class="top">
              <img src="{qr_path}" alt="QR Kod">
              <div class="barcode-text">{barcode_value}</div>
            </div>
            <div class="bottom">
              <div class="info">Model: {product_info.get('model', '')}</div>
              <div class="info">Renk: {product_info.get('color', '')}</div>
              <div class="info">Beden: {product_info.get('size', '')}</div>
            </div>
          </div>
        </body>
        </html>
        """
    elif layout_id == 'sadece_qr':
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
          <title>Barkod: {barcode_value}</title>
          <style>
            @page {{
              size: {width_mm}mm {height_mm}mm;
              margin: 0;
            }}
            body {{
              margin: 0;
              padding: 0;
              width: {width_mm}mm;
              height: {height_mm}mm;
              font-family: Arial, sans-serif;
              display: flex;
              flex-direction: column;
              align-items: center;
              justify-content: center;
            }}
            img {{
              max-width: {width_mm * 0.6}mm;
              max-height: {height_mm * 0.6}mm;
              margin-bottom: 2mm;
            }}
            .barcode-text {{
              font-size: {10 * width_mm / 67}pt;
              text-align: center;
              font-weight: bold;
              word-break: break-all;
            }}
          </style>
        </head>
        <body>
          <img src="{qr_path}" alt="QR Kod">
          <div class="barcode-text">{barcode_value}</div>
        </body>
        </html>
        """
    elif layout_id == 'buyuk_bilgi':
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
          <title>Barkod: {barcode_value}</title>
          <style>
            @page {{
              size: {width_mm}mm {height_mm}mm;
              margin: 0;
            }}
            body {{
              margin: 0;
              padding: 0;
              width: {width_mm}mm;
              height: {height_mm}mm;
              font-family: Arial, sans-serif;
            }}
            .label {{
              display: flex;
              width: 100%;
              height: 100%;
            }}
            .left {{
              width: 40%;
              display: flex;
              flex-direction: column;
              align-items: center;
              justify-content: center;
              padding: 2mm;
              box-sizing: border-box;
            }}
            .right {{
              width: 60%;
              display: flex;
              flex-direction: column;
              justify-content: center;
              text-align: center;
              padding: 2mm;
              box-sizing: border-box;
            }}
            img {{
              max-width: {width_mm * 0.25}mm;
              max-height: {height_mm * 0.4}mm;
              margin-bottom: 1mm;
            }}
            .barcode-text {{
              font-size: {8 * width_mm / 67}pt;
              text-align: center;
              font-weight: bold;
              word-break: break-all;
            }}
            .info {{
              margin-bottom: 2mm;
              font-size: {12 * width_mm / 67}pt;
              font-weight: bold;
            }}
          </style>
        </head>
        <body>
          <div class="label">
            <div class="left">
              <img src="{qr_path}" alt="QR Kod">
              <div class="barcode-text">{barcode_value}</div>
            </div>
            <div class="right">
              <div class="info">Model: {product_info.get('model', '')}</div>
              <div class="info">Renk: {product_info.get('color', '')}</div>
              <div class="info">Beden: {product_info.get('size', '')}</div>
            </div>
          </div>
        </body>
        </html>
        """
    # Varsayılan düzen
    return generate_barcode_html(barcode_value, product_info, qr_path, template, 'standart')

def generate_single_barcode_html(barcode_item, template, layout_id):
    """Tek bir barkod için yazdırma HTML'i oluşturur"""
    barcode_value = barcode_item.get('barcode', '')
    product_info = {
        'model': barcode_item.get('model', ''),
        'color': barcode_item.get('color', ''),
        'size': barcode_item.get('size', '')
    }
    qr_path = barcode_item.get('qr_path', '')
    
    html = generate_barcode_html(barcode_value, product_info, qr_path, template, layout_id)
    
    # Otomatik yazdırma ve pencere kapatma için script ekle
    script = """
    <script>
      window.onload = function() {
        setTimeout(function() {
          window.print();
          setTimeout(function() {
            window.close();
          }, 500);
        }, 300);
      };
    </script>
    """
    
    # Script'i body kapatma tag'inden önce ekle
    html = html.replace('</body>', f'{script}</body>')
    
    return html

def generate_a4_layout(barcodes, template, layout_id):
    """A4 veya özel sayfa boyutunda çoklu barkod düzeni oluşturur"""
    columns = template.get('columns', 3)
    rows = template.get('rows', 7)
    width_mm = template.get('width_mm', 210)
    height_mm = template.get('height_mm', 297)
    margin_top_mm = template.get('margin_top_mm', 15)
    margin_bottom_mm = template.get('margin_bottom_mm', 15)
    margin_left_mm = template.get('margin_left_mm', 8)
    margin_right_mm = template.get('margin_right_mm', 8)
    gap_column_mm = template.get('gap_column_mm', 2)
    gap_row_mm = template.get('gap_row_mm', 1)
    
    # Eğer şablonda belirtilmişse etiket boyutlarını kullan
    use_fixed_label_size = 'label_width_mm' in template and 'label_height_mm' in template
    label_width_mm = template.get('label_width_mm', None)
    label_height_mm = template.get('label_height_mm', None)
    
    totalBarcodes = len(barcodes)
    barcodesPerPage = columns * rows
    totalPages = (totalBarcodes + barcodesPerPage - 1) // barcodesPerPage  # Yukarı yuvarlama
    
    # Sayfa boyutu (A4 veya özel)
    page_size_css = "A4"
    if template.get('page_size') == 'custom_page':
        page_size_css = f"{width_mm}mm {height_mm}mm"
    
    # Etiket genişliği ve yüksekliği hesapla
    if use_fixed_label_size and label_width_mm and label_height_mm:
        # Özel etiket boyutları kullan
        label_width = label_width_mm
        label_height = label_height_mm
        
        # Grid yerine absolute positioning kullan
        use_grid = False
    else:
        # Hesaplanan boyutları kullan
        label_width = f"calc((100% - {gap_column_mm * (columns-1)}mm) / {columns})"
        label_height = f"calc((100% - {gap_row_mm * (rows-1)}mm) / {rows})"
        
        # Grid düzen kullan
        use_grid = True
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <title>Çoklu Etiket Düzeni</title>
      <style>
        @page {{
          size: {page_size_css};
          margin: 0;
        }}
        body {{
          margin: 0;
          padding: 0;
          background: white;
          font-family: Arial, sans-serif;
        }}
        .page {{
          width: {width_mm}mm;
          height: {height_mm}mm;
          box-sizing: border-box;
          padding: {margin_top_mm}mm {margin_right_mm}mm {margin_bottom_mm}mm {margin_left_mm}mm;
          position: relative;
          """
    
    if use_grid:
        html += f"""
          display: grid;
          grid-template-columns: repeat({columns}, {label_width});
          grid-template-rows: repeat({rows}, {label_height});
          column-gap: {gap_column_mm}mm;
          row-gap: {gap_row_mm}mm;
        """
    else:
        html += """
          /* Absolute positioning for fixed label sizes */
        """
    
    html += f"""
        }}
        .page:not(.last-page) {{
          page-break-after: always;
        }}
        .page.last-page {{
          page-break-after: auto;
        }}
    """
    
    # Etiket stilini ekle (layout_id'ye göre)
    if layout_id == 'standart':
        html += """
        .label {
          display: flex;
          border: none;
          box-sizing: border-box;
        }
        .left {
          width: 50%;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 1mm;
          box-sizing: border-box;
        }
        .right {
          width: 50%;
          display: flex;
          flex-direction: column;
          justify-content: center;
          text-align: center;
          padding: 1mm;
          box-sizing: border-box;
        }
        img {
          max-width: 18mm;
          max-height: 18mm;
          margin-bottom: 1mm;
        }
        .barcode-text {
          font-size: 8pt;
          text-align: center;
          font-weight: bold;
          word-break: break-all;
          line-height: 1.2;
        }
        .info {
          margin-bottom: 1.5mm;
          font-size: 8.5pt;
          font-weight: 600;
          line-height: 1.2;
        }
        """
    elif layout_id == 'ustuste':
        html += """
        .label {
          display: flex;
          flex-direction: column;
          align-items: center;
          border: none;
          box-sizing: border-box;
          padding: 1mm;
        }
        .top {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          margin-bottom: 1mm;
        }
        .bottom {
          display: flex;
          flex-direction: column;
          justify-content: center;
          text-align: center;
        }
        img {
          max-width: 16mm;
          max-height: 16mm;
          margin-bottom: 1mm;
        }
        .barcode-text {
          font-size: 7pt;
          text-align: center;
          font-weight: bold;
          word-break: break-all;
          line-height: 1.1;
        }
        .info {
          margin-bottom: 0.5mm;
          font-size: 7pt;
          font-weight: 600;
          line-height: 1.1;
        }
        """
    elif layout_id == 'sadece_qr':
        html += """
        .label {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          border: none;
          box-sizing: border-box;
          padding: 1mm;
        }
        img {
          max-width: 20mm;
          max-height: 20mm;
          margin-bottom: 1mm;
        }
        .barcode-text {
          font-size: 8pt;
          text-align: center;
          font-weight: bold;
          word-break: break-all;
          line-height: 1.1;
        }
        """
    elif layout_id == 'buyuk_bilgi':
        html += """
        .label {
          display: flex;
          border: none;
          box-sizing: border-box;
        }
        .left {
          width: 40%;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 1mm;
          box-sizing: border-box;
        }
        .right {
          width: 60%;
          display: flex;
          flex-direction: column;
          justify-content: center;
          text-align: center;
          padding: 1mm;
          box-sizing: border-box;
        }
        img {
          max-width: 16mm;
          max-height: 16mm;
          margin-bottom: 1mm;
        }
        .barcode-text {
          font-size: 7pt;
          text-align: center;
          font-weight: bold;
          word-break: break-all;
          line-height: 1.1;
        }
        .info {
          margin-bottom: 1mm;
          font-size: 9pt;
          font-weight: bold;
          line-height: 1.1;
        }
        """
    
    # Stili tamamla
    html += """
      </style>
    </head>
    <body>
    """
    
    # Sayfaları oluştur
    for page in range(totalPages):
        pageClass = "page last-page" if page == totalPages - 1 else "page"
        html += f'<div class="{pageClass}">'
        
        for i in range(barcodesPerPage):
            index = page * barcodesPerPage + i
            if index < totalBarcodes:
                barcode_item = barcodes[index]
                
                if layout_id == 'standart':
                    html += f"""
                    <div class="label">
                      <div class="left">
                        <img src="{barcode_item.get('qr_path', '')}" alt="QR Kod">
                        <div class="barcode-text">{barcode_item.get('barcode', '')}</div>
                      </div>
                      <div class="right">
                        <div class="info">Model: {barcode_item.get('model', '')}</div>
                        <div class="info">Renk: {barcode_item.get('color', '')}</div>
                        <div class="info">Beden: {barcode_item.get('size', '')}</div>
                      </div>
                    </div>
                    """
                elif layout_id == 'ustuste':
                    html += f"""
                    <div class="label">
                      <div class="top">
                        <img src="{barcode_item.get('qr_path', '')}" alt="QR Kod">
                        <div class="barcode-text">{barcode_item.get('barcode', '')}</div>
                      </div>
                      <div class="bottom">
                        <div class="info">Model: {barcode_item.get('model', '')}</div>
                        <div class="info">Renk: {barcode_item.get('color', '')}</div>
                        <div class="info">Beden: {barcode_item.get('size', '')}</div>
                      </div>
                    </div>
                    """
                elif layout_id == 'sadece_qr':
                    html += f"""
                    <div class="label">
                      <img src="{barcode_item.get('qr_path', '')}" alt="QR Kod">
                      <div class="barcode-text">{barcode_item.get('barcode', '')}</div>
                    </div>
                    """
                elif layout_id == 'buyuk_bilgi':
                    html += f"""
                    <div class="label">
                      <div class="left">
                        <img src="{barcode_item.get('qr_path', '')}" alt="QR Kod">
                        <div class="barcode-text">{barcode_item.get('barcode', '')}</div>
                      </div>
                      <div class="right">
                        <div class="info">Model: {barcode_item.get('model', '')}</div>
                        <div class="info">Renk: {barcode_item.get('color', '')}</div>
                        <div class="info">Beden: {barcode_item.get('size', '')}</div>
                      </div>
                    </div>
                    """
            else:
                html += '<div class="label"></div>'  # Boş etiket
        
        html += '</div>'  # Sayfa sonu
    
    # Otomatik yazdırma script'i
    html += """
      <script>
        window.onload = function() {
          setTimeout(function() {
            window.print();
          }, 500);
        };
      </script>
    </body>
    </html>
    """
    
    return html

@barcode_print_bp.route('/save_settings', methods=['POST'])
def save_settings():
    """Kullanıcı ayarlarını kaydeder"""
    try:
        data = request.get_json()
        settings = {
            'template': data.get('template', 'etiket_67x41'),
            'layout': data.get('layout', 'standart')
        }
        
        # settings.json dosyasına kaydet
        settings_path = os.path.join(current_app.instance_path, 'barcode_settings.json')
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        
        with open(settings_path, 'w') as f:
            json.dump(settings, f)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@barcode_print_bp.route('/get_settings', methods=['GET'])
def get_settings():
    """Kullanıcı ayarlarını döndürür"""
    try:
        settings_path = os.path.join(current_app.instance_path, 'barcode_settings.json')
        
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                settings = json.load(f)
        else:
            settings = {
                'template': 'etiket_67x41',
                'layout': 'standart'
            }
        
        return jsonify({'success': True, 'settings': settings})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@barcode_print_bp.route('/product/<barcode>', methods=['GET'])
def get_product_barcode(barcode):
    """Belirli bir ürün barkodunu yazdırma sayfasına yönlendirir"""
    from models import Product
    
    product = Product.query.filter_by(barcode=barcode).first()
    
    if not product:
        return "Ürün bulunamadı", 404
    
    return render_template(
        'barcode_print_product.html',
        barcode=barcode,
        product=product,
        templates=LABEL_TEMPLATES,
        layouts=LAYOUT_TEMPLATES
    )

# Özel etiket boyutu oluşturma
@barcode_print_bp.route('/custom_template', methods=['POST'])
def create_custom_template():
    """Özel etiket şablonu oluşturur"""
    try:
        data = request.get_json()
        template_id = data.get('id', f'custom_{len(LABEL_TEMPLATES) + 1}')
        name = data.get('name', 'Özel Şablon')
        width_mm = float(data.get('width_mm', 67))
        height_mm = float(data.get('height_mm', 41))
        page_size = data.get('page_size', 'custom')
        
        # Yeni şablon özellikleri
        template_data = {
            'name': name,
            'width_mm': width_mm,
            'height_mm': height_mm,
            'page_size': page_size,
            'margin_top_mm': float(data.get('margin_top_mm', 0)),
            'margin_bottom_mm': float(data.get('margin_bottom_mm', 0)),
            'margin_left_mm': float(data.get('margin_left_mm', 0)),
            'margin_right_mm': float(data.get('margin_right_mm', 0))
        }
        
        # Çoklu etiket (A4) için özel alanlar
        if page_size in ['A4', 'custom_page']:
            template_data.update({
                'columns': int(data.get('columns', 3)),
                'rows': int(data.get('rows', 7)),
                'gap_column_mm': float(data.get('gap_column_mm', 2)),
                'gap_row_mm': float(data.get('gap_row_mm', 2))
            })
            
            # Etiket boyutları belirtilmişse ekle
            if 'label_width_mm' in data and 'label_height_mm' in data:
                template_data.update({
                    'label_width_mm': float(data.get('label_width_mm')),
                    'label_height_mm': float(data.get('label_height_mm'))
                })
        
        # Yeni şablonu ekle
        LABEL_TEMPLATES[template_id] = template_data
        
        # Özel şablonları kaydet
        save_custom_templates()
        
        return jsonify({'success': True, 'template_id': template_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def save_custom_templates():
    """Özel şablonları dosyaya kaydeder"""
    try:
        custom_templates = {k: v for k, v in LABEL_TEMPLATES.items() if k.startswith('custom_')}
        
        if custom_templates:
            templates_path = os.path.join(current_app.instance_path, 'custom_templates.json')
            os.makedirs(os.path.dirname(templates_path), exist_ok=True)
            
            with open(templates_path, 'w') as f:
                json.dump(custom_templates, f)
    except Exception as e:
        print(f"Özel şablonları kaydetme hatası: {e}")

def load_custom_templates():
    """Özel şablonları dosyadan yükler"""
    try:
        templates_path = os.path.join(current_app.instance_path, 'custom_templates.json')
        
        if os.path.exists(templates_path):
            with open(templates_path, 'r') as f:
                custom_templates = json.load(f)
            
            # Şablonları güncelle
            LABEL_TEMPLATES.update(custom_templates)
    except Exception as e:
        print(f"Özel şablonları yükleme hatası: {e}")

# Uygulama başlangıcında özel şablonları yükle
load_custom_templates()