import os
from flask import Blueprint, request, jsonify, render_template
from dotenv import load_dotenv
from openai import OpenAI
from logger_config import app_logger

# Logger yapılandırması
logger = app_logger

# Çevre değişkenlerini yükle
load_dotenv()

# OpenAI istemcisini oluştur
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Model seçimi - Daha hızlı ve ekonomik model olarak o3 mini (gpt-3.5-turbo)
DEFAULT_MODEL = "gpt-4o"  # Stok tahminlemesin de en iyi model

# Blueprint oluşturma
openai_bp = Blueprint('openai_bp', __name__)

@openai_bp.route('/ai-analiz')
def ai_analiz():
    """
    AI analiz panelini gösteren sayfa
    """
    logger.debug("AI analiz sayfası açılıyor")
    return render_template('ai_analiz.html')

@openai_bp.route('/ai/analyze-text', methods=['POST'])
def analyze_text():
    """
    OpenAI API kullanarak metin analizi yapar
    """
    logger.debug(">> analyze_text fonksiyonu çağrıldı")

    try:
        # POST verilerini al
        data = request.get_json()

        if not data or 'text' not in data:
            logger.error("Geçersiz veri formatı, 'text' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "text" alanı gerekli.'}), 400

        user_text = data['text']
        logger.debug(f"Analiz edilecek metin: {user_text[:50]}...")

        # OpenAI API çağrısı - o3 mini ile
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,  # o3 mini - daha ekonomik ve hızlı
            messages=[
                {"role": "system", "content": "Sen bir metin analiz uzmanısın. Verilen metni analiz et ve önemli noktaları vurgula."},
                {"role": "user", "content": user_text}
            ],
            max_tokens=500,
            temperature=0.5
        )

        # Yanıtı işle - yeni API formatı
        analysis_result = response.choices[0].message.content.strip()
        logger.debug(f"OpenAI analiz sonucu: {analysis_result[:50]}...")

        return jsonify({
            'success': True,
            'analysis': analysis_result
        })

    except Exception as e:
        logger.error(f"OpenAI analiz hatası: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@openai_bp.route('/ai/siparis-ozeti', methods=['POST'])
def siparis_ozeti():
    """
    Sipariş verilerini özetlemek için OpenAI kullanır
    """
    logger.debug(">> siparis_ozeti fonksiyonu çağrıldı")

    try:
        # POST verilerini al
        data = request.get_json()

        if not data or 'siparis_bilgileri' not in data:
            logger.error("Geçersiz veri formatı, 'siparis_bilgileri' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "siparis_bilgileri" alanı gerekli.'}), 400

        siparis_bilgileri = data['siparis_bilgileri']
        logger.debug(f"Özeti çıkarılacak sipariş bilgileri alındı")

        # OpenAI API çağrısı - o3 mini ile
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Sen bir sipariş analiz uzmanısın. Verilen sipariş bilgilerini inceleyip özet çıkar ve önemli noktaları vurgula."},
                {"role": "user", "content": str(siparis_bilgileri)}
            ],
            max_tokens=500,
            temperature=0.3
        )

        # Yanıtı işle - yeni API formatı
        ozet = response.choices[0].message.content.strip()
        logger.debug(f"Sipariş özeti oluşturuldu")

        return jsonify({
            'success': True,
            'ozet': ozet
        })

    except Exception as e:
        logger.error(f"OpenAI sipariş özeti hatası: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@openai_bp.route('/ai/urun-onerileri', methods=['POST'])
def urun_onerileri():
    """
    Müşteri profiline göre ürün önerileri oluşturur
    """
    logger.debug(">> urun_onerileri fonksiyonu çağrıldı")

    try:
        # POST verilerini al
        data = request.get_json()

        if not data or 'musteri_profili' not in data:
            logger.error("Geçersiz veri formatı, 'musteri_profili' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "musteri_profili" alanı gerekli.'}), 400

        musteri_profili = data['musteri_profili']
        urun_listesi = data.get('urun_listesi', [])
        logger.debug(f"Müşteri profili ve ürün listesi alındı")

        # OpenAI API çağrısı için prompt hazırlama
        prompt = f"""
        Müşteri Profili:
        {musteri_profili}

        Mevcut Ürün Listesi:
        {urun_listesi}

        Yukarıdaki müşteri profiline göre ve mevcut ürün listesini dikkate alarak 
        bu müşteriye önerebileceğimiz en uygun 5 ürünü JSON formatında listele.
        Her ürün için şunları belirt: ad, açıklama, fiyat ve öneri sebebi.
        """

        # OpenAI API çağrısı - o3 mini ile
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Sen bir ürün öneri uzmanısın. Müşteri profiline göre en uygun ürünleri öner."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )

        # Yanıtı işle
        oneriler = response.choices[0].message.content.strip()

        # Token kullanım bilgilerini al
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens

        # OpenAI fiyatlandırma (TL cinsinden yaklaşık değerler)
        prompt_cost_per_1k = 0.15 * 33  # 0.15$ per 1K tokens * yaklaşık TL kuru
        completion_cost_per_1k = 0.20 * 33  # 0.20$ per 1K tokens * yaklaşık TL kuru

        # Maliyet hesaplaması (TL)
        prompt_cost = (prompt_tokens / 1000) * prompt_cost_per_1k
        completion_cost = (completion_tokens / 1000) * completion_cost_per_1k
        total_cost = prompt_cost + completion_cost

        logger.debug(f"Ürün önerileri oluşturuldu")
        logger.debug(f"Token kullanımı - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Toplam: {total_tokens}")
        logger.debug(f"Tahmini maliyet: {total_cost:.5f} TL")

        return jsonify({
            'success': True,
            'oneriler': oneriler,
            'token_usage': {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'estimated_cost': round(total_cost, 5)
            }
        })

    except Exception as e:
        logger.error(f"OpenAI ürün önerileri hatası: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@openai_bp.route('/ai/satis-analizi', methods=['POST'])
def satis_analizi():
    """
    Satış verilerini AI ile analiz eder
    """
    logger.debug(">> satis_analizi fonksiyonu çağrıldı")

    try:
        # POST verilerini al
        data = request.get_json()

        if not data or 'satis_verileri' not in data:
            logger.error("Geçersiz veri formatı, 'satis_verileri' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "satis_verileri" alanı gerekli.'}), 400

        satis_verileri = data['satis_verileri']
        logger.debug(f"Analiz edilecek satış verileri alındı")

        # OpenAI API çağrısı - o3 mini ile
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Sen bir satış analiz uzmanısın. Verilen satış verilerini analiz et, trendleri belirle ve önemli noktaları vurgula."},
                {"role": "user", "content": str(satis_verileri)}
            ],
            max_tokens=800,
            temperature=0.3
        )

        # Yanıtı işle
        analiz_sonucu = response.choices[0].message.content.strip()
        logger.debug(f"Satış analizi sonucu oluşturuldu")

        # Token kullanım bilgilerini al
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens

        # OpenAI fiyatlandırma (TL cinsinden yaklaşık değerler)
        prompt_cost_per_1k = 0.15 * 33  # 0.15$ per 1K tokens * yaklaşık TL kuru
        completion_cost_per_1k = 0.20 * 33  # 0.20$ per 1K tokens * yaklaşık TL kuru

        # Maliyet hesaplaması (TL)
        prompt_cost = (prompt_tokens / 1000) * prompt_cost_per_1k
        completion_cost = (completion_tokens / 1000) * completion_cost_per_1k
        total_cost = prompt_cost + completion_cost

        return jsonify({
            'success': True,
            'analiz': analiz_sonucu,
            'token_usage': {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'estimated_cost': round(total_cost, 5)
            }
        })

    except Exception as e:
        logger.error(f"OpenAI satış analizi hatası: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@openai_bp.route('/ai/trend-tahmini', methods=['POST'])
def trend_tahmini():
    """
    Satış verilerine göre gelecek dönem tahminleri yapar
    """
    logger.debug(">> trend_tahmini fonksiyonu çağrıldı")

    try:
        # POST verilerini al
        data = request.get_json()

        if not data or 'gecmis_veriler' not in data:
            logger.error("Geçersiz veri formatı, 'gecmis_veriler' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "gecmis_veriler" alanı gerekli.'}), 400

        gecmis_veriler = data['gecmis_veriler']
        tahmin_suresi = data.get('tahmin_suresi', 'bir ay')  # varsayılan bir ay
        logger.debug(f"Tahmin için geçmiş veriler alındı. Tahmin süresi: {tahmin_suresi}")

        # OpenAI API çağrısı
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Sen bir satış tahmin ve trend analizi uzmanısın. Geçmiş satış verilerine bakarak gelecek dönem için tahminler yap."},
                {"role": "user", "content": f"Aşağıdaki geçmiş satış verilerini analiz ederek gelecek {tahmin_suresi} için satış tahminleri yap. Mümkünse sayısal değerler ve yüzdelik değişimler belirt.\n\nGeçmiş Veriler:\n{str(gecmis_veriler)}"}
            ],
            max_tokens=1000,
            temperature=0.4
        )

        # Yanıtı işle
        tahmin_sonucu = response.choices[0].message.content.strip()
        logger.debug(f"Trend tahmini sonucu oluşturuldu")

        # Token kullanım bilgilerini al
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens

        # OpenAI fiyatlandırma (TL cinsinden yaklaşık değerler)
        prompt_cost_per_1k = 0.15 * 33  # 0.15$ per 1K tokens * yaklaşık TL kuru
        completion_cost_per_1k = 0.20 * 33  # 0.20$ per 1K tokens * yaklaşık TL kuru

        # Maliyet hesaplaması (TL)
        prompt_cost = (prompt_tokens / 1000) * prompt_cost_per_1k
        completion_cost = (completion_tokens / 1000) * completion_cost_per_1k
        total_cost = prompt_cost + completion_cost

        return jsonify({
            'success': True,
            'tahmin': tahmin_sonucu,
            'token_usage': {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'estimated_cost': round(total_cost, 5)
            }
        })

    except Exception as e:
        logger.error(f"OpenAI trend tahmini hatası: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@openai_bp.route('/ai/dashboard-analiz', methods=['POST'])
def dashboard_analiz():
    """
    Dashboard verileri için özet ve öngörüleri oluşturur
    """
    logger.debug(">> dashboard_analiz fonksiyonu çağrıldı")

    try:
        # POST verilerini al
        data = request.get_json()

        if not data or 'dashboard_verileri' not in data:
            logger.error("Geçersiz veri formatı, 'dashboard_verileri' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "dashboard_verileri" alanı gerekli.'}), 400

        dashboard_verileri = data['dashboard_verileri']
        logger.debug(f"Dashboard verileri analiz için alındı")

        # OpenAI API çağrısı
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Sen bir e-ticaret ve satış analiz uzmanısın. Dashboard verilerini analiz ederek önemli içgörüler çıkar ve eylem önerilerinde bulun."},
                {"role": "user", "content": f"Aşağıdaki e-ticaret dashboard verilerini analiz et. Önemli trendleri, anormal değişimleri belirle ve iş sahibine somut önerilerde bulun:\n\n{str(dashboard_verileri)}"}
            ],
            max_tokens=800,
            temperature=0.3
        )

        # Yanıtı işle
        analiz_sonucu = response.choices[0].message.content.strip()
        logger.debug(f"Dashboard analizi sonucu oluşturuldu")

        # Token kullanım bilgilerini al
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens

        # OpenAI fiyatlandırma (TL cinsinden yaklaşık değerler)
        prompt_cost_per_1k = 0.15 * 33  # 0.15$ per 1K tokens * yaklaşık TL kuru
        completion_cost_per_1k = 0.20 * 33  # 0.20$ per 1K tokens * yaklaşık TL kuru

        # Maliyet hesaplaması (TL)
        prompt_cost = (prompt_tokens / 1000) * prompt_cost_per_1k
        completion_cost = (completion_tokens / 1000) * completion_cost_per_1k
        total_cost = prompt_cost + completion_cost

        return jsonify({
            'success': True,
            'analiz': analiz_sonucu,
            'token_usage': {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'estimated_cost': round(total_cost, 5)
            }
        })

    except Exception as e:
        logger.error(f"OpenAI dashboard analizi hatası: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@openai_bp.route('/ai-analiz', methods=['GET'])
def ai_analiz_sayfasi():
    """
    AI analiz arayüzünü gösterir
    """
    return render_template('ai_analiz.html')