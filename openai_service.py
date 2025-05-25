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
    return render_template('ai_analiz.html')

@openai_bp.route('/ai/analyze-text', methods=['POST'])
def analyze_text():
    """
    OpenAI API kullanarak metin analizi yapar.
    """
    logger.debug(">> analyze_text fonksiyonu çağrıldı")
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            logger.error("Geçersiz veri formatı, 'text' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "text" alanı gerekli.'}), 400

        user_text = data['text']
        logger.debug(f"Analiz edilecek metin: {user_text[:50]}...")

        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Sen bir metin analiz uzmanısın. Verilen metni analiz et ve önemli noktaları vurgula."},
                {"role": "user", "content": user_text}
            ],
            max_tokens=500,
            temperature=0.5
        )
        analysis_result = response.choices[0].message.content.strip()
        logger.debug(f"OpenAI analiz sonucu: {analysis_result[:50]}...")

        # Token ve Maliyet (Maliyet hesaplaması burada eklenmemiş, istenirse eklenebilir)
        # prompt_tokens = response.usage.prompt_tokens
        # completion_tokens = response.usage.completion_tokens
        # total_tokens = response.usage.total_tokens
        # estimated_cost = calculate_openai_cost_tl(prompt_tokens, completion_tokens)

        return jsonify({
            'success': True,
            'analysis': analysis_result
            # 'token_usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'total_tokens': total_tokens, 'estimated_cost_tl': estimated_cost}
        })
    except Exception as e:
        logger.error(f"OpenAI metin analizi hatası: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

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

        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Sen bir sipariş analiz uzmanısın. Verilen sipariş bilgilerini inceleyip özet çıkar ve önemli noktaları vurgula."},
                {"role": "user", "content": str(siparis_bilgileri)}
            ],
            max_tokens=500,
            temperature=0.3
        )
        ozet = response.choices[0].message.content.strip()
        logger.debug("Sipariş özeti oluşturuldu")

        # Token ve Maliyet (Maliyet hesaplaması burada eklenmemiş, istenirse eklenebilir)

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
    Müşteri profiline göre ürün önerileri oluşturur.
    """
    logger.debug(">> urun_onerileri fonksiyonu çağrıldı")
    try:
        data = request.get_json()
        if not data or 'musteri_profili' not in data:
            logger.error("Geçersiz veri formatı, 'musteri_profili' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "musteri_profili" alanı gerekli.'}), 400

        musteri_profili = data['musteri_profili']
        urun_listesi = data.get('urun_listesi', []) # Mevcut ürünler isteğe bağlı
        logger.debug("Müşteri profili ve ürün listesi alındı")

        prompt = f"""
        Müşteri Profili:
        {musteri_profili}

        Varsa Mevcut Ürün Listemiz (Güllü Ayakkabı ürünleri - topuklu ayakkabılar, üretim malzemeleri vb.):
        {urun_listesi}

        Sen Güllü Ayakkabı firması için çalışan bir e-ticaret ürün öneri uzmanısın. 
        Yukarıdaki müşteri profiline göre ve mevcut ürün listemizi dikkate alarak
        bu müşteriye önerebileceğimiz en uygun 5 ürünü JSON formatında listele.
        Her ürün için şunları belirt: 'urun_adi', 'aciklama', 'fiyat_tahmini_tl' (eğer biliniyorsa) ve 'oneri_sebebi'.
        Önerilerini Güllü Ayakkabı'nın topuklu ayakkabı ve ayakkabı malzemeleri (topuk, taban, neolit vb.) ürün gamına uygun yap.
        """
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Sen Güllü Ayakkabı için çalışan bir ürün öneri uzmanısın. Müşteri profiline ve firmanın ürün gamına (topuklu ayakkabılar, ayakkabı üretim malzemeleri) göre en uygun ürünleri JSON formatında öner."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7,
            response_format={"type": "json_object"} # JSON output için
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
            'oneriler': oneriler_json_string, # AI'dan gelen JSON string'i direkt yolla
            'token_usage': {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'estimated_cost_tl': estimated_cost_tl
            }
        })
    except Exception as e:
        logger.error(f"OpenAI ürün önerileri hatası: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@openai_bp.route('/ai/satis-analizi', methods=['POST'])
def satis_analizi():
    """
    Satış verilerini AI ile analiz eder.
    """
    logger.debug(">> satis_analizi fonksiyonu çağrıldı")
    try:
        data = request.get_json()
        if not data or 'satis_verileri' not in data:
            logger.error("Geçersiz veri formatı, 'satis_verileri' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "satis_verileri" alanı gerekli.'}), 400

        satis_verileri = data['satis_verileri']
        logger.debug("Analiz edilecek satış verileri alındı")

        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Sen Güllü Ayakkabı firması için çalışan bir satış analiz uzmanısın. Özellikle topuklu ayakkabı ve ayakkabı üretim malzemeleri satışlarını analiz et, trendleri belirle ve önemli noktaları vurgula."},
                {"role": "user", "content": f"Güllü Ayakkabı Firması'na ait aşağıdaki satış verilerini analiz et. Önemli trendleri, iyi ve kötü giden ürünleri/kategorileri (topuklu ayakkabılar, topuk, taban, neolit) belirle ve somut önerilerde bulun:\n\n{str(satis_verileri)}"}
            ],
            max_tokens=1200, # Daha detaylı analiz için artırıldı
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
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'estimated_cost_tl': estimated_cost_tl
            }
        })
    except Exception as e:
        logger.error(f"OpenAI satış analizi hatası: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@openai_bp.route('/ai/trend-tahmini', methods=['POST'])
def trend_tahmini():
    """
    Satış verilerine göre gelecek dönem satış trendlerini tahmin eder.
    (Daha derin stok tahmini için /ai/stok-tahmini kullanılmalıdır)
    """
    logger.debug(">> trend_tahmini fonksiyonu çağrıldı")
    try:
        data = request.get_json()
        if not data or 'gecmis_veriler' not in data:
            logger.error("Geçersiz veri formatı, 'gecmis_veriler' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "gecmis_veriler" alanı gerekli.'}), 400

        gecmis_veriler = data['gecmis_veriler']
        tahmin_suresi = data.get('tahmin_suresi', 'bir ay')
        logger.debug(f"Trend tahmini için geçmiş veriler alındı. Tahmin süresi: {tahmin_suresi}")

        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Sen Güllü Ayakkabı için çalışan bir satış trendi tahmin uzmanısın. Geçmiş satış verilerine (topuklu ayakkabı ve malzemeleri) bakarak gelecek dönem için genel satış trendlerini tahmin et."},
                {"role": "user", "content": f"Güllü Ayakkabı Firması'na ait aşağıdaki geçmiş satış verilerini analiz ederek gelecek {tahmin_suresi} için genel satış trendlerini tahmin et. Mümkünse sayısal aralıklar ve yüzdelik değişimler belirt. Özellikle topuklu ayakkabı ve ayakkabı malzemeleri (topuk, taban, neolit) trendlerine odaklan.\n\nGeçmiş Veriler:\n{str(gecmis_veriler)}"}
            ],
            max_tokens=1000,
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
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'estimated_cost_tl': estimated_cost_tl
            }
        })
    except Exception as e:
        logger.error(f"OpenAI trend tahmini hatası: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@openai_bp.route('/ai/dashboard-analiz', methods=['POST'])
def dashboard_analiz():
    """
    Dashboard verileri için özet ve öngörüleri oluşturur.
    """
    logger.debug(">> dashboard_analiz fonksiyonu çağrıldı")
    try:
        data = request.get_json()
        if not data or 'dashboard_verileri' not in data:
            logger.error("Geçersiz veri formatı, 'dashboard_verileri' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "dashboard_verileri" alanı gerekli.'}), 400

        dashboard_verileri = data['dashboard_verileri']
        logger.debug("Dashboard verileri analiz için alındı")

        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Sen Güllü Ayakkabı firması için çalışan bir e-ticaret ve satış analiz uzmanısın. Dashboard verilerini analiz ederek önemli içgörüler çıkar ve eylem önerilerinde bulun. Firmanın topuklu ayakkabı ve ayakkabı malzemeleri (topuk, taban, neolit) üretip sattığını unutma."},
                {"role": "user", "content": f"Aşağıdaki Güllü Ayakkabı e-ticaret dashboard verilerini analiz et. Önemli trendleri, anormal değişimleri (hem ayakkabı satışları hem de malzeme satışları/kullanımı için) belirle ve iş sahibine (Abdurrahman'a) somut, uygulanabilir önerilerde bulun:\n\n{str(dashboard_verileri)}"}
            ],
            max_tokens=1200, # Daha detaylı analiz için artırıldı
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
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'estimated_cost_tl': estimated_cost_tl
            }
        })
    except Exception as e:
        logger.error(f"OpenAI dashboard analizi hatası: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# --- YENİ STOK TAHMİNLEME FONKSİYONU ---
@openai_bp.route('/ai/stok-tahmini', methods=['POST'])
def stok_tahmini():
    """
    Güllü Ayakkabı Firması için geçmiş satış, mevcut stok ve ürün bilgilerine dayanarak 
    derinlemesine ve sağlıklı stok tahmini yapar. Hem bitmiş ürünler (topuklu ayakkabı)
    hem de üretim malzemeleri (topuk, taban, neolit/jurdan) için kullanılabilir.
    """
    logger.debug(">> Güllü Ayakkabı - Derinlemesine Stok Tahmini fonksiyonu çağrıldı")

    try:
        data = request.get_json()

        if not data or 'stok_satis_verileri' not in data: # Anahtar adı güncellendi
            logger.error("Geçersiz veri formatı, 'stok_satis_verileri' alanı bulunamadı")
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı. "stok_satis_verileri" alanı gerekli.'}), 400

        stok_satis_verileri = data['stok_satis_verileri']
        tahmin_suresi = data.get('tahmin_suresi', 'gelecek 3 ay')
        ek_bilgiler = data.get('ek_bilgiler', None) # Opsiyonel: genel pazar durumu, planlanan kampanyalar vb.

        logger.debug(f"Stok tahmini için veriler alındı. Tahmin süresi: {tahmin_suresi}")
        logger.debug(f"Alınan Stok/Satış Verileri (ilk 100 karakter): {str(stok_satis_verileri)[:100]}")
        if ek_bilgiler:
            logger.debug(f"Ek Bilgiler (ilk 100 karakter): {str(ek_bilgiler)[:100]}")


        system_prompt_content = f"""
Sen Abdurrahman (Müşir) Bey'in Güllü Ayakkabı Firması için çalışan, alanında uzman bir E-Ticaret Stok Yönetimi ve Talep Tahmin Yapay Zekasısın. 
Firmanın hem topuklu ayakkabı üretip sattığını hem de topuk, taban, neolit (jurdan) gibi ayakkabı üretim malzemelerini hem kendi üretimi için kullandığını hem de dışarıya sattığını çok iyi biliyorsun.
Amacın, sağlanan verilere dayanarak mümkün olan en doğru ve uygulanabilir stok tahminlerini ve yönetim stratejilerini sunmaktır.

Analizlerinde Dikkat Etmen Gerekenler:
1.  **Derinlemesine Talep Tahmini:** Sadece geçmiş verilere değil, olası trendlere, mevsimselliğe (örneğin topuklu ayakkabılar için ilkbahar/yaz yoğunluğu) ve biliniyorsa pazarlama aktivitelerine göre talep tahmini yap.
2.  **Sağlıklı Stok Seviyeleri:** Stoksuz kalma (out-of-stock) durumlarını ve aşırı stok maliyetlerini minimize edecek optimum stok seviyelerini (güvenlik stoğu dahil) öner.
3.  **Ürün Bazlı Detay:** Mümkünse, her bir ürün veya ürün grubu (örneğin, 'stiletto modelleri', '37 numara neolit tabanlar') için ayrı tahminler ve öneriler sun.
4.  **Malzeme Yönetimi:** Ayakkabı üretimi için gereken malzemelerin (topuk, taban, neolit) stoklarını da göz önünde bulundur. Bu malzemelerin hem iç tüketim hem de dış satış taleplerini dengede tutacak öneriler getir.
5.  **E-Ticaret Odaklı:** Özellikle Trendyol gibi platformlardaki satış dinamiklerini, kampanya dönemlerini ve müşteri beklentilerini dikkate alarak stratejiler öner.
6.  **Aksiyon Odaklı Çıktı:** Tahminlerini net rakamlarla (örneğin, 'X modelinden önümüzdeki ay 150 adet satış bekleniyor, Y malzemesinden 500 adet sipariş verilmeli'), grafiksel gösterimler için uygun verilerle (eğer mümkünse JSON formatında özet tablolar) ve net gerekçelerle sun.
7.  **Riskler ve Fırsatlar:** Potansiyel riskleri (tedarik zinciri sorunları, talep düşüşü vb.) ve fırsatları (yeni trendler, artan talep vb.) vurgula.
8.  **Maliyetler:** Stok tutma maliyeti, sipariş maliyeti gibi faktörleri dolaylı da olsa göz önünde bulundurarak öneriler yap.
"""

        user_prompt_parts = [
            f"Merhaba, ben Abdurrahman (Müşir). Güllü Ayakkabı Firması'nın e-ticaret operasyonları için önümüzdeki '{tahmin_suresi}' dönemine yönelik kapsamlı bir stok tahmini ve yönetimi analizi yapmanı istiyorum."
        ]
        user_prompt_parts.append("\nİŞTE ANALİZ İÇİN VERİLER:")
        user_prompt_parts.append("1. Geçmiş Satışlar, Mevcut Stok Durumları ve Ürün/Malzeme Bilgileri:")
        user_prompt_parts.append(f"```json\n{str(stok_satis_verileri)}\n```") # Veriyi JSON bloğu olarak işaretlemek AI'ın daha iyi anlamasına yardımcı olabilir

        if ek_bilgiler:
            user_prompt_parts.append("\n2. Ek Bilgiler (Pazar Durumu, Kampanyalar Vb.):")
            user_prompt_parts.append(f"{str(ek_bilgiler)}")

        user_prompt_parts.append(f"\nLÜTFEN ANALİZİNDE ŞU NOKTALARA ODAKLANARAK '{tahmin_suresi}' İÇİN DETAYLI BİR RAPOR SUN:")
        user_prompt_parts.append("- Ürün ve malzeme bazında talep tahminleri (adet olarak).")
        user_prompt_parts.append("- Her ürün/malzeme için önerilen ideal stok seviyeleri (minimum, maksimum, güvenlik stoğu).")
        user_prompt_parts.append("- Yeniden sipariş noktaları (ROP) ve önerilen sipariş miktarları (EOQ benzeri yaklaşımlar, eğer uygunsa).")
        user_prompt_parts.append("- Stokta kalma süresi yüksek (yavaş hareket eden) veya tükenme riski olan ürünler/malzemeler için uyarılar ve stratejiler.")
        user_prompt_parts.append("- Üretim malzemelerinin (topuk, taban, neolit) hem iç üretim ihtiyacını hem de dış satış potansiyelini dengeleyecek stok planı.")
        user_prompt_parts.append("- Trendyol ve diğer e-ticaret kanalları için özel stok stratejileri (örneğin, kampanya dönemleri için hazırlık).")
        user_prompt_parts.append("- Genel olarak stok devir hızını artırma ve maliyetleri düşürme üzerine somut öneriler.")
        user_prompt_parts.append("\nAnalizini mümkün olduğunca Güllü Ayakkabı'nın özel durumunu (topuklu ayakkabı ve malzeme üretimi/satışı) yansıtacak şekilde yap. Teşekkürler Müşir!")

        user_prompt_content = "\n".join(user_prompt_parts)

        response = client.chat.completions.create(
            model=DEFAULT_MODEL, # gpt-4o kullanılacak
            messages=[
                {"role": "system", "content": system_prompt_content},
                {"role": "user", "content": user_prompt_content}
            ],
            max_tokens=3000, # Detaylı analiz için yüksek tutuldu
            temperature=0.2  # Daha kesin ve analitik sonuçlar için düşük sıcaklık
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
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'estimated_cost_tl': estimated_cost_tl
            }
        })

    except Exception as e:
        logger.error(f"OpenAI Stok Tahmini (Güllü Ayakkabı) hatası: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e), 'trace': traceback.format_exc()}), 500