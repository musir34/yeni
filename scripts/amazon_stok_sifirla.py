#!/usr/bin/env python3
"""Amazon'daki TÜM ürünlerin stoğunu bir kereliğine 0 gönderir.

Amazon'da satış istenmiyor. Stok gönderimi stock_sync/service.py içinde
DISABLED_PLATFORMS ile kapatıldı; bu betik kapatmadan SONRA bir kez çalıştırılır
ki Amazon'da açık stok kalmasın. Panel DB'sine YAZMAZ, yalnız Amazon'a gönderir.

Kapsam: products.amazon_sku dolu olan her ürün (CentralStock satırı olsun olmasın).

ÖNEMLİ: Önce yeni kod sunucuda canlı olmalı (git pull + restart). Eski kod
çalışırken 0 gönderilirse 3 dakikalık otomatik senkron gerçek stoğu geri yazar.

Çalıştırma:
    DISABLE_JOBS=1 python scripts/amazon_stok_sifirla.py            # kuru çalıştırma (göndermez)
    DISABLE_JOBS=1 python scripts/amazon_stok_sifirla.py --gonder   # gerçekten 0 gönderir
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")


async def _gonder(adapter, items):
    try:
        return await adapter.send_all_stocks(
            items,
            progress_callback=lambda sent, total: print(f"  {sent}/{total} gönderildi"),
        )
    finally:
        await adapter.close_session()


def main():
    gonder = "--gonder" in sys.argv[1:]

    from app import app
    from models import Product
    from stock_sync.adapters.amazon import AmazonAdapter
    from stock_sync.adapters.base import StockItem

    with app.app_context():
        products = Product.query.filter(
            Product.amazon_sku.isnot(None),
            Product.amazon_sku != ''
        ).all()

        # Aynı seller SKU'ya iki kez istek atma
        sku_to_barcode = {}
        for p in products:
            sku = p.amazon_sku.strip()
            if sku and sku not in sku_to_barcode:
                sku_to_barcode[sku] = p.barcode

        items = [
            StockItem(barcode=barcode, quantity=0, sku=sku)
            for sku, barcode in sku_to_barcode.items()
        ]
        print(f"Amazon seller SKU'su olan ürün: {len(items)}")

        if not items:
            print("Gönderilecek ürün yok.")
            return

        if not gonder:
            print("KURU ÇALIŞTIRMA: hiçbir şey gönderilmedi. Göndermek için --gonder ekle.")
            for item in items[:10]:
                print(f"  örnek: barkod={item.barcode} sku={item.sku} -> 0")
            return

        adapter = AmazonAdapter()
        if not adapter.is_configured:
            print("HATA: Amazon yapılandırılmamış (.env AMAZON_* eksik). Gönderilmedi.")
            sys.exit(1)

        results = asyncio.run(_gonder(adapter, items))

        hatalar = [r for r in results if not r.success]
        print(f"Bitti. Başarılı: {len(results) - len(hatalar)}, Hatalı: {len(hatalar)}")
        for r in hatalar:
            print(f"  HATA barkod={r.barcode}: {r.error_message}")
        if hatalar:
            sys.exit(1)


if __name__ == "__main__":
    main()
