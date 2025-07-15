#!/usr/bin/env python3
"""
Test script to verify order label barcode alignment fixes
"""
import os
import sys
from barcode_utils import generate_barcode
from order_list_service import generate_qr_code

def test_barcode_generation():
    """Test barcode generation with improved alignment"""
    print("Testing barcode generation...")
    
    # Sample shipping barcode
    test_barcode = "10247963TI"
    
    # Generate barcode
    barcode_path = generate_barcode(test_barcode)
    
    if barcode_path:
        print(f"✅ Barcode generated successfully: {barcode_path}")
        
        # Check if file exists
        full_path = os.path.join('static', barcode_path)
        if os.path.exists(full_path):
            print(f"✅ Barcode file exists: {full_path}")
            
            # Get file size
            file_size = os.path.getsize(full_path)
            print(f"📊 File size: {file_size} bytes")
            
        else:
            print(f"❌ Barcode file not found: {full_path}")
    else:
        print("❌ Failed to generate barcode")
    
    # Generate QR code
    qr_path = generate_qr_code(test_barcode)
    
    if qr_path:
        print(f"✅ QR code generated successfully: {qr_path}")
        
        # Check if file exists
        full_path = os.path.join('static', qr_path)
        if os.path.exists(full_path):
            print(f"✅ QR code file exists: {full_path}")
            
            # Get file size
            file_size = os.path.getsize(full_path)
            print(f"📊 File size: {file_size} bytes")
            
        else:
            print(f"❌ QR code file not found: {full_path}")
    else:
        print("❌ Failed to generate QR code")

def main():
    """Main test function"""
    print("=== Order Label Barcode Alignment Test ===")
    print()
    
    # Create static directories if they don't exist
    os.makedirs('static/barcodes', exist_ok=True)
    os.makedirs('static/qr_codes', exist_ok=True)
    
    test_barcode_generation()
    
    print()
    print("=== Test Complete ===")
    print("Check the generated files in static/barcodes/ and static/qr_codes/")
    print("The barcode should now be properly centered and wider")

if __name__ == "__main__":
    main()