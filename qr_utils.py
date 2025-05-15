from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from datetime import datetime

@qr_utils_bp.route('/generate_qr_labels_pdf', methods=['POST'])
def generate_qr_labels_pdf():
    """
    Birden fazla barkod alıp, her biri için QR kod üretip A4 sayfasında 60x40 mm ölçülerde PDF etiket oluşturur.
    """
    data = request.get_json()
    barcodes = data.get('barcodes', [])

    if not barcodes:
        return jsonify({'success': False, 'message': 'Barkod listesi boş!'})

    qr_dir = os.path.join('static', 'qr_codes')
    os.makedirs(qr_dir, exist_ok=True)

    # PDF dosyası için yol
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    pdf_path = os.path.join(qr_dir, f"etiketler_{timestamp}.pdf")

    c = canvas.Canvas(pdf_path, pagesize=A4)

    label_width = 60 * mm
    label_height = 40 * mm
    page_width, page_height = A4

    cols = int(page_width // label_width)
    rows = int(page_height // label_height)

    x_margin = (page_width - (cols * label_width)) / 2
    y_margin = (page_height - (rows * label_height)) / 2

    for i, barcode in enumerate(barcodes):
        col = i % cols
        row = (i // cols) % rows

        if i > 0 and i % (cols * rows) == 0:
            c.showPage()  # Yeni sayfaya geç

        qr = qrcode.make(barcode)
        qr_filename = os.path.join(qr_dir, f"{barcode}.png")
        qr.save(qr_filename)

        x = x_margin + col * label_width
        y = page_height - y_margin - (row + 1) * label_height

        c.drawImage(qr_filename, x + 5 * mm, y + 5 * mm, width=30 * mm, height=30 * mm)
        c.setFont("Helvetica", 8)
        c.drawCentredString(x + label_width / 2, y + 2 * mm, barcode)

    c.save()

    return jsonify({'success': True, 'pdf_path': f"/static/qr_codes/etiketler_{timestamp}.pdf"})