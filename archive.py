import os
import json
import traceback
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify
from models import db, Archive, Product
# Çok tablolu sipariş modelleri
from models import OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled
# update_service ve trendyol_api importları
from trendyol_api import SUPPLIER_ID
from update_service import update_order_status_to_picking

archive_bp = Blueprint('archive', __name__)


# ✅ Yeni Jinja Filtresi: Türkçe Ay Adları ile Tarih Formatlama
@archive_bp.app_template_filter('format_turkish_date')
def format_turkish_date_filter(value):
    """
    Datetime objesini Türkçe ay adıyla "Gün Ay" formatına çevirir.
    Örnek: 2023-10-27 -> "27 Ekim"
    """
    if not value:
        return ""
    try:
        turkish_months = [
            "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
            "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"
        ]
        # value string gelirse DateTime'a çevir (opsiyonel)
        if isinstance(value, str):
            # ISO veya "YYYY-MM-DD HH:MM:SS" vb. gelirse deneyelim
            try:
                value = datetime.fromisoformat(value)
            except Exception:
                pass

        day = getattr(value, "day", None)
        month_index = getattr(value, "month", None)
        if not day or not month_index:
            return str(value)

        return f"{day} {turkish_months[month_index]}"
    except Exception as e:
        print(f"Tarih formatlama hatası: {e}")
        return str(value)


#############################
# 1) Yardımcı Fonksiyonlar
#############################
def find_order_across_tables(order_number):
    """
    Siparişi 6 tabloda arar: Created, Picking, Shipped, Delivered, Cancelled, WooOrders
    Bulursa (obj, tablo_sinifi), bulamazsa (None, None)
    """
    from woocommerce_site.models import WooOrder
    
    # Önce Trendyol tablolarına bak
    for cls in [OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled]:
        found = cls.query.filter_by(order_number=order_number).first()
        if found:
            return found, cls
    
    # WooCommerce tablosuna bak
    found = WooOrder.query.filter_by(order_number=str(order_number)).first()
    if found:
        return found, WooOrder
    
    return None, None

# ✅ Yeni Yardımcı Fonksiyon: Arşivde Geçen Süreyi Hesapla
def compute_archived_duration(archive_date):
    """
    Arşiv tarihinden itibaren geçen süreyi (gün, saat, dakika) string olarak döndürür.
    """
    if not archive_date:
        return "Süre Hesaplanamıyor"
    try:
        now = datetime.now()
        diff = now - archive_date # Geçen süre olduğu için now - archive_date
        if diff.total_seconds() < 0:
            return "Henüz Arşivlenmedi" # Gelecekteki bir tarihse

        total_minutes = int(diff.total_seconds() // 60)
        if total_minutes < 60:
            return f"{total_minutes} dakika"

        total_hours = total_minutes // 60
        minutes = total_minutes % 60
        if total_hours < 24:
            return f"{total_hours} saat {minutes} dakika"

        days = total_hours // 24
        hours = total_hours % 24

        return f"{days} gün {hours} saat {minutes} dakika"
    except Exception as e:
        print(f"Arşiv süresi hesaplama hatası: {e}")
        return "Süre Hesaplanamıyor"


# compute_time_left fonksiyonu artık kullanılmıyor, yerine compute_archived_duration var.
# İsterseniz silebilirsiniz veya başka yerlerde kullanıyorsanız bırakabilirsiniz.
# def compute_time_left(delivery_date):
#     """
#     Kalan teslim süresini (gün saat dakika) string olarak döndürür.
#     """
#     if not delivery_date:
#         return "Kalan Süre Yok"
#     try:
#         now = datetime.now()
#         diff = delivery_date - now
#         if diff.total_seconds() <= 0:
#             return "0 dakika"
#         days, seconds = divmod(diff.total_seconds(), 86400)
#         hours, seconds = divmod(seconds, 3600)
#         minutes = int(seconds // 60)
#         return f"{int(days)} gün {int(hours)} saat {minutes} dakika"
#     except Exception as e:
#         print(f"Zaman hesaplama hatası: {e}")
#         return "Kalan Süre Yok"


def fetch_product_image(barcode):
    """
    'static/images' klasöründe barkod.jpg vb. arar, yoksa default döndürür.
    """
    images_dir = os.path.join('static', 'images')
    # Güvenlik: Path traversal önlemi
    if not os.path.isdir(images_dir):
        print(f"Hata: Resim klasörü bulunamadı: {images_dir}")
        return "/static/images/default.jpg"

    # İzin verilen uzantılar
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif']

    # Klasördeki tüm dosyaları kontrol et
    for filename in os.listdir(images_dir):
        name, ext = os.path.splitext(filename)
        if name == barcode and ext.lower() in allowed_extensions:
            return f"/static/images/{filename}"

    # Bulunamazsa default döndür
    return "/static/images/default.jpg"


# ✅ Yeni Jinja Filtresi: Türkçe Ay Adları ile Tarih Formatlama
# Bu fonksiyonu Flask uygulamanızın ana dosyasında (genellikle app.py veya run.py)
# Jinja environment'ına filtre olarak eklemeniz GEREKİR.
# Örnek kullanım: app.jinja_env.filters['format_turkish_date'] = format_turkish_date_filter
def format_turkish_date_filter(value):
    """
    Datetime objesini Türkçe ay adıyla "Gün Ay Yıl" formatına çevirir.
    Örnek: 2023-10-27 -> "27 Ekim 2023"
    """
    if not value:
        return ""
    try:
        # Ay adlarını Türkçe olarak tanımla
        turkish_months = [
            "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
            "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"
        ]
        # Datetime objesinden gün, ay ve yıl al
        day = value.day
        month_index = value.month
        year = value.year

        # Türkçe ay adını al
        turkish_month_name = turkish_months[month_index]

        # İstenen formatta string oluştur
        # Yılı istemediğin için "Gün Ay" formatı:
        return f"{day} {turkish_month_name}"
    except Exception as e:
        print(f"Tarih formatlama hatası: {e}")
        return str(value) # Hata olursa orijinal değeri döndür


#############################
# 2) Sipariş Statüsü Güncelleme
#############################
@archive_bp.route('/update_order_status', methods=['POST'])
def change_order_status():
    """
    Bir siparişin statüsünü güncelle.
    Eğer çok tablolu modelde sipariş Created/Picking/Shipped/... tablolarından birindeyse orada bulup statüsünü set etmek demek,
    ama gerçekte tablolar arası taşınması gerek.
    Basitçe "status" alanı varsa tablo içinde set ediyoruz demek.
    (Örneğin tabloyu tek kolonla güncellemek isterseniz).
    """
    order_number = request.form.get('order_number')
    new_status = request.form.get('status')
    print(f"Gelen order_number: {order_number}, status: {new_status}")

    # 1) Archive tablosunda mı?
    archived_order = Archive.query.filter_by(order_number=order_number).first()
    if archived_order:
        archived_order.status = new_status
        try:
            db.session.commit()
            print(f"Arşivlenmiş sipariş {order_number} durumu {new_status} olarak güncellendi.")
            return jsonify({'success': True, 'message': 'Durum güncellendi.'})
        except Exception as e:
            db.session.rollback()
            print(f"Arşiv statü güncelleme DB hatası: {e}")
            return jsonify({'success': False, 'message': 'Veritabanı hatası oluştu.'})


    # 2) Yoksa çok tablodan birinde mi?
    order_obj, table_cls = find_order_across_tables(order_number)
    if not order_obj:
        print("Sipariş bulunamadı.")
        return jsonify({'success': False, 'message': 'Sipariş bulunamadı.'})

    # Sadece tablo içindeki 'status' alanını güncelliyorsunuz
    # (NOT: gerçekte tabloyu taşımanız gerekebilir)
    order_obj.status = new_status
    try:
        db.session.commit()
        print(f"{table_cls.__tablename__} içindeki sipariş {order_number} statü {new_status} olarak güncellendi.")
        return jsonify({'success': True, 'message': 'Durum güncellendi.'})
    except Exception as e:
        db.session.rollback()
        print(f"Ana tablo statü güncelleme DB hatası: {e}")
        return jsonify({'success': False, 'message': 'Veritabanı hatası oluştu.'})


#############################
# 3) Siparişi İşleme Al (Arşiv -> "Picking")
#############################
@archive_bp.route('/process_order', methods=['POST'])
def execute_order_processing():
    """
    Arşivdeki siparişi 'Picking' statüsüne geçirmek için:
    1) Trendyol API'ye -> "Picking" update
    2) Arşiv kaydını sil, 'OrderPicking' tablosuna ekle
    """
    order_number = request.form.get('order_number')
    print(f"Gelen order_number: {order_number} işlem için.")

    archived_order = Archive.query.filter_by(order_number=order_number).first()
    if not archived_order:
        return jsonify({'success': False, 'message': 'Sipariş arşivde bulunamadı.'})

    print(f"Sipariş {order_number} arşivde bulundu, 'Picking' yapılacak.")
    # Trendyol update
    # details alanının string veya liste/dict olabileceği durumu için kontrol
    details = archived_order.details
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except json.JSONDecodeError:
            print(f"Hata: Sipariş {order_number} detayları JSON formatında değil.")
            return jsonify({'success': False, 'message': 'Sipariş detayları geçersiz formatta.'})
    elif not isinstance(details, (list, dict)):
        print(f"Hata: Sipariş {order_number} detayları beklenmedik tipte: {type(details)}")
        return jsonify({'success': False, 'message': 'Sipariş detayları geçersiz tipte.'})


    lines = []
    # Eğer details bir liste ise (ürün listesi)
    if isinstance(details, list):
        for d in details:
            line_id = d.get('line_id')
            if line_id is None: # line_id 0 da olabilir, None kontrolü daha doğru
                print(f"Hata: Sipariş {order_number} detaylarında 'line_id' değeri eksik.")
                return jsonify({'success': False, 'message': 'Ürün detaylarında line_id eksik.'})
            try:
                qty = int(d.get('quantity', 1))
                lines.append({"lineId": int(line_id), "quantity": qty})
            except (ValueError, TypeError):
                print(f"Hata: Sipariş {order_number} detaylarında 'quantity' değeri geçersiz.")
                return jsonify({'success': False, 'message': 'Ürün detaylarında miktar değeri geçersiz.'})
    # Eğer details tek bir ürün dict'i ise (veya beklenmedik format)
    elif isinstance(details, dict):
        # Trendyol API genellikle line_id listesi bekler, bu durum için logic eklemeniz gerekebilir
        print(f"Uyarı: Sipariş {order_number} detayları liste değil, dict formatında. Trendyol API isteği için uygun olmayabilir.")
        # Tek ürün dict'i için örnek bir line ekleme (gerçek API'ye göre düzenlenmeli)
        line_id = details.get('line_id')
        if line_id is not None:
            try:
                qty = int(details.get('quantity', 1))
                lines.append({"lineId": int(line_id), "quantity": qty})
            except (ValueError, TypeError):
                print(f"Hata: Sipariş {order_number} detaylarında 'quantity' değeri geçersiz.")
                return jsonify({'success': False, 'message': 'Ürün detaylarında miktar değeri geçersiz.'})
    else:
        print(f"Hata: Sipariş {order_number} detayları boş veya tanımsız.")
        return jsonify({'success': False, 'message': 'Sipariş detayları boş veya tanımsız.'})


    if not lines:
        print(f"Hata: Sipariş {order_number} için Trendyol API'ye gönderilecek ürün satırı bulunamadı.")
        return jsonify({'success': False, 'message': 'Trendyol API için ürün satırı bilgisi eksik.'})


    # shipment_package_id veya package_number kullanımı
    shipment_package_id = archived_order.shipment_package_id
    if shipment_package_id is None: # shipment_package_id yoksa package_number'ı dene
        shipment_package_id = archived_order.package_number
        if shipment_package_id is None:
            print(f"Hata: Sipariş {order_number} için shipment_package_id veya package_number bulunamadı.")
            return jsonify({'success': False, 'message': 'Paket kimliği bilgisi eksik.'})

    try:
        # Trendyol API update çağrısı
        supplier_id = SUPPLIER_ID
        print(f"Trendyol API'ye Picking update gönderiliyor: supplier_id={supplier_id}, shipment_package_id={shipment_package_id}, lines={lines}")
        result = update_order_status_to_picking(supplier_id, shipment_package_id, lines)

        if not result or not result.get('success'): # API'den success: True gelmeli
            api_error_message = result.get('message', 'Trendyol API bilinmeyen hata.') if result else 'Trendyol API isteği başarısız oldu.'
            print(f"Trendyol API Picking update başarısız: {api_error_message}")
            return jsonify({'success': False, 'message': f'Trendyol API hatası: {api_error_message}'})

    except Exception as e:
        print(f"Trendyol API Picking update sırasında hata: {e}")
        traceback.print_exc() # Hata detayını logla
        return jsonify({'success': False, 'message': f'Trendyol API çağrısı sırasında hata: {e}'})


    # Trendyol update başarılı -> arşivdeki kaydı "Picking" tablosuna taşıyalım
    from models import OrderPicking # picking tablosunu import

    # Yeni OrderPicking objesi oluştur
    new_picking = OrderPicking(
        order_number=archived_order.order_number,
        status='Picking', # Trendyol'a Picking gönderdiğimiz için burada da Picking yapıyoruz
        order_date=archived_order.order_date,
        details=archived_order.details, # JSON/Dict formatında saklandığını varsayalım
        shipment_package_id=archived_order.shipment_package_id,
        package_number=archived_order.package_number,
        shipping_barcode=archived_order.shipping_barcode,
        cargo_provider_name=archived_order.cargo_provider_name,
        customer_name=archived_order.customer_name,
        customer_surname=archived_order.customer_surname,
        customer_address=archived_order.customer_address,
        agreed_delivery_date=archived_order.agreed_delivery_date,
        # Eksik kolonları da ekleyin (örneğin: total_amount, currency, etc.)
    )

    try:
        db.session.add(new_picking)
        db.session.delete(archived_order)
        db.session.commit()
        print(f"Sipariş {order_number} 'Picking' tablosuna taşındı (arşivden çıkarıldı).")
        return jsonify({'success': True, 'message': 'Sipariş başarıyla işleme alındı.'})
    except Exception as e:
        db.session.rollback()
        print(f"Arşivden Picking'e taşıma DB hatası: {e}")
        traceback.print_exc() # Hata detayını logla
        return jsonify({'success': False, 'message': 'Veritabanı hatası: Sipariş taşınamadı.'})


#############################
# 4) Siparişi İptal Et
#############################
@archive_bp.route('/cancel_order', methods=['POST'])
def order_cancellation():
    """
    Siparişi bul (ya arşivde ya da 5 tablodan birinde) -> statüsünü "İptal Edildi" yap
    (Tabloda tutacaksanız 'OrderCancelled' tablosuna taşımanız da gerekebilir.)
    """
    order_number = request.form.get('order_number')
    print(f"Gelen iptal isteği için order_number: {order_number}")

    # 1) Arşivde mi?
    archived_order = Archive.query.filter_by(order_number=order_number).first()
    if archived_order:
        archived_order.status = 'İptal Edildi'
        try:
            db.session.commit()
            print(f"Arşivdeki sipariş {order_number} 'İptal Edildi' statüsüne alındı.")
            return jsonify({'success': True, 'message': 'Sipariş iptal edildi.'})
        except Exception as e:
            db.session.rollback()
            print(f"Arşiv iptal DB hatası: {e}")
            return jsonify({'success': False, 'message': 'Veritabanı hatası oluştu.'})


    # 2) Yoksa çok tablodan birinde
    order_obj, table_cls = find_order_across_tables(order_number)
    if not order_obj:
        print("Sipariş hem ana listede hem de arşivde bulunamadı.")
        return jsonify({'success': False, 'message': 'Sipariş bulunamadı.'})

    # Basitçe 'status' kolonu set ediyorsanız
    order_obj.status = 'İptal Edildi'
    try:
        db.session.commit()
        print(f"{table_cls.__tablename__} içindeki sipariş {order_number} iptal edildi.")
        # İptal edilen siparişi OrderCancelled tablosuna taşımak isterseniz buraya ekleyin
        # from models import OrderCancelled
        # new_cancelled = OrderCancelled(...)
        # db.session.add(new_cancelled)
        # db.session.delete(order_obj)
        # db.session.commit() # Tekrar commit etmeniz gerekebilir
        return jsonify({'success': True, 'message': 'Sipariş iptal edildi.'})
    except Exception as e:
        db.session.rollback()
        print(f"Ana tablo iptal DB hatası: {e}")
        return jsonify({'success': False, 'message': 'Veritabanı hatası oluştu.'})


#############################
# 5) Arşiv Görünümü
#############################
@archive_bp.route('/archive')
def display_archive():
    """
    Arşiv tablosundaki siparişleri listeler (sayfalı).
    """
    page = request.args.get('page', 1, type=int)
    per_page = 20

    try:
        pagination = Archive.query.order_by(Archive.archive_date.desc()).paginate( # order_date yerine archive_date ile sırala
            page=page, per_page=per_page, error_out=False)
        orders_to_show = pagination.items
        total_archived_orders_count = pagination.total
        total_pages = pagination.pages

    except Exception as e:
        print(f"Arşiv sorgulama hatası: {e}")
        traceback.print_exc()
        # Hata durumunda boş liste ve 0 toplam/sayfa döndür
        orders_to_show = []
        total_archived_orders_count = 0
        total_pages = 0
        # Frontend'e hata mesajı göndermek için flash kullanılabilir veya template'e hata flag'i gönderilebilir


    # Ürün dictionary (barkod -> product) - Sadece arşivdeki ürünler için çekmek daha verimli olabilir
    # Ancak şu anki yapı tüm ürünleri çekiyor, bu da çalışır.
    products_list = Product.query.all()
    products_dict = {p.barcode: p for p in products_list}

    for order in orders_to_show:
        # ✅ Düzeltme: Arşivde Geçen Süre
        order.archived_duration_string = compute_archived_duration(order.archive_date)

        # Kalan süre (bu artık kullanılmıyor ama obje üzerinde durabilir)
        # order.remaining_time = compute_time_left(order.agreed_delivery_date)
        # order.remaining_time_in_hours = ... # Bu da artık kullanılmıyor


        # Detay parse ve Ürünler listesi oluşturma
        details_json = order.details or '[]'
        if isinstance(details_json, str):
            try:
                details_list = json.loads(details_json)
            except json.JSONDecodeError:
                print(f"Hata: Sipariş {order.order_number} detayları JSON formatında değil.")
                details_list = []
        else:
            # Eğer details zaten liste/dict ise doğrudan kullan
            details_list = details_json if isinstance(details_json, list) else [details_json] if isinstance(details_json, dict) else []


        products = []
        for detail in details_list:
            product_barcode = detail.get('barcode', '')
            # product_info = products_dict.get(product_barcode) # Ürün detaylarını Product tablosundan çekiyorsanız kullanın

            # Detay objesinden SKU, Model, Renk, Beden gibi bilgileri al
            # Eğer details JSON'unuz bu alanları içeriyorsa buradan alabilirsiniz.
            sku = detail.get('sku', 'Bilinmeyen SKU')
            model = detail.get('model', 'Model Bilgisi Yok')
            color = detail.get('color', 'Renk Bilgisi Yok')
            size = detail.get('size', 'Beden Bilgisi Yok')
            # Görsel URL'si Trendyol detaylarında varsa onu kullan, yoksa fetch_product_image ile yerel dosyayı dene
            image_url = detail.get('imageUrl') # Trendyol API'den geliyorsa
            if not image_url: # Trendyol'dan gelmiyorsa veya boşsa yerel dosyayı dene
                image_url = fetch_product_image(product_barcode)


            products.append({
                'sku': sku,
                'barcode': product_barcode,
                'model': model, # Frontend'de kullanmak için ekledik
                'color': color, # Frontend'de kullanmak için ekledik
                'size': size,  # Frontend'de kullanmak için ekledik
                'image_url': image_url
            })
        order.products = products

    return render_template(
        'archive.html',
        orders=orders_to_show,
        page=page,
        total_pages=total_pages,
        total_archived_orders_count=total_archived_orders_count
    )

#############################
# 6) Sipariş Arşivleme
#############################
@archive_bp.route('/archive_order', methods=['POST'])
def archive_an_order():
    """
    Çok tablolu modelde, siparişi bul -> arşive ekle -> o tablodan sil.
    WooCommerce siparişleri için özel işlem yapılır.
    """
    order_number = request.form.get('order_number')
    archive_reason = request.form.get('archive_reason')
    print(f"Sipariş arşivleniyor: {order_number}, neden: {archive_reason}")

    # Siparişi 6 tablodan birinde ara (Trendyol + WooCommerce)
    order_obj, table_cls = find_order_across_tables(order_number)
    if not order_obj:
        return jsonify({'success': False, 'message': 'Sipariş bulunamadı.'})

    # WooCommerce siparişi mi kontrol et
    from woocommerce_site.models import WooOrder
    is_woo_order = table_cls == WooOrder
    
    if is_woo_order:
        # WooCommerce siparişi için özel alan eşleştirmesi
        # Adres birleştir
        address_parts = [
            order_obj.shipping_address_1 or order_obj.billing_address_1,
            order_obj.shipping_address_2 or order_obj.billing_address_2,
            order_obj.shipping_city or order_obj.billing_city,
            order_obj.shipping_state or order_obj.billing_state,
            order_obj.shipping_postcode or order_obj.billing_postcode,
        ]
        full_address = ' '.join([p for p in address_parts if p])
        
        # Details JSON oluştur
        import json
        details_list = []
        for item in order_obj.line_items or []:
            details_list.append({
                'woo_product_id': item.get('product_id'),
                'woo_variation_id': item.get('variation_id'),
                'quantity': item.get('quantity', 1),
                'price': item.get('price', 0),
                'product_name': item.get('name', ''),
                'sku': item.get('sku', '')
            })
        
        new_archive = Archive(
            order_number=order_obj.order_number,
            status=order_obj.status,
            order_date=order_obj.date_created,
            details=json.dumps(details_list, ensure_ascii=False),
            shipment_package_id=None,
            package_number=order_obj.order_number,
            shipping_barcode=None,
            cargo_provider_name='MNG',
            customer_name=order_obj.customer_first_name or '',
            customer_surname=order_obj.customer_last_name or '',
            customer_address=full_address,
            agreed_delivery_date=None,
            archive_reason=archive_reason,
            archive_date=datetime.now(),
            source='woocommerce'
        )
    else:
        # Trendyol siparişi - standart alan eşleştirmesi
        new_archive = Archive(
            order_number=order_obj.order_number,
            status=order_obj.status,
            order_date=order_obj.order_date,
            details=order_obj.details,
            shipment_package_id=getattr(order_obj, 'shipment_package_id', None),
            package_number=getattr(order_obj, 'package_number', None),
            shipping_barcode=getattr(order_obj, 'shipping_barcode', None),
            cargo_provider_name=getattr(order_obj, 'cargo_provider_name', None),
            customer_name=getattr(order_obj, 'customer_name', None),
            customer_surname=getattr(order_obj, 'customer_surname', None),
            customer_address=getattr(order_obj, 'customer_address', None),
            agreed_delivery_date=getattr(order_obj, 'agreed_delivery_date', None),
            archive_reason=archive_reason,
            archive_date=datetime.now(),
            source='trendyol'
        )
    
    try:
        db.session.add(new_archive)
        db.session.delete(order_obj)
        db.session.commit()
        
        table_name = 'woo_orders' if is_woo_order else table_cls.__tablename__
        print(f"Sipariş {order_number}, {table_name} tablosundan silindi, arşive eklendi.")
        return jsonify({'success': True, 'message': 'Sipariş arşive eklendi.'})
    except Exception as e:
        db.session.rollback()
        print(f"Arşivleme DB hatası: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Arşivleme sırasında veritabanı hatası oluştu.'})


#############################
# 7) Arşivden Geri Yükleme
#############################
@archive_bp.route('/restore_from_archive', methods=['POST'])
def recover_from_archive():
    """
    Arşivdeki siparişi orijinal tablosuna geri taşır:
    - WooCommerce siparişleri -> woo_orders tablosuna
    - Trendyol siparişleri -> orders_created tablosuna
    """
    order_number = request.form.get('order_number')
    print(f"Arşivden geri yükleniyor: {order_number}")

    archived_order = Archive.query.filter_by(order_number=order_number).first()
    if not archived_order:
        return jsonify({'success': False, 'message': 'Sipariş arşivde bulunamadı.'})

    # 🔥 Sipariş kaynağını kontrol et
    # Önce source alanını kontrol et (varsa)
    if hasattr(archived_order, 'source') and archived_order.source:
        is_woocommerce = (archived_order.source == 'woocommerce')
    else:
        # Eski kayıtlar için fallback: sipariş numarasına bak
        # WooCommerce sipariş numaraları genellikle 5 haneli (49787, 49797)
        # Trendyol sipariş numaraları 11 haneli (10725318633)
        order_num_str = str(order_number)
        is_woocommerce = len(order_num_str) <= 6 and order_num_str.isdigit() and '-' not in order_num_str
    
    try:
        if is_woocommerce:
            # 🛒 WooCommerce siparişini woo_orders tablosuna geri yükle
            from woocommerce_site.models import WooOrder
            
            # Details JSON'dan line_items'ı parse et
            details_json = archived_order.details or '[]'
            if isinstance(details_json, str):
                try:
                    details_list = json.loads(details_json)
                except json.JSONDecodeError:
                    details_list = []
            else:
                details_list = details_json if isinstance(details_json, list) else []
            
            # WooOrder formatına çevir
            line_items = []
            for item in details_list:
                line_items.append({
                    'product_id': item.get('woo_product_id'),
                    'variation_id': item.get('woo_variation_id'),
                    'quantity': item.get('quantity', 1),
                    'price': item.get('price', 0),
                    'total': item.get('line_total_price', 0),
                    'name': item.get('product_name', ''),
                    'sku': item.get('sku', '')
                })
            
            # Adres bilgisini parse et
            address = archived_order.customer_address or ''
            
            # WooOrder objesi oluştur
            restored_order = WooOrder()
            # order_id için integer overflow kontrolü
            try:
                order_id_int = int(archived_order.order_number)
                # PostgreSQL Integer max: 2147483647
                if order_id_int <= 2147483647:
                    restored_order.order_id = order_id_int
                else:
                    # Çok büyük sayı, NULL bırak
                    restored_order.order_id = None
                    print(f"⚠️  order_id çok büyük ({order_id_int}), NULL olarak ayarlandı")
            except ValueError:
                restored_order.order_id = None
            
            restored_order.order_number = archived_order.order_number
            restored_order.status = 'on-hold'  # Geri yüklenince tekrar sipariş hazırla ekranına düşsün
            restored_order.date_created = archived_order.order_date
            restored_order.customer_first_name = archived_order.customer_name
            restored_order.customer_last_name = archived_order.customer_surname
            restored_order.total = 0.0  # Arşivde bu bilgi yok
            restored_order.currency = 'TRY'
            restored_order.line_items = line_items
            restored_order.shipping_address_1 = address[:255] if address else None
            restored_order.billing_address_1 = address[:255] if address else None
            
            print(f"WooCommerce siparişi {order_number} woo_orders tablosuna geri yükleniyor.")
        else:
            # 📦 Trendyol siparişini orders_created tablosuna geri yükle
            from models import OrderCreated
            
            restored_order = OrderCreated()
            restored_order.order_number = archived_order.order_number
            restored_order.status = 'Created'  # Geri yüklenince 'Created' statüsüne alıyoruz
            restored_order.order_date = archived_order.order_date
            restored_order.details = archived_order.details
            restored_order.shipment_package_id = archived_order.shipment_package_id
            restored_order.package_number = archived_order.package_number
            restored_order.shipping_barcode = archived_order.shipping_barcode
            restored_order.cargo_provider_name = archived_order.cargo_provider_name
            restored_order.customer_name = archived_order.customer_name
            restored_order.customer_surname = archived_order.customer_surname
            restored_order.customer_address = archived_order.customer_address
            restored_order.agreed_delivery_date = archived_order.agreed_delivery_date
            
            # Ek alanlar (Archive'de varsa)
            if hasattr(archived_order, 'merchant_sku'):
                restored_order.merchant_sku = archived_order.merchant_sku
            if hasattr(archived_order, 'product_barcode'):
                restored_order.product_barcode = archived_order.product_barcode
            if hasattr(archived_order, 'product_name'):
                restored_order.product_name = archived_order.product_name
            if hasattr(archived_order, 'product_code'):
                restored_order.product_code = archived_order.product_code
            if hasattr(archived_order, 'product_size'):
                restored_order.product_size = archived_order.product_size
            if hasattr(archived_order, 'product_color'):
                restored_order.product_color = archived_order.product_color
            if hasattr(archived_order, 'amount'):
                restored_order.amount = archived_order.amount
            if hasattr(archived_order, 'discount'):
                restored_order.discount = archived_order.discount
            if hasattr(archived_order, 'currency_code'):
                restored_order.currency_code = archived_order.currency_code
            if hasattr(archived_order, 'line_id'):
                restored_order.line_id = archived_order.line_id
            if hasattr(archived_order, 'images'):
                restored_order.images = archived_order.images
            if hasattr(archived_order, 'estimated_delivery_start'):
                restored_order.estimated_delivery_start = archived_order.estimated_delivery_start
            if hasattr(archived_order, 'estimated_delivery_end'):
                restored_order.estimated_delivery_end = archived_order.estimated_delivery_end
            if hasattr(archived_order, 'cargo_tracking_link'):
                restored_order.cargo_tracking_link = archived_order.cargo_tracking_link
            if hasattr(archived_order, 'product_main_id'):
                restored_order.product_main_id = archived_order.product_main_id
            if hasattr(archived_order, 'product_model_code'):
                restored_order.product_model_code = archived_order.product_model_code
            if hasattr(archived_order, 'stockCode'):
                restored_order.stockCode = archived_order.stockCode
            if hasattr(archived_order, 'vat_base_amount'):
                restored_order.vat_base_amount = archived_order.vat_base_amount
            if hasattr(archived_order, 'origin_shipment_date'):
                restored_order.origin_shipment_date = archived_order.origin_shipment_date
            
            restored_order.source = 'TRENDYOL'
            
            print(f"Trendyol siparişi {order_number} orders_created tablosuna geri yükleniyor.")
        
        db.session.add(restored_order)
        db.session.delete(archived_order)
        db.session.commit()
        
        table_name = 'woo_orders' if is_woocommerce else 'orders_created'
        print(f"Sipariş {order_number} arşivden çıkartıldı, '{table_name}' tablosuna eklendi.")
        return jsonify({'success': True, 'message': 'Sipariş başarıyla geri yüklendi.'})
        
    except Exception as e:
        db.session.rollback()
        print(f"Arşivden geri yükleme DB hatası: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Arşivden geri yükleme hatası: {str(e)}'})


#############################
# 8) Arşivden Silme
#############################
@archive_bp.route('/delete_archived_order', methods=['POST'])
def remove_archived_order():
    """
    Arşivdeki siparişi kalıcı olarak silmek.
    """
    # Hem tekil hem de çoklu silme için 'order_numbers[]' veya 'order_number' alabiliriz
    order_numbers = request.form.getlist('order_numbers[]')
    if not order_numbers: # Liste boşsa tekil order_number'ı dene
        order_number = request.form.get('order_number')
        if order_number:
            order_numbers = [order_number]
        else:
            print("Silinecek sipariş numarası/numaraları alınamadı.")
            return jsonify({'success': False, 'message': 'Silinecek sipariş seçilmedi.'})

    deleted_count = 0
    try:
        for onum in order_numbers:
            print(f"Arşivden siliniyor: {onum}")
            archived_order = Archive.query.filter_by(order_number=onum).first()
            if archived_order:
                db.session.delete(archived_order)
                deleted_count += 1
            else:
                print(f"Uyarı: {onum} numaralı sipariş arşivde bulunamadı.")

        if deleted_count > 0:
            db.session.commit()
            message = f"{deleted_count} sipariş başarıyla silindi."
            print(message)
            return jsonify({'success': True, 'message': message})
        else:
            # Eğer order_numbers listesi boş değilse ama hiçbiri bulunamadıysa
            if order_numbers:
                message = "Belirtilen siparişlerden hiçbiri arşivde bulunamadı."
            else:
                message = "Silinecek sipariş bulunamadı."
            print(message)
            return jsonify({'success': False, 'message': message})

    except Exception as e:
        db.session.rollback()
        print(f"Arşivden silme DB hatası: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Silme sırasında veritabanı hatası oluştu.'})
