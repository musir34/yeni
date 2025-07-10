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


if __name__ == '__main__':
    print("Starting minimal Flask server for label editor...")
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)