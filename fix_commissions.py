"""
Komisyonu eksik siparişleri Trendyol API'den tekrar çekip güncelleyen script.
Tüm erişilebilir siparişleri statü bazlı sayfalama ile çeker.

Kullanım:
    python3.11 fix_commissions.py
    python3.11 fix_commissions.py --dry-run
"""
import os
import sys
import time
import asyncio
import aiohttp
import base64
import argparse
import logging

os.environ['ENABLE_JOBS'] = '0'

from dotenv import load_dotenv
load_dotenv()

from app import app
from models import db
from order_service import process_all_orders

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SUPPLIER_ID = os.getenv("SUPPLIER_ID")
BASE_URL = "https://api.trendyol.com/sapigw/"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("fix_commissions.log"),
    ]
)
logger = logging.getLogger("fix_commissions")


async def fetch_all_orders_by_status(status):
    """Belirli statüdeki TÜM siparişleri Trendyol API'den sayfalama ile çeker."""
    auth_str = f"{API_KEY}:{API_SECRET}"
    b64_auth = base64.b64encode(auth_str.encode()).decode('utf-8')
    url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/orders"
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/json"
    }

    all_orders = []
    page = 0
    total_pages = 1

    async with aiohttp.ClientSession() as session:
        while page < total_pages:
            params = {
                "status": status,
                "page": page,
                "size": 200,
                "orderByField": "CreatedDate",
                "orderByDirection": "DESC"
            }

            try:
                async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        logger.error(f"  API Hatası {resp.status}: {error[:200]}")
                        break

                    data = await resp.json()
                    content = data.get('content', []) or []
                    all_orders.extend(content)
                    total_pages = data.get('totalPages', 1)
                    total_elements = data.get('totalElements', 0)

                    if page == 0:
                        logger.info(f"  API toplam: {total_elements} sipariş, {total_pages} sayfa")

                    if page % 5 == 0 and page > 0:
                        logger.info(f"  Sayfa {page + 1}/{total_pages} — {len(all_orders)} sipariş")

            except Exception as e:
                logger.error(f"  Sayfa {page + 1} hatası: {e}")

            page += 1

            # Rate limit koruması
            if page % 20 == 0:
                await asyncio.sleep(1)

    return all_orders


def main():
    parser = argparse.ArgumentParser(description="Komisyonu eksik siparişleri Trendyol API'den düzelt")
    parser.add_argument("--dry-run", action="store_true", help="Sadece kaç sipariş çekileceğini göster")
    args = parser.parse_args()

    statuses = ["Delivered", "Shipped", "Created", "Picking", "Cancelled"]

    logger.info(f"{'='*60}")
    logger.info(f"Komisyon Düzeltme Script'i Başlıyor")
    logger.info(f"SUPPLIER_ID: {SUPPLIER_ID}")
    logger.info(f"Statüler: {', '.join(statuses)}")
    logger.info(f"{'='*60}")

    with app.app_context():
        grand_total_fetched = 0
        grand_total_processed = 0

        for status in statuses:
            logger.info(f"\n{'─'*40}")
            logger.info(f"Statü: {status}")

            orders = asyncio.run(fetch_all_orders_by_status(status))
            grand_total_fetched += len(orders)
            logger.info(f"  {len(orders)} sipariş çekildi")

            if args.dry_run:
                # Dry run: komisyon bilgisi var mı kontrol et
                has_comm = 0
                for o in orders:
                    for line in o.get('lines', []):
                        if line.get('commission') and float(line.get('commission', 0)) > 0:
                            has_comm += 1
                            break
                logger.info(f"  Komisyon bilgisi olan: {has_comm}/{len(orders)}")
                continue

            if not orders:
                logger.info("  İşlenecek sipariş yok")
                continue

            try:
                process_all_orders(orders)
                grand_total_processed += len(orders)
                logger.info(f"  {len(orders)} sipariş işlendi")
            except Exception as e:
                logger.error(f"  İşleme hatası: {e}")

            time.sleep(2)

        logger.info(f"\n{'='*60}")
        if args.dry_run:
            logger.info(f"DRY RUN — Toplam erişilebilir: {grand_total_fetched} sipariş")
        else:
            logger.info(f"TAMAMLANDI — Çekilen: {grand_total_fetched}, İşlenen: {grand_total_processed}")
        logger.info(f"{'='*60}")

        # Komisyon durumu özeti
        from sqlalchemy import text
        logger.info(f"\n--- Komisyon Durumu Özeti ---")
        for tbl in ['orders_created', 'orders_picking', 'orders_shipped', 'orders_delivered']:
            total = db.session.execute(text(f'SELECT COUNT(*) FROM {tbl}')).scalar()
            no_comm = db.session.execute(text(f'SELECT COUNT(*) FROM {tbl} WHERE commission IS NULL OR commission = 0')).scalar()
            logger.info(f"  {tbl}: {total} toplam, {total - no_comm} komisyonlu, {no_comm} komisyonsuz")


if __name__ == "__main__":
    main()
