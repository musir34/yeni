import os
import secrets

# Trendyol API bilgileri
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SUPPLIER_ID = os.getenv("SUPPLIER_ID")  # SATICI ID

missing = [var for var in [API_KEY, API_SECRET, SUPPLIER_ID] if not var]
if missing:
    missing_names = [name for name, value in {"API_KEY": API_KEY, "API_SECRET": API_SECRET, "SUPPLIER_ID": SUPPLIER_ID}.items() if not value]
    missing_str = ", ".join(missing_names)
    raise EnvironmentError(f"Missing required environment variables: {missing_str}")

# Webhook güvenlik anahtarı (eğer çevre değişkeni yoksa rastgele oluştur)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET") or secrets.token_hex(16)

# Trendyol API için temel URL
BASE_URL = "https://api.trendyol.com/sapigw/"

# Webhook URL'leri (kendi domain adresinizle değiştirin)
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "https://your-domain.com")
ORDER_WEBHOOK_URL = f"{WEBHOOK_BASE_URL}/webhook/orders"
PRODUCT_WEBHOOK_URL = f"{WEBHOOK_BASE_URL}/webhook/products"
