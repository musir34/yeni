from flask import Blueprint, render_template, request, redirect, url_for, jsonify, current_app, send_from_directory
import json
from datetime import datetime
from models import db, SiparisFisi, Product
# Eğer Pillow kütüphanesini logo boyutlandırma için kullanıyorsan bu import kalsın:
from PIL import Image
import os
# datetime importu zaten var, tekrar etmesine gerek yok eğer from datetime import datetime kullandıysan

# QR Kod oluşturmak için gerekli kütüphaneler
# Eğer yüklü değilse: pip install qrcode[svg]
import qrcode
import qrcode.image.svg # SVG formatında QR kod için
import io # QR kodunu bellekte tutmak için

siparis_fisi_bp = Blueprint("siparis_fisi_bp", __name__)

# json_loads filtresi zaten vardı, kalsın
@siparis_fisi_bp.app_template_filter('json_loads')
def json_loads_filter(s):
    # None veya boş string gelirse hata vermemesi için kontrol ekleyebiliriz
    if s is None or s.strip() == "":
        return []
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        # Hata olursa boş liste dön veya logla
        print(f"JSON Decode Error: {s}") # Debug için
        return []

# ------------------------------------------------------------
# YARDIMCI FONKSİYON: QR Kod Oluşturma ve Kaydetme (Sunucu Taraflı)
# ------------------------------------------------------------
def generate_and_save_qr_code(barcode_data):
    """
    Verilen barkod değeri için QR kod görseli oluşturur,
    static/qrcodes klasörüne kaydeder ve web adresini döndürür.
    Aynı barkod için tekrar oluşturmaz (performans).
    """
    # QR kodun kaydedileceği klasör yolu (uygulamanın root path'ine göre)
    qr_codes_dir = os.path.join(current_app.root_path, 'static', 'qrcodes')

    # Klasör yoksa oluştur
    if not os.path.exists(qr_codes_dir):
        os.makedirs(qr_codes_dir)

    # QR kod dosya adı (barkod değeri + .svg)
    # Dosya adında güvenli karakterler kullanmak önemli
    # Barkod değeri boş veya None gelirse varsayılan bir isim kullan
    safe_barcode_data = "".join(c for c in (barcode_data or "") if c.isalnum() or c in ('-', '_', '.'))
    if not safe_barcode_data:
         safe_barcode_data = "empty_barcode" # Varsayılan isim

    qr_file_name = f"{safe_barcode_data}.svg"
    qr_file_path = os.path.join(qr_codes_dir, qr_file_name)
    qr_web_path = url_for('static', filename=f'qrcodes/{qr_file_name}') # Web'den erişim yolu

    # Eğer dosya zaten varsa, tekrar oluşturmaya gerek yok (performans için)
    if os.path.exists(qr_file_path):
        return qr_web_path

    try:
        # QR kod objesi oluştur
        # error_correction: Hata düzeltme seviyesi (L, M, Q, H) - H en yüksek hata düzeltme
        # box_size: Her bir kutucuğun piksel boyutu
        # border: Kenar boşluğu
        qr = qrcode.QRCode(
            version=1, # QR kod versiyonu, 1 en küçük
            error_correction=qrcode.constants.ERROR_CORRECT_H, # Yüksek hata düzeltme
            box_size=10, # Boyut
            border=4, # Kenarlık
        )
        qr.add_data(barcode_data) # QR koduna eklenecek veri
        qr.make(fit=True) # QR kod matrisini oluştur

        # QR kod görselini SVG formatında oluştur ve dosyaya kaydet
        # SVG formatı yazdırma için genellikle daha iyi kalite sunar
        img = qr.make_image(image_factory=qrcode.image.svg.SvgImage)
        with open(qr_file_path, 'wb') as f:
            img.save(f)

        print(f"QR kod oluşturuldu ve kaydedildi: {qr_file_path}") # Debug
        return qr_web_path # Oluşturulan dosyanın web adresini döndür

    except Exception as e:
        print(f"QR kod oluşturulurken hata: {e}")
        # Hata durumunda placeholder görselin yolunu döndürebiliriz
        # Bu placeholder görselin static klasöründe olduğundan emin olmalısın
        # Örneğin: static/placeholder_qr_error.svg veya static/placeholder_qr_error.png
        # Eğer yoksa, basit bir placeholder servisi kullanabilirsin:
        return "https://via.placeholder.com/100x100?text=QR+Hata" # Geçici placeholder

# ------------------------------------------------------------
# YARDIMCI FONKSİYONLAR (Gruplama & Beden Sıralama)
# ... (Bu fonksiyonlar olduğu gibi kalacak) ...
# ------------------------------------------------------------
def group_products_by_model_and_color(products):
    """
    Product tablosundan gelen kayıtları (model, renk) ikilisine göre gruplar.
    Örn: grouped_products[(model_id, color)] = [list_of_products]
    """
    grouped_products = {}
    for product in products:
        # product_main_id veya color eksikse, boş string ile geçici olarak dolduralım
        key = (product.product_main_id or '', product.color or '')
        grouped_products.setdefault(key, []).append(product)
    return grouped_products

def sort_variants_by_size(product_group):
    """
    Ürünlerin 'size' alanını (beden) büyükten küçüğe doğru sıralar.
    Numerik değilse, alfabetik ters sırada sıralama yapar.
    """
    try:
        return sorted(product_group, key=lambda x: float(x.size), reverse=True)
    except (ValueError, TypeError):
        return sorted(product_group, key=lambda x: x.size, reverse=True)


# ------------------------------------------------------------
# YENİ ROTA: /siparis_fisi_urunler
# ... (Bu rota olduğu gibi kalacak) ...
# ------------------------------------------------------------
@siparis_fisi_bp.route("/siparis_fisi_urunler")
def siparis_fisi_urunler():
    """
    Product tablosundaki ürünleri (model_main_id, color) bazında gruplar,
    sayfalama yapar ve 'siparis_fisi_urunler.html' şablonuna gönderir.
    """
    # Tüm veya bir filtreyle çekebilirsiniz (örneğin hidden=False).
    products = Product.query.all()

    # 1) Gruplama: (model, color) bazında
    grouped_products = group_products_by_model_and_color(products)

    # 2) Sayfalama ayarları
    page = request.args.get('page', 1, type=int)
    per_page = 9
    total_groups = len(grouped_products)

    # 3) Grupları keylerine göre sıralayalım
    sorted_keys = sorted(grouped_products.keys())
    paginated_keys = sorted_keys[(page - 1) * per_page : page * per_page]

    # 4) Her grup içindeki product listelerini 'size' alanına göre sırala
    paginated_product_groups = {
        key: sort_variants_by_size(grouped_products[key])
        for key in paginated_keys
    }

    # 5) Toplam sayfa hesabı
    total_pages = (total_groups + per_page - 1) // per_page

    # Yılı burada hesaplıyoruz ve template'e gönderiyoruz (Eğer bu template'te yıl kullanılıyorsa)
    current_year = datetime.now().year


    return render_template(
        "siparis_fisi_urunler.html",  # Bu şablonu oluşturmalısınız
        grouped_products=paginated_product_groups,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        current_year=current_year # Yıl değişkenini template'e gönder
    )


# ================
# 1) Liste Görünümü
# ================
@siparis_fisi_bp.route("/siparis_fisi_sayfasi", methods=["GET"])
def siparis_fisi_sayfasi():
    """
    'siparis_fisi.html' adlı şablonu aç,
    fişleri tablo/kart şeklinde gösterir
    """
    model_kodu = request.args.get('model_kodu', '')
    renk = request.args.get('renk', '')

    query = SiparisFisi.query

    if model_kodu:
        query = query.filter(SiparisFisi.urun_model_kodu.ilike(f'%{model_kodu}%'))
    if renk:
        query = query.filter(SiparisFisi.renk.ilike(f'%{renk}%'))

    page = request.args.get('page', 1, type=int)
    per_page = 20  # Her sayfada gösterilecek fiş sayısı

    pagination = query.order_by(SiparisFisi.created_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    fisler = pagination.items

    # Yılı burada hesaplıyoruz ve template'e gönderiyoruz
    current_year = datetime.now().year

    return render_template(
        "siparis_fisi.html",
        fisler=fisler,
        pagination=pagination,
        current_year=current_year # Yıl değişkenini template'e gönder
    )


# =====================
# 2) Özet Liste Görünümü
# ... (Bu rota olduğu gibi kalacak) ...
# =====================
@siparis_fisi_bp.route("/siparis_fisi_listesi", methods=["GET"])
def siparis_fisi_listesi():
    """
    'siparis_fisi_listesi.html' adlı şablonu aç,
    fişlerin sadece ID, tarih vb. gibi özet bilgilerini göstermek için
    """
    fisler = SiparisFisi.query.order_by(SiparisFisi.created_date.desc()).all()
    # Yılı burada hesaplıyoruz ve template'e gönderiyoruz (Eğer bu template'te yıl kullanılıyorsa)
    current_year = datetime.now().year
    return render_template("siparis_fisi_listesi.html", fisler=fisler, current_year=current_year)


# ======================
# 3) Tek Fiş Yazdırma
# ... (Bu rota olduğu gibi kalacak) ...
# ======================
@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>/yazdir", methods=["GET"])
def siparis_fisi_yazdir(siparis_id):
    """
    Tek bir fişi yazdırmak için şablonu döner.
    'multiple=False' parametresi ile, şablonda
    tekli yazdırma olduğunu belirtiyoruz (yeşil nokta).
    """
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    # Yazdırma tarihini güncelle
    fis.print_date = datetime.now()
    db.session.commit()

    # Yılı burada hesaplıyoruz ve template'e gönderiyoruz (Eğer bu template'te yıl kullanılıyorsa)
    current_year = datetime.now().year

    return render_template(
        "siparis_fisi_print.html",
        fis=fis,
        multiple=False,
        current_year=current_year # Yıl değişkenini template'e gönder
    )

@siparis_fisi_bp.route("/siparis_fisi/bos_yazdir")
def bos_yazdir():
    """
    Boş bir fiş şablonu yazdırmak isterseniz kullanılacak endpoint
    """
    # Yılı burada hesaplıyoruz ve template'e gönderiyoruz (Eğer bu template'te yıl kullanılıyorsa)
    current_year = datetime.now().year
    return render_template("siparis_fisi_bos_print.html", current_year=current_year)


# ======================
# 4) Toplu Fiş Yazdırma
# ... (Bu rota olduğu gibi kalacak) ...
# ======================
@siparis_fisi_bp.route("/siparis_fisi/toplu_yazdir/<fis_ids>")
def toplu_yazdir(fis_ids):
    """
    Birden çok fişi aynı anda yazdırmak için,
    'multiple=True' parametresi gönderiyoruz (kırmızı nokta).
    """
    try:
        id_list = [int(id_) for id_ in fis_ids.split(',')]
        fisler = SiparisFisi.query.filter(SiparisFisi.siparis_id.in_(id_list)).all()
        if not fisler:
            return jsonify({"mesaj": "Seçili fişler bulunamadı"}), 404

        # Yazdırma tarihlerini güncelle
        current_time = datetime.now()
        for fis in fisler:
            fis.print_date = current_time
        db.session.commit()

        # Yılı burada hesaplıyoruz ve template'e gönderiyoruz (Eğer bu template'te yıl kullanılıyorsa)
        current_year = datetime.now().year

        return render_template(
            "siparis_fisi_toplu_print.html",
            fisler=fisler,
            multiple=True,
            current_year=current_year # Yıl değişkenini template'e gönder
        )
    except Exception as e:
        print(f"Toplu yazdırma hatası: {e}") # Debug
        return jsonify({"mesaj": "Hata oluştu", "error": str(e)}), 500


# =====================
# 5) Fiş Detay Sayfası
# ... (Bu rota olduğu gibi kalacak) ...
# =====================
@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>/detay", methods=["GET"])
def siparis_fisi_detay(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    if not fis.teslim_kayitlari:
        fis.teslim_kayitlari = "[]"
        # fis.kalan_adet'i burada set etmek yerine, ilk oluştuğunda set edildiğinden emin ol.
        # Detay sayfasında her zaman güncel hesaplanmış kalanı göstermek daha iyi olabilir.
        # Ancak senin modelinde kolon varsa, burayı değiştirmeyelim şimdilik.
        # fis.kalan_adet = fis.toplam_adet # Bu satır muhtemelen fiş oluşturulurken olmalı
        db.session.commit() # Eğer yukarıda bir değişiklik yaptıysan commit et

    # Yılı burada hesaplıyoruz ve template'e gönderiyoruz
    current_year = datetime.now().year

    return render_template("siparis_fisi_detay.html", fis=fis, current_year=current_year)


@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>/teslimat", methods=["POST"])
def teslimat_kaydi_ekle(siparis_id):
    """
    Yeni teslimat kaydı ekle
    """
    try:
        fis = SiparisFisi.query.get(siparis_id)
        if not fis:
            return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

        # teslim_kayitlari None gelirse boş liste yap
        kayitlar = json.loads(fis.teslim_kayitlari or "[]")

        model_code = request.form.get("model_code")
        color = request.form.get("color")

        beden_adetleri = {}
        toplam = 0
        for size in range(35, 42):
            key = f"beden_{size}"
            adet = int(request.form.get(key, 0)) # Varsayılan 0 yap
            beden_adetleri[key] = adet
            toplam += adet

        if toplam <= 0:
            # Kullanıcı dostu hata mesajı döndür
            # Flask'ta flash mesaj sistemi kullanmak daha iyi bir UI sunar
            return redirect(url_for("siparis_fisi_bp.siparis_fisi_detay", siparis_id=siparis_id, error="Teslim edilecek ürün adeti 0'dan büyük olmalı."))


        # Yeni kaydı ekle
        yeni_kayit = {
            "tarih": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "model_code": model_code,
            "color": color,
            **beden_adetleri, # Beden adetlerini dict olarak ekle
            "toplam": toplam
        }
        kayitlar.append(yeni_kayit)

        # Kalan adedi güncelle - TÜM teslimat kayıtlarındaki toplamları yeniden topla
        total_teslim_across_all_items = 0
        if kayitlar:
            # Her bir teslim kaydının toplam adetini alıp genel toplama ekle
            total_teslim_across_all_items = sum(k.get("toplam", 0) for k in kayitlar) # .get ile güvenli alım

        fis.teslim_kayitlari = json.dumps(kayitlar, ensure_ascii=False)
        fis.kalan_adet = fis.toplam_adet - total_teslim_across_all_items


        # Stokları güncelle (Trendyol mantığı: teslimat = stoktan düşüş)
        for size, adet in beden_adetleri.items():
            if adet > 0:
                size_num = size.split('_')[1] # beden_35 -> 35
                # İlgili bedenin barkodunu fis.kalemler_json içindeki barkodlar dict'ine bakmalısın.
                # Fis modelinde barkod_35 vs. kolonları yok, kalemler_json içinde var.
                kalemler_list = json.loads(fis.kalemler_json or "[]")
                # Doğru kalemi (model_code ve color eşleşen) bul
                target_kalem = next((k for k in kalemler_list if k.get('model_code') == model_code and k.get('color') == color), None)

                if target_kalem:
                    barkodlar_dict_kalem = target_kalem.get('barkodlar', {})
                    barkod = barkodlar_dict_kalem.get(size_num) # Beden numarasına göre barkodu al

                    if barkod:
                         # Barkoda göre ürünü bul ve stok düş
                        product_to_update = Product.query.filter_by(barcode=barkod).first()
                        if product_to_update:
                             product_to_update.quantity -= adet # MİKTARI DÜŞ
                             print(f"Stok güncellendi: Barkod {barkod}, Adet {adet} düşüldü.") # Debug

        db.session.commit()
        # Başarılı olunca fiş detay sayfasına geri dön
        # Flask'ta flash mesaj sistemi ile başarı mesajı gösterebilirsin
        return redirect(url_for("siparis_fisi_bp.siparis_fisi_detay", siparis_id=siparis_id))

    except Exception as e:
        # Hata durumunda kullanıcıya mesaj gösterilebilir
        print(f"Teslimat kaydı eklerken hata: {e}") # Debug için
        # Flask'ta flash mesaj sistemi kullanmak iyi olabilir
        return redirect(url_for("siparis_fisi_bp.siparis_fisi_detay", siparis_id=siparis_id, error=f"Teslimat eklenirken bir hata oluştu: {str(e)}"))


# ==================================
# 6) YENİ SİPARİŞ FİŞİ OLUŞTUR (Form)
# ... (Bu rota olduğu gibi kalacak) ...
# ==================================
@siparis_fisi_bp.route("/siparis_fisi/olustur", methods=["GET", "POST"])
def siparis_fisi_olustur():
    search_query = request.args.get('search', '').strip()

    # Base query
    query = Product.query.with_entities(
        Product.product_main_id.label('title'),
        Product.color
    )

    # Filtre
    if search_query:
        query = query.filter(Product.product_main_id == search_query)  # Tam eşleşme

    # Ürünleri gruplu çek
    urunler = query.group_by(Product.product_main_id, Product.color).all()

    if request.method == "POST":
        # Formdan birden çok model satırı al
        model_codes = request.form.getlist("model_codes[]")
        colors = request.form.getlist("colors[]")
        cift_basi_fiyat_list = request.form.getlist("cift_basi_fiyat[]")  # her satır için fiyat
        beden_35_list = request.form.getlist("beden_35[]")
        beden_36_list = request.form.getlist("beden_36[]")
        beden_37_list = request.form.getlist("beden_37[]")
        beden_38_list = request.form.getlist("beden_38[]")
        beden_39_list = request.form.getlist("beden_39[]")
        beden_40_list = request.form.getlist("beden_40[]")
        beden_41_list = request.form.getlist("beden_41[]")

        kalemler = []
        total_adet = 0
        total_fiyat = 0

        def parse_or_zero(lst, index):
            """Liste dolu mu, eleman var mı, int dönüştürülebilir mi? Yoksa 0."""
            if not lst or len(lst) <= index or not lst[index]:
                return 0
            try:
                return int(lst[index])
            except ValueError:
                return 0

        def parse_or_float_zero(lst, index):
            """Benzer mantıkla float dönüştürülür, yoksa 0.0."""
            if not lst or len(lst) <= index or not lst[index]:
                return 0.0
            try:
                return float(lst[index])
            except ValueError:
                return 0.0

        # Bütün satırları gez
        for i in range(len(model_codes)):
            mcode = (model_codes[i] or "").strip()
            clr = (colors[i] or "").strip()
            if not mcode: # Model kodu boşsa bu satırı atla
                continue

            b35 = parse_or_zero(beden_35_list, i)
            b36 = parse_or_zero(beden_36_list, i)
            b37 = parse_or_zero(beden_37_list, i)
            b38 = parse_or_zero(beden_38_list, i)
            b39 = parse_or_zero(beden_39_list, i)
            b40 = parse_or_zero(beden_40_list, i)
            b41 = parse_or_zero(beden_41_list, i)

            satir_toplam_adet = b35 + b36 + b37 + b38 + b39 + b40 + b41
            cift_fiyat = parse_or_float_zero(cift_basi_fiyat_list, i)
            satir_toplam_fiyat = satir_toplam_adet * cift_fiyat

            # Model + renk'e ait barkodları çekiyoruz
            products_for_barcode = Product.query.filter_by(product_main_id=mcode, color=clr).all()
            barkodlar = {}
            for p in products_for_barcode:
                if p.size and p.barcode:
                    barkodlar[str(int(float(p.size)))] = p.barcode # Bedenleri string olarak kaydet

            # Bu satırı ekle
            kalemler.append({
                "model_code": mcode,
                "color": clr,
                "beden_35": b35,
                "beden_36": b36,
                "beden_37": b37,
                "beden_38": b38,
                "beden_39": b39,
                "beden_40": b40,
                "beden_41": b41,
                "cift_basi_fiyat": cift_fiyat,
                "satir_toplam_adet": satir_toplam_adet,
                "satir_toplam_fiyat": satir_toplam_fiyat,
                "barkodlar": barkodlar # Barkod dict'ini kaydet
            })

            total_adet += satir_toplam_adet
            total_fiyat += satir_toplam_fiyat

        if not kalemler:
            # Kullanıcı dostu hata mesajı
             return redirect(url_for("siparis_fisi_bp.siparis_fisi_olustur", error="Sipariş fişi oluşturmak için en az bir geçerli ürün satırı eklemelisiniz."))


        # Tek sipariş fişi oluştur
        yeni_fis = SiparisFisi(
            urun_model_kodu="Çoklu Model",  # Burası istersen sabit
            renk="Birden Fazla", # Burası istersen sabit
            toplam_adet = total_adet,
            toplam_fiyat = total_fiyat,
            created_date = datetime.now(),
            kalemler_json = json.dumps(kalemler, ensure_ascii=False), # Kalemler listesini JSON olarak kaydet
            image_url = "/static/logo/gullu.png", # Varsayılan resim yolu
            kalan_adet = total_adet # Başlangıçta kalan adet toplam adete eşit
        )

        db.session.add(yeni_fis)
        db.session.commit()

        # Opsiyonel: Logo resmi boyutlandırma (Eğer PIL yüklüyse ve kullanmak istiyorsan)
        # Bu kısım sipariş fişi oluşturmayla direkt alakalı değil, istersen kaldırabilirsin.
        # Eğer kullanacaksan, Pillow kütüphanesinin (pip install Pillow) yüklü olduğundan emin ol.
        try:
            image_path = os.path.join(current_app.root_path, 'static', 'logo', 'gullu.png')
            if os.path.exists(image_path):
                 with Image.open(image_path) as img:
                     img = img.convert('RGB')
                     img = img.resize((250, 150), Image.Resampling.LANCZOS)
                     resized_image_path = os.path.join(current_app.root_path, 'static', 'logo', 'gullu_resized.png')
                     img.save(resized_image_path, 'PNG', quality=85)
                     # Fiş objesine yeniden boyutlandırılmış resmin yolunu kaydet (isteğe bağlı)
                     # yeni_fis.image_url = url_for('static', filename='logo/gullu_resized.png')
                     # db.session.commit() # Değişikliği kaydet
        except ImportError:
             print("Pillow kütüphanesi yüklü değil. Logo boyutlandırma atlandı.")
        except Exception as e:
             print(f"Logo yeniden boyutlandırma hatası: {e}")


        # Başarılı olunca sipariş fişleri listesine yönlendir
        return redirect(url_for("siparis_fisi_bp.siparis_fisi_sayfasi"))

    else:
        # GET isteği
        # Yılı burada hesaplıyoruz ve template'e gönderiyoruz (Eğer bu template'te yıl kullanılıyorsa)
        current_year = datetime.now().year
        return render_template("siparis_fisi_olustur.html", urunler=urunler, current_year=current_year)


# ===========================
# 7) CRUD JSON Endpoint'leri
# ... (Bu rotalar olduğu gibi kalacak) ...
# ===========================
@siparis_fisi_bp.route("/siparis_fisi", methods=["GET"])
def get_siparis_fisi_list():
    fisler = SiparisFisi.query.order_by(SiparisFisi.created_date.desc()).all()
    sonuc = []
    for fis in fisler:
        sonuc.append({
            "siparis_id": fis.siparis_id,
            "urun_model_kodu": fis.urun_model_kodu,
            "renk": fis.renk,
            # Beden adetlerini kalemler_json'dan almak daha doğru olabilir
            "beden_35": fis.beden_35, # Eğer bu kolonlar hala kullanılıyorsa kalsın
            "beden_36": fis.beden_36,
            "beden_37": fis.beden_37,
            "beden_38": fis.beden_38,
            "beden_39": fis.beden_39,
            "beden_40": fis.beden_40,
            "beden_41": fis.beden_41,
            "cift_basi_fiyat": float(fis.cift_basi_fiyat),
            "toplam_adet": fis.toplam_adet,
            "toplam_fiyat": float(fis.toplam_fiyat),
            "created_date": fis.created_date.strftime("%Y-%m-%d %H:%M:%S") if fis.created_date else None,
            "image_url": fis.image_url,
            "kalan_adet": fis.kalan_adet # Kalan adeti de ekleyelim
        })
    return jsonify(sonuc), 200

@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>", methods=["GET"])
def get_siparis_fisi(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    # Kalem detaylarını da JSON'a ekleyebiliriz
    kalemler_data = json.loads(fis.kalemler_json or "[]")

    return jsonify({
        "siparis_id": fis.siparis_id,
        "urun_model_kodu": fis.urun_model_kodu,
        "renk": fis.renk,
        # Beden adetlerini ana fiş objesinden alıyoruz (eğer hala tutuluyorsa)
        "beden_35": fis.beden_35,
        "beden_36": fis.beden_36,
        "beden_37": fis.beden_37,
        "beden_38": fis.beden_38,
        "beden_39": fis.beden_39,
        "beden_40": fis.beden_40,
        "beden_41": fis.beden_41,
        "cift_basi_fiyat": float(fis.cift_basi_fiyat),
        "toplam_adet": fis.toplam_adet,
        "toplam_fiyat": float(fis.toplam_fiyat),
        "created_date": fis.created_date.strftime("%Y-%m-%d %H:%M:%S") if fis.created_date else None,
        "image_url": fis.image_url,
        "kalan_adet": fis.kalan_adet,
        "kalemler": kalemler_data # Kalem detaylarını da ekledik
    }), 200

@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>", methods=["PUT"])
def update_siparis_fisi(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    data = request.json or {}
    # Ana fiş bilgilerini güncelle (kalemler_json'ı PUT ile güncellemek daha karmaşık olur, şimdilik ana bilgileri güncelleyelim)
    fis.urun_model_kodu = data.get("urun_model_kodu", fis.urun_model_kodu)
    fis.renk = data.get("renk", fis.renk)
    fis.cift_basi_fiyat = data.get("cift_basi_fiyat", fis.cift_basi_fiyat) # Ana fiş fiyatı güncellenirse

    # Beden adetlerini ana fiş objesinde güncelliyorsan burası kalsın
    fis.beden_35 = data.get("beden_35", fis.beden_35)
    fis.beden_36 = data.get("beden_36", fis.beden_36)
    fis.beden_37 = data.get("beden_37", fis.beden_37)
    fis.beden_38 = data.get("beden_38", fis.beden_38)
    fis.beden_39 = data.get("beden_39", fis.beden_39)
    fis.beden_40 = data.get("beden_40", fis.beden_40)
    fis.beden_41 = data.get("beden_41", fis.beden_41)


    # Toplam adet ve fiyatı yeniden hesapla (ana fiş bedenleri güncellendiyse)
    # Eğer toplam adet ve fiyat kalemler_json'dan hesaplanıyorsa, burası değişmeli
    fis.toplam_adet = (
        int(fis.beden_35 or 0) + int(fis.beden_36 or 0) + int(fis.beden_37 or 0) +
        int(fis.beden_38 or 0) + int(fis.beden_39 or 0) + int(fis.beden_40 or 0) + int(fis.beden_41 or 0)
    )
    # Toplam fiyatı kalemler_json'dan hesaplamak daha doğru olabilir
    # Şimdilik ana fiş fiyatı ve toplam adete göre hesaplayalım
    fis.toplam_fiyat = float(fis.toplam_adet) * float(fis.cift_basi_fiyat or 0.0)

    # Kalan adeti yeniden hesapla (teslimat kayıtları varsa)
    kayitlar = json.loads(fis.teslim_kayitlari or "[]")
    total_teslim_across_all_items = sum(k.get("toplam", 0) for k in kayitlar)
    fis.kalan_adet = fis.toplam_adet - total_teslim_across_all_items


    db.session.commit()
    return jsonify({"mesaj": "Sipariş fişi güncellendi."}), 200

@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>", methods=["DELETE"])
def delete_siparis_fisi(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    db.session.delete(fis)
    db.session.commit()
    return jsonify({"mesaj": "Sipariş fişi silindi."}), 200 # Başarılı silme mesajı


@siparis_fisi_bp.route("/maliyet_fisi_bos", methods=["GET"])
def maliyet_fisi_bos():
    """
    Boş maliyet fişi yazdırma endpoint'i
    """
    # Yılı burada hesaplıyoruz ve template'e gönderiyoruz (Eğer bu template'te yıl kullanılıyorsa)
    current_year = datetime.now().year
    return render_template("maliyet_fisi_print.html", now=datetime.now, current_year=current_year)

@siparis_fisi_bp.route("/maliyet_fisi/<int:siparis_id>/yazdir", methods=["GET"])
def maliyet_fisi_yazdir(siparis_id):
    """
    Maliyet fişi yazdırma endpoint'i
    """
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    # Yılı burada hesaplıyoruz ve template'e gönderiyoruz (Eğer bu template'te yıl kullanılıyorsa)
    current_year = datetime.now().year

    return render_template(
        "maliyet_fisi_print.html",
        fis=fis,
        current_year=current_year # Yıl değişkenini template'e gönder
    )


@siparis_fisi_bp.route("/get_product_details/<model_code>")
def get_product_details(model_code):
    products = Product.query.filter_by(product_main_id=model_code).all()

    if not products:
        return jsonify({"success": False, "message": "Ürün bulunamadı"})

    # Modele ait tüm benzersiz renkleri al
    colors = list(set(p.color for p in products if p.color))

    # Renk ve beden-barkod eşleştirmelerini yap
    product_data = {}
    for color in colors:
        product_data[color] = {}
        color_products = [p for p in products if p.color == color]
        for product in color_products:
            # Bedenleri string olarak kaydet (JSON'da keyler string olmalı)
            if product.size and product.barcode:
                 try:
                     # Bedeni float'a çevirip sonra int'e çevirerek .0 kısmını at
                     size_key = str(int(float(product.size)))
                     product_data[color][size_key] = product.barcode
                 except (ValueError, TypeError):
                      # Eğer beden numerik değilse, olduğu gibi string olarak kaydet
                      product_data[color][str(product.size)] = product.barcode


    return jsonify({
        "success": True,
        "colors": colors,
        "product_data": product_data
    })


# =========================================================
#  BARKOD ETİKETİ YAZDIRMA  ➜  Sunucu taraflı QR + is_printed
# =========================================================
@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>/barkod_yazdir", methods=["GET"])
def siparis_fisi_barkod_yazdir(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return "Sipariş fişi bulunamadı", 404

    try:
        kalemler = json.loads(fis.kalemler_json or "[]")
    except json.JSONDecodeError:
        kalemler = []

    unique_barcodes_to_print = []

    # ✅ EKLE → printed barkodları küme olarak al
    printed_set = set(fis.printed_barcodes or [])

    for kalem in kalemler:
        # … kalemden model, renk, barkodlar vs çek
        for size in range(35, 42):
            size_str = str(size)
            barcode = kalem.get("barkodlar", {}).get(size_str)
            quantity = int(kalem.get(f"beden_{size_str}", 0))
            if quantity > 0 and barcode:
                unique_barcodes_to_print.append({
                    "barcode"      : barcode,
                    "model"        : kalem.get("model_code", "N/A"),
                    "color"        : kalem.get("color", "N/A"),
                    "size"         : size_str,
                    "qr_image_path": generate_and_save_qr_code(barcode),
                    "print_count"  : quantity * 3,
                    "is_printed"   : barcode in printed_set   # ✅ burada kullanılıyor
                })

    return render_template(
        "siparis_fisi_barkod_print.html",
        barcodes=unique_barcodes_to_print,
        siparis_id=siparis_id
    )

# =========================================================
#  YAZDIRMA DURUMUNU GÜNCELLE
# =========================================================
@siparis_fisi_bp.route("/mark_as_printed", methods=["POST"])
def mark_as_printed():
    data = request.get_json(force=True) or {}
    siparis_id = data.get("siparis_id")
    barcodes   = data.get("barcodes", [])

    if not siparis_id:
        return jsonify(success=False, message="Sipariş ID'si eksik"), 400

    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify(success=False, message="Fiş bulunamadı"), 404

    # boşsa liste olarak başlat
    fis.printed_barcodes = fis.printed_barcodes or []

    # sadece yeni barkodları ekle
    new_ones = [bc for bc in barcodes if bc not in fis.printed_barcodes]
    if new_ones:
        fis.printed_barcodes.extend(new_ones)
        db.session.commit()

    return jsonify(success=True, added=new_ones), 200
