# 🆓 Ücretsiz Hava Durumu API - Open-Meteo

## ✅ Tamamen Ücretsiz ve Sınırsız!

**Open-Meteo** kullanılıyor:
- ✅ API key gerektirmez
- ✅ Tamamen ücretsiz
- ✅ Sınırsız kullanım
- ✅ Kayıt gerektirmez
- ✅ Çok hızlı ve güvenilir

## 🚀 Kurulum

**Hiçbir şey yapmanıza gerek yok!**

Kod otomatik olarak çalışır. `.env` dosyasında API key gerekmez.

## 📊 Özellikler

### Sağlanan Bilgiler
- ✅ Gerçek zamanlı sıcaklık
- ✅ Hissedilen sıcaklık
- ✅ Nem oranı (%)
- ✅ Basınç (hPa)
- ✅ Rüzgar hızı (km/h)
- ✅ Rüzgar yönü (K/D/G/B)
- ✅ Bulutluluk oranı (%)
- ✅ Hava durumu açıklaması (Türkçe)
- ✅ Emoji ikon

### Desteklenen Hava Durumları
- ☀️ Açık Hava
- 🌤️ Az Bulutlu
- ⛅ Parçalı Bulutlu
- ☁️ Kapalı Hava
- 🌫️ Sisli
- 🌦️ Çiseleyen
- 🌧️ Yağmurlu
- ⛈️ Fırtınalı
- ❄️ Karlı

## 🌐 API Bilgileri

**Endpoint:** https://api.open-meteo.com/v1/forecast

**İstanbul Koordinatları:**
- Enlem: 41.0082
- Boylam: 28.9784

**Örnek İstek:**
```
https://api.open-meteo.com/v1/forecast?latitude=41.0082&longitude=28.9784&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,cloud_cover,pressure_msl,surface_pressure,wind_speed_10m,wind_direction_10m&timezone=Europe/Istanbul&forecast_days=1
```

## 🧪 Test Etme

Tarayıcınızda yukarıdaki URL'yi açarak test edebilirsiniz. JSON formatında hava durumu bilgisi göreceksiniz.

## 📝 Kullanım

```python
from weather_service import get_weather_info

# Hava durumu bilgisi al
weather = get_weather_info()

print(f"🌡️ Sıcaklık: {weather['temperature']}°C")
print(f"💧 Nem: {weather['humidity']}%")
print(f"💨 Rüzgar: {weather['wind_speed']} km/h {weather['wind_direction']}")
print(f"{weather['icon']} {weather['description']}")
```

## 🔄 Önceki API'den Farklar

### OpenWeatherMap (Eski - Kaldırıldı)
- ❌ API key gerekiyordu
- ❌ 60 çağrı/dakika limiti
- ❌ Kayıt gerekiyordu
- ❌ 401 Unauthorized hatası alıyordunuz

### Open-Meteo (Yeni - Aktif)
- ✅ API key gerektirmez
- ✅ Sınırsız kullanım
- ✅ Kayıt gerektirmez
- ✅ Hemen çalışır

## 📈 Önbellekleme

5 dakikalık önbellekleme aktif:
- İlk istek → API'ye gider
- Sonraki istekler (5 dk içinde) → Cache'den gelir
- 5 dk sonra → Tekrar API'ye gider

Bu sayede hem hızlı hem de API'ye yük bindirmiyoruz.

## 🌍 Başka Şehirler

Farklı şehir için koordinatları değiştirin:

```python
# weather_service.py
ISTANBUL_LAT = 41.0082
ISTANBUL_LON = 28.9784

# Ankara için:
# ANKARA_LAT = 39.9334
# ANKARA_LON = 32.8597
```

## 🔗 Faydalı Linkler

- Open-Meteo Dökümantasyon: https://open-meteo.com/en/docs
- API Explorer: https://open-meteo.com/en/docs#api-documentation
- WMO Weather Codes: https://open-meteo.com/en/docs#weathervariables

## 💡 Avantajlar

1. **Ücretsiz:** Tamamen ücretsiz, hiçbir ödeme yok
2. **API Key Yok:** Hiçbir kayıt/key gerekmez
3. **Sınırsız:** Hiçbir limit yok
4. **Hızlı:** Çok hızlı yanıt süreleri
5. **Güvenilir:** Yüksek uptime garantisi
6. **Açık Kaynak:** Açık kaynak proje
7. **Gizlilik:** Veri toplamaz

## ✅ Sonuç

Artık tamamen ücretsiz ve sınırsız hava durumu servisi kullanıyorsunuz!

**Hiçbir şey yapmanıza gerek yok, sadece uygulamayı yeniden başlatın.**

Sunucu terminalinde şu mesajı göreceksiniz:
```
INFO - Hava durumu başarıyla alındı (Open-Meteo - Ücretsiz)
```
