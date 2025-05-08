
import os
from redis import Redis

redis_client = Redis(
    host=os.environ.get('REDIS_HOST', 'localhost'),
    port=int(os.environ.get('REDIS_PORT', 6379)),
    db=0,
    decode_responses=True
)

# Önbellek süreleri (saniye)
CACHE_TIMES = {
    'orders': 300,  # 5 dakika
    'products': 600,  # 10 dakika
    'user_data': 1800  # 30 dakika
}
