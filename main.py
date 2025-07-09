import os
import requests
import base64
import json

# 1. Replit Secrets'tan API bilgilerini çekiyoruz
# Bu bilgiler kodda görünmez, os.getenv ile güvenli şekilde alınır.

seller_id = "481286"           
api_key = "9lFDKnBOB7oZFxtqU4Jy" 
api_secret = "Z6YkYJctIPBSwoThjiDS"

# Bilgiler eksikse hata verip durduralım
if not all([seller_id, api_key, api_secret]):
    print("HATA: Lütfen SELLER_ID, API_KEY, ve API_SECRET bilgilerini Replit Secrets'a eklediğinden emin ol.")
    exit()

# 2. Trendyol API için gerekli URL ve başlıkları (headers) hazırlıyoruz
# URL'deki {sellerId} kısmını kendi ID'mizle değiştiriyoruz
url = f"https://apigw.trendyol.com/integration/product/sellers/{seller_id}/products"

# Trendyol, Basic Authentication kullanıyor. API Key ve Secret'ı birleştirip base64 ile şifreliyoruz.
auth_str = f"{api_key}:{api_secret}"
encoded_auth_str = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')

headers = {
    'Authorization': f'Basic {encoded_auth_str}',
    'User-Agent': f'{seller_id} - SelfIntegration'
}

# 3. API'ye göndereceğimiz filtreleme parametreleri
# Örnek olarak sadece onaylanmış (approved=true) ve ilk 5 (size=5) ürünü istiyoruz.
params = {
    'approved': 'true',
    'size': 5 
}

# 4. API'ye isteği gönder ve sonucu ekrana yazdır
print("Trendyol API'ye bağlanılıyor...")

try:
    # GET isteğini atıyoruz
    response = requests.get(url, headers=headers, params=params)

    # Eğer API'den 4xx veya 5xx gibi bir hata kodu dönerse, program hata verip durur.
    response.raise_for_status()

    # İstek başarılıysa (200 OK), gelen JSON verisini al
    product_data = response.json()

    print("\n✅ Bağlantı Başarılı! Gelen ürün bilgileri:\n")
    # Gelen JSON'ı daha okunaklı şekilde yazdırıyoruz
    print(json.dumps(product_data, indent=2, ensure_ascii=False))

except requests.exceptions.HTTPError as errh:
    print(f"❌ HTTP Hatası: {errh}")
    print(f"Hata Detayı: {response.text}")
except requests.exceptions.ConnectionError as errc:
    print(f"❌ Bağlantı Hatası: {errc}")
except requests.exceptions.Timeout as errt:
    print(f"❌ Zaman Aşımı Hatası: {errt}")
except requests.exceptions.RequestException as err:
    print(f"❌ Bir Hata Oluştu: {err}")