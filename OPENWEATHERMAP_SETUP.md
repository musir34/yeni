# OpenWeatherMap API Kurulum Rehberi

## 📍 İstanbul Lokasyon Seçimi

### Şu Anda Aktif Yöntem: LAT/LON (Koordinat) ✅

Kodunuzda **koordinat bazlı** sorgulama kullanılıyor. Bu **en kesin yöntemdir**.

```python
# weather_service.py dosyasında
ISTANBUL_LAT = 41.0082  # İstanbul Enlem
ISTANBUL_LON = 28.9784  # İstanbul Boylam

params = {
    "lat": ISTANBUL_LAT,
    "lon": ISTANBUL_LON,
    "appid": WEATHER_API_KEY,
    "units": "metric",
    "lang": "tr"
}
```

## 🔧 3 Farklı Lokasyon Seçim Yöntemi

### 1️⃣ Koordinat (LAT/LON) - ÖNERİLEN ✅

**Avantajları:**
- ✅ En kesin yöntem
- ✅ Yanlış şehir seçme riski YOK
- ✅ Tam olarak istediğiniz konumu seçer

**Kullanımı:**
```python
params = {
    "lat": 41.0082,
    "lon": 28.9784,
    "appid": API_KEY,
    "units": "metric",
    "lang": "tr"
}
```

**Diğer Şehirler için Koordinatlar:**
- Ankara: lat=39.9334, lon=32.8597
- İzmir: lat=38.4237, lon=27.1428
- Antalya: lat=36.8969, lon=30.7133

### 2️⃣ City ID - HIZLI VE KESİN

**Avantajları:**
- ✅ Hızlı
- ✅ OpenWeatherMap'in resmi ID sistemi
- ✅ Yanlış şehir seçme riski YOK

**Kullanımı:**
```python
params = {
    "id": 745044,  # İstanbul City ID
    "appid": API_KEY,
    "units": "metric",
    "lang": "tr"
}
```

**City ID Bulma:**
1. http://bulk.openweathermap.org/sample/city.list.json.gz
2. İndir ve aç
3. İstanbul'u bul → City ID: 745044

**Popüler Türk Şehirleri:**
- İstanbul: 745044
- Ankara: 323786
- İzmir: 311046
- Bursa: 750269
- Antalya: 323777

### 3️⃣ Şehir Adı (q Parameter) - BASİT AMA RİSKLİ ⚠️

**Dezavantajları:**
- ⚠️ Bazen yanlış şehir seçebilir
- ⚠️ Aynı isimde başka şehirler varsa karışabilir

**Kullanımı:**
```python
params = {
    "q": "Istanbul,TR",  # TR: Türkiye ülke kodu
    "appid": API_KEY,
    "units": "metric",
    "lang": "tr"
}
```

## 🔑 API Key Alma

### Adım 1: Kayıt Olun
1. https://openweathermap.org/ adresine gidin
2. Sağ üstte **Sign In** → **Create an Account**
3. Email ve şifre ile kayıt olun

### Adım 2: API Key Alın
1. Giriş yapın
2. Profil → **API keys** sekmesi
3. **Create Key** veya varsayılan key'i kopyalayın
4. Key örneği: `35f303ea3115545f81f839ee584e1269`

### Adım 3: .env Dosyasına Ekleyin

`.env` dosyasını açın (veya oluşturun):
```env
# Hava Durumu API
OPENWEATHER_API_KEY=35f303ea3115545f81f839ee584e1269
```

**Önemli:** `.env` dosyasını Git'e eklemeyin!
```bash
# .gitignore dosyasına ekleyin
.env
```

## 📊 API Limitleri

### Ücretsiz Plan (Free Tier)
- ✅ 60 çağrı/dakika
- ✅ 1,000,000 çağrı/ay
- ✅ Yeterli (5 dakika cache kullanıyoruz)

### Ücretli Planlar
Gerek yok! Ücretsiz plan yeterli.

## 🧪 Test Etme

### Terminal'de Test
```bash
# Python ile test
python -c "from weather_service import get_weather_info; import json; w=get_weather_info(); print(json.dumps(w, indent=2, default=str))"
```

### Tarayıcıda Test
API key'inizi test edin:
```
https://api.openweathermap.org/data/2.5/weather?lat=41.0082&lon=28.9784&appid=35f303ea3115545f81f839ee584e1269&units=metric&lang=tr
```

**Beklenen Sonuç:**
```json
{
  "coord": {"lon": 28.9784, "lat": 41.0082},
  "weather": [
    {
      "id": 800,
      "main": "Clear",
      "description": "açık",
      "icon": "01d"
    }
  ],
  "main": {
    "temp": 15.5,
    "feels_like": 14.8,
    "humidity": 65,
    "pressure": 1013
  },
  "wind": {
    "speed": 3.5,
    "deg": 180
  },
  "name": "Istanbul"
}
```

## 🔄 Yöntem Değiştirme

### LAT/LON'dan City ID'ye Geçiş

`weather_service.py` dosyasında:

```python
def fetch_weather_data():
    # Bu kısmı yorum satırı yap:
    # params = {
    #     "lat": ISTANBUL_LAT,
    #     "lon": ISTANBUL_LON,
    #     ...
    # }
    
    # Bu kısmın yorum satırını kaldır:
    params = {
        "id": ISTANBUL_CITY_ID,
        "appid": WEATHER_API_KEY,
        "units": "metric",
        "lang": "tr"
    }
```

### LAT/LON'dan Şehir Adına Geçiş

```python
def fetch_weather_data():
    # Bu kısmı yorum satırı yap:
    # params = {
    #     "lat": ISTANBUL_LAT,
    #     "lon": ISTANBUL_LON,
    #     ...
    # }
    
    # Bu kısmın yorum satırını kaldır:
    params = {
        "q": "Istanbul,TR",
        "appid": WEATHER_API_KEY,
        "units": "metric",
        "lang": "tr"
    }
```

## ❌ Sorun Giderme

### Hata: "API key bulunamadı"
```
Hava durumu API key bulunamadı
```

**Çözüm:**
1. `.env` dosyasında `OPENWEATHER_API_KEY` var mı?
2. Doğru yazıldı mı? (büyük/küçük harf önemli)
3. Sunucuyu yeniden başlattınız mı?

### Hata: "401 Unauthorized"
```
Hava durumu API hatası: 401 Client Error
```

**Çözüm:**
1. API key'iniz doğru mu?
2. API key aktif mi? (Yeni key'ler 10 dakika sonra aktif olur)
3. Tarayıcıda test URL'ini deneyin

### Hata: "429 Too Many Requests"
```
Hava durumu API hatası: 429 Client Error
```

**Çözüm:**
- Limit aşıldı (60/dakika)
- 5 dakika cache mekanizması çalışıyor mu?
- Birkaç dakika bekleyin

### Hata: "Yanlış Şehir Geliyor"
```
İstanbul yerine başka şehir bilgisi geliyor
```

**Çözüm:**
- Şehir adı yöntemi (q=Istanbul) yerine
- LAT/LON veya City ID kullanın
- Kodda zaten LAT/LON aktif ✅

## 📝 Notlar

- ✅ **LAT/LON yöntemi şu anda aktif ve önerilen yöntemdir**
- ✅ API key'ler 10 dakika sonra aktif olur
- ✅ Ücretsiz plan yeterlidir
- ✅ 5 dakikalık cache sayesinde limit sorunu yok
- ✅ API çalışmazsa uygulama normal devam eder

## 🌍 Farklı Şehirler

Başka bir şehir için hava durumu göstermek isterseniz:

```python
# weather_service.py dosyasında
# İstanbul koordinatları:
ISTANBUL_LAT = 41.0082
ISTANBUL_LON = 28.9784

# Ankara için değiştirin:
ANKARA_LAT = 39.9334
ANKARA_LON = 32.8597
```

Veya dinamik olarak:

```python
def fetch_weather_data(lat=41.0082, lon=28.9784):
    params = {
        "lat": lat,
        "lon": lon,
        ...
    }
```

## 🔗 Faydalı Linkler

- API Dokümantasyonu: https://openweathermap.org/api
- City ID Listesi: http://bulk.openweathermap.org/sample/
- API Key Yönetimi: https://home.openweathermap.org/api_keys
- Fiyatlandırma: https://openweathermap.org/price
