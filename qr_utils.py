
from flask import Blueprint, request, jsonify, send_file, current_app
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from datetime import datetime
import qrcode
import os
import io
import shutil

qr_utils_bp = Blueprint('qr_utils', __name__)

@qr_utils_bp.route('/generate_qr', methods=['GET'])
def generate_qr():
    """
    Barkod numarasına göre QR kod üretir ve path döndürür.
    """
    barcode = request.args.get('barcode')
    if not barcode:
        return jsonify({'success': False, 'message': 'Barkod parametresi gerekli'}), 400

    # QR kod klasörü
    qr_dir = os.path.join(current_app.root_path, 'static', 'qr_codes')
    os.makedirs(qr_dir, exist_ok=True)
    
    # QR kod dosya yolu
    qr_filename = f"{barcode}.png"
    qr_path = os.path.join(qr_dir, qr_filename)
    
    # Dosya zaten varsa, mevcut QR kodu kullan
    if os.path.exists(qr_path):
        return jsonify({
            'success': True, 
            'qr_code_path': f"/static/qr_codes/{qr_filename}"
        })
    
    # QR kod üret
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        qr.add_data(barcode)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img.save(qr_path)
        
        return jsonify({
            'success': True, 
            'qr_code_path': f"/static/qr_codes/{qr_filename}"
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@qr_utils_bp.route('/generate_qr_labels_pdf', methods=['POST'])
def generate_qr_labels_pdf():
    """
    Birden fazla barkod alıp, her biri için QR kod üretip A4 sayfasında
    maksimum 21 adet (3 kolon, 7 satır) olacak şekilde PDF etiket oluşturur.
    """
    data = request.get_json()
    items = data.get('items', [])

    if not items:
        return jsonify({'success': False, 'message': 'Ürün listesi boş!'}), 400

    # Quantity kadar barkodları tekrar eden tek bir liste oluştur
    barcodes_to_print = []
    for item in items:
        barcode_val = item.get('barcode')
        quantity_val = int(item.get('quantity', 0))
        if barcode_val and quantity_val > 0:
            barcodes_to_print.extend([barcode_val] * quantity_val)

    if not barcodes_to_print:
        return jsonify({'success': False, 'message': 'Yazdırılacak barkod bulunamadı.'}), 400

    # QR kodların geçici olarak kaydedileceği klasör
    qr_temp_dir = os.path.join(current_app.root_path, 'static', 'qr_temp')
    os.makedirs(qr_temp_dir, exist_ok=True)

    # PDF dosyası için geçici yol
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    pdf_temp_path = os.path.join(qr_temp_dir, f"etiketler_{timestamp}.pdf")

    # PDF Canvas ayarları
    c = canvas.Canvas(pdf_temp_path, pagesize=A4)
    page_width, page_height = A4

    # A4 boyutuna 21 etiket sığdırmak için 3 kolon ve 7 satır düzeni
    cols = 3
    rows = 7

    # Her bir etiket için ayrılan yaklaşık alan
    approx_label_width = page_width / cols
    approx_label_height = page_height / rows

    # Etiket içi boşluklar ve QR/Barkod boyutları
    padding_mm = 2 * mm
    qr_size_mm = 25 * mm  # QR kod boyutu
    barcode_text_height_mm = 5 * mm  # Barkod metni için ayrılan yer

    # Etiket içindeki kullanılabilir alan
    usable_width = approx_label_width - 2 * padding_mm
    usable_height = approx_label_height - 2 * padding_mm

    # QR kod ve metin yerleşimi için QR boyutu hesapla
    qr_draw_size = min(qr_size_mm, usable_width, usable_height - barcode_text_height_mm)

    # Font ayarı
    try:
        font_name = "Helvetica"
        c.setFont(font_name, 8)
    except Exception as e:
        print(f"Font yükleme hatası: {e}. Varsayılan font kullanılıyor.")
        font_name = "Helvetica"
        c.setFont(font_name, 8)

    for i, barcode in enumerate(barcodes_to_print):
        # Etiketin sayfadaki konumu
        col = i % cols
        row = (i // cols) % rows

        # Yeni sayfaya geçiş
        if i > 0 and i % (cols * rows) == 0:
            c.showPage()
            c.setFont(font_name, 8)  # Yeni sayfada font ayarını tekrar yap

        # Etiketin sol alt köşesinin koordinatları
        x_start = col * approx_label_width
        y_start = page_height - (row + 1) * approx_label_height

        # QR kod yerleşimi
        qr_x = x_start + padding_mm + (usable_width - qr_draw_size) / 2
        qr_y = y_start + padding_mm + barcode_text_height_mm

        # Barkod metin yerleşimi
        barcode_text_x = x_start + approx_label_width / 2
        barcode_text_y = y_start + padding_mm

        try:
            # QR kod görseli oluştur
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=2,
            )
            qr.add_data(barcode)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")

            # BytesIO nesnesi oluştur
            img_buffer = io.BytesIO()
            qr_img.save(img_buffer, format='PNG')
            img_buffer.seek(0)

            # PDF'e QR kodunu çiz
            c.drawImage(img_buffer, qr_x, qr_y, width=qr_draw_size, height=qr_draw_size)
            
            # Barkod metnini çiz (ortalı)
            c.drawCentredString(barcode_text_x, barcode_text_y, barcode)
        except Exception as e:
            print(f"QR kod oluşturma hatası ({barcode}): {e}")
            # Hata durumunda bu etiketi atla ve devam et
            continue

    # PDF'i kaydet
    c.save()

    # PDF'i kullanıcıya gönder
    try:
        response = send_file(
            pdf_temp_path,
            as_attachment=True,
            download_name=f"barkod_etiketler_{timestamp}.pdf"
        )
        
        # Temizlik için callback ekle (dosya indirildikten sonra)
        @response.call_on_close
        def cleanup():
            try:
                # Geçici PDF dosyasını sil
                if os.path.exists(pdf_temp_path):
                    os.remove(pdf_temp_path)
                    print(f"Geçici PDF dosyası silindi: {pdf_temp_path}")
            except Exception as e:
                print(f"Geçici dosya temizleme hatası: {e}")
                
        return response
    except Exception as e:
        return jsonify({'success': False, 'message': f'PDF dosyası gönderilemedi: {str(e)}'}), 500

def clean_temp_files():
    """Geçici QR ve PDF dosyalarını temizler"""
    qr_temp_dir = os.path.join(current_app.root_path, 'static', 'qr_temp')
    if os.path.exists(qr_temp_dir):
        try:
            shutil.rmtree(qr_temp_dir)
            os.makedirs(qr_temp_dir, exist_ok=True)
            print("Geçici dosyalar temizlendi.")
        except Exception as e:
            print(f"Geçici dosya temizleme hatası: {e}")
