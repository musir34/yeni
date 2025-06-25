#!/usr/bin/env python3
"""Güllü Shoes Label Editor Server"""
import os
import sys
from flask import Flask, render_template, request, jsonify

# Flask app setup
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'gullu_shoes_labels')

@app.route('/')
def home():
    return '''
    <h1>Güllü Shoes - Etiket Editörü</h1>
    <p><a href="/enhanced_product_label/advanced_editor">Drag & Drop Editör</a></p>
    <p>Sistem çalışıyor!</p>
    '''

@app.route('/enhanced_product_label/advanced_editor')
def advanced_editor():
    return render_template('advanced_label_editor.html')

# API endpoints
@app.route('/api/generate_advanced_label_preview', methods=['POST'])
def generate_preview():
    """Etiket önizlemesi oluştur"""
    try:
        # Enhanced product label modülünden fonksiyonu çağır
        from enhanced_product_label import generate_advanced_label_preview_new
        return generate_advanced_label_preview_new()
    except Exception as e:
        return jsonify({'error': f'Önizleme hatası: {str(e)}'}), 500

@app.route('/api/save_label_preset', methods=['POST'])
def save_preset():
    """Etiket presetini kaydet"""
    try:
        from enhanced_product_label import save_label_preset
        return save_label_preset() 
    except Exception as e:
        return jsonify({'error': f'Kaydetme hatası: {str(e)}'}), 500

if __name__ == '__main__':
    print("Güllü Shoes etiket editörü başlatılıyor...")
    print("Erişim: http://localhost:8080/enhanced_product_label/advanced_editor")
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)