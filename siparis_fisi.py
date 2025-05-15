# siparis_fisi.py
# ... (diğer importlar ve kodlar) ...

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, current_app, send_from_directory, send_file # send_file eklendi
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
# reportlab'e ihtiyacımız yok artık (PDF yerine HTML/CSS ile baskı alacağız)
# from reportlab.lib.pagesizes import A4 # Kaldırıldı
# from reportlab.pdfgen import canvas # Kaldırıldı
# from reportlab.lib.units import mm # Kaldırıldı
import qrcode.image.svg # SVG formatında QR kod için
import io # QR kodunu bellekte tutmak için

# Barkod resmi kaydetme fonksiyonu (Eğer kullanıyorsan, siparis_fisi_barkod_print rotasında kullanılmıyor gibi)
# Eğer kullanılıyorsa, barcode_utils dosyasından veya bu dosyada tanımlı olmalı.
# generate_barcode fonksiyonu order_list_service veya barcode_utils'de olabilir.
# from barcode_utils import generate_barcode # Eğer buradan import ediliyorsa

siparis_fisi_bp = Blueprint("siparis_fisi_bp", __name__)

# json_loads filtresi
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
    logoyu arka plana (watermark) olarak ekler,
    static/qr_codes klasörüne kaydeder ve web adresini döndürür.
    Aynı barkod için tekrar oluşturmaz (performans).
    """
    from PIL import Image, ImageEnhance

    qr_codes_dir = os.path.join(current_app.root_path, 'static', 'qr_codes')
    if not os.path.exists(qr_codes_dir):
        os.makedirs(qr_codes_dir)

    safe_barcode_data = "".join(c for c in (barcode_data or "") if c.isalnum() or c in ('-', '_', '.'))
    if not safe_barcode_data:
        safe_barcode_data = "empty_barcode"

    qr_file_name = f"{safe_barcode_data}.png"
    qr_file_path = os.path.join(qr_codes_dir, qr_file_name)
    qr_web_path = url_for('static', filename=f'qr_codes/{qr_file_name}')

    if os.path.exists(qr_file_path):
        return qr_web_path

    try:
        # --- QR Kodunu Üret ---
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(barcode_data)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")

        # --- LOGOYU ARKA PLANA EKLE ---
        logo_path = os.path.join(current_app.root_path, "static", "logo", "gullu.png")
        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            # Logoyu QR ile aynı boyuta getir
            logo = logo.resize(qr_img.size)
            # Logoyu saydamlaştır (opacity düşür: %15-20 gibi)
            alpha = logo.split()[3]
            alpha = ImageEnhance.Brightness(alpha).enhance(0.18)  # Opaklığı %18 yap
            logo.putalpha(alpha)

            # QR'ın altına logoyu yerleştir (arka plana)
            # Önce logoyu, sonra QR kodunu üste koy
            combined = Image.alpha_composite(logo, qr_img)
        else:
            combined = qr_img  # Logo yoksa sadece QR

        combined.save(qr_file_path, 'PNG')
        print(f"Logolu QR kod kaydedildi: {qr_file_path}")
        return qr_web_path

    except Exception as e:
        print(f"QR kod oluşturulurken hata: {e}")
        return "https://via.placeholder.com/100?text=QR+Hata"



# ------------------------------------------------------------
# YARDIMCI FONKSİYONLAR (Gruplama & Beden Sıralama)
# ... (Bu fonksiyonlar olduğu gibi kalacak) ...
# ------------------------------------------------------------
# group_products_by_model_and_color ve sort_variants_by_size fonksiyonları
# get_products.py dosyasında da tanımlı olabilir. Eğer merkezi bir yerde tanımlıysa,
# buradan kaldırılıp import edilmeli veya get_products.py içindeki halleri kullanılmalı.
# Senin yüklediğin dosyalarda bu fonksiyonlar get_products.py'de de var.
# Bu dosyada da tanımlı olmaları çakışmaya neden olabilir.
# Farz edelim bu dosyada kalan halleri kullanılıyor (veya get_products'tan import edildi).

def group_products_by_model_and_color(products):
    """
    Product tablosundan gelen kayıtları (model, renk) ikilisine göre gruplar.
    Örn: grouped_products[(model_id, color)] = [list_of_products]
    """
    grouped_products = {}
    for product in products:
        # product_main_id veya color eksikse, boş string ile geçici olarak dolduralım
        main_id = product.product_main_id if product.product_main_id else ''
        color = product.color if product.color else ''
        key = (main_id, color)
        grouped_products.setdefault(key, []).append(product)
    return grouped_products

def sort_variants_by_size(product_group):
    """
    Ürünlerin 'size' alanını (beden) büyükten küçüğe doğru sıralar.
    Numerik değilse, alfabetik ters sırada sıralama yapar.
    """
    try:
        # Bedenleri sayısal olarak sıralamaya çalış, hata olursa string olarak
        return sorted(product_group, key=lambda x: float(x.size) if x.size and isinstance(x.size, str) and x.size.replace('.', '', 1).isdigit() else (x.size or ''), reverse=True)
    except (ValueError, TypeError):
        # Sayısal olmayan veya boş bedenler için string sıralaması
        return sorted(product_group, key=lambda x: (x.size or ''), reverse=True)


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
    # Sıralama anahtarını model kodu (alfanumerik) ve renk (alfabetik) yapalım
    sorted_keys = sorted(grouped_products.keys(), key=lambda item: (item[0].lower(), item[1].lower()))

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
    # Boş fişte 'fis' objesi olmadığı için, template'in 'fis' olmadan çalışması lazım.
    # Maliyet fişi template'ini fis objesi göndermeden render ediyoruz.
    return render_template("siparis_fisi_bos_print.html", current_year=current_year, now=datetime.now()) # now objesini de gönderelim


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
        # db.session.commit() # Eğer yukarıda bir değişiklik yaptıysan commit et


    # Yılı burada hesaplıyoruz ve template'e gönderiyoruz
    current_year = datetime.now().year

    # Teslimat kayıtları string ise parse et
    teslim_kayitlari_parsed = []
    if fis.teslim_kayitlari:
        try:
            teslim_kayitlari_parsed = json.loads(fis.teslim_kayitlari)
        except json.JSONDecodeError:
            print(f"Hata: Sipariş fişi {siparis_id} teslim_kayitlari alanı JSON formatında değil.")
            teslim_kayitlari_parsed = [] # Hata durumunda boş liste


    # Kalemler listesi string ise parse et
    kalemler_parsed = []
    if fis.kalemler_json:
        try:
            kalemler_parsed = json.loads(fis.kalemler_json)
        except json.JSONDecodeError:
             print(f"Hata: Sipariş fişi {siparis_id} kalemler_json alanı JSON formatında değil.")
             kalemler_parsed = [] # Hata durumunda boş liste


    # Kalemler içinde her bir ürün detayını (barkod vb.) göstermek için
    # Burada ekstra bir liste hazırlayabiliriz veya template içinde kalemler_parsed üzerinde dönebiliriz.
    # Template içinde dönmek daha kolay.

    return render_template("siparis_fisi_detay.html", 
                           fis=fis, 
                           kalemler=kalemler_parsed, # Şablona parsed kalemleri gönder
                           teslim_kayitlari=teslim_kayitlari_parsed, # Şablona parsed teslimatları gönder
                           current_year=current_year)


@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>/teslimat", methods=["POST"])
def teslimat_kaydi_ekle(siparis_id):
    """
    Yeni teslimat kaydı ekle ve stok düş
    """
    try:
        fis = SiparisFisi.query.get(siparis_id)
        if not fis:
            # Flask'ta flash mesaj sistemi kullanmak daha iyi bir UI sunar
            # return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404
            flash("Sipariş fişi bulunamadı.", "danger")
            return redirect(url_for("siparis_fisi_bp.siparis_fisi_sayfasi"))


        # teslim_kayitlari None gelirse boş liste yap ve JSON parse et
        kayitlar = json.loads(fis.teslim_kayitlari or "[]")

        model_code = request.form.get("model_code")
        color = request.form.get("color")

        beden_adetleri = {}
        toplam_teslim_adet = 0
        # Beden numaraları 35'ten 41'e kadar
        for size in range(35, 42):
            key = f"beden_{size}"
            # Formdan gelen değeri int'e çevir, boş veya geçersizse 0 yap
            adet = int(request.form.get(key, 0) or 0) # Hem None hem boş string için 0 varsayılan
            beden_adetleri[f"beden_{size}"] = adet # Key'i beden_35 gibi sakla
            toplam_teslim_adet += adet

        if toplam_teslim_adet <= 0:
            # Kullanıcı dostu hata mesajı döndür
            flash("Teslim edilecek ürün adeti 0'dan büyük olmalı.", "warning")
            return redirect(url_for("siparis_fisi_bp.siparis_fisi_detay", siparis_id=siparis_id))


        # Yeni kaydı ekle
        yeni_kayit = {
            "tarih": datetime.now().strftime("%Y-%m-%d %H:%M"), # Tarih formatı tutarlı olmalı
            "model_code": model_code,
            "color": color,
            **beden_adetleri, # Beden adetlerini dict olarak ekle
            "toplam": toplam_teslim_adet # Bu teslimat kaydındaki toplam adet
        }
        kayitlar.append(yeni_kayit)

        # Kalan adedi güncelle - TÜM teslimat kayıtlarındaki toplamları yeniden topla
        total_teslim_across_all_items = 0
        if kayitlar:
            # Her bir teslim kaydının 'toplam' alanını güvenli bir şekilde topla
            total_teslim_across_all_items = sum(int(k.get("toplam", 0) or 0) for k in kayitlar if isinstance(k, dict)) # Dikkat: k dict olmalı

        fis.teslim_kayitlari = json.dumps(kayitlar, ensure_ascii=False)
        fis.kalan_adet = fis.toplam_adet - total_teslim_across_all_items


        # Stokları güncelle (Trendyol mantığı: teslimat = stoktan düşüş)
        # Yalnızca o anki teslimat kaydındaki adetleri düşüyoruz
        if toplam_teslim_adet > 0:
            kalemler_list = json.loads(fis.kalemler_json or "[]") # Fis'in genel kalemler listesi

            # Doğru kalemi (model_code ve color eşleşen) bul
            target_kalem = next((k for k in kalemler_list if isinstance(k, dict) and k.get('model_code') == model_code and k.get('color') == color), None)

            if target_kalem:
                barkodlar_dict_kalem = target_kalem.get('barkodlar', {}) # Kalemdeki barkodlar dict'i

                # Her beden için stok düşme
                for size_key, adet in beden_adetleri.items():
                     if adet > 0:
                          try:
                               size_num = size_key.split('_')[1] # beden_35 -> 35
                               barkod = barkodlar_dict_kalem.get(size_num) # Beden numarasına göre barkodu al

                               if barkod:
                                    # Barkoda göre ürünü Product tablosunda bul ve stok düş
                                    product_to_update = Product.query.filter_by(barcode=barkod).first()
                                    if product_to_update:
                                         # Mevcut stoğun None olma durumunu da ele al
                                         current_stock = product_to_update.quantity if product_to_update.quantity is not None else 0
                                         product_to_update.quantity = current_stock - adet # MİKTARI DÜŞ
                                         if product_to_update.quantity < 0: # Stok negatif olmamalı
                                             product_to_update.quantity = 0
                                             print(f"UYARI: Stok düşüşü negatif sonucu verdi. Barkod {barkod}, Mevcut: {current_stock}, Düşülecek: {adet}. Stok 0 yapıldı.")

                                         db.session.add(product_to_update) # Değişikliği session'a ekle
                                         print(f"Stok güncellendi: Barkod {barkod}, Adet {adet} düşüldü. Yeni Stok: {product_to_update.quantity}") # Debug
                                    else:
                                        print(f"UYARI: Barkod {barkod} Product tablosunda bulunamadı. Stok düşülmedi.")
                               else:
                                    print(f"UYARI: '{model_code} - {color}' kaleminde beden {size_num} için barkod bulunamadı.")
                          except Exception as stock_update_e:
                               print(f"HATA: Stok düşme sırasında hata oluştu (Barkod: {barkod}, Adet: {adet}): {stock_update_e}")
                               traceback.print_exc() # Hata detayını logla
                               # Hata oluştuğunda DB commit edilmeyecek (aşağıda rollback var)


        db.session.commit() # Tüm değişiklikleri commit et
        # Başarılı olunca fiş detay sayfasına geri dön
        flash("Teslimat kaydı başarıyla eklendi ve stok güncellendi!", "success")
        return redirect(url_for("siparis_fisi_bp.siparis_fisi_detay", siparis_id=siparis_id))

    except Exception as e:
        # Genel hata durumunda rollback yap
        db.session.rollback()
        print(f"Teslimat kaydı eklerken genel hata: {e}") # Debug için
        traceback.print_exc() # Hata detayını logla
        # Flask'ta flash mesaj sistemi kullanmak iyi olabilir
        flash(f"Teslimat eklenirken bir hata oluştu: {str(e)}", "danger")
        return redirect(url_for("siparis_fisi_bp.siparis_fisi_detay", siparis_id=siparis_id))


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
        # Model koduna göre büyük/küçük harf duyarsız tam eşleşme
        query = query.filter(db.func.lower(Product.product_main_id) == search_query.lower())

    # Ürünleri gruplu çek
    # product_main_id ve color None olabilir, gruplarken bunları da dikkate al.
    # Ayrıca distinct kullanarak aynı model-renk kombinasyonundan birden fazla gelmesini engelle.
    from sqlalchemy import distinct
    urunler = db.session.query(
        distinct(Product.product_main_id).label('title'),
        Product.color
    ).group_by(
        Product.product_main_id,
        Product.color
    ).order_by(
        Product.product_main_id,
        Product.color
    ).all()


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

        def parse_int_or_zero(lst, index):
            """Liste dolu mu, eleman var mı, int dönüştürülebilir mi? Yoksa 0."""
            if not lst or len(lst) <= index: # Index kontrolü önce yapılmalı
                return 0
            val = lst[index]
            if val is None or val == '': # None veya boş string
                return 0
            try:
                return int(val)
            except (ValueError, TypeError):
                return 0

        def parse_float_or_zero(lst, index):
            """Benzer mantıkla float dönüştürülür, yoksa 0.0."""
            if not lst or len(lst) <= index: # Index kontrolü önce yapılmalı
                return 0.0
            val = lst[index]
            if val is None or val == '': # None veya boş string
                 return 0.0
            try:
                # Virgüllü sayıları nokta ile değiştirerek parse et
                if isinstance(val, str):
                     val = val.replace(',', '.')
                return float(val)
            except (ValueError, TypeError):
                return 0.0


        # Bütün satırları gez
        for i in range(len(model_codes)):
            mcode = (model_codes[i] or "").strip()
            clr = (colors[i] or "").strip()
            # En azından model kodu varsa işlemi devam ettir
            if not mcode: # Model kodu boşsa bu satırı atla
                continue

            # Beden adetlerini al
            b35 = parse_int_or_zero(beden_35_list, i)
            b36 = parse_int_or_zero(beden_36_list, i)
            b37 = parse_int_or_zero(beden_37_list, i)
            b38 = parse_int_or_zero(beden_38_list, i)
            b39 = parse_int_or_zero(beden_39_list, i)
            b40 = parse_int_or_zero(beden_40_list, i)
            b41 = parse_int_or_zero(beden_41_list, i)

            satir_toplam_adet = b35 + b36 + b37 + b38 + b39 + b40 + b41

            # Sadece adeti 0'dan büyük olan satırları işleyelim
            if satir_toplam_adet > 0:

                cift_fiyat = parse_float_or_zero(cift_basi_fiyat_list, i)
                satir_toplam_fiyat = satir_toplam_adet * cift_fiyat

                # Model + renk'e ait barkodları çekiyoruz
                # product_main_id ve color None olabilir, query yaparken None değerleri de dahil et
                products_for_barcode = Product.query.filter(
                    Product.product_main_id == mcode if mcode else Product.product_main_id.is_(None),
                    Product.color == clr if clr else Product.color.is_(None)
                ).all()

                barkodlar = {}
                for p in products_for_barcode:
                    # Beden değerlerinin string/sayısal olması durumunu ele alalım
                    if p.size and p.barcode:
                         try:
                             # Bedeni float'a çevirip sonra int'e çevirerek .0 kısmını at
                             size_key = str(int(float(p.size)))
                             barkodlar[size_key] = p.barcode
                         except (ValueError, TypeError):
                              # Eğer beden numerik değilse, olduğu gibi string olarak kaydet
                              barkodlar[str(p.size or '')] = p.barcode # Size None ise boş string kaydet


                # Bu satırı ekle
                kalemler.append({
                    "model_code": mcode,
                    "color": clr,
                    "beden_35": b35,
                    "beden_36": b36,
                    "beden_37": b37,
                    "beden_38": b38,
                    "beden_39": b39, # Beden 39 key ismi düzeltildi
                    "beden_40": b40,
                    "beden_41": b41,
                    "cift_basi_fiyat": cift_fiyat,
                    "satir_toplam_adet": satir_toplam_adet,
                    "satir_toplam_fiyat": satir_toplam_fiyat,
                    "barkodlar": barkodlar # Barkod dict'ini kaydet
                })

                total_adet += satir_toplam_adet
                total_fiyat += satir_toplam_fiyat

        # Eğer hiç geçerli kalem yoksa (adet > 0)
        if not kalemler:
            # Kullanıcı dostu hata mesajı
            flash("Sipariş fişi oluşturmak için en az bir ürün için adet girmelisiniz.", "warning")
            return redirect(url_for("siparis_fisi_bp.siparis_fisi_olustur", search=search_query)) # Arama sorgusunu da geri gönder


        # Tek sipariş fişi oluştur
        yeni_fis = SiparisFisi(
            # Eğer fiş tek bir model-renk için oluşturuluyorsa bu alanlar anlamlı
            # Çoklu modelde sabit değerler kullanılıyordu
            urun_model_kodu=kalemler[0].get("model_code", "Çoklu Model") if len(kalemler) == 1 else "Çoklu Model", # Tek kalem varsa modelini al
            renk=kalemler[0].get("color", "Birden Fazla") if len(kalemler) == 1 else "Birden Fazla", # Tek kalem varsa rengini al
            toplam_adet = total_adet,
            toplam_fiyat = total_fiyat,
            created_date = datetime.now(),
            kalemler_json = json.dumps(kalemler, ensure_ascii=False), # Kalemler listesini JSON olarak kaydet
            # image_url = "/static/logo/gullu.png", # Varsayılan resim yolu, veya ilk ürün görseli çekilebilir
            kalan_adet = total_adet # Başlangıçta kalan adet toplam adete eşit
        )

        # İlk ürünün görselini bulup kaydetme (isteğe bağlı)
        if kalemler:
             ilk_kalem = kalemler[0]
             ilk_kalem_barkodlari = ilk_kalem.get("barkodlar", {})
             # İlk bedenin barkodunu alıp Product tablosundan görselini çekebiliriz
             ilk_beden_barkodu = None
             for size_num in range(35, 42):
                  if ilk_kalem_barkodlari.get(str(size_num)):
                       ilk_beden_barkodu = ilk_kalem_barkodlari.get(str(size_num))
                       break # İlk bulunan bedenin barkodu yeterli

             if ilk_beden_barkodu:
                  ilk_urun_obj = Product.query.filter_by(barcode=ilk_beden_barkodu).first()
                  if ilk_urun_obj and ilk_urun_obj.images:
                       # Ürünün images alanında URL varsa onu kullan
                       yeni_fis.image_url = ilk_urun_obj.images
                  else:
                       # Ürün yoksa veya görsel URL'si yoksa varsayılan görseli kullan
                       yeni_fis.image_url = url_for('static', filename='logo/gullu.png')
             else:
                  # İlk kalemde barkod bilgisi yoksa varsayılan görseli kullan
                  yeni_fis.image_url = url_for('static', filename='logo/gullu.png')


        # Eğer tek kalem varsa, beden adetlerini doğrudan ana fiş kolonlarına da kaydet (eski uyumluluk için)
        # Eğer ana fiş tablosundaki beden kolonları kaldırıldıysa bu kısım silinmeli.
        # Senin modellerinde hala beden_35 vb. kolonlar var, bu yüzden kaydediyoruz.
        if len(kalemler) == 1:
            tek_kalem = kalemler[0]
            yeni_fis.beden_35 = tek_kalem.get("beden_35", 0)
            yeni_fis.beden_36 = tek_kalem.get("beden_36", 0)
            yeni_fis.beden_37 = tek_kalem.get("beden_37", 0)
            yeni_fis.beden_38 = tek_kalem.get("beden_38", 0)
            yeni_fis.beden_39 = tek_kalem.get("beden_39", 0)
            yeni_fis.beden_40 = tek_kalem.get("beden_40", 0)
            yeni_fis.beden_41 = tek_kalem.get("beden_41", 0)
            yeni_fis.cift_basi_fiyat = tek_kalem.get("cift_basi_fiyat", 0.0) # Ana fiş fiyatı tek kalemden alınır

        db.session.add(yeni_fis)
        db.session.commit()

        # Başarılı olunca sipariş fişleri listesine yönlendir
        flash("Sipariş fişi başarıyla oluşturuldu!", "success")
        return redirect(url_for("siparis_fisi_bp.siparis_fisi_sayfasi"))

    else:
        # GET isteği
        # Yılı burada hesaplıyoruz ve template'e gönderiyoruz (Eğer bu template'te yıl kullanılıyorsa)
        current_year = datetime.now().year
        # Arama sorgusunu template'e gönder ki arama kutusu dolu kalsın
        return render_template("siparis_fisi_olustur.html", urunler=urunler, current_year=current_year, search_query=search_query)


# ===========================
# 7) CRUD JSON Endpoint'leri
# ... (Bu rotalar olduğu gibi kalacak) ...
# ===========================
@siparis_fisi_bp.route("/siparis_fisi", methods=["GET"])
def get_siparis_fisi_list():
    fisler = SiparisFisi.query.order_by(SiparisFisi.created_date.desc()).all()
    sonuc = []
    for fis in fisler:
        # Kalemler JSON'unu parse edip özet bilgilerini ekleyelim (isteğe bağlı)
        kalemler_parsed = []
        if fis.kalemler_json:
            try:
                kalemler_parsed = json.loads(fis.kalemler_json)
            except json.JSONDecodeError:
                pass # Hata olursa boş kalır

        sonuc.append({
            "siparis_id": fis.siparis_id,
            "urun_model_kodu": fis.urun_model_kodu,
            "renk": fis.renk,
            # Beden adetlerini ana fiş objesinden alıyoruz (eğer hala kullanılıyorsa)
            "beden_35": fis.beden_35,
            "beden_36": fis.beden_36,
            "beden_37": fis.beden_37,
            "beden_38": fis.beden_38,
            "beden_39": fis.beden_39,
            "beden_40": fis.beden_40,
            "beden_41": fis.beden_41,
            "cift_basi_fiyat": float(fis.cift_basi_fiyat or 0.0),
            "toplam_adet": fis.toplam_adet,
            "toplam_fiyat": float(fis.toplam_fiyat or 0.0),
            "created_date": fis.created_date.strftime("%Y-%m-%d %H:%M:%S") if fis.created_date else None,
            "print_date": fis.print_date.strftime("%Y-%m-%d %H:%M:%S") if fis.print_date else None, # Yazdırma tarihini de ekle
            "image_url": fis.image_url,
            "kalan_adet": fis.kalan_adet,
            "kalemler_ozet": [{"model": k.get("model_code"), "color": k.get("color"), "adet": k.get("satir_toplam_adet")} for k in kalemler_parsed if isinstance(k, dict)] # Kalemlerin kısa özeti
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
        "cift_basi_fiyat": float(fis.cift_basi_fiyat or 0.0),
        "toplam_adet": fis.toplam_adet,
        "toplam_fiyat": float(fis.toplam_fiyat or 0.0),
        "created_date": fis.created_date.strftime("%Y-%m-%d %H:%M:%S") if fis.created_date else None,
        "print_date": fis.print_date.strftime("%Y-%m-%d %H:%M:%S") if fis.print_date else None,
        "image_url": fis.image_url,
        "kalan_adet": fis.kalan_adet,
        "teslim_kayitlari": json.loads(fis.teslim_kayitlari or "[]"), # Teslimatları da ekle
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
    total_teslim_across_all_items = sum(int(k.get("toplam", 0) or 0) for k in kayitlar if isinstance(k, dict))
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
    # Boş fişte 'fis' objesi olmadığı için, template'in 'fis' olmadan çalışması lazım.
    # Maliyet fişi template'ini fis objesi göndermeden render ediyoruz.
    return render_template("maliyet_fisi_print.html", current_year=current_year, now=datetime.now()) # now objesini de gönderelim


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
        now=datetime.now(), # now objesini de gönderelim
        current_year=current_year # Yıl değişkenini template'e gönder
    )


@siparis_fisi_bp.route("/get_product_details/<model_code>")
def get_product_details(model_code):
    # None veya boş string gelirse filtrelemeyi farklı yap
    if not model_code or model_code.lower() == 'none':
         products = Product.query.filter(Product.product_main_id.is_(None) | (Product.product_main_id == '')).all()
    else:
         products = Product.query.filter(db.func.lower(Product.product_main_id) == model_code.lower()).all()


    if not products:
        return jsonify({"success": False, "message": "Ürün bulunamadı"})

    # Modele ait tüm benzersiz renkleri al
    # None veya boş renkleri de gruplamaya dahil et
    colors_query = db.session.query(distinct(Product.color)).filter(
        Product.product_main_id == model_code if model_code else Product.product_main_id.is_(None) | (Product.product_main_id == '')
    ).all()
    colors = [c[0] for c in colors_query if c[0] is not None and c[0] != '']
    # Eğer None veya boş renk varsa, listeye "Renk Bilinmiyor" gibi bir şey ekleyebiliriz
    if db.session.query(Product).filter(
        Product.product_main_id == model_code if model_code else Product.product_main_id.is_(None) | (Product.product_main_id == ''),
        (Product.color.is_(None) | (Product.color == ''))
    ).count() > 0:
        # colors.append("Renk Bilinmiyor") # Placeholder eklemek isteyebilirsin
        pass # Şimdilik sadece dolu renkleri listeliyoruz


    # Renk ve beden-barkod eşleştirmelerini yap
    product_data = {}
    # Her renk için
    for color in colors:
        product_data[color] = {}
        # O model ve renge ait ürünleri çek
        color_products = Product.query.filter(
            Product.product_main_id == model_code if model_code else Product.product_main_id.is_(None) | (Product.product_main_id == ''),
            Product.color == color if color else Product.color.is_(None) | (Product.color == '') # Renk None veya boşsa
        ).all()

        for product in color_products:
            # Beden değerlerinin string/sayısal olması durumunu ele alalım
            if product.size and product.barcode:
                 try:
                     # Bedeni float'a çevirip sonra int'e çevirerek .0 kısmını at
                     size_key = str(int(float(product.size)))
                     barkodlar[size_key] = product.barcode
                 except (ValueError, TypeError):
                      # Eğer beden numerik değilse, olduğu gibi string olarak kaydet
                      barkodlar[str(product.size or '')] = product.barcode # Size None ise boş string kaydet


    # Eğer model-renk eşleşen ama rengi None/boş olan ürünler varsa
    none_color_products = Product.query.filter(
         Product.product_main_id == model_code if model_code else Product.product_main_id.is_(None) | (Product.product_main_id == ''),
         (Product.color.is_(None) | (Product.color == ''))
    ).all()
    if none_color_products:
        product_data["Renk Bilinmiyor"] = {} # Placeholder renk
        for product in none_color_products:
            if product.size and product.barcode:
                 try:
                     size_key = str(int(float(product.size)))
                     product_data["Renk Bilinmiyor"][size_key] = product.barcode
                 except (ValueError, TypeError):
                      product_data["Renk Bilinmiyor"][str(product.size or '')] = product.barcode

    # Renk listesine placeholder rengi ekle (eğer varsa)
    if "Renk Bilinmiyor" in product_data and "Renk Bilinmiyor" not in colors:
         colors.append("Renk Bilinmiyor")


    return jsonify({
        "success": True,
        "colors": colors,
        "product_data": product_data
    })


# =========================================================
#  BARKOD ETİKETİ YAZDIRMA  ➜  A4'e 21 adet (3x7) düzeni
# =========================================================
@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>/barkod_yazdir", methods=["GET"])
def siparis_fisi_barkod_yazdir(siparis_id):
    """
    Belirli bir SiparisFisi'ne ait ürünlerin barkodları için A4'e 21 adet (3x7)
    düzende QR kod etiket çıktısı alınabilecek HTML şablonu döndürür.
    """
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return "Sipariş fişi bulunamadı", 404

    try:
        # kalemler_json string ise parse et, değilse veya boşsa boş liste
        kalemler = json.loads(fis.kalemler_json or "[]") if isinstance(fis.kalemler_json, str) else (fis.kalemler_json if fis.kalemler_json is not None else [])
    except json.JSONDecodeError:
        print(f"Hata: Sipariş fişi {siparis_id} kalemler_json alanı JSON formatında değil.")
        kalemler = []

    barcodes_to_print = []

    # fis.printed_barcodes alanı JSON (list) olmalı. None ise boş liste olarak başlat.
    # Eğer string olarak kaydedilmişse parse et (eski veriler için uyumluluk)
    printed_barcodes_list = []
    if fis.printed_barcodes:
         if isinstance(fis.printed_barcodes, str):
              try:
                   printed_barcodes_list = json.loads(fis.printed_barcodes)
                   if not isinstance(printed_barcodes_list, list):
                       print(f"UYARI: Sipariş fişi {siparis_id} printed_barcodes alanı JSON parse edildi ama liste değil. Boş liste yapılıyor.")
                       printed_barcodes_list = []
              except json.JSONDecodeError:
                   print(f"UYARI: Sipariş fişi {siparis_id} printed_barcodes alanı JSON parse hatası. Boş liste yapılıyor.")
                   printed_barcodes_list = []
         elif isinstance(fis.printed_barcodes, list):
              printed_barcodes_list = fis.printed_barcodes
         else:
              print(f"UYARI: Sipariş fişi {siparis_id} printed_barcodes alanı beklenmedik tipte: {type(fis.printed_barcodes)}. Boş liste yapılıyor.")
              printed_barcodes_list = []

    printed_set = set(printed_barcodes_list)


    for kalem in kalemler:
        if not isinstance(kalem, dict): # Kalem dict formatında olmalı
             continue

        # Model, renk bilgileri
        kalem_model = kalem.get("model_code", "N/A")
        kalem_color = kalem.get("color", "N/A")

        # Bedenlere göre dön
        for size in range(35, 42):
            size_str = str(size)
            # Miktar ve barkod bilgisi al (güvenli erişim)
            quantity = int(kalem.get(f"beden_{size_str}", 0) or 0) # Miktar 0 veya None/boş ise 0
            barkodlar_dict = kalem.get("barkodlar", {}) # Barkod dict'ini al, None ise boş dict

            # Barkod dict'inde beden barkodu var mı kontrol et
            if isinstance(barkodlar_dict, dict):
                 barcode = barkodlar_dict.get(size_str) # Barkod dict'inden beden barkodunu al
            else:
                 barcode = None # barkodlar alanı dict değilse barkod yok sayılır
                 print(f"UYARI: Sipariş fişi {fis.siparis_id}, Kalem {kalem_model}-{kalem_color} için 'barkodlar' alanı dict değil: {barkodlar_dict}. Barkodlar alınamadı.")


            # Sadece adet > 0 VE barkod mevcutsa işleme al
            if quantity > 0 and barcode:
                barcodes_to_print.append({
                    "barcode"      : barcode,
                    "model"        : kalem_model,
                    "color"        : kalem_color,
                    "size"         : size_str, # Beden string olarak kalsın
                    "qr_image_path": generate_and_save_qr_code(barcode), # QR kodu üret/getir
                    "print_count"  : quantity, # Bu bedenden kaç adet
                    "is_printed"   : barcode in printed_set   # Daha önce basıldı mı?
                })

    return render_template(
        "siparis_fisi_barkod_print.html",
        barcodes=barcodes_to_print, # Şablona barkod listesini gönder
        siparis_id=siparis_id # Şablona sipariş ID'sini gönder
    )

# =========================================================
#  YAZDIRMA DURUMUNU GÜNCELLE
# =========================================================
@siparis_fisi_bp.route("/mark_as_printed", methods=["POST"])
def mark_as_printed():
    data = request.get_json(force=True) or {}
    siparis_id = data.get("siparis_id")
    barcodes   = data.get("barcodes", []) # Gelen barkodlar listesi

    if not siparis_id:
        return jsonify(success=False, message="Sipariş ID'si eksik"), 400

    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify(success=False, message="Fiş bulunamadı"), 404

    # fis.printed_barcodes alanı JSON (list) olmalı.
    # Eğer None, string veya farklı tipteyse güvenli bir şekilde listeye çevir.
    printed_barcodes_list = []
    if fis.printed_barcodes:
         if isinstance(fis.printed_barcodes, str):
              try:
                   printed_barcodes_list = json.loads(fis.printed_barcodes)
                   if not isinstance(printed_barcodes_list, list): # Parse edildi ama liste değilse
                       print(f"UYARI: Sipariş fişi {siparis_id} printed_barcodes alanı JSON parse edildi ama liste değil. Boş liste yapılıyor.")
                       printed_barcodes_list = []
              except json.JSONDecodeError:
                   print(f"UYARI: Sipariş fişi {siparis_id} printed_barcodes alanı JSON parse hatası. Boş liste yapılıyor.")
                   printed_barcodes_list = []
         elif isinstance(fis.printed_barcodes, list):
              printed_barcodes_list = fis.printed_barcodes
         else:
              print(f"UYARI: Sipariş fişi {siparis_id} printed_barcodes alanı beklenmedik tipte: {type(fis.printed_barcodes)}. Boş liste yapılıyor.")
              printed_barcodes_list = []

    # Gelen barkodları mevcut printed_barcodes listesine ekle (sadece yeni olanları)
    new_ones = []
    # Gelen data 'barcodes' anahtarıyla bir liste olmalı
    if isinstance(barcodes, list):
         for bc in barcodes:
              # Sadece geçerli string barkodları ve daha önce eklenmemiş olanları ekle
              if isinstance(bc, str) and bc not in printed_barcodes_list:
                   printed_barcodes_list.append(bc)
                   new_ones.append(bc)

    if new_ones:
        # Güncellenmiş listeyi tekrar JSON string olarak kaydet
        fis.printed_barcodes = json.dumps(printed_barcodes_list, ensure_ascii=False)
        db.session.commit()
        print(f"Sipariş fişi {siparis_id} için {len(new_ones)} adet barkod 'basıldı' olarak işaretlendi.")
        return jsonify(success=True, added=new_ones), 200
    else:
        print(f"Sipariş fişi {siparis_id} için basılacak yeni barkod yok.")
        return jsonify(success=True, added=[]), 200 # Başarılı ama eklenecek yeni yok


# ... (Geri kalan siparis_fisi.py kodları) ...