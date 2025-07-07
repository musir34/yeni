#!/usr/bin/env python3
"""Basit etiket editörü sunucusu - sadece gerekli bileşenler"""
import os
import sys
import logging
from flask import Flask, render_template

# Logging ayarları
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask uygulaması
app = Flask(__name__)
app.secret_key = 'gullu_shoes_label_editor'

@app.route('/')
def home():
    return "Güllü Shoes - Etiket Editörü Sistemi Çalışıyor!"


if __name__ == '__main__':
    logger.info("Etiket editörü sunucusu başlatılıyor...")
    try:
        app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Sunucu başlatma hatası: {e}")
        import traceback
        traceback.print_exc()