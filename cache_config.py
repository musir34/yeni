
import os
from redis import Redis
from flask_caching import Cache

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

# Flask-Caching nesnesi
cache = Cache(config={
    'CACHE_TYPE': 'redis',
    'CACHE_REDIS_HOST': redis_client.connection_pool.connection_kwargs.get('host', 'localhost'),
    'CACHE_REDIS_PORT': redis_client.connection_pool.connection_kwargs.get('port', 6379),
    'CACHE_REDIS_DB': redis_client.connection_pool.connection_kwargs.get('db', 0)
})
