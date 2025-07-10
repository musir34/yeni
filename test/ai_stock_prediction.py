import os
import json
import logging
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from openai import OpenAI
from sqlalchemy import func, desc, and_
from models import db, Product
from prophet import Prophet
from flask import Blueprint, render_template, jsonify, request, current_app

# Logger kurulumu
logger = logging.getLogger(__name__)

ai_stock_prediction_bp = Blueprint('ai_stock_prediction', __name__)

class StockPredictor:
    def __init__(self):
        """Yapay zeka destekli stok tahmin sisteminin başlatıcısı"""
        self.client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
        
    def get_product_sales_data(self, product_main_id, color=None, size=None, days=90):
        """
        Belirli bir ürün için son {days} gündeki satış verilerini döndürür
        """
        try:
            # Şu anki tarih
            now = datetime.now()
            start_date = now - timedelta(days=days)
            
            # Satış verilerini çek (örnek: tüm sipariş tablolarından, sipariş tarihi son X gün olanlar)
            from analysis import all_orders_union
            from sqlalchemy.sql import text
            
            # SQLAlchemy Session nesnesi al
            with db.session.no_autoflush:
                # Tüm tablolardaki (Created, Picking, Shipped, Delivered, Cancelled) siparişleri birleştir
                union_query = all_orders_union(start_date, now)
                
                # Union sorgu üzerinde filtreleme
                # SQLAlchemy'nin text() fonksiyonunu kullanarak ham SQL sorgusu çalıştır
                filters = []
                
                # Temel filtre - ürün ID'si
                product_filter = f"product_main_id = '{product_main_id}'"
                filters.append(product_filter)
                
                # Eğer renk ve/veya beden belirtilmişse filtrelere ekle
                if color:
                    color_filter = f"product_color = '{color}'"
                    filters.append(color_filter)
                if size:
                    size_filter = f"product_size = '{size}'"
                    filters.append(size_filter)
                
                # Tüm filtreleri AND ile birleştir
                where_clause = " AND ".join(filters)
                
                # SQL sorgusu oluştur ve text() ile çalıştır
                sql_query = text(f"""
                    SELECT DATE(order_date) as date, SUM(quantity) as sold_quantity
                    FROM ({union_query}) as union_orders
                    WHERE {where_clause}
                    GROUP BY DATE(order_date)
                    ORDER BY DATE(order_date)
                """)
                
                daily_sales = db.session.execute(sql_query).fetchall()
                
                # Satış verisini pandas DataFrame'e dönüştür
                # fetchall() sonuçları için uygun formatta DataFrame oluştur
                if daily_sales:
                    df = pd.DataFrame([(date, qty) for date, qty in daily_sales], columns=['ds', 'y'])
                else:
                    df = pd.DataFrame(columns=['ds', 'y'])
                
                # Boş gün kontrolü - satış olmayan günler için 0 değeri ata
                date_range = pd.date_range(start=start_date, end=now)
                date_df = pd.DataFrame({'ds': date_range})
                df = pd.merge(date_df, df, on='ds', how='left').fillna(0)
                
                return df
                
        except Exception as e:
            logger.error(f"Satış verisi alınırken hata: {e}", exc_info=True)
            return pd.DataFrame(columns=['ds', 'y'])  # Boş DataFrame döndür
    
    def predict_future_sales(self, product_main_id, color=None, size=None, forecast_days=30, history_days=90):
        """
        Prophet modeli kullanarak gelecek satışları tahmin eder
        """
        try:
            # Geçmiş satış verilerini al
            sales_df = self.get_product_sales_data(product_main_id, color, size, days=history_days)
            
            # Yeterli veri var mı kontrol et
            if len(sales_df[sales_df['y'] > 0]) < 5:  # En az 5 gün satış olmalı
                logger.warning(f"Ürün {product_main_id} için yeterli satış verisi yok. Tahmin yapılamıyor.")
                return None
                
            # Prophet modelini hazırla ve eğit
            # Prophet'ın beklediği parametreleri doğru şekilde ayarla
            model = Prophet(
                # Boolean değil, otomatik algılama için metin değerleri kullan
                daily_seasonality='auto',
                yearly_seasonality='auto',
                weekly_seasonality='auto',
                seasonality_mode='multiplicative'
            )
            model.fit(sales_df)
            
            # Gelecek için tahmin yap
            future = model.make_future_dataframe(periods=forecast_days)
            forecast = model.predict(future)
            
            # Tahminleri düzenle (negatif değerleri 0 yap)
            forecast['yhat'] = forecast['yhat'].clip(lower=0)
            forecast['yhat_lower'] = forecast['yhat_lower'].clip(lower=0)
            forecast['yhat_upper'] = forecast['yhat_upper'].clip(lower=0)
            
            # Tarihi string formatına çevir
            forecast['ds'] = forecast['ds'].dt.strftime('%Y-%m-%d')
            
            return forecast
        
        except Exception as e:
            logger.error(f"Satış tahmini yapılırken hata: {e}", exc_info=True)
            return None
    
    def analyze_stock_with_ai(self, product_data, sales_forecast=None):
        """
        OpenAI API'si kullanarak stok analizi yapar ve öneriler sunar
        """
        try:
            # OpenAI'ye gönderilecek veriyi hazırla
            prompt_data = {
                "product": {
                    "barcode": product_data.get("barcode"),
                    "title": product_data.get("title"),
                    "model_id": product_data.get("product_main_id"),
                    "color": product_data.get("color"),
                    "size": product_data.get("size"),
                    "current_stock": product_data.get("quantity", 0),
                    "sale_price": product_data.get("sale_price", 0),
                    "cost": product_data.get("cost_try", 0)
                }
            }
            
            # Eğer satış tahmin verisi varsa ekle
            if sales_forecast is not None:
                # forecast_days değişkenini tanımla
                days_to_forecast = 30  # Varsayılan tahmin gün sayısı
                
                prompt_data["sales_forecast"] = {
                    "next_7_days": float(sales_forecast.iloc[-days_to_forecast:-days_to_forecast+7]['yhat'].sum()),
                    "next_15_days": float(sales_forecast.iloc[-days_to_forecast:-days_to_forecast+15]['yhat'].sum()),
                    "next_30_days": float(sales_forecast.iloc[-days_to_forecast:]['yhat'].sum())
                }
            
            # OpenAI'ye prompt gönder
            system_prompt = """
            Sen bir stok yönetim ve tahmin uzmanısın. Verilen ürün bilgilerine göre stok durumunu analiz et ve tavsiyelerde bulun.
            Satış tahminlerini kullanarak stok tükenmeden önce ne kadar süre kaldığını hesapla.
            Stok seviyelerinin yeterliliğini değerlendir ve sipariş zamanlaması için tavsiyeler sun.
            Yanıtını aşağıdaki JSON formatında oluştur:
            {
                "stock_analysis": {
                    "current_stock_level": "ürünün mevcut stok seviyesi",
                    "stock_status": "kritik/düşük/yeterli/yüksek/aşırı stok",
                    "estimated_days_until_stockout": "mevcut stokun tahmini kaç gün dayanacağı (tahmin edilebilirse)"
                },
                "recommendations": {
                    "action_needed": "stok ekle/stok azalt/izle/acil sipariş ver",
                    "suggested_order_quantity": "sipariş edilmesi önerilen miktar (gerekiyorsa)",
                    "optimal_timing": "sipariş verilmesi gereken en uygun zaman",
                    "explanation": "önerilerin detaylı açıklaması",
                    "confidence_level": "tavsiyenin güven düzeyi (düşük/orta/yüksek)"
                }
            }
            """
            
            response = self.client.chat.completions.create(
                model="gpt-4o", # the newest OpenAI model is "gpt-4o" which was released May 13, 2024. do not change this unless explicitly requested by the user
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(prompt_data, ensure_ascii=False)}
                ],
                response_format={"type": "json_object"}
            )
            
            # Yanıtı JSON olarak parse et
            try:
                # String olduğunu doğrula ve sonra parse et
                content = response.choices[0].message.content
                if isinstance(content, str):
                    analysis_result = json.loads(content)
                    return analysis_result
                else:
                    logger.error(f"AI yanıtı string değil: {type(content)}")
                    return {"error": "AI yanıtı beklenmeyen format"}
            except json.JSONDecodeError as e:
                logger.error(f"AI yanıtı JSON olarak parse edilemedi: {e}")
                return {"error": "AI yanıtı işlenirken hata oluştu"}
                
        except Exception as e:
            logger.error(f"AI stok analizi sırasında hata: {e}", exc_info=True)
            return {"error": f"Stok analizi yapılırken hata: {str(e)}"}
    
    def get_stock_health_report(self, top_n=20, days_forecast=30, include_variants=False):
        """
        Tüm ürünlerin stok durumu raporu
        """
        try:
            # Aktif ürünleri al (arşivde olmayanlar)
            products = Product.query.filter_by(archived=False).all()
            
            report_items = []
            
            if include_variants:
                # Her bir ürün varyantı için ayrı rapor
                for product in products:
                    # Gerçek tahmin yapma
                    sales_forecast = self.predict_future_sales(
                        product.product_main_id, 
                        product.color, 
                        product.size, 
                        forecast_days=days_forecast
                    )
                    
                    # Ürün verisi dictionary'si
                    product_data = {
                        "barcode": product.barcode,
                        "title": product.title,
                        "product_main_id": product.product_main_id,
                        "color": product.color,
                        "size": product.size,
                        "quantity": product.quantity,
                        "sale_price": product.sale_price,
                        "cost_try": product.cost_try
                    }
                    
                    # AI analizi
                    analysis = self.analyze_stock_with_ai(product_data, sales_forecast)
                    
                    # Rapor öğesi
                    item = {
                        "product": product_data,
                        "analysis": analysis
                    }
                    
                    report_items.append(item)
            else:
                # Modele ve renge göre grupla (varyantları birleştir)
                from sqlalchemy import func
                product_groups = db.session.query(
                    Product.product_main_id,
                    Product.color,
                    func.sum(Product.quantity).label('total_quantity')
                ).filter(
                    Product.archived == False
                ).group_by(
                    Product.product_main_id,
                    Product.color
                ).all()
                
                # Her grup için rapor
                for group in product_groups:
                    model_id, color, total_quantity = group
                    
                    # Grup için ilk ürünü örnek olarak al
                    sample_product = Product.query.filter_by(
                        product_main_id=model_id, 
                        color=color
                    ).first()
                    
                    if not sample_product:
                        continue
                    
                    # Satış tahmini
                    sales_forecast = self.predict_future_sales(
                        model_id, color, forecast_days=days_forecast
                    )
                    
                    # Ürün verisi dictionary'si
                    product_data = {
                        "barcode": f"{model_id}_{color}_group",
                        "title": sample_product.title,
                        "product_main_id": model_id,
                        "color": color,
                        "size": "Tüm Bedenler",
                        "quantity": total_quantity,
                        "sale_price": sample_product.sale_price,
                        "cost_try": sample_product.cost_try
                    }
                    
                    # AI analizi
                    analysis = self.analyze_stock_with_ai(product_data, sales_forecast)
                    
                    # Rapor öğesi
                    item = {
                        "product": product_data,
                        "analysis": analysis
                    }
                    
                    report_items.append(item)
            
            # En kritik ürünleri sırala
            def get_criticality_score(item):
                if "error" in item["analysis"]:
                    return 0
                    
                stock_status = item["analysis"].get("stock_analysis", {}).get("stock_status", "")
                days_until_stockout = item["analysis"].get("stock_analysis", {}).get("estimated_days_until_stockout", 999)
                
                if isinstance(days_until_stockout, str):
                    try:
                        days_until_stockout = float(days_until_stockout)
                    except:
                        days_until_stockout = 999
                
                # Kritiklik puanı - düşük stok ve az gün kalan ürünler önce gelsin
                if "kritik" in stock_status.lower():
                    return 1000 - days_until_stockout
                elif "düşük" in stock_status.lower():
                    return 500 - days_until_stockout
                elif "yeterli" in stock_status.lower():
                    return 0
                else:
                    return -500  # Yüksek ve aşırı stok en sonda
            
            # En kritikten en az kritiğe doğru sırala ve ilk N ürünü döndür
            sorted_items = sorted(report_items, key=get_criticality_score, reverse=True)
            return sorted_items[:top_n] if top_n else sorted_items
            
        except Exception as e:
            logger.error(f"Stok sağlık raporu alınırken hata: {e}", exc_info=True)
            return []

# Blueprint rotaları

@ai_stock_prediction_bp.route('/ai-stock-dashboard', methods=['GET'])
def ai_stock_dashboard():
    """
    AI destekli stok analiz paneli
    """
    include_variants = request.args.get('include_variants', 'false').lower() == 'true'
    top_n = int(request.args.get('top_n', 20))
    days = int(request.args.get('days', 30))
    
    predictor = StockPredictor()
    
    return render_template(
        'ai_stock_dashboard.html',
        include_variants=include_variants,
        top_n=top_n,
        days=days
    )

@ai_stock_prediction_bp.route('/api/stock-health-report', methods=['GET'])
def get_stock_health_report_api():
    """
    Stok sağlık raporu API'si
    """
    include_variants = request.args.get('include_variants', 'false').lower() == 'true'
    top_n = int(request.args.get('top_n', 20))
    days = int(request.args.get('days', 30))
    
    predictor = StockPredictor()
    report = predictor.get_stock_health_report(top_n=top_n, days_forecast=days, include_variants=include_variants)
    
    return jsonify({
        "success": True,
        "report": report,
        "count": len(report)
    })

@ai_stock_prediction_bp.route('/api/product-sales-prediction/<product_main_id>', methods=['GET'])
def get_product_sales_prediction_api(product_main_id):
    """
    Belirli bir ürün için satış tahmini API'si
    """
    color = request.args.get('color')
    size = request.args.get('size')
    forecast_days = int(request.args.get('forecast_days', 30))
    history_days = int(request.args.get('history_days', 90))
    
    predictor = StockPredictor()
    forecast = predictor.predict_future_sales(
        product_main_id, 
        color, 
        size, 
        forecast_days=forecast_days, 
        history_days=history_days
    )
    
    if forecast is None:
        return jsonify({
            "success": False,
            "message": "Tahmin için yeterli veri yok"
        })
    
    # Forecast dataframe'i JSON'a dönüştür
    forecast_data = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].to_dict(orient='records')
    
    return jsonify({
        "success": True,
        "forecast": forecast_data,
        "next_7_days": float(forecast.iloc[-forecast_days:-forecast_days+7]['yhat'].sum()),
        "next_15_days": float(forecast.iloc[-forecast_days:-forecast_days+15]['yhat'].sum()),
        "next_30_days": float(forecast.iloc[-forecast_days:]['yhat'].sum())
    })

@ai_stock_prediction_bp.route('/api/product-stock-analysis/<product_main_id>', methods=['GET'])
def get_product_stock_analysis_api(product_main_id):
    """
    Belirli bir ürün için AI stok analizi API'si
    """
    color = request.args.get('color')
    size = request.args.get('size')
    forecast_days = int(request.args.get('forecast_days', 30))
    
    # Ürünü bul
    product_query = Product.query.filter_by(product_main_id=product_main_id)
    if color:
        product_query = product_query.filter_by(color=color)
    if size:
        product_query = product_query.filter_by(size=size)
    
    product = product_query.first()
    
    if not product:
        return jsonify({
            "success": False,
            "message": "Ürün bulunamadı"
        })
    
    # Ürün verisi dictionary'si
    product_data = {
        "barcode": product.barcode,
        "title": product.title,
        "product_main_id": product.product_main_id,
        "color": product.color,
        "size": product.size,
        "quantity": product.quantity,
        "sale_price": product.sale_price,
        "cost_try": product.cost_try
    }
    
    predictor = StockPredictor()
    
    # Satış tahmini
    forecast = predictor.predict_future_sales(
        product_main_id, 
        color, 
        size, 
        forecast_days=forecast_days
    )
    
    # AI analizi
    analysis = predictor.analyze_stock_with_ai(product_data, forecast)
    
    return jsonify({
        "success": True,
        "product": product_data,
        "analysis": analysis
    })