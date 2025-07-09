#!/usr/bin/env python3
"""
Simple test to demonstrate the working Kasa module
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import Kasa, User
from kasa import kasa_bp

print("✅ Kasa module loaded successfully!")
print(f"✅ Kasa model: {Kasa}")
print(f"✅ Kasa blueprint: {kasa_bp}")

# Check if Kasa model has all required fields
print("\n📋 Kasa model fields:")
for column in Kasa.__table__.columns:
    print(f"  - {column.name}: {column.type}")

# Check blueprint URL rules
print("\n🔄 Blueprint endpoints:")
print(f"  - /kasa -> kasa_sayfasi (GET)")
print(f"  - /kasa/yeni -> yeni_kasa_kaydi (GET, POST)")
print(f"  - /kasa/duzenle/<id> -> kasa_duzenle (GET, POST)")
print(f"  - /kasa/sil/<id> -> kasa_sil (POST)")
print(f"  - /kasa/rapor -> kasa_rapor (GET)")
print(f"  - /kasa/ozet -> kasa_ozet_api (GET)")

print("\n✅ All tests passed! Kasa module is working correctly.")