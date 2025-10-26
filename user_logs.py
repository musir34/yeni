from flask import Blueprint, render_template, request, session
from flask_login import current_user
from models import db, UserLog, User
from login_logout import roles_required
from datetime import datetime, timedelta
import json
import urllib.parse
import logging

# Sabit sözlükler - Genişletilmiş versiyon
PAGE_NAME_MAP = {
    # Genel Sayfalar
    'home': 'Ana Sayfa',
    'home_bp.home': 'Ana Sayfa',
    'index': 'Ana Sayfa',
    'bilinmeyen': 'Bilinmeyen Sayfa',
    
    # Ürün İşlemleri
    'get_products.product_list': 'Ürün Listesi',
    'get_products.fetch_products': 'Ürün Çekme',
    'get_products.fetch_products_route': 'Ürün Çekme',
    'get_products.update_products': 'Ürün Güncelleme',
    'get_products.archive_product': 'Ürün Arşivleme',
    'get_products.restore_from_archive': 'Arşivden Geri Yükleme',
    'get_products.delete_product_variants': 'Ürün Varyantı Silme',
    'get_products.delete_product_api': 'Ürün Silme',
    'get_products.bulk_delete_products': 'Toplu Ürün Silme',
    'get_products.update_product_prices': 'Ürün Fiyat Güncelleme',
    'get_products.update_model_price': 'Model Fiyat Güncelleme',
    'get_products.update_product_cost': 'Ürün Maliyet Güncelleme',
    'get_products.delete_model_api': 'Model Silme',
    'get_products.search_products': 'Ürün Arama',
    'get_products.product_label': 'Ürün Etiketi',
    'product_list': 'Ürün Listesi',
    
    # Sipariş İşlemleri
    'order_list': 'Sipariş Listesi',
    'order_list_service.order_list_all': 'Tüm Siparişler',
    'order_list_service.order_list_new': 'Yeni Siparişler',
    'order_list_service.order_list_processed': 'İşlenen Siparişler',
    'order_list_service.order_list_shipped': 'Kargolanan Siparişler',
    'order_list_service.order_list_delivered': 'Teslim Edilen Siparişler',
    'order_list_service.order_list_cancelled': 'İptal Edilen Siparişler',
    'siparisler.yeni_siparis': 'Yeni Sipariş',
    'siparisler.siparis_detay': 'Sipariş Detay',
    'siparisler.siparis_guncelle': 'Sipariş Güncelleme',
    'siparisler.siparis_sil': 'Sipariş Silme',
    'siparis_hazirla_bp.index': 'Sipariş Hazırlama',
    'siparis_hazirla_bp.hazirla': 'Sipariş Hazırlama',
    
    # Sipariş Fişi
    'siparis_fisi.siparis_fisi_olustur': 'Sipariş Fişi Oluşturma',
    'siparis_fisi.siparis_fisi_sayfasi': 'Sipariş Fişi Sayfası',
    'siparis_fisi.siparis_fisi_listesi': 'Sipariş Fişi Listesi',
    'siparis_fisi_bp.siparis_fisi_urunler': 'Sipariş Fişi Ürünleri',
    
    # Kasa İşlemleri
    'kasa.kasa': 'Kasa Yönetimi',
    'kasa_bp.kasa': 'Kasa Yönetimi',
    'kasa.kasa_yeni': 'Yeni Kasa Kaydı',
    'kasa.kasa_duzenle': 'Kasa Kaydı Düzenleme',
    'kasa.kasa_sil': 'Kasa Kaydı Silme',
    'kasa.kasa_rapor': 'Kasa Raporu',
    'kasa_bp.kasa_rapor': 'Kasa Raporu',
    'kasa.kategoriler': 'Kasa Kategorileri',
    
    # Raf Sistemi
    'raf_bp.yonetim': 'Raf Yönetimi',
    'raf_bp.stok_guncelle': 'Raf Stok Güncelleme',
    'raf_bp.olustur': 'Raf Oluşturma',
    'raf_bp.sil': 'Raf Silme',
    'raf_bp.stok_sil': 'Raf Stok Silme',
    'raf_bp.stok_ekle': 'Raf Stok Ekleme',
    'raf_bp.stoklar': 'Raf Stokları',
    'raf_bp.stok_form': 'Raf Stok Formu',
    'raf_bp.form': 'Raf Formu',
    
    # Üretim Önerisi
    'uretim_oneri_bp.uretim_oneri': 'Üretim Önerisi',
    'uretim_oneri_bp.uretim_oneri_haftalik': 'Haftalık Üretim Önerisi',
    'uretim_oneri_bp.api_uretim_oneri_plan': 'Üretim Planı Oluşturma',
    
    # Kullanıcı İşlemleri
    'login_logout.login': 'Giriş',
    'login_logout.logout': 'Çıkış',
    'login_logout.register': 'Kayıt',
    'login_logout.approve_users': 'Kullanıcı Onaylama',
    'login_logout.delete_user': 'Kullanıcı Silme',
    'login_logout.setup_totp': '2FA Kurulumu',
    'login_logout.verify_totp': '2FA Doğrulama',
    'login': 'Giriş',
    'register': 'Kayıt',
    
    # Stok İşlemleri
    'stock_report': 'Stok Raporu',
    'stock_report_bp.stock_report': 'Stok Raporu',
    'stock_management.stock_addition': 'Stok Ekleme',
    'stock_management_bp.stock_addition': 'Stok Ekleme',
    
    # Kar/Zarar
    'profit.index': 'Kar/Zarar Analizi',
    'profit_bp.index': 'Kar/Zarar Analizi',
    'profit.save_costs': 'Maliyet Kaydetme',
    
    # Analiz ve Raporlar
    'analysis': 'Analiz Sayfası',
    'exchange_form': 'Değişim Formu',
    'degisim.exchange_form': 'Değişim Formu',
    
    # Diğer
    'user_logs': 'Kullanıcı Logları',
    'user_logs.view_logs': 'Kullanıcı Logları',
    'archive': 'Arşiv',
    'archive_bp.archive': 'Arşiv',
    'order_aggregation_bp.toplam_siparisler': 'Toplam Siparişler',
    'intelligent_stock_analyzer_bp.index': 'Akıllı Stok Analizi',
    'image_manager_bp.image_manager': 'Görsel Yönetimi',
    'openai_bp.ai_analiz': 'AI Analiz',
    'rapor_gir_bp.raporlama': 'Raporlama',
}

ACTION_TYPE_MAP = {
    'PAGE_VIEW': 'Sayfa Görüntüleme',
    'LOGIN': 'Giriş Yapıldı',
    'LOGOUT': 'Çıkış Yapıldı',
    'CREATE': 'Oluşturma',
    'UPDATE': 'Güncelleme',
    'DELETE': 'Silme',
    'ARCHIVE': 'Arşivleme',
    'RESTORE': 'Geri Yükleme',
    'PRINT': 'Yazdırma',
    'EXPORT': 'Dışa Aktarma',
    'FETCH': 'Veri Çekme',
    'BULK_DELETE': 'Toplu Silme',
    'PRICE_UPDATE': 'Fiyat Güncelleme',
    'COST_UPDATE': 'Maliyet Güncelleme',
    'STOCK_UPDATE': 'Stok Güncelleme',
    'DELETE_PRODUCTS': 'Ürün Silme',
    'BULK_DELETE_PRODUCTS': 'Toplu Ürün Silme',
    'VIEW': 'Görüntüleme',
    'SEARCH': 'Arama',
}

user_logs_bp = Blueprint('user_logs', __name__)

def translate_page_name(page: str) -> str:
    return PAGE_NAME_MAP.get(page, page or 'Ana Sayfa')

def translate_action_type(action: str) -> str:
    return ACTION_TYPE_MAP.get(action, action)

def get_browser_info() -> str:
    return request.user_agent.browser or "Bilinmiyor"

def get_platform_info() -> str:
    return request.user_agent.platform or "Bilinmiyor"

def extract_page_from_referrer(referrer: str) -> str:
    if referrer:
        parsed_url = urllib.parse.urlparse(referrer)
        page = parsed_url.path.split('/')[-1]
        return PAGE_NAME_MAP.get(page, 'Doğrudan Giriş') if page else 'Doğrudan Giriş'
    return 'Doğrudan Giriş'

def log_user_action(action: str, details = None, force_log: bool = False, log_level: str = "INFO") -> None:
    """
    Geliştirilmiş kullanıcı işlem loglama fonksiyonu
    
    Args:
        action: İşlem tipi (örn: 'UPDATE', 'DELETE', 'CREATE') veya 'UPDATE: product_list' formatında
        details: İşlem detayları (dict veya string)
        force_log: Oturum açmamış kullanıcılar için zorunlu loglama
        log_level: Log seviyesi
        
    Örnekler:
        log_user_action('UPDATE', {'sayfa': 'Ürün Listesi', 'model': 'ABC123', 'değişiklik': 'Fiyat güncellendi'})
        log_user_action('DELETE', {'sayfa': 'Ürün Listesi', 'silinen_ürün': 'XYZ789'})
    """
    if current_user.is_authenticated or force_log:
        user_id = current_user.id if current_user.is_authenticated else session.get('user_id')
        user_role = getattr(current_user, 'role', session.get('role', 'anonymous'))
        username = getattr(current_user, 'username', 'Bilinmeyen')

        # action içinden işlem tipini ve sayfayı ayrıştır
        action_parts = action.split(': ', 1)
        action_type_raw = action_parts[0].strip()
        action_page_raw = action_parts[1].strip() if len(action_parts) > 1 else ''

        # Türkçe çeviriler
        translated_action = translate_action_type(action_type_raw)
        translated_page = translate_page_name(action_page_raw)

        # Rol çevirisi
        role_display = {
            'admin': 'Yönetici',
            'worker': 'Personel',
            'manager': 'Yönetici Yardımcısı'
        }.get(user_role, 'Ziyaretçi')

        # Detay sözlüğünü genişlet
        extended_details = {
            'Kullanıcı': username,
            'İşlem': translated_action,
            'Kullanıcı Rolü': role_display,
            'Tarayıcı': get_browser_info(),
            'İşletim Sistemi': get_platform_info(),
            'Zaman': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        # Sayfa bilgisi varsa ekle
        if translated_page:
            extended_details['Sayfa'] = translated_page
            
        # Gelinen sayfa bilgisi
        if request.referrer:
            extended_details['Gelinen Sayfa'] = extract_page_from_referrer(request.referrer)

        # Kullanıcının gönderdiği detayları ekle
        if details:
            if isinstance(details, dict):
                # Anahtar adlarını Türkçeleştir ve ekle
                for k, v in details.items():
                    # Anahtar isimlerini daha okunabilir hale getir
                    formatted_key = k.replace('_', ' ').title()
                    extended_details[formatted_key] = v
            else:
                extended_details['Detay'] = str(details)

        try:
            new_log = UserLog(
                user_id=user_id,
                action=action,
                details=json.dumps(extended_details, ensure_ascii=False),
                ip_address=request.remote_addr,
                page_url=request.url
            )
            db.session.add(new_log)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logging.error(f"Log kaydedilemedi: {e}")

@user_logs_bp.route('/api/log-user-activity', methods=['POST'])
def log_user_activity_api():
    """
    JavaScript'ten gelen kullanıcı hareketlerini toplu olarak kaydetmek için API endpoint'i
    """
    try:
        data = request.get_json()
        if not data:
            return {'success': False, 'message': 'Veri bulunamadı'}, 400
        
        logs = data.get('logs', [])
        if not logs:
            return {'success': False, 'message': 'Log verisi bulunamadı'}, 400
        
        user_id = current_user.id if current_user.is_authenticated else None
        user_role = getattr(current_user, 'role', 'anonymous')
        
        saved_count = 0
        for log_entry in logs:
            try:
                action = log_entry.get('action', 'UNKNOWN')
                details = log_entry.get('details', {})
                
                # Detayları genişlet
                extended_details = {
                    'İşlem': translate_action_type(action),
                    'Kullanıcı Rolü': (
                        'Yönetici' if user_role == 'admin' else
                        'Personel' if user_role == 'worker' else
                        'Yönetici Yardımcısı' if user_role == 'manager' else
                        'Ziyaretçi'
                    ),
                    'Tarayıcı': get_browser_info(),
                    'İşletim Sistemi': get_platform_info(),
                }
                
                # JavaScript'ten gelen detayları ekle
                extended_details.update(details)
                
                new_log = UserLog(
                    user_id=user_id,
                    action=action,
                    details=json.dumps(extended_details, ensure_ascii=False),
                    ip_address=request.remote_addr,
                    page_url=details.get('page_url', request.referrer)
                )
                db.session.add(new_log)
                saved_count += 1
                
            except Exception as e:
                logging.error(f"Tekil log kaydedilemedi: {e}")
                continue
        
        db.session.commit()
        return {'success': True, 'message': f'{saved_count} hareket kaydedildi', 'saved_count': saved_count}
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Toplu log kaydetme hatası: {e}")
        return {'success': False, 'message': 'Sunucu hatası'}, 500

@user_logs_bp.route('/user-logs')
@roles_required('admin', 'manager')
def view_logs():
    page = request.args.get('page', 1, type=int)
    per_page = 50

    user_id = request.args.get('user_id', type=int)
    action_filter = request.args.get('action', type=str)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    keyword = request.args.get('keyword', type=str)

    query = UserLog.query.join(User)

    if user_id:
        query = query.filter(UserLog.user_id == user_id)
    if action_filter:
        query = query.filter(UserLog.action.ilike(f'%{action_filter}%'))
    if keyword:
        query = query.filter(UserLog.details.ilike(f'%{keyword}%'))

    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(UserLog.timestamp >= start_date)
    except ValueError as ve:
        logging.error(f"Başlangıç tarihi hatalı: {ve}")

    try:
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(UserLog.timestamp <= end_date)
    except ValueError as ve:
        logging.error(f"Bitiş tarihi hatalı: {ve}")

    logs = query.order_by(UserLog.timestamp.desc()).paginate(page=page, per_page=per_page)
    for log in logs.items:
        try:
            log.details_dict = json.loads(log.details) if log.details else {}
        except Exception as e:
            log.details_dict = {}
            logging.error(f"Log detayları yüklenemedi: {e}")

    users = User.query.all()
    return render_template('user_logs.html', logs=logs, users=users)


import io
import pandas as pd
from flask import send_file

@user_logs_bp.route('/user-logs/export', methods=['GET'])
@roles_required('admin', 'manager')
def export_logs():
    """
    Kullanıcı loglarını filtreye göre Excel'e aktaran endpoint.
    """
    user_id = request.args.get('user_id', type=int)
    action_filter = request.args.get('action')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    keyword = request.args.get('keyword', type=str)

    query = UserLog.query.join(User)

    # Filtreler
    if user_id:
        query = query.filter(UserLog.user_id == user_id)
    if action_filter:
        query = query.filter(UserLog.action.ilike(f'%{action_filter}%'))
    if keyword:
        query = query.filter(UserLog.details.ilike(f'%{keyword}%'))

    # Tarih
    from datetime import datetime, timedelta
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(UserLog.timestamp >= start_date)
    except ValueError:
        pass

    try:
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(UserLog.timestamp <= end_date)
    except ValueError:
        pass

    # Veriyi çek
    logs = query.order_by(UserLog.timestamp.desc()).all()

    # DataFrame'e çevir
    data = []
    for log in logs:
        try:
            details_dict = json.loads(log.details) if log.details else {}
        except:
            details_dict = {}

        data.append({
            "Tarih": log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            "Kullanıcı": log.user.username,
            "IP": log.ip_address,
            "Ham Aksiyon": log.action,
            "Açıklama": details_dict.get('İşlem', ''),
            "Sayfa": details_dict.get('Sayfa', ''),
            **{k: str(v) for k, v in details_dict.items()
               if k not in ['İşlem','Sayfa']}
        })

    # Excel oluştur
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df = pd.DataFrame(data)
        df.to_excel(writer, index=False, sheet_name='Loglar')

    output.seek(0)
    return send_file(output, download_name='kullanici_loglari.xlsx', as_attachment=True)
