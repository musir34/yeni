import os
import requests
import base64
import time
import logging

# --- AYARLAR BÖLÜMÜ ---
# Bilgileri Replit'in "Secrets" (Kilit ikonu) bölümünden otomatik okuyoruz.
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SUPPLIER_ID = os.getenv("SUPPLIER_ID")

# Loglama ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("replit_urun_test.log"),
        logging.StreamHandler()
    ]
)

# --- ANA FONKSİYONLAR ---

def get_products_from_trendyol():
    """Trendyol API'sine bağlanıp ürünleri çekmeye çalışan ana fonksiyon."""

    if not all([API_KEY, API_SECRET, SUPPLIER_ID]):
        logging.error("API Bilgileri eksik! Lütfen Replit'in Secrets (kilit ikonu) bölümünü kontrol et.")
        return None

    # Ürünleri çekmek için kullandığımız o meşhur API adresi
    url = f"https://api.trendyol.com/integration/product/sellers/{SUPPLIER_ID}/products"

    auth_str = f"{API_KEY}:{API_SECRET}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()

    headers = {
        "Authorization": f"Basic {encoded_auth}",
        "User-Agent": f"GulluAyakkabi_{SUPPLIER_ID}/1.3_ReplitTest"
    }

    params = {'page': 0, 'size': 50}

    logging.info("Replit üzerinden Trendyol'dan ÜRÜNLERİ çekme işlemi başlatılıyor...")
    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)

        if response.status_code == 200:
            logging.info("ÜRÜNLER BAŞARIYLA ÇEKİLDİ! (Replit)")
            return response.json()
        else:
            # Burası çok önemli, bakalım yine 556 hatası alacak mıyız?
            logging.error(f"API Hatası (Replit - Ürünler): Status Kodu: {response.status_code}, Cevap: {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        logging.error(f"Ağ Hatası (Replit - Ürünler): {e}")
        return None

# --- PROGRAMIN BAŞLANGIÇ NOKTASI ---

if __name__ == "__main__":
    products = get_products_from_trendyol()
    if products:
        total_products = products.get('totalElements', 0)
        logging.info(f"Toplam {total_products} ürün bulundu.")
    else:
        logging.warning("Ürünler çekilemedi. Trendyol API'sinin ürünler servisinde sorun devam ediyor olabilir.")