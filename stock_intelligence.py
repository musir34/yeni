from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for
from models import db, Product
from sqlalchemy import func, desc, asc, and_, or_
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json
import logging
import os
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from prophet import Prophet
from prophet.plot import plot_plotly, plot_components_plotly
from flask_login import login_required, current_user
import openai
from dotenv import load_dotenv

# Logger ayarları
logger = logging.getLogger(__name__)

# Blueprint oluşturma
stock_intelligence_bp = Blueprint('stock_intelligence', __name__)

# .env dosyasını yükle
load_dotenv()

# OpenAI API anahtarını al
try:
    openai.api_key = os.environ.get("OPENAI_API_KEY")
except Exception as e:
    logger.error(f"OpenAI API anahtarı yüklenirken hata: {e}")

# Stok Zekası sınıfı
class StockIntelligence:
    def __init__(self):
        """Yapay zeka destekli stok tahmin sisteminin başlatıcısı"""
        self.app = current_app
        self.logger = logging.getLogger(__name__)
        self.prediction_settings = {
            'forecast_days': 30,  # Varsayılan tahmin süresi
            'history_days': 90,   # Varsayılan geçmiş veri süresi
            'confidence_interval': 0.9,  # %90 güven aralığı
            'include_history': True,     # Geçmiş verileri göster
        }
        
        # Stok durum eşikleri
        self.stock_thresholds = {
            'critical': 7,    # 7 gün veya daha az stok kaldıysa kritik
            'warning': 14,    # 14 gün veya daha az stok kaldıysa uyarı
            'healthy': 30,    # 30 gün veya daha fazla stok kaldıysa sağlıklı
        }
    
    def get_product_sales_data(self, product_main_id, color=None, size=None, days=90):
        """
        Belirli bir ürün için son {days} gündeki satış verilerini döndürür
        """
        try:
            # Tarih aralığını belirle
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Tüm satış tablolarını birleştiren bir sorgu (orders_* tabloları)
            # Burada "all_orders_union" fonksiyonunu kullanacağız
            from analysis import all_orders_union
            
            # Birleştirilmiş sorguyu al
            all_orders_query = all_orders_union(start_date, end_date)
            
            # Ürün filtresi (Temel filtreleme: model kodu)
            filters = [all_orders_query.c.product_main_id.contains(product_main_id)]
            
            # Renk filtresi (opsiyonel)
            if color:
                filters.append(all_orders_query.c.product_color.contains(color))
            
            # Beden filtresi (opsiyonel)
            if size:
                filters.append(all_orders_query.c.product_size.contains(size))
            
            # Ana sorgu: Günlük satış sayıları
            sales_by_date = db.session.query(
                func.date_trunc('day', all_orders_query.c.order_date).label('date'),
                func.sum(all_orders_query.c.quantity).label('sales')
            ).filter(
                and_(*filters)
            ).group_by(
                func.date_trunc('day', all_orders_query.c.order_date)
            ).order_by(
                func.date_trunc('day', all_orders_query.c.order_date)
            ).all()
            
            # Sonuçları pandas DataFrame'e dönüştür
            df = pd.DataFrame([(d.date, d.sales) for d in sales_by_date], columns=['ds', 'y'])
            
            # Eksik günleri doldur (satış olmayan günler)
            date_range = pd.date_range(start=start_date, end=end_date, freq='D')
            date_df = pd.DataFrame({'ds': date_range})
            df = pd.merge(date_df, df, on='ds', how='left')
            df['y'] = df['y'].fillna(0)
            
            return df
        
        except Exception as e:
            self.logger.error(f"Ürün satış verisi alınırken hata: {e}")
            return pd.DataFrame([(datetime.now() - timedelta(days=i), 0) for i in range(days, 0, -1)], columns=['ds', 'y'])
    
    def predict_future_sales(self, product_main_id, color=None, size=None, forecast_days=30, history_days=90):
        """
        Prophet modeli kullanarak gelecek satışları tahmin eder
        """
        try:
            # Geçmiş satış verilerini al
            sales_df = self.get_product_sales_data(product_main_id, color, size, days=history_days)
            
            # Yeterli veri var mı kontrol et
            if len(sales_df) < 7:  # En az 1 haftalık veri
                return {
                    'success': False,
                    'error': 'Yeterli satış verisi bulunamadı. Tahmin için en az 7 günlük veri gereklidir.'
                }
            
            # Prophet modelini oluştur ve eğit
            model = Prophet(
                interval_width=self.prediction_settings['confidence_interval'],
                seasonality_mode='multiplicative'
            )
            # Mevsimsellik ayarlarını manuel olarak ekleyelim
            model.add_seasonality(name='weekly', period=7, fourier_order=3)
            model.add_seasonality(name='yearly', period=365.25, fourier_order=5)
            
            # Çok düşük satışlar veya sıfır satışlar için özel ayarlar
            if sales_df['y'].mean() < 1:
                model = Prophet(
                    interval_width=self.prediction_settings['confidence_interval'],
                    seasonality_mode='additive'
                )
                # Düşük satışlar için daha basit model kullanalım
            
            # Modeli eğit
            model.fit(sales_df)
            
            # Tahmin için future DataFrame oluştur
            future = model.make_future_dataframe(periods=forecast_days)
            
            # Tahmin yap
            forecast = model.predict(future)
            
            # Tarih formatlarını düzenleme
            forecast['ds'] = forecast['ds'].dt.strftime('%Y-%m-%d')
            sales_df['ds'] = sales_df['ds'].dt.strftime('%Y-%m-%d')
            
            # Prophet tahmin grafiği oluştur
            fig1 = plot_plotly(model, forecast, figsize=(800, 500))
            fig1.update_layout(
                title='Ürün Satış Tahmini',
                xaxis_title='Tarih',
                yaxis_title='Satış Miktarı',
                legend_title='Veri Türü',
                template='plotly_white'
            )
            
            # Bileşen grafiği oluştur
            fig2 = plot_components_plotly(model, forecast, figsize=(800, 500))
            fig2.update_layout(
                title='Satış Tahmin Bileşenleri',
                template='plotly_white'
            )
            
            # Sonuçları döndür
            return {
                'success': True,
                'forecast': forecast.to_dict('records'),
                'sales_history': sales_df.to_dict('records'),
                'forecast_plot': fig1.to_json(),
                'components_plot': fig2.to_json(),
                'average_daily_sales': sales_df['y'].mean(),
                'forecast_total': forecast.iloc[-forecast_days:]['yhat'].sum(),
                'forecast_days': forecast_days
            }
            
        except Exception as e:
            self.logger.error(f"Satış tahmini yapılırken hata: {e}")
            return {
                'success': False,
                'error': f'Tahmin yapılırken hata oluştu: {str(e)}'
            }
    
    def analyze_stock_with_ai(self, product_data, sales_forecast=None):
        """
        OpenAI API'si kullanarak stok analizi yapar ve öneriler sunar
        """
        try:
            # OpenAI API anahtarı kontrol
            if not openai.api_key:
                return {
                    'success': False,
                    'error': 'OpenAI API anahtarı bulunamadı.'
                }
            
            # Ürün bilgilerini hazırla
            product_info = {
                'ürün_kodu': product_data.get('product_main_id', ''),
                'ürün_adı': product_data.get('title', ''),
                'renk': product_data.get('color', ''),
                'beden': product_data.get('size', ''),
                'mevcut_stok': product_data.get('quantity', 0),
            }
            
            # Tahmin verileri varsa ekle
            if sales_forecast and sales_forecast.get('success'):
                forecast_data = sales_forecast.get('forecast', [])
                history_data = sales_forecast.get('sales_history', [])
                
                # Son 30 günün ortalama günlük satışı
                avg_daily_sales = 0
                if history_data:
                    sales_values = [item.get('y', 0) for item in history_data]
                    avg_daily_sales = sum(sales_values) / len(sales_values) if sales_values else 0
                
                # Gelecek 30 günün toplam tahmini satışı
                forecast_total = 0
                if forecast_data:
                    forecast_days = sales_forecast.get('forecast_days', 30)
                    forecast_values = [item.get('yhat', 0) for item in forecast_data[-forecast_days:]]
                    forecast_total = sum(forecast_values)
                
                # Tahmini tükenme süresi (gün)
                stock_out_days = float('inf')  # Varsayılan olarak sonsuz
                if avg_daily_sales > 0 and product_info['mevcut_stok'] > 0:
                    stock_out_days = product_info['mevcut_stok'] / avg_daily_sales
                
                product_info.update({
                    'ortalama_günlük_satış': round(avg_daily_sales, 2),
                    'tahmini_30_gün_satış': round(forecast_total, 2),
                    'tahmini_tükenme_süresi_gün': round(stock_out_days, 1) if stock_out_days != float('inf') else 'tükenmeyecek'
                })
            
            # OpenAI API istek mesajı - modern format
            system_message = "Sen bir yapay zeka destekli stok analiz ve üretim planlama uzmanısın. Verilen ürün ve satış verileri doğrultusunda akıllı stok analizi yapıp, üretim için öneriler sunacaksın. Analizini ve önerilerini kısa, net ve somut yap. Temelde şunları belirtmelisin: 1. Stok durumu (kritik, uyarı, veya sağlıklı) 2. Somut aksiyon (Örn: '35, 36, 38 numaralardan üret') 3. Üretilecek miktar (kesin rakam) 4. Aciliyet durumu (hemen, 1 hafta içinde, vb.)"
            
            user_message = f"""Aşağıdaki ürün ve satış verilerini analiz ederek stok durumunu değerlendir ve somut öneriler sun:
                
                {json.dumps(product_info, indent=2, ensure_ascii=False)}
                
                Üretim kararı için aşağıdakileri göz önünde bulundur:
                - Kritik stok (7 günden az kalan ürün): ACİL üretim gerektirir
                - Uyarı stoku (7-14 gün): Yakında üretim planlan
                - Sağlıklı stok (14+ gün): Şu an üretim gerektirmez
                
                Ürünün mevcutta kaç günlük satışı karşılayacağını, satış hızının nasıl olduğunu ve stok trend analizini yap.
                Üretimde önceliklendirme nedenini açıkla."""
                
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ]
            
            # OpenAI API çağrısı (modern format)
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.5,
                max_tokens=500
            )
            
            # Cevabı işle
            ai_analysis = response.choices[0].message.content
            
            # Stok durum kodunu belirle
            stock_status = "normal"
            if "kritik" in ai_analysis.lower():
                stock_status = "critical"
            elif "uyarı" in ai_analysis.lower():
                stock_status = "warning"
            
            # Somut aksiyonları çıkar
            action_needed = "Şu an için aksiyon gerekmiyor."
            production_need = 0
            
            if "üret" in ai_analysis.lower():
                # Basit bir yaklaşım: "X adet üret" ifadesini bul
                import re
                
                # Sayı ve "adet" kelimesiyle ilgili kalıpları ara
                matches = re.findall(r'(\d+)(?:\s*-\s*\d+)?\s*adet', ai_analysis)
                if matches:
                    production_need = int(matches[0])
                    
                # Aksiyon cümlesini bul
                action_sentences = [s for s in ai_analysis.split('.') if 'üret' in s.lower()]
                if action_sentences:
                    action_needed = action_sentences[0].strip()
            
            # Analiz sonuçlarını yapılandır
            analysis_result = {
                'success': True,
                'stock_analysis': {
                    'full_analysis': ai_analysis,
                    'stock_status': stock_status,
                    'stock_remaining_days': product_info.get('tahmini_tükenme_süresi_gün', 'belirsiz')
                },
                'recommendations': {
                    'action_needed': action_needed,
                    'production_amount': production_need
                }
            }
            
            return analysis_result
            
        except Exception as e:
            self.logger.error(f"AI stok analizi yapılırken hata: {e}")
            return {
                'success': False,
                'error': f'Stok analizi yapılırken hata oluştu: {str(e)}'
            }
    
    def get_stock_health_report(self, top_n=20, days_forecast=30, include_variants=False):
        """
        Tüm ürünlerin stok durumu raporu
        """
        try:
            products = []
            if include_variants:
                # Tüm varyantları dahil et
                products = Product.query.filter(
                    Product.archived.is_(False),
                    Product.hidden.is_(False),
                    Product.quantity.isnot(None)
                ).all()
            else:
                # Model ve renk bazında grupla
                with db.session.begin() as session:
                    # Önce model ve renk bazında grupla
                    products_grouped = session.query(
                        Product.product_main_id,
                        Product.color,
                        func.sum(Product.quantity).label('total_quantity')
                    ).filter(
                        Product.archived.is_(False),
                        Product.hidden.is_(False),
                        Product.quantity.isnot(None)
                    ).group_by(
                        Product.product_main_id,
                        Product.color
                    ).all()
                    
                    # Her grup için bir ürün örneği al
                    for group in products_grouped:
                        product = Product.query.filter(
                            Product.product_main_id == group.product_main_id,
                            Product.color == group.color,
                            Product.archived.is_(False)
                        ).first()
                        
                        if product:
                            # Toplam stok miktarını ata
                            product.quantity = group.total_quantity
                            products.append(product)
            
            # Her ürün için analiz yap
            results = []
            for product in products:
                # Satış tahminini al
                forecast = self.predict_future_sales(
                    product.product_main_id, 
                    product.color,
                    forecast_days=days_forecast
                )
                
                # Tahmin başarılı ise analiz yap
                if forecast.get('success'):
                    # Ürün verilerini topla
                    product_data = {
                        'product_main_id': product.product_main_id,
                        'title': product.title,
                        'color': product.color,
                        'size': product.size,
                        'quantity': product.quantity,
                        'barcode': product.barcode
                    }
                    
                    # AI analizi yap
                    analysis = self.analyze_stock_with_ai(product_data, forecast)
                    
                    # Sonucu listeye ekle
                    results.append({
                        'product': product_data,
                        'forecast': forecast,
                        'analysis': analysis
                    })
            
            # Kritiklik skoruna göre sırala
            def get_criticality_score(item):
                # Analiz başarısız ise düşük puan ver
                if not item['analysis'].get('success'):
                    return -1
                
                # Stok durumuna göre puan
                stock_status = item['analysis']['stock_analysis']['stock_status']
                if stock_status == 'critical':
                    return 3
                elif stock_status == 'warning':
                    return 2
                else:
                    return 1
            
            # Sonuçları kritiklik skoruna göre sırala
            results.sort(key=get_criticality_score, reverse=True)
            
            # En yüksek puanlı (en kritik) top_n ürünü döndür
            return results[:top_n]
            
        except Exception as e:
            self.logger.error(f"Stok sağlık raporu oluşturulurken hata: {e}")
            return []

# Routes (API ve Arayüz)

@stock_intelligence_bp.route('/dashboard')
@login_required
def ai_stock_dashboard():
    """
    AI destekli stok analiz paneli
    """
    return render_template('ai_stock_dashboard.html')

@stock_intelligence_bp.route('/api/stock-health-report')
@login_required
def get_stock_health_report_api():
    """
    Stok sağlık raporu API'si
    """
    try:
        # Query parametrelerini al
        top_n = request.args.get('top_n', 20, type=int)
        days_forecast = request.args.get('days_forecast', 30, type=int)
        include_variants = request.args.get('include_variants', 'false').lower() == 'true'
        
        # Stok zekası sınıfını başlat
        stock_intelligence = StockIntelligence()
        
        # Raporu al
        report = stock_intelligence.get_stock_health_report(
            top_n=top_n,
            days_forecast=days_forecast,
            include_variants=include_variants
        )
        
        return jsonify(report)
    
    except Exception as e:
        logger.error(f"Stok raporu API hatası: {e}")
        return jsonify({'error': str(e)}), 500

@stock_intelligence_bp.route('/api/product-sales-prediction/<product_main_id>')
@login_required
def get_product_sales_prediction_api(product_main_id):
    """
    Belirli bir ürün için satış tahmini API'si
    """
    try:
        # Query parametrelerini al
        color = request.args.get('color')
        size = request.args.get('size')
        forecast_days = request.args.get('forecast_days', 30, type=int)
        history_days = request.args.get('history_days', 90, type=int)
        
        # Stok zekası sınıfını başlat
        stock_intelligence = StockIntelligence()
        
        # Tahmini al
        forecast = stock_intelligence.predict_future_sales(
            product_main_id=product_main_id,
            color=color,
            size=size,
            forecast_days=forecast_days,
            history_days=history_days
        )
        
        return jsonify(forecast)
    
    except Exception as e:
        logger.error(f"Satış tahmini API hatası: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@stock_intelligence_bp.route('/api/product-stock-analysis/<product_main_id>')
@login_required
def get_product_stock_analysis_api(product_main_id):
    """
    Belirli bir ürün için AI stok analizi API'si
    """
    try:
        # Query parametrelerini al
        color = request.args.get('color')
        size = request.args.get('size')
        
        # Ürün verisini al
        if size:
            # Belirli bir beden için
            product = Product.query.filter(
                Product.product_main_id == product_main_id,
                Product.color == color,
                Product.size == size,
                Product.archived.is_(False)
            ).first()
        else:
            # Tüm bedenler için toplu analiz
            product = Product.query.filter(
                Product.product_main_id == product_main_id,
                Product.color == color,
                Product.archived.is_(False)
            ).first()
            
            if product:
                # Aynı model ve renkteki tüm ürünlerin toplam stok miktarını hesapla
                total_quantity = db.session.query(func.sum(Product.quantity)).filter(
                    Product.product_main_id == product_main_id,
                    Product.color == color,
                    Product.archived.is_(False)
                ).scalar() or 0
                
                # Toplam stok miktarını ata
                product.quantity = total_quantity
        
        if not product:
            return jsonify({'success': False, 'error': 'Ürün bulunamadı'})
        
        # Ürün verisini hazırla
        product_data = {
            'product_main_id': product.product_main_id,
            'title': product.title,
            'color': product.color,
            'size': product.size,
            'quantity': product.quantity,
            'barcode': product.barcode
        }
        
        # Stok zekası sınıfını başlat
        stock_intelligence = StockIntelligence()
        
        # Satış tahmini
        forecast = stock_intelligence.predict_future_sales(
            product_main_id=product_main_id,
            color=color,
            size=size
        )
        
        # Stok analizi
        analysis = stock_intelligence.analyze_stock_with_ai(product_data, forecast)
        
        # Sonuçları birleştir
        response = {
            'success': True,
            'product': product_data,
            'forecast': forecast,
            'analysis': analysis
        }
        
        return jsonify(response)
    
    except Exception as e:
        logger.error(f"Stok analizi API hatası: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500