from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required
# ProductQuestion modelini models.py dosyasından import et
from models import db, Product, ProductQuestion # ProductQuestion buraya eklendi
from sqlalchemy import desc
import logging
import asyncio
import aiohttp
import base64
import json
from datetime import datetime, timedelta
import os

# Trendyol API bilgilerini al
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL

# Logger ayarları
logger = logging.getLogger(__name__)

# Blueprint oluştur
product_questions_bp = Blueprint('product_questions', __name__)

# ARTIK ProductQuestion MODEL TANIMI BURADA DEĞİL, models.py İÇİNDE.
# Aşağıdaki ProductQuestion sınıf tanımı kaldırıldı.

# Trendyol API'den ürün sorularını asenkron olarak çek
async def fetch_trendyol_questions_async():
    """
    Trendyol API'den tüm ürün sorularını asenkron olarak çeker
    """
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/questions"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }

        # Parametreler (son 90 günlük soruları çek)
        ninety_days_ago = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")
        today = datetime.utcnow().strftime("%Y-%m-%d")

        params = {
            "startDate": ninety_days_ago,
            "endDate": today,
            "status": "WAITING_FOR_ANSWER",  # Cevaplanmamış sorular
            "page": 0,
            "size": 100,  # Sayfa başına 100 soru
        }

        logger.info(f"Trendyol ürün soruları API çağrısı başlatılıyor: {url}")

        async with aiohttp.ClientSession() as session:
            # İlk sayfayı çek ve toplam sayfa sayısını öğren
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Trendyol API hatası: {response.status} - {error_text}")
                    return []

                data = await response.json()
                total_pages = data.get('totalPages', 1)
                total_elements = data.get('totalElements', 0)

                if total_elements == 0:
                    logger.info("Cevaplanmamış ürün sorusu bulunamadı.")
                    return []

                logger.info(f"Toplam {total_elements} soru, {total_pages} sayfa bulundu.")

                # Tüm sayfaları paralel olarak çek
                all_questions = []
                semaphore = asyncio.Semaphore(5)  # Aynı anda 5 istek sınırı

                # İlk sayfanın sonuçlarını ekle
                all_questions.extend(data.get('content', []))

                # Diğer sayfalar için görevler oluştur (1. sayfadan başla, 0. sayfayı zaten çektik)
                tasks = []
                for page in range(1, total_pages):
                    page_params = params.copy()
                    page_params['page'] = page
                    tasks.append(fetch_questions_page(session, url, headers, page_params, semaphore))

                # Tüm görevleri çalıştır
                page_results = await asyncio.gather(*tasks)

                # Sonuçları birleştir
                for result in page_results:
                    if result:
                        all_questions.extend(result)

                logger.info(f"Toplam {len(all_questions)} soru başarıyla çekildi.")
                return all_questions

    except Exception as e:
        logger.error(f"Ürün sorularını çekerken hata oluştu: {e}", exc_info=True)
        return []


async def fetch_questions_page(session, url, headers, params, semaphore):
    """
    Belirli bir sayfadaki soruları çeken yardımcı fonksiyon
    """
    try:
        async with semaphore:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Sayfa {params['page']} çekilirken hata: {response.status} - {error_text}")
                    return []

                data = await response.json()
                questions = data.get('content', [])
                logger.debug(f"Sayfa {params['page']}: {len(questions)} soru çekildi.")
                return questions

    except Exception as e:
        logger.error(f"Sayfa {params['page']} çekilirken hata: {e}", exc_info=True)
        return []


# Cevaplanmış sorular için de ayrı bir fonksiyon
async def fetch_answered_questions_async():
    """
    Trendyol API'den cevaplanmış ürün sorularını çeker
    """
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/questions"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }

        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        today = datetime.utcnow().strftime("%Y-%m-%d")

        params = {
            "startDate": thirty_days_ago,
            "endDate": today,
            "status": "ANSWERED", 
            "page": 0,
            "size": 100,
        }

        logger.info(f"Trendyol cevaplanmış ürün soruları API çağrısı başlatılıyor")

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Trendyol API hatası: {response.status} - {error_text}")
                    return []

                data = await response.json()
                total_pages = data.get('totalPages', 1)
                total_elements = data.get('totalElements', 0)

                if total_elements == 0:
                    logger.info("Cevaplanmış ürün sorusu bulunamadı.")
                    return []

                logger.info(f"Toplam {total_elements} cevaplanmış soru bulundu.")

                all_questions = data.get('content', [])

                if total_pages > 1:
                    semaphore = asyncio.Semaphore(5)
                    tasks = []
                    for page in range(1, total_pages):
                        page_params = params.copy()
                        page_params['page'] = page
                        tasks.append(fetch_questions_page(session, url, headers, page_params, semaphore))

                    page_results = await asyncio.gather(*tasks)
                    for result in page_results:
                        if result:
                            all_questions.extend(result)

                return all_questions

    except Exception as e:
        logger.error(f"Cevaplanmış soruları çekerken hata: {e}", exc_info=True)
        return []


def process_questions(questions_data, status="WAITING_FOR_ANSWER"):
    """
    Trendyol'dan gelen sorular verisini işle ve veritabanına kaydet
    """
    if not questions_data:
        logger.warning("İşlenecek soru verisi bulunamadı.")
        return 0

    logger.info(f"Toplam {len(questions_data)} soru işleniyor...")

    new_count = 0
    update_count = 0

    try:
        for question in questions_data:
            question_id = question.get('id')

            if not question_id:
                logger.warning("Soru ID'si bulunamadı, atlıyorum.")
                continue

            existing_question = ProductQuestion.query.filter_by(question_id=str(question_id)).first()

            question_date_str = question.get('questionDate')
            question_date = None

            if question_date_str:
                try:
                    question_date = datetime.fromisoformat(question_date_str.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    try:
                        question_date = datetime.strptime(question_date_str.split('.')[0], "%Y-%m-%dT%H:%M:%S")
                    except:
                        logger.warning(f"Tarih formatı çevrilemedi: {question_date_str}")
                        question_date = datetime.utcnow()  

            answer_date_str = question.get('answerDate')
            answer_date = None

            if answer_date_str:
                try:
                    answer_date = datetime.fromisoformat(answer_date_str.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    try:
                        answer_date = datetime.strptime(answer_date_str.split('.')[0], "%Y-%m-%dT%H:%M:%S")
                    except:
                        answer_date = datetime.utcnow() if question.get('answer') else None

            product_id = str(question.get('productId', ''))
            barcode = question.get('barcode', '')

            if not barcode and product_id:
                product = Product.query.filter_by(product_main_id=product_id).first() # product_main_id ile eşleşme daha doğru olabilir
                if product:
                    barcode = product.barcode

            question_data = {
                'question_id': str(question_id),
                'product_id': product_id,
                'barcode': barcode,
                'product_name': question.get('productName', ''),
                'question_text': question.get('text', ''), # Trendyol API'de 'text' olarak geliyor
                'asker_name': question.get('userName', ''), # Trendyol API 'userName' olarak dönebilir
                'question_date': question_date,
                'status': status, # Dışarıdan gelen status kullanılacak
                'answer_text': question.get('answer', {}).get('text') if isinstance(question.get('answer'), dict) else question.get('answer'), # Cevap bir dict içinde 'text' olarak gelebilir
                'answer_date': answer_date,
                'is_approved': question.get('public', False), # 'public' alanı onay durumu olabilir
                'last_sync': datetime.utcnow()
            }

            if existing_question:
                for key, value in question_data.items():
                    setattr(existing_question, key, value)
                update_count += 1
            else:
                new_question = ProductQuestion(**question_data)
                db.session.add(new_question)
                new_count += 1

        db.session.commit()
        logger.info(f"Toplam {new_count} yeni soru eklendi, {update_count} soru güncellendi.")
        return new_count + update_count

    except Exception as e:
        db.session.rollback()
        logger.error(f"Soruları işlerken hata: {e}", exc_info=True)
        return 0


async def send_Youtube(question_id, answer_text):
    """
    Trendyol API'ye soru cevabını gönder
    """
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/questions/{question_id}/answers"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }

        payload = {
            "text": answer_text
        }

        logger.info(f"Trendyol'a soru cevabı gönderiliyor: Soru ID={question_id}")

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response_text = await response.text()

                if response.status in (200, 201, 204): # 204 No Content de başarılı sayılabilir
                    logger.info(f"Soru cevabı başarıyla gönderildi: {response.status}")
                    return True, "Cevap başarıyla gönderildi."
                else:
                    logger.error(f"Cevap gönderilirken hata: {response.status} - {response_text}")
                    return False, f"Hata: {response.status} - {response_text}"

    except Exception as e:
        error_msg = f"Cevap gönderilirken bir hata oluştu: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg


# API endpoint: Trendyol'dan soruları çek ve veritabanına kaydet
@product_questions_bp.route('/fetch_questions', methods=['POST'])
@login_required
async def fetch_questions_route():
    try:
        # Bekleyen soruları çek
        waiting_questions = await fetch_trendyol_questions_async()
        waiting_count = process_questions(waiting_questions, "WAITING_FOR_ANSWER")

        # Cevaplanmış soruları da çek
        answered_questions = await fetch_answered_questions_async()
        answered_count = process_questions(answered_questions, "ANSWERED")

        total_updated_count = waiting_count + answered_count # Güncellenen veya eklenen toplam soru

        if total_updated_count > 0:
            message = f"Toplam {waiting_count} bekleyen ve {answered_count} cevaplanmış olmak üzere {total_updated_count} soru güncellendi."
            flash(message, "success")
        else:
            flash("Yeni ürün sorusu bulunamadı veya mevcutlar güncel.", "info")

        return redirect(url_for('product_questions.questions_list'))

    except Exception as e:
        error_msg = f"Ürün sorularını çekerken bir hata oluştu: {str(e)}"
        logger.error(error_msg, exc_info=True)
        flash(error_msg, "danger")
        return redirect(url_for('product_questions.questions_list'))


# Ürün soruları listesi
@product_questions_bp.route('/questions', methods=['GET'])
@login_required
def questions_list():
    status = request.args.get('status', 'WAITING_FOR_ANSWER')
    search_term = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = ProductQuestion.query

    if status:
        query = query.filter(ProductQuestion.status == status)

    if search_term:
        search_pattern = f"%{search_term}%"
        query = query.filter(
            (ProductQuestion.product_name.ilike(search_pattern)) | 
            (ProductQuestion.question_text.ilike(search_pattern)) | 
            (ProductQuestion.barcode.ilike(search_pattern))
        )

    query = query.order_by(desc(ProductQuestion.question_date))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    questions = pagination.items

    waiting_count = ProductQuestion.query.filter_by(status="WAITING_FOR_ANSWER").count()
    answered_count = ProductQuestion.query.filter_by(status="ANSWERED").count()

    return render_template(
        'product_questions/questions_list.html',
        questions=questions,
        pagination=pagination,
        waiting_count=waiting_count,
        answered_count=answered_count,
        current_status=status,
        search_term=search_term
    )


# Soru detayları ve cevaplama
@product_questions_bp.route('/questions/<question_id_param>', methods=['GET', 'POST']) # question_id -> question_id_param
@login_required
async def question_detail(question_id_param): # question_id -> question_id_param
    # question_id_param string gelebilir, int'e çevirme gereksinimi yok çünkü DB'de String.
    question = ProductQuestion.query.filter_by(question_id=str(question_id_param)).first_or_404()

    if request.method == 'POST':
        answer_text = request.form.get('answer_text', '').strip()

        if not answer_text:
            flash("Lütfen bir cevap yazın.", "warning")
            return redirect(url_for('product_questions.question_detail', question_id_param=question_id_param))

        success, message = await send_Youtube(question_id_param, answer_text)

        if success:
            question.answer_text = answer_text
            question.answer_date = datetime.utcnow()
            question.status = "ANSWERED"
            db.session.commit()
            flash("Cevabınız başarıyla kaydedildi ve Trendyol'a gönderildi.", "success")
        else:
            flash(f"Cevap gönderilirken bir hata oluştu: {message}", "danger")

        return redirect(url_for('product_questions.question_detail', question_id_param=question_id_param))

    product = None
    if question.barcode:
        product = Product.query.filter_by(barcode=question.barcode).first()
    elif question.product_id: # Barkod yoksa product_id ile dene (product_main_id olabilir bu)
        product = Product.query.filter_by(product_main_id=str(question.product_id)).first()

    return render_template(
        'product_questions/question_detail.html',
        question=question,
        product=product
    )


# AJAX endpoint: Soru cevaplama
@product_questions_bp.route('/api/answer_question', methods=['POST'])
@login_required
async def answer_question_api():
    try:
        data = request.get_json()
        question_id = data.get('question_id')
        answer_text = data.get('answer_text', '').strip()

        if not question_id or not answer_text:
            return jsonify({'success': False, 'message': 'Soru ID ve cevap gereklidir.'})

        question = ProductQuestion.query.filter_by(question_id=str(question_id)).first()

        if not question:
            return jsonify({'success': False, 'message': 'Soru bulunamadı.'})

        success, message = await send_Youtube(question_id, answer_text)

        if success:
            question.answer_text = answer_text
            question.answer_date = datetime.utcnow()
            question.status = "ANSWERED"
            db.session.commit()

            return jsonify({
                'success': True, 
                'message': 'Cevap başarıyla gönderildi.',
                'answer_date': question.answer_date.strftime("%d.%m.%Y %H:%M")
            })
        else:
            return jsonify({'success': False, 'message': message})

    except Exception as e:
        logger.error(f"Soru cevaplama hatası: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Bir hata oluştu: {str(e)}'})