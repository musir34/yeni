from flask import Blueprint, request, jsonify, render_template, flash, redirect
from models import db, Raf, Product, RafUrun
import qrcode
import barcode
from barcode.writer import ImageWriter
import os
from PIL import Image, ImageDraw, ImageFont

# YENİ EKLENEN IMPORT'LAR
import io
from flask import send_file

raf_bp = Blueprint("raf", __name__, url_prefix="/raf")


@raf_bp.route("/api/kademeli-liste", methods=["GET"])
def raf_kademeli_liste():
    """
    Rafları 3 katmanlı bir yapıda döndürür. Frontend'in artık path'lere ihtiyacı olmadığı için
    bu kısmı sadeleştirebiliriz ama şimdilik bu şekilde kalmasının bir zararı yok.
    """
    raflar = Raf.query.order_by(Raf.ana, Raf.ikincil, Raf.kat).all()
    kademeli_raflar = {}

    for r in raflar:
        ana_kod = r.ana
        ikincil_tam_kod = f"{r.ana}-{r.ikincil}"
        kat_kod = r.kat

        if ana_kod not in kademeli_raflar:
            kademeli_raflar[ana_kod] = {}

        if ikincil_tam_kod not in kademeli_raflar[ana_kod]:
            kademeli_raflar[ana_kod][ikincil_tam_kod] = []

        kademeli_raflar[ana_kod][ikincil_tam_kod].append({
            "kat":
            kat_kod,
            "qr_path":
            "/" + r.qr_path if r.qr_path else "",
            "barcode_path":
            "/" + r.barcode_path if r.barcode_path else ""
        })

    return jsonify(kademeli_raflar)


@raf_bp.route("/api/gruplu-liste", methods=["GET"])
def raf_gruplu_liste():
    raflar = Raf.query.order_by(Raf.kod.asc()).all()
    gruplar = {}
    for r in raflar:
        ana = r.ana
        if ana not in gruplar:
            gruplar[ana] = []
        gruplar[ana].append({
            "kod": r.kod,
            "qr": "/" + r.qr_path,
            "barkod": "/" + r.barcode_path
        })
    return jsonify(gruplar)


@raf_bp.route('/yonetim')
def raf_yonetimi():
    ana_raflar = db.session.query(Raf.ana).distinct().all()
    grouped_raflar = {}
    for ana in ana_raflar:
        ikinciller = Raf.query.filter_by(ana=ana[0]).all()
        grouped_raflar[ana[0]] = [f"{r.ana}-{r.ikincil}" for r in ikinciller]

    return render_template("raf_olustur.html", grouped_raflar=grouped_raflar)


@raf_bp.route("/api/stoklar/<string:raf_kodu>", methods=["GET"])
def api_get_raf_stoklari(raf_kodu):
    raf = Raf.query.filter_by(kod=raf_kodu).first()
    if not raf:
        return jsonify({"error": "Raf bulunamadı"}), 404

    urunler_db = RafUrun.query.filter_by(raf_kodu=raf.kod).all()

    if not urunler_db:
        return jsonify([])

    barkodlar = [u.urun_barkodu for u in urunler_db]
    urun_bilgileri_map = {
        p.barcode: {
            "model": p.product_main_id,
            "color": p.color,
            "size": p.size
        }
        for p in Product.query.filter(Product.barcode.in_(barkodlar))
    }

    detaylar = []
    for u in urunler_db:
        urun_bilgi = urun_bilgileri_map.get(u.urun_barkodu)
        if urun_bilgi:
            detaylar.append({
                "barkod": u.urun_barkodu,
                "adet": u.adet,
                "model": urun_bilgi["model"],
                "color": urun_bilgi["color"],
                "size": urun_bilgi["size"]
            })

    return jsonify(detaylar)


@raf_bp.route("/stok-guncelle", methods=["POST"])
def raf_stok_guncelle():
    raf_kodu = request.form.get("raf_kodu")
    barkod = request.form.get("barkod")
    yeni_adet = int(request.form.get("adet"))

    urun = RafUrun.query.filter_by(raf_kodu=raf_kodu,
                                   urun_barkodu=barkod).first()
    if urun:
        urun.adet = yeni_adet
        db.session.commit()
        flash("Stok güncellendi.", "success")
    else:
        flash("Ürün rafta bulunamadı.", "danger")

    return redirect("/raf/stoklar")


@raf_bp.route("/stoklar", methods=["GET"])
def raf_stok_listesi():
    raflar = Raf.query.order_by(Raf.kod).all()
    raf_stoklari = {}
    barkod_map = {
        p.barcode: {
            "product_main_id": p.product_main_id,
            "color": p.color,
            "size": p.size
        }
        for p in
        Product.query.with_entities(Product.barcode, Product.product_main_id,
                                    Product.color, Product.size)
    }
    for raf in raflar:
        urunler = RafUrun.query.filter_by(raf_kodu=raf.kod).all()
        detaylar = []
        for u in urunler:
            urun_bilgi = barkod_map.get(u.urun_barkodu)
            if urun_bilgi:
                detaylar.append({
                    "barkod": u.urun_barkodu,
                    "adet": u.adet,
                    "model": urun_bilgi["product_main_id"],
                    "color": urun_bilgi["color"],
                    "size": urun_bilgi["size"]
                })
        raf_stoklari[raf.kod] = detaylar
    return render_template("raf_stok_liste.html", raf_stoklari=raf_stoklari)


def qrcode_with_text(data, filename):
    qr = qrcode.QRCode(box_size=12, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black",
                           back_color="white").convert("RGB")
    width, height = qr_img.size
    text_height_area = 80
    total_height = height + text_height_area
    new_img = Image.new("RGB", (width, total_height), "white")
    new_img.paste(qr_img, (0, 0))
    draw = ImageDraw.Draw(new_img)
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), data, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (width - text_width) / 2
    y = height + (text_height_area - text_height) / 2
    draw.text((x, y), data, fill="black", font=font)
    new_img.save(filename, dpi=(300, 300))


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

    os.makedirs("static/raflar", exist_ok=True)
    barcode_path = f"static/raflar/barcode_{kod}.png"
    qr_path = f"static/raflar/qr_{kod}.png"

    barcode.get("code128", kod,
                writer=ImageWriter()).save(barcode_path.replace(".png", ""))
    qrcode_with_text(kod, qr_path)

    yeni_raf = Raf(kod=kod,
                   ana=ana,
                   ikincil=ikincil,
                   kat=kat,
                   barcode_path=barcode_path,
                   qr_path=qr_path)
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

        urunler = RafUrun.query.filter_by(raf_kodu=raf.kod).all()
        for urun in urunler:
            db.session.delete(urun)

        if raf.barcode_path and os.path.exists(raf.barcode_path):
            os.remove(raf.barcode_path)
        if raf.qr_path and os.path.exists(raf.qr_path):
            os.remove(raf.qr_path)

        db.session.delete(raf)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"{kod} başarıyla silindi."
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@raf_bp.route("/stok-sil", methods=["POST"])
def raf_urun_sil():
    raf_kodu = request.form.get("raf_kodu")
    barkod = request.form.get("barkod")
    if not raf_kodu or not barkod:
        flash("Geçersiz istek. Raf kodu ve barkod gerekli.", "danger")
        return redirect("/raf/yonetim")
    urun = RafUrun.query.filter_by(raf_kodu=raf_kodu,
                                   urun_barkodu=barkod).first()
    if not urun:
        flash("Ürün rafta bulunamadı.", "warning")
        return redirect("/raf/yonetim")
    db.session.delete(urun)
    db.session.commit()
    flash("Ürün raftan silindi.", "success")
    return redirect("/raf/yonetim")


@raf_bp.route("/stok-ekle", methods=["POST"])
def stok_ekle_api():
    data = request.json
    raf_kodu = data.get("raf_kodu")
    urunler = data.get("urunler")
    if not raf_kodu or not urunler:
        return jsonify({"error": "Raf kodu ve ürün listesi zorunludur."}), 400
    for barkod in urunler:
        mevcut_kayit = RafUrun.query.filter_by(raf_kodu=raf_kodu,
                                               urun_barkodu=barkod).first()
        if mevcut_kayit:
            mevcut_kayit.adet += 1
        else:
            yeni = RafUrun(raf_kodu=raf_kodu, urun_barkodu=barkod, adet=1)
            db.session.add(yeni)
    db.session.commit()
    return jsonify({"message": "Stok başarıyla eklendi."}), 200


@raf_bp.route('/api/check-raf/<raf_kodu>', methods=['GET'])
def check_raf_var_mi(raf_kodu):
    raf = Raf.query.filter_by(kod=raf_kodu).first()
    if raf:
        return jsonify(success=True, message="Raf mevcut.")
    else:
        return jsonify(success=False, message="Bu raf mevcut değil."), 404


@raf_bp.route("/api/liste", methods=["GET"])
def raf_listesi_api():
    raflar = Raf.query.order_by(Raf.kod.asc()).all()
    return jsonify([{
        "kod": r.kod,
        "barkod": "/" + r.barcode_path,
        "qr": "/" + r.qr_path
    } for r in raflar])


@raf_bp.route("/stok-form", methods=["GET"])
def stok_form():
    return render_template("stock_addition.html")


@raf_bp.route("/form", methods=["GET"])
def raf_form_sayfasi():
    return render_template("raf_olustur.html")


# YENİ EKLENEN ROUTE'LAR (Anlık Görsel Oluşturma için)
@raf_bp.route('/etiket/qr/<string:raf_kodu>')
def generate_qr_etiket(raf_kodu):
    """Verilen raf koduna göre anlık olarak QR kod resmi oluşturur ve döndürür."""
    # QR kodu bellekte bir byte dizisi olarak oluştur
    img_buffer = io.BytesIO()
    # Not: Yazdırma etiketinde yazı zaten var, o yüzden basit qrcode.make kullanıyoruz
    qr_img = qrcode.make(raf_kodu)
    qr_img.save(img_buffer, 'PNG')
    img_buffer.seek(0)  # Buffer'ın başına git

    # Resmi tarayıcıya gönder
    return send_file(img_buffer, mimetype='image/png')


@raf_bp.route('/etiket/barkod/<string:raf_kodu>')
def generate_barcode_etiket(raf_kodu):
    """Verilen raf koduna göre anlık olarak Barkod resmi oluşturur ve döndürür."""
    # Barkodu bellekte bir byte dizisi olarak oluştur
    CODE128 = barcode.get_barcode_class('code128')
    ean = CODE128(raf_kodu, writer=ImageWriter())

    img_buffer = io.BytesIO()
    ean.write(img_buffer)
    img_buffer.seek(0)  # Buffer'ın başına git

    # Resmi tarayıcıya gönder
    return send_file(img_buffer, mimetype='image/png')
