from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from datetime import datetime
import qrcode
import os
import io
from flask import Blueprint, request, jsonify, send_file # send_file eklendi

# Blueprint tanımı (eğer qr_utils.py ayrı bir blueprint olarak kullanılmıyorsa bu satır kaldırılmalı/düzenlenmeli)
# from app import app # Eğer app objesine erişim gerekiyorsa
qr_utils_bp = Blueprint('qr_utils', __name__)

@qr_utils_bp.route('/generate_qr_labels_pdf', methods=['POST'])
def generate_qr_labels_pdf():
    """
    Birden fazla barkod alıp, her biri için QR kod üretip A4 sayfasında
    maksimum 21 adet (3 kolon, 7 satır) olacak şekilde PDF etiket oluşturur.
    """
    data = request.get_json()
    # Beklenen data formatı: [{'barcode': 'BARKOD1', 'quantity': 2}, {'barcode': 'BARKOD2', 'quantity': 1}]
    # Quantity kadar tekrar eden barkod listesi oluşturulmalı
    items = data.get('items', [])

    if not items:
        return jsonify({'success': False, 'message': 'Ürün listesi boş!'}), 400

    # Quantity kadar barkodları tekrar eden tek bir liste oluştur
    barcodes_to_print = []
    for item in items:
        barcode_val = item.get('barcode')
        quantity_val = int(item.get('quantity', 0)) # Miktarı int yap
        if barcode_val and quantity_val > 0:
            barcodes_to_print.extend([barcode_val] * quantity_val)

    if not barcodes_to_print:
         return jsonify({'success': False, 'message': 'Yazdırılacak barkod bulunamadı.'}), 400

    # QR kodların geçici olarak kaydedileceği klasör (PDF oluşturulduktan sonra silinebilir)
    qr_temp_dir = os.path.join('static', 'qr_temp')
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
    qr_size_mm = 25 * mm # QR kod boyutu
    barcode_text_height_mm = 5 * mm # Barkod metni için ayrılan yer

    # Etiket içindeki kullanılabilir alan
    usable_width = approx_label_width - 2 * padding_mm
    usable_height = approx_label_height - 2 * padding_mm

    # QR kod ve metin yerleşimi için başlangıç koordinatları
    # QR kodu ve metni etiket alanının içinde ortalamak için hesaplamalar
    qr_draw_size = min(qr_size_mm, usable_width, usable_height - barcode_text_height_mm) # Kullanılabilir alandan küçük olsun

    for i, barcode in enumerate(barcodes_to_print):
        # Etiketin sayfadaki konumu
        col = i % cols
        row = (i // cols) % rows

        # Yeni sayfaya geçiş
        if i > 0 and i % (cols * rows) == 0:
            c.showPage()

        # Etiketin sol alt köşesinin koordinatları
        # x = sol_kenar_boslugu + kolon_indexi * etiket_genisligi
        # y = sayfa_yuksekligi - ust_kenar_boslugu - (satir_indexi + 1) * etiket_yuksekligi

        # Boşlukları otomatik hesaplamak yerine 0,0 noktasından başlayıp etiket alanlarını kullanıyoruz
        x_start = col * approx_label_width
        y_start = page_height - (row + 1) * approx_label_height # Y ekseni tersten artar

        # Etiket içindeki elemanların konumu (etiket alanının sol alt köşesine göre)
        # QR kodunun sol alt köşesi: etiket alanı_x + sol_padding + (kullanılabilir alan - QR boyutu) / 2
        qr_x = x_start + padding_mm + (usable_width - qr_draw_size) / 2
        qr_y = y_start + padding_mm + barcode_text_height_mm # Barkod metninin üstüne

        # Barkod metninin konumu (etiket alanının ortasına hizalanmış)
        barcode_text_x = x_start + approx_label_width / 2
        barcode_text_y = y_start + padding_mm # En altta

        try:
            # QR kod görseli oluştur ve geçici dosyaya kaydet
            # QR kodunu direkt ReportLab'e drawImage ile çizmek daha performanslı olabilir, dosya kaydı yerine BytesIO kullanmak gibi.
            # Şimdilik dosya kaydıyla devam edelim.
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10, # Piksel boyutu
                border=2,    # Kenarlık
            )
            qr.add_data(barcode)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")

            # QR görselini geçici olarak kaydet
            qr_temp_filename = os.path.join(qr_temp_dir, f"{barcode}_{i}.png") # Aynı barkoddan birden çok olabilir, index ekle
            qr_img.save(qr_temp_filename)

            # PDF'e QR kodunu çiz
            c.drawImage(qr_temp_filename, qr_x, qr_y, width=qr_draw_size, height=qr_draw_size)

            # PDF'e barkod metnini çiz
            c.setFont("Helvetica", 8) # Font boyutu ayarlanabilir
            c.drawCentredString(barcode_text_x, barcode_text_y, barcode)

            # Geçici QR dosyasını sil (isteğe bağlı, işlemi bitirdikten sonra topluca da silinebilir)
            # os.remove(qr_temp_filename)

        except Exception as e:
            print(f"Barkod {barcode} için QR kod oluşturma veya çizme hatası: {e}")
            # Hata durumunda boş bir alan veya hata mesajı çizilebilir
            c.setFont("Helvetica", 8)
            c.setFillColorRGB(1,0,0) # Kırmızı renk
            c.drawCentredString(barcode_text_x, barcode_text_y + qr_draw_size/2, "QR HATA")
            c.setFillColorRGB(0,0,0) # Rengi siyaha geri çevir


    # PDF'i kaydet
    c.save()

    # Geçici QR dosyalarını temizle (PDF oluşturulduktan sonra)
    try:
        for f in os.listdir(qr_temp_dir):
            os.remove(os.path.join(qr_temp_dir, f))
        # os.rmdir(qr_temp_dir) # Klasörü de silebilirsiniz eğer boşsa
    except Exception as e:
        print(f"Geçici QR dosyaları silinirken hata: {e}")


    # PDF dosyasını yanıt olarak gönder
    # as_attachment=True ile dosya indirme olarak sunulur
    return send_file(pdf_temp_path, as_attachment=True, mimetype='application/pdf', download_name=f"etiketler_{timestamp}.pdf")

# Blueprint'i Flask uygulamasına kaydettiğinizden emin olun.
# Örnek: app.register_blueprint(qr_utils_bp)
# Ayrıca, bu fonksiyonu çağıracak bir frontend route veya API endpoint'i oluşturmanız gerekecektir.
# Bu endpoint'e {'items': [{'barcode': 'BARKOD1', 'quantity': 2}, ...]} formatında POST isteği göndermelisiniz.