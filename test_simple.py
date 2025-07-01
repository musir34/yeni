#!/usr/bin/env python3
from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def hello():
    return 'Test server çalışıyor!'

if __name__ == '__main__':
    print("Basit test server başlatılıyor...")
    app.run(host='0.0.0.0', port=8080, debug=False)