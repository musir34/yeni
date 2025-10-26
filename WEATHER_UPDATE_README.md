# Hava Durumu ve Saat Güncellemesi

## Yapılan Değişiklikler

### 1. Yeni Hava Durumu Servisi (`weather_service.py`)
OpenWeatherMap API entegrasyonu ile detaylı hava durumu bilgisi:
- ✅ Gerçek zamanlı İstanbul hava durumu
- ✅ Sıcaklık (hissedilen sıcaklık dahil)
- ✅ Nem, basınç, görüş mesafesi
- ✅ Rüzgar hızı ve yönü
- ✅ Gün doğumu/batımı
- ✅ Emoji ile görsel hava durumu ikonları
- ✅ 5 dakikalık önbellekleme (API limiti için)

### 2. Türkiye Saati (İstanbul) Desteği
Tüm uygulama artık **Türkiye/İstanbul** saat dilimini kullanıyor:
- ✅ `get_istanbul_time()` fonksiyonu ile tutarlı saat
- ✅ Veritabanı sorgularında UTC->IST dönüşümü
- ✅ Tüm tarih/saat gösterimlerinde IST kullanımı

### 3. Güncellenmiş Sayfalar

#### `home.py` (Anasayfa)
- Hava durumu servisi entegrasyonu
- İstanbul saati ile tüm hesaplamalar
- Template'e hava durumu bilgisi gönderimi

#### `siparis_hazirla.py` (Sipariş Hazırlama)
- Hava durumu servisi entegrasyonu
- İstanbul saati ile sipariş zamanlamaları
- Geriye kalan süre hesaplamaları düzeltildi

#### `templates/home.html`
Kullanıcı bilgi kutusuna eklenenler:
- 🌡️ Anlık hava durumu (emoji + açıklama)
- 🌡️ Sıcaklık ve hissedilen sıcaklık
- 💨 Rüzgar hızı ve yönü
- 💧 Nem oranı
- 👁️ Görüş mesafesi
- 🕐 Türkiye saati (gün/ay/yıl/saat)

Geliştirilmiş canvas animasyonu:
- Gün/gece döngüsüne göre gradient gökyüzü
- Şafak ve gün batımı renkleri
- Güneş ışınları efekti
- Gelişmiş ay efektleri (kraterler, ışık halkası)
- Daha fazla yıldız (150 adet)
- Daha fazla bulut (8 adet) ve şeffaflık efektleri

#### `templates/siparis_hazirla.html`
- Home.html ile aynı hava durumu ve saat gösterimi
- Aynı gelişmiş canvas animasyonu
- Kullanıcı bilgi kutusu genişletildi

### 4. API Yapılandırması

#### OpenWeatherMap API Anahtarı
`.env` dosyasına eklenmelidir:
```env
OPENWEATHER_API_KEY=your_api_key_here
```

**Ücretsiz API Anahtarı Alma:**
1. https://openweathermap.org/ adresine git
2. Sign up / Create Account
3. API Keys sekmesinden key'i kopyala
4. `.env` dosyasına ekle

**Limitler (Ücretsiz Plan):**
- 60 çağrı/dakika
- 1,000,000 çağrı/ay
- Bu yüzden 5 dakikalık cache kullanıyoruz

### 5. Yedekler
Eğer API key yoksa veya API çalışmazsa:
- Varsayılan "Bilinmiyor" durumu gösterilir
- Uygulama normal çalışmaya devam eder
- Sadece hava durumu bilgisi gösterilmez

## Kurulum

1. Weather service için gerekli paket zaten var (requests):
```bash
pip install requests
```

2. `.env` dosyasına API key ekle:
```env
OPENWEATHER_API_KEY=your_openweathermap_api_key
```

3. Uygulamayı yeniden başlat

## Kullanım

### Hava Durumu Bilgisi Alma
```python
from weather_service import get_weather_info, get_istanbul_time

# Hava durumu bilgisi
weather = get_weather_info()
print(f"Sıcaklık: {weather['temperature']}°C")
print(f"Durum: {weather['description']}")
print(f"Nem: {weather['humidity']}%")

# İstanbul saati
now = get_istanbul_time()
print(f"İstanbul Saati: {now}")
```

### Template'de Kullanım
```python
@app.route("/")
def index():
    weather = get_weather_info()
    current_time = get_istanbul_time()
    return render_template("page.html", 
                         weather=weather, 
                         current_time=current_time)
```

```html
<!-- Template'de -->
{% if weather %}
  <div>{{ weather.icon }} {{ weather.description }}</div>
  <div>{{ weather.temperature }}°C</div>
  <div>Nem: {{ weather.humidity }}%</div>
{% endif %}

{% if current_time %}
  <div>{{ current_time.strftime('%d %B %Y, %A - %H:%M:%S') }}</div>
{% endif %}
```

## Özellikler

### Hava Durumu Bilgileri
```python
{
    "temperature": 15.5,          # Sıcaklık (°C)
    "feels_like": 14.2,           # Hissedilen (°C)
    "humidity": 65,               # Nem (%)
    "pressure": 1013,             # Basınç (hPa)
    "wind_speed": 12.5,           # Rüzgar (km/h)
    "wind_direction": "KB",       # Yön (K/D/G/B)
    "description": "Az Bulutlu",  # Türkçe açıklama
    "icon": "🌤️",                # Emoji
    "visibility": 10.0,           # Görüş (km)
    "clouds": 25,                 # Bulut (%)
    "sunrise": "06:45",           # Gün doğumu
    "sunset": "18:30",            # Gün batımı
    "is_day": True,               # Gündüz mü?
    "city": "İstanbul",           # Şehir
    "last_update": datetime(...)  # Güncelleme zamanı
}
```

### Saat Dilimleri
- **Veritabanı**: UTC (varsayılan)
- **Uygulama**: Europe/Istanbul (IST)
- **Dönüşüm**: Otomatik (weather_service ve home.py'de)

## Sorun Giderme

### API Hatası
```
Hava durumu bilgisi alınamadı
```
- API key'in doğru olduğundan emin ol
- İnternet bağlantısını kontrol et
- API limitini aşmadığından emin ol (5dk cache kullanıyoruz)

### Saat Farkı
Eğer hala saat farkı varsa:
1. Sunucu saat dilimini kontrol et: `timedatectl` (Linux)
2. Python timezone ayarını kontrol et
3. Veritabanı timestamp'larının UTC olduğundan emin ol

## Test

```python
# Terminal'de test
python -c "from weather_service import get_weather_info, get_istanbul_time; import json; print(json.dumps(get_weather_info(), indent=2, default=str)); print('Saat:', get_istanbul_time())"
```

## Notlar

- ✅ Tüm saatler artık Türkiye/İstanbul diliminde
- ✅ 3 saatlik fark sorunu çözüldü
- ✅ Hava durumu 5 dakikada bir güncellenir
- ✅ API çalışmazsa uygulama normal devam eder
- ✅ Canvas animasyonları geliştirildi (gradient, ışık efektleri)
- ✅ Mobil uyumlu tasarım korundu
