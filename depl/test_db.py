
import os
import psycopg2
from psycopg2 import OperationalError

# Veritabanı bağlantı bilgileri
db_params = {
    'dbname': 'neondb',
    'user': 'neondb_owner',
    'password': 'npg_Z0a3kSwtrOJf',
    'host': 'ep-cool-bonus-a64bzq6f.us-west-2.aws.neon.tech',
    'port': '5432',
    'sslmode': 'require'
}

# DATABASE_URL formatı
DATABASE_URL = f"postgresql://{db_params['user']}:{db_params['password']}@{db_params['host']}:{db_params['port']}/{db_params['dbname']}?sslmode=require"

print("Veritabanına bağlanmaya çalışıyorum...")

try:
    # Bağlantıyı dene
    conn = psycopg2.connect(**db_params)
    
    # Bağlantı başarılıysa cursor oluştur
    cursor = conn.cursor()
    
    # Basit bir sorgu çalıştır
    cursor.execute("SELECT version();")
    
    # Sorgu sonucunu al
    db_version = cursor.fetchone()
    
    print(f"PostgreSQL veritabanına başarıyla bağlandı!")
    print(f"PostgreSQL versiyonu: {db_version[0]}")
    
    # Veritabanındaki tabloları listele
    cursor.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name;
    """)
    
    tables = cursor.fetchall()
    
    print("\nVeritabanındaki tablolar:")
    for table in tables:
        print(f"- {table[0]}")
    
    # Bağlantıyı kapat
    cursor.close()
    conn.close()
    print("\nVeritabanı bağlantısı kapatıldı.")
    
except OperationalError as e:
    print(f"Bağlantı hatası: {e}")
except Exception as e:
    print(f"Beklenmeyen hata: {e}")
