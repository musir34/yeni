# new_orders_service.py dosyası (güncellenmiş prepare_new_orders fonksiyonu)
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, make_response
from models import db, OrderCreated
import json
import traceback
from datetime import datetime
# qr_utils_bp'yi import et ve register et
from qr_utils import qr_utils_bp, generate_qr_labels_pdf # generate_qr_labels_pdf fonksiyonunu da import et

# Logger'ı kullanıyorsan buradan alabilirsin
# from logger_config import app_logger
# logger = app_logger


new_orders_service_bp = Blueprint('new_orders_service', __name__)

# qr_utils_bp'yi new_orders_service blueprint'ine kaydet (veya app'de merkezi olarak kaydet)
# Eğer app.py'de tüm blueprint'leri kaydediyorsan bu satıra gerek olmayabilir.
# new_orders_service_bp.register_blueprint(qr_utils_bp)


@new_orders_service_bp.route('/order-list/new', methods=['GET'])
def get_new_orders():
    """
    'Yeni' statüsündeki siparişleri gösterir.
    Artık 'OrderCreated' tablosunu sorguluyoruz.
    """
    # print(">> get_new_orders fonksiyonu çağrıldı.") # İsteğe bağlı log
    page = int(request.args.get('page', 1))
    per_page = 50

    try:
        # Veritabanından OrderCreated tablosundaki siparişleri al
        # (En güncel tarih en üstte)
        orders_query = OrderCreated.query.order_by(OrderCreated.order_date.desc())

        # Sayfalama (Flask-SQLAlchemy paginate)
        paginated_orders = orders_query.paginate(page=page, per_page=per_page, error_out=False)
        orders = paginated_orders.items # Mevcut sayfadaki sipariş objeleri
        total_orders_count = paginated_orders.total # Toplam sipariş sayısı (paginate edilen sorgu için)
        total_pages = paginated_orders.pages # Toplam sayfa sayısı (paginate edilen sorgu için)

        # print(f">> get_new_orders: Toplam {len(orders)} sipariş bulundu (sayfa {page}).") # İsteğe bağlı log

        # Şablonda ürün detaylarını göstermek için details alanını işle
        for order in orders:
            # details alanını doğru formatta kontrol et ve parse et
            # Bu kısım order_list.html şablonunun beklentisine göre ayarlanmalıdır.
            # Eğer şablon details'ın JSON string değil, liste/dict olmasını bekliyorsa bu parse işlemi burada yapılmalıdır.
            # Eğer order.details zaten DB'den çekilirken ORM tarafından otomatik parse ediliyorsa (PostgreSQL JSON/JSONB sütunları için olabilir) bu parse etme kodu gereksiz olabilir.
            # Loglar details'ın <class 'str'> olduğunu gösterdi, bu yüzden parse etmek doğru.
            if isinstance(order.details, str):
                try:
                    # details alanını JSON'dan Python listesine/sözlüğüne çevir
                    order.details = json.loads(order.details)
                except (json.JSONDecodeError, TypeError):
                     # JSON formatı hatalıysa veya None ise hata logu ver ve boş liste ata
                     print(f"!!! get_new_orders: Sipariş {order.order_number} ({order.siparis_no if hasattr(order, 'siparis_no') else 'N/A'}) için detaylar JSON formatında değil veya parse hatası.") # siparis_no ekledik loga
                     order.details = [] # Hata durumunda boş liste ata
            elif order.details is None:
                 # Details alanı None ise boş liste ata
                 order.details = []

            # Eğer details hala geçerli bir liste değilse veya boşsa,
            # alternatif olarak merchant_sku ve product_barcode alanlarından detay listesi oluştur (Mevcut fallback mantığı)
            # Bu fallback mantığı, details alanı boş veya tamamen hatalı olduğunda kullanılır.
            # Ancak normalde details alanı Trendyol API'sinden gelen detayları içermelidir.
            if not isinstance(order.details, list) or not order.details:
                # print(f">> get_new_orders: Sipariş {order.order_number} için detaylar listesi alternatif alanlardan oluşturuluyor.") # İsteğe bağlı log
                # merchant_sku ve product_barcode alanları virgülle ayrılmış stringler içeriyor olabilir
                skus = order.merchant_sku.split(', ') if order.merchant_sku else []
                barcodes = order.product_barcode.split(', ') if order.product_barcode else []

                # SKU ve barkod listelerinin uzunluklarını eşitle
                max_length = max(len(skus), len(barcodes))
                skus += [''] * (max_length - len(skus))
                barcodes += [''] * (max_length - len(barcodes))

                # Yeni bir detay listesi oluştur
                # NOT: Bu alternatif detay listesi product_main_id, color, size gibi diğer alanları içermez!
                # Bu yüzden prepare_new_orders rotası için details JSON'unun doğruluğu kritiktir.
                order.details = [{'sku': s, 'barcode': b} for s, b in zip(skus, barcodes)]
            # else:
                # print(f">> get_new_orders: Sipariş {order.order_number} için detaylar listesi mevcut ve geçerli görünüyor.") # İsteğe bağlı log


        # order_list.html şablonuna gerekli değişkenleri gönder
        # Şablonun 'orders' listesi içindeki her order objesinin '.details' alanını işleyebildiğinden emin olun.
        return render_template(
            'order_list.html',
            orders=orders, # İşlenmiş (details alanı muhtemelen liste/dict olmuş) sipariş listesi
            pagination=paginated, # Sayfalama bilgileri
            page=paginated.page if paginated else 1, # Mevcut sayfa numarası
            total_pages=paginated.pages if paginated else 1, # Toplam sayfa sayısı
            total_orders_count=paginated.total if paginated else len(orders), # Toplam sipariş sayısı
            list_title="Yeni Siparişler", # Liste başlığı
            active_list='new' # Aktif liste bilgisi (UI'da vurgulama için)
        )
    except Exception as e:
        print(f"!!! HATA: get_new_orders rotasında beklenmedik hata: {e}")
        traceback.print_exc() # Hata detayını logla
        # Hata durumunda kullanıcıya bilgi ver ve boş liste ile şablonu render et
        return render_template(
            'order_list.html',
            orders=[], pagination=None, page=1, total_pages=1, total_orders_count=0,
            list_title="Yeni Siparişler", active_list='new', error_message=str(e) # Hata mesajını şablona gönder
        ), 500


# Yeni siparişleri ürüne (şimdilik SKU+Renk+Beden) göre gruplayıp miktar etiketleri hazırlama rotası
# Bu rota, depoda ürün toplamak için kullanılacak toplu etiketleri oluşturur.
@new_orders_service_bp.route('/prepare-new-orders', methods=['GET'])
def prepare_new_orders():
    """
    Tüm 'Yeni' statüsündeki siparişleri (OrderCreated tablosu) çeker.
    Her siparişin detaylarındaki ürün kalemlerini toplar ve benzersiz ürünler için
    (product_main_id, sku, renk, beden kombinasyonuna göre) toplam miktarı hesaplar.
    Hazırlanan listeyi SKU'nun başındaki model koduna ve ardından renge göre sıralar.
    Etiket üzerinde sadece SKU ve toplam miktar gösterilir.
    """
    print(">> prepare-new-orders rotası çağrıldı.") # Rota çağrıldığında logla
    try:
        # 'Created' statüsündeki tüm siparişleri OrderCreated tablosundan çek
        # Eğer OrderCreated tablosu başka statüleri de içeriyorsa filtreleme eklenebilir:
        # new_orders = OrderCreated.query.filter_by(status='Created').all()
        # Şu an OrderCreated'daki tüm siparişlerin işlenmesi isteniyor:
        new_orders = OrderCreated.query.all()

        print(f">> OrderCreated tablosundan {len(new_orders)} adet sipariş çekildi.") # Çekilen sipariş sayısını logla

        # Benzersiz ürünlere (product_main_id veya None, sku, renk, beden) göre toplanan miktarları tutacak sözlük
        # Anahtar: (product_main_id, sku, renk, beden) - Bu kombinasyon benzersiz bir ürün varyantını temsil eder.
        # Değer: Bu varyantın toplam miktarı (farklı siparişlerden gelen aynı varyantların toplamı)
        aggregated_product_items = {}

        if not new_orders:
            print(">> OrderCreated tablosu boş. İşlenecek sipariş yok.") # Sipariş yoksa bilgi ver
            # Eğer sipariş yoksa, boş bir liste ile template'i render et veya başka bir işlem yap
            return render_template('barcode_quantity_label.html', product_items=[])


        # Her bir siparişi tek tek işle
        for order in new_orders:
            # Her siparişin 'details' alanındaki ürün kalemlerini işle.
            # 'details' alanı veritabanında JSON string olarak saklanıyor olmalı.
            # print(f">>> Sipariş No: {order.order_number}, Details tipi: {type(order.details)}, Details içeriği: {str(order.details)[:200]}...") # Ham veya işlenmiş details alanını logla (ilk 200 karakter)

            if order.details: # details alanı boş veya None değilse
                try:
                    items = order.details
                    if isinstance(items, str): # Eğer details alanı hala string ise JSON'a çevir
                         items = json.loads(items)

                    # Parse işleminden sonra 'items' bir liste olmalıdır.
                    # print(f">>> Sipariş {order.order_number} detayları JSON olarak başarıyla parse/hazır. Ürün kalem sayısı: {len(items) if isinstance(items, list) else 0}") # Parse edildiğini logla

                    # Eğer 'items' geçerli bir liste ise, her bir ürün kalemini işle
                    if isinstance(items, list):
                        for item in items:
                            # Gerekli bilgileri al (güvenli erişim için .get() metodu None döndürür, hata vermez)
                            product_main_id = item.get('product_main_id') # Loglara göre şu an boş geliyor
                            sku = item.get('sku') # merchantSku (Loglara göre dolu geliyor)
                            color = item.get('color') # Renk bilgisi
                            size = item.get('size') # Beden bilgisi
                            quantity = item.get('quantity') # Miktar bilgisi

                            # Her ürün kaleminin alınan bilgilerini logla (teşhis için önemli)
                            # print(f">>>> Ürün Kalemi - PM_ID: '{product_main_id}', SKU: '{sku}', Renk: '{color}', Beden: '{size}', Miktar: {quantity} (tip: {type(quantity)})") # Bu logu biraz daha az detaylı hale getirebiliriz

                            # Ürünü toplama havuzuna dahil etmek için koşul:
                            # SKU olmalı (etikette gösterilecek), miktar geçerli bir tam sayı ve pozitif olmalı.
                            # product_main_id eksik olsa bile SKU varsa işliyoruz.
                            if sku and isinstance(quantity, int) and quantity > 0:
                                # Gruplama anahtarı: product_main_id (None olabilir), sku, renk, beden.
                                item_key = (product_main_id, sku, color, size)

                                # Toplanan miktarları güncelle
                                if item_key in aggregated_product_items:
                                    aggregated_product_items[item_key] += quantity
                                else:
                                    aggregated_product_items[item_key] = quantity
                                # print(f">>>> '{item_key}' için güncel toplam miktar: {aggregated_product_items[item_key]}") # Güncel toplam miktarı logla

                            # Eğer ürün kalemi belirlenen koşulları sağlamıyorsa neden atlandığını logla
                            elif not sku:
                                 print(f">>>> Ürün Kalemi atlandı (SKU Eksik): Sipariş {order.order_number} - {item}. ")
                            elif not isinstance(quantity, int) or quantity <= 0:
                                 print(f">>>> Ürün Kalemi atlandı (Miktar Geçersiz): Sipariş {order.order_number} - {item}. Miktar: {quantity}")
                            else:
                                 print(f">>>> Ürün Kalemi atlandı (Beklenmeyen Durum): Sipariş {order.order_number} - {item}. PM_ID: '{product_main_id}', SKU: '{sku}', Miktar: {quantity}.")


                except json.JSONDecodeError:
                    # Details alanı geçerli JSON formatında değilse hata logu
                    print(f"!!! HATA: Sipariş {order.order_number} ({order.siparis_no if hasattr(order, 'siparis_no') else 'N/A'}) için detaylar JSON decode hatası: {str(order.details)[:200]}...")
                    traceback.print_exc() # Hata detayını yazdır
                except Exception as e:
                    # Details işlenirken beklenmedik başka bir hata oluşursa logla
                    print(f"!!! HATA: Sipariş {order.order_number} ({order.siparis_no if hasattr(order, 'siparis_no') else 'N/A'}) detayları işlenirken beklenmedik hata: {e}")
                    traceback.print_exc() # Hata detayını yazdır
            else:
                # Details alanı boş veya None ise logla
                print(f">>> Sipariş No: {order.order_number} ({order.siparis_no if hasattr(order, 'siparis_no') else 'N/A'}) detay alanı boş veya None.")


        print(f">> Toplama tamamlandı. Benzersiz ürün öğesi sayısı (Gruplama anahtarına göre): {len(aggregated_product_items)}") # Toplanan benzersiz öğe sayısını logla

        # Toplanan veriyi şablon için uygun formata getir (liste haline getir)
        # Her öğe bir sözlük olacak ve etikette gösterilecek bilgileri içerecek.
        product_list_for_template = []
        for (product_main_id, sku, color, size), total_quantity in aggregated_product_items.items():
            product_list_for_template.append({
                'product_main_id': product_main_id, # product_main_id hala None/boş olabilir, bilgisi taşınıyor
                'sku': sku, # Etikette gösterilecek
                'color': color, # İkinci sıralama kriteri
                'size': size,   # Üçüncü sıralama kriteri
                'quantity': total_quantity # Etikette gösterilecek
            })

        print(f">> Şablon için hazırlanmış ürün listesi boyutu (sıralanmadan önce): {len(product_list_for_template)}") # Hazırlanan listenin boyutunu logla


        # Hazırlanan listeyi SKU'nun başındaki model koduna ve ardından renge göre sırala.
        # SKU formatı "MODELKODU-VARYANT" şeklindeydi (örn: "009-38 Açık Mavi").
        # Sıralama anahtarı (key) fonksiyonu, her bir ürün öğesi için bir tuple döndürecek:
        # (Model Kodu Sayısal Değeri, Renk Stringi, Tam SKU Stringi, Beden Stringi)
        def sort_key_by_model_code_and_color(item):
            sku = item.get('sku', '') # Öğeden SKU'yu al (varsayılan boş string)
            color = item.get('color', '') # Öğeden rengi al (varsayılan boş string)
            size = item.get('size', '') # Öğeden bedeni al (varsayılan boş string)

            model_code_str = ''
            # SKU boş değilse ve içinde '-' varsa
            if sku and '-' in sku:
                # '-' işaretinden önceki kısmı al
                parts = sku.split('-', 1) # İlk '-' işaretine göre böl
                model_code_str = parts[0] # İlk parça model kodudur

            model_code_int = float('inf') # Sayısal çevrilemezse sonsuz yap (listenin sonuna gider)
            # Eğer model kodu stringi boş değilse ve sadece sayılardan oluşuyorsa
            if model_code_str and model_code_str.isdigit():
                try:
                    model_code_int = int(model_code_str) # Sayısal değere çevir
                except ValueError:
                    # Sayıya çevirme hatası olursa (olmamalı ama önlem)
                    pass # Sonsuz olarak kalır

            # Sıralama için tuple döndür: (Model Kodu Sayısal, Renk Stringi, Tam SKU Stringi, Beden Stringi)
            # Sıralama sırası: 1. Model Kodu (Sayısal), 2. Renk (Alfabetik), 3. Tam SKU (Alfabetik), 4. Beden (Alfabetik)
            return (model_code_int, color, sku, size)

        # Sıralanmış listeyi oluştur
        sorted_product_list = sorted(
            product_list_for_template,
            key=sort_key_by_model_code_and_color # Özel sıralama anahtar fonksiyonumuzu kullan
        )

        print(f">> Sıralanmış ürün listesi boyutu: {len(sorted_product_list)}") # Sıralanmış listenin boyutunu logla
        print(">> İlk 5 sıralanmış ürün öğesi:", sorted_product_list[:5]) # İlk birkaç öğeyi logla
        print(">> Son 5 sıralanmış ürün öğesi:", sorted_product_list[-5:]) # Son birkaç öğeyi logla


        # Sıralanmış listeyi etiket şablonuna gönder.
        # 'product_items' değişken adının HTML şablonuyla eşleşmelidir.
        response = render_template('barcode_quantity_label.html', product_items=sorted_product_list)
        print(">> render_template çağrısı tamamlandı. Sayfa render edildi.") # Template render edildiğinde logla
        return response # Render edilmiş HTML yanıtını döndür

    except Exception as e:
        # prepare_new_orders fonksiyonu içinde herhangi bir beklenmedik hata oluşursa logla
        print(f"!!! KRİTİK HATA: prepare_new_orders rotasında beklenmedik bir hata oluştu: {e}")
        traceback.print_exc() # Hata detayını yazdır
        # Kullanıcıya hata mesajı gösteren bir yanıt döndür
        return "Bir hata oluştu: Siparişler hazırlanırken bir sorun yaşandı.", 500

# Yeni Rota: Toplu QR Etiket PDF Oluşturma
@new_orders_service_bp.route('/generate-bulk-qr-pdf', methods=['GET'])
def generate_bulk_qr_pdf():
    """
    'Yeni' statüsündeki tüm siparişlerdeki barkodları toplayıp,
    Adet bilgisine göre QR kod etiket PDF'i oluşturur (A4, 21 etiket).
    """
    print(">> generate-bulk-qr-pdf rotası çağrıldı.")

    try:
        # 1. 'Yeni' statüsündeki siparişlerdeki ürün/barkod/adet bilgisini topla
        new_orders = OrderCreated.query.all()
        items_for_pdf = []

        for order in new_orders:
            if order.details:
                try:
                    details_list = json.loads(order.details) if isinstance(order.details, str) else order.details
                    if isinstance(details_list, list):
                        for item in details_list:
                            barcode_val = item.get('barcode')
                            quantity_val = int(item.get('quantity', 0))
                            if barcode_val and quantity_val > 0:
                                # generate_qr_labels_pdf function expects [{'barcode': 'BARKOD', 'quantity': MIKTAR}, ...]
                                # where quantity is the number of times this specific barcode should appear as an item to print.
                                # So we add the item with its quantity.
                                items_for_pdf.append({'barcode': barcode_val, 'quantity': quantity_val})
                except json.JSONDecodeError:
                    print(f"!!! HATA: Sipariş {order.order_number} detayları JSON formatında değil.")
                    continue
                except Exception as e:
                     print(f"!!! HATA: Sipariş {order.order_number} detayları işlenirken hata: {e}")
                     continue

        if not items_for_pdf:
            print(">> PDF oluşturmak için ürün bilgisi toplanamadı.")
            flash("PDF oluşturmak için ürün bilgisi toplanamadı. Yeni sipariş yok veya detayları eksik.", "warning")
            return redirect(url_for('new_orders_service.get_new_orders')) # Yeni siparişler listesine geri dön

        print(f">> PDF için hazırlanmış {len(items_for_pdf)} adet ürün öğesi.")
        # 2. generate_qr_labels_pdf fonksiyonunu çağır
        # Bu fonksiyon bir Flask yanıtı döndürür (send_file)
        # generate_qr_labels_pdf fonksiyonu POST metodu bekliyor, burası GET.
        # generate_qr_labels_pdf fonksiyonunun signature'ını JSON body yerine 
        # parametre alacak şekilde değiştirmek daha doğru olur, veya burada sahte bir POST request contexti yaratmak.
        # Fonksiyonun kendisini import edip doğrudan çağırmak daha temiz.

        # generate_qr_labels_pdf'i doğrudan çağırmak için, ondan json/request bağımlılığını kaldırmalıyız.
        # veya o fonksiyondan döndürülen send_file objesini döndürmeliyiz.
        # En temiz yol generate_qr_labels_pdf'in sadece PDF dosya yolunu döndürmesi,
        # ve bu rotanın send_file yapması.

        # Mevcut generate_qr_labels_pdf fonksiyonu bir JSON yanıtı ve dosya yolu döndürüyor.
        # Bu rotadan o fonksiyonu çağıralım ve dönen JSON'u işleyip PDF'i gönderelim.
        # Ancak generate_qr_labels_pdf POST bekliyor ve request.get_json kullanıyor.
        # Burada request contexti yok. Ya generate_qr_labels_pdf'i refactor etmeli
        # ya da burada bir test request contexti yaratmalıyız.
        # Refactor daha iyi. Ama şu anki kodla generate_qr_labels_pdf'i direkt çağıramayız.
        # Başka bir yöntem: generate_qr_labels_pdf fonksiyonunun logic'ini buraya taşımak.

        # generate_qr_labels_pdf içeriğini buraya taşıyalım ve modify edelim:
        # --- Başlangıç: generate_bulk_qr_pdf içinde PDF oluşturma logic ---
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        import qrcode
        import os
        import io
        # from flask import send_file # Zaten yukarıda import edildi

        # app objesine erişim (eğer gerekiyorsa)
        # from flask import current_app

        qr_temp_dir = os.path.join('static', 'qr_temp')
        os.makedirs(qr_temp_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pdf_temp_path = os.path.join(qr_temp_dir, f"etiketler_{timestamp}.pdf")

        c = canvas.Canvas(pdf_temp_path, pagesize=A4)
        page_width, page_height = A4

        cols = 3 # 21 etiket için 3 kolon
        rows = 7 # 21 etiket için 7 satır

        # Her bir etiket için ayrılan yaklaşık alan (boşluklar dahil)
        approx_label_width = page_width / cols
        approx_label_height = page_height / rows

        # Etiket içindeki boşluklar ve eleman boyutları
        padding_mm = 2 * mm
        qr_size_mm = 25 * mm # QR kod boyutu
        barcode_text_height_mm = 5 * mm # Barkod metni için ayrılan yükseklik

        # Kullanılabilir alan ve QR/Metin çizim boyutu
        usable_width = approx_label_width - 2 * padding_mm
        usable_height = approx_label_height - 2 * padding_mm
        qr_draw_size = min(qr_size_mm, usable_width, usable_height - barcode_text_height_mm) # Kullanılabilir alana sığacak en büyük QR

        # Font ayarı
        try:
            # Uygulamanın root_path'ini kullanarak font yolunu bul
            # current_app'in import edildiğinden emin ol (yukarıda var)
            # font_path = os.path.join(current_app.root_path, 'static', 'fonts', 'arial.ttf')
            # if not os.path.exists(font_path):
            #    print(f"!!! Font dosyası bulunamadı: {font_path}. Varsayılan font kullanılıyor.")
            #    raise IOError("Font not found") # IOE hatası fırlatıp varsayılan fontu kullanmaya zorla

            # ReportLab'in kendi fontlarını kullanmak daha güvenli olabilir.
            # "Helvetica" gibi standart fontlar her zaman bulunur.
            font_name = "Helvetica"
            c.setFont(font_name, 8) # Font boyutu ayarlanabilir

        except IOError:
             font_name = "Helvetica"
             c.setFont(font_name, 8)
        except Exception as font_e:
             print(f"!!! Font yükleme hatası: {font_e}. Varsayılan ReportLab fontu kullanılıyor.")
             font_name = "Helvetica"
             c.setFont(font_name, 8)


        # items_for_pdf listesindeki her bir öğe için etiket çizimi
        for i, item in enumerate(items_for_pdf):
            barcode = item.get('barcode', 'BARKOD_YOK')

            # Etiketin sayfadaki sol alt köşesi
            x_start = col * approx_label_width
            y_start = page_height - (row + 1) * approx_label_height

            # Etiket içindeki QR kod ve metin konumu
            # QR kodunun sol alt köşesi
            qr_x = x_start + padding_mm + (usable_width - qr_draw_size) / 2
            qr_y = y_start + padding_mm + barcode_text_height_mm

            # Barkod metninin konumu (etiket alanının ortasına hizalanmış, en altta)
            barcode_text_x = x_start + approx_label_width / 2
            barcode_text_y = y_start + padding_mm

            try:
                # QR kod görseli oluştur (BytesIO ile bellekte tut)
                qr = qrcode.QRCode(
                    version=1, error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10, border=2
                )
                qr.add_data(barcode)
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="black", back_color="white")

                # BytesIO nesnesi oluştur
                img_buffer = io.BytesIO()
                qr_img.save(img_buffer, format='PNG')
                img_buffer.seek(0) # Başlangıca dön

                # PDF'e QR kodunu çiz (BytesIO'dan)
                c.drawImage(io.BytesIO(img_buffer.getvalue()), qr_x, qr_y, width=qr_draw_size, height=qr_draw_size)

                # PDF'e barkod metnini çiz
                # Font tekrar ayarlanmalı eğer loop içinde set ediyorsak
                c.setFont(font_name, 8)
                c.drawCentredString(barcode_text_x, barcode_text_y, barcode)

            except Exception as e:
                print(f"Barkod {barcode} için QR kod oluşturma veya çizme hatası: {e}")
                # Hata durumunda hata mesajı çizilebilir
                c.setFont(font_name, 8)
                c.setFillColorRGB(1,0,0) # Kırmızı
                c.drawCentredString(barcode_text_x, barcode_text_y + qr_draw_size/2, "QR HATA")
                c.setFillColorRGB(0,0,0) # Siyah


        # PDF'i kaydet
        c.save()

        # Geçici QR dosyalarını temizle (eğer kaydedildiyse, BytesIO kullanıyorsak buna gerek yok)
        # Şu anki mantık BytesIO kullandığı için geçici dosya kaydı yok, temizliğe gerek yok.
        # Eğer generate_qr_labels_pdf içindeki os.remove satırı aktif olsaydı, o fonksiyon içindeki loop'ta temizlenirdi.
        # Eğer dışarıda topluca silme düşünülüyorsa, kaydedilen dosya isimlerini tutmak gerekirdi.
        # BytesIO kullanımı geçici dosya ihtiyacını ortadan kaldırdığı için bu temizlik adımı gereksizleşti.


        # PDF dosyasını yanıt olarak gönder
        # BytesIO kullanılarak bellekte tutulan PDF'i de gönderebilirsiniz, disk I/O'dan kaçınır.
        # Ama mevcut ReportLab kütüphanesi dosya yoluna yazar gibi görünüyor.
        # PDF dosyasını diskten oku ve BytesIO'ya yazıp gönder (daha güvenli temizlik için)
        try:
            with open(pdf_temp_path, 'rb') as f:
                pdf_buffer = io.BytesIO(f.read())
            pdf_buffer.seek(0)

            # Geçici PDF dosyasını sil
            os.remove(pdf_temp_path)

            # send_file ile BytesIO'dan gönder
            return send_file(pdf_buffer, as_attachment=True, mimetype='application/pdf', download_name=f"etiketler_{timestamp}.pdf")

        except FileNotFoundError:
            print(f"!!! HATA: Oluşturulan PDF dosyası bulunamadı: {pdf_temp_path}")
            flash("PDF dosyası oluşturuldu ancak bulunamadı.", "danger")
            return redirect(url_for('new_orders_service.prepare_new_orders'))
        except Exception as file_e:
            print(f"!!! HATA: PDF dosyası okunurken veya gönderilirken hata: {file_e}")
            traceback.print_exc()
            flash("PDF dosyası oluşturuldu ancak gönderilirken bir hata oluştu.", "danger")
            return redirect(url_for('new_orders_service.prepare_new_orders'))


        # --- Sonu: generate_bulk_qr_pdf içinde PDF oluşturma logic ---


    except Exception as e:
        print(f"!!! KRİTİK HATA: generate-bulk-qr-pdf rotasında beklenmedik bir hata oluştu: {e}")
        traceback.print_exc()
        flash("Toplu QR etiket PDF oluşturulurken beklenmedik bir hata oluştu.", "danger")
        return redirect(url_for('new_orders_service.get_new_orders')) # Hata durumunda Yeni siparişler listesine yönlendir


@new_orders_service_bp.route('/print-customer-info', methods=['POST'])
def print_customer_info():
    """
    Seçilen siparişlerin müşteri bilgilerini yazdırmak için PDF oluşturur.
    """
    try:
        # POST'tan gelen sipariş numaralarını al
        order_numbers = request.form.getlist('order_numbers')
        
        if not order_numbers:
            return jsonify({'error': 'Sipariş numarası seçilmedi'}), 400
        
        # Seçilen siparişleri veritabanından çek
        orders = OrderCreated.query.filter(OrderCreated.order_number.in_(order_numbers)).all()
        
        if not orders:
            return jsonify({'error': 'Seçilen siparişler bulunamadı'}), 404
        
        # PDF oluştur
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        import io
        
        # Geçici dosya oluştur
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=A4)
        width, height = A4
        
        y_position = height - 50
        line_height = 20
        
        # Başlık
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, y_position, "Müşteri Bilgileri Raporu")
        y_position -= 40
        
        # Her sipariş için müşteri bilgilerini yazdır
        for order in orders:
            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, y_position, f"Sipariş No: {order.order_number}")
            y_position -= line_height
            
            c.setFont("Helvetica", 10)
            c.drawString(70, y_position, f"Müşteri Adı: {order.customer_name or 'Belirtilmemiş'} {order.customer_surname or ''}")
            y_position -= line_height
            
            c.drawString(70, y_position, f"Telefon: {order.customer_phone or 'Belirtilmemiş'}")
            y_position -= line_height
            
            # Adresi satırlara böl (çok uzunsa)
            address = order.customer_address or 'Adres belirtilmemiş'
            if len(address) > 80:
                # Uzun adresi satırlara böl
                words = address.split(' ')
                lines = []
                current_line = ""
                for word in words:
                    if len(current_line + " " + word) <= 80:
                        current_line += " " + word if current_line else word
                    else:
                        lines.append(current_line)
                        current_line = word
                if current_line:
                    lines.append(current_line)
                
                c.drawString(70, y_position, "Adres:")
                y_position -= line_height
                for line in lines:
                    c.drawString(90, y_position, line)
                    y_position -= line_height
            else:
                c.drawString(70, y_position, f"Adres: {address}")
                y_position -= line_height
            
            c.drawString(70, y_position, f"Sipariş Tarihi: {order.order_date}")
            y_position -= line_height
            
            c.drawString(70, y_position, f"Kargo Firması: {order.cargo_provider_name or 'Belirtilmemiş'}")
            y_position -= line_height * 2
            
            # Sayfa sonu kontrolü
            if y_position < 100:
                c.showPage()
                y_position = height - 50
        
        c.save()
        pdf_buffer.seek(0)
        
        # PDF'i indir
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        response = make_response(pdf_buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=musteri_bilgileri_{timestamp}.pdf'
        
        return response
        
    except Exception as e:
        print(f"!!! HATA: Müşteri bilgileri yazdırılırken hata: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Müşteri bilgileri yazdırılırken bir hata oluştu'}), 500