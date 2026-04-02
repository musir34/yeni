"""
Barkod Alias (Takma Ad) Yönetim Yardımcıları
═══════════════════════════════════════════════

Bu modül barkod alias sistemini yönetir.
Tüm barkod işlemlerinde normalize_barcode() kullanılmalıdır.
"""

from models import db, BarcodeAlias
from functools import lru_cache


# Türkçe → ASCII karakter dönüşüm tablosu
_TR_MAP = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def strip_turkish(text: str) -> str:
    """Türkçe karakterleri ASCII karşılıklarına çevirir.
    ç→c, ğ→g, ı→i, ö→o, ş→s, ü→u (ve büyük harfler)"""
    if not text:
        return ""
    return text.translate(_TR_MAP)


def normalize_barcode(barcode: str) -> str:
    """
    Verilen barkodu ana barkoda çevirir.
    Eğer alias ise -> ana barkod döner
    Eğer alias değilse -> kendisi döner
    Türkçe karakterli barkodlar ASCII versiyonuyla da eşleşir.

    Örnek:
        normalize_barcode('ABC123')  # 'ABC123' alias ise -> 'XYZ789' döner
        normalize_barcode('XYZ789')  # alias değil -> 'XYZ789' döner (kendisi)
        normalize_barcode('gulluayakkabi5234')  # DB'de 'güllüayakkabı5234' varsa -> onu döner

    Args:
        barcode: Normalize edilecek barkod

    Returns:
        Ana barkod (main_barcode) veya kendisi
    """
    if not barcode:
        return ""

    barcode = str(barcode).strip().replace(" ", "")

    # 1) Tam eşleşme ile alias ara
    alias = BarcodeAlias.query.get(barcode)
    if alias:
        return alias.main_barcode

    # 2) Türkçe karakter farkı kontrolü
    ascii_bc = strip_turkish(barcode)
    if ascii_bc != barcode:
        # Barkodun kendisi Türkçe karakter içeriyor — olduğu gibi dön
        return barcode

    # Okutulan barkod ASCII ama DB'deki Türkçeli olabilir
    # translate() + lower() ile DB tarafında case-insensitive karşılaştır
    from models import Product
    from sqlalchemy import func
    tr_chars = "çğıöşüÇĞİÖŞÜ"
    en_chars = "cgiosuCGIOSU"
    p = Product.query.filter(
        func.lower(func.translate(Product.barcode, tr_chars, en_chars)) == ascii_bc.lower()
    ).first()
    if p:
        return p.barcode

    return barcode


def is_alias(barcode: str) -> bool:
    """
    Verilen barkodun bir alias olup olmadığını kontrol eder.
    
    Args:
        barcode: Kontrol edilecek barkod
        
    Returns:
        True ise alias, False ise ana barkod veya tanımsız
    """
    if not barcode:
        return False
    
    barcode = str(barcode).strip().replace(" ", "")
    return BarcodeAlias.query.get(barcode) is not None


def add_alias(alias_barcode: str, main_barcode: str, created_by: str = None, note: str = None, merge_stocks: bool = True) -> dict:
    """
    Yeni bir barkod alias ekler ve isteğe bağlı olarak stokları birleştirir.
    
    Args:
        alias_barcode: Alternatif (alias) barkod
        main_barcode: Ana (gerçek) barkod
        created_by: Ekleyen kullanıcı
        note: Açıklama (opsiyonel)
        merge_stocks: True ise stokları otomatik birleştirir
        
    Returns:
        {'success': bool, 'message': str, 'stock_merged': dict}
    """
    from models import CentralStock, RafUrun
    
    alias_barcode = str(alias_barcode).strip().replace(" ", "")
    main_barcode = str(main_barcode).strip().replace(" ", "")
    
    if not alias_barcode or not main_barcode:
        return {'success': False, 'message': 'Barkod boş olamaz'}
    
    if alias_barcode == main_barcode:
        return {'success': False, 'message': 'Alias ve ana barkod aynı olamaz'}
    
    # Zaten var mı?
    existing = BarcodeAlias.query.get(alias_barcode)
    if existing:
        return {
            'success': False, 
            'message': f'Bu alias zaten var: {alias_barcode} -> {existing.main_barcode}'
        }
    
    stock_info = {
        'central_merged': 0,
        'raf_merged': 0,
        'raf_details': []
    }
    
    try:
        # 🔥 STOK BİRLEŞTİRME İŞLEMİ
        if merge_stocks:
            # 1. CentralStock'u birleştir
            alias_stock = CentralStock.query.get(alias_barcode)
            main_stock = CentralStock.query.get(main_barcode)
            
            if alias_stock and alias_stock.qty > 0:
                if main_stock:
                    # Ana barkoda ekle
                    main_stock.qty = (main_stock.qty or 0) + alias_stock.qty
                    stock_info['central_merged'] = alias_stock.qty
                else:
                    # Ana barkod için yeni kayıt oluştur
                    main_stock = CentralStock(barcode=main_barcode, qty=alias_stock.qty)
                    db.session.add(main_stock)
                    stock_info['central_merged'] = alias_stock.qty
                
                # Alias'ın CentralStock kaydını sil
                db.session.delete(alias_stock)
            
            # 2. Raf stoklarını birleştir
            alias_raf_items = RafUrun.query.filter_by(urun_barkodu=alias_barcode).all()
            
            for alias_raf in alias_raf_items:
                # Aynı rafta ana barkod var mı?
                main_raf = RafUrun.query.filter_by(
                    raf_kodu=alias_raf.raf_kodu,
                    urun_barkodu=main_barcode
                ).first()
                
                if main_raf:
                    # Varsa miktarı ekle
                    main_raf.adet += alias_raf.adet
                    stock_info['raf_merged'] += alias_raf.adet
                    stock_info['raf_details'].append({
                        'raf': alias_raf.raf_kodu,
                        'merged': alias_raf.adet,
                        'action': 'merged'
                    })
                else:
                    # Yoksa barkodu değiştir (ana barkod yap)
                    alias_raf.urun_barkodu = main_barcode
                    stock_info['raf_merged'] += alias_raf.adet
                    stock_info['raf_details'].append({
                        'raf': alias_raf.raf_kodu,
                        'moved': alias_raf.adet,
                        'action': 'moved'
                    })
        
        # Yeni alias oluştur
        new_alias = BarcodeAlias(
            alias_barcode=alias_barcode,
            main_barcode=main_barcode,
            created_by=created_by,
            note=note
        )
        
        db.session.add(new_alias)
        db.session.commit()
        
        message = f'Alias eklendi: {alias_barcode} -> {main_barcode}'
        if merge_stocks and (stock_info['central_merged'] > 0 or stock_info['raf_merged'] > 0):
            message += f"\n📦 Stoklar birleştirildi: Merkez {stock_info['central_merged']}, Raf {stock_info['raf_merged']} adet"
        
        return {
            'success': True, 
            'message': message,
            'stock_merged': stock_info
        }
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'message': f'Hata: {str(e)}'}


def remove_alias(alias_barcode: str) -> dict:
    """
    Bir barkod alias'ı siler.
    
    Args:
        alias_barcode: Silinecek alias
        
    Returns:
        {'success': bool, 'message': str}
    """
    alias_barcode = str(alias_barcode).strip().replace(" ", "")
    
    alias = BarcodeAlias.query.get(alias_barcode)
    if not alias:
        return {'success': False, 'message': 'Alias bulunamadı'}
    
    try:
        db.session.delete(alias)
        db.session.commit()
        return {'success': True, 'message': f'Alias silindi: {alias_barcode}'}
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'message': f'Hata: {str(e)}'}


def get_all_aliases(main_barcode: str = None) -> list:
    """
    Tüm alias'ları listeler veya belirli bir ana barkoda ait alias'ları getirir.
    
    Args:
        main_barcode: Filtre için ana barkod (opsiyonel)
        
    Returns:
        List of BarcodeAlias objects
    """
    if main_barcode:
        main_barcode = str(main_barcode).strip().replace(" ", "")
        return BarcodeAlias.query.filter_by(main_barcode=main_barcode).all()
    
    return BarcodeAlias.query.all()


def get_alias_info(barcode: str) -> dict:
    """
    Bir barkod hakkında detaylı bilgi döner.
    
    Args:
        barcode: Sorgulanacak barkod
        
    Returns:
        {
            'is_alias': bool,
            'main_barcode': str,
            'aliases': [str, ...],  # Eğer ana barkodsa, tüm alias'ları
            'note': str
        }
    """
    barcode = str(barcode).strip().replace(" ", "")
    
    # Bu bir alias mi?
    alias = BarcodeAlias.query.get(barcode)
    if alias:
        return {
            'is_alias': True,
            'main_barcode': alias.main_barcode,
            'aliases': [],
            'note': alias.note
        }
    
    # Ana barkod ise, tüm alias'larını getir
    aliases = BarcodeAlias.query.filter_by(main_barcode=barcode).all()
    return {
        'is_alias': False,
        'main_barcode': barcode,
        'aliases': [a.alias_barcode for a in aliases],
        'note': None
    }


def merge_existing_alias_stocks(alias_barcode: str) -> dict:
    """
    Mevcut bir alias'ın stokunu ana barkoda birleştir.
    Alias kaydını silmez, sadece stokları taşır.
    
    Args:
        alias_barcode: Stokları birleştirilecek alias barkod
        
    Returns:
        {'success': bool, 'message': str, 'stock_merged': dict}
    """
    from models import CentralStock, RafUrun
    
    alias_barcode = str(alias_barcode).strip().replace(" ", "")
    
    # Alias var mı kontrol et
    alias = BarcodeAlias.query.get(alias_barcode)
    if not alias:
        return {'success': False, 'message': 'Alias bulunamadı'}
    
    main_barcode = alias.main_barcode
    stock_merged = {'central_merged': 0, 'raf_merged': 0, 'raf_details': []}
    
    try:
        # 1. Merkez stok birleştirme
        alias_stock = CentralStock.query.get(alias_barcode)
        main_stock = CentralStock.query.get(main_barcode)
        
        if alias_stock and alias_stock.qty > 0:
            if main_stock:
                main_stock.qty += alias_stock.qty
            else:
                # Ana barkod için stok kaydı yoksa oluştur
                main_stock = CentralStock(barcode=main_barcode, qty=alias_stock.qty)
                db.session.add(main_stock)
            
            stock_merged['central_merged'] = alias_stock.qty
            
            # Alias stok kaydını sil
            db.session.delete(alias_stock)
        
        # 2. Raf stokları birleştirme
        alias_raf_stocks = RafUrun.query.filter_by(urun_barkodu=alias_barcode).all()
        
        for raf_stock in alias_raf_stocks:
            # Aynı rafta ana barkod var mı?
            main_raf = RafUrun.query.filter_by(
                raf_kodu=raf_stock.raf_kodu,
                urun_barkodu=main_barcode
            ).first()
            
            if main_raf:
                # Birleştir
                main_raf.adet += raf_stock.adet
                db.session.delete(raf_stock)  # Eski kaydı sil
                stock_merged['raf_details'].append({
                    'raf': raf_stock.raf_kodu,
                    'adet': raf_stock.adet,
                    'action': 'merged'
                })
            else:
                # Taşı (barkod değiştir)
                raf_stock.urun_barkodu = main_barcode
                stock_merged['raf_details'].append({
                    'raf': raf_stock.raf_kodu,
                    'adet': raf_stock.adet,
                    'action': 'moved'
                })
            
            stock_merged['raf_merged'] += raf_stock.adet
        
        db.session.commit()
        
        message = f'✅ Stoklar başarıyla birleştirildi: {alias_barcode} → {main_barcode}\n'
        message += f'📦 Merkez: {stock_merged["central_merged"]} adet\n'
        message += f'📦 Raf: {stock_merged["raf_merged"]} adet'
        
        return {
            'success': True,
            'message': message,
            'stock_merged': stock_merged
        }
        
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'message': f'Hata: {str(e)}'}
