#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify
from enhanced_product_label import print_multiple_labels

app = Flask(__name__)

@app.route('/enhanced_product_label/api/print_multiple_labels', methods=['POST'])
def debug_print_multiple_labels():
    """Debug API endpoint"""
    print("="*50)
    print("DEBUG: API çağrısı alındı!")
    print("="*50)
    
    data = request.get_json()
    print(f"DEBUG: Gelen veri: {data}")
    
    if data:
        print(f"DEBUG: labels_per_row: {data.get('labels_per_row')}")
        print(f"DEBUG: labels_per_col: {data.get('labels_per_col')}")
        print(f"DEBUG: top_margin: {data.get('top_margin')}")
        print(f"DEBUG: left_margin: {data.get('left_margin')}")
        print(f"DEBUG: horizontal_gap: {data.get('horizontal_gap')}")
        print(f"DEBUG: vertical_gap: {data.get('vertical_gap')}")
        print(f"DEBUG: label_width: {data.get('label_width')}")
        print(f"DEBUG: label_height: {data.get('label_height')}")
        print(f"DEBUG: Labels count: {len(data.get('labels', []))}")
        
    try:
        result = print_multiple_labels()
        print(f"DEBUG: Sonuç: {result}")
        return result
    except Exception as e:
        print(f"DEBUG: HATA: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    print("Debug sunucusu başlatılıyor...")
    app.run(host='0.0.0.0', port=8080, debug=True)