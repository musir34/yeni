# config.py - Application configuration classes
import os


def normalize_database_url(database_url):
    if not database_url:
        return database_url

    if database_url.startswith('postgresql://') and '+' not in database_url.split('://', 1)[0]:
        return database_url.replace('postgresql://', 'postgresql+pg8000://', 1)

    return database_url

class BaseConfig:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default_secret')
    SQLALCHEMY_DATABASE_URI = normalize_database_url(os.getenv(
        'DATABASE_URL',
        'sqlite:///app.db'
    ))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

class DevelopmentConfig(BaseConfig):
    DEBUG = True

class ProductionConfig(BaseConfig):
    DEBUG = False

config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
}