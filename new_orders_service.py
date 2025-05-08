# Dosya Adı: webs/new_orders_service.py

from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from models import db, OrderCreated
import json
# import os # Bu import kullanılmıyor gibi, kaldırılabilir veya bırakılabilir
# import logging # Logger kullanacaksanız bu satır kalsın, kullanmıyorsanız kaldırılabilir
import traceback # Hata detaylarını görmek için traceback ekle

# Logger'ı kullanıyorsan buradan alabilirsin (logger_config.py dosyan varsa)
# from logger_config import app_logger
# logger = app_logger # Eğer logger_config kullanılıyorsa bu satırı aktif et


new_orders_service_bp = Blueprint('new_orders_service', __name__)

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
    print(">> prepare_new_orders rotası çağrıldı.") # Rota çağrıldığında logla
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
        # product_main_id şu an API'den gelmediği için anahtar aslında (None, sku, renk, beden) gibi davranacak,
        # bu da SKU+renk+beden kombinasyonuna göre gruplama yapmasını sağlar.
        aggregated_product_items = {}

        if not new_orders:
            print(">> OrderCreated tablosu boş. İşlenecek sipariş yok.") # Sipariş yoksa bilgi ver

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

# ... (webs/new_orders_service.py dosyasının geri kalan fonksiyonları ve rotaları burada devam ediyor) ...
# Eğer bu dosyada başka rotalar veya fonksiyonlar varsa buraya eklenmelidir.