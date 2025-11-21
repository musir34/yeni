"""
Central blueprint registration for the Flask app.
"""
def register_blueprints(app):
    # Import blueprint objects
    from siparisler import siparisler_bp
    from product_service import product_service_bp
    from claims_service import claims_service_bp
    from order_service import order_service_bp
    from update_service import update_service_bp
    from archive import archive_bp
    from order_list_service import order_list_service_bp
    from login_logout import login_logout_bp
    from degisim import degisim_bp
    from home import home_bp
    from get_products import get_products_bp
    from all_orders_service import all_orders_service_bp
    from new_orders_service import new_orders_service_bp, qr_utils_bp
    from processed_orders_service import processed_orders_service_bp
    from iade_islemleri import iade_islemleri
    from siparis_fisi import siparis_fisi_bp
    from analysis import analysis_bp
    from stock_report import stock_report_bp
    from openai_service import openai_bp
    from user_logs import user_logs_bp
    from stock_management import stock_management_bp
    from commission_update_routes import commission_update_bp
    from product_label import product_label_bp
    from intelligent_stock_analyzer import blueprint as intelligent_stock_bp
    from image_manager import image_manager_bp
    from routes.common.health import health_bp
    from kasa import kasa_bp
    from raf_sistemi import raf_bp
    from rapor_gir import rapor_gir_bp
    from profit import profit_bp
    from canli_panel import canli_panel_bp
    from siparis_hazirla import siparis_hazirla_bp
    from gorev import gorev_bp, attach_jobs
    from uretim_oneri import uretim_oneri_bp
    from barcode_alias_routes import barcode_alias_bp  # 🔥 BARKOD ALIAS SİSTEMİ
    from woocommerce_site import woo_bp  # 🛒 WOOCOMMERCE SİPARİŞ SİSTEMİ



    # Register all blueprints
    for bp in [
        siparisler_bp,
        product_service_bp,
        claims_service_bp,
        order_service_bp,
        update_service_bp,
        archive_bp,
        order_list_service_bp,
        login_logout_bp,
        degisim_bp,
        home_bp,
        get_products_bp,
        all_orders_service_bp,
        new_orders_service_bp,
        qr_utils_bp,
        processed_orders_service_bp,
        iade_islemleri,
        siparis_fisi_bp,
        analysis_bp,
        stock_report_bp,
        openai_bp,
        user_logs_bp,
        stock_management_bp,
        commission_update_bp,
        product_label_bp,
        intelligent_stock_bp,
        image_manager_bp,
        health_bp,
        raf_bp,
        kasa_bp,
        rapor_gir_bp,
        profit_bp,
        canli_panel_bp,
        siparis_hazirla_bp,
        gorev_bp,
        uretim_oneri_bp,
        barcode_alias_bp,  # 🔥 BARKOD ALIAS SİSTEMİ
        woo_bp,  # 🛒 WOOCOMMERCE SİPARİŞ SİSTEMİ
    ]:
        app.register_blueprint(bp)