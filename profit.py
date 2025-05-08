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
    ReturnProduct,
    db,
    OrderCreated,
    OrderPicking,
    OrderShipped,
    OrderDelivered,
    OrderCancelled,
    Product,
    ReturnOrder,
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
        formatted = "{:,.2f}".format(float_value).replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted
    except (TypeError, ValueError):
        logging.warning(f"'{value}' değeri formatlanamadı, string olarak döndürülüyor.")
        try:
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
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")

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
                start_date=start_date, end_date=end_date,
                package_cost=request.form.get("package_cost", ""),
                monthly_employee_salary=request.form.get("monthly_employee_salary", ""),
                shipping_cost=request.form.get("shipping_cost", ""),
                auto_reload="1",
            )
           )

    try:
        existing_products = Product.query.filter(Product.barcode.in_(updates.keys())).all()
        existing_barcodes = {p.barcode for p in existing_products}

        for prod in existing_products:
             if prod.barcode in updates:
                 prod.cost_try = updates[prod.barcode]

        missing_barcodes = set(updates.keys()) - existing_barcodes
        for bc in missing_barcodes:
            try:
                new_product = Product(
                    barcode=bc,
                    cost_try=updates[bc],
                    # --- Aşağısı Product modelindeki zorunlu alanlara göre doldurulacak ---
                    title=f"Oto-Eklenen: {bc}", # Örnek
                    product_main_id=None,       # Örnek (Boş bırakılabilirse)
                    quantity=0,                 # Örnek
                    images=None,                # Örnek (JSON veya text alanıysa None/boş string olabilir)
                    variants=None,              # Örnek
                    size="",                    # Örnek
                    color="",                   # Örnek
                    archived=False,             # Örnek (Boolean)
                    locked=False,               # Örnek (Boolean)
                    on_sale=False,              # Örnek (Boolean)
                    reject_reason=None,         # Örnek (Boş bırakılabilirse)
                    sale_price=0.0,             # Örnek
                    list_price=0.0,             # Örnek
                    currency_type="TRY"         # Örnek (Varsayılan para birimi)
                    # --- EĞER BAŞKA ZORUNLU ALAN VARSA EKLE ---
                )
                db.session.add(new_product)
            except TypeError as te:
                db.session.rollback()
                logging.error(f"'{bc}' barkodlu yeni ürün oluşturulurken TypeError: {te}. Zorunlu alanlar eksik/yanlış.", exc_info=True)
                flash(f"'{bc}' barkodlu ürün için maliyet kaydedilemedi. Ürün tablosundaki zorunlu alanlar eksik/yanlış. Detaylar log dosyasında.", "error")
                continue

        db.session.commit()
        flash(f"{len(updates)} adet maliyet güncellendi/eklendi.", "success")

    except Exception as e:
        db.session.rollback()
        logging.error("Maliyetler kaydedilirken hata: %s", e, exc_info=True)
        if not isinstance(e, TypeError):
             flash(f"Maliyetler kaydedilemedi. Veritabanı hatası: {e}", "error")

    return redirect(
        url_for(
            "profit.profit_report",
            start_date=start_date, end_date=end_date,
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

    context = {
         "analysis": [], "cancelled_orders": [], "returned_orders": [], "other_excluded_orders": [],
        "top_profit_products": [], "top_commission_products": [], "top_discount_products": [],
        "missing_cost_entries": [], "total_records_found": 0,
        "total_profit": 0.0, "avg_profit": 0.0, "total_revenue": 0.0, "total_discount_sum": 0.0,
        "total_expenses_sum": 0.0, "total_commission_sum": 0.0, "total_product_cost_sum": 0.0,
        "total_employee_cost_period": 0.0, "total_package_cost_period": 0.0,
        "total_shipping_cost_period": 0.0, "total_return_shipping_cost": 0.0,
        "avg_profit_margin": 0.0, "order_count": 0, "total_barcodes_processed": 0,
        "start_date": form_source.get("start_date", ""), "end_date": form_source.get("end_date", ""),
        "package_cost": form_source.get("package_cost", ""),
        "monthly_employee_salary": form_source.get("monthly_employee_salary", ""),
        "shipping_cost": form_source.get("shipping_cost", ""), # Formdaki değer (baz ve iade için)
        "total_profit_str": "0,00", "avg_profit_str": "0,00", "total_revenue_str": "0,00",
        "total_discount_sum_str": "0,00", "total_expenses_sum_str": "0,00",
        "total_commission_sum_str": "0,00", "total_product_cost_sum_str": "0,00",
        "total_employee_cost_period_str": "0,00", "total_package_cost_period_str": "0,00",
        "total_shipping_cost_period_str": "0,00", "total_return_shipping_cost_str": "0,00",
        "shipping_cost_str": "0,00", "avg_profit_margin_str": "0.00",
    }
    try:
        # Formdaki kargo maliyetini iadeler ve baz giden kargo için saklayalım
        form_shipping_cost_float = float((context["shipping_cost"] or '0').replace(',', '.'))
        context["shipping_cost_str"] = format_number(form_shipping_cost_float) # Formda göstermek için
    except ValueError:
        form_shipping_cost_float = 0.0 # Hatalıysa 0 kullan
        context["shipping_cost_str"] = "Hatalı Giriş"


    if request.method == "POST" or request.args.get("auto_reload") == "1":
        analysis_temp = []
        cancelled_orders_temp = []
        returned_orders_temp = []
        other_excluded_temp = []
        missing_cost_barcodes = set()
        missing_cost_entries_list = []
        product_summary = defaultdict(lambda: {"total_profit": 0.0, "total_commission": 0.0, "total_discount": 0.0, "count": 0})

        total_profit_minus_employee = 0.0
        total_revenue = 0.0
        total_discount_sum = 0.0
        total_expenses_minus_employee = 0.0
        total_commission_sum = 0.0
        total_product_cost_sum = 0.0
        total_package_cost_period = 0.0
        total_outgoing_shipping_cost_period = 0.0 # GİDEN kargo maliyeti toplamı
        total_return_shipping_cost = 0.0 # İade kargo maliyeti toplamı
        processed_order_count = 0
        total_barcodes_processed = 0
        total_records_found = 0

        try:
            package_cost_per_item = float((context["package_cost"] or '0').replace(',', '.'))
            monthly_employee_salary = float((context["monthly_employee_salary"] or '0').replace(',', '.'))
            # form_shipping_cost_float yukarıda tanımlandı

            start_date_str = context["start_date"]
            end_date_str = context["end_date"]
            if not start_date_str or not end_date_str:
                flash("Başlangıç ve Bitiş tarihleri zorunludur.", "error")
                return render_template("profit.html", **context)
            start_date_obj = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date_obj_inclusive = datetime.strptime(end_date_str, "%Y-%m-%d") + timedelta(days=1, microseconds=-1)
            days_in_range = (datetime.strptime(end_date_str, "%Y-%m-%d") - start_date_obj).days + 1
            if days_in_range <= 0:
                flash("Bitiş tarihi başlangıç tarihinden önce olamaz.", "error")
                return render_template("profit.html", **context)

            logging.info(f"Form Girdileri - Paket/adet: {package_cost_per_item}, Aylık Maaş: {monthly_employee_salary}, Baz/İade Kargo: {form_shipping_cost_float}, Başlangıç: {start_date_str}, Bitiş: {end_date_str}")
            logging.info(f"Tarih aralığındaki gün sayısı: {days_in_range}")
            db_query_end_date = end_date_obj_inclusive
            cancelled_order_numbers = set()
            returned_order_numbers = set()

            # -- İptal & iade siparişleri çek
            try:
                # İptal Edilenler
                cancelled_orders_query = (
                    OrderCancelled.query.with_entities(
                        OrderCancelled.order_number, OrderCancelled.merchant_sku,
                        OrderCancelled.status, OrderCancelled.product_barcode
                    ).filter(
                        OrderCancelled.order_date >= start_date_obj,
                        OrderCancelled.order_date <= db_query_end_date,
                    ).all()
                )
                cancelled_orders_temp = []
                for o in cancelled_orders_query:
                     barcode_val = o[3] if len(o) > 3 else None
                     if o[0]:
                         cancelled_orders_temp.append({
                             "order_number": o[0], "merchant_sku": o[1], "status": o[2],
                             "barcode": barcode_val, "reason": "İptal Edildi",
                         })
                cancelled_order_numbers = {item["order_number"] for item in cancelled_orders_temp if item["order_number"]}
                logging.info(f"{len(cancelled_order_numbers)} adet iptal edilmiş sipariş listelendi.")

                # İade Edilenler
                # !!! JOIN koşulunu kontrol et !!!
                returned_orders_query_result = (
                    ReturnOrder.query
                    .join(ReturnProduct, ReturnOrder.id == ReturnProduct.return_order_id)
                    .with_entities(
                        ReturnOrder.order_number, ReturnOrder.status,
                        ReturnOrder.return_reason, ReturnProduct.barcode,
                    ).filter(
                        ReturnOrder.return_date >= start_date_obj,
                        ReturnOrder.return_date <= db_query_end_date,
                    ).all()
                )
                returned_orders_temp = []
                temp_returned_nos = set()
                total_return_shipping_cost = 0.0

                for o in returned_orders_query_result:
                    order_num = o[0]
                    barcode_val = o[3] if len(o) > 3 else None
                    if order_num and order_num not in temp_returned_nos:
                        return_shipping_cost_per_order = form_shipping_cost_float # İade için formdaki değer
                        total_return_shipping_cost += return_shipping_cost_per_order
                        returned_orders_temp.append({
                            "order_number": order_num, "status": o[1],
                            "reason": f"İade Edildi ({o[2] or 'Belirtilmemiş'})",
                            "barcode": barcode_val,
                            "cost": return_shipping_cost_per_order
                        })
                        temp_returned_nos.add(order_num)
                returned_order_numbers = temp_returned_nos
                logging.info(f"{len(returned_order_numbers)} adet iade edilmiş sipariş listelendi.")
                logging.info(f"Toplam iade kargo maliyeti: {total_return_shipping_cost:.2f} TL")

            except AttributeError as ae:
                 logging.error("İptal/İade sorgusunda model hatası: %s", ae, exc_info=True)
                 flash(f"Veritabanı modeli hatası: İptal/iade bilgileri çekilemedi ({ae}).", "error")
                 return render_template("profit.html", **context)
            except Exception as e:
                logging.error("İptal/İade siparişleri çekilirken genel hata: %s", e, exc_info=True)
                flash(f"İptal veya iade bilgileri çekilirken bir sorun oluştu: {e}", "warning")

            # -- Aktif siparişler --
            orders = []
            table_classes = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered]
            all_individual_barcodes = set()
            logging.info("Ana sipariş tabloları sorgulanıyor...")
            all_excluded_order_nos = cancelled_order_numbers.union(returned_order_numbers)
            total_records_found = len(all_excluded_order_nos)
            for cls in table_classes:
                try:
                    results = (
                        cls.query.filter(
                            cls.order_date >= start_date_obj,
                            cls.order_date <= db_query_end_date,
                        )
                        .filter(cls.order_number.notin_(all_excluded_order_nos))
                        .all()
                    )
                    count = len(results)
                    logging.info(f"{cls.__tablename__}: {count} adet potansiyel kayıt bulundu.")
                    total_records_found += count
                    orders.extend(results)
                    for o in results:
                        product_barcode_raw = getattr(o, "product_barcode", None)
                        if product_barcode_raw and product_barcode_raw.strip():
                            individual_barcodes_list = [b.strip() for b in product_barcode_raw.split(',') if b.strip()]
                            all_individual_barcodes.update(individual_barcodes_list)
                except Exception as e:
                    logging.error("Tablo sorgulanırken hata (%s): %s", cls.__tablename__, e, exc_info=True)
                    flash(f"{cls.__tablename__} tablosu sorgulanırken bir veritabanı hatası oluştu.", "error")

            logging.info(f"İncelenecek (iptal/iade olmayan) sipariş sayısı: {len(orders)}")
            context["total_records_found"] = total_records_found

            if not orders:
                if cancelled_orders_temp or returned_orders_temp:
                     flash("Belirtilen tarih aralığında analize dahil edilecek aktif sipariş bulunamadı (Sadece iptal/iadeler listeleniyor).", "info")
                else:
                     flash("Belirtilen tarih aralığında işlenecek hiçbir kayıt (aktif, iptal, iade) bulunamadı.", "info")
                context.update({
                    "analysis": [], "cancelled_orders": cancelled_orders_temp, "returned_orders": returned_orders_temp,
                    "other_excluded_orders": [], "missing_cost_entries": [],
                })
                context["total_return_shipping_cost_str"] = format_number(total_return_shipping_cost)
                return render_template("profit.html", **context)

            # --- Ürün maliyetlerini çek ---
            product_costs = {}
            if all_individual_barcodes:
                  try:
                    products = Product.query.filter(Product.barcode.in_(all_individual_barcodes)).all()
                    product_costs = {p.barcode.strip(): float(p.cost_try)
                                     for p in products
                                     if p.barcode and p.barcode.strip() in all_individual_barcodes and p.cost_try is not None}
                    logging.info(f"{len(product_costs)}/{len(all_individual_barcodes)} *tekil* barkod için maliyet bulundu (None olmayan).")
                  except Exception as e:
                    logging.error("Ürün maliyetleri çekilirken hata: %s", e, exc_info=True)
                    flash("Ürün maliyetleri alınırken bir veritabanı hatası oluştu.", "error")
            else:
                 logging.warning("Maliyet çekmek için geçerli tekil barkod bulunamadı.")

            processed_order_ids = set()

            # -- Sipariş işleme döngüsü --
            for o in orders:
                order_id = getattr(o, "id", None)
                order_number = getattr(o, "order_number", "N/A")
                merchant_sku = getattr(o, "merchant_sku", None) or f"SKU_{order_id or 'UnknownID'}"
                order_status = getattr(o, "status", "Bilinmiyor")

                if order_id and order_id in processed_order_ids:
                    continue

                try:
                    product_barcode_raw = getattr(o, "product_barcode", None)
                    reason = None
                    order_total_product_cost = 0.0
                    cost_calculation_possible = True
                    display_barcode_in_excluded = product_barcode_raw or f"BARKODSUZ_{order_id or 'ID'}"
                    num_barcodes_in_order = 0
                    individual_barcodes_in_order = []

                    if not product_barcode_raw or not product_barcode_raw.strip():
                        reason = "Barkod Boş/Yok"
                        cost_calculation_possible = False
                    else:
                        individual_barcodes_in_order = [b.strip() for b in product_barcode_raw.split(',') if b.strip()]
                        num_barcodes_in_order = len(individual_barcodes_in_order)
                        if num_barcodes_in_order == 0:
                            reason = "Geçersiz Barkod Formatı"
                            cost_calculation_possible = False
                        else:
                            missing_barcodes_in_this_order = []
                            for bc in individual_barcodes_in_order:
                                cost = product_costs.get(bc)
                                if cost is None:
                                    cost_calculation_possible = False
                                    missing_barcodes_in_this_order.append(bc)
                                    if bc not in missing_cost_barcodes:
                                        missing_cost_entries_list.append({"barcode": bc, "merchant_sku": f"{merchant_sku} ({bc})"})
                                        missing_cost_barcodes.add(bc)
                                elif cost <= 0:
                                    logging.warning(f"Sipariş {order_number}, Barkod '{bc}' maliyeti sıfır veya negatif. Hesaplamada 0 olarak kullanıldı.")
                                    order_total_product_cost += 0.0
                                else:
                                    order_total_product_cost += cost
                            if not cost_calculation_possible:
                                reason = f"Ürün Maliyeti Bulunamadı ({', '.join(missing_barcodes_in_this_order)})"

                    if not cost_calculation_possible or reason:
                        other_excluded_temp.append({
                            "order_number": order_number, "merchant_sku": merchant_sku,
                            "status": order_status, "reason": reason or "Bilinmeyen Maliyet Hatası",
                            "barcode": display_barcode_in_excluded,
                        })
                        if order_id: processed_order_ids.add(order_id)
                        continue

                    # ----- Geçerli Sipariş Maliyetleri -----
                    cost_try_val = order_total_product_cost
                    commission_val = float(getattr(o, 'commission', 0) or 0)
                    if commission_val == 0.0:
                        logging.warning(f"Sipariş {order_number} ({merchant_sku}) için komisyon sıfır.")

                    # Paket Maliyeti
                    line_package_cost = package_cost_per_item * num_barcodes_in_order

                    # ◄◄◄ KARGO MALİYETİ HESAPLAMA (İSTEĞE GÖRE GÜNCELLENDİ) ►►►
                    base_shipping_cost = form_shipping_cost_float # Formdan gelen baz maliyet
                    additional_shipping_cost = 0.0
                    if num_barcodes_in_order > 1:
                        # İkinci ve sonraki her ürün için +30 TL ekle
                        additional_shipping_cost = (num_barcodes_in_order - 1) * 30.0
                    line_shipping_cost = base_shipping_cost + additional_shipping_cost # Nihai giden kargo maliyeti

                    # --- Kâr Hesapları ---
                    amount_val = float(getattr(o, 'amount', 0) or 0)
                    discount_val = float(getattr(o, 'discount', 0) or 0)
                    net_income = amount_val - discount_val
                    order_expenses_initial = commission_val + cost_try_val + line_package_cost + line_shipping_cost
                    profit_initial = net_income - order_expenses_initial

                    # --- Toplamları Güncelle ---
                    total_revenue += amount_val
                    total_discount_sum += discount_val
                    total_commission_sum += commission_val
                    total_product_cost_sum += cost_try_val
                    total_package_cost_period += line_package_cost
                    total_outgoing_shipping_cost_period += line_shipping_cost #◄◄◄ Güncellendi
                    total_expenses_minus_employee += order_expenses_initial
                    total_profit_minus_employee += profit_initial
                    processed_order_count += 1
                    total_barcodes_processed += num_barcodes_in_order
                    profit_margin_initial = (profit_initial / net_income * 100) if net_income > 0 else 0.0

                    # --- SKU Özeti (Basit) ---
                    product_summary[merchant_sku]["total_profit"] += profit_initial
                    product_summary[merchant_sku]["total_commission"] += commission_val
                    product_summary[merchant_sku]["total_discount"] += discount_val
                    product_summary[merchant_sku]["count"] += 1

                    # --- Analiz Listesi ---
                    analysis_temp.append({
                        "order_number": order_number, "merchant_sku": merchant_sku, "status": order_status,
                        "product_barcode": product_barcode_raw,
                        "num_barcodes": num_barcodes_in_order,
                        "amount": amount_val, "discount": discount_val, "net_income": net_income,
                        "commission": commission_val, "product_cost": cost_try_val,
                        "package_cost": line_package_cost,
                        "shipping_cost": line_shipping_cost, #◄◄◄ Güncellendi
                        "employee_cost": 0.0,
                        "total_expenses": order_expenses_initial,
                        "profit": profit_initial,
                        "profit_margin": profit_margin_initial,
                    })
                    if order_id: processed_order_ids.add(order_id)

                except Exception as e:
                    logging.error("Sipariş işlenirken hata (ID=%s, No=%s): %s", order_id, order_number, e, exc_info=True)
                    flash(f"'{order_number}' numaralı sipariş işlenirken beklenmedik bir hata oluştu. Detaylar log dosyasında.", "error")
                    other_excluded_temp.append({
                        "order_number": order_number, "merchant_sku": merchant_sku, "status": order_status,
                        "reason": f"İşlem Hatası: {e}", "barcode": getattr(o, "product_barcode", "BARKOD OKUNAMADI"),
                    })
                    if order_id: processed_order_ids.add(order_id)
            # -- /Sipariş işleme döngüsü

            if processed_order_count == 0 and not analysis_temp:
                 flash("Analiz edilecek geçerli sipariş bulunamadı (Maliyet eksik, iptal/iade veya diğer nedenlerle tümü hariç tutulmuş olabilir).", "warning")
                 context.update({
                     "analysis": [], "cancelled_orders": cancelled_orders_temp, "returned_orders": returned_orders_temp,
                     "other_excluded_orders": other_excluded_temp, "missing_cost_entries": missing_cost_entries_list,
                     "total_return_shipping_cost": total_return_shipping_cost,
                     "total_return_shipping_cost_str": format_number(total_return_shipping_cost),
                 })
                 return render_template("profit.html", **context)

            # -- Personel maliyetini hesapla (BARKOD başına) --
            per_barcode_employee_cost = 0.0
            total_employee_cost_period = 0.0
            if monthly_employee_salary > 0 and days_in_range > 0:
                try:
                    days_in_month = calendar.monthrange(start_date_obj.year, start_date_obj.month)[1]
                    daily_salary = monthly_employee_salary / days_in_month
                    total_employee_cost_period = daily_salary * days_in_range
                    if total_barcodes_processed > 0:
                        per_barcode_employee_cost = total_employee_cost_period / total_barcodes_processed
                        logging.info(f"Personel maliyeti ({days_in_range} gün): {total_employee_cost_period:.2f} TL | Barkod başı ({total_barcodes_processed} barkod): {per_barcode_employee_cost:.2f} TL")
                    else:
                         logging.info(f"Personel maliyeti ({days_in_range} gün): {total_employee_cost_period:.2f} TL | Barkod yok, dağıtılamadı.")
                except Exception as e:
                     logging.error("Personel maliyeti hesaplanırken hata: %s", e, exc_info=True)
                     flash("Personel maliyeti hesaplanırken bir hata oluştu.", "error")
                     per_barcode_employee_cost = 0.0
                     total_employee_cost_period = 0.0

            # -- Hesaplanan personel maliyetini sipariş satırlarına dağıt --
            if per_barcode_employee_cost > 0:
                 for item in analysis_temp:
                     item_total_employee_cost = per_barcode_employee_cost * item['num_barcodes']
                     item["employee_cost"] = item_total_employee_cost
                     item["total_expenses"] += item_total_employee_cost
                     item["profit"] -= item_total_employee_cost
                     item["profit_margin"] = (item["profit"] / item["net_income"] * 100 if item["net_income"] > 0 else 0)

            # -- Nihai Kâr/Zarar Toplamları --
            final_total_profit = total_profit_minus_employee - total_employee_cost_period
            final_total_expenses = total_expenses_minus_employee + total_employee_cost_period + total_return_shipping_cost # İade kargo da genel gidere dahil
            final_avg_profit = final_total_profit / processed_order_count if processed_order_count > 0 else 0.0
            total_net_income_sum = total_revenue - total_discount_sum
            final_avg_profit_margin = (final_total_profit / total_net_income_sum * 100 if total_net_income_sum > 0 else 0.0)

            # Top listeler (SKU karı yaklaşık)
            product_summary_list = [{"sku": sku, **data} for sku, data in product_summary.items()]
            sku_profit_adjustment_factor = (final_total_profit / total_profit_minus_employee) if total_profit_minus_employee > 0 and final_total_profit >= 0 else 0
            for item in product_summary_list:
                adjusted_profit = item['total_profit'] * sku_profit_adjustment_factor
                item['total_profit_str'] = format_number(adjusted_profit)
                item['total_commission_str'] = format_number(item['total_commission'])
                item['total_discount_str'] = format_number(item['total_discount'])
                item['total_profit'] = adjusted_profit # Sıralama için güncelle
            top_profit_products = sorted(product_summary_list, key=lambda x: x["total_profit"], reverse=True)[:10]
            top_commission_products = sorted(product_summary_list, key=lambda x: x["total_commission"], reverse=True)[:10]
            top_discount_products = sorted(product_summary_list, key=lambda x: x["total_discount"], reverse=True)[:10]

            # Analiz listesini formatla
            for item in analysis_temp:
                for key in ['amount', 'discount', 'net_income', 'commission', 'product_cost', 'package_cost', 'shipping_cost', 'employee_cost', 'total_expenses', 'profit']:
                    item[key + '_str'] = format_number(item[key])
                item['profit_margin_str'] = format_number(item['profit_margin']).replace(",",".")

            # Context güncelle
            context.update({
                "analysis": analysis_temp, "cancelled_orders": cancelled_orders_temp,
                "returned_orders": returned_orders_temp, "other_excluded_orders": other_excluded_temp,
                "missing_cost_entries": missing_cost_entries_list,
                "order_count": processed_order_count,
                "total_barcodes_processed": total_barcodes_processed,
                "total_profit": final_total_profit, "avg_profit": final_avg_profit,
                "total_revenue": total_revenue, "total_discount_sum": total_discount_sum,
                "total_expenses_sum": final_total_expenses,
                "total_commission_sum": total_commission_sum, "total_product_cost_sum": total_product_cost_sum,
                "avg_profit_margin": final_avg_profit_margin,
                "total_employee_cost_period": total_employee_cost_period,
                "total_package_cost_period": total_package_cost_period,
                "total_shipping_cost_period": total_outgoing_shipping_cost_period, # Giden Kargo Toplamı
                "total_return_shipping_cost": total_return_shipping_cost, # İade Kargo Toplamı
                "top_profit_products": top_profit_products, "top_commission_products": top_commission_products,
                "top_discount_products": top_discount_products,
                "total_profit_str": format_number(final_total_profit), "avg_profit_str": format_number(final_avg_profit),
                "total_revenue_str": format_number(total_revenue), "total_discount_sum_str": format_number(total_discount_sum),
                "total_expenses_sum_str": format_number(final_total_expenses),
                "total_commission_sum_str": format_number(total_commission_sum),
                "total_product_cost_sum_str": format_number(total_product_cost_sum),
                "total_employee_cost_period_str": format_number(total_employee_cost_period),
                "total_package_cost_period_str": format_number(total_package_cost_period),
                "total_shipping_cost_period_str": format_number(total_outgoing_shipping_cost_period), # Giden Kargo str
                "total_return_shipping_cost_str": format_number(total_return_shipping_cost), # İade Kargo str
                "shipping_cost_str": context["shipping_cost_str"], # Formdaki baz/iade kargo str
                "avg_profit_margin_str": format_number(final_avg_profit_margin).replace(",",".")
            })

        except ValueError as ve:
            logging.error("Form verisi hatası (ValueError): %s", ve, exc_info=True)
            flash(f"Lütfen maliyetleri, maaşı ve kargoyu geçerli bir sayı olarak girin (Örn: 123,45). Hata: {ve}", "error")
            return render_template("profit.html", **context)
        except Exception as e:
            logging.error("Kâr analizi sırasında genel hata oluştu: %s", e, exc_info=True)
            flash(f"Analiz sırasında beklenmedik bir hata oluştu: {e}. Detaylar log dosyasında.", "error")
            return render_template("profit.html", **context)

    # GET isteği veya POST sonrası render
    return render_template("profit.html", **context)