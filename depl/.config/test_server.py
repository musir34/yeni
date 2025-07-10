#!/usr/bin/env python3
from flask import Flask, render_template
import os

app = Flask(__name__)
app.secret_key = 'test_key'

@app.route('/')
def home():
    return "Test server working!"

@app.route('/enhanced_product_label')
def enhanced_product_label():
    return render_template('enhanced_product_label.html')

@app.route('/enhanced_product_label/advanced_editor')
def advanced_editor():
    return render_template('advanced_label_editor.html')

if __name__ == '__main__':
    print("Starting test server...")
    app.run(host='0.0.0.0', port=8080, debug=False)