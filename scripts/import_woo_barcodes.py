"""
CSV -> products.woo_barcode importer

Expected CSV columns: product_id,barcode
product_id = WooCommerce product_id (integer)
barcode = gerçek ürün barkodu (string)

Usage:
    .venv/bin/python scripts/import_woo_barcodes.py /path/to/mapping.csv

Behavior:
- Tries to match each product_id to an existing Product using these heuristics (in order):
  1) Product.product_main_id == str(product_id)
  2) Product.platform_listing_id == str(product_id)
  3) Product.product_code == str(product_id)
  4) Product.barcode == barcode
- If a product is matched, sets product.woo_product_id and product.woo_barcode
- Commits every 100 updates
"""
import csv
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from models import db, Product


def match_and_update(product_id, barcode):
    # Try multiple heuristics to find product
    q = None
    if product_id is None:
        return False, 'no_product_id'
    pid_str = str(product_id)

    q = Product.query.filter_by(product_main_id=pid_str).first()
    if not q:
        q = Product.query.filter_by(platform_listing_id=pid_str).first()
    if not q:
        q = Product.query.filter_by(product_code=pid_str).first()
    if not q:
        q = Product.query.filter_by(barcode=barcode).first()

    if not q:
        return False, 'not_found'

    q.woo_product_id = int(product_id)
    q.woo_barcode = barcode
    return True, q.barcode


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: import_woo_barcodes.py /path/to/mapping.csv')
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f'File not found: {csv_path}')
        sys.exit(1)

    with app.app_context():
        updated = 0
        skipped = 0
        not_found = 0
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, start=1):
                product_id = row.get('product_id') or row.get('productId') or row.get('id')
                barcode = (row.get('barcode') or row.get('barkod') or row.get('sku') or '').strip()
                if not product_id or not barcode:
                    skipped += 1
                    continue

                ok, info = match_and_update(product_id, barcode)
                if ok:
                    updated += 1
                else:
                    if info == 'not_found':
                        not_found += 1
                    else:
                        skipped += 1

                if (i % 100) == 0:
                    db.session.commit()
                    print(f'Processed {i} rows, updated={updated}, not_found={not_found}, skipped={skipped}')

        db.session.commit()
        print(f'Done. updated={updated}, not_found={not_found}, skipped={skipped}')
