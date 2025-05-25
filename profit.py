# profit.py
from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
)
from datetime import datetime, timedelta
import logging
import calendar
from collections import defaultdict
import re

# --------------------------------------------------------------------------
# Veritabanı Modellerinizi Buraya Import Edin
# --------------------------------------------------------------------------
from models import (
    ReturnProduct, # Kullanılıyor mu kontrol et
    db,
    OrderCreated,
    OrderPicking,
    OrderShipped,
    OrderDelivered,
    OrderCancelled,
    Product,
    ReturnOrder, # Kullanılıyor
)
# --------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

profit_bp = Blueprint("profit", __name__, url_prefix="/profit")


# --------------------------------------------------------------------------
# Yardımcı Fonksiyonlar
# --------------------------------------------------------------------------
def format_number(value):
    """Ondalıklı sayıları '1.234,56' biçiminde döndürür."""
    if value is None:
        return "0,00"
    try:
        float_value = float(value)
        # Sayıyı string'e çevir, noktayı geçici bir karaktere, virgülü noktaya çevir, sonra geçici karakteri virgüle çevir
        formatted_str = "{:,.2f}".format(float_value) # Örn: 1,234.56 (Amerikan formatı)
        # Amerikan formatını Türk formatına çevir
        if '.' in formatted_str:
            parts = formatted_str.split('.')
            integer_part = parts[0].replace(',', '.') # 1.234
            decimal_part = parts[1]
            return f"{integer_part},{decimal_part}"
        else: # Ondalık kısım yoksa
            return formatted_str.replace(',', '.') + ",00"

    except (TypeError, ValueError):
        logging.warning(f"'{value}' değeri formatlanamadı, string olarak döndürülüyor.")
        try:
            # Sadece noktayı virgüle çevir
            return str(value).replace('.', ',')
        except:
            return str(value)


# --------------------------------------------------------------------------
# Eksik maliyet kaydetme
# --------------------------------------------------------------------------
@profit_bp.route("/save-costs", methods=["POST"])
def save_missing_costs():
    """
    Eksik maliyet formundan gelen değerleri Product tablosuna yazar
    ve aynı tarih aralığı ile ana raporu yeniden oluşturur.
    """
    start_date_str = request.form.get("start_date") # start_date -> start_date_str
    end_date_str = request.form.get("end_date")     # end_date -> end_date_str

    updates = {
        key.replace("cost_", ""): float(val.replace(',', '.'))
        for key, val in request.form.items()
        if key.startswith("cost_") and val and val.strip()
    }

    if not updates:
        flash("Kaydedilecek geçerli maliyet bulunamadı.", "warning")
        return redirect(
            url_for(
                "profit.profit_report",
                start_date=start_date_str, end_date=end_date_str, # Değişken adları güncellendi
                package_cost=request.form.get("package_cost", ""),
                monthly_employee_salary=request.form.get("monthly_employee_salary", ""),
                shipping_cost=request.form.get("shipping_cost", ""),
                auto_reload="1",
            )
           )

    try:
        existing_products = Product.query.filter(Product.barcode.in_(updates.keys())).all()

        # USD kuru al (eğer maliyetler USD ise ve TRY'ye çevrilecekse)
        # from get_products import fetch_usd_rate # Bu fonksiyon async, burada direkt çağıramayız.
        # Şimdilik cost_try'ın direkt girildiğini varsayalım.
        # Eğer USD girilip TRY hesaplanacaksa, bu kısım yeniden düzenlenmeli.

        for prod in existing_products:
             if prod.barcode in updates:
                 prod.cost_try = updates[prod.barcode] # cost_try olarak kaydediyoruz
                 prod.cost_date = datetime.utcnow() # Maliyet güncelleme tarihini de set et
                 # prod.cost_usd = ... # Eğer USD giriliyorsa bu da set edilmeli

        # Product modelinin constructor'ı yok, alanları direkt atıyoruz.
        # Product.__init__ metodunu kullanmıyoruz.
        missing_barcodes = set(updates.keys()) - {p.barcode for p in existing_products}
        for bc in missing_barcodes:
            try:
                new_product = Product(
                    barcode=bc,
                    cost_try=updates[bc],
                    cost_date=datetime.utcnow(),
                    title=f"Oto-Eklenen: {bc}", 
                    product_main_id=None,       
                    quantity=0,                 
                    images=None,                
                    variants=None,              
                    size="",                    
                    color="",                   
                    archived=False,             
                    locked=False,               
                    on_sale=False,              
                    reject_reason=None,         
                    sale_price=0.0,             
                    list_price=0.0,             
                    currency_type="TRY"         
                )
                db.session.add(new_product)
            except Exception as te: # Genel Exception yakala
                db.session.rollback()
                logging.error(f"'{bc}' barkodlu yeni ürün oluşturulurken hata: {te}. Model tanımını kontrol edin.", exc_info=True)
                flash(f"'{bc}' barkodlu ürün için maliyet kaydedilemedi. Model tanımı veya zorunlu alanlarda sorun olabilir. Detaylar log dosyasında.", "error")
                continue

        db.session.commit()
        flash(f"{len(updates)} adet maliyet güncellendi/eklendi.", "success")

    except Exception as e:
        db.session.rollback()
        logging.error("Maliyetler kaydedilirken hata: %s", e, exc_info=True)
        if not isinstance(e, TypeError): # TypeError zaten yukarıda yakalandı
             flash(f"Maliyetler kaydedilemedi. Veritabanı hatası: {e}", "error")

    return redirect(
        url_for(
            "profit.profit_report",
            start_date=start_date_str, end_date=end_date_str, # Değişken adları güncellendi
            package_cost=request.form.get("package_cost", ""),
            monthly_employee_salary=request.form.get("monthly_employee_salary", ""),
            shipping_cost=request.form.get("shipping_cost", ""),
            auto_reload="1",
        )
    )


# --------------------------------------------------------------------------
# Ana rapor
# --------------------------------------------------------------------------
@profit_bp.route("/", methods=["GET", "POST"])
def profit_report():
    if request.method == "POST":
        form_source = request.form
    else:
        form_source = request.args

    # now değişkenini context'e ekle
    context = {
        "now": datetime.now(), # Jinja2 için 'now' eklendi
        "analysis": [], "cancelled_orders": [], "returned_orders": [], "other_excluded_orders": [],
        "top_profit_products": [], "top_commission_products": [], "top_discount_products": [],
        "missing_cost_entries": [], "total_records_found": 0,
        "total_profit": 0.0, "avg_profit": 0.0, "total_revenue": 0.0, "total_discount_sum": 0.0,
        "total_expenses_sum": 0.0, "total_commission_sum": 0.0, "total_product_cost_sum": 0.0,
        "total_employee_cost_period": 0.0, "total_package_cost_period": 0.0,
        "total_shipping_cost_period": 0.0, "total_return_shipping_cost": 0.0,
        "avg_profit_margin": 0.0, "order_count": 0, "total_barcodes_processed": 0,
        "start_date": form_source.get("start_date", ""), "end_date": form_source.get("end_date", ""),
        "package_cost": form_source.get("package_cost", "0"), # Default "0" olsun
        "monthly_employee_salary": form_source.get("monthly_employee_salary", "0"), # Default "0"
        "shipping_cost": form_source.get("shipping_cost", "0"), # Default "0"
        "total_profit_str": "0,00", "avg_profit_str": "0,00", "total_revenue_str": "0,00",
        "total_discount_sum_str": "0,00", "total_expenses_sum_str": "0,00",
        "total_commission_sum_str": "0,00", "total_product_cost_sum_str": "0,00",
        "total_employee_cost_period_str": "0,00", "total_package_cost_period_str": "0,00",
        "total_shipping_cost_period_str": "0,00", "total_return_shipping_cost_str": "0,00",
        "shipping_cost_str": "0,00", "avg_profit_margin_str": "0.00",
    }
    try:
        form_shipping_cost_float = float((context["shipping_cost"] or '0').replace(',', '.'))
        context["shipping_cost_str"] = format_number(form_shipping_cost_float) 
    except ValueError:
        form_shipping_cost_float = 0.0 
        context["shipping_cost_str"] = "Hatalı Giriş"


    if request.method == "POST" or request.args.get("auto_reload") == "1":
        analysis_temp = []
        cancelled_orders_temp = []
        returned_orders_temp = []
        other_excluded_temp = []
        missing_cost_barcodes = set()
        missing_cost_entries_list = []
        product_summary = defaultdict(lambda: {"total_profit": 0.0, "total_commission": 0.0, "total_discount": 0.0, "count": 0, "titles": set()}) # titles eklendi

        total_profit_minus_employee = 0.0
        total_revenue = 0.0
        total_discount_sum = 0.0
        total_expenses_minus_employee = 0.0
        total_commission_sum = 0.0
        total_product_cost_sum = 0.0
        total_package_cost_period = 0.0
        total_outgoing_shipping_cost_period = 0.0 
        total_return_shipping_cost = 0.0 
        processed_order_count = 0
        total_barcodes_processed_in_analysis = 0 # Sadece analize dahil edilenlerin barkod sayısı
        total_records_found = 0

        try:
            package_cost_per_item_str = (context["package_cost"] or "0").replace(',', '.')
            monthly_employee_salary_str = (context["monthly_employee_salary"] or "0").replace(',', '.')

            package_cost_per_item = float(package_cost_per_item_str) if package_cost_per_item_str else 0.0
            monthly_employee_salary = float(monthly_employee_salary_str) if monthly_employee_salary_str else 0.0
            # form_shipping_cost_float yukarıda tanımlandı

            start_date_str = context["start_date"]
            end_date_str = context["end_date"]
            if not start_date_str or not end_date_str:
                flash("Başlangıç ve Bitiş tarihleri zorunludur.", "error")
                context["now"] = datetime.now() # Hata durumunda da now'ı gönder
                return render_template("profit.html", **context)

            start_date_obj = datetime.strptime(start_date_str, "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0)
            end_date_obj_inclusive = datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999)

            days_in_range = (end_date_obj_inclusive.date() - start_date_obj.date()).days + 1
            if days_in_range <= 0:
                flash("Bitiş tarihi başlangıç tarihinden önce olamaz.", "error")
                context["now"] = datetime.now()
                return render_template("profit.html", **context)

            logging.info(f"Form Girdileri - Paket/adet: {package_cost_per_item}, Aylık Maaş: {monthly_employee_salary}, Baz/İade Kargo: {form_shipping_cost_float}, Başlangıç: {start_date_str}, Bitiş: {end_date_str}")
            logging.info(f"Tarih aralığındaki gün sayısı: {days_in_range}")

            cancelled_order_numbers = set()
            returned_order_numbers = set()

            try:
                cancelled_orders_query = (
                    OrderCancelled.query.with_entities(
                        OrderCancelled.order_number, OrderCancelled.merchant_sku,
                        OrderCancelled.status, OrderCancelled.product_barcode
                    ).filter(
                        OrderCancelled.order_date.between(start_date_obj, end_date_obj_inclusive)
                    ).all()
                )
                for o in cancelled_orders_query:
                     barcode_val = o.product_barcode if hasattr(o, 'product_barcode') else None
                     if o.order_number:
                         cancelled_orders_temp.append({
                             "order_number": o.order_number, "merchant_sku": o.merchant_sku, "status": o.status,
                             "barcode": barcode_val, "reason": "İptal Edildi",
                         })
                         cancelled_order_numbers.add(o.order_number)
                logging.info(f"{len(cancelled_order_numbers)} adet iptal edilmiş sipariş listelendi.")

                returned_orders_query_result = (
                    ReturnOrder.query
                    .join(ReturnProduct, ReturnOrder.id == ReturnProduct.return_order_id)
                    .with_entities(
                        ReturnOrder.order_number, ReturnOrder.status,
                        ReturnOrder.return_reason, ReturnProduct.barcode,
                    ).filter(
                        ReturnOrder.return_date.between(start_date_obj, end_date_obj_inclusive)
                    ).all()
                )
                temp_returned_nos = set() # Bir siparişin birden fazla iade kalemi olabilir, kargo maliyetini bir kez ekle

                for o in returned_orders_query_result:
                    order_num = o.order_number
                    barcode_val = o.barcode if hasattr(o, 'barcode') else None
                    return_reason_val = o.return_reason if hasattr(o, 'return_reason') else 'Belirtilmemiş'

                    if order_num and order_num not in temp_returned_nos:
                        return_shipping_cost_per_order = form_shipping_cost_float
                        total_return_shipping_cost += return_shipping_cost_per_order
                        temp_returned_nos.add(order_num)

                    returned_orders_temp.append({
                        "order_number": order_num, "status": o.status,
                        "reason": f"İade ({return_reason_val})",
                        "barcode": barcode_val,
                        "cost": form_shipping_cost_float # Her bir iade satırı için değil, sipariş başına
                    })
                returned_order_numbers = temp_returned_nos
                logging.info(f"{len(returned_order_numbers)} adet iade edilmiş sipariş (benzersiz sipariş no) listelendi.")
                logging.info(f"Toplam iade kargo maliyeti: {total_return_shipping_cost:.2f} TL")

            except AttributeError as ae:
                 logging.error("İptal/İade sorgusunda model hatası: %s", ae, exc_info=True)
                 flash(f"Veritabanı modeli hatası: İptal/iade bilgileri çekilemedi ({ae}).", "error")
                 context["now"] = datetime.now()
                 return render_template("profit.html", **context)
            except Exception as e:
                logging.error("İptal/İade siparişleri çekilirken genel hata: %s", e, exc_info=True)
                flash(f"İptal veya iade bilgileri çekilirken bir sorun oluştu: {e}", "warning")

            orders = []
            table_classes = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered]
            all_individual_barcodes_in_scope = set()
            all_excluded_order_nos = cancelled_order_numbers.union(returned_order_numbers)

            logging.info(f"Hariç tutulacak sipariş numaraları (iptal/iade): {len(all_excluded_order_nos)}")
            total_records_found = len(all_excluded_order_nos)

            for cls in table_classes:
                try:
                    # notin_ ile hariç tutma
                    query_obj = cls.query.filter(
                        cls.order_date.between(start_date_obj, end_date_obj_inclusive)
                    )
                    if all_excluded_order_nos: # Eğer hariç tutulacak sipariş varsa filtrele
                        query_obj = query_obj.filter(cls.order_number.notin_(all_excluded_order_nos))

                    results = query_obj.all()

                    count = len(results)
                    logging.info(f"{cls.__tablename__}: {count} adet potansiyel kayıt bulundu (iptal/iadeler hariç).")
                    total_records_found += count
                    orders.extend(results)

                    for o in results:
                        product_barcode_raw = getattr(o, "product_barcode", None)
                        if product_barcode_raw and product_barcode_raw.strip():
                            individual_barcodes_list = [b.strip() for b in product_barcode_raw.split(',') if b.strip()]
                            all_individual_barcodes_in_scope.update(individual_barcodes_list)
                except Exception as e:
                    logging.error("Tablo sorgulanırken hata (%s): %s", cls.__tablename__, e, exc_info=True)
                    flash(f"{cls.__tablename__} tablosu sorgulanırken bir veritabanı hatası oluştu.", "error")

            logging.info(f"Analize dahil edilecek sipariş sayısı: {len(orders)}")
            context["total_records_found"] = total_records_found

            if not orders and not (cancelled_orders_temp or returned_orders_temp) : # Eğer hiç aktif, iptal veya iade sipariş yoksa
                flash("Belirtilen tarih aralığında işlenecek hiçbir kayıt (aktif, iptal, iade) bulunamadı.", "info")
                context["now"] = datetime.now()
                return render_template("profit.html", **context)


            product_costs = {}
            product_titles = {} # Barkod -> Ürün Başlığı
            if all_individual_barcodes_in_scope:
                  try:
                    # Product.title'ı da çekelim
                    products_db = Product.query.filter(Product.barcode.in_(all_individual_barcodes_in_scope)).all()
                    for p in products_db:
                        if p.barcode and p.barcode.strip() in all_individual_barcodes_in_scope:
                            if p.cost_try is not None:
                                product_costs[p.barcode.strip()] = float(p.cost_try)
                            if p.title:
                                product_titles[p.barcode.strip()] = p.title
                    logging.info(f"{len(product_costs)}/{len(all_individual_barcodes_in_scope)} *tekil* barkod için maliyet bulundu (None olmayan).")
                    logging.info(f"{len(product_titles)}/{len(all_individual_barcodes_in_scope)} *tekil* barkod için başlık bulundu.")
                  except Exception as e:
                    logging.error("Ürün maliyet/başlıkları çekilirken hata: %s", e, exc_info=True)
                    flash("Ürün maliyet/başlıkları alınırken bir veritabanı hatası oluştu.", "error")
            else:
                 logging.warning("Maliyet/başlık çekmek için geçerli tekil barkod bulunamadı.")

            processed_order_ids = set()

            for o in orders:
                order_id_attr = getattr(o, "id", None) # Her sipariş tablosunda id olmalı
                order_number = getattr(o, "order_number", f"NO_{order_id_attr or uuid.uuid4()}")
                merchant_sku = getattr(o, "merchant_sku", None) or f"SKU_{order_id_attr or 'Bilinmiyor'}"
                order_status = getattr(o, "status", "Bilinmiyor")
                product_title_from_order = getattr(o, "product_name", None) # Siparişteki ürün adı

                if order_id_attr and order_id_attr in processed_order_ids: # Aynı ID'li siparişi tekrar işleme
                    continue

                try:
                    product_barcode_raw = getattr(o, "product_barcode", None)
                    reason = None
                    order_total_product_cost = 0.0
                    cost_calculation_possible = True
                    display_barcode_in_excluded = product_barcode_raw or f"BARKODSUZ_{order_id_attr or 'ID'}"
                    num_barcodes_in_order = 0
                    individual_barcodes_in_order = []
                    current_order_titles = set() # Bu siparişteki ürün başlıkları

                    if not product_barcode_raw or not product_barcode_raw.strip():
                        reason = "Barkod Boş/Yok"
                        cost_calculation_possible = False
                    else:
                        individual_barcodes_in_order = [b.strip() for b in product_barcode_raw.split(',') if b.strip()]
                        num_barcodes_in_order = len(individual_barcodes_in_order)
                        if num_barcodes_in_order == 0:
                            reason = "Geçerli Barkod Yok"
                            cost_calculation_possible = False
                        else:
                            missing_barcodes_in_this_order = []
                            for bc_idx, bc in enumerate(individual_barcodes_in_order):
                                cost = product_costs.get(bc)
                                current_order_titles.add(product_titles.get(bc, f"Başlıksız Ürün ({bc})"))

                                if cost is None: # Maliyet hiç yoksa
                                    cost_calculation_possible = False
                                    missing_barcodes_in_this_order.append(bc)
                                    if bc not in missing_cost_barcodes: # Daha önce eklenmediyse
                                        # SKU'yu siparişten, başlığı Product tablosundan al
                                        sku_for_missing = merchant_sku.split(', ')[bc_idx] if merchant_sku and bc_idx < len(merchant_sku.split(', ')) else f"SKU_{bc}"
                                        title_for_missing = product_titles.get(bc, "Başlık Bilinmiyor")
                                        missing_cost_entries_list.append({"barcode": bc, "merchant_sku": sku_for_missing, "title": title_for_missing})
                                        missing_cost_barcodes.add(bc)
                                elif cost <= 0: # Maliyet 0 veya negatifse
                                    logging.warning(f"Sipariş {order_number}, Barkod '{bc}' maliyeti sıfır veya negatif ({cost}). Hesaplamada 0 olarak kullanıldı.")
                                    order_total_product_cost += 0.0 # Kâra etkisi olmaz ama gider olarak 0 görünür
                                else: # Geçerli maliyet
                                    order_total_product_cost += cost

                            if not cost_calculation_possible: # Eğer maliyeti bulunamayan barkod varsa
                                reason = f"Ürün Maliyeti Bulunamadı ({', '.join(missing_barcodes_in_this_order)})"

                    # Eğer maliyet hesaplanamadıysa veya başka bir sebep varsa, bu siparişi hariç tut
                    if not cost_calculation_possible or reason:
                        other_excluded_temp.append({
                            "order_number": order_number, "merchant_sku": merchant_sku,
                            "status": order_status, "reason": reason or "Bilinmeyen Maliyet Hatası",
                            "barcode": display_barcode_in_excluded, # Virgülle ayrılmış olabilir
                        })
                        if order_id_attr: processed_order_ids.add(order_id_attr)
                        continue # Bu siparişi atla, sonraki siparişe geç

                    # ----- Geçerli Sipariş Maliyetleri ve Kâr Hesapları -----
                    cost_try_val = order_total_product_cost # Bu siparişteki tüm ürünlerin toplam maliyeti
                    commission_val = float(getattr(o, 'commission', 0) or 0)
                    if commission_val == 0.0 and float(getattr(o, 'amount', 0) or 0) > 0: # Ciro varsa ama komisyon 0'sa uyar
                        logging.warning(f"Sipariş {order_number} ({merchant_sku}) için komisyon sıfır, ciro: {getattr(o, 'amount', 0)}.")

                    line_package_cost = package_cost_per_item * num_barcodes_in_order

                    base_shipping_cost_for_order = form_shipping_cost_float 
                    additional_shipping_cost_for_order = 0.0
                    if num_barcodes_in_order > 1:
                        additional_shipping_cost_for_order = (num_barcodes_in_order - 1) * 30.0
                    line_shipping_cost_for_order = base_shipping_cost_for_order + additional_shipping_cost_for_order

                    amount_val = float(getattr(o, 'amount', 0) or 0)
                    discount_val = float(getattr(o, 'discount', 0) or 0)
                    net_income = amount_val - discount_val
                    order_expenses_initial = commission_val + cost_try_val + line_package_cost + line_shipping_cost_for_order
                    profit_initial = net_income - order_expenses_initial

                    total_revenue += amount_val
                    total_discount_sum += discount_val
                    total_commission_sum += commission_val
                    total_product_cost_sum += cost_try_val
                    total_package_cost_period += line_package_cost
                    total_outgoing_shipping_cost_period += line_shipping_cost_for_order
                    total_expenses_minus_employee += order_expenses_initial
                    total_profit_minus_employee += profit_initial
                    processed_order_count += 1
                    total_barcodes_processed_in_analysis += num_barcodes_in_order # Sadece analize dahil olanların barkod sayısı
                    profit_margin_initial = (profit_initial / net_income * 100) if net_income > 0 else 0.0

                    # Tekil SKU yerine sipariş bazlı başlıkları kullan
                    order_display_title = " / ".join(sorted(list(current_order_titles))) or merchant_sku

                    product_summary[order_display_title]["total_profit"] += profit_initial
                    product_summary[order_display_title]["total_commission"] += commission_val
                    product_summary[order_display_title]["total_discount"] += discount_val
                    product_summary[order_display_title]["count"] += 1
                    product_summary[order_display_title]["titles"].update(current_order_titles)


                    analysis_temp.append({
                        "order_number": order_number, "merchant_sku": merchant_sku, "status": order_status,
                        "product_barcode": product_barcode_raw, # Virgüllü ham barkodlar
                        "num_barcodes": num_barcodes_in_order,
                        "amount": amount_val, "discount": discount_val, "net_income": net_income,
                        "commission": commission_val, "product_cost": cost_try_val,
                        "package_cost": line_package_cost,
                        "shipping_cost": line_shipping_cost_for_order,
                        "employee_cost": 0.0, # Henüz atanmadı
                        "total_expenses": order_expenses_initial, # Henüz personel dahil değil
                        "profit": profit_initial, # Henüz personel dahil değil
                        "profit_margin": profit_margin_initial, # Henüz personel dahil değil
                    })
                    if order_id_attr: processed_order_ids.add(order_id_attr)

                except Exception as e:
                    logging.error("Sipariş işlenirken hata (ID=%s, No=%s): %s", order_id_attr, order_number, e, exc_info=True)
                    flash(f"'{order_number}' numaralı sipariş işlenirken beklenmedik bir hata oluştu. Detaylar log dosyasında.", "error")
                    other_excluded_temp.append({
                        "order_number": order_number, "merchant_sku": merchant_sku, "status": order_status,
                        "reason": f"İç Hata: {str(e)[:100]}", # Hata mesajını kısalt
                        "barcode": getattr(o, "product_barcode", "BARKOD_HATA"),
                    })
                    if order_id_attr: processed_order_ids.add(order_id_attr)

            if processed_order_count == 0 and not (cancelled_orders_temp or returned_orders_temp or other_excluded_temp) and not missing_cost_entries_list:
                 # Eğer hiçbir işlem yapılmadıysa (ne analiz, ne hariç tutma, ne de maliyet eksiği)
                 flash("Belirtilen tarih aralığında hiçbir sipariş bulunamadı veya filtrelere takıldı.", "info")
                 context["now"] = datetime.now()
                 return render_template("profit.html", **context)
            elif processed_order_count == 0 and not missing_cost_entries_list:
                 # Analiz edilecek sipariş yok ama hariç tutulanlar var VEYA maliyet eksiği yok
                 flash("Analize dahil edilecek geçerli sipariş bulunamadı. Hariç tutulanları veya maliyet girilecekleri kontrol edin.", "warning")
                 # Bu durumda bile özet ve hariç tutulan tablolar gösterilmeli

            per_barcode_employee_cost = 0.0
            total_employee_cost_period = 0.0
            if monthly_employee_salary > 0 and days_in_range > 0:
                try:
                    # Ayın gün sayısını doğru hesapla (her ay farklı olabilir)
                    # Basitlik için ortalama 30 gün kullanabiliriz veya daha hassas olabiliriz.
                    # Şimdilik ayın ilk gününü baz alarak o ayın gün sayısını alalım.
                    # Ya da basitçe günlük maliyeti hesaplayalım.
                    daily_salary_total = monthly_employee_salary / 30.4375 # Ortalama gün sayısı
                    total_employee_cost_period = daily_salary_total * days_in_range

                    if total_barcodes_processed_in_analysis > 0: # Sadece analize dahil edilen barkod sayısına böl
                        per_barcode_employee_cost = total_employee_cost_period / total_barcodes_processed_in_analysis
                        logging.info(f"Personel maliyeti ({days_in_range} gün): {total_employee_cost_period:.2f} TL | Barkod başı ({total_barcodes_processed_in_analysis} barkod): {per_barcode_employee_cost:.2f} TL")
                    else:
                         logging.info(f"Personel maliyeti ({days_in_range} gün): {total_employee_cost_period:.2f} TL | Analize dahil barkod yok, dağıtılamadı.")
                except Exception as e:
                     logging.error("Personel maliyeti hesaplanırken hata: %s", e, exc_info=True)
                     flash("Personel maliyeti hesaplanırken bir hata oluştu.", "error")

            if per_barcode_employee_cost > 0:
                 for item in analysis_temp:
                     item_total_employee_cost = per_barcode_employee_cost * item['num_barcodes']
                     item["employee_cost"] = item_total_employee_cost
                     item["total_expenses"] += item_total_employee_cost
                     item["profit"] -= item_total_employee_cost
                     item["profit_margin"] = (item["profit"] / item["net_income"] * 100) if item["net_income"] > 0 else 0.0

            final_total_profit = total_profit_minus_employee - total_employee_cost_period - total_return_shipping_cost # İade kargo maliyetini de düş
            final_total_expenses = total_expenses_minus_employee + total_employee_cost_period + total_return_shipping_cost
            final_avg_profit = final_total_profit / processed_order_count if processed_order_count > 0 else 0.0
            total_net_income_sum = total_revenue - total_discount_sum
            final_avg_profit_margin = (final_total_profit / total_net_income_sum * 100) if total_net_income_sum > 0 else 0.0

            # product_summary'deki SKU'ları daha anlamlı hale getir (örneğin ilk ürün başlığını al)
            formatted_product_summary = []
            for display_title_key, data in product_summary.items():
                # display_title_key zaten birleşik başlıklar veya SKU
                sku_for_display = display_title_key # Anahtarın kendisi SKU gibi kullanılabilir.

                adjusted_profit_for_sku = data['total_profit'] * sku_profit_adjustment_factor if total_profit_minus_employee > 0 and final_total_profit >= 0 else 0
                formatted_product_summary.append({
                    "sku": sku_for_display, # Artık bu order_display_title
                    "total_profit": adjusted_profit_for_sku,
                    "total_commission": data['total_commission'],
                    "total_discount": data['total_discount'],
                    "count": data['count'],
                    "total_profit_str": format_number(adjusted_profit_for_sku),
                    "total_commission_str": format_number(data['total_commission']),
                    "total_discount_str": format_number(data['total_discount'])
                })

            top_profit_products = sorted(formatted_product_summary, key=lambda x: x["total_profit"], reverse=True)[:10]
            top_commission_products = sorted(formatted_product_summary, key=lambda x: x["total_commission"], reverse=True)[:10]
            top_discount_products = sorted(formatted_product_summary, key=lambda x: x["total_discount"], reverse=True)[:10]


            for item in analysis_temp:
                for key_item in ['amount', 'discount', 'net_income', 'commission', 'product_cost', 'package_cost', 'shipping_cost', 'employee_cost', 'total_expenses', 'profit']:
                    item[key_item + '_str'] = format_number(item[key_item])
                item['profit_margin_str'] = "{:.2f}".format(item['profit_margin']).replace(".",",") # Kâr marjı formatı

            context.update({
                "analysis": analysis_temp, "cancelled_orders": cancelled_orders_temp,
                "returned_orders": returned_orders_temp, "other_excluded_orders": other_excluded_temp,
                "missing_cost_entries": missing_cost_entries_list, # Artık title da içeriyor
                "order_count": processed_order_count,
                "total_barcodes_processed": total_barcodes_processed_in_analysis, # Sadece analize dahil edilenler
                "total_profit": final_total_profit, "avg_profit": final_avg_profit,
                "total_revenue": total_revenue, "total_discount_sum": total_discount_sum,
                "total_expenses_sum": final_total_expenses,
                "total_commission_sum": total_commission_sum, "total_product_cost_sum": total_product_cost_sum,
                "avg_profit_margin": final_avg_profit_margin,
                "total_employee_cost_period": total_employee_cost_period,
                "total_package_cost_period": total_package_cost_period,
                "total_shipping_cost_period": total_outgoing_shipping_cost_period, 
                "total_return_shipping_cost": total_return_shipping_cost, 
                "top_profit_products": top_profit_products, 
                "top_commission_products": top_commission_products,
                "top_discount_products": top_discount_products,
                "total_profit_str": format_number(final_total_profit), 
                "avg_profit_str": format_number(final_avg_profit),
                "total_revenue_str": format_number(total_revenue), 
                "total_discount_sum_str": format_number(total_discount_sum),
                "total_expenses_sum_str": format_number(final_total_expenses),
                "total_commission_sum_str": format_number(total_commission_sum), 
                "total_product_cost_sum_str": format_number(total_product_cost_sum),
                "total_employee_cost_period_str": format_number(total_employee_cost_period),
                "total_package_cost_period_str": format_number(total_package_cost_period),
                "total_shipping_cost_period_str": format_number(total_outgoing_shipping_cost_period), 
                "total_return_shipping_cost_str": format_number(total_return_shipping_cost), 
                "shipping_cost_str": context["shipping_cost_str"], 
                "avg_profit_margin_str": "{:.2f}".format(final_avg_profit_margin).replace(".",",")
            })
            # Gerekirse SKU özetini de context'e ekle
            context["product_summary_for_charts"] = formatted_product_summary


        except ValueError as ve:
            logging.error("Form verisi hatası (ValueError): %s", ve, exc_info=True)
            flash(f"Lütfen maliyetleri, maaşı ve kargoyu geçerli bir sayı olarak girin (Örn: 123,45 veya 123.45). Hata: {ve}", "error")
        except Exception as e:
            logging.error("Kâr analizi sırasında genel hata oluştu: %s", e, exc_info=True)
            flash(f"Analiz sırasında beklenmedik bir hata oluştu: {e}. Detaylar log dosyasında.", "error")

        # Her durumda (başarılı veya hatalı POST sonrası) 'now' değişkenini context'e ekle
        context["now"] = datetime.now()


    return render_template("profit.html", **context)