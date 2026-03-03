# -*- coding: utf-8 -*-
"""
Hava Durumu Servisi
Open-Meteo API kullanarak İstanbul için detaylı hava durumu bilgisi sağlar
TAMAMEN ÜCRETSİZ - API KEY GEREKTİRMEZ
"""

import os
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from logger_config import app_logger as logger

# İstanbul timezone
IST = ZoneInfo("Europe/Istanbul")

# Open-Meteo API (Tamamen ücretsiz, API key gerektirmez!)
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"

# Başakşehir İkitelli OSB koordinatları
ISTANBUL_LAT = 41.0685  # Enlem (Başakşehir İkitelli)
ISTANBUL_LON = 28.7856  # Boylam (Başakşehir İkitelli)

# Cache mekanizması (5 dakikada bir güncellenir)
_weather_cache = {
    "data": None,
    "last_update": None
}

def get_istanbul_time():
    """İstanbul saatini döner"""
    return datetime.now(IST)


def get_weather_icon_emoji(weather_code, is_day=True):
    """
    Hava durumu koduna göre emoji döner
    Open-Meteo WMO Weather Codes
    https://open-meteo.com/en/docs
    """
    # WMO Weather interpretation codes (WW)
    if weather_code == 0:  # Clear sky
        return "☀️" if is_day else "🌙"
    elif weather_code in [1, 2, 3]:  # Mainly clear, partly cloudy, overcast
        if weather_code == 1:
            return "🌤️" if is_day else "☁️"
        elif weather_code == 2:
            return "⛅"
        else:
            return "☁️"
    elif weather_code in [45, 48]:  # Fog
        return "🌫️"
    elif weather_code in [51, 53, 55]:  # Drizzle
        return "🌦️"
    elif weather_code in [61, 63, 65]:  # Rain
        if weather_code == 61:
            return "🌧️"
        else:
            return "⛈️"
    elif weather_code in [71, 73, 75, 77]:  # Snow
        return "❄️"
    elif weather_code in [80, 81, 82]:  # Rain showers
        return "🌧️"
    elif weather_code in [85, 86]:  # Snow showers
        return "❄️"
    elif weather_code in [95, 96, 99]:  # Thunderstorm
        return "⛈️"
    else:
        return "🌡️"


def get_weather_description_tr(weather_code):
    """
    WMO Weather Code'u Türkçe açıklamaya çevirir
    Open-Meteo WMO kodları
    """
    descriptions = {
        0: "Açık Hava",
        1: "Az Bulutlu",
        2: "Parçalı Bulutlu",
        3: "Kapalı Hava",
        45: "Sisli",
        48: "Dondurucu Sis",
        51: "Hafif Çiseleyen",
        53: "Çiseleyen",
        55: "Yoğun Çiseleyen",
        61: "Hafif Yağmur",
        63: "Yağmurlu",
        65: "Şiddetli Yağmur",
        71: "Hafif Kar",
        73: "Karlı",
        75: "Yoğun Kar",
        77: "Kar Taneleri",
        80: "Hafif Sağanak",
        81: "Sağanak Yağışlı",
        82: "Şiddetli Sağanak",
        85: "Hafif Kar Sağanağı",
        86: "Yoğun Kar Sağanağı",
        95: "Fırtınalı",
        96: "Dolu ile Fırtına",
        99: "Şiddetli Dolu Fırtınası"
    }
    
    return descriptions.get(weather_code, "Bilinmiyor")


def fetch_weather_data():
    """
    Open-Meteo API'den hava durumu verisini çeker
    TAMAMEN ÜCRETSİZ - API KEY GEREKTİRMEZ
    """
    try:
        # Open-Meteo API parametreleri (API key gerektirmez!)
        params = {
            "latitude": ISTANBUL_LAT,
            "longitude": ISTANBUL_LON,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,cloud_cover,pressure_msl,surface_pressure,wind_speed_10m,wind_direction_10m,is_day,wind_gusts_10m",
            "timezone": "Europe/Istanbul",
            "forecast_days": 1
        }
        
        response = requests.get(WEATHER_API_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        logger.info(f"Hava durumu başarıyla alındı (Open-Meteo - Ücretsiz)")
        return data
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Hava durumu API hatası: {e}")
        return None
    except Exception as e:
        logger.error(f"Hava durumu verisi işlenirken hata: {e}")
        return None


def get_weather_info():
    """
    Önbellekli hava durumu bilgisini döner
    5 dakikada bir güncellenir
    """
    now = get_istanbul_time()
    
    # Cache kontrolü
    if _weather_cache["data"] and _weather_cache["last_update"]:
        time_diff = now - _weather_cache["last_update"]
        if time_diff < timedelta(minutes=5):
            return _weather_cache["data"]
    
    # API'den yeni veri çek
    raw_data = fetch_weather_data()
    
    if not raw_data:
        # API başarısız olursa varsayılan değerler döner
        return {
            "temperature": None,
            "feels_like": None,
            "humidity": None,
            "pressure": None,
            "wind_speed": None,
            "wind_direction": None,
            "description": "Bilinmiyor",
            "icon": "🌡️",
            "visibility": None,
            "clouds": None,
            "sunrise": None,
            "sunset": None,
            "is_day": True,
            "city": "Başakşehir İkitelli",
            "last_update": now
        }
    
    try:
        # Open-Meteo API yanıtından gerekli bilgileri çıkar
        current = raw_data.get("current", {})
        
        # API'den gün/gece bilgisi al (1=gündüz, 0=gece)
        is_day = bool(current.get("is_day", 1))
        
        # Rüzgar yönü
        wind_deg = current.get("wind_direction_10m", 0)
        directions = ["K", "KD", "D", "GD", "G", "GB", "B", "KB"]
        wind_direction = directions[int((wind_deg + 22.5) / 45) % 8]
        
        # Hava durumu kodu
        weather_code = current.get("weather_code", 0)
        
        # Rüzgar hızı ve şiddetini al
        wind_speed = round(current.get("wind_speed_10m", 0), 1)
        wind_gusts = round(current.get("wind_gusts_10m", 0), 1) if current.get("wind_gusts_10m") else None
        
        weather_info = {
            "temperature": round(current.get("temperature_2m", 0), 1),
            "feels_like": round(current.get("apparent_temperature", 0), 1),
            "humidity": current.get("relative_humidity_2m", 0),
            "pressure": round(current.get("pressure_msl", 0)),
            "wind_speed": wind_speed,
            "wind_gusts": wind_gusts,
            "wind_direction": wind_direction,
            "wind_direction_deg": wind_deg,  # Derece cinsinden rüzgar yönü (animasyon için)
            "description": get_weather_description_tr(weather_code),
            "icon": get_weather_icon_emoji(weather_code, is_day),
            "visibility": 10.0,  # Open-Meteo visibility vermez, varsayılan
            "clouds": current.get("cloud_cover", 0),
            "sunrise": None,  # Open-Meteo temel API'de yok
            "sunset": None,
            "is_day": is_day,
            "city": "Başakşehir İkitelli",
            "last_update": now,
            "weather_code": weather_code  # Debug için
        }
        
        # Cache'e kaydet
        _weather_cache["data"] = weather_info
        _weather_cache["last_update"] = now
        
        return weather_info
        
    except Exception as e:
        logger.error(f"Hava durumu verisi işlenirken hata: {e}")
        return _weather_cache.get("data") or {
            "temperature": None,
            "description": "Hata",
            "icon": "❌",
            "is_day": True,
            "city": "Başakşehir İkitelli",
            "last_update": now
        }


def format_weather_info(weather_info):
    """Hava durumu bilgisini formatlanmış string olarak döner"""
    if not weather_info or weather_info.get("temperature") is None:
        return "Hava durumu bilgisi alınamadı"
    
    parts = [
        f"{weather_info['icon']} {weather_info['description']}",
        f"{weather_info['temperature']}°C",
    ]
    
    if weather_info.get("feels_like"):
        parts.append(f"(Hissedilen: {weather_info['feels_like']}°C)")
    
    return " • ".join(parts)
