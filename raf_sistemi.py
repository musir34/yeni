from flask import Blueprint, request, jsonify
from models import db, Raf
import qrcode
import barcode
from barcode.writer import ImageWriter
import os
from flask import Blueprint, request, jsonify, render_template

raf_bp = Blueprint("raf", __name__, url_prefix="/raf")

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

    os.makedirs("static", exist_ok=True)
    barcode_path = f"static/barcode_{kod}.png"
    qr_path = f"static/qr_{kod}.png"

    barcode.get("code128", kod, writer=ImageWriter()).save(barcode_path.replace(".png", ""))
    qrcode.make(kod).save(qr_path)

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


@raf_bp.route("/stok-form", methods=["GET"])
def stok_form():
    return render_template("raf_stok_ekle.html")



@raf_bp.route("/form", methods=["GET"])
def raf_form_sayfasi():
    return render_template("raf_olustur.html")
