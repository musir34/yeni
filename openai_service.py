import os
from flask import Blueprint, request, jsonify, render_template
from dotenv import load_dotenv
from openai import OpenAI
from logger_config import app_logger
import traceback # Hata ayıklama için eklendi

# Logger yapılandırması
logger = app_logger

# Çevre değişkenlerini yükle
load_dotenv()

# OpenAI istemcisini oluştur
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Model seçimi - Stok tahminlemesinde ve genel analizlerde en iyi model olarak gpt-4o
DEFAULT_MODEL = "gpt-4o"

# Blueprint oluşturma
openai_bp = Blueprint('openai_bp', __name__)

# --- Maliyet Hesaplama için Sabitler (GPT-4o Mayıs 2024 fiyatları baz alınmıştır) ---
# Input: $5.00 / 1M tokens => $0.005 / 1K tokens
# Output: $15.00 / 1M tokens => $0.015 / 1K tokens
USD_TRY_EXCHANGE_RATE = 33  # Kullanıcının kodundaki kur varsayımı
GPT4O_PROMPT_COST_PER_1K_USD = 0.005
GPT4O_COMPLETION_COST_PER_1K_USD = 0.015

def calculate_openai_cost_tl(prompt_tokens, completion_tokens):
    """OpenAI API çağrısının yaklaşık maliyetini TL cinsinden hesaplar."""
    prompt_cost_tl = (prompt_tokens / 1000) * GPT4O_PROMPT_COST_PER_1K_USD * USD_TRY_EXCHANGE_RATE
    completion_cost_tl = (completion_tokens / 1000) * GPT4O_COMPLETION_COST_PER_1K_USD * USD_TRY_EXCHANGE_RATE
    total_cost_tl = prompt_cost_tl + completion_cost_tl
    return round(total_cost_tl, 5)

@openai_bp.route('/ai-analiz', methods=['GET'])
def ai_analiz():
    """
    AI analiz panelini/arayüzünü gösteren sayfa.
    Bu sayfa artık özellikle stok tahminlemesi için de kullanılabilir.
    """
    logger.debug("AI analiz sayfası açılıyor")
    return render_template('ai_analiz.html') # Bu HTML dosyasının var olduğundan emin olmalısın

@openai_bp.route('/ai/analyze-text', methods=['POST'])
def analyze_text():
    """
    OpenAI API kullanarak metin analizi yapar.
    """
    logger.debug(">> analyze-text fonksiyonu çağrıldı")
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            logger.error("Geçersiz veri formatı, 'text' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "text" alanı gerekli.'}), 400

        user_text = data['text']
        logger.debug(f"Analiz edilecek metin: {user_text[:50]}...")

        system_prompt = """Sen bir metin analiz uzmanısın. Sana verilen metni dikkatlice analiz et. 
        Önemli noktaları, ana fikirleri ve eğer varsa eyleme geçirilebilir içgörüleri belirle. 
        Analizini net başlıklar altında ve madde işaretleri kullanarak Güllü Ayakkabı bağlamında (eğer metin bu konuda ise) sun."""

        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            max_tokens=700, # Biraz artırıldı
            temperature=0.5
        )
        analysis_result = response.choices[0].message.content.strip()
        logger.debug(f"OpenAI analiz sonucu: {analysis_result[:50]}...")

        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens
        estimated_cost_tl = calculate_openai_cost_tl(prompt_tokens, completion_tokens)
        logger.debug(f"Token kullanımı (analyze_text) - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Toplam: {total_tokens}, Tahmini Maliyet: {estimated_cost_tl:.5f} TL")

        return jsonify({
            'success': True,
            'analysis': analysis_result,
            'token_usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'total_tokens': total_tokens, 'estimated_cost_tl': estimated_cost_tl}
        })
    except Exception as e:
        logger.error(f"OpenAI metin analizi hatası: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e), 'trace': traceback.format_exc()}), 500

@openai_bp.route('/ai/siparis-ozeti', methods=['POST'])
def siparis_ozeti():
    """
    Sipariş verilerini özetlemek için OpenAI kullanır.
    """
    logger.debug(">> siparis_ozeti fonksiyonu çağrıldı")
    try:
        data = request.get_json()
        if not data or 'siparis_bilgileri' not in data:
            logger.error("Geçersiz veri formatı, 'siparis_bilgileri' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "siparis_bilgileri" alanı gerekli.'}), 400

        siparis_bilgileri = data['siparis_bilgileri']
        logger.debug("Özeti çıkarılacak sipariş bilgileri alındı")

        system_prompt = """Sen Güllü Ayakkabı için çalışan bir sipariş analiz uzmanısın. 
        Verilen sipariş bilgilerini (JSON veya metin formatında olabilir) dikkatlice incele.
        Aşağıdaki yapıda bir özet çıkar:
        - **Genel Sipariş Bilgileri:** (Sipariş ID, Tarih vb. önemli bilgiler)
        - **Müşteri Notları/Özel İstekler:** (Eğer varsa ve önemliyse)
        - **Ürünler:** (Her ürün için: Adı, Adedi, Varsa varyantı (renk/beden))
        - **Dikkat Edilmesi Gerekenler:** (Stok durumu, aciliyet, potansiyel sorunlar vb.)
        Özeti Güllü Ayakkabı operasyonları için faydalı olacak şekilde, net ve anlaşılır bir dille sun."""

        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Lütfen aşağıdaki sipariş bilgilerini Güllü Ayakkabı için özetle:\n\n{str(siparis_bilgileri)}"}
            ],
            max_tokens=600, # Biraz artırıldı
            temperature=0.3
        )
        ozet = response.choices[0].message.content.strip()
        logger.debug("Sipariş özeti oluşturuldu")

        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens
        estimated_cost_tl = calculate_openai_cost_tl(prompt_tokens, completion_tokens)
        logger.debug(f"Token kullanımı (siparis_ozeti) - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Toplam: {total_tokens}, Tahmini Maliyet: {estimated_cost_tl:.5f} TL")

        return jsonify({
            'success': True,
            'ozet': ozet,
            'token_usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'total_tokens': total_tokens, 'estimated_cost_tl': estimated_cost_tl}
        })
    except Exception as e:
        logger.error(f"OpenAI sipariş özeti hatası: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e), 'trace': traceback.format_exc()}), 500

@openai_bp.route('/ai/urun-onerileri', methods=['POST'])
def urun_onerileri():
    logger.debug(">> urun_onerileri fonksiyonu çağrıldı")
    try:
        data = request.get_json()
        if not data or 'musteri_profili' not in data:
            logger.error("Geçersiz veri formatı, 'musteri_profili' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "musteri_profili" alanı gerekli.'}), 400

        musteri_profili = data['musteri_profili']
        urun_listesi_str = data.get('urun_listesi', "[]") # String olarak alıp loglayalım
        logger.debug(f"Müşteri profili alındı. Ürün listesi (ilk 100 char): {urun_listesi_str[:100]}")

        system_prompt = """Sen Güllü Ayakkabı firması için çalışan bir e-ticaret ürün öneri uzmanısın. 
        Güllü Ayakkabı'nın topuklu ayakkabılar ve ayakkabı üretim malzemeleri (topuk, taban, neolit/jurdan vb.) sattığını biliyorsun.
        Müşteri profiline ve firmanın ürün gamına göre en uygun ürünleri JSON formatında önermelisin.
        Önerdiğin ürünlerin açıklamalarını ve öneri sebeplerini ikna edici, müşteri dostu ve Güllü Ayakkabı markasına yakışır bir dille yaz.
        Kesinlikle Güllü Ayakkabı'nın ürün gamı dışından bir şey önerme."""

        user_prompt = f"""
        Müşteri Profili:
        {musteri_profili}

        Güllü Ayakkabı Ürün Listemiz (Referans İçin):
        {urun_listesi_str} 

        Yukarıdaki müşteri profiline göre ve mevcut ürün listemizi dikkate alarak bu müşteriye önerebileceğimiz en uygun 5 ürünü JSON formatında listele.
        Her ürün için şunları belirt: 'urun_adi', 'aciklama' (detaylı ve çekici), 'fiyat_tahmini_tl' (biliniyorsa veya genel bir aralık), ve 'oneri_sebebi' (müşteri profiliyle bağlantılı, ikna edici).
        JSON çıktın şu yapıda olmalı: {{ "onerilen_urunler": [ {{...}}, {{...}} ] }}
        """
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=1000,
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        oneriler_json_string = response.choices[0].message.content.strip()

        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens
        estimated_cost_tl = calculate_openai_cost_tl(prompt_tokens, completion_tokens)

        logger.debug("Ürün önerileri oluşturuldu (JSON formatında)")
        logger.debug(f"Token kullanımı - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Toplam: {total_tokens}")
        logger.debug(f"Tahmini maliyet: {estimated_cost_tl:.5f} TL")

        return jsonify({
            'success': True,
            'oneriler': oneriler_json_string, 
            'token_usage': {
                'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 
                'total_tokens': total_tokens, 'estimated_cost_tl': estimated_cost_tl
            }
        })
    except Exception as e:
        logger.error(f"OpenAI ürün önerileri hatası: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e), 'trace': traceback.format_exc()}), 500

@openai_bp.route('/ai/satis-analizi', methods=['POST'])
def satis_analizi():
    logger.debug(">> satis_analizi fonksiyonu çağrıldı")
    try:
        data = request.get_json()
        if not data or 'satis_verileri' not in data:
            logger.error("Geçersiz veri formatı, 'satis_verileri' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "satis_verileri" alanı gerekli.'}), 400

        satis_verileri_str = data['satis_verileri']
        logger.debug(f"Analiz edilecek satış verileri alındı (ilk 100 char): {str(satis_verileri_str)[:100]}")

        system_prompt = """Sen Güllü Ayakkabı firması için çalışan kıdemli bir satış analiz uzmanısın. 
        Firmanın topuklu ayakkabı ve ayakkabı üretim malzemeleri (topuk, taban, neolit/jurdan) sattığını biliyorsun.
        Analizini bir rapor formatında sun. Ana başlıklar kullan (Örn: 1. Genel Satış Performansı, 2. Ürün Kategorisi Bazında Analiz, 3. Öne Çıkan Trendler, 4. Dikkat Edilmesi Gereken Noktalar, 5. Stratejik Öneriler). 
        Önerilerini numaralandırılmış liste halinde, somut ve uygulanabilir şekilde ver. 
        Bulgularını mümkün olduğunca sayılara ve verilere dayandır. Anlaşılır ve profesyonel bir dil kullan."""

        user_prompt = f"""Güllü Ayakkabı Firması'na ait aşağıdaki satış verilerini analiz et. 
        Özellikle topuklu ayakkabılar ve ayakkabı malzemeleri (topuk, taban, neolit) satışlarına odaklan.
        Önemli trendleri, iyi ve kötü giden ürünleri/kategorileri belirle.
        Satışları artırmak, maliyetleri düşürmek ve genel karlılığı iyileştirmek için somut, verilere dayalı önerilerde bulun.
        Analizini yukarıda belirtilen rapor formatında sun.

        Satış Verileri:
        ```json
        {str(satis_verileri_str)}
        ```
        """
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=1500, # Detaylı rapor için artırıldı
            temperature=0.3
        )
        analiz_sonucu = response.choices[0].message.content.strip()
        logger.debug("Satış analizi sonucu oluşturuldu")

        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens
        estimated_cost_tl = calculate_openai_cost_tl(prompt_tokens, completion_tokens)

        logger.debug(f"Token kullanımı - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Toplam: {total_tokens}")
        logger.debug(f"Tahmini maliyet: {estimated_cost_tl:.5f} TL")

        return jsonify({
            'success': True,
            'analiz': analiz_sonucu,
            'token_usage': {
                'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens,
                'total_tokens': total_tokens, 'estimated_cost_tl': estimated_cost_tl
            }
        })
    except Exception as e:
        logger.error(f"OpenAI satış analizi hatası: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e), 'trace': traceback.format_exc()}), 500

@openai_bp.route('/ai/trend-tahmini', methods=['POST'])
def trend_tahmini():
    logger.debug(">> trend_tahmini fonksiyonu çağrıldı")
    try:
        data = request.get_json()
        if not data or 'gecmis_veriler' not in data:
            logger.error("Geçersiz veri formatı, 'gecmis_veriler' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "gecmis_veriler" alanı gerekli.'}), 400

        gecmis_veriler_str = data['gecmis_veriler']
        tahmin_suresi = data.get('tahmin_suresi', 'bir sonraki çeyrek')
        logger.debug(f"Trend tahmini için geçmiş veriler alındı (ilk 100 char): {str(gecmis_veriler_str)[:100]}. Tahmin süresi: {tahmin_suresi}")

        system_prompt = """Sen Güllü Ayakkabı için çalışan bir satış trendi ve pazar analizi uzmanısın. 
        Firmanın topuklu ayakkabı ve ayakkabı üretim malzemeleri (topuk, taban, neolit/jurdan) sattığını biliyorsun.
        Tahminlerini net başlıklar altında (örn: A. Genel Pazar Trendleri, B. Topuklu Ayakkabı Kategori Trendleri, C. Ayakkabı Malzemeleri Trendleri, D. Öngörüler ve Stratejik Notlar) ve maddeler halinde sun. 
        Belirttiğin sayısal aralıkları ve yüzdelik değişimleri kolay anlaşılır bir şekilde ifade et. 
        Tahminlerinin dayanaklarını (geçmiş verilerdeki örüntüler, mevsimsel etkiler, pazar bilgileri vb.) kısaca açıkla."""

        user_prompt = f"""Güllü Ayakkabı Firması'na ait aşağıdaki geçmiş satış verilerini ve biliniyorsa genel pazar bilgilerini analiz ederek gelecek '{tahmin_suresi}' için satış trendlerini tahmin et. 
        Mümkünse sayısal aralıklar (örn: %10-%15 artış) ve yüzdelik değişimler belirt. 
        Özellikle topuklu ayakkabı ve ayakkabı malzemeleri (topuk, taban, neolit) trendlerine odaklan.
        Tahminlerini yukarıda belirtilen rapor formatında sun.

        Geçmiş Veriler ve Pazar Bilgileri:
        ```json
        {str(gecmis_veriler_str)}
        ```
        """
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=1200, # Detaylı tahmin için artırıldı
            temperature=0.4
        )
        tahmin_sonucu = response.choices[0].message.content.strip()
        logger.debug("Trend tahmini sonucu oluşturuldu")

        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens
        estimated_cost_tl = calculate_openai_cost_tl(prompt_tokens, completion_tokens)

        logger.debug(f"Token kullanımı - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Toplam: {total_tokens}")
        logger.debug(f"Tahmini maliyet: {estimated_cost_tl:.5f} TL")

        return jsonify({
            'success': True,
            'tahmin': tahmin_sonucu,
            'token_usage': {
                'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens,
                'total_tokens': total_tokens, 'estimated_cost_tl': estimated_cost_tl
            }
        })
    except Exception as e:
        logger.error(f"OpenAI trend tahmini hatası: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e), 'trace': traceback.format_exc()}), 500

@openai_bp.route('/ai/dashboard-analiz', methods=['POST'])
def dashboard_analiz():
    logger.debug(">> dashboard_analiz fonksiyonu çağrıldı")
    try:
        data = request.get_json()
        if not data or 'dashboard_verileri' not in data:
            logger.error("Geçersiz veri formatı, 'dashboard_verileri' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "dashboard_verileri" alanı gerekli.'}), 400

        dashboard_verileri_str = data['dashboard_verileri']
        logger.debug(f"Dashboard verileri analiz için alındı (ilk 100 char): {str(dashboard_verileri_str)[:100]}")

        system_prompt = """Sen Güllü Ayakkabı firması için çalışan bir e-ticaret ve satış analiz uzmanısın. 
        Firmanın topuklu ayakkabı ve ayakkabı malzemeleri (topuk, taban, neolit/jurdan) üretip sattığını biliyorsun.
        Analizini Abdurrahman Bey'e (Müşir Abi'ye) hitaben, doğrudan, samimi ama profesyonel bir dille yaz. 
        Raporunu şu yapıda sun:
        1.  **Genel Durum Değerlendirmesi:** Dashboard'daki kilit metriklerin özeti.
        2.  **Olumlu Gelişmeler ve Fırsatlar:** İyi giden alanlar ve değerlendirilebilecek fırsatlar.
        3.  **Dikkat Edilmesi Gereken Alanlar ve Riskler:** İyileştirme gerektiren veya risk barındıran noktalar.
        4.  **Abdurrahman Bey'e (Müşir Abi'ye) Özel Somut Eylem Planı:** Net, önceliklendirilmiş ve uygulanabilir adımlar.
        Önemli bulgularını ve önerilerini **kalın** veya _italik_ ile vurgulayarak, madde işaretleri veya numaralı listelerle ayırarak sun."""

        user_prompt = f"""Abdurrahman Bey (Müşir Abi) için aşağıdaki Güllü Ayakkabı e-ticaret dashboard verilerini analiz et. 
        Hem topuklu ayakkabı satışları hem de malzeme satışları/kullanımı açısından önemli trendleri, anormal değişimleri belirle. 
        İşini kolaylaştıracak, somut, uygulanabilir önerilerde bulun. Analizini yukarıda belirtilen rapor formatında sun.

        Dashboard Verileri:
        ```json
        {str(dashboard_verileri_str)}
        ```
        """
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=1500, # Detaylı analiz için artırıldı
            temperature=0.3
        )
        analiz_sonucu = response.choices[0].message.content.strip()
        logger.debug("Dashboard analizi sonucu oluşturuldu")

        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens
        estimated_cost_tl = calculate_openai_cost_tl(prompt_tokens, completion_tokens)

        logger.debug(f"Token kullanımı - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Toplam: {total_tokens}")
        logger.debug(f"Tahmini maliyet: {estimated_cost_tl:.5f} TL")

        return jsonify({
            'success': True,
            'analiz': analiz_sonucu,
            'token_usage': {
                'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens,
                'total_tokens': total_tokens, 'estimated_cost_tl': estimated_cost_tl
            }
        })
    except Exception as e:
        logger.error(f"OpenAI dashboard analizi hatası: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e), 'trace': traceback.format_exc()}), 500

# --- YENİ STOK TAHMİNLEME FONKSİYONU ---
@openai_bp.route('/ai/stok-tahmini', methods=['POST'])
def stok_tahmini():
    logger.debug(">> Güllü Ayakkabı - Derinlemesine Stok Tahmini fonksiyonu çağrıldı")
    try:
        data = request.get_json()

        if not data or 'stok_satis_verileri' not in data:
            logger.error("Geçersiz veri formatı, 'stok_satis_verileri' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "stok_satis_verileri" alanı gerekli.'}), 400

        stok_satis_verileri_str = data['stok_satis_verileri'] # String olarak alalım
        tahmin_suresi = data.get('tahmin_suresi', 'gelecek 3 ay')
        ek_bilgiler_str = data.get('ek_bilgiler', None) # String olarak alalım

        logger.debug(f"Stok tahmini için veriler alındı. Tahmin süresi: {tahmin_suresi}")
        logger.debug(f"Alınan Stok/Satış Verileri (ilk 100 karakter): {str(stok_satis_verileri_str)[:100]}")
        if ek_bilgiler_str:
            logger.debug(f"Ek Bilgiler (ilk 100 karakter): {str(ek_bilgiler_str)[:100]}")

        system_prompt_content = f"""
Sen Abdurrahman (Müşir) Bey'in Güllü Ayakkabı Firması için çalışan, alanında uzman bir E-Ticaret Stok Yönetimi ve Talep Tahmin Yapay Zekasısın. 
Firmanın hem topuklu ayakkabı üretip sattığını hem de topuk, taban, neolit (jurdan) gibi ayakkabı üretim malzemelerini hem kendi üretimi için kullandığını hem de dışarıya sattığını çok iyi biliyorsun.
Amacın, sağlanan verilere dayanarak mümkün olan en doğru ve uygulanabilir stok tahminlerini ve yönetim stratejilerini sunmaktır.
Abdurrahman Bey'e (Müşir Abi'ye) doğrudan hitap ediyormuş gibi, çözüm odaklı, profesyonel ve güven verici bir dil kullan. Onun işini kolaylaştırmayı hedefle.

Analizlerinde Dikkat Etmen Gerekenler ve Rapor Formatı:
1.  **Yönetici Özeti (En Başa Eklenecek):** Abdurrahman Bey için 2-3 paragraflık, en kritik bulguları ve en önemli 3-5 eylem önerisini içeren bir özet sun.
2.  **Derinlemesine Talep Tahmini:** Sadece geçmiş verilere değil, olası trendlere, mevsimselliğe (örneğin topuklu ayakkabılar için ilkbahar/yaz yoğunluğu, malzemeler için üretim döngüleri) ve biliniyorsa pazarlama aktivitelerine göre talep tahmini yap. Tahminlerinin dayanaklarını açıkla.
3.  **Sağlıklı Stok Seviyeleri:** Stoksuz kalma (out-of-stock) durumlarını ve aşırı stok maliyetlerini minimize edecek optimum stok seviyelerini (güvenlik stoğu dahil) öner.
4.  **Ürün/Malzeme Bazlı Detay:** Her bir ana ürün veya ürün/malzeme grubu (örneğin, 'stiletto modelleri', '37 numara neolit tabanlar', 'standart topuklar') için ayrı tahminler ve öneriler sun.
5.  **Malzeme Yönetimi Dengesi:** Ayakkabı üretimi için gereken malzemelerin (topuk, taban, neolit) stoklarını da göz önünde bulundur. Bu malzemelerin hem iç tüketim (üretilecek ayakkabı miktarına göre) hem de dış satış taleplerini dengede tutacak öneriler getir.
6.  **E-Ticaret Stratejileri:** Özellikle Trendyol gibi platformlardaki satış dinamiklerini, kampanya dönemlerini ve müşteri beklentilerini dikkate alarak stratejiler öner.
7.  **Aksiyon Odaklı Çıktı:** Tahminlerini net rakamlarla (örneğin, 'X modelinden önümüzdeki {tahmin_suresi} içinde YYY adet satış bekleniyor, Z malzemesinden AAA adet sipariş verilmeli'), grafiksel gösterimler için uygun verilerle (mümkünse Markdown formatında özet tablolar) ve net gerekçelerle sun. Önemli rakamları ve önerileri **kalın** veya _italik_ yaparak vurgula.
8.  **Riskler, Fırsatlar ve Öneriler:** Potansiyel riskleri (tedarik zinciri sorunları, talep düşüşü vb.) ve fırsatları (yeni trendler, artan talep vb.) vurgula. Somut, uygulanabilir öneriler listesi sun.
9.  **Maliyet Bilinci:** Stok tutma maliyeti, sipariş maliyeti gibi faktörleri dolaylı da olsa göz önünde bulundurarak öneriler yap.
10. **Okunabilirlik:** Raporunu açık ve anlaşılır bir dille yaz. Karmaşık terimlerden kaçın veya açıkla. Başlıklar, alt başlıklar ve madde işaretleri kullanarak okunabilirliği artır.
"""

        user_prompt_parts = [
            f"Merhaba, ben Abdurrahman (Müşir). Güllü Ayakkabı Firması'nın e-ticaret operasyonları için önümüzdeki '{tahmin_suresi}' dönemine yönelik kapsamlı bir stok tahmini ve yönetimi analizi yapmanı istiyorum."
        ]
        user_prompt_parts.append("\nİŞTE ANALİZ İÇİN VERİLER:")
        user_prompt_parts.append("1. Geçmiş Satışlar, Mevcut Stok Durumları ve Ürün/Malzeme Bilgileri (JSON formatında):")
        # Veriyi JSON bloğu olarak işaretlemek AI'ın daha iyi anlamasına yardımcı olabilir
        user_prompt_parts.append(f"```json\n{str(stok_satis_verileri_str)}\n```") 

        if ek_bilgiler_str:
            user_prompt_parts.append("\n2. Ek Bilgiler (Pazar Durumu, Planlanan Kampanyalar, Tedarikçi Bilgileri Vb.):")
            user_prompt_parts.append(f"{str(ek_bilgiler_str)}")

        user_prompt_parts.append(f"\nLÜTFEN ANALİZİNİ SİSTEM PROMPT'UNDA BELİRTİLEN FORMAT VE DETAY SEVİYESİNDE, '{tahmin_suresi}' İÇİN SUN. ŞU NOKTALARA ÖZELLİKLE ODAKLAN:")
        user_prompt_parts.append("- **Yönetici Özeti** (Raporun en başında yer almalı).")
        user_prompt_parts.append("- Ürün ve malzeme bazında talep tahminleri (adet olarak, mümkünse güven aralıkları veya senaryolarla).")
        user_prompt_parts.append("- Her ürün/malzeme için önerilen ideal stok seviyeleri (minimum, maksimum, güvenlik stoğu).")
        user_prompt_parts.append("- Yeniden sipariş noktaları (ROP) ve önerilen sipariş miktarları (EOQ veya benzeri pratik yaklaşımlar).")
        user_prompt_parts.append("- Stokta kalma süresi yüksek (yavaş hareket eden) veya tükenme riski olan kritik ürünler/malzemeler için uyarılar ve özel stratejiler.")
        user_prompt_parts.append("- Üretim malzemelerinin (topuk, taban, neolit) hem iç üretim ihtiyacını hem de dış satış potansiyelini dengeleyecek detaylı stok planı.")
        user_prompt_parts.append("- Trendyol ve diğer e-ticaret kanalları için özel stok stratejileri (örneğin, kampanya dönemleri için hazırlık, hızlı satan ürünlerin yönetimi).")
        user_prompt_parts.append("- Genel olarak stok devir hızını artırma ve stok maliyetlerini (tutma, sipariş, stoksuz kalma) düşürme üzerine somut, uygulanabilir öneriler.")
        user_prompt_parts.append("\nAnalizini mümkün olduğunca Güllü Ayakkabı'nın özel durumunu (topuklu ayakkabı ve malzeme üretimi/satışı) yansıtacak şekilde, benim (Abdurrahman/Müşir) kolayca anlayıp uygulayabileceğim şekilde yap. Teşekkürler!")

        user_prompt_content = "\n".join(user_prompt_parts)

        logger.debug(f"Oluşturulan System Prompt (ilk 200 char): {system_prompt_content[:200]}...")
        logger.debug(f"Oluşturulan User Prompt (ilk 200 char): {user_prompt_content[:200]}...")


        response = client.chat.completions.create(
            model=DEFAULT_MODEL, 
            messages=[
                {"role": "system", "content": system_prompt_content},
                {"role": "user", "content": user_prompt_content}
            ],
            max_tokens=3500, # Daha da detaylı analiz ve rapor için artırıldı
            temperature=0.25  # Daha kesin ve analitik sonuçlar için düşük sıcaklık, hafif artışla esneklik
        )

        tahmin_raporu = response.choices[0].message.content.strip()
        logger.debug(f"Stok tahmini raporu oluşturuldu (ilk 100 karakter): {tahmin_raporu[:100]}...")

        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens
        estimated_cost_tl = calculate_openai_cost_tl(prompt_tokens, completion_tokens)

        logger.debug(f"Token kullanımı - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Toplam: {total_tokens}")
        logger.debug(f"Tahmini maliyet: {estimated_cost_tl:.5f} TL")

        return jsonify({
            'success': True,
            'tahmin_raporu': tahmin_raporu,
            'token_usage': {
                'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens,
                'total_tokens': total_tokens, 'estimated_cost_tl': estimated_cost_tl
            }
        })

    except Exception as e:
        logger.error(f"OpenAI Stok Tahmini (Güllü Ayakkabı) hatası: {str(e)}")
        logger.error(traceback.format_exc()) # Tam hata izini logla
        return jsonify({'success': False, 'error': str(e), 'trace': traceback.format_exc()}), 500