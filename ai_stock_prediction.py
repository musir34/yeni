# ai_stock_prediction.py
# =============================================================
#   AI Destekli Stok Tahmin ve Analiz Sistemi – Güllü Shoes
#   Tam Dosya – HATA DÜZELTİLMİŞ SÜRÜM – 20 Mayıs 2025
# =============================================================

import os
import json
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from openai import OpenAI
from prophet import Prophet
from sqlalchemy.sql import text
from sqlalchemy import func

from models import db, Product
from flask import Blueprint, render_template, jsonify, request

# -------------------------------------------------------------------------
# Logger
# -------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Blueprint
# -------------------------------------------------------------------------
ai_stock_prediction_bp = Blueprint("ai_stock_prediction", __name__)

# -------------------------------------------------------------------------
# Ana Sınıf
# -------------------------------------------------------------------------
class StockPredictor:
    def __init__(self):
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # -------------------------------------------------------------
    # 1. Geçmiş Satış Verisini Çek
    # -------------------------------------------------------------
    def get_product_sales_data(self,
                               product_main_id: str,
                               color: str | None = None,
                               size: str | None = None,
                               days: int = 90) -> pd.DataFrame:
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # Basitleştirilmiş parametreler
            base_params = {
                "start_date": start_date,
                "end_date": end_date,
                "model_id": product_main_id
            }
            
            # Sorgu filtreleri
            filters = ["product_main_id = :model_id"]

            if color:
                filters.append("product_color = :color")
                base_params["color"] = color
            if size:
                filters.append("product_size = :size")
                base_params["size"] = size

            where_clause = " AND ".join(filters)

            # Parametre formatı için :param_name şeklinde kullanım
            final_sql = text(f"""
                SELECT DATE(order_date) AS ds,
                       SUM(quantity)    AS y
                FROM (
                    SELECT * FROM orders_created
                    WHERE order_date BETWEEN :start_date AND :end_date
                    UNION ALL
                    SELECT * FROM orders_picking
                    WHERE order_date BETWEEN :start_date AND :end_date
                    UNION ALL
                    SELECT * FROM orders_shipped
                    WHERE order_date BETWEEN :start_date AND :end_date
                    UNION ALL
                    SELECT * FROM orders_delivered
                    WHERE order_date BETWEEN :start_date AND :end_date
                    UNION ALL
                    SELECT * FROM orders_cancelled
                    WHERE order_date BETWEEN :start_date AND :end_date
                ) AS u
                WHERE {where_clause}
                GROUP BY DATE(order_date)
                ORDER BY DATE(order_date)
            """)

            # Parametre göndermek için base_params'ı kullan
            rows = db.session.execute(final_sql, base_params).fetchall()

            if rows:
                df = pd.DataFrame(rows, columns=["ds", "y"])
            else:
                df = pd.DataFrame(columns=["ds", "y"])

            full_range = pd.date_range(start=start_date, end=end_date)
            df_full = pd.DataFrame({"ds": full_range}).merge(df, on="ds", how="left").fillna(0)
            return df_full

        except Exception as e:
            db.session.rollback()
            logger.error(f"Satış verisi alınırken hata: {e}", exc_info=True)
            return pd.DataFrame(columns=["ds", "y"])

    # -------------------------------------------------------------
    # 2. Prophet ile Gelecek Satış Tahmini
    # -------------------------------------------------------------
    def predict_future_sales(self,
                             product_main_id: str,
                             color: str | None = None,
                             size: str | None = None,
                             forecast_days: int = 30,
                             history_days: int = 90):
        try:
            sales_df = self.get_product_sales_data(product_main_id, color, size, history_days)
            if (sales_df["y"] > 0).sum() < 5:
                logger.warning(f"{product_main_id} için yeterli veri yok.")
                return None

            model = Prophet(seasonality_mode="multiplicative")
            model.fit(sales_df)

            future = model.make_future_dataframe(periods=forecast_days)
            forecast = model.predict(future)

            for col in ["yhat", "yhat_lower", "yhat_upper"]:
                forecast[col] = forecast[col].clip(lower=0)

            forecast["ds"] = forecast["ds"].dt.strftime("%Y-%m-%d")
            return forecast

        except Exception as e:
            logger.error(f"Satış tahmini yapılırken hata: {e}", exc_info=True)
            return None

    # -------------------------------------------------------------
    # 3. OpenAI ile Stok Analizi
    # -------------------------------------------------------------
    def analyze_stock_with_ai(self,
                              product_data: dict,
                              sales_forecast: pd.DataFrame | None = None):
        try:
            prompt_data = {
                "product": {
                    "barcode":        product_data.get("barcode"),
                    "title":          product_data.get("title"),
                    "model_id":       product_data.get("product_main_id"),
                    "color":          product_data.get("color"),
                    "size":           product_data.get("size"),
                    "current_stock":  product_data.get("quantity", 0),
                    "sale_price":     product_data.get("sale_price", 0),
                    "cost":           product_data.get("cost_try", 0)
                }
            }

            if sales_forecast is not None:
                p30 = sales_forecast.tail(30)["yhat"]
                prompt_data["sales_forecast"] = {
                    "next_7_days":  float(p30.tail(7).sum()),
                    "next_15_days": float(p30.tail(15).sum()),
                    "next_30_days": float(p30.sum())
                }

            system_prompt = (
                "Sen bir stok yönetim ve tahmin uzmanısın. "
                "Verilen JSON'daki veriye göre stok seviyesini değerlendir, "
                "kaç gün yeteceğini tahmin et ve sipariş önerisi sun. "
                "Yanıtı sadece JSON formatında döndür."
            )

            resp = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": json.dumps(prompt_data, ensure_ascii=False)}
                ],
                response_format={"type": "json_object"},
            )

            return json.loads(resp.choices[0].message.content)

        except Exception as e:
            logger.error(f"AI stok analizi sırasında hata: {e}", exc_info=True)
            return {"error": str(e)}

    # -------------------------------------------------------------
    # 4. Stok Sağlık Raporu
    # -------------------------------------------------------------
    def get_stock_health_report(self,
                                top_n: int = 20,
                                days_forecast: int = 30,
                                include_variants: bool = False):
        try:
            products = Product.query.filter_by(archived=False).all()
            report_items = []

            if include_variants:
                for p in products:
                    forecast = self.predict_future_sales(
                        p.product_main_id, p.color, p.size, days_forecast
                    )
                    pdata = {
                        "barcode": p.barcode,
                        "title": p.title,
                        "product_main_id": p.product_main_id,
                        "color": p.color,
                        "size": p.size,
                        "quantity": p.quantity,
                        "sale_price": p.sale_price,
                        "cost_try": p.cost_try
                    }
                    analysis = self.analyze_stock_with_ai(pdata, forecast)
                    report_items.append({"product": pdata, "analysis": analysis})
            else:
                groups = db.session.query(
                    Product.product_main_id,
                    Product.color,
                    func.sum(Product.quantity).label("total_qty")
                ).filter(
                    Product.archived == False
                ).group_by(
                    Product.product_main_id,
                    Product.color
                ).all()

                for model_id, color, total_qty in groups:
                    sample = Product.query.filter_by(product_main_id=model_id, color=color).first()
                    if not sample:
                        continue
                    forecast = self.predict_future_sales(
                        model_id, color, forecast_days=days_forecast
                    )
                    pdata = {
                        "barcode": f"{model_id}_{color}_group",
                        "title": sample.title,
                        "product_main_id": model_id,
                        "color": color,
                        "size": "Tüm Bedenler",
                        "quantity": total_qty,
                        "sale_price": sample.sale_price,
                        "cost_try": sample.cost_try
                    }
                    analysis = self.analyze_stock_with_ai(pdata, forecast)
                    report_items.append({"product": pdata, "analysis": analysis})

            def score(item):
                analysis = item.get("analysis", {})
                if "error" in analysis:
                    return -1e9
                sa = analysis.get("stock_analysis", {})
                status = sa.get("stock_status", "").lower()
                try:
                    days_left = float(sa.get("estimated_days_until_stockout", 999))
                except ValueError:
                    days_left = 999
                if "kritik" in status:
                    return 1000 - days_left
                if "düşük" in status:
                    return 500 - days_left
                return -days_left

            sorted_items = sorted(report_items, key=score, reverse=True)
            return sorted_items[:top_n] if top_n else sorted_items

        except Exception as e:
            logger.error(f"Stok sağlık raporu alınırken hata: {e}", exc_info=True)
            return []

# -------------------------------------------------------------------------
# Blueprint Rotaları
# -------------------------------------------------------------------------

@ai_stock_prediction_bp.route("/ai-stock-dashboard")
def ai_stock_dashboard():
    include_variants = request.args.get("include_variants", "false").lower() == "true"
    top_n  = int(request.args.get("top_n", 20))
    days   = int(request.args.get("days", 30))
    return render_template("ai_stock_dashboard.html",
                           include_variants=include_variants,
                           top_n=top_n,
                           days=days)

@ai_stock_prediction_bp.route("/api/stock-health-report")
def get_stock_health_report_api():
    include_variants = request.args.get("include_variants", "false").lower() == "true"
    top_n  = int(request.args.get("top_n", 20))
    days   = int(request.args.get("days", 30))

    predictor = StockPredictor()
    report = predictor.get_stock_health_report(top_n=top_n,
                                               days_forecast=days,
                                               include_variants=include_variants)
    return jsonify({"success": True, "count": len(report), "report": report})

@ai_stock_prediction_bp.route("/api/product-sales-prediction/<product_main_id>")
def get_product_sales_prediction_api(product_main_id):
    color = request.args.get("color")
    size  = request.args.get("size")
    forecast_days = int(request.args.get("forecast_days", 30))
    history_days  = int(request.args.get("history_days", 90))

    predictor = StockPredictor()
    forecast = predictor.predict_future_sales(product_main_id, color, size,
                                              forecast_days, history_days)
    if forecast is None:
        return jsonify({"success": False, "message": "Yeterli veri yok"})

    start_idx = len(forecast) - forecast_days
    to_json = lambda row: {
        "ds": row["ds"],
        "yhat":        float(row["yhat"]),
        "yhat_lower":  float(row["yhat_lower"]),
        "yhat_upper":  float(row["yhat_upper"])
    }
    forecast_data = [to_json(r) for _, r in forecast.iterrows()]

    return jsonify({
        "success": True,
        "forecast": forecast_data,
        "next_7_days":  float(forecast.iloc[start_idx:start_idx+7]["yhat"].sum()),
        "next_15_days": float(forecast.iloc[start_idx:start_idx+15]["yhat"].sum()),
        "next_30_days": float(forecast.iloc[start_idx:]["yhat"].sum())
    })

@ai_stock_prediction_bp.route("/api/product-stock-analysis/<product_main_id>")
def get_product_stock_analysis_api(product_main_id):
    color = request.args.get("color")
    size  = request.args.get("size")
    forecast_days = int(request.args.get("forecast_days", 30))

    q = Product.query.filter_by(product_main_id=product_main_id)
    if color: q = q.filter_by(color=color)
    if size:  q = q.filter_by(size=size)
    product = q.first()

    if not product:
        return jsonify({"success": False, "message": "Ürün bulunamadı"})

    pdata = {
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
    forecast  = predictor.predict_future_sales(product_main_id,
                                               color, size,
                                               forecast_days)
    analysis  = predictor.analyze_stock_with_ai(pdata, forecast)

    return jsonify({"success": True,
                    "product": pdata,
                    "analysis": analysis})
