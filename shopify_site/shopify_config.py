"""
Shopify Admin API konfigürasyonu.
Yeni API: client_id + client_secret ile OAuth token alınır.
"""

import os
import logging
import threading
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class ShopifyConfig:
    """Shopify Admin API ayarları — OAuth client credentials."""

    STORE_DOMAIN = (
        os.getenv("SHOPIFY_STORE_DOMAIN")
        or os.getenv("SHOPIFY_SHOP_DOMAIN")
        or ""
    ).strip().rstrip("/")

    CLIENT_ID = (
        os.getenv("SHOPIFY_CLIENT_ID") or ""
    ).strip()

    CLIENT_SECRET = (
        os.getenv("SHOPIFY_CLIENT_SECRET") or ""
    ).strip()

    # Eski yöntemle de çalışsın (varsa doğrudan token)
    _STATIC_TOKEN = (
        os.getenv("SHOPIFY_ACCESS_TOKEN")
        or os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN")
        or os.getenv("SHOPIFY_TOKEN")
        or ""
    ).strip()

    API_VERSION = (os.getenv("SHOPIFY_API_VERSION") or "2026-01").strip()
    TIMEOUT = int(os.getenv("SHOPIFY_TIMEOUT", "30"))
    LOCATION_ID = (os.getenv("SHOPIFY_LOCATION_ID") or "").strip()

    # Cached token
    _access_token: str = ""
    _token_expires_at: float = 0
    _token_lock = threading.Lock()

    @classmethod
    def is_configured(cls) -> bool:
        has_domain = bool(cls.STORE_DOMAIN)
        has_credentials = bool(cls.CLIENT_ID and cls.CLIENT_SECRET)
        has_static = bool(cls._STATIC_TOKEN)
        return has_domain and (has_credentials or has_static)

    @classmethod
    def normalized_store_domain(cls) -> str:
        domain = cls.STORE_DOMAIN.replace("https://", "").replace("http://", "")
        return domain.rstrip("/")

    @classmethod
    def _obtain_token(cls) -> str:
        """client_id + client_secret ile access token al."""
        import time
        import requests as req

        url = f"https://{cls.normalized_store_domain()}/admin/oauth/access_token"
        payload = {
            "client_id": cls.CLIENT_ID,
            "client_secret": cls.CLIENT_SECRET,
            "grant_type": "client_credentials",
        }
        resp = req.post(url, json=payload, timeout=cls.TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token", "")
        if not token:
            raise RuntimeError(f"Shopify token alınamadı: {data}")
        expires_in = data.get("expires_in", 86400)
        cls._token_expires_at = time.time() + expires_in - 300  # 5 dk erken yenile
        logger.info("[SHOPIFY] OAuth token alındı (expires_in=%ds)", expires_in)
        return token

    @classmethod
    def get_access_token(cls) -> str:
        """Geçerli access token döndür. Yoksa veya süresi dolmuşsa al."""
        import time

        # Eski statik token varsa onu kullan
        if cls._STATIC_TOKEN:
            return cls._STATIC_TOKEN

        # Yeni yöntem: client credentials
        with cls._token_lock:
            if cls._access_token and time.time() < cls._token_expires_at:
                return cls._access_token
            cls._access_token = cls._obtain_token()
            return cls._access_token

    @classmethod
    def reset_token(cls):
        """Token'ı sıfırla (hata durumunda yeniden almak için)."""
        with cls._token_lock:
            cls._access_token = ""

    @classmethod
    def graphql_url(cls) -> str:
        return f"https://{cls.normalized_store_domain()}/admin/api/{cls.API_VERSION}/graphql.json"

    @classmethod
    def rest_base_url(cls) -> str:
        return f"https://{cls.normalized_store_domain()}/admin/api/{cls.API_VERSION}"

    @classmethod
    def get_headers(cls) -> dict:
        return {
            "X-Shopify-Access-Token": cls.get_access_token(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }