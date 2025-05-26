from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for, flash, session
from models import db, Product, StockAnalysisRecord, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled
from sqlalchemy import func, desc, asc, and_, or_, extract, text, select
from datetime import datetime, timedelta, date
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
from collections import defaultdict
import re
import holidays
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import io
import base64
from PIL import Image, ImageDraw, ImageFont
import uuid

# Logger ayarları
logger = logging.getLogger(__name__)

# Blueprint oluşturma
stock_intelligence_bp = Blueprint('stock_intelligence', __name__, url_prefix='/stock_intelligence')

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
            'seasonality_mode': 'multiplicative',  # Mevsimsellik modu
            'seasonality_prior_scale': 10.0,  # Mevsimsellik ağırlığı
            'holidays_prior_scale': 10.0,  # Tatil günleri ağırlığı
            'changepoint_prior_scale': 0.05,  # Değişim noktaları hassasiyeti
        }

        # Stok durum eşikleri
        self.stock_thresholds = {
            'critical': 7,    # 7 gün veya daha az stok kaldıysa kritik
            'warning': 14,    # 14 gün veya daha az stok kaldıysa uyarı
            'healthy': 30,    # 30 gün veya daha fazla stok kaldıysa sağlıklı
        }

        # E-posta bildirim ayarları
        self.notification_settings = {
            'enabled': False,  # Varsayılan olarak kapalı
            'recipients': [],  # Bildirim alacak e-postalar
            'critical_threshold': 5,  # En az bu kadar kritik ürün olduğunda bildirim gönder
            'warning_threshold': 10,  # En az bu kadar uyarı ürünü olduğunda bildirim gönder
            'frequency': 'daily',  # daily, weekly
            'time': '09:00',  # Bildirim saati
        }

        # Satış kanalları
        self.sales_channels = [
            'online',  # Online satış
            'store',   # Mağaza satışı
            'wholesale'  # Toptan satış
        ]

        # Kategori sınıflandırması
        self.product_categories = {
            'casual': 'Günlük Ayakkabı',
            'formal': 'Klasik Ayakkabı',
            'sport': 'Spor Ayakkabı',
            'boots': 'Çizme/Bot',
            'sandals': 'Sandalet/Terlik',
            'special': 'Özel Tasarım'
        }

        # Tarihsel karşılaştırma periyotları
        self.comparison_periods = {
            'last_week': 7,
            'last_month': 30,
            'last_quarter': 90,
            'last_year': 365
        }

        # Türkiye tatil günleri
        try:
            # Holidays paketi farklı ülke kodları kullanabiliyor, TR veya Turkey deniyoruz
            import holidays
            try:
                self.tr_holidays = holidays.Turkey()
            except:
                try:
                    self.tr_holidays = holidays.TR()
                except:
                    # Varsayılan olarak boş sözlük
                    self.tr_holidays = {}
        except Exception as e:
            self.logger.warning(f"Tatil günleri yüklenirken hata: {e}")
            self.tr_holidays = {}

    def combined_orders_query(self):
        """
        Tüm sipariş tablolarını birleştiren bir alt sorgu oluşturur
        (Created, Picking, Shipped, Delivered, Cancelled)
        Cancelled siparişler genellikle satıştan sayılmaz, bu yüzden hariç tutulabilir veya farklı işlenebilir.
        Şimdilik Created, Picking, Shipped, Delivered tablolarını birleştirelim.
        """
        from sqlalchemy import union_all, select, literal_column
        from sqlalchemy.sql import alias
        # models importları dosyanın başında zaten var, burada tekrar gerek yok.

        created = select(
            OrderCreated.id,
            OrderCreated.order_number,
            OrderCreated.order_date,
            literal_column("'Created'").label('status'),
            OrderCreated.quantity,
            OrderCreated.amount,
            OrderCreated.product_main_id,
            OrderCreated.product_color,
            OrderCreated.product_size,
            OrderCreated.merchant_sku
        )

        picking = select(
            OrderPicking.id,
            OrderPicking.order_number,
            OrderPicking.order_date,
            literal_column("'Picking'").label('status'),
            OrderPicking.quantity,
            OrderPicking.amount,
            OrderPicking.product_main_id,
            OrderPicking.product_color,
            OrderPicking.product_size,
            OrderPicking.merchant_sku
        )

        shipped = select(
            OrderShipped.id,
            OrderShipped.order_number,
            OrderShipped.order_date,
            literal_column("'Shipped'").label('status'),
            OrderShipped.quantity,
            OrderShipped.amount,
            OrderShipped.product_main_id,
            OrderShipped.product_color,
            OrderShipped.product_size,
            OrderShipped.merchant_sku
        )

        delivered = select(
            OrderDelivered.id,
            OrderDelivered.order_number,
            OrderDelivered.order_date,
            literal_column("'Delivered'").label('status'),
            OrderDelivered.quantity,
            OrderDelivered.amount,
            OrderDelivered.product_main_id,
            OrderDelivered.product_color,
            OrderDelivered.product_size,
            OrderDelivered.merchant_sku
        )

        # UNION ALL ile hepsini birleştir
        # Satış tahmini için genellikle sadece 'Delivered' veya 'Shipped' olanlar dikkate alınır.
        # Ancak burada tüm hareketleri görmek için birleştiriyoruz.
        # İptal edilen siparişleri (OrderCancelled) bu birleşime dahil etmiyoruz çünkü satış sayılmazlar.
        union_query = union_all(created, picking, shipped, delivered)

        return union_query.alias(name='all_orders')

    def get_product_sales_data(self, product_main_id, color=None, size=None, days=90):
        """
        Belirli bir ürün için son {days} gündeki satış verilerini döndürür.
        Satış olarak 'Delivered' veya 'Shipped' durumundaki siparişler kabul edilebilir.
        Bu örnekte, combined_orders_query'den gelen ve 'Cancelled' olmayan tüm hareketleri alıp,
        sonrasında daha spesifik filtreleme yapılabilir ya da direkt bu fonksiyon içinde
        sadece belirli statüdeki siparişler sorgulanabilir.
        Şimdilik, tüm birleşik siparişleri (iptaller hariç) kullanıyoruz.
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # combined_orders_query tüm sipariş hareketlerini (iptaller hariç) getirir.
            # Satış tahmini için genellikle sadece 'Delivered' (teslim edildi) veya 'Shipped' (kargolandı)
            # siparişler dikkate alınır. Bu fonksiyon bu ayrımı yapmalı.
            # Şimdilik combined_orders_query'yi kullanıyoruz ama idealde filtrelenmeli.

            # Örnek: Sadece 'Delivered' siparişleri almak için
            # query = db.session.query(
            #     func.date_trunc('day', OrderDelivered.order_date).label('date'),
            #     func.sum(OrderDelivered.quantity).label('sales')
            # ).filter(OrderDelivered.order_date >= start_date, OrderDelivered.order_date <= end_date)

            # Mevcut combined_orders_query'yi kullanarak devam edelim ve product_main_id, color, size filtrelerini ekleyelim.
            # Satışları temsil eden durumlar 'Shipped' ve 'Delivered' olarak kabul edilebilir.

            all_sales_query = select(
                OrderDelivered.order_date.label('order_date'),
                OrderDelivered.quantity.label('quantity'),
                OrderDelivered.product_main_id.label('product_main_id'),
                OrderDelivered.product_color.label('product_color'),
                OrderDelivered.product_size.label('product_size')
            ).where(
                OrderDelivered.order_date.between(start_date, end_date)
            ).union_all(
                select(
                    OrderShipped.order_date,
                    OrderShipped.quantity,
                    OrderShipped.product_main_id,
                    OrderShipped.product_color,
                    OrderShipped.product_size
                ).where(
                    OrderShipped.order_date.between(start_date, end_date)
                )
            ).alias('actual_sales')


            filters = [all_sales_query.c.product_main_id.contains(product_main_id)]
            if color:
                filters.append(all_sales_query.c.product_color.contains(color))
            if size:
                filters.append(all_sales_query.c.product_size.contains(size))

            sales_by_date_query = db.session.query(
                func.date_trunc('day', all_sales_query.c.order_date).label('date'),
                func.sum(all_sales_query.c.quantity).label('sales')
            ).select_from(all_sales_query).filter(
                and_(*filters)
            ).group_by(
                func.date_trunc('day', all_sales_query.c.order_date)
            ).order_by(
                func.date_trunc('day', all_sales_query.c.order_date)
            )

            sales_by_date = sales_by_date_query.all()

            df = pd.DataFrame([(d.date, float(d.sales) if d.sales is not None else 0) for d in sales_by_date], columns=['ds', 'y'])

            # Tarih aralığını datetime objeleriyle oluştur
            date_range_pd = pd.date_range(start=start_date.date(), end=end_date.date(), freq='D')
            date_df = pd.DataFrame({'ds': date_range_pd})

            # df'teki 'ds' sütununu da datetime objesine çevir (eğer değilse)
            if not pd.api.types.is_datetime64_any_dtype(df['ds']):
                 df['ds'] = pd.to_datetime(df['ds'])

            df = pd.merge(date_df, df, on='ds', how='left')
            df['y'] = df['y'].fillna(0).astype(float)

            return df

        except Exception as e:
            self.logger.error(f"Ürün satış verisi alınırken hata: {e}")
            # Hata durumunda boş DataFrame yerine, beklenen formatta boş veri döndür
            date_range_pd = pd.date_range(start=(datetime.now() - timedelta(days=days)).date(), end=datetime.now().date(), freq='D')
            return pd.DataFrame({'ds': date_range_pd, 'y': 0})

    def get_model_variants_data(self, product_main_id=None, days=7):
        """
        Belirli bir model kodu için tüm renk ve beden varyantlarının satış verilerini döndürür
        Eğer product_main_id None ise, tüm modeller için verileri getirir (bu durumda çok veri olabilir, dikkatli kullanılmalı)
        Sonuçları hiyerarşik yapıda model -> renk -> beden şeklinde döndürür
        Satışlar 'Delivered' veya 'Shipped' siparişlerden hesaplanır.
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # Satışları temsil eden sorgu (Delivered ve Shipped)
            sales_query = select(
                OrderDelivered.product_main_id,
                OrderDelivered.product_color,
                OrderDelivered.product_size,
                OrderDelivered.order_date,
                OrderDelivered.quantity
            ).where(OrderDelivered.order_date.between(start_date, end_date)
            ).union_all(
                select(
                    OrderShipped.product_main_id,
                    OrderShipped.product_color,
                    OrderShipped.product_size,
                    OrderShipped.order_date,
                    OrderShipped.quantity
                ).where(OrderShipped.order_date.between(start_date, end_date))
            ).alias('sales_data')

            filters = []
            if product_main_id:
                filters.append(sales_query.c.product_main_id == product_main_id)

            sales_by_variant_query = db.session.query(
                sales_query.c.product_main_id,
                sales_query.c.product_color,
                sales_query.c.product_size,
                func.sum(sales_query.c.quantity).label('total_sales')
            ).select_from(sales_query).filter(
                and_(*filters) # Filtreleri uygula
            ).group_by(
                sales_query.c.product_main_id,
                sales_query.c.product_color,
                sales_query.c.product_size
            ).order_by(
                sales_query.c.product_main_id,
                sales_query.c.product_color,
                sales_query.c.product_size
            )

            sales_by_variant = sales_by_variant_query.all()

            result = []

            if product_main_id and not sales_by_variant:
                self.logger.info(f"Model {product_main_id} için son {days} günde satış verisi bulunamadı, mevcut stoklarla listeleniyor.")
                products_db = Product.query.filter(
                    Product.product_main_id == product_main_id,
                    Product.archived.is_(False)
                ).all()

                if not products_db:
                    return []

                model_info_data = {
                    'model_id': product_main_id,
                    'title': products_db[0].title if products_db else product_main_id,
                    'colors': []
                }

                colors_data_map = {}
                for p_item in products_db:
                    if p_item.color not in colors_data_map:
                        colors_data_map[p_item.color] = {
                            'color': p_item.color,
                            'total_sales': 0,
                            'current_stock': 0,
                            'image': p_item.images, # İlk bulduğu ürünün resmini alır
                            'sizes': [],
                            'daily_avg_sales': 0,
                            'days_until_stockout': "∞",
                            'suggested_production': 0
                        }

                    colors_data_map[p_item.color]['current_stock'] += (p_item.quantity or 0)
                    colors_data_map[p_item.color]['sizes'].append({
                        'size': p_item.size,
                        'barcode': p_item.barcode,
                        'total_sales': 0,
                        'daily_avg_sales': 0,
                        'current_stock': (p_item.quantity or 0),
                        'days_until_stockout': "∞",
                        'suggested_production': max(0, int((0 * 30) - (p_item.quantity or 0))) # 0 satışa göre öneri
                    })

                for color_name_key, color_val_data in colors_data_map.items():
                    color_val_data['sizes'] = sorted(color_val_data['sizes'], key=lambda x: float(x['size']) if x['size'] and x['size'].isdigit() else 0)
                    model_info_data['colors'].append(color_val_data)

                model_info_data['colors'] = sorted(model_info_data['colors'], key=lambda x: x['color'])
                return [model_info_data]

            models_map = {}
            for sale_item in sales_by_variant:
                model_id_val = sale_item[0]
                color_val = sale_item[1]
                size_val = sale_item[2]
                total_sales_val = float(sale_item[3]) if sale_item[3] is not None else 0

                if model_id_val not in models_map:
                    product_ref = Product.query.filter(Product.product_main_id == model_id_val).first()
                    models_map[model_id_val] = {
                        'model_id': model_id_val,
                        'title': product_ref.title if product_ref else model_id_val,
                        'colors': {}
                    }

                if color_val not in models_map[model_id_val]['colors']:
                    color_stock_val = db.session.query(func.sum(Product.quantity)).filter(
                        Product.product_main_id == model_id_val,
                        Product.color == color_val,
                        Product.archived.is_(False)
                    ).scalar() or 0
                    product_color_ref = Product.query.filter(Product.product_main_id == model_id_val, Product.color == color_val).first()
                    models_map[model_id_val]['colors'][color_val] = {
                        'color': color_val,
                        'total_sales': 0,
                        'current_stock': int(color_stock_val),
                        'image': product_color_ref.images if product_color_ref else "",
                        'sizes': {}
                    }

                size_stock_val = db.session.query(func.sum(Product.quantity)).filter(
                    Product.product_main_id == model_id_val,
                    Product.color == color_val,
                    Product.size == size_val,
                    Product.archived.is_(False)
                ).scalar() or 0

                daily_avg_sales_val = total_sales_val / days if days > 0 else 0
                days_until_stockout_val = (size_stock_val / daily_avg_sales_val) if daily_avg_sales_val > 0 else float('inf')
                target_days_val = 30
                suggested_production_val = max(0, int((daily_avg_sales_val * target_days_val) - size_stock_val))

                size_product_ref = Product.query.filter(
                    Product.product_main_id == model_id_val,
                    Product.color == color_val,
                    Product.size == size_val
                ).first()

                models_map[model_id_val]['colors'][color_val]['sizes'][size_val] = {
                    'size': size_val,
                    'barcode': size_product_ref.barcode if size_product_ref else "-",
                    'total_sales': total_sales_val,
                    'daily_avg_sales': round(daily_avg_sales_val, 2),
                    'current_stock': int(size_stock_val),
                    'days_until_stockout': round(days_until_stockout_val, 1) if days_until_stockout_val != float('inf') else "∞",
                    'suggested_production': suggested_production_val
                }
                models_map[model_id_val]['colors'][color_val]['total_sales'] += total_sales_val

            for model_id_key, model_item_data in models_map.items():
                colors_list_data = []
                for color_name_key, color_item_data in model_item_data['colors'].items():
                    sizes_list_data = sorted(list(color_item_data['sizes'].values()), key=lambda x: float(x['size']) if x['size'] and x['size'].isdigit() else 0)

                    color_stock_total = color_item_data['current_stock']
                    color_sales_total = color_item_data['total_sales']
                    color_daily_avg_sales = (color_sales_total / days) if days > 0 else 0
                    color_days_until_stockout = (color_stock_total / color_daily_avg_sales) if color_daily_avg_sales > 0 else float('inf')
                    color_suggested_production = max(0, int((color_daily_avg_sales * 30) - color_stock_total))

                    color_item_data['sizes'] = sizes_list_data
                    color_item_data['daily_avg_sales'] = round(color_daily_avg_sales, 2)
                    color_item_data['days_until_stockout'] = round(color_days_until_stockout, 1) if color_days_until_stockout != float('inf') else "∞"
                    color_item_data['suggested_production'] = color_suggested_production
                    colors_list_data.append(color_item_data)

                model_item_data['colors'] = sorted(colors_list_data, key=lambda x: x['color'])
                result.append(model_item_data)

            return result

        except Exception as e:
            self.logger.error(f"Model varyant verisi alınırken hata: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []

    def predict_future_sales(self, product_main_id, color=None, size=None, forecast_days=30, history_days=90):
        """
        Prophet modeli kullanarak gelecek satışları tahmin eder
        Mevsimsellik, tatil günleri ve özel günleri dikkate alır
        """
        try:
            sales_df = self.get_product_sales_data(product_main_id, color, size, days=history_days)

            if len(sales_df) < 7 or sales_df['y'].sum() == 0 : # En az 7 günlük veri ve en az 1 satış
                self.logger.warning(f"Yetersiz satış verisi: {product_main_id}, color: {color}, size: {size}. Satış sayısı: {sales_df['y'].sum()}, Veri noktası: {len(sales_df)}")
                # Yetersiz veri durumunda grafikler için boş veya sıfır tahmin döndür
                blank_future = pd.date_range(start=sales_df['ds'].max() + timedelta(days=1) if not sales_df.empty else datetime.now(), periods=forecast_days, freq='D')
                blank_forecast_df = pd.DataFrame({'ds': blank_future, 'yhat': 0, 'yhat_lower': 0, 'yhat_upper': 0})

                # Tarih formatlarını düzenle
                sales_df['ds'] = pd.to_datetime(sales_df['ds']).dt.strftime('%Y-%m-%d')
                blank_forecast_df['ds'] = pd.to_datetime(blank_forecast_df['ds']).dt.strftime('%Y-%m-%d')

                return {
                    'success': True, # Başarılı ama tahmin yok gibi işaretleyebiliriz veya success: False
                    'message': 'Yeterli satış verisi bulunamadı veya hiç satış yapılmamış. Tahmin yapılamadı.',
                    'forecast': blank_forecast_df.to_dict('records'),
                    'sales_history': sales_df.to_dict('records'),
                    'forecast_plot': go.Figure().to_json(), # Boş grafik
                    'components_plot': go.Figure().to_json(), # Boş grafik
                    'average_daily_sales': 0,
                    'forecast_total': 0,
                    'forecast_days': forecast_days
                }

            sales_df['y'] = pd.to_numeric(sales_df['y'], errors='coerce').fillna(0)

            model = Prophet(
                interval_width=self.prediction_settings['confidence_interval'],
                seasonality_mode=self.prediction_settings['seasonality_mode'],
                seasonality_prior_scale=self.prediction_settings['seasonality_prior_scale'],
                changepoint_prior_scale=self.prediction_settings['changepoint_prior_scale']
            )

            model.add_seasonality(name='weekly', period=7, fourier_order=3) # Basitleştirilmiş fourier order
            if history_days > 180 : # Yıllık mevsimsellik için daha fazla veri gerekebilir
                 model.add_seasonality(name='yearly', period=365.25, fourier_order=5) # Basitleştirilmiş
            if history_days > 60: # Aylık için
                 model.add_seasonality(name='monthly', period=30.5, fourier_order=3) # Basitleştirilmiş

            try:
                if self.tr_holidays: # Eğer tatil günleri yüklendiyse
                    # Prophet için tatil günlerini DataFrame formatına getir
                    current_year = datetime.now().year
                    years_for_holidays = list(range(current_year - 2, current_year + 3)) # Son 2 yıl ve gelecek 2 yıl + bu yıl

                    holiday_events = []
                    for year_to_check in years_for_holidays:
                        for date_val, name_val in sorted(holidays.Turkey(years=year_to_check).items()):
                            holiday_events.append({'holiday': name_val, 'ds': pd.to_datetime(date_val)})

                    if holiday_events:
                        holidays_df = pd.DataFrame(holiday_events)
                        model.add_regressor('holidays_effect', prior_scale=self.prediction_settings['holidays_prior_scale'], mode='additive')
                        # sales_df'e tatil günlerini ekle (0/1 olarak)
                        sales_df['holidays_effect'] = 0
                        for hol_date in holidays_df['ds']:
                            sales_df.loc[sales_df['ds'].dt.date == hol_date.date(), 'holidays_effect'] = 1

            except Exception as holiday_error:
                self.logger.warning(f"Tatil günleri Prophet'e eklenirken hata: {holiday_error}")

            # Özel günler (manuel)
            special_events_list = [
                {'holiday': 'OkulAcilisi', 'ds': pd.to_datetime(f'{datetime.now().year}-09-15'), 'lower_window': -15, 'upper_window': 5},
                {'holiday': 'KisSezonuBaslangic', 'ds': pd.to_datetime(f'{datetime.now().year}-11-01'), 'lower_window': -15, 'upper_window': 30},
                {'holiday': 'YazSezonuBaslangic', 'ds': pd.to_datetime(f'{datetime.now().year}-05-01'), 'lower_window': -15, 'upper_window': 30},
            ]
            # Gelecek yıllar için de eklenebilir
            for i in range(1, 3): # Gelecek 2 yıl için
                special_events_list.extend([
                    {'holiday': 'OkulAcilisi', 'ds': pd.to_datetime(f'{datetime.now().year+i}-09-15'), 'lower_window': -15, 'upper_window': 5},
                    {'holiday': 'KisSezonuBaslangic', 'ds': pd.to_datetime(f'{datetime.now().year+i}-11-01'), 'lower_window': -15, 'upper_window': 30},
                    {'holiday': 'YazSezonuBaslangic', 'ds': pd.to_datetime(f'{datetime.now().year+i}-05-01'), 'lower_window': -15, 'upper_window': 30},
                ])

            events_df = pd.DataFrame(special_events_list)
            # events_df'teki ds sütununu datetime yap
            events_df['ds'] = pd.to_datetime(events_df['ds'])

            # Prophet'in beklediği tatil formatı: 'holiday' ve 'ds' sütunları olan bir DataFrame
            # Eğer model.holidays zaten varsa birleştir, yoksa ata
            if hasattr(model, 'holidays') and model.holidays is not None:
                 model.holidays = pd.concat([model.holidays, events_df])
            else:
                 model.holidays = events_df


            model.fit(sales_df.copy()) # .copy() ile orijinal df'i koru

            future = model.make_future_dataframe(periods=forecast_days)

            # Eğer tatil etkisini regressor olarak eklediysek, future df'e de eklemeliyiz.
            if 'holidays_effect' in sales_df.columns:
                future['holidays_effect'] = 0
                if 'holidays_df' in locals() and not holidays_df.empty:
                     for hol_date_fut in holidays_df['ds']:
                        future.loc[future['ds'].dt.date == hol_date_fut.date(), 'holidays_effect'] = 1

            forecast = model.predict(future)

            forecast_display = forecast.copy()
            sales_df_display = sales_df.copy()

            # Tarihleri string'e çevirmeden önce datetime objesi olduklarından emin ol
            forecast_display['ds'] = pd.to_datetime(forecast_display['ds']).dt.strftime('%Y-%m-%d')
            sales_df_display['ds'] = pd.to_datetime(sales_df_display['ds']).dt.strftime('%Y-%m-%d')

            try:
                fig1 = plot_plotly(model, forecast, figsize=(750, 500)) # Boyut ayarı
                fig1.update_layout(
                    title={'text': f'{product_main_id} Ürün Satış Tahmini', 'font': {'size': 18}},
                    xaxis_title='Tarih', yaxis_title='Satış Miktarı',
                    template='plotly_white', margin=dict(t=50, l=50, r=30, b=50)
                )
                today_val = datetime.now()
                fig1.add_shape(type="line", line=dict(dash="dash", width=1, color="red"),
                               x0=today_val, y0=0, x1=today_val, y1=1, yref="paper")
                fig1.add_annotation(x=today_val, y=1, yref="paper", text="Bugün", showarrow=False, yanchor="bottom", font=dict(color="red", size=10))

                fig2 = plot_components_plotly(model, forecast, figsize=(750, 550)) # Boyut ayarı
                fig2.update_layout(
                    title={'text': f'{product_main_id} Satış Bileşenleri', 'font': {'size': 18}},
                    template='plotly_white', height=600, margin=dict(t=50, l=50, r=30, b=50)
                )
                # Alt grafik başlıklarını Türkçeleştirme (isteğe bağlı, daha karmaşık olabilir)
                # Örnek: fig2.layout.annotations[0].text = 'Trend' (indekslere dikkat)

                avg_daily_sales_val = float(sales_df['y'].mean()) if not pd.isna(sales_df['y'].mean()) else 0.0
                # Tahmin edilen satışlar negatif olmamalı
                forecast_total_val = forecast.iloc[-forecast_days:]['yhat'].apply(lambda x: max(0, x)).sum()
                forecast_total_val = float(forecast_total_val) if not pd.isna(forecast_total_val) else 0.0

                return {
                    'success': True,
                    'forecast': forecast_display[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].to_dict('records'),
                    'sales_history': sales_df_display.to_dict('records'),
                    'forecast_plot': fig1.to_json(),
                    'components_plot': fig2.to_json(),
                    'average_daily_sales': round(avg_daily_sales_val,2),
                    'forecast_total': round(forecast_total_val,2),
                    'forecast_days': forecast_days
                }
            except Exception as e_plot:
                self.logger.error(f"Prophet grafik oluşturma hatası: {e_plot}")
                avg_daily_sales_val = float(sales_df['y'].mean()) if not pd.isna(sales_df['y'].mean()) else 0.0
                forecast_total_val = forecast.iloc[-forecast_days:]['yhat'].apply(lambda x: max(0, x)).sum() # Negatifleri 0 yap
                forecast_total_val = float(forecast_total_val) if not pd.isna(forecast_total_val) else 0.0

                return { # Grafik olmadan temel verileri döndür
                    'success': True,
                    'message': 'Tahmin yapıldı ancak grafikler oluşturulamadı.',
                    'forecast': forecast_display[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].to_dict('records'),
                    'sales_history': sales_df_display.to_dict('records'),
                    'forecast_plot': None,
                    'components_plot': None,
                    'average_daily_sales': round(avg_daily_sales_val,2),
                    'forecast_total': round(forecast_total_val,2),
                    'forecast_days': forecast_days
                }

        except Exception as e:
            self.logger.error(f"Satış tahmini yapılırken genel hata: {e}, Ürün: {product_main_id}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': f'Tahmin yapılırken bir hata oluştu: {str(e)}'
            }

    def analyze_stock_with_ai(self, product_data, sales_forecast=None):
        """
        OpenAI API'si kullanarak stok analizi yapar ve öneriler sunar
        """
        try:
            if not openai.api_key:
                return {'success': False, 'error': 'OpenAI API anahtarı bulunamadı.'}

            product_info_dict = {
                'ürün_kodu': product_data.get('product_main_id', ''),
                'ürün_adı': product_data.get('title', ''),
                'renk': product_data.get('color', ''),
                'beden': product_data.get('size', ''), # Beden bilgisi varsa ekle
                'mevcut_stok': product_data.get('quantity', 0),
            }

            # Eğer genel bir model-renk analizi ise (beden belirtilmemişse)
            if not product_data.get('size') and product_data.get('color'):
                 product_info_dict['analiz_kapsamı'] = f"{product_data.get('color')} renginin tüm bedenleri için genel durum"


            if sales_forecast and sales_forecast.get('success'):
                # sales_forecast['forecast'] bir liste, son forecast_days kadarını al
                forecast_days_val = sales_forecast.get('forecast_days', 30)

                # Ortalama günlük satış geçmiş veriden
                history_data_list = sales_forecast.get('sales_history', [])
                avg_daily_sales_hist = 0
                if history_data_list:
                    sales_values_hist = [item.get('y', 0) for item in history_data_list]
                    avg_daily_sales_hist = sum(sales_values_hist) / len(sales_values_hist) if sales_values_hist else 0

                # Gelecek X günün toplam tahmini satışı (negatif olmayan)
                forecast_data_list = sales_forecast.get('forecast', [])
                # Tahmin edilen günlük satışlar (yhat) üzerinden ortalama
                avg_forecasted_daily_sales = 0
                if forecast_data_list:
                    # Sadece tahmin periyodunu al (make_future_dataframe tüm geçmişi de içerir)
                    # forecast_days_val kadar sondan veri alıp ortalamasını hesapla
                    future_forecast_entries = [max(0, item.get('yhat',0)) for item in forecast_data_list[-forecast_days_val:]]
                    if future_forecast_entries:
                         avg_forecasted_daily_sales = sum(future_forecast_entries) / len(future_forecast_entries)


                # Stok tükenme süresi için geçmiş ortalama satışları kullanmak daha güvenli olabilir
                # Ya da tahmin edilen ortalama günlük satışı kullanabiliriz. Şimdilik geçmişi kullanalım.
                # Eğer geçmiş satış yoksa, tahmin edilen ortalamayı kullanalım.
                effective_daily_sales_for_stockout = avg_daily_sales_hist if avg_daily_sales_hist > 0 else avg_forecasted_daily_sales

                stock_out_days_val = float('inf')
                if effective_daily_sales_for_stockout > 0 and product_info_dict['mevcut_stok'] > 0:
                    stock_out_days_val = product_info_dict['mevcut_stok'] / effective_daily_sales_for_stockout

                product_info_dict.update({
                    'geçmiş_ortalama_günlük_satış': round(avg_daily_sales_hist, 2),
                    f'tahmini_gelecek_{forecast_days_val}_gün_ortalama_günlük_satış': round(avg_forecasted_daily_sales, 2),
                    'tahmini_tükenme_süresi_gün': round(stock_out_days_val, 1) if stock_out_days_val != float('inf') else 'Çok Yüksek veya Satış Yok'
                })

            # Daha detaylı prompt
            system_message_content = f"""Sen bir ayakkabı sektörü stok yönetimi ve üretim planlama uzmanısın. 
            Sana verilen ürünün mevcut stok bilgisi, geçmiş satışları ve gelecek satış tahminlerini dikkate alarak kapsamlı bir analiz yapacaksın.
            Analizinde şu noktalara odaklan:
            1. Stok Durumu: Mevcut stok kaç günlük satışı karşılar? Stok seviyesi kritik mi (örn: <{self.stock_thresholds['critical']} gün), uyarı mı (örn: <{self.stock_thresholds['warning']} gün), yoksa sağlıklı mı (örn: >{self.stock_thresholds['warning']} gün)?
            2. Satış Hızı Değerlendirmesi: Ürünün satış hızı nasıl (hızlı, normal, yavaş)? Bu hız stokları ne kadar sürede tüketebilir?
            3. Üretim Önerisi: Eğer stok kritik veya uyarı seviyesindeyse, üretim yapılmalı mı?
               - Hangi bedenlerden (eğer analiz beden bazlıysa) veya genel olarak ne kadar üretilmeli? (Örn: '30 günlük satışı karşılayacak kadar, yani X adet üretilmeli.')
               - Üretim için bir aciliyet durumu belirt (örn: 'Hemen üretime başlanmalı', '1 hafta içinde planlanmalı', 'Şu an acil değil').
            4. Ek Notlar: Varsa dikkat çekmek istediğin özel bir durum (örn: satışlarda ani artış/düşüş, stok eritme önerisi vb.).
            Cevabını net, anlaşılır ve maddeler halinde Türkçe olarak ver. Özellikle üretim miktarı ve aciliyet konusunda somut ol.
            """

            user_message_content = f"""Aşağıdaki ayakkabı ürünü için detaylı stok analizi ve üretim önerisi yapmanı rica ediyorum:
            {json.dumps(product_info_dict, indent=2, ensure_ascii=False)}
            Analizini yukarıdaki sistem mesajında belirtilen format ve detayda sun.
            """

            messages_payload = [
                {"role": "system", "content": system_message_content},
                {"role": "user", "content": user_message_content}
            ]

            response = openai.chat.completions.create(
                model="gpt-3.5-turbo", # veya gpt-4
                messages=messages_payload,
                temperature=0.3, # Daha tutarlı cevaplar için düşük temperature
                max_tokens=600 # Cevap uzunluğunu ayarla
            )

            ai_analysis_text = response.choices[0].message.content

            # AI cevabından temel bilgileri ayrıştırmaya çalışalım (opsiyonel, zor olabilir)
            stock_status_code = "normal" # healthy, warning, critical
            if "kritik" in ai_analysis_text.lower(): stock_status_code = "critical"
            elif "uyarı" in ai_analysis_text.lower() and "kritik" not in ai_analysis_text.lower() : stock_status_code = "warning" # Kritik değilse uyarı
            elif "sağlıklı" in ai_analysis_text.lower() : stock_status_code = "healthy"

            # Basitçe üretim önerisi var mı?
            action_needed_text = "AI analizi sonucunda özel bir aksiyon belirtilmedi."
            production_amount_val = 0
            if "üretim" in ai_analysis_text.lower() or "üretilmeli" in ai_analysis_text.lower():
                 action_needed_text = "AI, üretim veya stok takviyesi öneriyor. Detaylar analizde."
                 # Miktar çıkarmak için daha karmaşık regex gerekebilir, şimdilik genel bırakalım.
                 # matches = re.findall(r'(\d+)\s*adet üretilmeli', ai_analysis_text, re.IGNORECASE)
                 # if matches: production_amount_val = int(matches[0])

            analysis_result_dict = {
                'success': True,
                'raw_analysis': ai_analysis_text, # Ham AI cevabı
                'summary': { # Ayrıştırılmış özet (basit)
                    'stock_status_code': stock_status_code,
                    'stock_remaining_days_info': product_info_dict.get('tahmini_tükenme_süresi_gün', 'N/A'),
                    'action_suggestion': action_needed_text,
                    'suggested_production_quantity': production_amount_val # Eğer çıkarılabildiyse
                }
            }
            return analysis_result_dict

        except Exception as e:
            self.logger.error(f"AI stok analizi yapılırken hata: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': f'AI Stok analizi sırasında bir hata oluştu: {str(e)}'
            }

    def get_stock_health_report(self, top_n=10, days_forecast=30, include_variants=False):
        """
        Tüm ürünlerin (veya model/renk bazında) stok durumu raporu.
        Performans için top_n ile sınırlı.
        `include_variants`: True ise her bir product_main_id/color/size için ayrı analiz yapar.
                           False ise product_main_id/color bazında toplu stok ve satışları analiz eder.
        """
        try:
            products_to_analyze = []

            if include_variants:
                # En düşük stoklu N varyantı al (product_main_id, color, size bazında)
                # Bu sorgu çok sayıda ürün döndürebilir, dikkatli olunmalı.
                # Belki en çok satan veya en az stoğu olan N varyant seçilebilir.
                # Şimdilik quantity > 0 olan ve en düşük stoklu N varyantı alalım.
                # Order by quantity and then by some sales metric might be better.
                products_db_variants = Product.query.filter(
                    Product.archived.is_(False),
                    Product.hidden.is_(False), # gizli olmayanlar
                    Product.quantity.isnot(None),
                    Product.quantity > 0 # Stoğu olanlar
                ).order_by(Product.quantity.asc()).limit(top_n * 2).all() # Biraz daha fazla alıp sonra işleyebiliriz
                # products_to_analyze = products_db_variants[:top_n] # Direkt ilk N tanesini al

                # Daha mantıklı bir seçim: Önce son X günde satışı olan ürünleri, sonra stok miktarına göre sırala
                # Bu kısım karmaşıklaşabilir, şimdilik basit tutalım ve stok miktarına göre alalım.
                # Ancak idealde satış hızı da dikkate alınmalı.
                # Örneğin, son 30 günde en az 1 satışı olan ve stoğu en düşük N ürün.

                # Geçici olarak stok miktarına göre ilk N ürün
                products_to_analyze = products_db_variants[:top_n]


            else: # Model-Renk bazında toplu analiz
                # Model ve renk bazında toplam stoğu en düşük olan N grubu al
                grouped_products_db = db.session.query(
                    Product.product_main_id,
                    Product.color,
                    Product.title, # İlk ürünün başlığını alabiliriz
                    func.sum(Product.quantity).label('total_quantity'),
                    func.min(Product.images).label('image_url') # İlk ürünün resmini al
                ).filter(
                    Product.archived.is_(False),
                    Product.hidden.is_(False),
                    Product.quantity.isnot(None),
                    Product.quantity > 0
                ).group_by(
                    Product.product_main_id,
                    Product.color,
                    Product.title, # Gruplamaya title'ı da ekleyelim
                ).order_by(func.sum(Product.quantity).asc()).limit(top_n).all()

                for group_item in grouped_products_db:
                    # Bu product_data yapay bir obje, AI analizine uygun hale getirilecek
                    products_to_analyze.append({
                        'product_main_id': group_item.product_main_id,
                        'color': group_item.color,
                        'title': group_item.title if group_item.title else group_item.product_main_id + " " + group_item.color,
                        'quantity': float(group_item.total_quantity) if group_item.total_quantity else 0,
                        'size': None, # Model-Renk bazında olduğu için size None
                        'barcode': None, # Model-Renk bazında barkod yok
                        'is_group': True, # Bu bir grup analizi olduğunu belirtir
                        'image': group_item.image_url
                    })

            results_list = []
            for p_data in products_to_analyze:
                try:
                    current_product_main_id = p_data.product_main_id if hasattr(p_data, 'product_main_id') else p_data['product_main_id']
                    current_color = p_data.color if hasattr(p_data, 'color') else p_data['color']
                    current_size = p_data.size if hasattr(p_data, 'size') else p_data.get('size') # get ile None dönebilir

                    # Ürün bilgilerini Product objesinden veya dict'ten al
                    product_info_for_ai = {
                        'product_main_id': current_product_main_id,
                        'title': p_data.title if hasattr(p_data, 'title') else p_data.get('title'),
                        'color': current_color,
                        'size': current_size, # None olabilir
                        'quantity': float(p_data.quantity) if (hasattr(p_data, 'quantity') and p_data.quantity is not None) else float(p_data.get('quantity',0)),
                        'barcode': p_data.barcode if hasattr(p_data, 'barcode') else p_data.get('barcode') # None olabilir
                    }

                    # Satış tahmini (size None ise model-renk bazında tahmin)
                    sales_forecast_data = self.predict_future_sales(
                        product_main_id=current_product_main_id,
                        color=current_color,
                        size=current_size, # None ise, get_product_sales_data bunu dikkate almalı
                        forecast_days=days_forecast,
                        history_days=self.prediction_settings['history_days'] # init'teki history_days
                    )

                    # AI Analizi
                    ai_stock_analysis = self.analyze_stock_with_ai(product_info_for_ai, sales_forecast_data)

                    results_list.append({
                        'product_info': product_info_for_ai,
                        'sales_forecast_summary': {
                            'success': sales_forecast_data.get('success'),
                            'message': sales_forecast_data.get('message'),
                            'average_daily_sales': sales_forecast_data.get('average_daily_sales'),
                            'forecast_total': sales_forecast_data.get('forecast_total'),
                            'forecast_days': sales_forecast_data.get('forecast_days'),
                            'forecast_plot_json': sales_forecast_data.get('forecast_plot'), # JSON string
                            'components_plot_json': sales_forecast_data.get('components_plot') # JSON string
                        },
                        'ai_analysis': ai_stock_analysis
                    })

                except Exception as inner_e:
                    self.logger.error(f"Rapor için ürün işlenirken hata: {p_data} - Hata: {inner_e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
                    continue # Bir sonraki ürüne geç

            # Sonuçları AI analizindeki kritiklik durumuna göre sırala (varsa)
            def get_criticality_from_ai(item):
                status_code = item.get('ai_analysis', {}).get('summary', {}).get('stock_status_code', 'healthy')
                if status_code == 'critical': return 3
                if status_code == 'warning': return 2
                return 1 # healthy veya bilinmiyor

            results_list.sort(key=get_criticality_from_ai, reverse=True) # En kritik olanlar üste

            return results_list[:top_n] # Son olarak top_n kadarını döndür.

        except Exception as e:
            self.logger.error(f"Stok sağlık raporu oluşturulurken genel hata: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []


# Routes (API ve Arayüz)

@stock_intelligence_bp.route('/dashboard')
# @login_required # Giriş kontrolü aktif edilecekse yorumu kaldırın
def ai_stock_dashboard():
    """ AI destekli stok analiz paneli """
    # Bu sayfa için gerekli başlangıç verileri (örn: model listesi) buradan gönderilebilir
    # Veya sayfa yüklendikten sonra AJAX ile API'lerden çekilebilir.
    return render_template('gullushoes_stock_dashboard.html') # Template adını kontrol edin

@stock_intelligence_bp.route('/analysis-history')
# @login_required
def analysis_history():
    """ Geçmiş stok analizlerini görüntüleme sayfası """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 15 # Sayfa başına analiz sayısı
        analyses_pagination = StockAnalysisRecord.query.order_by(
            StockAnalysisRecord.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)

        analyses = analyses_pagination.items
        return render_template('stock_analysis_history.html', 
                               analyses=analyses, 
                               pagination=analyses_pagination)
    except Exception as e:
        logger.error(f"Analiz geçmişi sayfası yüklenirken hata: {e}")
        flash('Analiz geçmişi yüklenirken bir sorun oluştu.', 'danger')
        return redirect(url_for('stock_intelligence.ai_stock_dashboard')) # Ana panele yönlendir

@stock_intelligence_bp.route('/view-analysis/<int:analysis_id>')
# @login_required
def view_analysis(analysis_id):
    """ Belirli bir analizi görüntüle """
    try:
        analysis_record = StockAnalysisRecord.query.get_or_404(analysis_id)
        # analysis_results JSON olduğu için Python dict'ine çevrilmiş olmalı (SQLAlchemy JSON type ile)
        # Eğer string ise: analysis_data = json.loads(analysis_record.analysis_results)
        analysis_data = analysis_record.analysis_results 

        return render_template('view_stock_analysis.html', 
                               analysis=analysis_record, 
                               analysis_data=analysis_data,
                               created_at_formatted=analysis_record.created_at.strftime('%d.%m.%Y %H:%M'))
    except Exception as e:
        logger.error(f"Analiz detayı ({analysis_id}) görüntülenirken hata: {e}")
        flash('Analiz detayı görüntülenirken bir sorun oluştu.', 'danger')
        return redirect(url_for('stock_intelligence.analysis_history'))


@stock_intelligence_bp.route('/api/stock-health-report')
# @login_required
def get_stock_health_report_api():
    """ Stok sağlık raporu API'si """
    try:
        top_n_param = request.args.get('top_n', 10, type=int)
        days_forecast_param = request.args.get('days_forecast', 30, type=int)
        include_variants_param = request.args.get('include_variants', 'false').lower() == 'true'
        save_analysis_param = request.args.get('save_analysis', 'false').lower() == 'true'
        analysis_name_param = request.args.get('analysis_name', f'Stok Sağlık Raporu - {datetime.now().strftime("%Y-%m-%d %H:%M")}')

        # API üzerinden gelen top_n için bir üst sınır koymak iyi bir pratik
        if top_n_param > 20: top_n_param = 20 

        stock_intel_instance = StockIntelligence()
        report_data = stock_intel_instance.get_stock_health_report(
            top_n=top_n_param,
            days_forecast=days_forecast_param,
            include_variants=include_variants_param
        )

        response_payload = {'success': True, 'report': report_data}

        if save_analysis_param and report_data: # Sadece rapor verisi varsa kaydet
            try:
                analysis_params_dict = {
                    'top_n': top_n_param, 'days_forecast': days_forecast_param,
                    'include_variants': include_variants_param, 'report_generation_time': datetime.now().isoformat()
                }
                new_analysis_record = StockAnalysisRecord(
                    user_id=current_user.id if current_user and hasattr(current_user, 'id') and current_user.is_authenticated else None, # Kullanıcı girişi varsa
                    analysis_name=analysis_name_param,
                    analysis_parameters=analysis_params_dict,
                    analysis_results=report_data # Raporun kendisini JSON olarak kaydet
                )
                db.session.add(new_analysis_record)
                db.session.commit()
                response_payload['analysis_saved'] = True
                response_payload['analysis_id'] = new_analysis_record.id
                flash(f"'{analysis_name_param}' adlı analiz başarıyla kaydedildi.", "success")
            except Exception as save_err:
                db.session.rollback()
                logger.error(f"Analiz kaydedilirken veritabanı hatası: {save_err}")
                response_payload['analysis_saved'] = False
                response_payload['save_error'] = str(save_err)
                flash("Analiz veritabanına kaydedilirken bir hata oluştu.", "danger")

        return jsonify(response_payload)

    except Exception as e:
        logger.error(f"Stok raporu API hatası: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@stock_intelligence_bp.route('/api/model-variants-analysis')
# @login_required
def get_model_variants_analysis_api():
    """ Model koduna göre varyant analizleri API'si """
    try:
        product_main_id_param = request.args.get('product_main_id')
        days_param = request.args.get('days', 7, type=int)

        if not product_main_id_param:
            return jsonify({'success': False, 'error': 'product_main_id parametresi zorunludur.'}), 400

        stock_intel_instance = StockIntelligence()
        logger.info(f"Model varyant analizi başlatılıyor: Model ID: {product_main_id_param}, Gün: {days_param}")

        variants_data_list = stock_intel_instance.get_model_variants_data(
            product_main_id=product_main_id_param,
            days=days_param
        )

        if not variants_data_list and product_main_id_param: # Eğer boş döndüyse ve model ID varsa
             logger.warning(f"Model {product_main_id_param} için varyant verisi bulunamadı veya işlenemedi.")
             # Belki burada ürünün var olup olmadığını kontrol etmek iyi olabilir.
             # Product.query.filter_by(product_main_id=product_main_id_param).first()

        return jsonify({
            'success': True,
            'model_id_analyzed': product_main_id_param,
            'days_analyzed': days_param,
            'data': variants_data_list # Bu zaten [{model_data_with_colors_and_sizes}] formatında olmalı
        })

    except Exception as e:
        logger.error(f"Model varyant analizi API hatası: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@stock_intelligence_bp.route('/api/models-list')
def get_models_list_api():
    """ Sistemdeki tüm aktif model kodlarını ve başlıklarını listeleyen API """
    try:
        models_result = db.session.query(
            Product.product_main_id,
            Product.title,
            # Product.id yerine func.count(1) kullanarak her gruptaki satır (varyant) sayısını alıyoruz.
            func.count(1).label('variant_count')
        ).filter(
            Product.archived.is_(False),
            Product.hidden.is_(False)  # Bu alanın Product modelinde olduğundan emin olun
        ).group_by(
            Product.product_main_id,
            Product.title
        ).order_by(
            Product.product_main_id
        ).all()

        output_list = [{
            'product_main_id': model.product_main_id,
            'title': model.title if model.title else model.product_main_id,
            'variants_count': model.variant_count
        } for model in models_result]

        return jsonify(output_list)

    except Exception as e:
        logger.error(f"Model listesi API hatası: {e}")
        # traceback modülünün import edildiğinden emin olarak tam hatayı logla
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': f"Sunucu hatası: Model listesi alınamadı. Detaylar için logları kontrol edin."}), 500


@stock_intelligence_bp.route('/api/product-sales-prediction/<path:product_main_id_param>') # path ile / içeren ID'leri de alabilir
# @login_required
def get_product_sales_prediction_api(product_main_id_param):
    """ Belirli bir ürün (model/renk/beden veya model/renk) için satış tahmini API'si """
    try:
        color_param = request.args.get('color') # Opsiyonel
        size_param = request.args.get('size')   # Opsiyonel
        forecast_days_param = request.args.get('forecast_days', 30, type=int)
        history_days_param = request.args.get('history_days', 90, type=int)

        stock_intel_instance = StockIntelligence()
        forecast_result = stock_intel_instance.predict_future_sales(
            product_main_id=product_main_id_param,
            color=color_param,
            size=size_param,
            forecast_days=forecast_days_param,
            history_days=history_days_param
        )

        return jsonify(forecast_result) # success durumunu ve varsa error'u içerir

    except Exception as e:
        logger.error(f"Satış tahmini API hatası ({product_main_id_param}): {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@stock_intelligence_bp.route('/api/product-stock-analysis/<path:product_main_id_param>')
# @login_required
def get_product_stock_analysis_api(product_main_id_param):
    """ Belirli bir ürün (model/renk/beden veya model/renk) için AI stok analizi API'si """
    try:
        color_param = request.args.get('color') # Opsiyonel ama genellikle model/renk analizi için gerekli
        size_param = request.args.get('size')   # Opsiyonel, beden bazlı analiz için

        # AI analizi için ürün bilgilerini topla
        # Eğer size belirtilmemişse, model-renk bazında toplam stok alınır.
        # Eğer size belirtilmişse, o spesifik varyantın stoğu alınır.

        product_data_for_ai = {}

        if size_param and color_param: # Beden bazlı analiz
            product_instance = Product.query.filter(
                Product.product_main_id == product_main_id_param,
                Product.color == color_param,
                Product.size == size_param,
                Product.archived.is_(False)
            ).first()
            if not product_instance:
                return jsonify({'success': False, 'error': 'Belirtilen ürün varyantı bulunamadı.'}), 404
            product_data_for_ai = {
                'product_main_id': product_instance.product_main_id,
                'title': product_instance.title,
                'color': product_instance.color,
                'size': product_instance.size,
                'quantity': product_instance.quantity or 0,
                'barcode': product_instance.barcode
            }
        elif color_param: # Model-Renk bazlı analiz (tüm bedenlerin toplam stoğu)
            base_product_info = Product.query.filter( # Başlık gibi genel bilgileri almak için
                Product.product_main_id == product_main_id_param,
                Product.color == color_param,
                Product.archived.is_(False)
            ).first()
            if not base_product_info: # Bu model-renk kombinasyonunda hiç ürün yoksa
                 return jsonify({'success': False, 'error': f'{product_main_id_param} modeli için {color_param} renginde ürün bulunamadı.'}), 404

            total_quantity_for_color = db.session.query(func.sum(Product.quantity)).filter(
                Product.product_main_id == product_main_id_param,
                Product.color == color_param,
                Product.archived.is_(False)
            ).scalar() or 0
            product_data_for_ai = {
                'product_main_id': product_main_id_param,
                'title': base_product_info.title, # İlk bulunan varyantın başlığını kullan
                'color': color_param,
                'size': None, # Beden belirtilmedi
                'quantity': total_quantity_for_color,
            }
        else: # Sadece product_main_id ile genel model analizi desteklenmiyorsa hata ver
            return jsonify({'success': False, 'error': 'Analiz için en azından renk bilgisi (color) gereklidir.'}), 400

        stock_intel_instance = StockIntelligence()

        # Satış tahmini (size None ise model-renk bazında tahmin yapılır)
        sales_forecast_data = stock_intel_instance.predict_future_sales(
            product_main_id=product_main_id_param,
            color=color_param,
            size=size_param # None olabilir
        )

        # AI ile Stok Analizi
        ai_analysis_result = stock_intel_instance.analyze_stock_with_ai(product_data_for_ai, sales_forecast_data)

        return jsonify({
            'success': True,
            'product_details_analyzed': product_data_for_ai,
            'sales_forecast_data': sales_forecast_data, # Tahmin sonuçlarını da döndür
            'ai_stock_analysis': ai_analysis_result
        })

    except Exception as e:
        logger.error(f"AI Stok analizi API hatası ({product_main_id_param}): {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500