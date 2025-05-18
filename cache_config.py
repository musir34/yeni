import os
from flask_caching import Cache

cache = Cache(config={
    "CACHE_TYPE": "RedisCache",  # ✨ DİKKAT: RedisCache büyük harflerle
    "CACHE_REDIS_URL": os.getenv("REDIS_URL"),
    "CACHE_DEFAULT_TIMEOUT": 300
})

# Önbellek süresi ayarları (isteğe bağlı)
CACHE_TIMES = {
    'orders': 300,
    'products': 600,
    'user_data': 1800
}
