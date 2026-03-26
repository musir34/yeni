from flask import Blueprint, request, jsonify, render_template, flash, redirect, url_for
from models import db, Raf, Product, RafUrun, CentralStock
from user_logs import log_user_action
import qrcode
import barcode
from barcode.writer import ImageWriter
import os
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime  # 🔧 datetime import eklendi

# YENİ EKLENEN IMPORT'LAR
import io
from flask import send_file

# 🔥 BARKOD ALIAS DESTEĞİ
from barcode_alias_helper import normalize_barcode

# 🔥 MERKEZ STOK SENKRONİZASYONU
from stock_management import sync_central_stock, sync_multiple_barcodes

raf_bp = Blueprint("raf", __name__, url_prefix="/raf")


#barkod ile ürün arama
@raf_bp.route("/api/ara/<string:barkod>", methods=["GET"])
def barkod_ara(barkod):
    """
    Barkod girildiğinde ürünün hangi raflarda olduğunu döndürür.
    Sadece adet > 0 olan raf kayıtları gösterilir.
    
    🔥 BARKOD ALIAS DESTEKLİ: Alias girilirse ana barkod olarak arar.
    """
    # 🔥 Barkodu normalize et (alias ise ana barkoda çevir)
    normalized = normalize_barcode(barkod)
    
    urunler = (RafUrun.query
               .filter_by(urun_barkodu=normalized)
               .filter(RafUrun.adet > 0)
               .all())
    if not urunler:
        return jsonify({"message": "Bu barkod için stok bulunamadı."}), 404

    detaylar = []
    for u in urunler:
        raf = Raf.query.filter_by(kod=u.raf_kodu).first()
        detaylar.append({
            "raf_kodu": u.raf_kodu,
            "raf_adi": raf.kod if raf else "",
            "adet": u.adet
        })

    return jsonify({
        "barkod": normalized,  # Ana barkodu döndür
        "searched_barcode": barkod,  # Aranan orijinal barkod
        "raflar": detaylar
    })



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

    # 👇 0 adetli kayıtlar gelmez
    urunler_db = (RafUrun.query
                  .filter_by(raf_kodu=raf.kod)
                  .filter(RafUrun.adet > 0)
                  .all())

    if not urunler_db:
        return jsonify([])

    barkodlar = [u.urun_barkodu for u in urunler_db]
    urun_bilgileri_map = {
        p.barcode: {"model": p.product_main_id, "color": p.color, "size": p.size}
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
    from models import CentralStock

    raf_kodu = request.form.get("raf_kodu")
    barkod = (request.form.get("barkod") or "").strip().replace(" ", "")
    
    # 🔥 Barkodu normalize et
    normalized = normalize_barcode(barkod)
    
    try:
        yeni_adet = int(request.form.get("adet"))
    except (TypeError, ValueError):
        flash("Geçersiz adet.", "danger")
        return redirect(url_for("raf.raf_yonetimi"))  # 👈 raf listesine dön

    urun = RafUrun.query.filter_by(raf_kodu=raf_kodu, urun_barkodu=normalized).first()
    if not urun:
        flash("Ürün rafta bulunamadı.", "danger")
        return redirect(url_for("raf.raf_yonetimi"))  # 👈

    if yeni_adet <= 0:
        db.session.delete(urun)
        db.session.commit()
        sync_central_stock(normalized)
        try: log_user_action("DELETE", {"işlem_açıklaması": f"Raf stok kaldırıldı — {raf_kodu} / {normalized}", "sayfa": "Raf Yönetimi", "raf_kodu": raf_kodu, "barkod": normalized})
        except: pass
        flash(f"{raf_kodu} rafından {normalized} kaldırıldı. CentralStock güncellendi.", "success")
        return redirect(url_for("raf.raf_yonetimi"))

    urun.adet = yeni_adet
    db.session.commit()
    sync_central_stock(normalized)
    try: log_user_action("STOCK_UPDATE", {"işlem_açıklaması": f"Raf stok güncellendi — {raf_kodu} / {normalized} → {yeni_adet} adet", "sayfa": "Raf Yönetimi", "raf_kodu": raf_kodu, "barkod": normalized, "yeni_adet": yeni_adet})
    except: pass
    flash(f"{raf_kodu} rafındaki {normalized} adet {yeni_adet} olarak güncellendi.", "success")
    return redirect(url_for("raf.raf_yonetimi"))  # 👈



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
        for p in Product.query.with_entities(
            Product.barcode, Product.product_main_id, Product.color, Product.size
        )
    }

    for raf in raflar:
        # 👇 0 adetli kayıtlar gelmez
        urunler = (RafUrun.query
                   .filter_by(raf_kodu=raf.kod)
                   .filter(RafUrun.adet > 0)
                   .all())
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
    try: log_user_action("CREATE", {"işlem_açıklaması": f"Yeni raf oluşturuldu — {kod}", "sayfa": "Raf Yönetimi", "raf_kodu": kod})
    except: pass

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

        # 🔥 Etkilenen barkodları kaydet
        urunler = RafUrun.query.filter_by(raf_kodu=raf.kod).all()
        affected_barcodes = [urun.urun_barkodu for urun in urunler]
        
        # RafUrun kayıtlarını sil
        for urun in urunler:
            db.session.delete(urun)

        if raf.barcode_path and os.path.exists(raf.barcode_path):
            os.remove(raf.barcode_path)
        if raf.qr_path and os.path.exists(raf.qr_path):
            os.remove(raf.qr_path)

        db.session.delete(raf)
        db.session.commit()
        try: log_user_action("DELETE", {"işlem_açıklaması": f"Raf silindi — {raf.kod}", "sayfa": "Raf Yönetimi", "raf_kodu": raf.kod, "etkilenen_barkod": len(affected_barcodes)})
        except: pass
        sync_multiple_barcodes(affected_barcodes)

        return jsonify({
            "success": True,
            "message": f"{kod} başarıyla silindi."
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@raf_bp.route("/toplu-sil", methods=["POST"])
def toplu_raf_sil():
    """Seçili rafları toplu olarak siler. 
    - Ana raf kodu verilirse (örn: 'Z') o ana rafla başlayan tüm rafları siler.
    - İkincil raf kodu verilirse (örn: 'A-01') o ikincil raftaki tüm katları siler.
    - Tam raf kodu verilirse (örn: 'A-01-02') sadece o rafı siler."""
    try:
        data = request.json
        raf_kodlari = data.get("raf_kodlari", [])
        
        if not raf_kodlari:
            return jsonify({"error": "Silinecek raf seçilmedi."}), 400
        
        silinen_raflar = []
        affected_barcodes = set()  # 🔥 Etkilenen barkodlar
        silinecek_raflar = []  # Raf objelerini sakla
        
        # 1. Önce tüm silinecek rafları ve ürünlerini topla
        for kod in raf_kodlari:
            # Eğer kod tek harf ise (ana raf), o harfle başlayan tüm rafları bul
            if len(kod) == 1 or (len(kod) <= 2 and '-' not in kod):
                # Ana raf kodu - tüm alt rafları bul
                raflar = Raf.query.filter(Raf.kod.like(f"{kod}%")).all()
            # Eğer kod A-01 formatında ise (ikincil raf), o ikincil raftaki tüm katları bul
            elif kod.count('-') == 1:
                # İkincil raf kodu - tüm katları bul
                raflar = Raf.query.filter(Raf.kod.like(f"{kod}-%")).all()
            else:
                # Tek raf kodu
                raflar = [Raf.query.filter_by(kod=kod).first()]
                raflar = [r for r in raflar if r is not None]
            
            silinecek_raflar.extend(raflar)
        
        # 2. Önce tüm RafUrun kayıtlarını sil ve etkilenen barkodları kaydet
        for raf in silinecek_raflar:
            urunler = RafUrun.query.filter_by(raf_kodu=raf.kod).all()
            for urun in urunler:
                # 🔥 Etkilenen barkodları kaydet
                affected_barcodes.add(urun.urun_barkodu)
                db.session.delete(urun)
        
        # 3. RafUrun silmelerini commit et
        db.session.flush()
        
        # 4. Şimdi Raf kayıtlarını sil
        for raf in silinecek_raflar:
            # Dosyaları sil
            try:
                if raf.barcode_path and os.path.exists(raf.barcode_path):
                    os.remove(raf.barcode_path)
            except:
                pass
            try:
                if raf.qr_path and os.path.exists(raf.qr_path):
                    os.remove(raf.qr_path)
            except:
                pass
            
            silinen_raflar.append(raf.kod)
            db.session.delete(raf)
        
        db.session.commit()
        try: log_user_action("BULK_DELETE", {"işlem_açıklaması": f"Toplu raf silindi — {len(silinen_raflar)} raf ({', '.join(silinen_raflar[:5])}{'...' if len(silinen_raflar)>5 else ''})", "sayfa": "Raf Yönetimi", "silinen_raflar": len(silinen_raflar), "etkilenen_barkod": len(affected_barcodes)})
        except: pass
        sync_multiple_barcodes(list(affected_barcodes))
        
        return jsonify({
            "success": True,
            "message": f"{len(silinen_raflar)} raf başarıyla silindi.",
            "silinen_raflar": silinen_raflar
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@raf_bp.route("/stok-sil", methods=["POST"])
def raf_urun_sil():
    raf_kodu = request.form.get("raf_kodu")
    barkod = (request.form.get("barkod") or "").strip().replace(" ", "")
    barkod = normalize_barcode(barkod)
    if not raf_kodu or not barkod:
        flash("Geçersiz istek. Raf kodu ve barkod gerekli.", "danger")
        return redirect(url_for("raf.raf_yonetimi"))  # 👈

    urun = RafUrun.query.filter_by(raf_kodu=raf_kodu, urun_barkodu=barkod).first()
    if not urun:
        flash("Ürün rafta bulunamadı.", "warning")
        return redirect(url_for("raf.raf_yonetimi"))  # 👈

    db.session.delete(urun)
    db.session.commit()
    try: log_user_action("DELETE", {"işlem_açıklaması": f"Raf ürün silindi — {raf_kodu} / {barkod}", "sayfa": "Raf Yönetimi", "raf_kodu": raf_kodu, "barkod": barkod})
    except: pass
    sync_central_stock(barkod)
    
    flash(f"{raf_kodu} rafından {barkod} silindi. CentralStock güncellendi.", "success")
    return redirect(url_for("raf.raf_yonetimi"))  # 👈



@raf_bp.route("/stok-ekle", methods=["POST"])
def stok_ekle_api():
    data = request.json
    raf_kodu = data.get("raf_kodu")
    urunler = data.get("urunler")
    if not raf_kodu or not urunler:
        return jsonify({"error": "Raf kodu ve ürün listesi zorunludur."}), 400
    urunler = [normalize_barcode(b) for b in urunler]
    for barkod in urunler:
        mevcut_kayit = RafUrun.query.filter_by(raf_kodu=raf_kodu,
                                               urun_barkodu=barkod).first()
        if mevcut_kayit:
            mevcut_kayit.adet += 1
        else:
            yeni = RafUrun(raf_kodu=raf_kodu, urun_barkodu=barkod, adet=1)
            db.session.add(yeni)
    db.session.commit()
    try: log_user_action("STOCK_UPDATE", {"işlem_açıklaması": f"Rafa stok eklendi — {raf_kodu}, {len(urunler)} barkod", "sayfa": "Raf Yönetimi", "raf_kodu": raf_kodu, "ürün_sayısı": len(urunler)})
    except: pass
    sync_multiple_barcodes(urunler)
    
    return jsonify({"message": "Stok başarıyla eklendi."}), 200


@raf_bp.route('/api/check-raf/<raf_kodu>', methods=['GET'])
def check_raf_var_mi(raf_kodu):
    """
    Raf kodunun sistemde olup olmadığını kontrol eder.
    🔧 "=" ve "*" karakterlerini "-" ile değiştirir (telefon klavyelerinden kaynaklanan sorun için).
    """
    # 🔧 "=" ve "*" karakterlerini "-" ile değiştir
    raf_kodu = raf_kodu.replace('=', '-').replace('*', '-')
    
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
