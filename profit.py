# profit.py
from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
    jsonify,
)
from datetime import datetime, timedelta
import logging
import calendar
import requests as http_requests
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, getcontext

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
    ModelMaliyet,
    ModelDirekMaliyet,
)
# --------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

profit_bp = Blueprint("profit", __name__, url_prefix="/profit")

# Parasal hesaplar için hassasiyet
getcontext().prec = 28

# --------------------------------------------------------------------------
# Döviz Kuru (Harem Altın → fallback: exchangerate-api)
# --------------------------------------------------------------------------
_kur_cache = {"value": None, "ts": None}

def _fetch_usd_try() -> float | None:
    """Güncel USD/TL kurunu çek. Önce Harem Altın, sonra fallback."""
    # Cache: 10 dakika
    if _kur_cache["value"] and _kur_cache["ts"] and (datetime.utcnow() - _kur_cache["ts"]).seconds < 600:
        return _kur_cache["value"]

    # 1) Harem Altın
    try:
        resp = http_requests.get(
            "https://www.haremaltin.com/dashboard/ajax/doviz",
            headers={"X-Requested-With": "XMLHttpRequest",
                     "User-Agent": "Mozilla/5.0",
                     "Referer": "https://www.haremaltin.com/"},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            # Harem formatı: data["data"]["USDTRY"]["satis"] veya data["USD"]["spidr_sell"]
            usd = None
            if isinstance(data, dict):
                if "data" in data and "USDTRY" in data["data"]:
                    usd = float(data["data"]["USDTRY"].get("satis") or data["data"]["USDTRY"].get("alis") or 0)
                elif "USD" in data:
                    usd = float(data["USD"].get("spidr_sell") or data["USD"].get("satis") or 0)
            if usd and usd > 0:
                _kur_cache.update({"value": usd, "ts": datetime.utcnow()})
                logging.info(f"Harem Altın USD/TL: {usd}")
                return usd
    except Exception as e:
        logging.warning(f"Harem Altın kur çekme hatası: {e}")

    # 2) Fallback: exchangerate-api (ücretsiz, limitsiz)
    try:
        resp = http_requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
        if resp.status_code == 200:
            rate = float(resp.json().get("rates", {}).get("TRY", 0))
            if rate > 0:
                _kur_cache.update({"value": rate, "ts": datetime.utcnow()})
                logging.info(f"ExchangeRate API USD/TL: {rate}")
                return rate
    except Exception as e:
        logging.warning(f"ExchangeRate API kur çekme hatası: {e}")

    return _kur_cache.get("value")


@profit_bp.route("/api/exchange-rate", methods=["GET"])
def api_exchange_rate():
    """Güncel USD/TL kurunu JSON olarak döndür."""
    rate = _fetch_usd_try()
    if rate:
        return jsonify(success=True, rate=rate)
    return jsonify(success=False, rate=0, message="Kur alınamadı"), 503


# --------------------------------------------------------------------------
# Yardımcı Fonksiyonlar
# --------------------------------------------------------------------------
def d(value) -> Decimal:
    """
    UI'dan gelen "123,45" gibi değerleri güvenli şekilde Decimal'e çevirir.
    None/boş/hatalıysa 0 döner.
    """
    if value is None:
        return Decimal("0")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    s = str(value).strip()
    if not s:
        return Decimal("0")
    try:
        # Türkçe ondalık: virgülü noktaya çevir
        s = s.replace(".", "").replace(",", ".") if "," in s and "." in s else s.replace(",", ".")
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def format_number(value) -> str:
    """
    Ondalıklı sayıları '1.234,56' biçiminde döndürür.
    Decimal veya sayısal tür bekler.
    """
    if value is None:
        return "0,00"
    try:
        quantized = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        s = f"{quantized:,.2f}"
        # 1,234.56 -> 1.234,56
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        try:
            return str(value).replace(".", ",")
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

    # cost_{BARCODE} => Decimal
    updates = {}
    for key, val in request.form.items():
        if key.startswith("cost_"):
            bc = key.replace("cost_", "").strip()
            cost_val = d(val)
            if bc and cost_val > 0:
                updates[bc] = cost_val

    if not updates:
        flash("Kaydedilecek geçerli maliyet bulunamadı.", "warning")
        return redirect(
            url_for(
                "profit.profit_report",
                start_date=start_date, end_date=end_date,
                package_cost=request.form.get("package_cost", ""),
                monthly_employee_salary=request.form.get("monthly_employee_salary", ""),
                shipping_cost=request.form.get("shipping_cost", ""),
                exchange_rate=request.form.get("exchange_rate", ""),
                auto_reload="1",
            )
           )

    try:
        existing_products = Product.query.filter(Product.barcode.in_(updates.keys())).all()
        existing_barcodes = {p.barcode for p in existing_products}

        for prod in existing_products:
            if prod.barcode in updates:
                prod.cost_try = float(updates[prod.barcode])  # DB alanı float ise

        # Not: Yeni Product açma davranışını koruyoruz (mevcut koddaki gibi)
        missing_barcodes = set(updates.keys()) - existing_barcodes
        for bc in missing_barcodes:
            try:
                new_product = Product(
                    barcode=bc,
                    cost_try=float(updates[bc]),
                    # --- Aşağısı Product modelindeki zorunlu alanlara göre doldurulacak ---
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
                    # --- EĞER BAŞKA ZORUNLU ALAN VARSA EKLE ---
                )
                db.session.add(new_product)
            except TypeError as te:
                db.session.rollback()
                logging.error(f"'{bc}' barkodlu yeni ürün oluşturulurken TypeError: {te}. Zorunlu alanlar eksik/yanlış.", exc_info=True)
                flash(f"'{bc}' barkodlu ürün için maliyet kaydedilemedi. Zorunlu alanlar eksik/yanlış. Detaylar logda.", "error")
                continue

        db.session.commit()
        flash(f"{len(updates)} adet maliyet güncellendi/eklendi.", "success")

    except Exception as e:
        db.session.rollback()
        logging.error("Maliyetler kaydedilirken hata: %s", e, exc_info=True)
        flash("Maliyetler kaydedilemedi. Veritabanı hatası. Detaylar logda.", "error")

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
        "total_profit": Decimal("0.0"), "avg_profit": Decimal("0.0"),
        "total_revenue": Decimal("0.0"), "total_discount_sum": Decimal("0.0"),
        "total_expenses_sum": Decimal("0.0"), "total_commission_sum": Decimal("0.0"),
        "total_product_cost_sum": Decimal("0.0"),
        "total_uretim_cost_sum": Decimal("0.0"),
        "total_employee_cost_period": Decimal("0.0"), "total_package_cost_period": Decimal("0.0"),
        "total_shipping_cost_period": Decimal("0.0"), "total_return_shipping_cost": Decimal("0.0"),
        "avg_profit_margin": Decimal("0.0"), "order_count": 0, "total_barcodes_processed": 0,
        "start_date": form_source.get("start_date", ""), "end_date": form_source.get("end_date", ""),
        "package_cost": form_source.get("package_cost", ""),
        "monthly_employee_salary": form_source.get("monthly_employee_salary", ""),
        "shipping_cost": form_source.get("shipping_cost", ""),  # Formdaki değer (baz ve iade için)
        "exchange_rate": form_source.get("exchange_rate", ""),
        "total_profit_str": "0,00", "avg_profit_str": "0,00", "total_revenue_str": "0,00",
        "total_discount_sum_str": "0,00", "total_expenses_sum_str": "0,00",
        "total_commission_sum_str": "0,00", "total_product_cost_sum_str": "0,00",
        "total_uretim_cost_sum_str": "0,00",
        "total_employee_cost_period_str": "0,00", "total_package_cost_period_str": "0,00",
        "total_shipping_cost_period_str": "0,00", "total_return_shipping_cost_str": "0,00",
        "shipping_cost_str": "0,00", "avg_profit_margin_str": "0.00",
    }

    # Formdaki kargo baz maliyetini oku (Decimal)
    form_shipping_cost = d(context["shipping_cost"])
    context["shipping_cost_str"] = format_number(form_shipping_cost)

    # Döviz kuru (USD → TL)
    form_exchange_rate = d(context["exchange_rate"])
    context["exchange_rate_str"] = format_number(form_exchange_rate)

    if request.method == "POST" or request.args.get("auto_reload") == "1":
        analysis_temp = []
        cancelled_orders_temp = []
        returned_orders_temp = []
        other_excluded_temp = []
        missing_cost_barcodes = set()
        missing_cost_entries_list = []
        product_summary = defaultdict(lambda: {"total_profit": Decimal("0.0"),
                                               "total_commission": Decimal("0.0"),
                                               "total_discount": Decimal("0.0"),
                                               "count": 0})

        total_profit_minus_employee = Decimal("0.0")
        total_revenue = Decimal("0.0")
        total_discount_sum = Decimal("0.0")
        total_expenses_minus_employee = Decimal("0.0")
        total_commission_sum = Decimal("0.0")
        total_product_cost_sum = Decimal("0.0")
        total_package_cost_period = Decimal("0.0")
        total_outgoing_shipping_cost_period = Decimal("0.0")  # GİDEN kargo maliyeti toplamı
        total_return_shipping_cost = Decimal("0.0")  # İade kargo maliyeti toplamı
        total_uretim_cost_sum = Decimal("0.0")  # Üretim maliyeti toplamı (USD→TL)
        processed_order_count = 0
        total_barcodes_processed = 0
        total_records_found = 0

        try:
            package_cost_per_item = d(context["package_cost"])
            monthly_employee_salary = d(context["monthly_employee_salary"])
            # form_shipping_cost zaten Decimal

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

            logging.info(f"Form Girdileri - Paket/adet: {package_cost_per_item}, Aylık Maaş: {monthly_employee_salary}, Baz/İade Kargo: {form_shipping_cost}, Başlangıç: {start_date_str}, Bitiş: {end_date_str}")
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
                total_return_shipping_cost = Decimal("0.0")

                for o in returned_orders_query_result:
                    order_num = o[0]
                    barcode_val = o[3] if len(o) > 3 else None
                    if order_num and order_num not in temp_returned_nos:
                        # Dönüş kargosu: baz kargo kadar
                        return_shipping_cost_per_order = form_shipping_cost
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
                logging.info(f"Toplam iade kargo maliyeti (dönüş): {total_return_shipping_cost} TL")

            except AttributeError as ae:
                logging.error("İptal/İade sorgusunda model hatası: %s", ae, exc_info=True)
                flash("Veritabanı modeli hatası: İptal/iade bilgileri çekilemedi.", "error")
                return render_template("profit.html", **context)
            except Exception as e:
                logging.error("İptal/İade siparişleri çekilirken genel hata: %s", e, exc_info=True)
                flash("İptal/iade bilgileri çekilirken bir sorun oluştu. Detaylar logda.", "warning")

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
                    flash("Belirtilen tarihlerde analize dahil edilecek aktif sipariş yok (Sadece iptal/iadeler listelendi).", "info")
                else:
                    flash("Belirtilen tarihlerde işlenecek kayıt bulunamadı.", "info")
                context.update({
                    "analysis": [], "cancelled_orders": cancelled_orders_temp, "returned_orders": returned_orders_temp,
                    "other_excluded_orders": [], "missing_cost_entries": [],
                })
                context["total_return_shipping_cost_str"] = format_number(total_return_shipping_cost)
                return render_template("profit.html", **context)

            # --- Barkod → Model eşlemesi (üretim maliyeti için) ---
            barcode_to_model = {}
            if all_individual_barcodes:
                try:
                    products = Product.query.filter(Product.barcode.in_(all_individual_barcodes)).all()
                    for p in products:
                        bc = (p.barcode or "").strip()
                        mid = (p.product_main_id or "").strip()
                        if bc and mid:
                            barcode_to_model[bc] = mid
                except Exception as e:
                    logging.error("Barkod-model eşlemesi çekilirken hata: %s", e, exc_info=True)

            # --- Üretim maliyetlerini çek (model bazlı, USD) ---
            model_uretim_costs = {}  # model_id → USD maliyet
            if form_exchange_rate > 0:
                try:
                    # Direkt maliyet girilmişler
                    direk_rows = ModelDirekMaliyet.query.all()
                    for dr in direk_rows:
                        if dr.deger and dr.deger > 0:
                            model_uretim_costs[dr.model_id] = Decimal(str(dr.deger))

                    # Kalem toplam (direkt yoksa)
                    kalem_rows = db.session.query(
                        ModelMaliyet.model_id,
                        db.func.sum(ModelMaliyet.deger).label("toplam"),
                    ).group_by(ModelMaliyet.model_id).all()
                    for kr in kalem_rows:
                        if kr.model_id not in model_uretim_costs and kr.toplam and kr.toplam > 0:
                            model_uretim_costs[kr.model_id] = Decimal(str(kr.toplam))

                    logging.info(f"{len(model_uretim_costs)} model için üretim maliyeti bulundu. Kur: {form_exchange_rate}")
                except Exception as e:
                    logging.error("Üretim maliyetleri çekilirken hata: %s", e, exc_info=True)

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
                    order_total_product_cost = Decimal("0.0")
                    cost_calculation_possible = True
                    display_barcode_in_excluded = product_barcode_raw or f"BARKODSUZ_{order_id or 'ID'}"
                    num_barcodes_in_order = 0
                    individual_barcodes_in_order = []

                    if not product_barcode_raw or not product_barcode_raw.strip():
                        reason = "Barkod Boş/Yok"
                    else:
                        individual_barcodes_in_order = [b.strip() for b in product_barcode_raw.split(',') if b.strip()]
                        num_barcodes_in_order = len(individual_barcodes_in_order)
                        if num_barcodes_in_order == 0:
                            reason = "Geçersiz Barkod Formatı"

                    if reason:
                        other_excluded_temp.append({
                            "order_number": order_number, "merchant_sku": merchant_sku,
                            "status": order_status, "reason": reason,
                            "barcode": display_barcode_in_excluded,
                        })
                        if order_id: processed_order_ids.add(order_id)
                        continue

                    # ----- Geçerli Sipariş Maliyetleri -----
                    commission_val = d(getattr(o, 'commission', 0) or 0)

                    # --- Üretim Maliyeti (USD → TL) ---
                    line_uretim_cost = Decimal("0.0")
                    if form_exchange_rate > 0 and model_uretim_costs:
                        seen_models = set()
                        for bc in individual_barcodes_in_order:
                            mid = barcode_to_model.get(bc)
                            if mid and mid not in seen_models:
                                usd_cost = model_uretim_costs.get(mid, Decimal("0.0"))
                                line_uretim_cost += usd_cost * form_exchange_rate
                                seen_models.add(mid)

                    # --- Komisyon veya üretim maliyeti yoksa hariç tut ---
                    if commission_val <= 0 or line_uretim_cost <= 0:
                        reasons = []
                        if commission_val <= 0:
                            reasons.append("Komisyon Yok")
                        if line_uretim_cost <= 0:
                            reasons.append("Üretim Maliyeti Yok")
                        other_excluded_temp.append({
                            "order_number": order_number, "merchant_sku": merchant_sku,
                            "status": order_status, "reason": " / ".join(reasons),
                            "barcode": display_barcode_in_excluded,
                        })
                        if order_id: processed_order_ids.add(order_id)
                        continue

                    # Paket Maliyeti (adet × paket/adet)
                    line_package_cost = package_cost_per_item * Decimal(num_barcodes_in_order)

                    # --- KARGO MALİYETİ (SABİT BAZ) ---
                    line_shipping_cost = form_shipping_cost

                    # --- Kâr Hesapları ---
                    amount_val = d(getattr(o, 'amount', 0) or 0)
                    discount_val = d(getattr(o, 'discount', 0) or 0)
                    net_income = amount_val - discount_val
                    order_expenses_initial = commission_val + line_package_cost + line_shipping_cost + line_uretim_cost
                    profit_initial = net_income - order_expenses_initial

                    # --- Toplamları Güncelle ---
                    total_revenue += amount_val
                    total_discount_sum += discount_val
                    total_commission_sum += commission_val
                    total_uretim_cost_sum += line_uretim_cost
                    total_package_cost_period += line_package_cost
                    total_outgoing_shipping_cost_period += line_shipping_cost
                    total_expenses_minus_employee += order_expenses_initial
                    total_profit_minus_employee += profit_initial
                    processed_order_count += 1
                    total_barcodes_processed += num_barcodes_in_order
                    profit_margin_initial = (profit_initial / net_income * Decimal("100")) if net_income > 0 else Decimal("0.0")

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
                        "commission": commission_val,
                        "uretim_cost": line_uretim_cost,
                        "package_cost": line_package_cost,
                        "shipping_cost": line_shipping_cost,
                        "employee_cost": Decimal("0.0"),
                        "total_expenses": order_expenses_initial,
                        "profit": profit_initial,
                        "profit_margin": profit_margin_initial,
                    })
                    if order_id: processed_order_ids.add(order_id)

                except Exception as e:
                    logging.error("Sipariş işlenirken hata (ID=%s, No=%s): %s", order_id, order_number, e, exc_info=True)
                    flash(f"'{order_number}' numaralı sipariş işlenirken beklenmedik bir hata oluştu. Detaylar logda.", "error")
                    other_excluded_temp.append({
                        "order_number": order_number, "merchant_sku": merchant_sku, "status": order_status,
                        "reason": "İşlem Hatası", "barcode": getattr(o, "product_barcode", "BARKOD OKUNAMADI"),
                    })
                    if order_id: processed_order_ids.add(order_id)
            # -- /Sipariş işleme döngüsü

            # --- İADE SİPARİŞLER İÇİN GİDİŞ KARGOSUNU DA EKLE ---
            # Aktif listeden çıkarıldıkları için (not in) onların gidiş kargosu toplam giden kargoya DAHİL DEĞİL.
            # Senin istediğin: iade varsa 1×baz (gidiş) + 1×baz (dönüş).
            extra_outgoing_for_returns = Decimal(len(returned_order_numbers)) * form_shipping_cost
            total_outgoing_shipping_cost_period += extra_outgoing_for_returns
            total_expenses_minus_employee += extra_outgoing_for_returns
            total_profit_minus_employee -= extra_outgoing_for_returns  # kârdan düş

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
            per_barcode_employee_cost = Decimal("0.0")
            total_employee_cost_period = Decimal("0.0")
            if monthly_employee_salary > 0 and days_in_range > 0:
                try:
                    days_in_month = calendar.monthrange(start_date_obj.year, start_date_obj.month)[1]
                    daily_salary = monthly_employee_salary / Decimal(days_in_month)
                    total_employee_cost_period = daily_salary * Decimal(days_in_range)
                    if total_barcodes_processed > 0:
                        per_barcode_employee_cost = (total_employee_cost_period / Decimal(total_barcodes_processed)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        logging.info(f"Personel maliyeti ({days_in_range} gün): {total_employee_cost_period:.2f} TL | Barkod başı ({total_barcodes_processed}): {per_barcode_employee_cost:.2f} TL")
                    else:
                        logging.info(f"Personel maliyeti ({days_in_range} gün): {total_employee_cost_period:.2f} TL | Barkod yok, dağıtılamadı.")
                except Exception as e:
                    logging.error("Personel maliyeti hesaplanırken hata: %s", e, exc_info=True)
                    flash("Personel maliyeti hesaplanırken bir hata oluştu. Detaylar logda.", "error")
                    per_barcode_employee_cost = Decimal("0.0")
                    total_employee_cost_period = Decimal("0.0")

            # -- Hesaplanan personel maliyetini sipariş satırlarına dağıt --
            if per_barcode_employee_cost > 0:
                for item in analysis_temp:
                    item_total_employee_cost = per_barcode_employee_cost * Decimal(item['num_barcodes'])
                    item["employee_cost"] = item_total_employee_cost
                    item["total_expenses"] += item_total_employee_cost
                    item["profit"] -= item_total_employee_cost
                    item["profit_margin"] = (item["profit"] / item["net_income"] * Decimal("100") if item["net_income"] > 0 else Decimal("0"))

            # -- Nihai Kâr/Zarar Toplamları --
            final_total_profit = total_profit_minus_employee - total_employee_cost_period
            # İade dönüş kargosu zaten total_return_shipping_cost'ta tutuluyor ve genel gidere eklenmeli
            final_total_expenses = total_expenses_minus_employee + total_employee_cost_period + total_return_shipping_cost
            final_avg_profit = (final_total_profit / Decimal(processed_order_count)) if processed_order_count > 0 else Decimal("0.0")
            total_net_income_sum = total_revenue - total_discount_sum
            final_avg_profit_margin = (final_total_profit / total_net_income_sum * Decimal("100") if total_net_income_sum > 0 else Decimal("0.0"))

            # Top listeler (SKU karı yaklaşık)
            product_summary_list = [{"sku": sku, **data} for sku, data in product_summary.items()]
            sku_profit_adjustment_factor = (final_total_profit / total_profit_minus_employee) if total_profit_minus_employee > 0 and final_total_profit >= 0 else Decimal("0")
            for item in product_summary_list:
                adjusted_profit = item['total_profit'] * sku_profit_adjustment_factor
                item['total_profit_str'] = format_number(adjusted_profit)
                item['total_commission_str'] = format_number(item['total_commission'])
                item['total_discount_str'] = format_number(item['total_discount'])
                item['total_profit'] = adjusted_profit  # sıralama için

            top_profit_products = sorted(product_summary_list, key=lambda x: x["total_profit"], reverse=True)[:10]
            top_commission_products = sorted(product_summary_list, key=lambda x: x["total_commission"], reverse=True)[:10]
            top_discount_products = sorted(product_summary_list, key=lambda x: x["total_discount"], reverse=True)[:10]

            # Analiz listesini formatla
            for item in analysis_temp:
                for key in ['amount', 'discount', 'net_income', 'commission', 'uretim_cost', 'package_cost', 'shipping_cost', 'employee_cost', 'total_expenses', 'profit']:
                    item[key + '_str'] = format_number(item[key])
                # Yüzde için nokta kullanımı isteniyordu
                item['profit_margin_str'] = format_number(item['profit_margin']).replace(",", ".")

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
                "total_uretim_cost_sum": total_uretim_cost_sum,
                "avg_profit_margin": final_avg_profit_margin,
                "total_employee_cost_period": total_employee_cost_period,
                "total_package_cost_period": total_package_cost_period,
                "total_shipping_cost_period": total_outgoing_shipping_cost_period,  # Giden Kargo Toplamı (iade gidişleri dahil)
                "total_return_shipping_cost": total_return_shipping_cost,          # İade Kargo Toplamı (dönüş)
                "top_profit_products": top_profit_products, "top_commission_products": top_commission_products,
                "top_discount_products": top_discount_products,
                "total_profit_str": format_number(final_total_profit), "avg_profit_str": format_number(final_avg_profit),
                "total_revenue_str": format_number(total_revenue), "total_discount_sum_str": format_number(total_discount_sum),
                "total_expenses_sum_str": format_number(final_total_expenses),
                "total_commission_sum_str": format_number(total_commission_sum),
                "total_product_cost_sum_str": format_number(total_product_cost_sum),
                "total_uretim_cost_sum_str": format_number(total_uretim_cost_sum),
                "total_employee_cost_period_str": format_number(total_employee_cost_period),
                "total_package_cost_period_str": format_number(total_package_cost_period),
                "total_shipping_cost_period_str": format_number(total_outgoing_shipping_cost_period),
                "total_return_shipping_cost_str": format_number(total_return_shipping_cost),
                "shipping_cost_str": context["shipping_cost_str"],
                "avg_profit_margin_str": format_number(final_avg_profit_margin).replace(",", "."),
            })

        except Exception as e:
            logging.error("Kâr analizi sırasında genel hata oluştu: %s", e, exc_info=True)
            flash("Analiz sırasında beklenmedik bir hata oluştu. Detaylar logda.", "error")
            return render_template("profit.html", **context)

    # GET isteği veya POST sonrası render
    return render_template("profit.html", **context)
