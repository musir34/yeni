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


if __name__ == '__main__':
    print("Etiket editörü başlatılıyor...")
    app.run(host='0.0.0.0', port=8080, debug=False)