from flask import Flask, send_file
import os

app = Flask(__name__)

@app.route('/')
def index():
    return send_file('test_print.html')

@app.route('/test')
def test():
    return send_file('test_print.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081, debug=True)