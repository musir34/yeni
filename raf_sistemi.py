from flask import Blueprint, request, jsonify
from models import db, Raf
import qrcode
import barcode
from barcode.writer import ImageWriter
import os
from flask import Blueprint, request, jsonify, render_template
from PIL import Image, ImageDraw, ImageFont
import qrcode

raf_bp = Blueprint("raf", __name__, url_prefix="/raf")

def qrcode_with_text(data, filename):
    import qrcode
    from PIL import Image, ImageDraw, ImageFont

    # 1. QR kodu daha büyük üret
    qr = qrcode.QRCode(box_size=12, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    width, height = qr_img.size

    # 2. Yazı alanını geniş tut
    text_height = 80
    total_height = height + text_height
    new_img = Image.new("RGB", (width, total_height), "white")
    new_img.paste(qr_img, (0, 0))

    # 3. Yazı boyutunu büyüt
    draw = ImageDraw.Draw(new_img)
    try:
        font = ImageFont.truetype("arial.ttf", 48)  # daha büyük yazı
    except:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), data, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # ortala ve dikey olarak dengeli yerleştir
    x = (width - text_width) / 2
    y = height + (text_height // 4)

    draw.text((x, y), data, fill="black", font=font)
    new_img.save(filename, dpi=(300, 300))  # yüksek dpi ile kaydet



@raf_bp.route("/olustur", methods=["POST"])
def raf_olustur_api():
    data = request.json
    ana = data.get("ana")
    ikincil = data.get("ikincil")
    kat = data.get("kat", "").zfill(2)

    if not ana or not ikincil or not kat:
        return jsonify({"error": "Tüm alanlar zorunludur."}), 400

    kod = f"{ana}-{ikincil}-{kat}"

    if Raf.query.filter_by(kod=kod).first():
        return jsonify({"error": "Bu raf zaten kayıtlı."}), 409

    # static/raflar klasörü varsa oluştur
    os.makedirs("static/raflar", exist_ok=True)

    barcode_path = f"static/raflar/barcode_{kod}.png"
    qr_path = f"static/raflar/qr_{kod}.png"

    # Barkod oluştur
    barcode.get("code128", kod, writer=ImageWriter()).save(barcode_path.replace(".png", ""))

    # QR oluştur (altına yazılı)
    qrcode_with_text(kod, qr_path)

    yeni_raf = Raf(
        kod=kod,
        ana=ana,
        ikincil=ikincil,
        kat=kat,
        barcode_path=barcode_path,
        qr_path=qr_path
    )
    db.session.add(yeni_raf)
    db.session.commit()

    return jsonify({
        "message": "Raf başarıyla oluşturuldu.",
        "kod": kod,
        "barcode": barcode_path,
        "qr": qr_path
    }), 201


@raf_bp.route("/sil/<string:kod>", methods=["POST"])
def raf_sil(kod):
    try:
        raf = Raf.query.filter_by(kod=kod).first()
        if not raf:
            return jsonify({"error": "Raf bulunamadı."}), 404

        # önce raf_urunleri'ndeki ürünleri sil (tek tek)
        urunler = RafUrun.query.filter_by(raf_kodu=raf.kod).all()
        for urun in urunler:
            db.session.delete(urun)

        # sonra görselleri sil
        if raf.barcode_path and os.path.exists(raf.barcode_path):
            os.remove(raf.barcode_path)
        if raf.qr_path and os.path.exists(raf.qr_path):
            os.remove(raf.qr_path)

        # en son rafı sil
        db.session.delete(raf)
        db.session.commit()

        return jsonify({"success": True, "message": f"{kod} başarıyla silindi."})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500



@raf_bp.route("/stok-ekle", methods=["POST"])
def stok_ekle_api():
    data = request.json
    raf_kodu = data.get("raf_kodu")
    urunler = data.get("urunler")  # Liste bekliyoruz: ["12345", "12346", ...]

    if not raf_kodu or not urunler:
        return jsonify({"error": "Raf kodu ve ürün listesi zorunludur."}), 400

    for barkod in urunler:
        mevcut_kayit = RafUrun.query.filter_by(raf_kodu=raf_kodu, urun_barkodu=barkod).first()
        if mevcut_kayit:
            mevcut_kayit.adet += 1
        else:
            yeni = RafUrun(raf_kodu=raf_kodu, urun_barkodu=barkod, adet=1)
            db.session.add(yeni)

    db.session.commit()
    return jsonify({"message": "Stok başarıyla eklendi."}), 200

@raf_bp.route('/api/check-raf/<raf_kodu>', methods=['GET'])
def check_raf_var_mi(raf_kodu):
    from models import Raf  # modelde raflar varsa
    raf = Raf.query.filter_by(kod=raf_kodu).first()
    if raf:
        return jsonify(success=True, message="Raf mevcut.")
    else:
        return jsonify(success=False, message="Bu raf mevcut değil."), 404



@raf_bp.route("/api/liste", methods=["GET"])
def raf_listesi_api():
    raflar = Raf.query.order_by(Raf.kod.asc()).all()
    return jsonify([
        {
            "kod": r.kod,
            "barkod": "/" + r.barcode_path,
            "qr": "/" + r.qr_path
        }
        for r in raflar
    ])


@raf_bp.route("/stok-form", methods=["GET"])
def stok_form():
    return render_template("raf_stok_ekle.html")


@raf_bp.route("/form", methods=["GET"])
def raf_form_sayfasi():
    return render_template("raf_olustur.html")
