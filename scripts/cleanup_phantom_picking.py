"""
Phantom picking temizligi:
Terfi sirasinda (sync guard eklenmeden onceki pencerede) hem orders_hazirlaniyor hem
orders_picking'e cift dusen, HIC paketlenmemis (picked_by IS NULL) kayitlari siler.
Dogru kopya (orders_hazirlaniyor) korunur.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['ENABLE_JOBS'] = 'off'

import app as A
from models import db, OrderPicking, OrderHazirlaniyor

with A.app.app_context():
    h_nums = {o.order_number for o in OrderHazirlaniyor.query.all()}

    # Silinecekler: picking'te + hazirlaniyor'da da var + hic paketlenmemis
    phantoms = [o for o in OrderPicking.query.all()
                if o.order_number in h_nums and not getattr(o, 'picked_by', None)]

    print(f"Toplam picking: {OrderPicking.query.count()}")
    print(f"Silinecek phantom (picking∩hazirlaniyor & picked_by bos): {len(phantoms)}")
    for o in phantoms:
        print(f"   SIL: {o.order_number}  (id={o.id}, start={o.picking_start_time})")

    if phantoms:
        ids = [o.id for o in phantoms]
        OrderPicking.query.filter(OrderPicking.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        print(f"\n✅ {len(ids)} phantom kayit silindi.")
    else:
        print("\nSilinecek kayit yok.")

    print(f"SONRA -> picking: {OrderPicking.query.count()} | hazirlaniyor: {OrderHazirlaniyor.query.count()}")
