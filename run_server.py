#!/usr/bin/env python3
"""
Basit server başlatıcı - ana uygulama çalışmıyorsa alternatif
"""

import subprocess
import sys
import time
import os

def run_main_app():
    """Ana uygulamayı çalıştır"""
    try:
        print("Ana uygulama başlatılıyor...")
        process = subprocess.Popen([
            sys.executable, 'app.py'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # 5 saniye bekle ve durumu kontrol et
        time.sleep(5)
        
        if process.poll() is None:
            print("✅ Uygulama başarıyla çalışıyor!")
            print("Port 8080'de sunuluyor...")
            process.wait()
        else:
            stdout, stderr = process.communicate()
            print("❌ Uygulama başlatılamadı")
            if stderr:
                print(f"Hata: {stderr.decode()}")
            return False
            
    except Exception as e:
        print(f"❌ Başlatma hatası: {e}")
        return False
        
    return True

if __name__ == '__main__':
    success = run_main_app()
    if not success:
        print("Ana uygulama başlatılamadı.")
        sys.exit(1)