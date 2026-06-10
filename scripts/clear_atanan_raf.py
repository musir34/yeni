#!/usr/bin/env python3
"""Eski OTOMATİK raf atamalarını (atanan_raf) temizler.

Manuel raf-okutmalı toplamaya geçildiği için, eskiden otomatik atanmış
`atanan_raf` değerleri artık yanıltıcı (siparis_hazirla ekranında "sistem
önerisi"/"raf boşalmış" uyarısı üretir). Bu script aktif sipariş
tablolarındaki atanan_raf'ı NULL yapar. Stok/raf verisine DOKUNMAZ.

Çalıştırma:
    DISABLE_JOBS=1 python scripts/clear_atanan_raf.py            # sadece say (dry-run)
    DISABLE_JOBS=1 python scripts/clear_atanan_raf.py --confirm  # uygula
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")


def main():
    confirm = "--confirm" in sys.argv
    from app import app
    from models import db, OrderCreated, OrderHazirlaniyor

    with app.app_context():
        targets = [("orders_created", OrderCreated), ("orders_hazirlaniyor", OrderHazirlaniyor)]
        total = 0
        for name, model in targets:
            n = model.query.filter(model.atanan_raf.isnot(None)).count()
            total += n
            print(f"  {name}: atanan_raf dolu = {n}")
            if confirm and n:
                model.query.filter(model.atanan_raf.isnot(None)).update(
                    {model.atanan_raf: None}, synchronize_session=False
                )
        if confirm:
            db.session.commit()
            print(f"✅ Toplam {total} siparişin atanan_raf değeri TEMİZLENDİ (NULL).")
        else:
            print(f"DRY-RUN — toplam {total} kayıt etkilenecek. Uygulamak için --confirm ekle.")


if __name__ == "__main__":
    main()
