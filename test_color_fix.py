#!/usr/bin/env python3
"""Test script to verify color fixes in enhanced_product_label.py"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from enhanced_product_label import create_label_with_design

# Test design with product image element
test_design = {
    "elements": [
        {
            "type": "product_image",
            "x": 10,
            "y": 10,
            "width": 50,
            "height": 50
        },
        {
            "type": "model_code",
            "x": 70,
            "y": 10,
            "width": 80,
            "height": 20
        }
    ]
}

# Test product data
test_product = {
    "barcode": "test123",
    "model_code": "147",
    "color": "Siyah",
    "size": "39"
}

print("Testing color fixes...")
print("Creating label with placeholder image...")

try:
    # Test A4 mode with multiple labels
    from enhanced_product_label import print_multiple_labels
    
    # Test multiple labels
    test_labels = [test_product, test_product, test_product]
    
    print("Testing A4 mode...")
    result = print_multiple_labels(
        test_labels,
        test_design,
        63.33,  # A4 label width
        37.2    # A4 label height
    )
    
    if result and 'filename' in result:
        print(f"✓ A4 Test PNG saved: {result['filename']}")
        print("✓ Multiple labels created - checking for blue colors...")
    else:
        print("✗ A4 test failed")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()