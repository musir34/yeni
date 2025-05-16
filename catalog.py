# catalog_blueprint.py
# =========================================================
#   Güllü Shoes – PDF Katalog Üretimi (ReportLab)
#   © 2025 – Müşir’in ayakkabıları için şık tasarım
# =========================================================
from flask import Blueprint, send_file, current_app
from models import Product
import os, time
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors

catalog_bp = Blueprint("catalog", __name__)

# ---------- ÖZELLEŞTİRİLEBİLİR TASARIM AYARLARI ----------------------------
PAGE_SIZE        = A4
MARGIN           = 15 * mm
GRID_COLS        = 2
GRID_ROWS        = 2
IMAGE_SIZE       = 95 * mm
BLOCK_VPAD       = 4 * mm
BLOCK_BORDER_R   = 8
LINE_SPACING     = 6 * mm        # 🔎 Satır arası boşluk
BRAND_COLOR      = (0.80, 0.10, 0.20)
FONT_REG         = "DejaVu"
FONT_BOLD        = "DejaVu-Bold"
COVER_SLOGAN     = "2025 Yaz Koleksiyonu"
CONTACT_LINE     = "gullushoes.com  •  +90 553 944 66 17  •  +90 555 026 20 31  •  @gullushoess"
# ---------------------------------------------------------------------------

@catalog_bp.route("/generate_catalog_reportlab", methods=["GET"])
def generate_catalog_reportlab():
    print("▶ Katalog üretimi başlıyor…")
    t0 = time.time()

    # -------- ÜRÜNLERİ ÇEK / SÜZ -------------------------------------------------
    products = Product.query.filter_by(size="37").all()
    uniq, final = set(), []
    for p in products:
        key = (p.product_main_id, p.color)
        if key not in uniq:
            uniq.add(key)
            img_path = os.path.join(current_app.root_path, "static", "images", f"{p.barcode}.jpg")
            if os.path.exists(img_path):
                final.append(p)

    if not final:
        return "Gösterilecek ürün bulunamadı!", 404
        
@catalog_bp.route("/print_barcodes_a4", methods=["GET", "POST"])
def print_barcodes_a4():
    """
    Ürün barkodlarını A4 kağıda 3x7 (21 adet) düzeninde yazdırır.
    GET: Form gösterir
    POST: PDF etiket dosyası oluşturur
    """
    from flask import render_template, flash, redirect, url_for
    
    if request.method == "GET":
        return render_template("print_barcodes_a4_form.html")
    
    # POST işlemi
    barcode_list = request.form.get("barcode_list", "").strip()
    if not barcode_list:
        flash("Lütfen en az bir barkod girin", "warning")
        return redirect(url_for("catalog.print_barcodes_a4"))
    
    # Barkodları satır satır böl ve temizle
    lines = barcode_list.strip().split("\n")
    items = []
    
    for line in lines:
        parts = line.strip().split(",")
        if len(parts) >= 1:
            barcode = parts[0].strip()
            # İkinci eleman varsa adet olarak al, yoksa 1 varsay
            quantity = 1
            if len(parts) >= 2:
                try:
                    quantity = int(parts[1].strip())
                    if quantity <= 0:
                        quantity = 1
                except ValueError:
                    quantity = 1
            
            if barcode:
                items.append({"barcode": barcode, "quantity": quantity})
    
    if not items:
        flash("Geçerli barkod bulunamadı", "warning")
        return redirect(url_for("catalog.print_barcodes_a4"))
    
    # QR kodlarını oluştur ve PDF'e aktar
    from qr_utils import generate_qr_labels_pdf
    
    # Flask test_request_context ile generate_qr_labels_pdf fonksiyonunu çağır
    with current_app.test_request_context():
        from flask import request as flask_request
        flask_request.json = {"items": items}
        return generate_qr_labels_pdf()

    # -------- PDF / FONT ----------------------------------------------------------------
    out_path = os.path.join(current_app.root_path, "static", "catalog_reportlab.pdf")
    c = canvas.Canvas(out_path, pagesize=PAGE_SIZE)

    font_dir = os.path.join(current_app.root_path, "static", "fonts")
    try:
        pdfmetrics.registerFont(TTFont(FONT_REG,  os.path.join(font_dir, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, os.path.join(font_dir, "DejaVuSans-Bold.ttf")))
    except Exception as e:
        print("⚠ Font yüklenemedi →", e)

    # -------- YARDIMCI ÇİZİM FONKSİYONLARI ---------------------------------------
    def cover_page():
        pw, ph = PAGE_SIZE
        c.setFillColorRGB(*BRAND_COLOR, alpha=0.04)
        c.rect(0, 0, pw, ph, fill=1, stroke=0)
        logo_path = os.path.join(current_app.root_path, "static", "images", "gullu.png")
        if os.path.exists(logo_path):
            try:
                logo = ImageReader(logo_path)
                c.drawImage(logo, pw/2 - 35*mm, ph*0.60,
                            width=70*mm, height=60*mm,
                            preserveAspectRatio=True, anchor="c", mask="auto")
            except Exception as e:
                print("Logo yüklenemedi:", e)
        c.setFillColorRGB(*BRAND_COLOR)
        c.setFont(FONT_BOLD, 40)
        c.drawCentredString(pw/2, ph*0.48, "GÜLLÜ SHOES")
        c.setFont(FONT_REG, 22)
        c.drawCentredString(pw/2, ph*0.42, COVER_SLOGAN)
        c.setFont(FONT_REG, 12)
        c.setFillColor(colors.black)
        c.drawCentredString(pw/2, 20*mm, CONTACT_LINE)
        c.showPage()

    def draw_product_box(prod, x, y, w, h):
        c.setStrokeColorRGB(0.87, 0.87, 0.87)
        c.roundRect(x, y, w, h, BLOCK_BORDER_R, stroke=1, fill=0)

        # Görsel
        img_path = os.path.join(current_app.root_path, "static", "images", f"{prod.barcode}.jpg")
        try:
            img = ImageReader(img_path)
            img_x = x + (w-IMAGE_SIZE)/2
            img_y = y + h - IMAGE_SIZE - BLOCK_VPAD
            c.drawImage(img, img_x, img_y,
                        width=IMAGE_SIZE, height=IMAGE_SIZE,
                        preserveAspectRatio=True, anchor="c", mask="auto")
        except Exception:
            c.setFont(FONT_REG, 10)
            c.drawCentredString(x + w/2, y + h/2, "Görsel Yok")

        # Metinler (ferah aralıklarla)
        base_x = x + 6*mm
        base_y = y + 6*mm
        c.setFont(FONT_BOLD, 11)
        c.setFillColorRGB(*BRAND_COLOR)
        c.drawString(base_x, base_y + 2*LINE_SPACING, f"Model: {prod.product_main_id}")

        c.setFont(FONT_REG, 10)
        c.setFillColor(colors.black)
        c.drawString(base_x, base_y + LINE_SPACING, f"Renk : {prod.color}")
        c.drawString(base_x, base_y, f"Barkod: {prod.barcode}")

        if getattr(prod, "price", None):
            c.drawRightString(x + w - 6*mm, base_y, f"{prod.price:,.0f} ₺")

    # -------------------- ÇİZİM ---------------------------------------------------
    cover_page()
    pw, ph  = PAGE_SIZE
    cell_w  = (pw - 2*MARGIN) / GRID_COLS
    cell_h  = (ph - 2*MARGIN - 12*mm) / GRID_ROWS
    page_idx = 1

    for i, prod in enumerate(final):
        if i % (GRID_ROWS*GRID_COLS) == 0:
            if i:
                c.showPage()
            c.setFont(FONT_BOLD, 16)
            c.setFillColorRGB(*BRAND_COLOR)
            c.drawCentredString(pw/2, ph - MARGIN + 4*mm, f"GÜLLÜ SHOES – {COVER_SLOGAN}")
            c.setFillColor(colors.black)
            c.setFont(FONT_REG, 9)
            c.drawCentredString(pw/2, 10*mm, f"Sayfa {page_idx}")
            c.drawCentredString(pw/2, 6*mm, CONTACT_LINE)
            page_idx += 1

        idx = i % (GRID_ROWS*GRID_COLS)
        row, col = divmod(idx, GRID_COLS)
        x = MARGIN + col * cell_w + 3*mm
        y = ph - MARGIN - (row+1)*cell_h + 3*mm
        draw_product_box(prod, x, y, cell_w - 6*mm, cell_h - 6*mm)

    c.save()
    print(f"✅ Katalog oluşturuldu → {time.time() - t0:.2f} sn")
    return send_file(out_path, as_attachment=True)
