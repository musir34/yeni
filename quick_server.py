#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, '.')

from flask import Flask, render_template, request, jsonify
from PIL import Image, ImageDraw, ImageFont
import io
import base64

app = Flask(__name__)
app.secret_key = 'label_editor_key'

@app.route('/')
def home():
    return "Güllü Shoes - Etiket Editörü Çalışıyor!"

@app.route('/enhanced_product_label/advanced_editor')
def advanced_editor():
    return render_template('advanced_label_editor.html')

@app.route('/api/generate_advanced_label_preview', methods=['POST'])
def generate_preview():
    try:
        data = request.json
        # Basit bir önizleme oluştur
        img = Image.new('RGB', (400, 200), 'white')
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "Önizleme Hazır", fill='black')
        
        # Base64 encode
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'image': f'data:image/png;base64,{img_str}'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Etiket editörü başlatılıyor...")
    app.run(host='0.0.0.0', port=8080, debug=False)