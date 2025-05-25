import os
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import text, inspect
from logger_config import app_logger
from models import db, Product, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled, ReturnOrder
import traceback
import json
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# Logger yapılandırması
logger = app_logger

# Çevre değişkenlerini yükle
load_dotenv()

# OpenAI istemcisini oluştur
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Model seçimi - en güncel ve en iyi model
DEFAULT_MODEL = "gpt-4o"

# Blueprint oluşturma
ai_brain_bp = Blueprint('ai_brain_bp', __name__)

# Zamanlanmış görevler için scheduler
scheduler = BackgroundScheduler()

class AIBrain:
    """
    Sistemin yapay zeka 'beyin' katmanı.
    Veritabanına bağlanır, verileri analiz eder ve önerilerde bulunur.
    """
    
    def __init__(self):
        self.logger = app_logger
        self.client = client
        self.model = DEFAULT_MODEL
        self.logger.info("AI Brain initialized")
        
    def get_db_schema(self):
        """Veritabanı şemasını döndürür - tablo adları ve sütunlar"""
        try:
            inspector = inspect(db.engine)
            schema_info = {}
            
            for table_name in inspector.get_table_names():
                columns = []
                for column in inspector.get_columns(table_name):
                    columns.append(f"{column['name']} ({column['type']})")
                
                schema_info[table_name] = columns
            
            return schema_info
        except Exception as e:
            self.logger.error(f"Veritabanı şeması alınırken hata: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {"error": str(e)}
    
    def get_stock_summary(self):
        """Stok durumunun özetini döndürür"""
        try:
            # En düşük stoklu 10 ürün
            low_stock_query = db.session.query(Product).filter(
                Product.archived == False,
                Product.quantity > 0
            ).order_by(Product.quantity.asc()).limit(10)
            
            low_stock_products = []
            for product in low_stock_query:
                low_stock_products.append({
                    "barcode": product.barcode,
                    "title": product.title,
                    "quantity": product.quantity,
                    "color": product.color,
                    "size": product.size
                })
            
            # Tükenen ürünler
            out_of_stock_query = db.session.query(Product).filter(
                Product.archived == False,
                Product.quantity <= 0
            ).limit(10)
            
            out_of_stock_products = []
            for product in out_of_stock_query:
                out_of_stock_products.append({
                    "barcode": product.barcode,
                    "title": product.title,
                    "color": product.color,
                    "size": product.size
                })
            
            # Toplam ürün ve stok sayısı
            total_products = db.session.query(Product).filter(Product.archived == False).count()
            total_stock = db.session.query(db.func.sum(Product.quantity)).filter(Product.archived == False).scalar() or 0
            
            return {
                "low_stock_products": low_stock_products,
                "out_of_stock_products": out_of_stock_products,
                "total_products": total_products,
                "total_stock": total_stock
            }
        except Exception as e:
            self.logger.error(f"Stok özeti alınırken hata: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {"error": str(e)}
    
    def get_sales_summary(self, days=30):
        """Son X gündeki satış özetini döndürür"""
        try:
            # Son X gün için tarih hesapla
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Teslim edilen siparişleri getir
            delivered_orders = db.session.query(OrderDelivered).filter(
                OrderDelivered.order_date >= start_date,
                OrderDelivered.order_date <= end_date
            ).all()
            
            # İstatistikleri hesapla
            total_orders = len(delivered_orders)
            total_revenue = sum(order.amount or 0 for order in delivered_orders)
            
            # Ürün bazlı satış analizi
            product_sales = {}
            for order in delivered_orders:
                # product_barcode alanı virgülle ayrılmış barkodlar içerebilir
                if order.product_barcode:
                    barcodes = order.product_barcode.split(',')
                    for barcode in barcodes:
                        barcode = barcode.strip()
                        if barcode:
                            if barcode not in product_sales:
                                product_sales[barcode] = {"count": 0, "revenue": 0}
                            
                            product_sales[barcode]["count"] += 1
                            if order.amount:
                                # Siparişteki ürün sayısına göre orantılı dağıt
                                product_count = len(barcodes)
                                product_sales[barcode]["revenue"] += order.amount / product_count if product_count > 0 else 0
            
            # En çok satılan ürünleri bul
            top_selling_products = []
            for barcode, data in sorted(product_sales.items(), key=lambda x: x[1]["count"], reverse=True)[:10]:
                product = db.session.query(Product).filter(Product.barcode == barcode).first()
                if product:
                    top_selling_products.append({
                        "barcode": barcode,
                        "title": product.title,
                        "count": data["count"],
                        "revenue": data["revenue"],
                        "color": product.color,
                        "size": product.size
                    })
                else:
                    # Ürün bulunamadıysa da ekle
                    top_selling_products.append({
                        "barcode": barcode,
                        "title": "Bilinmeyen Ürün",
                        "count": data["count"],
                        "revenue": data["revenue"]
                    })
            
            return {
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "total_orders": total_orders,
                "total_revenue": total_revenue,
                "top_selling_products": top_selling_products
            }
        except Exception as e:
            self.logger.error(f"Satış özeti alınırken hata: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {"error": str(e)}
    
    def get_return_summary(self, days=30):
        """Son X gündeki iade özetini döndürür"""
        try:
            # Son X gün için tarih hesapla
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # İade siparişlerini getir
            return_orders = db.session.query(ReturnOrder).filter(
                ReturnOrder.return_date >= start_date,
                ReturnOrder.return_date <= end_date
            ).all()
            
            # İstatistikleri hesapla
            total_returns = len(return_orders)
            total_refund = sum(order.refund_amount or 0 for order in return_orders)
            
            # İade nedenleri analizi
            return_reasons = {}
            for order in return_orders:
                reason = order.return_reason or "Belirtilmemiş"
                if reason not in return_reasons:
                    return_reasons[reason] = 0
                return_reasons[reason] += 1
            
            # En yaygın iade nedenleri
            top_return_reasons = []
            for reason, count in sorted(return_reasons.items(), key=lambda x: x[1], reverse=True):
                top_return_reasons.append({
                    "reason": reason,
                    "count": count,
                    "percentage": (count / total_returns * 100) if total_returns > 0 else 0
                })
            
            return {
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "total_returns": total_returns,
                "total_refund": total_refund,
                "top_return_reasons": top_return_reasons
            }
        except Exception as e:
            self.logger.error(f"İade özeti alınırken hata: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {"error": str(e)}
    
    def get_order_status_summary(self):
        """Sipariş durumlarının özetini döndürür"""
        try:
            # Her durumdaki sipariş sayılarını al
            created_count = db.session.query(OrderCreated).count()
            picking_count = db.session.query(OrderPicking).count()
            shipped_count = db.session.query(OrderShipped).count()
            delivered_count = db.session.query(OrderDelivered).count()
            cancelled_count = db.session.query(OrderCancelled).count()
            
            # Son 7 gündeki siparişleri al
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            
            recent_created = db.session.query(OrderCreated).filter(OrderCreated.order_date >= start_date).count()
            recent_delivered = db.session.query(OrderDelivered).filter(OrderDelivered.order_date >= start_date).count()
            
            return {
                "status_counts": {
                    "created": created_count,
                    "picking": picking_count,
                    "shipped": shipped_count,
                    "delivered": delivered_count,
                    "cancelled": cancelled_count
                },
                "recent_orders": {
                    "created_last_7_days": recent_created,
                    "delivered_last_7_days": recent_delivered
                }
            }
        except Exception as e:
            self.logger.error(f"Sipariş durumu özeti alınırken hata: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {"error": str(e)}
    
    def analyze_data(self, analysis_type="daily"):
        """
        Mevcut verileri analiz eder ve içgörüler sağlar
        analysis_type: 'daily', 'weekly', 'monthly', 'custom'
        """
        try:
            # Tüm veri özetlerini topla
            stock_summary = self.get_stock_summary()
            sales_summary = self.get_sales_summary(days=30 if analysis_type == "monthly" else 7 if analysis_type == "weekly" else 1)
            return_summary = self.get_return_summary(days=30 if analysis_type == "monthly" else 7 if analysis_type == "weekly" else 1)
            order_status_summary = self.get_order_status_summary()
            
            # Verileri OpenAI'ya gönder
            system_prompt = """Sen Güllü Ayakkabı firması için çalışan bir satış ve stok analiz uzmanısın. 
            Firmanın topuklu ayakkabı ve ayakkabı malzemeleri (topuk, taban, neolit/jurdan) üretip sattığını biliyorsun.
            Verilen günlük/haftalık/aylık raporu analiz ederek değerli içgörüler, tavsiyeler ve eylem önerileri sun.
            Raporunu şu yapıda hazırla:

            1. **Özet Durum:** Sistemin genel durumunun kısa özeti.
            2. **Stok Durumu:** Stok seviyelerinin analizi, dikkat edilmesi gereken ürünler.
            3. **Satış Performansı:** Satış trendleri ve en çok satan ürünlerin analizi.
            4. **İade Analizi:** İade oranları ve nedenlerinin analizi.
            5. **Sipariş Durumu:** Mevcut sipariş durumlarının genel görünümü.
            6. **Önerilen Aksiyonlar:** Önceliklendirilmiş, somut eylem önerileri.

            Analizini açık, kısa ve aksiyona dönüştürülebilir şekilde yap. Önemli noktaları **kalın** yaz.
            """
            
            combined_data = {
                "analysis_type": analysis_type,
                "stock_summary": stock_summary,
                "sales_summary": sales_summary,
                "return_summary": return_summary,
                "order_status_summary": order_status_summary,
                "current_date": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            
            user_prompt = f"""Lütfen aşağıdaki Güllü Ayakkabı {analysis_type} verilerini analiz et:
            ```json
            {json.dumps(combined_data, indent=2, default=str)}
            ```
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1500
            )
            
            analysis_result = response.choices[0].message.content
            if analysis_result:
                analysis_result = analysis_result.strip()
            
            self.logger.info(f"{analysis_type.capitalize()} analiz tamamlandı.")
            
            return {
                "success": True,
                "analysis": analysis_result,
                "data": combined_data,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Veri analizi sırasında hata: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e),
                "trace": traceback.format_exc()
            }
    
    def check_risky_orders(self):
        """Riskli siparişleri kontrol eder"""
        try:
            # Yeni oluşturulan siparişleri al
            new_orders = db.session.query(OrderCreated).filter(
                OrderCreated.created_at >= (datetime.now() - timedelta(hours=24))
            ).all()
            
            if not new_orders:
                self.logger.info("Son 24 saatte yeni sipariş bulunmadı.")
                return {"success": True, "message": "Son 24 saatte yeni sipariş bulunmadı."}
            
            # Siparişleri analiz için hazırla
            orders_data = []
            for order in new_orders:
                order_data = {
                    "order_number": order.order_number,
                    "order_date": order.order_date.isoformat() if order.order_date else None,
                    "customer_name": f"{order.customer_name or ''} {order.customer_surname or ''}",
                    "customer_address": order.customer_address,
                    "amount": order.amount,
                    "product_name": order.product_name,
                    "product_barcode": order.product_barcode,
                    "quantity": order.quantity
                }
                orders_data.append(order_data)
            
            # OpenAI ile risk analizi yap
            system_prompt = """Sen Güllü Ayakkabı firmasının sipariş doğrulama ve risk analizi uzmanısın. 
            Verilen siparişleri analiz ederek şüpheli veya sorunlu olabilecek siparişleri belirlemelisin.
            
            Şu tür durumları riskli olarak değerlendir:
            1. Teslimat adresi eksik, belirsiz veya tuhaf görünen siparişler
            2. Çok yüksek miktarda veya değerde ürün içeren olağandışı siparişler
            3. Aynı müşteriden kısa sürede çok sayıda sipariş
            4. Adres bilgisi ile ödeme bilgisi arasında tutarsızlık olan siparişler
            
            Çıktını JSON formatında olmalı:
            {
                "risky_orders": [
                    {
                        "order_number": "sipariş numarası",
                        "risk_level": "yüksek/orta/düşük",
                        "risk_reasons": ["neden 1", "neden 2"],
                        "recommendation": "Bu sipariş için önerilen aksiyon"
                    }
                ],
                "summary": "Genel risk değerlendirmesi özeti"
            }
            """
            
            user_prompt = f"""Lütfen aşağıdaki siparişleri risk açısından değerlendir:
            ```json
            {json.dumps(orders_data, indent=2, default=str)}
            ```
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
                max_tokens=1000
            )
            
            content = response.choices[0].message.content
            if content:
                content = content.strip()
                analysis_result = json.loads(content)
            else:
                analysis_result = {"risky_orders": [], "summary": "Analiz sonucu alınamadı."}
            
            self.logger.info(f"Sipariş risk analizi tamamlandı. {len(analysis_result.get('risky_orders', []))} riskli sipariş bulundu.")
            
            return {
                "success": True,
                "analysis": analysis_result,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Sipariş risk analizi sırasında hata: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e),
                "trace": traceback.format_exc()
            }
    
    def answer_question(self, question):
        """Kullanıcının sorduğu soruya veritabanı bilgilerini kullanarak cevap verir"""
        try:
            # İlgili verileri topla
            context_data = {}
            
            # Sorunun içeriğine göre ilgili verileri ekle
            if any(keyword in question.lower() for keyword in ["stok", "stock", "ürün", "product"]):
                context_data["stock_summary"] = self.get_stock_summary()
            
            if any(keyword in question.lower() for keyword in ["satış", "sales", "gelir", "revenue", "sipariş", "order"]):
                context_data["sales_summary"] = self.get_sales_summary()
                context_data["order_status_summary"] = self.get_order_status_summary()
            
            if any(keyword in question.lower() for keyword in ["iade", "return", "geri"]):
                context_data["return_summary"] = self.get_return_summary()
            
            # Hiçbir özel bağlam bulunamadıysa genel veri özetlerini ekle
            if not context_data:
                context_data["stock_summary"] = self.get_stock_summary()
                context_data["sales_summary"] = self.get_sales_summary()
                context_data["order_status_summary"] = self.get_order_status_summary()
            
            # OpenAI ile soruyu yanıtla
            system_prompt = """Sen Güllü Ayakkabı firması için çalışan bir veri analiz asistanısın.
            Firmanın topuklu ayakkabı ve ayakkabı malzemeleri üretip sattığını biliyorsun.
            Sana verilen veri bağlamını kullanarak sorulan soruları doğru, açık ve yardımcı bir şekilde yanıtla.
            Eğer veri yetersizse, bunu belirt. Eğer soruyu yanıtlamak için daha fazla bilgiye ihtiyacın varsa, hangi ek bilgilere ihtiyacın olduğunu açıkça belirt.
            
            Yanıtını şu formatta yapılandır:
            1. Soruya doğrudan yanıt
            2. Varsa destekleyici veriler ve analizler
            3. Varsa ek öneriler veya aksiyonlar
            
            Her zaman doğru, dürüst ve yardımcı olmaya çalış.
            """
            
            user_prompt = f"""Soru: {question}
            
            Aşağıdaki veri bağlamını kullanarak yanıtını oluştur:
            ```json
            {json.dumps(context_data, indent=2, default=str)}
            ```
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content if response.choices and response.choices[0].message else None
            answer = content.strip() if content else "Yanıt alınamadı."
            
            self.logger.info(f"Soru yanıtlandı: {question[:50]}...")
            
            return {
                "success": True,
                "question": question,
                "answer": answer,
                "context_used": list(context_data.keys()),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Soru yanıtlama sırasında hata: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {
                "success": False,
                "question": question,
                "error": str(e),
                "trace": traceback.format_exc()
            }

# AI Brain singleton instance
ai_brain = AIBrain()

# Scheduled Tasks
def run_daily_analysis():
    """Günlük analiz çalıştırır ve sonuçları kaydeder"""
    logger.info("Günlük analiz görevi başlatılıyor...")
    result = ai_brain.analyze_data(analysis_type="daily")
    if result["success"]:
        logger.info("Günlük analiz başarıyla tamamlandı.")
        # İleride sonuçları bir veritabanı tablosuna kaydedebiliriz
    else:
        logger.error(f"Günlük analiz sırasında hata: {result.get('error')}")

def check_for_risky_orders():
    """Riskli siparişleri kontrol eder"""
    logger.info("Riskli sipariş kontrolü başlatılıyor...")
    result = ai_brain.check_risky_orders()
    if result["success"]:
        logger.info("Riskli sipariş kontrolü başarıyla tamamlandı.")
        risky_orders = result.get("analysis", {}).get("risky_orders", [])
        if risky_orders:
            logger.warning(f"{len(risky_orders)} adet riskli sipariş tespit edildi!")
            # İleride e-posta bildirimi veya bildirim gönderebiliriz
    else:
        logger.error(f"Riskli sipariş kontrolü sırasında hata: {result.get('error')}")

def run_hourly_stock_check():
    """Saatlik stok kontrolü yapar"""
    logger.info("Saatlik stok kontrolü başlatılıyor...")
    stock_summary = ai_brain.get_stock_summary()
    if "error" not in stock_summary:
        logger.info("Saatlik stok kontrolü başarıyla tamamlandı.")
        low_stock_count = len(stock_summary.get("low_stock_products", []))
        out_of_stock_count = len(stock_summary.get("out_of_stock_products", []))
        
        if low_stock_count > 0 or out_of_stock_count > 0:
            logger.warning(f"Stok uyarısı: {low_stock_count} ürün düşük stokta, {out_of_stock_count} ürün tükendi!")
            # İleride e-posta bildirimi veya bildirim gönderebiliriz
    else:
        logger.error(f"Saatlik stok kontrolü sırasında hata: {stock_summary.get('error')}")

# API Endpoints
@ai_brain_bp.route('/api/ai-brain/analyze', methods=['POST'])
def api_analyze_data():
    """Veri analizi API endpoint'i"""
    try:
        data = request.get_json()
        analysis_type = data.get('analysis_type', 'daily')
        
        if analysis_type not in ['daily', 'weekly', 'monthly', 'custom']:
            return jsonify({"success": False, "error": "Geçersiz analiz türü. 'daily', 'weekly', 'monthly' veya 'custom' olmalı."}), 400
        
        result = ai_brain.analyze_data(analysis_type=analysis_type)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Analiz API hatası: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500

@ai_brain_bp.route('/api/ai-brain/check-orders', methods=['POST'])
def api_check_risky_orders():
    """Riskli sipariş kontrolü API endpoint'i"""
    try:
        result = ai_brain.check_risky_orders()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Sipariş kontrolü API hatası: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500

@ai_brain_bp.route('/api/ai-brain/ask', methods=['POST'])
def api_ask_question():
    """Soru sorma API endpoint'i"""
    try:
        data = request.get_json()
        if not data or 'question' not in data:
            return jsonify({"success": False, "error": "Geçersiz veri formatı. 'question' alanı gerekli."}), 400
        
        question = data['question']
        result = ai_brain.answer_question(question)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Soru API hatası: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500

@ai_brain_bp.route('/ai-brain/dashboard', methods=['GET'])
def ai_brain_dashboard():
    """AI Brain Dashboard sayfası"""
    from flask import render_template
    return render_template('ai_brain_dashboard.html')

# Zamanlanmış görevleri başlat
def start_scheduler():
    """Zamanlanmış görevleri başlatır"""
    # Günlük analiz - Her sabah 07:00'de çalıştır
    scheduler.add_job(
        run_daily_analysis,
        CronTrigger(hour=7, minute=0),
        id='daily_analysis',
        replace_existing=True
    )
    
    # Riskli sipariş kontrolü - Her 4 saatte bir çalıştır
    scheduler.add_job(
        check_for_risky_orders,
        IntervalTrigger(hours=4),
        id='risky_order_check',
        replace_existing=True
    )
    
    # Saatlik stok kontrolü - Her saat başı çalıştır
    scheduler.add_job(
        run_hourly_stock_check,
        IntervalTrigger(hours=1),
        id='hourly_stock_check',
        replace_existing=True
    )
    
    # Scheduler'ı başlat
    if not scheduler.running:
        scheduler.start()
        logger.info("AI Brain scheduler başlatıldı.")