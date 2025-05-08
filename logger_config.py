
import logging
import logging.handlers
import os
from datetime import datetime

# Log dizini oluştur
if not os.path.exists('logs'):
    os.makedirs('logs')

def setup_logger(name, log_file, level=logging.INFO):
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler
    file_handler = logging.handlers.RotatingFileHandler(
        f'logs/{log_file}', 
        maxBytes=5*1024*1024,  # 5MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Ana loglayıcıları oluştur
app_logger = setup_logger('app', 'app.log')
order_logger = setup_logger('orders', 'orders.log')
api_logger = setup_logger('api', 'api.log')
frontend_logger = setup_logger('frontend', 'frontend.log')
db_logger = setup_logger('database', 'database.log')
