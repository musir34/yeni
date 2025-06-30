#!/bin/bash
cd /home/runner/workspace
echo "Starting Güllü Shoes Label Editor..."
python -c "
from flask import Flask, render_template
import os

app = Flask(__name__)
app.secret_key = 'gullu_labels'

@app.route('/')
def home():
    return '''<h1>Güllü Shoes Etiket Sistemi</h1>
    <p><a href=\"/editor\">Editöre Git</a></p>'''

@app.route('/editor')  
def editor():
    return render_template('advanced_label_editor.html')

print('Server starting on port 8080...')
app.run(host='0.0.0.0', port=8080, debug=False)
" &

echo "Server started in background"
sleep 5
curl -s http://localhost:8080 | head -1