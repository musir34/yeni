from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, jsonify
from models import db, Product
import aiohttp
import asyncio
import base64
import logging
import json
from datetime import datetime, timedelta
from sqlalchemy import text
import time
from functools import wraps
from flask_login import login_required, current_user

# Trendyol API bilgilerini içe aktar
try:
    from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL
    logger = logging.getLogger(__name__)
    logger.info("Trendyol API bilgileri başarıyla yüklendi.")
except ImportError:
    logger = logging.getLogger(__name__)
    logger.error("trendyol_api.py dosyası bulunamadı veya Trendyol API bilgileri eksik.")
    # Eksik bilgileri tutacak placeholder değişkenler tanımla
    API_KEY = None
    API_SECRET = None
    SUPPLIER_ID = None
    BASE_URL = "https://api.trendyol.com/sapigw/"

# Blueprint oluştur
customer_questions_bp = Blueprint('customer_questions', __name__, url_prefix='/customer_questions')

# Müşteri sorusunu saklamak için veritabanı modeli
# models.py dosyasına eklenmeli
"""
class CustomerQuestion(db.Model):
    __tablename__ = 'customer_questions'
    
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, unique=True, nullable=False)
    customer_id = db.Column(db.Integer)
    creation_date = db.Column(db.DateTime)
    product_name = db.Column(db.String(255))
    product_main_id = db.Column(db.String(50))
    image_url = db.Column(db.String(255))
    text = db.Column(db.Text)
    status = db.Column(db.String(50))
    user_name = db.Column(db.String(100))
    web_url = db.Column(db.String(255))
    answer_text = db.Column(db.Text, nullable=True)
    answer_date = db.Column(db.DateTime, nullable=True)
    rejected_reason = db.Column(db.Text, nullable=True)
    rejected_date = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f'<CustomerQuestion {self.question_id}>'
"""

@customer_questions_bp.route('/')
@login_required
def questions_list():
    """
    Tüm müşteri sorularını listeler
    """
    from models import CustomerQuestion
    
    # Filtre parametrelerini al
    status = request.args.get('status', 'all')
    
    # Varsayılan olarak tüm soruları getir
    query = CustomerQuestion.query
    
    # Duruma göre filtrele
    if status != 'all':
        query = query.filter(CustomerQuestion.status == status)
    
    # Soruları en yeniden eskiye doğru sırala
    questions = query.order_by(CustomerQuestion.creation_date.desc()).all()
    
    return render_template('customer_questions/list.html', questions=questions, current_status=status)


@customer_questions_bp.route('/fetch', methods=['POST'])
@login_required
def fetch_questions_route():
    """
    Trendyol API'den müşteri sorularını çekme işlemini başlatır
    """
    # Trendyol API bilgilerini kontrol et
    if not API_KEY or not API_SECRET or not SUPPLIER_ID:
        flash("Trendyol API bilgileri eksik. Müşteri soruları çekilemez.", "danger")
        return redirect(url_for('customer_questions.questions_list'))
    
    try:
        # Asenkron fonksiyonu çalıştırmak için asyncio loop oluştur
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            questions_data = loop.run_until_complete(fetch_customer_questions_async())
        finally:
            loop.close()
        
        if questions_data:
            # Çekilen soruları veritabanına kaydet
            saved_count = process_questions_data(questions_data)
            flash(f"{saved_count} yeni müşteri sorusu başarıyla kaydedildi.", "success")
        else:
            flash("Müşteri soruları çekilemedi. Lütfen logları kontrol edin.", "warning")
    
    except Exception as e:
        logger.error(f"Müşteri sorularını çekerken hata oluştu: {e}", exc_info=True)
        flash(f"Müşteri sorularını çekerken hata oluştu: {str(e)}", "danger")
    
    return redirect(url_for('customer_questions.questions_list'))


async def fetch_customer_questions_async():
    """
    Trendyol API'den tüm müşteri sorularını asenkron olarak çeker
    """
    logger.info("Trendyol'dan müşteri sorularını çekme işlemi başladı")
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        
        # Trendyol API endpointi
        url = f"{BASE_URL}integration/qna/sellers/{SUPPLIER_ID}/questions/filter"
        
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        # Son 14 günlük soruları çekelim (maksimum 2 hafta)
        end_date = int(datetime.now().timestamp() * 1000)  # Şu anki zaman (milisaniye)
        start_date = int((datetime.now() - timedelta(days=14)).timestamp() * 1000)  # 14 gün öncesi
        
        # İlk sayfa parametreleri
        params = {
            "startDate": start_date,
            "endDate": end_date,
            "page": 0,
            "size": 50,  # Bir sayfada maksimum 50 soru
            "orderByField": "CreatedDate",
            "orderByDirection": "DESC"
        }
        
        all_questions = []
        
        async with aiohttp.ClientSession() as session:
            # İlk sayfa isteğini yap ve toplam sayfa sayısını al
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"API Hatası: {response.status} - {error_text}")
                    return None
                
                response_data = await response.json()
                
                total_pages = response_data.get('totalPages', 1)
                total_elements = response_data.get('totalElements', 0)
                
                logger.info(f"Toplam soru sayısı: {total_elements}, Toplam sayfa: {total_pages}")
                
                # İlk sayfadaki soruları ekle
                if 'content' in response_data and response_data['content']:
                    all_questions.extend(response_data['content'])
                
                # Eğer birden fazla sayfa varsa, diğer sayfaları paralel olarak çek
                if total_pages > 1:
                    tasks = []
                    semaphore = asyncio.Semaphore(5)  # Aynı anda en fazla 5 istek
                    
                    for page in range(1, total_pages):
                        page_params = params.copy()
                        page_params['page'] = page
                        tasks.append(fetch_questions_page(session, url, headers, page_params, semaphore))
                    
                    pages_results = await asyncio.gather(*tasks)
                    
                    # Tüm sayfalardan gelen soruları birleştir
                    for page_questions in pages_results:
                        if page_questions:
                            all_questions.extend(page_questions)
        
        logger.info(f"Toplam {len(all_questions)} soru başarıyla çekildi")
        return all_questions
    
    except Exception as e:
        logger.error(f"Müşteri sorularını çekerken hata: {e}", exc_info=True)
        return None


async def fetch_questions_page(session, url, headers, params, semaphore):
    """
    Belirli bir sayfadaki müşteri sorularını çeker
    """
    try:
        async with semaphore:
            # Rate limiting için biraz bekle
            await asyncio.sleep(0.5)
            
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Sayfa {params['page']} için API Hatası: {response.status} - {error_text}")
                    return None
                
                response_data = await response.json()
                
                if 'content' in response_data and response_data['content']:
                    logger.debug(f"Sayfa {params['page']}: {len(response_data['content'])} soru çekildi")
                    return response_data['content']
                return []
    
    except Exception as e:
        logger.error(f"Sayfa {params['page']} çekilirken hata: {e}")
        return None


def process_questions_data(questions_data):
    """
    Trendyol'dan çekilen soruları veritabanına kaydeder
    """
    from models import CustomerQuestion
    
    if not questions_data:
        return 0
    
    new_count = 0
    updated_count = 0
    
    try:
        for question in questions_data:
            question_id = question.get('id')
            
            # Soru zaten veritabanında var mı kontrol et
            existing_question = CustomerQuestion.query.filter_by(question_id=question_id).first()
            
            if existing_question:
                # Soru zaten varsa, durumunu güncelle
                existing_question.status = question.get('status')
                
                # Eğer bir cevap verilmişse, cevabı da güncelle
                if 'answer' in question and question['answer']:
                    existing_question.answer_text = question['answer'].get('text')
                    if question['answer'].get('creationDate'):
                        existing_question.answer_date = datetime.fromtimestamp(question['answer'].get('creationDate') / 1000)
                
                # Reddedilmiş cevap varsa, güncelleyelim
                if 'rejectedAnswer' in question and question['rejectedAnswer']:
                    existing_question.rejected_reason = question['rejectedAnswer'].get('reason')
                    if question['rejectedAnswer'].get('creationDate'):
                        existing_question.rejected_date = datetime.fromtimestamp(question['rejectedAnswer'].get('creationDate') / 1000)
                
                updated_count += 1
            else:
                # Yeni soru oluştur
                new_question = CustomerQuestion()
                new_question.question_id = question_id
                new_question.customer_id = question.get('customerId')
                new_question.creation_date = datetime.fromtimestamp(question.get('creationDate', 0) / 1000) if question.get('creationDate') else None
                new_question.product_name = question.get('productName')
                new_question.product_main_id = question.get('productMainId')
                new_question.image_url = question.get('imageUrl')
                new_question.text = question.get('text', '')
                new_question.status = question.get('status', 'UNKNOWN')
                new_question.user_name = question.get('userName')
                new_question.web_url = question.get('webUrl')
                
                # Eğer bir cevap verilmişse, cevabı da ekle
                if 'answer' in question and question['answer']:
                    new_question.answer_text = question['answer'].get('text')
                    if question['answer'].get('creationDate'):
                        new_question.answer_date = datetime.fromtimestamp(question['answer'].get('creationDate') / 1000)
                
                # Reddedilmiş cevap varsa ekleyelim
                if 'rejectedAnswer' in question and question['rejectedAnswer']:
                    new_question.rejected_reason = question['rejectedAnswer'].get('reason')
                    if question['rejectedAnswer'].get('creationDate'):
                        new_question.rejected_date = datetime.fromtimestamp(question['rejectedAnswer'].get('creationDate') / 1000)
                
                db.session.add(new_question)
                new_count += 1
        
        db.session.commit()
        logger.info(f"{new_count} yeni soru eklendi, {updated_count} soru güncellendi")
        return new_count
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Soruları kaydederken hata oluştu: {e}", exc_info=True)
        raise


@customer_questions_bp.route('/answer/<int:question_id>', methods=['GET', 'POST'])
@login_required
def answer_question(question_id):
    """
    Müşteri sorusunu cevaplama sayfası
    """
    from models import CustomerQuestion
    
    question = CustomerQuestion.query.filter_by(question_id=question_id).first_or_404()
    
    if request.method == 'POST':
        answer_text = request.form.get('answer')
        
        if not answer_text or len(answer_text.strip()) < 3:
            flash("Geçerli bir cevap yazmalısınız.", "warning")
            return render_template('customer_questions/answer.html', question=question)
        
        try:
            # Cevabı Trendyol'a gönder
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                success = loop.run_until_complete(send_answer_to_trendyol(question_id, answer_text))
            finally:
                loop.close()
            
            if success:
                # Başarılı olursa veritabanını güncelle
                question.answer_text = answer_text
                question.answer_date = datetime.now()
                question.status = "WAITING_FOR_APPROVE"  # Onay bekliyor durumuna güncelle
                db.session.commit()
                
                flash("Cevabınız başarıyla gönderildi. Trendyol onayından sonra müşteriye iletilecektir.", "success")
                return redirect(url_for('customer_questions.questions_list'))
            else:
                flash("Cevap gönderilirken bir hata oluştu. Lütfen daha sonra tekrar deneyin.", "danger")
        
        except Exception as e:
            logger.error(f"Cevap gönderilirken hata: {e}", exc_info=True)
            flash(f"Cevap gönderilirken bir hata oluştu: {str(e)}", "danger")
    
    return render_template('customer_questions/answer.html', question=question)


async def send_answer_to_trendyol(question_id, answer_text):
    """
    Müşteri sorusuna verilen cevabı Trendyol API'ye gönderir
    """
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        
        # Trendyol API endpointi
        url = f"{BASE_URL}integration/qna/sellers/{SUPPLIER_ID}/questions/{question_id}/answers"
        
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        # Gönderilecek cevap verisi
        data = {
            "text": answer_text,
            "hasPrivateInfo": False  # Özel bilgi içermiyorsa false, içeriyorsa true
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    logger.info(f"Soru #{question_id} için cevap başarıyla gönderildi")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Cevap gönderilirken API Hatası: {response.status} - {error_text}")
                    return False
    
    except Exception as e:
        logger.error(f"Cevap gönderilirken hata: {e}", exc_info=True)
        return False


@customer_questions_bp.route('/get_question/<int:question_id>')
@login_required
def get_question_by_id(question_id):
    """
    Trendyol API'den belirli bir soruyu ID'ye göre çeker ve detaylarını gösterir
    """
    try:
        # Asenkron fonksiyonu çalıştırmak için asyncio loop oluştur
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            question_data = loop.run_until_complete(fetch_question_by_id_async(question_id))
        finally:
            loop.close()
        
        if question_data:
            # Sadece göstermek için, kaydetme
            return render_template('customer_questions/detail.html', question=question_data)
        else:
            flash("Soru bulunamadı veya çekilemedi.", "warning")
    
    except Exception as e:
        logger.error(f"Soru detaylarını çekerken hata: {e}", exc_info=True)
        flash(f"Soru detaylarını çekerken hata oluştu: {str(e)}", "danger")
    
    return redirect(url_for('customer_questions.questions_list'))


async def fetch_question_by_id_async(question_id):
    """
    Trendyol API'den belirli bir soruyu ID'ye göre çeker
    """
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        
        # Trendyol API endpointi
        url = f"{BASE_URL}integration/qna/sellers/{SUPPLIER_ID}/questions/{question_id}"
        
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"API Hatası: {response.status} - {error_text}")
                    return None
                
                question_data = await response.json()
                logger.info(f"Soru #{question_id} başarıyla çekildi")
                return question_data
    
    except Exception as e:
        logger.error(f"Soru çekilirken hata: {e}", exc_info=True)
        return None


def format_date(timestamp):
    """
    Unix timestamp'i (milisaniye) okunabilir tarih formatına dönüştürür
    """
    if not timestamp:
        return ""
    
    try:
        dt = datetime.fromtimestamp(timestamp / 1000)
        return dt.strftime("%d.%m.%Y %H:%M")
    except:
        return ""