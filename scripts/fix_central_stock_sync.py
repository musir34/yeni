#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CentralStock tablosunu RafUrun toplamlarıyla senkronize eder.
Adet=0 olan RafUrun kayıtlarını temizler.
"""

import sys
sys.path.insert(0, '/Users/abdurrahmankuli/Documents/Webs/yeni')

from app import app
from models import db, CentralStock, RafUrun
from sqlalchemy import func, text
from datetime import datetime, timezone

def sync_all_central_stock():
    """Tüm CentralStock kayıtlarını raflardaki toplamla senkronize et - SQL ile hızlı"""
    
    print('🔧 CentralStock senkronizasyonu başlıyor...\n')
    
    # 1. Adet 0 veya altı olan RafUrun kayıtlarını sil
    deleted = RafUrun.query.filter(RafUrun.adet <= 0).delete()
    print(f'🗑️ Silinen boş RafUrun kayıtları: {deleted}')
    
    # 2. Raflardaki toplam stokları hesapla
    raf_totals = db.session.query(
        RafUrun.urun_barkodu.label('barcode'),
        func.sum(RafUrun.adet).label('total')
    ).filter(
        RafUrun.adet > 0
    ).group_by(
        RafUrun.urun_barkodu
    ).all()
    
    raf_dict = {r.barcode: int(r.total) for r in raf_totals}
    print(f'📊 Rafta bulunan benzersiz barkod: {len(raf_dict)}')
    
    # 3. CentralStock kayıtlarını güncelle
    fixed_count = 0
    cs_all = CentralStock.query.all()
    
    for cs in cs_all:
        raf_toplam = raf_dict.get(cs.barcode, 0)
        
        if cs.qty != raf_toplam:
            print(f'   ✏️ {cs.barcode}: {cs.qty} → {raf_toplam}')
            cs.qty = raf_toplam
            cs.updated_at = datetime.now(timezone.utc)
            fixed_count += 1
    
    db.session.commit()
    
    print(f'\n✅ Tamamlandı!')
    print(f'   Düzeltilen CentralStock: {fixed_count}')
    
    # Kontrol
    print(f'\n📊 Kontrol (019852370939):')
    cs = CentralStock.query.filter_by(barcode='019852370939').first()
    print(f'   CentralStock: {cs.qty if cs else "yok"}')
    raf = RafUrun.query.filter_by(urun_barkodu='019852370939').all()
    print(f'   RafUrun kayıtları: {len(raf)}')
    
    # Kalan tutarsızlık kontrolü
    print(f'\n📊 Kalan tutarsızlık kontrolü:')
    tutarsiz = 0
    for cs in CentralStock.query.filter(CentralStock.qty > 0).all():
        raf_toplam = raf_dict.get(cs.barcode, 0)
        if cs.qty != raf_toplam:
            tutarsiz += 1
    print(f'   Kalan tutarsız kayıt: {tutarsiz}')


if __name__ == '__main__':
    with app.app_context():
        sync_all_central_stock()
