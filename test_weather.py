#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hava Durumu API Test Scripti
Gerçek zamanlı hava durumu verilerini gösterir
"""

from weather_service import fetch_weather_data, get_weather_info, get_weather_description_tr, get_weather_icon_emoji

print("=" * 60)
print("🌤️  HAVA DURUMU API TEST - İSTANBUL")
print("=" * 60)

# Ham API verisini çek
print("\n1️⃣  Open-Meteo API'den ham veri çekiliyor...")
raw_data = fetch_weather_data()

if raw_data and "current" in raw_data:
    current = raw_data["current"]
    print("\n✅ API Yanıtı (Ham Veri):")
    print("-" * 60)
    print(f"🌡️  Sıcaklık: {current.get('temperature_2m')}°C")
    print(f"🤚 Hissedilen: {current.get('apparent_temperature')}°C")
    print(f"💧 Nem: {current.get('relative_humidity_2m')}%")
    print(f"☁️  Bulut Örtüsü: {current.get('cloud_cover')}%")
    print(f"💨 Rüzgar Hızı: {current.get('wind_speed_10m')} km/h")
    print(f"🌪️  Rüzgar Şiddeti: {current.get('wind_gusts_10m')} km/h")
    print(f"🧭 Rüzgar Yönü: {current.get('wind_direction_10m')}°")
    print(f"📊 Basınç: {current.get('pressure_msl')} hPa")
    print(f"🌧️  Yağış: {current.get('precipitation', 0)} mm")
    print(f"🔢 Hava Durumu Kodu: {current.get('weather_code')}")
    print(f"☀️  Gündüz mü?: {current.get('is_day')} (1=Gündüz, 0=Gece)")
    
    # Kod açıklaması
    weather_code = current.get('weather_code', 0)
    is_day = bool(current.get('is_day', 1))
    print(f"\n📝 Hava Durumu Açıklaması: {get_weather_description_tr(weather_code)}")
    print(f"🎨 İkon: {get_weather_icon_emoji(weather_code, is_day)}")
else:
    print("\n❌ API'den veri alınamadı!")

# İşlenmiş veriyi göster
print("\n" + "=" * 60)
print("2️⃣  İşlenmiş Hava Durumu Bilgisi:")
print("=" * 60)

weather_info = get_weather_info()

if weather_info:
    print(f"\n{weather_info['icon']}  {weather_info['description']}")
    print(f"🌡️  Sıcaklık: {weather_info['temperature']}°C")
    print(f"🤚 Hissedilen: {weather_info['feels_like']}°C")
    print(f"💧 Nem: {weather_info['humidity']}%")
    print(f"☁️  Bulutluluk: {weather_info['clouds']}%")
    print(f"💨 Rüzgar: {weather_info['wind_speed']} km/h {weather_info['wind_direction']}")
    if weather_info.get('wind_gusts'):
        print(f"🌪️  Rüzgar Şiddeti: {weather_info['wind_gusts']} km/h")
    print(f"📊 Basınç: {weather_info['pressure']} hPa")
    print(f"🌆 Şehir: {weather_info['city']}")
    print(f"🌞 Gündüz mü?: {'Evet' if weather_info['is_day'] else 'Hayır'}")
    print(f"🔢 Hava Kodu: {weather_info.get('weather_code', 'Bilinmiyor')}")
    print(f"🕐 Son Güncelleme: {weather_info['last_update'].strftime('%H:%M:%S')}")
else:
    print("\n❌ Hava durumu bilgisi alınamadı!")

print("\n" + "=" * 60)
print("✨ Test tamamlandı!")
print("=" * 60)
