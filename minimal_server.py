#!/usr/bin/env python3
"""Minimal Flask server for label editor testing"""
import os
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'test_key_for_labels'

@app.route('/')
def home():
    return "Güllü Shoes Label System - Test Server"

@app.route('/enhanced_product_label')
def enhanced_product_label():
    return render_template('enhanced_product_label.html')

@app.route('/enhanced_product_label/advanced_editor')
def advanced_editor():
    return render_template('advanced_label_editor.html')

@app.route('/api/generate_advanced_label_preview', methods=['POST'])
def generate_advanced_label_preview():
    try:
        from enhanced_product_label import generate_advanced_label_preview_new
        return generate_advanced_label_preview_new()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/save_label_preset', methods=['POST'])
def save_label_preset():
    try:
        from enhanced_product_label import save_label_preset
        return save_label_preset()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting minimal Flask server for label editor...")
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)